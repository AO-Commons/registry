#!/usr/bin/env python3
"""Build the registry base's tables and fields in an empty Airtable base.

Run once against a newly created, empty base. Safe to re-run: existing tables
are reported and skipped rather than duplicated or overwritten.

Every single-select and multi-select option is derived from
schema/ao.schema.json at runtime, so the Airtable vocabulary cannot drift
from the schema enums. That drift is the failure this whole design is trying
to avoid — a base whose options say "Delegated" while the schema says
"delegated" turns the sync into a translation layer nobody maintains.

Usage:  python3 scripts/setup_airtable_base.py
Env:    AIRTABLE_TOKEN, AIRTABLE_BASE_ID

The token needs schema.bases:write, which the *runtime* sync token should
NOT have. Use a separate short-lived token here and delete it afterwards.

Requires: pip install requests
"""

import json
import os
import sys
from pathlib import Path

import requests

from airtable_fields import INTAKE_TABLE, REGISTRY_TABLE, SOURCES_TABLE

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = json.loads((ROOT / "schema" / "ao.schema.json").read_text())
META = "https://api.airtable.com/v0/meta/bases"

PROPERTIES = SCHEMA["properties"]


def enum_of(*path: str) -> list[dict]:
    """Pull an enum out of the schema and shape it as Airtable choices."""
    node = PROPERTIES
    for key in path:
        node = node[key]
    values = node.get("enum") or node["items"]["enum"]
    return [{"name": value} for value in values]


def text(name: str, description: str = "", multiline: bool = False) -> dict:
    field = {"name": name, "type": "multilineText" if multiline else "singleLineText"}
    if description:
        field["description"] = description
    return field


def url(name: str, description: str = "") -> dict:
    field = {"name": name, "type": "url"}
    if description:
        field["description"] = description
    return field


def date(name: str, description: str = "") -> dict:
    field = {
        "name": name,
        "type": "date",
        "options": {"dateFormat": {"name": "iso", "format": "YYYY-MM-DD"}},
    }
    if description:
        field["description"] = description
    return field


def checkbox(name: str, description: str = "") -> dict:
    field = {
        "name": name,
        "type": "checkbox",
        "options": {"icon": "check", "color": "greenBright"},
    }
    if description:
        field["description"] = description
    return field


def select(name: str, choices: list[dict], multi: bool = False, description: str = "") -> dict:
    field = {
        "name": name,
        "type": "multipleSelects" if multi else "singleSelect",
        "options": {"choices": choices},
    }
    if description:
        field["description"] = description
    return field


REGISTRY_FIELDS = [
    text("ID", "Stable slug, matches the published filename. Never change it once published — citations depend on it."),
    text("Name", "The organization's own name for itself."),
    checkbox("Published", "The sync gate. Unchecked records are invisible to the public repo."),
    select("Status", enum_of("status"), description="Operating state as of the last verification."),
    text("Summary", "One or two neutral sentences. Descriptive, not promotional.", multiline=True),
    url("Website"),
    text("Aliases", "Former or alternative names, comma-separated."),
    text("Launched", "YYYY, YYYY-MM, or YYYY-MM-DD — whatever precision the evidence supports. Text, not a date, so partial precision survives."),
    select("Categories", enum_of("categories"), multi=True),
    select(
        "Agent Roles",
        enum_of("agent_roles"),
        multi=True,
        description="Which organizational functions agents hold. The membership criterion — authority, not tooling.",
    ),
    select(
        "Autonomy Level",
        enum_of("autonomy_level"),
        description="What the evidence supports, NOT what the organization claims. Use 'undetermined' when sources conflict.",
    ),
    text(
        "Human Oversight",
        "The specific mechanisms: thresholds, vetoes, review cadence, kill switches. If there are none, write that explicitly — an empty field reads as 'not yet researched'.",
        multiline=True,
    ),
    select("Governance Model", enum_of("governance_model")),
    text("Agent Stack", "Frameworks, models, or platforms, comma-separated. Not an endorsement."),
    select("Legal Wrapper", enum_of("legal_wrapper")),
    text("Jurisdiction", "ISO 3166-1 alpha-2, or a subdivision where it matters (e.g. US-WY)."),
    checkbox("Is Onchain"),
    text("Chains", "Comma-separated."),
    text("Contracts", "Chain-prefixed addresses, one per line (e.g. ethereum:0xabc...).", multiline=True),
    url("Link: Docs"),
    url("Link: Repo"),
    url("Link: Blog"),
    url("Link: Forum"),
    url("Link: X"),
    url("Link: Discord"),
    url("Link: Farcaster"),
    select("Verification Method", enum_of("verification", "properties", "method")),
    date("Verified On"),
    text("Verified By", "Role or handle of the reviewer — never personal contact details."),
    text("Verification Notes", multiline=True),
    text("Tags", "Comma-separated, lowercase-hyphenated."),
    date("Added"),
    date("Updated"),
    text("Notes", "Internal maintainer notes. Never published.", multiline=True),
]

