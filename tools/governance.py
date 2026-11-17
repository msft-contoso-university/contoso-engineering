#!/usr/bin/env python3
"""Check story structure and human acceptance without giving an agent authority."""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

OWNER = "msft-contoso-university"
REPOSITORIES = frozenset(f"{OWNER}/contoso-{name}" for name in (
    "engineering", "platform", "web", "students", "academics", "enrollments"
))
SECTIONS = (
    "user story", "goal", "scope", "acceptance criteria", "verification",
    "affected repositories", "risk and rollback",
)
PLACEHOLDER = re.compile(r"^(?:_?no response_?|todo|tbd|n/a|none|\.\.\.)[.!]?$", re.I)
LINK = re.compile(
    r"(?im)^\s*(?:closes|fixes|resolves)\s+"
    r"(?:(?P<url>https://github\.com/)(?P<url_repo>[\w.-]+/[\w.-]+)/issues/"
    r"|(?P<repo>[\w.-]+/[\w.-]+)?#)(?P<number>[1-9]\d*)\s*$"
)


def story_errors(body):
    sections = {}
    errors = []
    current = None
    for line in (body or "").splitlines():
        heading = re.fullmatch(r"#{2,3}\s+([^#]+?)\s*#*\s*", line)
        if heading:
            current = heading.group(1).strip().lower()
            if current in sections:
                errors.append(f"duplicate section: {current}")
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    for name in SECTIONS:
        content = "\n".join(sections.get(name, [])).strip()
        if not content or PLACEHOLDER.fullmatch(content):
            errors.append(f"missing substantive section: {name}")
    criteria = [
        match.group(1).strip()
        for line in sections.get("acceptance criteria", [])
        if (match := re.match(r"^\s*[-*]\s+\[[ xX]\]\s+(.+)$", line))
    ]
    if not criteria or any(PLACEHOLDER.fullmatch(item) for item in criteria):
        errors.append("acceptance criteria require substantive task-list items")
    affected = "\n".join(sections.get("affected repositories", []))
    tokens = re.findall(r"msft-contoso-university/contoso-[a-z-]+", affected)
    if not tokens or any(token not in REPOSITORIES for token in tokens):
        errors.append("affected repositories must name allowlisted full repository names")
    return errors


def linked_stories(body, repository):
    if repository not in REPOSITORIES:
        raise ValueError(f"repository is not allowlisted: {repository}")
    result = set()
    for match in LINK.finditer(body or ""):
        target = match["url_repo"] or match["repo"] or repository
        if target not in REPOSITORIES:
            raise ValueError(f"linked story is not allowlisted: {target}")
        result.add((target, int(match["number"])))
    if not 1 <= len(result) <= 4:
        raise ValueError("PR needs 1-4 story links on separate 'Closes #123' lines")
    return sorted(result)


def api(path, paginate=False):
    command = ["gh", "api", path]
    if paginate:
        command += ["--paginate", "--slurp"]
    response = subprocess.run(command, capture_output=True, text=True, check=False)
    if response.returncode:
        raise ValueError(f"GitHub API request failed for {path}; exit {response.returncode}")
    return json.loads(response.stdout)


def check_pr(repository, number, read=api):
    if repository not in REPOSITORIES or number < 1:
        raise ValueError("invalid repository or pull request number")
    pull = read(f"repos/{repository}/pulls/{number}")
    accepted = []
    for target, issue_number in linked_stories(pull.get("body"), repository):
        issue = read(f"repos/{target}/issues/{issue_number}")
        if "pull_request" in issue or issue.get("state") != "open":
            raise ValueError(f"{target}#{issue_number} must be an open issue, not a PR")
        errors = story_errors(issue.get("body"))
        if errors:
            raise ValueError(f"{target}#{issue_number}: " + "; ".join(errors))
        if "ready-for-agent" not in {label["name"] for label in issue.get("labels", [])}:
            raise ValueError(f"{target}#{issue_number} is not human-accepted (ready-for-agent)")
        pages = read(f"repos/{target}/issues/{issue_number}/timeline?per_page=100", paginate=True)
        events = [event for page in pages for event in page
                  if event.get("event") == "labeled"
                  and event.get("label", {}).get("name") == "ready-for-agent"]
        actor = events[-1].get("actor") if events else None
        if not actor or actor.get("type") != "User" or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9-]{0,38}", actor.get("login", "")
        ):
            raise ValueError(f"{target}#{issue_number}: acceptance must be by an identifiable human")
        permission = read(f"repos/{target}/collaborators/{actor['login']}/permission")
        if permission.get("permission") not in {"admin", "maintain", "write"}:
            raise ValueError(f"{target}#{issue_number}: accepting human lacks repository write access")
        accepted.append({"repository": target, "issue": issue_number, "accepted_by": actor["login"]})
    return {"structural_validation": "passed", "human_acceptance": accepted}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    story = commands.add_parser("check-story")
    story.add_argument("--body-file", type=Path, required=True)
    pull = commands.add_parser("check-pr")
    pull.add_argument("--repository", required=True)
    pull.add_argument("--number", type=int, required=True)
    args = parser.parse_args()
    try:
        if args.command == "check-story":
            errors = story_errors(args.body_file.read_text(encoding="utf-8"))
            result = {"structural_validation": "failed" if errors else "passed", "errors": errors,
                      "human_acceptance": "not evaluated"}
        else:
            result = check_pr(args.repository, args.number)
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(f"governance error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 1 if result.get("errors") else 0


if __name__ == "__main__":
    sys.exit(main())
