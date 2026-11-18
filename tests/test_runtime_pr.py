import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import runtime_pr


class RuntimePrTests(unittest.TestCase):
    def context(self, service="web", **changes):
        values = {
            "service": service, "sha": "a" * 40,
            "repository": f"{runtime_pr.OWNER}/contoso-{service}",
            "event_name": "pull_request",
            "event": {"number": 13, "pull_request": {
                "base": {"repo": {"full_name": f"{runtime_pr.OWNER}/contoso-{service}"}},
                "head": {"sha": "a" * 40},
            }},
            "harness": "b" * 40, "run_id": "1234", "attempt": "2",
        }
        return runtime_pr.context(**{**values, **changes})

    @staticmethod
    def reader(path):
        if path.endswith("/git/ref/heads/main"):
            return {"ref": "refs/heads/main", "object": {"type": "commit", "sha": "c" * 40}}
        return {"sha": path.rsplit("/", 1)[1]}

    def test_each_service_tests_exact_pr_head_and_resolves_three_mains(self):
        for service in sorted(runtime_pr.SERVICES):
            with self.subTest(service=service):
                read = unittest.mock.Mock(side_effect=self.reader)
                expected = self.context(service)
                plan = runtime_pr.resolve(expected, read)
                refs = runtime_pr.validate_plan(plan, expected)
                self.assertEqual(refs[service], "a" * 40)
                self.assertEqual(set(refs), runtime_pr.SERVICES)
                self.assertEqual(sum(call.args[0].endswith("/git/ref/heads/main")
                                     for call in read.call_args_list), 3)
                self.assertFalse(any(f"contoso-{service}/git/ref" in call.args[0]
                                     for call in read.call_args_list))
                self.assertEqual(set(refs.values()), {"a" * 40, "c" * 40})

    def test_wrong_caller_event_merge_sha_and_missing_context_fail(self):
        for changes in (
            {"service": "unknown"}, {"repository": f"{runtime_pr.OWNER}/contoso-students"},
            {"event_name": "workflow_dispatch"}, {"event_name": "pull_request_target"},
            {"sha": "d" * 40}, {"sha": "main"}, {"sha": "0" * 40},
            {"harness": "main"}, {"run_id": ""}, {"attempt": "0"}, {"event": {}},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.context(**changes)

    def test_missing_floating_mismatched_and_tag_resolution_fail(self):
        for response in (
            {}, {"ref": "refs/heads/main", "object": {"type": "commit", "sha": "main"}},
            {"ref": "refs/heads/main", "object": {"type": "tag", "sha": "c" * 40}},
            {"ref": "refs/heads/other", "object": {"type": "commit", "sha": "c" * 40}},
            {"sha": "d" * 40},
        ):
            with self.subTest(response=response), self.assertRaises(ValueError):
                runtime_pr.resolve(self.context(), lambda path: response)

    def test_api_failure_does_not_fall_back_to_frozen_candidates(self):
        with self.assertRaisesRegex(ValueError, "unavailable"):
            runtime_pr.resolve(self.context(), unittest.mock.Mock(side_effect=ValueError("unavailable")))

    def test_plan_cannot_drop_replace_or_add_sources_or_rebind_run(self):
        expected = self.context()
        baseline = runtime_pr.resolve(expected, self.reader)
        for mutation in ("missing", "unknown", "floating", "candidate", "run", "harness"):
            plan = copy.deepcopy(baseline)
            if mutation == "missing":
                del plan["sources"]["students"]
            elif mutation == "unknown":
                plan["sources"]["unapproved"] = "e" * 40
            elif mutation == "floating":
                plan["sources"]["students"] = "main"
            elif mutation == "candidate":
                plan["sources"]["web"] = "e" * 40
            elif mutation == "run":
                plan["runAttempt"] = "1"
            else:
                plan["harnessCommit"] = "e" * 40
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                runtime_pr.validate_plan(plan, expected)

    def test_verified_sources_and_runtime_evidence_are_bound_to_plan(self):
        expected = self.context()
        plan = runtime_pr.resolve(expected, self.reader)
        with patch.object(runtime_pr, "verify_sources") as verify:
            checked = runtime_pr.source_evidence(plan, expected, Path("services"))
        verify.assert_called_once_with(plan["sources"], Path("services"))
        with patch.object(runtime_pr, "verify_runtime", return_value={"reports": 1, "testsPassed": 7}):
            report = runtime_pr.runtime_evidence(plan, expected, checked, Path("results"))
        self.assertEqual(plan["sources"], report["checkedOutSources"])
        self.assertEqual(expected["runId"], report["runId"])
        self.assertEqual(expected["harnessCommit"], report["harnessCommit"])
        self.assertEqual({name: "Passed" for name in runtime_pr.CASES}, report["requiredTests"])
        self.assertEqual(7, report["testsPassed"])
        for value in ({}, plan, {**checked, "checkedOutSources": {"web": "d" * 40}}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                runtime_pr.runtime_evidence(plan, expected, value, Path("results"))
        with patch.object(runtime_pr, "verify_sources", side_effect=ValueError("mismatch")):
            with self.assertRaisesRegex(ValueError, "mismatch"):
                runtime_pr.source_evidence(plan, expected, Path("services"))

    def test_missing_failed_skipped_or_zero_results_cannot_make_runtime_evidence(self):
        expected = self.context()
        plan = runtime_pr.resolve(expected, self.reader)
        checked = {**plan, "checkedOutSources": dict(plan["sources"])}
        for outcome in ("missing", "Failed", "NotExecuted", "zero", "partial", "duplicate", "aborted"):
            with self.subTest(outcome=outcome), tempfile.TemporaryDirectory() as directory:
                names = sorted(runtime_pr.CASES)
                if outcome == "zero":
                    names = []
                elif outcome == "partial":
                    names.pop()
                elif outcome == "duplicate":
                    names.append(names[0])
                results = "".join(
                    f'<UnitTestResult testName="{name}" outcome="'
                    f'{"Passed" if index > 0 or outcome not in ("Failed", "NotExecuted") else outcome}"/>'
                    for index, name in enumerate(names)
                )
                if outcome != "missing":
                    Path(directory, "runtime.trx").write_text(
                        '<TestRun xmlns="http://microsoft.com/schemas/VisualStudio/TeamTest/2010">'
                        f'<Results>{results}</Results><ResultSummary outcome="'
                        f'{"Aborted" if outcome == "aborted" else "Completed"}">'
                        f'<Counters total="{len(names)}" passed="{len(names)}"/>'
                        '</ResultSummary></TestRun>'
                    )
                with self.assertRaises(ValueError):
                    runtime_pr.runtime_evidence(plan, expected, checked, directory)

    def test_actual_checkout_mismatch_dirty_or_missing_fails(self):
        expected = self.context()
        plan = runtime_pr.resolve(expected, self.reader)
        with tempfile.TemporaryDirectory() as directory:
            for service in runtime_pr.SERVICES:
                Path(directory, f"contoso-{service}").mkdir()
            for sha, dirty in (("d" * 40, ""), ("c" * 40, " M source.cs")):
                def git(command, **kwargs):
                    service = Path(command[2]).name.removeprefix("contoso-")
                    output = sha if command[3] == "rev-parse" else dirty
                    if command[3] == "rev-parse" and service == "web":
                        output = "a" * 40
                    return runtime_pr.subprocess.CompletedProcess(command, 0, stdout=output)
                with self.subTest(sha=sha, dirty=dirty), patch(
                    "runtime_checks.subprocess.run", side_effect=git,
                ), self.assertRaises(ValueError):
                    runtime_pr.source_evidence(plan, expected, directory)
        with self.assertRaises(ValueError):
            runtime_pr.source_evidence(plan, expected, directory)


if __name__ == "__main__":
    unittest.main()
