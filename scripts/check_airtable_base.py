#!/usr/bin/env python3
"""Compare the live Airtable base against what the scripts expect.

Read-only. Needs only schema.bases:read, so it is safe to run with the
runtime token — and worth running periodically, not just once. The failure
this catches is someone renaming a field or editing a select option in the
Airtable UI: the sync doesn't error on that, it just silently stops
populating the affected field, and records quietly lose data.

Reports three kinds of finding:
  MISSING  — the scripts need it and it isn't there. Breaks the sync.
  DRIFT    — it exists but the type or options differ. Usually breaks it too.
  EXTRA    — in the base but not in the definitions. Informational; maintainers
             are free to add their own columns, and the sync ignores them.

Usage:  python3 scripts/check_airtable_base.py
Env:    AIRTABLE_TOKEN, AIRTABLE_BASE_ID
Requires: pip install requests
"""

import os
import sys

import requests

import setup_airtable_base as setup
from airtable_fields import SOURCES_LINK_FIELD

META = "https://api.airtable.com/v0/meta/bases"

missing: list[str] = []
drift: list[str] = []
extra: list[str] = []


def choices_of(field: dict) -> set[str] | None:
    options = field.get("options") or {}
    if "choices" not in options:
        return None
    return {choice["name"] for choice in options["choices"]}


def main() -> int:
    token = os.environ.get("AIRTABLE_TOKEN")
    base_id = os.environ.get("AIRTABLE_BASE_ID")
    if not token or not base_id:
        print("AIRTABLE_TOKEN and AIRTABLE_BASE_ID must be set.", file=sys.stderr)
        return 2

    response = requests.get(
        f"{META}/{base_id}/tables",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    if not response.ok:
        print(f"Airtable API error {response.status_code}: {response.text}", file=sys.stderr)
        return 2

    live = {table["name"]: table for table in response.json()["tables"]}

    for table_name, _, expected_fields in setup.TABLES:
        if table_name not in live:
            missing.append(f"table {table_name!r}")
            continue

        live_fields = {field["name"]: field for field in live[table_name]["fields"]}

        for expected in expected_fields:
            name = expected["name"]
            actual = live_fields.get(name)
            if actual is None:
                missing.append(f"{table_name}.{name} ({expected['type']})")
                continue
            if actual["type"] != expected["type"]:
                drift.append(
                    f"{table_name}.{name}: base has {actual['type']}, "
                    f"scripts expect {expected['type']}"
                )
                continue
            expected_choices = choices_of(expected)
            if expected_choices is not None:
                actual_choices = choices_of(actual) or set()
                if added := actual_choices - expected_choices:
                    drift.append(
                        f"{table_name}.{name}: base has options not in the schema "
                        f"{sorted(added)} — records using them will fail validation"
                    )
                if absent := expected_choices - actual_choices:
                    drift.append(
                        f"{table_name}.{name}: base is missing options {sorted(absent)}"
                    )

        expected_names = {field["name"] for field in expected_fields}
        # The link field, the formula fields, and Airtable's auto-created
        # reverse links all exist without appearing in the table definitions.
        expected_names |= {
            SOURCES_LINK_FIELD,
            "Publish Blockers",
            "Suggested ID",
            setup.REGISTRY_TABLE,
            setup.SOURCES_TABLE,
            setup.INTAKE_TABLE,
        }
        for name in sorted(set(live_fields) - expected_names):
            extra.append(f"{table_name}.{name} ({live_fields[name]['type']})")

    # The one field created separately, after both endpoints existed.
    registry = live.get(setup.REGISTRY_TABLE)
    if registry:
        link = next((f for f in registry["fields"] if f["name"] == SOURCES_LINK_FIELD), None)
        if link is None:
            missing.append(
                f"{setup.REGISTRY_TABLE}.{SOURCES_LINK_FIELD} (link to {setup.SOURCES_TABLE})"
            )
        elif link["type"] != "multipleRecordLinks":
            drift.append(
                f"{setup.REGISTRY_TABLE}.{SOURCES_LINK_FIELD} is {link['type']}, "
                "expected a link field"
            )

    for label, findings in (("MISSING", missing), ("DRIFT", drift), ("EXTRA", extra)):
        if findings:
            print(f"\n{label} ({len(findings)}):")
            for finding in findings:
                print(f"  - {finding}")

    if missing or drift:
        print(
            f"\n{len(missing) + len(drift)} problem(s). The sync would not populate "
            "these correctly — fix the base, or update scripts/setup_airtable_base.py "
            "and scripts/airtable_fields.py if the base is right and the scripts are stale.",
            file=sys.stderr,
        )
        return 1

    tables = len(setup.TABLES)
    fields = sum(len(f) for _, _, f in setup.TABLES) + 1  # + the Sources link
    print(f"Base matches the scripts: {tables} tables, {fields} fields.")
    if extra:
        print(f"({len(extra)} extra field(s) in the base — ignored by the sync.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