SOURCES_FIELDS = [
    url("URL"),
    text("Title"),
    date("Accessed"),
    text("Supports", "Which schema fields this source is evidence for, comma-separated. This is what makes a claim auditable."),
]

INTAKE_FIELDS = [
    text("Submission", "The issue title."),
    {"name": "Issue Number", "type": "number", "options": {"precision": 0},
     "description": "The upsert key — an edited issue updates its row rather than creating a second."},
    url("Issue URL"),
    select("Type", [{"name": "New AO"}, {"name": "Correction"}]),
    select("Status", [
        {"name": "New"}, {"name": "In review"}, {"name": "Needs info"},
        {"name": "Accepted"}, {"name": "Declined"}, {"name": "Duplicate"},
    ], description="Set by reviewers. The sync never reads this table — acceptance means copying into Registry."),
    text("Organization Name"),
    url("Website"),
    text("Summary", multiline=True),
    text("Human Oversight", multiline=True),
    text("Sources Given", "As submitted. Verify before copying anything across.", multiline=True),
    text("Agent Roles Claimed", "Normalized to schema tokens, ready to copy into Registry."),
    text("Autonomy Claimed", "What the submitter claims. Check it against the sources before believing it."),
    text("Target Record ID", "For corrections: the registry slug being corrected."),
    checkbox("Self Submission"),
    text("Raw Body", "The full issue body, so nothing is lost to parsing.", multiline=True),
    text("Reviewer Notes", multiline=True),
]

TABLES = [
    (REGISTRY_TABLE, "One row per autonomous organization. Source of truth for the public registry; rows with Published checked are synced to github.com/AO-Commons/registry.", REGISTRY_FIELDS),
    (SOURCES_TABLE, "Evidence for registry claims. Linked from Registry — every published record needs at least one.", SOURCES_FIELDS),
    (INTAKE_TABLE, "Submissions from the GitHub issue forms, awaiting review. Deliberately separate from Registry: a submission is a claim, a registry record is a verified claim.", INTAKE_FIELDS),
]


def api(method: str, path: str, token: str, **kwargs) -> dict:
    response = requests.request(
        method,
        f"{META}/{path}",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=30,
        **kwargs,
    )
    if not response.ok:
        print(f"\nAirtable API error {response.status_code}: {response.text}", file=sys.stderr)
        response.raise_for_status()
    return response.json()


def main() -> int:
    token = os.environ.get("AIRTABLE_TOKEN")
    base_id = os.environ.get("AIRTABLE_BASE_ID")
    if not token or not base_id:
        print("AIRTABLE_TOKEN and AIRTABLE_BASE_ID must be set.", file=sys.stderr)
        return 2

    existing = {t["name"]: t for t in api("GET", f"{base_id}/tables", token).get("tables", [])}
    created: dict[str, str] = {}

    for name, description, fields in TABLES:
        if name in existing:
            print(f"- {name}: already exists, skipping ({len(existing[name]['fields'])} fields)")
            created[name] = existing[name]["id"]
            continue
        result = api(
            "POST",
            f"{base_id}/tables",
            token,
            json={"name": name, "description": description, "fields": fields},
        )
        created[name] = result["id"]
        print(f"- {name}: created with {len(fields)} fields")

    # Link fields come last: both endpoints of a link must exist first.
    # Airtable auto-creates the reverse field on the other table; its default
    # name doesn't matter, since nothing reads it.
    tables = api("GET", f"{base_id}/tables", token)["tables"]
    registry_table = next(t for t in tables if t["name"] == REGISTRY_TABLE)
    registry_fields = {field["name"] for field in registry_table["fields"]}

    if "Sources" not in registry_fields:
        api(
            "POST",
            f"{base_id}/tables/{created[REGISTRY_TABLE]}/fields",
            token,
            json={
                "name": "Sources",
                "type": "multipleRecordLinks",
                "description": "Evidence for this record. At least one required to publish.",
                "options": {"linkedTableId": created[SOURCES_TABLE]},
            },
        )
        print(f"- {REGISTRY_TABLE}.Sources: linked to {SOURCES_TABLE}")
    else:
        print(f"- {REGISTRY_TABLE}.Sources: already exists, skipping")

    print(
        "\nDone.\n\n"
        f"  AIRTABLE_BASE_ID={base_id}\n\n"
        "Next: add a record with Published checked, then dry-run the sync:\n"
        "  python3 scripts/sync_from_airtable.py && python3 scripts/validate.py\n\n"
        "Then delete the schema.bases:write token you used here — the runtime\n"
        "sync token should not be able to alter the base structure."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
