# CLAUDE.md — AO Commons Registry (public)

This repository is **public**, and it is a data repository with an unusual constraint: most of it is generated.

## The one rule that governs everything

**Airtable is the source of truth. `data/` is a generated mirror.**

Never hand-edit files in [data/](data/). A sync run overwrites them, so an edit there is a change that silently disappears — worse than one that fails loudly. If a record is wrong, the fix goes into Airtable (via the MCP connector) or into an issue that a maintainer applies to the base.

Everything outside `data/` — schema, documentation, issue forms, workflows, scripts — is edited here normally.

## What this registry tracks

Autonomous organizations: organizations in which AI agents hold meaningful operational or governance roles alongside humans. The membership criterion is *authority*, not tooling. Agents holding an organizational function (governance, treasury, operations, research, development, moderation, external representation) qualify; an organization that merely uses models to produce content does not.

## Evidentiary standards

These matter more here than the schema does.

1. **Record what is evidenced, not what is claimed.** Organizations overstate their autonomy, because autonomy is the interesting part of the story. A launch post saying "fully autonomous" next to a governance doc requiring human signatures is `delegated` or `supervised-autonomous`. Read the governance document, not the announcement.
2. **`undetermined` and `unknown` are correct answers.** When sources conflict or are silent, say so. A confident wrong value is worse than an honest gap, because it propagates into other people's analyses.
3. **Every record needs sources, and every contested field should name which source supports it** via `sources[].supports`.
4. **Never infer a field to fill it in.** Absent evidence, omit an optional field.
5. **`summary` is descriptive, not promotional.** Neutral prose, no marketing language, even where the organization's own copy is the only source.

## Working with records

- `id` is a stable slug matching the filename. It never changes once published — downstream citations depend on it. Renamed organizations keep the slug and gain an `aliases` entry.
- Records validate against [schema/ao.schema.json](schema/ao.schema.json) in CI. [schema/example.yml](schema/example.yml) shows every field populated.
- Self-reported records are listed and labelled `verification.method: self-reported`. That is a label, not a lesser tier.

## Public-repo hygiene

No internal identifiers — no Google Docs links, no CRM record IDs, no internal Drive paths. The `airtable_record_id` field is the sole intended Airtable reference, and it points at the public registry base only, never the CRM.

Personal data does not belong here. The registry tracks organizations. Individual founders, staff, and contact details are out of scope even when publicly available — including in issue threads, which should be edited if a submitter includes them.

git history is public. A committed mistake is a published mistake.

## Voice

Terse and factual in data; plain and unhyped in prose. Define terms on first use — readers span governance researchers, engineers, funders, and university administrators. Dates in ISO format (YYYY-MM-DD).
