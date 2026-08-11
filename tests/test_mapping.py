#!/usr/bin/env python3
"""Checks the seam between the JSON Schemas, the Airtable base, and the scripts.

This is the part of the system that breaks silently. A field renamed in
Airtable, an enum value added to a schema but not the intake form, a select
option capitalized differently — none of these raise an error at the time.
They produce records that quietly fail validation, or worse, records that
validate but say the wrong thing.

Checks are driven off airtable_fields.COLLECTIONS, so adding a collection
extends the coverage rather than silently escaping it.

Deliberately dependency-light: plain asserts, run directly, no pytest.

Usage:  python3 tests/test_mapping.py
"""

import json
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import airtable_fields as AF  # noqa: E402
import setup_airtable_base as setup  # noqa: E402
from intake_to_airtable import checked_options, parse_issue_form, to_enum_token  # noqa: E402
from sync_from_airtable import build_record  # noqa: E402

SCHEMAS = {
    spec.key: json.loads((ROOT / "schema" / spec.schema_file).read_text())
    for spec in AF.COLLECTIONS
}
AO = SCHEMAS["registry"]

TABLE_FIELDS = {name: fields for name, _, fields in setup.TABLES}

passed = 0


def check(label: str) -> None:
    global passed
    passed += 1
    print(f"  ok  {label}")


def field_options(fields: list[dict], name: str) -> list[str]:
    for field in fields:
        if field["name"] == name:
            return [choice["name"] for choice in field["options"]["choices"]]
    raise AssertionError(f"no field named {name!r}")


# --- The Airtable vocabulary must equal the schema vocabulary ---------------
# Not "be compatible with" — equal. Anything else makes the sync a translation
# layer, and translation layers rot.

ENUM_FIELDS = {
    AF.REGISTRY.table: {
        "Status *": AO["properties"]["status"]["enum"],
        "Categories *": AO["properties"]["categories"]["items"]["enum"],
        "Agent Roles *": AO["properties"]["agent_roles"]["items"]["enum"],
        "Autonomy Level *": AO["properties"]["autonomy_level"]["enum"],
        "Governance Model": AO["properties"]["governance_model"]["enum"],
        "Legal Wrapper": AO["properties"]["legal_wrapper"]["enum"],
        "Verification Method *": AO["properties"]["verification"]["properties"]["method"]["enum"],
    },
}
count = 0
for table, fields in ENUM_FIELDS.items():
    for name, expected in fields.items():
        assert field_options(TABLE_FIELDS[table], name) == expected, f"{table}.{name} drifted"
        count += 1
check(f"Airtable select options equal schema enums ({count} fields)")

for table in ENUM_FIELDS:
    states = set(field_options(TABLE_FIELDS[table], "Review State"))
    status = set(field_options(TABLE_FIELDS[table], "Status *"))
    assert not (states & status), f"{table}: Review State overlaps Status"
assert "Review State" in AF.INTERNAL_ONLY, "Review State must never be published"
check("Review State is internal-only and shares no values with Status")


# --- The `*` marker must mean exactly "the schema requires this" -----------

for spec in AF.COLLECTIONS:
    required = set(SCHEMAS[spec.key]["required"])
    mapped = {**spec.simple, **spec.multi_select}
    starred = {key for name, key in mapped.items() if name.endswith(" *")}
    starred |= {"verification", "sources"}  # marked via their own fields
    assert starred == required, (
        f"{spec.table}: starred fields and schema-required keys disagree — "
        f"starred-only {starred - required}, required-only {required - starred}"
    )
check("every `*` field maps to a schema-required key and vice versa")


# --- Every field a script reads or writes must exist in the base ------------

for spec in AF.COLLECTIONS:
    defined = {f["name"] for f in TABLE_FIELDS[spec.table]} | {AF.SOURCES_LINK_FIELD}
    missing = spec.airtable_field_names() - defined
    assert not missing, f"{spec.table}: sync reads absent fields {missing}"
check("every field the sync reads exists in the base")

