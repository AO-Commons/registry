#!/usr/bin/env python3
"""Apply the defined table structure to the Airtable base.

Converges rather than creates: missing tables are created, missing fields are
added, and fields listed in RENAMES are renamed in place. Safe to re-run, and
safe against a base that already holds records — it never deletes a field or
drops data.

Every single-select and multi-select option is derived from the JSON Schemas
at runtime, so the Airtable vocabulary cannot drift from the schema enums.
That drift is the failure this whole design is trying to avoid — a base whose
options say "Delegated" while the schema says "delegated" turns the sync into
a translation layer nobody maintains.

Usage:  python3 scripts/setup_airtable_base.py
Env:    AIRTABLE_TOKEN, AIRTABLE_BASE_ID

The token needs schema.bases:write, which the runtime sync token should NOT
have.

Requires: pip install requests
"""

import json
import os
import sys
from pathlib import Path

import requests

from airtable_fields import (
    INTAKE_TABLE,
    REGISTRY_TABLE,
    SOURCES_LINK_FIELD,
    SOURCES_TABLE,
)

ROOT = Path(__file__).resolve().parent.parent
AO_SCHEMA = json.loads((ROOT / "schema" / "ao.schema.json").read_text())
META = "https://api.airtable.com/v0/meta/bases"

# Applied before fields are created, so an existing base converges onto the
# current names instead of accumulating duplicates alongside them.
RENAMES = {
    REGISTRY_TABLE: {
        "ID": "ID *", "Name": "Name *", "Summary": "Summary *", "Status": "Status *",
        "Categories": "Categories *", "Agent Roles": "Agent Roles *",
        "Autonomy Level": "Autonomy Level *",
        "Verification Method": "Verification Method *", "Verified On": "Verified On *",
        "Sources": SOURCES_LINK_FIELD,
    },
    SOURCES_TABLE: {"URL": "URL *", "Accessed": "Accessed *"},
}


def enum_of(schema: dict, *path: str) -> list[dict]:
    """Pull an enum out of a schema and shape it as Airtable choices."""
    node = schema["properties"]
    for key in path:
        node = node[key]
    values = node.get("enum") or node["items"]["enum"]
    return [{"name": value} for value in values]


def text(name, description="", multiline=False):
    field = {"name": name, "type": "multilineText" if multiline else "singleLineText"}
    if description:
        field["description"] = description
    return field


def url(name, description=""):
    field = {"name": name, "type": "url"}
    if description:
        field["description"] = description
    return field


def date(name, description=""):
    field = {"name": name, "type": "date",
             "options": {"dateFormat": {"name": "iso", "format": "YYYY-MM-DD"}}}
    if description:
        field["description"] = description
    return field


def checkbox(name, description=""):
    field = {"name": name, "type": "checkbox",
             "options": {"icon": "check", "color": "greenBright"}}
    if description:
        field["description"] = description
    return field


def select(name, choices, multi=False, description=""):
    field = {"name": name, "type": "multipleSelects" if multi else "singleSelect",
             "options": {"choices": choices}}
    if description:
        field["description"] = description
    return field


REQUIRED_NOTE = "Required — a record missing this cannot be published."

REVIEW_STATE = select(
    "Review State",
    [{"name": "Draft"}, {"name": "Needs sources"},
     {"name": "Insufficient information"}, {"name": "Ready to publish"}],
    description="Our confidence in the record, for maintainers only. Never published — deliberately separate from Status, which describes the subject.",
)

