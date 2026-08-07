#!/usr/bin/env python3
"""Create the first Tooling records and their sources in Airtable.

Airtable is the source of truth, so records cannot simply be written into
data/ — the next sync would delete them as unpublished. This script puts them
where they belong, and exists in the repository so the provenance of the
first two entries is reviewable rather than being someone's untracked typing.

Idempotent: records and sources already present are left alone, so re-running
after a partial failure is safe. It never edits an existing record — if you
have since corrected one of these by hand, that correction stands.

Usage:  python3 scripts/seed_tooling.py
Env:    AIRTABLE_TOKEN, AIRTABLE_BASE_ID
Requires: pip install requests
"""

import os
import sys

import requests

from airtable_fields import SOURCES_LINK_FIELD, SOURCES_TABLE, TOOLING_TABLE

API = "https://api.airtable.com/v0"
ACCESSED = "2026-08-07"

# Every claim below is traceable to one of these. `supports` names which
# fields each backs, which is what lets a reader check one specific claim.
SOURCES = {
    "paperclip-repo": {
        "URL *": "https://github.com/paperclipai/paperclip",
        "Title": "Paperclip — repository",
        "Accessed *": ACCESSED,
        "Supports": "license, languages, open_source, launched",
    },
    "paperclip-site": {
        "URL *": "https://paperclip.ing/",
        "Title": "Paperclip — product site",
        "Accessed *": ACCESSED,
        "Supports": "agent_model, human_controls, self_hostable, maintainer",
    },
    "paperclip-docs": {
        "URL *": "https://docs.paperclip.ing/guides/org/agents/",
        "Title": "Paperclip Docs — Agents",
        "Accessed *": ACCESSED,
        "Supports": "agent_model",
    },
    "buzz-announcement": {
        "URL *": "https://block.xyz/inside/introducing-buzz-where-humans-and-agents-work-together",
        "Title": "Introducing Buzz: where humans and agents work together",
        "Accessed *": ACCESSED,
        "Supports": "agent_model, protocols, model_agnostic, launched",
    },
    "buzz-repo": {
        "URL *": "https://github.com/block/buzz",
        "Title": "Buzz — repository",
        "Accessed *": ACCESSED,
        "Supports": "license, languages, open_source, self_hostable",
    },
}

RECORDS = [
    {
        "sources": ["paperclip-repo", "paperclip-site", "paperclip-docs"],
        "fields": {
            "ID *": "paperclip",
            "Name *": "Paperclip",
            "Summary *": (
                "An open-source Node.js and React application for orchestrating teams of AI "
                "agents against business goals, with org charts, per-agent budgets, and "
                "approval gates. Users bring their own agents from any provider."
            ),
            "Website": "https://paperclip.ing",
            "Status *": "active",
            "Launched": "2026-03-02",
            "Categories *": ["orchestration", "governance", "observability"],
            "Agent Model": (
                "Agents are managed workers arranged in an org chart — described as employees "
                "that wake on scheduled \"heartbeats\", execute assigned work, and go dormant "
                "between runs. They do not set direction or hold budget authority; the "
                "documentation places humans in the role of the board of directors."
            ),
            "Human Controls": (
                "Human approval required before an agent is hired and before an agent executes "
                "a strategy. Per-agent and per-project budgets that auto-pause execution when "
                "limits are hit. Any agent can be paused, resumed, overridden, reassigned, or "
                "terminated. Full run transcripts and per-agent cost tracking."
            ),
            "Maintainer": "Paperclip Labs, Inc.",
            "Open Source": "yes",
            "License": "MIT",
            "Self Hostable": "yes",
            "Model Agnostic": "yes",
            "Languages": "TypeScript",
            "Link: Repo": "https://github.com/paperclipai/paperclip",
            "Link: Docs": "https://docs.paperclip.ing",
            "Link: X": "https://x.com/papercliping",
            "Link: Discord": "https://discord.gg/m4HZY7xNG3",
            "Verification Method *": "documented",
            "Verified On *": ACCESSED,
            "Verified By": "ao-commons-research",
            "Verification Notes": (
                "Maintainer taken from the site's copyright line, not a stated legal entity. "
                "Controls read from documentation, not exercised against a running instance."
            ),
            "Tags": "agent-management, budget-caps, approval-gates",
            "Review State": "Ready to publish",
            "Published": True,
            "Added": ACCESSED,
            "Updated": ACCESSED,
        },
    },
    {
        "sources": ["buzz-announcement", "buzz-repo"],
        "fields": {
            "ID *": "buzz",
            "Name *": "Buzz",
            "Summary *": (
                "A self-hostable workspace where humans and AI agents share the same channels, "
                "threads, code repositories, and workflows. Built as a Nostr relay, so every "
                "message, review approval, and git event is a signed event in one log."
            ),
            "Website": "https://buzz.xyz",
            "Status *": "active",
            "Launched": "2026-07-21",
            "Categories *": ["collaboration", "identity"],
            "Agent Model": (
                "Agents are participants rather than command-responders, holding their own "
                "cryptographic Nostr identities and defined permissions. They post, review "
                "code, send patches, and run approved workflows alongside humans under the "
                "same identity model. Block's announcement is explicit that this makes agents "
                "teammates, not holders of organizational authority."
            ),
            "Human Controls": (
                "Per-agent permission scopes, and automations that must be approved before an "
                "agent can run them. Every action by human or agent is a signed event in an "
                "append-only log, so the audit trail is inherent rather than a feature. "
                "Self-hosting means the operator controls the relay."
            ),
            "Maintainer": "Block, Inc.",
            "Open Source": "yes",
            "License": "Apache-2.0",
            "Self Hostable": "yes",
            "Model Agnostic": "yes",
            "Languages": "Rust",
            "Protocols": "nostr",
            "Link: Repo": "https://github.com/block/buzz",
            "Link: Blog": "https://block.xyz/inside/introducing-buzz-where-humans-and-agents-work-together",
            "Verification Method *": "documented",
            "Verified On *": ACCESSED,
            "Verified By": "ao-commons-research",
            "Verification Notes": (
                "Launch date is the public announcement; the repository was created 2026-03-06, "
                "months earlier. Controls read from documentation, not exercised against a "
                "running instance."
            ),
            "Tags": "nostr, self-hostable, agent-identity",
            "Review State": "Ready to publish",
            "Published": True,
            "Added": ACCESSED,
            "Updated": ACCESSED,
        },
    },
]


