#!/usr/bin/env python3
"""Regenerate data/ from the Airtable registry base.

Airtable is the source of truth; this script produces the published mirror.
Reads every Registry record with Published checked, writes one YAML per
record plus a combined registry.json, and removes files whose records are no
longer published.

Records that fail schema validation are skipped and reported rather than
written — one malformed row shouldn't block every other update — but the
skip is always visible in the run summary, never silent.

Usage:  python3 scripts/sync_from_airtable.py
Env:    AIRTABLE_TOKEN, AIRTABLE_BASE_ID
Requires: pip install jsonschema pyyaml requests
"""

import json
import os
import sys
from pathlib import Path

import requests
import yaml
from jsonschema import Draft202012Validator, FormatChecker

from airtable_fields import (
    COMMA_LIST_FIELDS,
    KEY_ORDER,
    LINK_FIELDS,
    MULTI_SELECT_FIELDS,
    ONCHAIN_CHECKBOX,
    ONCHAIN_LIST_FIELDS,
    REGISTRY_TABLE,
    SCHEMA_VERSION,
    SIMPLE_FIELDS,
    SOURCE_FIELDS,
    SOURCES_TABLE,
    VERIFICATION_FIELDS,
)

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "schema" / "ao.schema.json"
DATA_DIR = ROOT / "data" / "aos"
BUNDLE_PATH = ROOT / "data" / "registry.json"
API = "https://api.airtable.com/v0"

# An Airtable filter typo or an API page returning empty should not quietly
# empty the registry. Below this many existing records we don't guess.
DELETION_GUARD_MIN_RECORDS = 5
DELETION_GUARD_FRACTION = 0.25

report_lines: list[str] = []


def report(line: str) -> None:
    print(line)
    report_lines.append(line)