REGISTRY_FIELDS = [
    text("ID *", f"{REQUIRED_NOTE} Stable lowercase-hyphenated slug; becomes the published filename. Never change it once published — citations depend on it."),
    text("Name *", f"{REQUIRED_NOTE} The organization's own name for itself."),
    checkbox("Published", "The sync gate. Unchecked records are invisible to the public repo."),
    select("Status *", enum_of(AO_SCHEMA, "status"), description=f"{REQUIRED_NOTE} The organization's operating state — not our confidence in the record. See Review State for that."),
    text("Summary *", f"{REQUIRED_NOTE} At least 20 characters. One or two neutral sentences, descriptive rather than promotional.", multiline=True),
    url("Website"),
    text("Aliases", "Former or alternative names, comma-separated."),
    text("Launched", "YYYY, YYYY-MM, or YYYY-MM-DD — whatever precision the evidence supports. Text, not a date, so partial precision survives."),
    select("Categories *", enum_of(AO_SCHEMA, "categories"), multi=True, description=REQUIRED_NOTE),
    select("Agent Roles *", enum_of(AO_SCHEMA, "agent_roles"), multi=True,
           description=f"{REQUIRED_NOTE} Which organizational functions agents hold. The membership criterion — authority, not tooling."),
    select("Autonomy Level *", enum_of(AO_SCHEMA, "autonomy_level"),
           description=f"{REQUIRED_NOTE} What the evidence supports, NOT what the organization claims. 'undetermined' is legitimate when sources conflict."),
    text("Human Oversight", "The specific mechanisms: thresholds, vetoes, review cadence, kill switches. If there are none, write that explicitly — an empty field reads as 'not yet researched'.", multiline=True),
    select("Governance Model", enum_of(AO_SCHEMA, "governance_model")),
    text("Agent Stack", "Frameworks, models, or platforms, comma-separated. Not an endorsement."),
    select("Legal Wrapper", enum_of(AO_SCHEMA, "legal_wrapper")),
    text("Jurisdiction", "ISO 3166-1 alpha-2, or a subdivision where it matters (e.g. US-WY)."),
    checkbox("Is Onchain"),
    text("Chains", "Comma-separated."),
    text("Contracts", "Chain-prefixed addresses, one per line (e.g. ethereum:0xabc...).", multiline=True),
    url("Link: Docs"), url("Link: Repo"), url("Link: Blog"), url("Link: Forum"),
    url("Link: X"), url("Link: Discord"), url("Link: Farcaster"),
    select("Verification Method *", enum_of(AO_SCHEMA, "verification", "properties", "method"), description=REQUIRED_NOTE),
    date("Verified On *", REQUIRED_NOTE),
    text("Verified By", "Role or handle of the reviewer — never personal contact details."),
    text("Verification Notes", multiline=True),
    text("Tags", "Comma-separated, lowercase-hyphenated."),
    date("Added"), date("Updated"),
    REVIEW_STATE,
    text("Notes", "Internal maintainer notes. Never published.", multiline=True),
]


SOURCES_FIELDS = [
    url("URL *", REQUIRED_NOTE),
    text("Title"),
    date("Accessed *", REQUIRED_NOTE),
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
    text("Organization Name", "The name of whatever was submitted — organization or tool."),
    url("Website"),
    text("Summary", multiline=True),
    text("Human Oversight", "For AOs: the controls described. For tools: the oversight it ships with.", multiline=True),
    text("Sources Given", "As submitted. Verify before copying anything across.", multiline=True),
    text("Agent Roles Claimed", "AO submissions. Normalized to schema tokens, ready to copy across."),
    text("Autonomy Claimed", "AO submissions. What the submitter claims — check it against the sources before believing it."),
    text("Tool Categories", "Tool submissions. Normalized to schema tokens."),
    text("Agent Model Claimed", "Tool submissions: how agents participate, as described by the submitter.", multiline=True),
    text("License", "Tool submissions."),
    text("Used By", "Tool submissions: AOs the submitter says run on this."),
    text("Target Record ID", "For corrections: the slug being corrected."),
    checkbox("Self Submission"),
    text("Raw Body", "The full issue body, so nothing is lost to parsing.", multiline=True),
    text("Reviewer Notes", multiline=True),
]

TABLES = [
    (REGISTRY_TABLE, "One row per autonomous organization — agents holding organizational authority. Rows with Published checked sync to github.com/AO-Commons/registry.", REGISTRY_FIELDS),
    (SOURCES_TABLE, "Evidence for claims in both collections. Every published record needs at least one.", SOURCES_FIELDS),
    (INTAKE_TABLE, "Submissions from the GitHub issue forms, awaiting review. Deliberately separate: a submission is a claim, a published record is a verified claim.", INTAKE_FIELDS),
]

# Required fields each table's Publish Blockers formula checks, as
# (field name, kind, label). "multi" covers multipleSelects and linked
# records, where an empty value is still a non-empty cell.
BLOCKERS = {
    REGISTRY_TABLE: [
        ("ID *", "single", "ID"), ("Name *", "single", "Name"),
        ("Summary *", "length20", "Summary(20+)"), ("Status *", "single", "Status"),
        ("Categories *", "multi", "Categories"), ("Agent Roles *", "multi", "AgentRoles"),
        ("Autonomy Level *", "single", "AutonomyLevel"),
        ("Verification Method *", "single", "VerificationMethod"),
        ("Verified On *", "single", "VerifiedOn"),
        (SOURCES_LINK_FIELD, "multi", "Sources"),
    ],
}

LINKED_TABLES = [REGISTRY_TABLE]


def api(method: str, path: str, token: str, **kwargs) -> dict:
    response = requests.request(
        method, f"{META}/{path}",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=30, **kwargs,
    )
    if not response.ok:
        raise requests.HTTPError(f"{response.status_code}: {response.text}", response=response)
    return response.json()


def fetch_tables(base_id: str, token: str) -> dict[str, dict]:
    return {table["name"]: table for table in api("GET", f"{base_id}/tables", token)["tables"]}


