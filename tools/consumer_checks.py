"""Plan pinned, read-only consumer checks and reject absent/failed test evidence."""

import argparse
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

from contract_impact import canonical_path, select

ROOT = Path(__file__).resolve().parents[1]
SHA = re.compile(r"[0-9a-f]{40}\Z")
PROJECT = re.compile(r"tests/[A-Za-z0-9_./-]+\.csproj\Z")
NAMESPACE = {"t": "http://microsoft.com/schemas/VisualStudio/TeamTest/2010"}


def plan(manifest, candidates, repository, contract_files=None):
    if not isinstance(repository, str) or not repository.startswith("msft-contoso-university/"):
        raise ValueError("caller must be an allowlisted Contoso producer")
    if not isinstance(manifest, dict):
        raise ValueError("contract manifest must be an object")
    producer = repository.removeprefix("msft-contoso-university/")
    if not isinstance(candidates, dict) or set(candidates) != {"version", "status", "consumers"}:
        raise ValueError("invalid candidate lock fields")
    if type(candidates["version"]) is not int or candidates["version"] != 1:
        raise ValueError("unsupported candidate lock version")
    if candidates["status"] != "candidate-only-not-release":
        raise ValueError("consumer candidates must not be presented as approved releases")
    locks = candidates["consumers"]
    if not isinstance(locks, dict) or set(locks) != {"contoso-web", "contoso-enrollments"}:
        raise ValueError("the complete consumer allowlist must be pinned")
    for lock in locks.values():
        if not isinstance(lock, dict) or set(lock) != {"commit", "project"}:
            raise ValueError("invalid consumer pin")
        if not isinstance(lock["commit"], str) or not SHA.fullmatch(lock["commit"]):
            raise ValueError("consumer commit must be a full immutable SHA")
        project = canonical_path(lock["project"])
        if not PROJECT.fullmatch(project):
            raise ValueError("consumer project must be a tests csproj")
    # Check every mapped consumer even for implementation-only response changes.
    changed = [
        item["path"] for item in manifest.get("contracts", [])
        if isinstance(item, dict) and item.get("producer") == producer
    ]
    if contract_files is not None:
        if not set(changed).issubset(contract_files):
            raise ValueError("a mapped producer contract has been removed")
        changed = contract_files
    checks = select(manifest, producer, changed)
    if not checks:
        raise ValueError("caller has no mapped producer contract")
    rows = []
    for name in sorted({item["repository"] for item in checks}):
        if name not in locks:
            raise ValueError(f"consumer is not pinned: {name}")
        rows.append({"repository": f"msft-contoso-university/{name}", **locks[name]})
    return {"include": rows}


def verify_results(directory):
    directory = Path(directory)
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("test evidence directory is missing or linked")
    files = sorted(directory.rglob("*.trx"))
    if not 1 <= len(files) <= 20:
        raise ValueError("expected 1-20 TRX reports")
    passed = 0
    for path in files:
        if path.is_symlink() or not 1 <= path.stat().st_size <= 5_000_000:
            raise ValueError("invalid test evidence file")
        root = ET.parse(path).getroot()
        counters = root.find(".//t:Counters", NAMESPACE)
        results = root.findall(".//t:UnitTestResult", NAMESPACE)
        if counters is None:
            raise ValueError("TRX counters are missing")
        total = int(counters.get("total", "0"))
        count = int(counters.get("passed", "0"))
        if total <= 0 or count != total or len(results) != total:
            raise ValueError("no tests executed, or tests failed/skipped")
        if any(result.get("outcome") != "Passed" for result in results):
            raise ValueError("a consumer test did not pass")
        for field in ("failed", "error", "timeout", "aborted", "notExecuted", "inconclusive"):
            if int(counters.get(field, "0")) != 0:
                raise ValueError(f"nonpassing test counter: {field}")
        passed += count
    return {"reports": len(files), "testsPassed": passed}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    planner = commands.add_parser("plan")
    planner.add_argument("--repository", required=True)
    planner.add_argument("--producer-root", type=Path, required=True)
    planner.add_argument("--manifest", type=Path, default=ROOT / "contracts/dependencies.json")
    planner.add_argument("--candidates", type=Path, default=ROOT / "contracts/consumer-candidates.json")
    verifier = commands.add_parser("verify-results")
    verifier.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "plan":
            contracts = args.producer_root / "contracts"
            if contracts.is_symlink() or not contracts.is_dir():
                raise ValueError("producer contracts directory is missing or linked")
            files = sorted(contracts.rglob("*"))
            if len(files) > 100 or any(path.is_symlink() for path in files):
                raise ValueError("producer contracts exceed bounds or contain links")
            result = plan(
                json.loads(args.manifest.read_text(encoding="utf-8")),
                json.loads(args.candidates.read_text(encoding="utf-8")),
                args.repository,
                [path.relative_to(args.producer_root).as_posix() for path in files if path.is_file()],
            )
        else:
            result = verify_results(args.directory)
    except (OSError, ValueError, TypeError, ET.ParseError) as error:
        print(f"consumer check error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
