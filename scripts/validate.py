#!/usr/bin/env python3
"""Validate published records against their schemas.

Checks every file in each collection's data directory — plus the reference
records in schema/ — for schema conformance, and the invariants the schema
itself can't express: filename matches `id`, ids are unique within a
collection, and each JSON bundle agrees with its directory.

Usage:  python3 scripts/validate.py
Requires: pip install jsonschema pyyaml
"""

import json
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker

from airtable_fields import COLLECTIONS, RegistryLoader

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_DIR = ROOT / "schema"
DATA_ROOT = ROOT / "data"

# Reference records, checked alongside real ones: a schema change that
# invalidates the documented example means the docs are now wrong.
EXAMPLES = {
    "registry": "example.yml",
    "tooling": "example-tool.yml",
}

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
    total = 0

    for spec in COLLECTIONS:
        schema = json.loads((SCHEMA_DIR / spec.schema_file).read_text())
        validator = Draft202012Validator(schema, format_checker=FormatChecker())

        example_path = SCHEMA_DIR / EXAMPLES[spec.key]
        if example_path.exists():
            example = load(example_path)
            if isinstance(example, dict):
                check_schema(validator, example_path, example)
        else:
            errors.append(f"schema/{EXAMPLES[spec.key]}: missing reference record")

        data_dir = DATA_ROOT / spec.data_dir
        files = sorted(data_dir.glob("*.yml")) + sorted(data_dir.glob("*.yaml"))
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
        bundle_path = DATA_ROOT / spec.bundle
        if bundle_path.exists():
            try:
                bundle = json.loads(bundle_path.read_text())
            except json.JSONDecodeError as exc:
                error(bundle_path, f"is not valid JSON: {exc}")
            else:
                bundle_ids = {r.get("id") for r in bundle.get(spec.key, [])}
                if bundle_ids != set(seen_ids):
                    detail = []
                    if missing := sorted(set(seen_ids) - bundle_ids):
                        detail.append(f"missing {missing}")
                    if extra := sorted(bundle_ids - set(seen_ids)):
                        detail.append(f"unexpected {extra}")
                    error(bundle_path, f"out of sync with data/{spec.data_dir}/: " + "; ".join(detail))

        total += len(files)

    if errors:
        print(f"{len(errors)} problem(s) found:\n", file=sys.stderr)
        for message in errors:
            print(f"  {message}", file=sys.stderr)
        return 1

    collections = ", ".join(spec.key for spec in COLLECTIONS)
    if total:
        print(f"Schemas, reference records, and {total} published record(s) valid ({collections}).")
    else:
        print(f"Schemas and reference records valid ({collections}). No published records yet.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
