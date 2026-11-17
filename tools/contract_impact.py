#!/usr/bin/env python3
"""Select explicitly mapped consumer checks for changed API contracts."""

import argparse
import json
import re
import sys
from pathlib import Path, PurePosixPath

MANIFEST = Path(__file__).resolve().parents[1] / "contracts" / "dependencies.json"
NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def canonical_path(value):
    if not isinstance(value, str) or not value:
        raise ValueError("file path must be a non-empty string")
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or any(part in (".", "..") for part in normalized.split("/")):
        raise ValueError(f"invalid repository-relative path: {value}")
    if str(path) != normalized or ":" in normalized:
        raise ValueError(f"invalid repository-relative path: {value}")
    return normalized


def select(manifest, repository, changed_files):
    if not isinstance(manifest, dict) or set(manifest) != {"version", "repositories", "contracts"}:
        raise ValueError("invalid manifest fields")
    if manifest["version"] != 1 or isinstance(manifest["version"], bool):
        raise ValueError("unsupported manifest version")
    repos = manifest["repositories"]
    if not isinstance(repos, list) or not repos or any(
        not isinstance(item, str) or not NAME.fullmatch(item) for item in repos
    ) or len(set(repos)) != len(repos):
        raise ValueError("invalid repository allowlist")
    if repository not in repos:
        raise ValueError(f"repository is not allowlisted: {repository}")
    contracts = manifest["contracts"]
    if not isinstance(contracts, list) or not contracts:
        raise ValueError("manifest must contain contracts")
    index = {}
    for contract in contracts:
        if not isinstance(contract, dict) or set(contract) != {"producer", "path", "consumers"}:
            raise ValueError("invalid contract entry")
        producer = contract["producer"]
        path = canonical_path(contract["path"])
        if producer not in repos or not path.startswith("contracts/"):
            raise ValueError("contract producer or path is invalid")
        key = (producer, path)
        if key in index:
            raise ValueError(f"duplicate contract: {producer}:{path}")
        consumers = contract["consumers"]
        if not isinstance(consumers, list) or not consumers:
            raise ValueError(f"contract has no consumers: {producer}:{path}")
        checks = set()
        for consumer in consumers:
            if not isinstance(consumer, dict) or set(consumer) != {"repository", "test"}:
                raise ValueError("invalid consumer entry")
            target, test = consumer["repository"], consumer["test"]
            if target not in repos or target == producer or not isinstance(test, str) or not NAME.fullmatch(test):
                raise ValueError("invalid consumer or test identifier")
            if (target, test) in checks:
                raise ValueError("duplicate consumer check")
            checks.add((target, test))
        index[key] = checks
    required = set()
    for raw_path in changed_files:
        path = canonical_path(raw_path)
        key = (repository, path)
        if path.startswith("contracts/") and key not in index:
            raise ValueError(f"unmapped contract file: {repository}:{path}")
        required.update(index.get(key, ()))
    return [{"repository": repo, "test": test} for repo, test in sorted(required)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--changed-file", action="append", default=[])
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    args = parser.parse_args()
    try:
        with args.manifest.open(encoding="utf-8") as file:
            manifest = json.load(file)
        result = select(manifest, args.repository, args.changed_file)
    except (OSError, json.JSONDecodeError, ValueError, TypeError) as error:
        print(f"contract impact error: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"required_consumer_tests": result}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
