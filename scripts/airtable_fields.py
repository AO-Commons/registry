"""The mapping between Airtable field names and schema keys.

Kept in one place because it's the seam where the two sides of the sync have
to agree. The other Airtable scripts import it, and a field renamed in
Airtable is a change here.

One collection lives in this base: Registry, the autonomous organizations
where agents hold organizational authority. Tooling moved to the
knowledge-graph repository, where a tool is a Resource — something you
consult to decide how to build — rather than a second kind of registry
entry needing its own schema and intake path.

Airtable field names are human-facing (Title Case, spaces); schema keys are
snake_case. Enum values are stored in Airtable exactly as the schema spells
them, so the sync stays a copy rather than a translation layer nobody wants
to maintain. A trailing `*` marks a field the schema requires.
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

# Read by name rather than through a mapping. Shared by both collections —
# the Sources table serves them both, so a report covering an organization
# and the tool it runs on is one row, cited twice.
PUBLISHED_FIELD = "Published"
SOURCES_LINK_FIELD = "Sources *"
SUPPORTS_FIELD = "Supports"

# Sources table field name -> key in a `sources[]` entry.
SOURCE_FIELDS = {
    "URL *": "url",
    "Title": "title",
    "Accessed *": "accessed",
}

# Fields that exist for maintainers and never reach the published data.
# Review State in particular is deliberately NOT the schema's `status`:
# "insufficient information" describes our knowledge, not the subject, and
# putting it in `status` would produce records that fail validation.
INTERNAL_ONLY = {
    "Published",
    "Review State",
    "Publish Blockers",
    "Suggested ID",
    "Notes",
    "Intake",
    "Registry",
}

SCHEMA_VERSION = "0.1"


class Collection:
    """One synced table: how its Airtable fields map onto a schema."""

    def __init__(
        self,
        key,
        table,
        schema_file,
        data_dir,
        bundle,
        simple,
        multi_select,
        comma_lists,
        links,
        verification,
        key_order,
        onchain_checkbox=None,
        onchain_lists=None,
    ):
        self.key = key
        self.table = table
        self.schema_file = schema_file
        self.data_dir = data_dir
        self.bundle = bundle
        self.simple = simple
        self.multi_select = multi_select
        self.comma_lists = comma_lists
        self.links = links
        self.verification = verification
        self.key_order = key_order
        self.onchain_checkbox = onchain_checkbox
        self.onchain_lists = onchain_lists or {}

    def airtable_field_names(self):
        """Every Airtable field this collection reads."""
        return (
            set(self.simple)
            | set(self.multi_select)
            | set(self.comma_lists)
            | set(self.links)
            | set(self.verification)
            | set(self.onchain_lists)
            | {PUBLISHED_FIELD, SOURCES_LINK_FIELD}
            | ({self.onchain_checkbox} if self.onchain_checkbox else set())
        )


REGISTRY = Collection(
    key="registry",
    table=REGISTRY_TABLE,
    schema_file="ao.schema.json",
    data_dir="aos",
    bundle="registry.json",
    simple={
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
    },
    multi_select={
        "Categories *": "categories",
        "Agent Roles *": "agent_roles",
    },
    comma_lists={
        "Aliases": "aliases",
        "Agent Stack": "agent_stack",
        "Tags": "tags",
    },
    links={
        "Link: Docs": "docs",
        "Link: Repo": "repo",
        "Link: Blog": "blog",
        "Link: Forum": "forum",
        "Link: X": "x",
        "Link: Discord": "discord",
        "Link: Farcaster": "farcaster",
    },
    verification={
        "Verification Method *": "method",
        "Verified On *": "verified_on",
        "Verified By": "verified_by",
        "Verification Notes": "notes",
    },
    onchain_checkbox="Is Onchain",
    onchain_lists={
        "Chains": ("chains", ","),
        "Contracts": ("contracts", "\n"),
    },
    key_order=[
        "schema_version", "id", "name", "aliases", "summary", "website", "status",
        "launched", "categories", "agent_roles", "autonomy_level", "human_oversight",
        "governance_model", "agent_stack", "legal_wrapper", "jurisdiction", "onchain",
        "links", "sources", "verification", "tags", "airtable_record_id", "added",
        "updated",
    ],
)


COLLECTIONS = [REGISTRY]
