#!/usr/bin/env python3
"""Checks the seam between the JSON Schema, the Airtable base, and the scripts.

This is the part of the system that breaks silently. A field renamed in
Airtable, an enum value added to the schema but not the intake form, a
select option capitalized differently — none of these raise an error at the
time. They produce records that quietly fail validation, or worse, records
that validate but say the wrong thing.

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

SCHEMA = json.loads((ROOT / "schema" / "ao.schema.json").read_text())
PROPS = SCHEMA["properties"]
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())

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
    "Status": PROPS["status"]["enum"],
    "Categories": PROPS["categories"]["items"]["enum"],
    "Agent Roles": PROPS["agent_roles"]["items"]["enum"],
    "Autonomy Level": PROPS["autonomy_level"]["enum"],
    "Governance Model": PROPS["governance_model"]["enum"],
    "Legal Wrapper": PROPS["legal_wrapper"]["enum"],
    "Verification Method": PROPS["verification"]["properties"]["method"]["enum"],
}
for name, expected in ENUM_FIELDS.items():
    assert field_options(setup.REGISTRY_FIELDS, name) == expected, f"{name} options drifted"
check(f"Airtable select options equal schema enums ({len(ENUM_FIELDS)} fields)")


# --- Every field a script reads or writes must exist in the base ------------

registry_names = {f["name"] for f in setup.REGISTRY_FIELDS} | {"Sources"}
sync_reads = (
    set(AF.SIMPLE_FIELDS)
    | set(AF.MULTI_SELECT_FIELDS)
    | set(AF.COMMA_LIST_FIELDS)
    | set(AF.LINK_FIELDS)
    | set(AF.VERIFICATION_FIELDS)
    | set(AF.ONCHAIN_LIST_FIELDS)
    | {AF.ONCHAIN_CHECKBOX, "Published", "Sources"}
)
assert not (sync_reads - registry_names), f"sync reads absent fields: {sync_reads - registry_names}"
check(f"every field the sync reads exists in the base ({len(sync_reads)})")

source_names = {f["name"] for f in setup.SOURCES_FIELDS}
assert not ((set(AF.SOURCE_FIELDS) | {"Supports"}) - source_names)
check("every Sources field the sync reads exists")

INTAKE_WRITES = {
    "Submission", "Issue Number", "Issue URL", "Type", "Status", "Raw Body",
    "Organization Name", "Website", "Summary", "Human Oversight", "Sources Given",
    "Target Record ID", "Agent Roles Claimed", "Autonomy Claimed", "Self Submission",
}
intake_names = {f["name"] for f in setup.INTAKE_FIELDS}
assert not (INTAKE_WRITES - intake_names), f"intake writes absent fields: {INTAKE_WRITES - intake_names}"
check(f"every field the intake script writes exists in the base ({len(INTAKE_WRITES)})")


# --- The intake form must not offer options the schema rejects --------------

form = yaml.safe_load((ROOT / ".github" / "ISSUE_TEMPLATE" / "new-ao.yml").read_text())
form_roles = {
    to_enum_token(option["label"])
    for block in form["body"]
    if block.get("id") == "agent_roles"
    for option in block["attributes"]["options"]
}
assert form_roles <= set(PROPS["agent_roles"]["items"]["enum"]), (
    f"form offers roles the schema rejects: {form_roles - set(PROPS['agent_roles']['items']['enum'])}"
)
check(f"every intake-form agent role is a valid schema value ({len(form_roles)})")

form_autonomy = {
    to_enum_token(option)
    for block in form["body"]
    if block.get("id") == "autonomy_level"
    for option in block["attributes"]["options"]
    if not option.lower().startswith("not sure")
}
assert form_autonomy <= set(PROPS["autonomy_level"]["enum"]), (
    f"form offers autonomy levels the schema rejects: {form_autonomy - set(PROPS['autonomy_level']['enum'])}"
)
check(f"every intake-form autonomy level is a valid schema value ({len(form_autonomy)})")


# --- Parsing a rendered issue form ------------------------------------------

BODY = """### Organization name

Example Collective

### Website

https://example.org

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


# --- Building a record from an Airtable row ---------------------------------

ROW = {
    "id": "recAAAAAAAAAAAAAA",
    "fields": {
        "ID": "example-collective", "Name": "Example Collective",
        "Aliases": "Example DAO, ExCo",
        "Summary": "A research collective in which agents draft and screen grant proposals.",
        "Website": "https://example.org", "Status": "active", "Launched": "2025-03",
        "Categories": ["research", "grantmaking"], "Agent Roles": ["leadership", "research"],
        "Autonomy Level": "delegated",
        "Human Oversight": "Disbursements above $5,000 require a 3-of-5 signature.",
        "Governance Model": "multisig", "Agent Stack": "Claude, custom orchestration",
        "Legal Wrapper": "nonprofit", "Jurisdiction": "US-CA",
        "Is Onchain": True, "Chains": "ethereum",
        "Contracts": "ethereum:0x0000000000000000000000000000000000000000",
        "Link: Docs": "https://docs.example.org",
        "Verification Method": "documented", "Verified On": "2026-08-01",
        "Verified By": "ao-commons-research", "Tags": "grants, human-in-the-loop",
        "Added": "2026-08-01", "Updated": "2026-08-01", "Published": True,
        "Notes": "INTERNAL REVIEWER NOTE — must never be published",
        "Sources": ["recS2", "recS1"],
    },
}
SOURCES = {
    "recS2": {"id": "recS2", "fields": {"URL": "https://example.org/blog/launch",
                                        "Title": "Launch", "Accessed": "2026-08-01",
                                        "Supports": "launched"}},
    "recS1": {"id": "recS1", "fields": {"URL": "https://example.org/governance",
                                        "Title": "Governance", "Accessed": "2026-08-01",
                                        "Supports": "autonomy_level, human_oversight"}},
}

record = build_record(ROW, SOURCES)
problems = sorted(VALIDATOR.iter_errors(record), key=lambda e: list(e.path))
assert not problems, "; ".join(
    f"{'.'.join(str(p) for p in e.path) or '(root)'}: {e.message}" for e in problems
)
check("a fully populated Airtable row produces a schema-valid record")

assert "INTERNAL REVIEWER NOTE" not in json.dumps(record), "internal notes leaked into output"
assert "Notes" not in record
check("internal-only fields never reach published output")

assert record["aliases"] == ["Example DAO", "ExCo"]
assert record["onchain"] == {
    "is_onchain": True, "chains": ["ethereum"],
    "contracts": ["ethereum:0x0000000000000000000000000000000000000000"],
}
assert [s["url"] for s in record["sources"]] == [
    "https://example.org/blog/launch", "https://example.org/governance",
], "sources sort by url, so reordering the Airtable link field produces no diff"
assert list(record)[:2] == ["schema_version", "id"], "key order is fixed, not insertion order"
check("output is deterministic: sorted lists, fixed key order")

unchecked = build_record({"id": "recB", "fields": {**ROW["fields"], "Is Onchain": False,
                                                   "Chains": "", "Contracts": ""}}, SOURCES)
assert unchecked["onchain"] == {"is_onchain": False}, "unchecked means not-onchain, not unknown"
check("an unchecked on-chain box means 'not on-chain', not 'unknown'")

sourceless = build_record({"id": "recC", "fields": {**ROW["fields"], "Sources": []}}, SOURCES)
assert list(VALIDATOR.iter_errors(sourceless)), "a sourceless record must fail validation"
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
check("every table has a valid primary field type and unique field names")

print(f"\n{passed} checks passed.")
