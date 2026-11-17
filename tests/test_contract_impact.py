import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("contract_impact", ROOT / "tools" / "contract_impact.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
sys.path.insert(0, str(ROOT / "tools"))
import consumer_checks


class ContractImpactTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((ROOT / "contracts" / "dependencies.json").read_text(encoding="utf-8"))

    def test_selects_all_consumers_and_deduplicates(self):
        result = module.select(self.manifest, "contoso-students", [
            "contracts/students.openapi.yaml", "contracts\\students.openapi.yaml", "src/Student.cs"
        ])
        self.assertEqual(result, [
            {"repository": "contoso-enrollments", "test": "students-contract"},
            {"repository": "contoso-web", "test": "students-contract"}
        ])

    def test_unrelated_change_selects_no_consumer_tests(self):
        self.assertEqual(module.select(self.manifest, "contoso-web", ["src/Index.cs"]), [])

    def test_unknown_contract_or_repository_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "unmapped contract"):
            module.select(self.manifest, "contoso-students", ["contracts/new.yaml"])
        with self.assertRaisesRegex(ValueError, "not allowlisted"):
            module.select(self.manifest, "other-repo", [])

    def test_rejects_traversal_and_absolute_paths(self):
        for path in ["../contracts/students.openapi.yaml", "/contracts/a.yaml", "C:\\contracts\\a.yaml"]:
            with self.subTest(path=path), self.assertRaises(ValueError):
                module.select(self.manifest, "contoso-students", [path])

    def test_rejects_invalid_and_duplicate_mapping(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["contracts"].append(copy.deepcopy(manifest["contracts"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate contract"):
            module.select(manifest, "contoso-students", [])
        manifest = copy.deepcopy(self.manifest)
        manifest["contracts"][0]["consumers"] = []
        with self.assertRaisesRegex(ValueError, "no consumers"):
            module.select(manifest, "contoso-students", [])


class ConsumerCheckTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((ROOT / "contracts/dependencies.json").read_text(encoding="utf-8"))
        self.candidates = {
            "version": 1, "status": "candidate-only-not-release",
            "consumers": {
                name: {"commit": character * 40, "project": f"tests/{name}/Tests.csproj"}
                for name, character in (("contoso-web", "a"), ("contoso-enrollments", "b"))
            },
        }

    def test_selects_all_consumers_with_exact_candidate_pins(self):
        rows = consumer_checks.plan(
            self.manifest, self.candidates, "msft-contoso-university/contoso-academics"
        )["include"]
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["commit"], "b" * 40)
        self.assertEqual(rows[1]["repository"], "msft-contoso-university/contoso-web")
        only_web = consumer_checks.plan(
            self.manifest, self.candidates, "msft-contoso-university/contoso-enrollments"
        )["include"]
        self.assertEqual([row["repository"] for row in only_web], ["msft-contoso-university/contoso-web"])

    def test_rejects_foreign_or_nonproducer_caller(self):
        for repository in ("other/contoso-academics", "msft-contoso-university/contoso-web"):
            with self.subTest(repository=repository), self.assertRaises(ValueError):
                consumer_checks.plan(self.manifest, self.candidates, repository)

    def test_removed_or_unmapped_producer_contract_cannot_skip_consumers(self):
        for paths in ([], ["contracts/academics.openapi.yaml", "contracts/new-api.yaml"]):
            with self.subTest(paths=paths), self.assertRaises(ValueError):
                consumer_checks.plan(self.manifest, self.candidates,
                                     "msft-contoso-university/contoso-academics", paths)

    def test_rejects_missing_mutable_or_unsafe_consumer_pin(self):
        for field, value in (("commit", "main"), ("project", "tests/../run.csproj"),
                             ("project", "tests/a.csproj\ninjected=true")):
            candidate = copy.deepcopy(self.candidates)
            candidate["consumers"]["contoso-web"][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                consumer_checks.plan(self.manifest, candidate, "msft-contoso-university/contoso-academics")
        del self.candidates["consumers"]["contoso-web"]
        with self.assertRaises(ValueError):
            consumer_checks.plan(self.manifest, self.candidates, "msft-contoso-university/contoso-academics")

    def test_requires_executed_passing_tests_not_just_successful_command(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "results.trx"
            for total, passed, outcome, expected in ((1, 1, "Passed", True),
                                                    (0, 0, "Passed", False),
                                                    (1, 0, "Failed", False),
                                                    (1, 0, "NotExecuted", False)):
                path.write_text(
                    '<TestRun xmlns="http://microsoft.com/schemas/VisualStudio/TeamTest/2010">'
                    f'<Results><UnitTestResult outcome="{outcome}"/></Results>'
                    f'<ResultSummary><Counters total="{total}" passed="{passed}"/></ResultSummary>'
                    '</TestRun>', encoding="utf-8"
                )
                with self.subTest(outcome=outcome, total=total):
                    if expected:
                        self.assertEqual(consumer_checks.verify_results(temporary)["testsPassed"], 1)
                    else:
                        with self.assertRaises(ValueError):
                            consumer_checks.verify_results(temporary)
            path.unlink()
            with self.assertRaises(ValueError):
                consumer_checks.verify_results(temporary)
            path.write_text("<invalid", encoding="utf-8")
            with self.assertRaises(consumer_checks.ET.ParseError):
                consumer_checks.verify_results(temporary)


if __name__ == "__main__":
    unittest.main()
