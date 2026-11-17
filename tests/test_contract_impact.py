import copy
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("contract_impact", ROOT / "tools" / "contract_impact.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


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


if __name__ == "__main__":
    unittest.main()
