#!/usr/bin/env python3
"""Regenerate data/ from the Airtable base.

Airtable is the source of truth; this script produces the published mirror.
Reads every published record in each collection — organizations and tooling —
writes one YAML per record plus a combined JSON bundle, and removes files
whose records are no longer published.

Records that fail schema validation are skipped and reported rather than
written: one malformed row shouldn't block every other update, but the skip
is always visible in the run summary, never silent.

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
    COLLECTIONS,
    PUBLISHED_FIELD,
    SCHEMA_VERSION,
    SOURCE_FIELDS,
    SOURCES_LINK_FIELD,
    SOURCES_TABLE,
    SUPPORTS_FIELD,
    RegistryLoader,
)

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_DIR = ROOT / "schema"
DATA_ROOT = ROOT / "data"
API = "https://api.airtable.com/v0"

# An Airtable filter typo or an API page returning empty should not quietly
# empty a collection. Below this many existing records we don't guess.
DELETION_GUARD_MIN_RECORDS = 5
DELETION_GUARD_FRACTION = 0.25

report_lines: list[str] = []
failed = False


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


def build_record(row: dict, sources_by_id: dict[str, dict], spec) -> dict:
    """Map one Airtable row onto a schema-shaped dict."""
    fields = row.get("fields", {})
    record: dict = {"schema_version": SCHEMA_VERSION}

    for airtable_name, key in spec.simple.items():
        value = fields.get(airtable_name)
        if value not in (None, ""):
            record[key] = value

    for airtable_name, key in spec.multi_select.items():
        if values := fields.get(airtable_name):
            record[key] = sorted(values)

    for airtable_name, key in spec.comma_lists.items():
        if values := split_list(fields.get(airtable_name)):
            record[key] = values

    # `onchain` is only meaningful when the checkbox is set; an unchecked box
    # means "not on-chain", not "unknown", so we emit the object either way
    # once the field has been considered.
    if spec.onchain_checkbox and (
        spec.onchain_checkbox in fields or any(f in fields for f in spec.onchain_lists)
    ):
        onchain: dict = {"is_onchain": bool(fields.get(spec.onchain_checkbox))}
        for airtable_name, (key, separator) in spec.onchain_lists.items():
            if values := split_list(fields.get(airtable_name), separator):
                onchain[key] = values
        record["onchain"] = onchain

    if links := {
        key: fields[airtable_name]
        for airtable_name, key in spec.links.items()
        if fields.get(airtable_name)
    }:
        record["links"] = links

    if verification := {
        key: fields[airtable_name]
        for airtable_name, key in spec.verification.items()
        if fields.get(airtable_name)
    }:
        record["verification"] = verification

    sources = []
    for source_id in fields.get(SOURCES_LINK_FIELD, []):
        source_row = sources_by_id.get(source_id)
        if not source_row:
            continue
        source_fields = source_row.get("fields", {})
        source = {
            key: source_fields[airtable_name]
            for airtable_name, key in SOURCE_FIELDS.items()
            if source_fields.get(airtable_name)
        }
        if supports := split_list(source_fields.get(SUPPORTS_FIELD)):
            source["supports"] = supports
        if source.get("url"):
            sources.append(source)
    if sources:
        # Sorted so a reordered Airtable link field doesn't produce a diff.
        record["sources"] = sorted(sources, key=lambda s: s["url"])

    record["airtable_record_id"] = row["id"]
    return {key: record[key] for key in spec.key_order if key in record}


def published_slugs(data_dir: Path) -> dict[str, str]:
    """Airtable record ID -> the slug it was last published under.

    A record keeps its Airtable ID forever but its slug is a promise to
    readers, so this is what lets the sync notice the two coming apart.
    """
    previous: dict[str, str] = {}
    for path in data_dir.glob("*.yml"):
        try:
            record = yaml.load(path.read_text(), Loader=RegistryLoader)
        except yaml.YAMLError:
            continue
        if isinstance(record, dict) and record.get("airtable_record_id"):
            previous[record["airtable_record_id"]] = record.get("id")
    return previous


def write_yaml(path: Path, record: dict) -> None:
    path.write_text(
        yaml.safe_dump(
            record,
            sort_keys=False,      # key_order already decided the order
            allow_unicode=True,
            default_flow_style=False,
            width=88,
        )
    )


def sync_collection(spec, base_id: str, token: str, sources_by_id: dict) -> bool:
    """Regenerate one collection. Returns False if the run should fail."""
    data_dir = DATA_ROOT / spec.data_dir
    data_dir.mkdir(parents=True, exist_ok=True)
    schema = json.loads((SCHEMA_DIR / spec.schema_file).read_text())
    validator = Draft202012Validator(schema, format_checker=FormatChecker())

    rows = fetch_all(base_id, spec.table, token)
    published = [row for row in rows if row.get("fields", {}).get(PUBLISHED_FIELD)]
    report(f"\n{spec.table}: {len(rows)} record(s), {len(published)} published.")

    valid: dict[str, dict] = {}
    skipped: list[str] = []

    for row in published:
        record = build_record(row, sources_by_id, spec)
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
        report(f"  skipped {len(skipped)} record(s) — these will not be published:")
        for line in skipped:
            report(f"    - {line}")

    # A slug that changes breaks every citation pointing at the old one. With
    # ID derived from a name, an ordinary typo fix can trigger this, so it
    # stops the run rather than quietly republishing at a new address.
    previous = published_slugs(data_dir)
    renamed = [
        (previous[record["airtable_record_id"]], record_id)
        for record_id, record in sorted(valid.items())
        if previous.get(record.get("airtable_record_id")) not in (None, record_id)
    ]
    if renamed and os.environ.get("SYNC_ALLOW_SLUG_CHANGES") != "1":
        print(
            f"\nRefusing to sync {spec.table}: {len(renamed)} record(s) would change slug.\n"
            + "\n".join(f"  {old} -> {new}" for old, new in renamed)
            + "\nThe slug is the published filename and the citation key; changing it\n"
            "breaks existing links. Prefer restoring the original slug and recording\n"
            "the new name under Aliases. If the rename is intended, re-run with\n"
            "SYNC_ALLOW_SLUG_CHANGES=1.",
            file=sys.stderr,
        )
        return False

    existing = {path.stem for path in data_dir.glob("*.yml")}
    removed = existing - set(valid)
    if (
        removed
        and len(existing) >= DELETION_GUARD_MIN_RECORDS
        and len(removed) / len(existing) > DELETION_GUARD_FRACTION
        and os.environ.get("SYNC_ALLOW_DELETIONS") != "1"
    ):
        print(
            f"\nRefusing to sync {spec.table}: would remove {len(removed)} of "
            f"{len(existing)} existing records ({sorted(removed)}).\n"
            "Check the Airtable view and the Published field. If intended, re-run "
            "with SYNC_ALLOW_DELETIONS=1.",
            file=sys.stderr,
        )
        return False

    for record_id, record in sorted(valid.items()):
        write_yaml(data_dir / f"{record_id}.yml", record)
    for record_id in sorted(removed):
        (data_dir / f"{record_id}.yml").unlink()
        report(f"  removed {record_id}.yml — no longer published.")

    # No generation timestamp inside the bundle: it would produce a diff on
    # every run even when nothing changed. Commit dates already record when.
    (DATA_ROOT / spec.bundle).write_text(
        json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "count": len(valid),
                spec.key: [valid[key] for key in sorted(valid)],
            },
            indent=2,
            ensure_ascii=False,
            sort_keys=False,
        )
        + "\n"
    )
    report(f"  wrote {len(valid)} record(s) to data/{spec.data_dir}/ and data/{spec.bundle}.")
    return True


def main() -> int:
    token = os.environ.get("AIRTABLE_TOKEN")
    base_id = os.environ.get("AIRTABLE_BASE_ID")
    if not token or not base_id:
        print("AIRTABLE_TOKEN and AIRTABLE_BASE_ID must be set.", file=sys.stderr)
        return 2

    # Fetched once and shared: the Sources table serves both collections, so
    # a report covering an organization and the tool it runs on is one row.
    sources_by_id = {row["id"]: row for row in fetch_all(base_id, SOURCES_TABLE, token)}
    report(f"Fetched {len(sources_by_id)} source(s).")

    ok = True
    for spec in COLLECTIONS:
        if not sync_collection(spec, base_id, token, sources_by_id):
            ok = False

    if summary_path := os.environ.get("GITHUB_STEP_SUMMARY"):
        Path(summary_path).write_text(
            "## Airtable sync\n\n```\n" + "\n".join(report_lines) + "\n```\n"
        )

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