source_names = {f["name"] for f in TABLE_FIELDS[AF.SOURCES_TABLE]}
assert not ((set(AF.SOURCE_FIELDS) | {AF.SUPPORTS_FIELD}) - source_names)
check("every Sources field the sync reads exists")

INTAKE_WRITES = {
    "Submission", "Issue Number", "Issue URL", "Type", "Status", "Raw Body",
    "Organization Name", "Website", "Summary", "Human Oversight", "Sources Given",
    "Target Record ID", "Agent Roles Claimed", "Autonomy Claimed", "Self Submission",
    "Tool Categories", "Agent Model Claimed", "License", "Used By",
}
intake_names = {f["name"] for f in TABLE_FIELDS[AF.INTAKE_TABLE]}
assert not (INTAKE_WRITES - intake_names), f"intake writes absent: {INTAKE_WRITES - intake_names}"
check(f"every field the intake script writes exists in the base ({len(INTAKE_WRITES)})")

# The blocker formulas must check exactly the starred fields, or the Airtable
# guard and the schema would disagree about what "complete" means.
for table, checks in setup.BLOCKERS.items():
    starred = {f["name"] for f in TABLE_FIELDS[table] if f["name"].endswith(" *")}
    starred.add(AF.SOURCES_LINK_FIELD)
    assert {name for name, _, _ in checks} == starred, (
        f"{table}: Publish Blockers checks {[n for n, _, _ in checks]}, starred are {sorted(starred)}"
    )
check("Publish Blockers checks exactly the starred fields")


# --- The intake form must not offer options the schema rejects --------------

form = yaml.safe_load((ROOT / ".github" / "ISSUE_TEMPLATE" / "new-ao.yml").read_text())
form_roles = {
    to_enum_token(option["label"])
    for block in form["body"] if block.get("id") == "agent_roles"
    for option in block["attributes"]["options"]
}
assert form_roles <= set(AO["properties"]["agent_roles"]["items"]["enum"])
check(f"every intake-form agent role is a valid schema value ({len(form_roles)})")

form_autonomy = {
    to_enum_token(option)
    for block in form["body"] if block.get("id") == "autonomy_level"
    for option in block["attributes"]["options"]
    if not option.lower().startswith("not sure")
}
assert form_autonomy <= set(AO["properties"]["autonomy_level"]["enum"])
check(f"every intake-form autonomy level is a valid schema value ({len(form_autonomy)})")



# --- Parsing a rendered issue form ------------------------------------------

BODY = """### Organization name

Example Collective

### Which functions do AI agents hold?

- [X] Leadership — agents set direction or hold executive authority
- [ ] Treasury — agents allocate, disburse, or manage funds
- [X] External representation — agents speak or negotiate for the organization

### How much authority do agents actually exercise?

Supervised-autonomous — agents act independently, humans can veto

### When did it launch?

_No response_
"""
sections = parse_issue_form(BODY)
assert sections["Organization name"] == "Example Collective"
assert "When did it launch?" not in sections, "_No response_ must be dropped, not stored"
assert checked_options(sections["Which functions do AI agents hold?"]) == [
    "leadership", "external-representation",
], "only ticked boxes, normalized to schema tokens"
assert to_enum_token(sections["How much authority do agents actually exercise?"]) == "supervised-autonomous"
check("issue-form parsing, including unticked boxes and empty responses")


# --- Building records from Airtable rows ------------------------------------

SOURCES = {
    "recS2": {"id": "recS2", "fields": {"URL *": "https://example.org/blog/launch",
                                        "Title": "Launch", "Accessed *": "2026-08-01",
                                        "Supports": "launched"}},
    "recS1": {"id": "recS1", "fields": {"URL *": "https://example.org/governance",
                                        "Title": "Governance", "Accessed *": "2026-08-01",
                                        "Supports": "autonomy_level, human_oversight"}},
}

