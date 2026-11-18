"""Bind service PR runtime checks to immutable sources and complete test evidence."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

from governance import api
from runtime_checks import CASES, SERVICES, candidates, verify_runtime, verify_sources

OWNER = "msft-contoso-university"
STATUS = "service-pr-software-integration-only-not-release-or-cloud-proof"


def commit(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{40}", value) or value == "0" * 40:
        raise ValueError("source must be a full nonzero immutable commit SHA")
    return value


def context(service, sha, repository, event_name, event, harness, run_id, attempt):
    if not isinstance(service, str) or service not in SERVICES:
        raise ValueError("candidate service is not allowlisted")
    expected = f"{OWNER}/contoso-{service}"
    if repository != expected or event_name != "pull_request":
        raise ValueError("runtime caller must be the candidate service pull_request workflow")
    pull = event.get("pull_request", {})
    number = event.get("number")
    if (
        not isinstance(pull, dict)
        or type(number) is not int or number <= 0
        or pull.get("base", {}).get("repo", {}).get("full_name") != expected
        or pull.get("head", {}).get("sha") != commit(sha)
    ):
        raise ValueError("candidate must match the exact service PR head, not a merge SHA")
    if any(not isinstance(value, str) or not re.fullmatch(r"[1-9][0-9]*", value)
           for value in (run_id, attempt)):
        raise ValueError("run ID and attempt are required")
    return {
        "version": 1, "status": STATUS,
        "candidateService": service, "candidateRepository": expected,
        "candidatePrNumber": number, "candidateSha": sha,
        "harnessCommit": commit(harness), "runId": run_id, "runAttempt": attempt,
    }


def resolve(context_value, read=api):
    refs = {}
    for service in sorted(SERVICES):
        repository = f"{OWNER}/contoso-{service}"
        if service == context_value["candidateService"]:
            sha = context_value["candidateSha"]
        else:
            ref = read(f"repos/{repository}/git/ref/heads/main")
            if (ref.get("ref") != "refs/heads/main"
                    or ref.get("object", {}).get("type") != "commit"):
                raise ValueError(f"{service} main must resolve directly to a commit")
            sha = commit(ref.get("object", {}).get("sha"))
        observed = read(f"repos/{repository}/git/commits/{sha}")
        if observed.get("sha") != sha:
            raise ValueError(f"{service} resolved commit is missing or mismatched")
        refs[service] = sha
    return {**context_value, "sources": refs}


def validate_plan(value, expected):
    if not isinstance(value, dict) or set(value) != set(expected) | {"sources"}:
        raise ValueError("runtime source plan is incomplete or unrecognized")
    stable_context = {key: item for key, item in expected.items() if key != "runAttempt"}
    if any(value[key] != item for key, item in stable_context.items()):
        raise ValueError("runtime source plan belongs to another PR, harness or run")
    if not isinstance(value["runAttempt"], str) or not re.fullmatch(r"[1-9][0-9]*", value["runAttempt"]):
        raise ValueError("runtime source plan has an invalid resolver attempt")
    refs = candidates({
        "version": 1, "status": "candidate-only-not-release", "services": value["sources"],
    })
    for sha in refs.values():
        commit(sha)
    if refs[expected["candidateService"]] != expected["candidateSha"]:
        raise ValueError("runtime candidate source differs from the PR head")
    return refs


def source_evidence(plan, expected, directory):
    refs = validate_plan(plan, expected)
    verify_sources(refs, directory)
    return {**plan, "runAttempt": expected["runAttempt"], "checkedOutSources": dict(refs)}


def runtime_evidence(plan, expected, checked, directory):
    refs = validate_plan(plan, expected)
    if checked != {
        **plan, "runAttempt": expected["runAttempt"], "checkedOutSources": refs,
    }:
        raise ValueError("verified checkout evidence is missing or mismatched")
    result = verify_runtime(directory)
    return {
        **checked, **result,
        "requiredTests": {name: "Passed" for name in sorted(CASES)},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["resolve", "sources", "results"])
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    try:
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
        expected = context(
            os.environ["CANDIDATE_SERVICE"], os.environ["CANDIDATE_SHA"],
            os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_EVENT_NAME"], event,
            os.environ["HARNESS_COMMIT"], os.environ["GITHUB_RUN_ID"],
            os.environ["GITHUB_RUN_ATTEMPT"],
        )
        harness = subprocess.run(
            ["git", "-C", str(Path(__file__).resolve().parents[1]), "rev-parse", "HEAD"],
            check=True, text=True, capture_output=True,
        ).stdout.strip()
        if harness != expected["harnessCommit"]:
            raise ValueError("harness checkout differs from the reviewed control commit")
        if args.command == "resolve":
            plan = resolve(expected)
            validate_plan(plan, expected)
            with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
                output.write(f"plan={json.dumps(plan, separators=(',', ':'))}\n")
                for service, sha in sorted(plan["sources"].items()):
                    output.write(f"{service}={sha}\n")
        else:
            if args.directory is None or args.evidence is None:
                raise ValueError("source/result directory and evidence directory are required")
            plan = json.loads(os.environ["RUNTIME_PLAN"])
            if args.command == "sources":
                checked = source_evidence(plan, expected, args.directory)
                args.evidence.mkdir(parents=True, exist_ok=True)
                (args.evidence / "source-evidence.json").write_text(
                    json.dumps(checked, indent=2) + "\n", encoding="utf-8",
                )
            else:
                checked = json.loads(
                    (args.evidence / "source-evidence.json").read_text(encoding="utf-8")
                )
                result = runtime_evidence(plan, expected, checked, args.directory)
                (args.evidence / "runtime-evidence.json").write_text(
                    json.dumps(result, indent=2) + "\n", encoding="utf-8",
                )
                print(json.dumps(result))
    except (OSError, KeyError, ValueError, TypeError, AttributeError,
            ET.ParseError, subprocess.CalledProcessError) as error:
        print(f"service PR runtime evidence error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
