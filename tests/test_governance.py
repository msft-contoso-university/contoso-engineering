import copy
import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "governance", Path(__file__).resolve().parents[1] / "tools" / "governance.py"
)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

BODY = """### User story
As a registrar, I want to find students by surname so that enrollment takes fewer steps.
### Goal
Find a seeded student by exact surname without opening each student record.
### Scope
Students lookup and its web consumer; no new data fields or public data.
### Acceptance criteria
- [ ] An existing exact surname returns the expected synthetic student.
- [ ] An unknown surname returns an empty result without a server error.
### Verification
Run the Students lookup tests and the web lookup integration test.
### Affected repositories
msft-contoso-university/contoso-students
msft-contoso-university/contoso-web
### Risk and rollback
Read-only change; revert the artifact if lookup failures rise.
"""
REPO = "msft-contoso-university/contoso-engineering"


class StoryTests(unittest.TestCase):
    def test_complete_structure_is_not_human_acceptance(self):
        self.assertEqual(gate.story_errors(BODY), [])
        issue = {"body": BODY, "state": "open", "labels": []}
        with self.assertRaisesRegex(ValueError, "not human-accepted"):
            gate.check_pr(REPO, 1, self.reader(issue))

    def test_missing_goal_and_placeholder_criteria_fail(self):
        body = BODY.replace("### Goal", "### Removed goal")
        self.assertTrue(any("goal" in error for error in gate.story_errors(body)))
        body = BODY[:BODY.index("### Acceptance criteria")] + """### Acceptance criteria
- [ ] TODO
"""
        self.assertIn("acceptance criteria require substantive task-list items", gate.story_errors(body))

    def test_duplicate_sections_and_unknown_repositories_fail(self):
        body = BODY + "\n### Goal\nA different goal.\n"
        self.assertIn("duplicate section: goal", gate.story_errors(body))
        self.assertTrue(gate.story_errors(BODY.replace("contoso-web", "contoso-unknown")))

    def test_links_are_bounded_and_scoped(self):
        self.assertEqual(gate.linked_stories("Closes #12", REPO), [(REPO, 12)])
        self.assertEqual(
            gate.linked_stories(f"Fixes https://github.com/{REPO}/issues/12", REPO), [(REPO, 12)]
        )
        for body in ["Please merge", "Closes outsider/private#12", "\n".join(
            f"Closes #{number}" for number in range(1, 6)
        )]:
            with self.subTest(body=body), self.assertRaises(ValueError):
                gate.linked_stories(body, REPO)

    @staticmethod
    def reader(issue=None, actor_type="User", permission="write", timeline=True):
        issue = copy.deepcopy(issue or {
            "body": BODY, "state": "open", "labels": [{"name": "ready-for-agent"}]
        })

        def read(path, paginate=False):
            if "/pulls/" in path:
                return {"body": "Closes #12"}
            if "/timeline?" in path:
                return [[{"event": "labeled", "label": {"name": "ready-for-agent"},
                          "actor": {"type": actor_type, "login": "maintainer"}}]] if timeline else [[]]
            if "/collaborators/" in path:
                return {"permission": permission}
            return issue
        return read

    def test_human_with_write_access_can_accept(self):
        result = gate.check_pr(REPO, 1, self.reader())
        self.assertEqual(result["human_acceptance"][0]["accepted_by"], "maintainer")

    def test_bot_read_only_user_or_missing_audit_event_cannot_accept(self):
        for options in [{"actor_type": "Bot"}, {"permission": "read"}, {"timeline": False}]:
            with self.subTest(options=options), self.assertRaises(ValueError):
                gate.check_pr(REPO, 1, self.reader(**options))

    def test_closed_issues_and_pr_links_cannot_substitute_for_stories(self):
        for issue in [{"body": BODY, "state": "closed"},
                      {"body": BODY, "state": "open", "pull_request": {}}]:
            with self.subTest(issue=issue), self.assertRaisesRegex(ValueError, "open issue"):
                gate.check_pr(REPO, 1, self.reader(issue))


if __name__ == "__main__":
    unittest.main()