AO_ROW = {"id": "recAAAAAAAAAAAAAA", "fields": {
    "ID *": "example-collective", "Name *": "Example Collective",
    "Aliases": "Example DAO, ExCo",
    "Summary *": "A research collective in which agents draft and screen grant proposals.",
    "Website": "https://example.org", "Status *": "active", "Launched": "2025-03",
    "Categories *": ["research", "grantmaking"], "Agent Roles *": ["leadership", "research"],
    "Autonomy Level *": "delegated",
    "Human Oversight": "Disbursements above $5,000 require a 3-of-5 signature.",
    "Governance Model": "multisig", "Agent Stack": "Claude, custom orchestration",
    "Legal Wrapper": "nonprofit", "Jurisdiction": "US-CA",
    "Is Onchain": True, "Chains": "ethereum",
    "Contracts": "ethereum:0x0000000000000000000000000000000000000000",
    "Link: Docs": "https://docs.example.org",
    "Verification Method *": "documented", "Verified On *": "2026-08-01",
    "Verified By": "ao-commons-research", "Tags": "grants, human-in-the-loop",
    "Added": "2026-08-01", "Updated": "2026-08-01", "Published": True,
    "Review State": "Ready to publish",
    "Notes": "INTERNAL REVIEWER NOTE — must never be published",
    AF.SOURCES_LINK_FIELD: ["recS2", "recS1"],
}}


for spec, row in ((AF.REGISTRY, AO_ROW),):
    validator = Draft202012Validator(SCHEMAS[spec.key], format_checker=FormatChecker())
    record = build_record(row, SOURCES, spec)
    problems = sorted(validator.iter_errors(record), key=lambda e: list(e.path))
    assert not problems, f"{spec.table}: " + "; ".join(
        f"{'.'.join(str(p) for p in e.path) or '(root)'}: {e.message}" for e in problems
    )
    assert "INTERNAL REVIEWER NOTE" not in json.dumps(record), f"{spec.table}: internal note leaked"
    assert list(record)[:2] == ["schema_version", "id"], f"{spec.table}: key order not fixed"
check("records are schema-valid with internal fields excluded")

ao_record = build_record(AO_ROW, SOURCES, AF.REGISTRY)
assert ao_record["aliases"] == ["Example DAO", "ExCo"]
assert ao_record["onchain"] == {
    "is_onchain": True, "chains": ["ethereum"],
    "contracts": ["ethereum:0x0000000000000000000000000000000000000000"],
}
assert [s["url"] for s in ao_record["sources"]] == [
    "https://example.org/blog/launch", "https://example.org/governance",
], "sources sort by url, so reordering the Airtable link field produces no diff"
check("output is deterministic: sorted lists, fixed key order")

unchecked = build_record(
    {"id": "recB", "fields": {**AO_ROW["fields"], "Is Onchain": False, "Chains": "", "Contracts": ""}},
    SOURCES, AF.REGISTRY,
)
assert unchecked["onchain"] == {"is_onchain": False}, "unchecked means not-onchain, not unknown"
check("an unchecked on-chain box means 'not on-chain', not 'unknown'")


for spec, row in ((AF.REGISTRY, AO_ROW),):
    validator = Draft202012Validator(SCHEMAS[spec.key], format_checker=FormatChecker())
    sourceless = build_record(
        {"id": "recD", "fields": {**row["fields"], AF.SOURCES_LINK_FIELD: []}}, SOURCES, spec
    )
    assert list(validator.iter_errors(sourceless)), f"{spec.table}: sourceless record must fail"
check("a record with no sources fails rather than publishing")


# --- Table structure --------------------------------------------------------

ALLOWED_PRIMARY = {
    "singleLineText", "email", "url", "multilineText", "number", "percent",
    "currency", "duration", "date", "dateTime", "phoneNumber", "barcode",
}
for name, _, fields in setup.TABLES:
    assert fields[0]["type"] in ALLOWED_PRIMARY, f"{name}: primary field type {fields[0]['type']}"
    names = [f["name"] for f in fields]
    assert len(names) == len(set(names)), f"{name}: duplicate field names"
check(f"every table has a valid primary field type and unique field names ({len(setup.TABLES)})")

print(f"\n{passed} checks passed.")
