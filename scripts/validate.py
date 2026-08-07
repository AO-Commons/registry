#!/usr/bin/env python3
"""Validate registry records against the schema.

Checks every file in data/aos/ (plus the reference record in schema/) for
schema conformance, and the invariants the schema itself can't express:
filename matches `id`, ids are unique, and registry.json agrees with the
individual records.

Usage:  python3 scripts/validate.py
Requires: pip install jsonschema pyyaml
"""

import json
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker

from airtable_fields import RegistryLoader

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "schema" / "ao.schema.json"
EXAMPLE_PATH = ROOT / "schema" / "example.yml"
DATA_DIR = ROOT / "data" / "aos"
BUNDLE_PATH = ROOT / "data" / "registry.json"


errors: list[str] = []


def error(path: Path, message: str) -> None:
    errors.append(f"{path.relative_to(ROOT)}: {message}")


def load(path: Path):
    try:
        return yaml.load(path.read_text(), Loader=RegistryLoader)
    except yaml.YAMLError as exc:
        error(path, f"is not valid YAML: {exc}")
        return None


def check_schema(validator, path: Path, record) -> None:
    for problem in sorted(validator.iter_errors(record), key=lambda e: list(e.path)):
        location = ".".join(str(p) for p in problem.path) or "(root)"
        error(path, f"{location}: {problem.message}")


def main() -> int:
    schema = json.loads(SCHEMA_PATH.read_text())
    validator = Draft202012Validator(schema, format_checker=FormatChecker())

    # The reference record is checked too — a schema change that invalidates
    # the documented example means the docs are now wrong.
    example = load(EXAMPLE_PATH)
    if isinstance(example, dict):
        check_schema(validator, EXAMPLE_PATH, example)

    files = sorted(DATA_DIR.glob("*.yml")) + sorted(DATA_DIR.glob("*.yaml"))
    seen_ids: dict[str, Path] = {}

    for path in files:
        record = load(path)
        if record is None:
            continue
        if not isinstance(record, dict):
            error(path, "should contain a single record object")
            continue

        check_schema(validator, path, record)

        record_id = record.get("id")
        if isinstance(record_id, str):
            if record_id != path.stem:
                error(path, f"id '{record_id}' does not match filename '{path.stem}'")
            if record_id in seen_ids:
                error(path, f"duplicate id '{record_id}', also in {seen_ids[record_id].name}")
            else:
                seen_ids[record_id] = path

    # The bundle is generated, so a mismatch means a sync ran halfway.
    if BUNDLE_PATH.exists():
        try:
            bundle = json.loads(BUNDLE_PATH.read_text())
        except json.JSONDecodeError as exc:
            error(BUNDLE_PATH, f"is not valid JSON: {exc}")
        else:
            bundle_ids = {r.get("id") for r in bundle.get("organizations", [])}
            if bundle_ids != set(seen_ids):
                detail = []
                if missing := sorted(set(seen_ids) - bundle_ids):
                    detail.append(f"missing {missing}")
                if extra := sorted(bundle_ids - set(seen_ids)):
                    detail.append(f"unexpected {extra}")
                error(BUNDLE_PATH, "out of sync with data/aos/: " + "; ".join(detail))

    if errors:
        print(f"{len(errors)} problem(s) found:\n", file=sys.stderr)
        for message in errors:
            print(f"  {message}", file=sys.stderr)
        return 1

    if not files:
        print("Schema and reference record valid. No records in data/aos/ yet.")
    else:
        print(f"Schema, reference record, and {len(files)} registry record(s) valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
