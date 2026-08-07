"""The mapping between Airtable field names and schema keys.

Kept in one place because it's the seam where the two sides of the sync have
to agree. The other Airtable scripts import it, and a field renamed in
Airtable is a change here.

Airtable field names are human-facing (Title Case, spaces); schema keys are
snake_case. Enum values are stored in Airtable exactly as the schema spells
them, so the sync stays a copy rather than a translation layer nobody wants
to maintain.

A trailing `*` marks a field the schema requires — a record missing any of
them cannot be published. The marker is part of the field name, so it shows
up in the Airtable UI without anyone having to consult documentation.
"""

import yaml


class RegistryLoader(yaml.SafeLoader):
    """SafeLoader that leaves dates as strings.

    The schema validates ISO-8601 date *strings*; PyYAML would otherwise
    resolve unquoted `2026-08-01` to a datetime.date and every date field
    would fail its type check. Dropping the timestamp resolver keeps records
    readable — no quoting every date by hand.

    Shared by every script that reads generated records, so they cannot
    disagree about what a date is.
    """


RegistryLoader.yaml_implicit_resolvers = {
    prefix: [(tag, regexp) for tag, regexp in resolvers if tag != "tag:yaml.org,2002:timestamp"]
    for prefix, resolvers in RegistryLoader.yaml_implicit_resolvers.items()
}


REGISTRY_TABLE = "Registry"
SOURCES_TABLE = "Sources"
INTAKE_TABLE = "Intake"

# Fields the sync reads by name rather than through a mapping.
PUBLISHED_FIELD = "Published"
SOURCES_LINK_FIELD = "Sources *"
SUPPORTS_FIELD = "Supports"

# Airtable field name -> schema key, for values that copy across unchanged.
SIMPLE_FIELDS = {
    "ID *": "id",
    "Name *": "name",
    "Summary *": "summary",
    "Website": "website",
    "Status *": "status",
    "Launched": "launched",
    "Autonomy Level *": "autonomy_level",
    "Human Oversight": "human_oversight",
    "Governance Model": "governance_model",
    "Legal Wrapper": "legal_wrapper",
    "Jurisdiction": "jurisdiction",
    "Added": "added",
    "Updated": "updated",
}

# Airtable multipleSelects -> schema arrays.
MULTI_SELECT_FIELDS = {
    "Categories *": "categories",
    "Agent Roles *": "agent_roles",
}

# Comma-separated singleLineText -> schema arrays. Airtable has no plain list
# type, and multipleSelects would force a closed vocabulary on fields whose
# values are open-ended.
COMMA_LIST_FIELDS = {
    "Aliases": "aliases",
    "Agent Stack": "agent_stack",
    "Tags": "tags",
}

# Nested under `onchain`. Contracts is multilineText (one per line) because
# addresses are long enough that comma-separation is unreadable in the UI.
ONCHAIN_CHECKBOX = "Is Onchain"
ONCHAIN_LIST_FIELDS = {
    "Chains": ("chains", ","),
    "Contracts": ("contracts", "\n"),
}

# Airtable field name -> key under `links`.
LINK_FIELDS = {
    "Link: Docs": "docs",
    "Link: Repo": "repo",
    "Link: Blog": "blog",
    "Link: Forum": "forum",
    "Link: X": "x",
    "Link: Discord": "discord",
    "Link: Farcaster": "farcaster",
}

# Airtable field name -> key under `verification`.
VERIFICATION_FIELDS = {
    "Verification Method *": "method",
    "Verified On *": "verified_on",
    "Verified By": "verified_by",
    "Verification Notes": "notes",
}

# Sources table field name -> key in a `sources[]` entry.
SOURCE_FIELDS = {
    "URL *": "url",
    "Title": "title",
    "Accessed *": "accessed",
}

# Fields that exist for maintainers and never reach the published data.
# Review State in particular is deliberately NOT the schema's `status`:
# "insufficient information" describes our knowledge, not the organization,
# and putting it in `status` would produce records that fail validation.
INTERNAL_ONLY = {
    "Published",
    "Review State",
    "Publish Blockers",
    "Suggested ID",
    "Notes",
    "Intake",
    "Registry",
}

# The order keys appear in generated YAML. Stable ordering keeps diffs
# meaningful — without it every sync run reshuffles every file.
KEY_ORDER = [
    "schema_version",
    "id",
    "name",
    "aliases",
    "summary",
    "website",
    "status",
    "launched",
    "categories",
    "agent_roles",
    "autonomy_level",
    "human_oversight",
    "governance_model",
    "agent_stack",
    "legal_wrapper",
    "jurisdiction",
    "onchain",
    "links",
    "sources",
    "verification",
    "tags",
    "airtable_record_id",
    "added",
    "updated",
]

SCHEMA_VERSION = "0.1"
