"""Verify pinned runtime inputs and complete, non-skipped software integration evidence."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

from consumer_checks import NAMESPACE, verify_results

ROOT = Path(__file__).resolve().parents[1]
SERVICES = {"web", "students", "academics", "enrollments"}
CASES = {
    "WebJourneyPersistsEnrollmentAndGradeAcrossRealServices",
    "ReaderCannotWriteThroughWebOrDirectApi",
    "AppOnlyIdentityCannotWriteDelegatedEnrollment",
    "MissingStudentReference",
    "MissingCourseReference",
    "UpstreamTransportFailureIsVisibleAndDoesNotPersist",
    "WrongAudienceDoesNotReachEnrollmentWrites",
}


def candidates(value):
    if not isinstance(value, dict) or set(value) != {"version", "status", "services"}:
        raise ValueError("invalid runtime candidate manifest")
    if type(value["version"]) is not int or value["version"] != 1 or value["status"] != "candidate-only-not-release":
        raise ValueError("runtime sources are candidates, not approved releases")
    refs = value["services"]
    if not isinstance(refs, dict) or set(refs) != SERVICES:
        raise ValueError("all four runtime sources must be pinned")
    if any(not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha) for sha in refs.values()):
        raise ValueError("runtime sources require full immutable commit SHAs")
    return refs


def verify_sources(refs, directory):
    for service, sha in refs.items():
        root = Path(directory) / f"contoso-{service}"
        if root.is_symlink() or not root.is_dir():
            raise ValueError("runtime source directory missing or linked")
        observed = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"], check=True, text=True, capture_output=True
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain"], check=True, text=True, capture_output=True
        ).stdout.strip()
        if observed != sha or dirty:
            raise ValueError(f"{service} source does not match the clean immutable pin")


def verify_runtime(directory):
    result = verify_results(directory)
    names = []
    for path in Path(directory).rglob("*.trx"):
        root = ET.parse(path).getroot()
        summary = root.find("t:ResultSummary", NAMESPACE)
        if summary is None or summary.get("outcome") not in {"Completed", "Passed"}:
            raise ValueError("runtime test run did not complete successfully")
        names.extend(item.get("testName") for item in root.findall(".//t:UnitTestResult", NAMESPACE))
    if not CASES.issubset(names) or len(names) != len(set(names)):
        raise ValueError("required runtime journeys/refusals are missing or duplicated")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["pins", "sources", "results"])
    parser.add_argument("--directory", type=Path)
    args = parser.parse_args()
    try:
        refs = candidates(json.loads((ROOT / "contracts/runtime-candidates.json").read_text()))
        if args.command == "pins":
            with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
                for service, sha in sorted(refs.items()):
                    output.write(f"{service}={sha}\n")
        elif args.command == "sources":
            if args.directory is None:
                raise ValueError("source directory is required")
            verify_sources(refs, args.directory)
        else:
            if args.directory is None:
                raise ValueError("evidence directory is required")
            result = verify_runtime(args.directory)
            (args.directory / "runtime-evidence.json").write_text(json.dumps({
                "status": "software-integration-only-not-release-or-cloud-proof",
                "sources": refs, "harnessCommit": os.environ.get("GITHUB_SHA"), **result,
            }, indent=2) + "\n")
            print(json.dumps(result))
    except (OSError, KeyError, ValueError, TypeError, ET.ParseError, subprocess.CalledProcessError) as error:
        print(f"runtime evidence error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