def fetch_all(base_id: str, table: str, token: str) -> list[dict]:
    """Page through a table. Airtable caps pages at 100 records."""
    records, offset = [], None
    while True:
        params = {"pageSize": 100}
        if offset:
            params["offset"] = offset
        response = requests.get(
            f"{API}/{base_id}/{table}",
            headers={"Authorization": f"Bearer {token}"},
            params=params,
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        records.extend(payload.get("records", []))
        offset = payload.get("offset")
        if not offset:
            return records


def split_list(value, separator: str = ",") -> list[str]:
    if not value:
        return []
    return [part.strip() for part in str(value).split(separator) if part.strip()]


def build_record(row: dict, sources_by_id: dict[str, dict]) -> dict:
    """Map one Airtable row onto a schema-shaped dict."""
    fields = row.get("fields", {})
    record: dict = {"schema_version": SCHEMA_VERSION}

    for airtable_name, key in SIMPLE_FIELDS.items():
        value = fields.get(airtable_name)
        if value not in (None, ""):
            record[key] = value

    for airtable_name, key in MULTI_SELECT_FIELDS.items():
        if values := fields.get(airtable_name):
            record[key] = sorted(values)

    for airtable_name, key in COMMA_LIST_FIELDS.items():
        if values := split_list(fields.get(airtable_name)):
            record[key] = values

    # `onchain` is only meaningful when the checkbox is set; an unchecked box
    # means "not on-chain", not "unknown", so we emit the object either way
    # once the field has been considered.
    if ONCHAIN_CHECKBOX in fields or any(f in fields for f in ONCHAIN_LIST_FIELDS):
        onchain: dict = {"is_onchain": bool(fields.get(ONCHAIN_CHECKBOX))}
        for airtable_name, (key, separator) in ONCHAIN_LIST_FIELDS.items():
            if values := split_list(fields.get(airtable_name), separator):
                onchain[key] = values
        record["onchain"] = onchain

    if links := {
        key: fields[airtable_name]
        for airtable_name, key in LINK_FIELDS.items()
        if fields.get(airtable_name)
    }:
        record["links"] = links

    if verification := {
        key: fields[airtable_name]
        for airtable_name, key in VERIFICATION_FIELDS.items()
        if fields.get(airtable_name)
    }:
        record["verification"] = verification

    sources = []
    for source_id in fields.get("Sources", []):
        source_row = sources_by_id.get(source_id)
        if not source_row:
            continue
        source_fields = source_row.get("fields", {})
        source = {
            key: source_fields[airtable_name]
            for airtable_name, key in SOURCE_FIELDS.items()
            if source_fields.get(airtable_name)
        }
        if supports := split_list(source_fields.get("Supports")):
            source["supports"] = supports
        if source.get("url"):
            sources.append(source)
    if sources:
        # Sorted so a reordered Airtable link field doesn't produce a diff.
        record["sources"] = sorted(sources, key=lambda s: s["url"])

    record["airtable_record_id"] = row["id"]
    return {key: record[key] for key in KEY_ORDER if key in record}


def write_yaml(path: Path, record: dict) -> None:
    path.write_text(
        yaml.safe_dump(
            record,
            sort_keys=False,      # KEY_ORDER already decided the order
            allow_unicode=True,
            default_flow_style=False,
            width=88,
        )
    )


def main() -> int:
    token = os.environ.get("AIRTABLE_TOKEN")
    base_id = os.environ.get("AIRTABLE_BASE_ID")
    if not token or not base_id:
        print("AIRTABLE_TOKEN and AIRTABLE_BASE_ID must be set.", file=sys.stderr)
        return 2

    schema = json.loads(SCHEMA_PATH.read_text())
    validator = Draft202012Validator(schema, format_checker=FormatChecker())

    rows = fetch_all(base_id, REGISTRY_TABLE, token)
    sources_by_id = {row["id"]: row for row in fetch_all(base_id, SOURCES_TABLE, token)}
    published = [row for row in rows if row.get("fields", {}).get("Published")]
    report(f"Fetched {len(rows)} record(s), {len(published)} published.")

    valid: dict[str, dict] = {}
    skipped: list[str] = []

    for row in published:
        record = build_record(row, sources_by_id)
        record_id = record.get("id")
        if not record_id:
            skipped.append(f"{row['id']} — no ID field set")
            continue
        problems = sorted(validator.iter_errors(record), key=lambda e: list(e.path))
        if problems:
            detail = "; ".join(
                f"{'.'.join(str(p) for p in e.path) or '(root)'}: {e.message}"
                for e in problems[:3]
            )
            skipped.append(f"{record_id} — {detail}")
            continue
        if record_id in valid:
            skipped.append(f"{record_id} — duplicate ID, second occurrence dropped")
            continue
        valid[record_id] = record

    if skipped:
        report(f"\nSkipped {len(skipped)} record(s) — these will not appear in the registry:")
        for line in skipped:
            report(f"  - {line}")

    existing = {path.stem for path in DATA_DIR.glob("*.yml")}
    removed = existing - set(valid)

    # Refuse to proceed on a deletion that looks like a failure rather than a
    # decision. Re-run with SYNC_ALLOW_DELETIONS=1 once you've confirmed it.
    if (
        removed
        and len(existing) >= DELETION_GUARD_MIN_RECORDS
        and len(removed) / len(existing) > DELETION_GUARD_FRACTION
        and os.environ.get("SYNC_ALLOW_DELETIONS") != "1"
    ):
        print(
            f"\nRefusing to sync: would remove {len(removed)} of {len(existing)} "
            f"existing records ({sorted(removed)}).\n"
            "That is more than the guard allows. Check the Airtable view and the "
            "Published field. If the removal is intended, re-run with "
            "SYNC_ALLOW_DELETIONS=1.",
            file=sys.stderr,
        )
        return 1

    for record_id, record in sorted(valid.items()):
        write_yaml(DATA_DIR / f"{record_id}.yml", record)
    for record_id in sorted(removed):
        (DATA_DIR / f"{record_id}.yml").unlink()
        report(f"Removed {record_id}.yml — no longer published.")

    # No generation timestamp inside the bundle: it would produce a diff on
    # every run even when nothing changed. Commit dates already record when.
    BUNDLE_PATH.write_text(
        json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "count": len(valid),
                "organizations": [valid[key] for key in sorted(valid)],
            },
            indent=2,
            ensure_ascii=False,
            sort_keys=False,
        )
        + "\n"
    )

    report(f"\nWrote {len(valid)} record(s) to data/aos/ and data/registry.json.")

    if summary_path := os.environ.get("GITHUB_STEP_SUMMARY"):
        Path(summary_path).write_text("## Airtable sync\n\n```\n" + "\n".join(report_lines) + "\n```\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