def api(method: str, path: str, token: str, **kwargs) -> dict:
    response = requests.request(
        method,
        f"{API}/{path}",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=30,
        **kwargs,
    )
    if not response.ok:
        raise requests.HTTPError(f"{response.status_code}: {response.text}", response=response)
    return response.json()


def fetch_all(base_id: str, table: str, token: str) -> list[dict]:
    records, offset = [], None
    while True:
        params = {"pageSize": 100}
        if offset:
            params["offset"] = offset
        payload = api("GET", f"{base_id}/{table}", token, params=params)
        records.extend(payload.get("records", []))
        offset = payload.get("offset")
        if not offset:
            return records


def main() -> int:
    token = os.environ.get("AIRTABLE_TOKEN")
    base_id = os.environ.get("AIRTABLE_BASE_ID")
    if not token or not base_id:
        print("AIRTABLE_TOKEN and AIRTABLE_BASE_ID must be set.", file=sys.stderr)
        return 2

    # Sources are shared across both collections, so match on URL rather than
    # creating a second row for a report already cited elsewhere.
    existing_sources = {
        row["fields"].get("URL *"): row["id"]
        for row in fetch_all(base_id, SOURCES_TABLE, token)
        if row.get("fields", {}).get("URL *")
    }
    source_ids: dict[str, str] = {}
    for key, fields in SOURCES.items():
        url = fields["URL *"]
        if url in existing_sources:
            source_ids[key] = existing_sources[url]
            print(f"source already present: {url}")
            continue
        created = api("POST", f"{base_id}/{SOURCES_TABLE}", token,
                      json={"records": [{"fields": fields}]})
        source_ids[key] = created["records"][0]["id"]
        print(f"created source: {url}")

    existing_tools = {
        row["fields"].get("ID *")
        for row in fetch_all(base_id, TOOLING_TABLE, token)
        if row.get("fields", {}).get("ID *")
    }

    for record in RECORDS:
        record_id = record["fields"]["ID *"]
        if record_id in existing_tools:
            print(f"tool already present, left untouched: {record_id}")
            continue
        fields = dict(record["fields"])
        fields[SOURCES_LINK_FIELD] = [source_ids[key] for key in record["sources"]]
        api("POST", f"{base_id}/{TOOLING_TABLE}", token, json={"records": [{"fields": fields}]})
        print(f"created tool: {record_id} ({len(fields[SOURCES_LINK_FIELD])} sources)")

    print(
        "\nDone. Next:\n"
        "  python3 scripts/sync_from_airtable.py && python3 scripts/validate.py\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
