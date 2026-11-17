import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import runtime_checks


class RuntimeChecksTests(unittest.TestCase):
    def test_missing_floating_or_unknown_sources_fail(self):
        baseline = json.loads((runtime_checks.ROOT / "contracts/runtime-candidates.json").read_text())
        for mutation in ("missing", "floating", "unknown"):
            value = copy.deepcopy(baseline)
            if mutation == "missing":
                del value["services"]["web"]
            elif mutation == "floating":
                value["services"]["web"] = "main"
            else:
                value["services"]["unapproved"] = "a" * 40
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                runtime_checks.candidates(value)

    def test_incomplete_or_skipped_runtime_evidence_is_rejected(self):
        for mutation in ("complete", "missing", "skipped"):
            names = sorted(runtime_checks.CASES)
            if mutation == "missing":
                names.pop()
            results = "".join(
                f'<UnitTestResult testName="{name}" outcome="{"NotExecuted" if mutation == "skipped" and index == 0 else "Passed"}"/>'
                for index, name in enumerate(names)
            )
            total = len(names)
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                Path(directory, "runtime.trx").write_text(
                    '<TestRun xmlns="http://microsoft.com/schemas/VisualStudio/TeamTest/2010">'
                    f'<Results>{results}</Results><ResultSummary outcome="Completed">'
                    f'<Counters total="{total}" passed="{total}"/></ResultSummary></TestRun>'
                )
                if mutation == "complete":
                    self.assertEqual(total, runtime_checks.verify_runtime(directory)["testsPassed"])
                else:
                    with self.assertRaises(ValueError):
                        runtime_checks.verify_runtime(directory)