def build_formulas(table: dict, checks: list) -> list[dict]:
    """Formula fields, written against field IDs rather than names.

    Field IDs sidestep every escaping question a name like `ID *` would
    otherwise raise inside a formula string.
    """
    ids = {field["name"]: field["id"] for field in table["fields"]}
    if any(name not in ids for name, _, _ in checks) or "Name *" not in ids:
        return []

    clauses = []
    for name, kind, label in checks:
        ref = "{" + ids[name] + "}"
        if kind == "length20":
            clauses.append(f'IF(LEN({ref})>=20, "", "{label} ")')
        elif kind == "multi":
            clauses.append(f'IF(LEN(ARRAYJOIN({ref}))>0, "", "{label} ")')
        else:
            clauses.append(f'IF({ref}, "", "{label} ")')

    name_ref = "{" + ids["Name *"] + "}"
    return [
        {"name": "Publish Blockers", "type": "formula",
         "description": "Required fields still empty. Must be blank before Published is ticked.",
         "options": {"formula": "TRIM(" + " & ".join(clauses) + ")"}},
        {"name": "Suggested ID", "type": "formula",
         "description": "A slug derived from Name. Copy it into ID * — or override it; the slug need not match the name, and must never change once published.",
         "options": {"formula": (
             f'IF({name_ref}, LOWER(REGEX_REPLACE(REGEX_REPLACE(TRIM({name_ref}),'
             ' "[^a-zA-Z0-9]+", "-"), "^-+|-+$", "")), "")')}},
    ]


def main() -> int:
    token = os.environ.get("AIRTABLE_TOKEN")
    base_id = os.environ.get("AIRTABLE_BASE_ID")
    if not token or not base_id:
        print("AIRTABLE_TOKEN and AIRTABLE_BASE_ID must be set.", file=sys.stderr)
        return 2

    live = fetch_tables(base_id, token)
    changed = 0

    # 1. Tables.
    for name, description, fields in TABLES:
        if name in live:
            continue
        api("POST", f"{base_id}/tables", token,
            json={"name": name, "description": description, "fields": fields})
        print(f"created table {name} ({len(fields)} fields)")
        changed += 1
    if changed:
        live = fetch_tables(base_id, token)

    # 2. Renames, before field creation, so an existing base converges onto
    #    the current names rather than gaining duplicates beside them.
    for table_name, renames in RENAMES.items():
        table = live.get(table_name)
        if not table:
            continue
        by_name = {field["name"]: field for field in table["fields"]}
        for old, new in renames.items():
            if old in by_name and new not in by_name:
                api("PATCH", f"{base_id}/tables/{table['id']}/fields/{by_name[old]['id']}",
                    token, json={"name": new})
                print(f"renamed {table_name}.{old} -> {new}")
                changed += 1
    if changed:
        live = fetch_tables(base_id, token)

    # 3. Missing fields on existing tables.
    for table_name, _, fields in TABLES:
        table = live[table_name]
        present = {field["name"] for field in table["fields"]}
        for field in fields:
            if field["name"] in present:
                continue
            api("POST", f"{base_id}/tables/{table['id']}/fields", token, json=field)
            print(f"added {table_name}.{field['name']} ({field['type']})")
            changed += 1

    # 4. Link fields, once both endpoints exist. Both collections point at
    #    the one Sources table.
    live = fetch_tables(base_id, token)
    for table_name in LINKED_TABLES:
        table = live[table_name]
        if SOURCES_LINK_FIELD in {f["name"] for f in table["fields"]}:
            continue
        api("POST", f"{base_id}/tables/{table['id']}/fields", token, json={
            "name": SOURCES_LINK_FIELD, "type": "multipleRecordLinks",
            "description": f"{REQUIRED_NOTE} Evidence for this record.",
            "options": {"linkedTableId": live[SOURCES_TABLE]["id"]},
        })
        print(f"added {table_name}.{SOURCES_LINK_FIELD} (link to {SOURCES_TABLE})")
        changed += 1
    live = fetch_tables(base_id, token)

    # 5. Formula fields last: they reference the IDs of everything above.
    for table_name, checks in BLOCKERS.items():
        table = live[table_name]
        present = {field["name"] for field in table["fields"]}
        for formula in build_formulas(table, checks):
            if formula["name"] in present:
                continue
            try:
                api("POST", f"{base_id}/tables/{table['id']}/fields", token, json=formula)
                print(f"added {table_name}.{formula['name']} (formula)")
                changed += 1
            except requests.HTTPError as error:
                # Some Airtable plans and API versions refuse formula
                # creation. Not fatal: everything else is in place, and the
                # field can be added by hand from the formula printed here.
                print(f"\ncould not create {table_name}.{formula['name']}: {error}", file=sys.stderr)
                print(f"add it manually with:\n\n{formula['options']['formula']}\n", file=sys.stderr)

    print(f"\n{changed} change(s) applied." if changed else "\nBase already matches the definitions.")
    print(f"  AIRTABLE_BASE_ID={base_id}\n")
    print("Verify with:  python3 scripts/check_airtable_base.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
