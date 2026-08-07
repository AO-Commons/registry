# scripts/

| Script | Status | Purpose |
|---|---|---|
| [validate.py](validate.py) | working | Validates records against the schema and checks id/filename/bundle invariants. Runs in CI on every PR |
| `sync_from_airtable.py` | **not written** | Regenerates `data/` from the Airtable base |
| `intake_to_airtable.py` | **not written** | Forwards issue-form submissions into the Airtable intake table |

The two Airtable scripts have workflows waiting for them ([sync-from-airtable.yml](../.github/workflows/sync-from-airtable.yml), [intake-to-airtable.yml](../.github/workflows/intake-to-airtable.yml)), both gated off by repository variables so nothing runs half-configured.

## The data flow

```
GitHub issue form ─→ intake_to_airtable.py ─→ Airtable "Intake" table
                                                      │
                                              human review, editing
                                                      ↓
                                              Airtable "Registry" table
                                                      │
                                              sync_from_airtable.py
                                                      ↓
                                         data/aos/*.yml + data/registry.json
```

Airtable is the source of truth. `data/` is generated output, and pull requests editing it are closed rather than merged — the next sync would overwrite them.

Intake and registry are **separate tables**. A submission is a claim; a record is a verified claim. Keeping them apart means an unreviewed submission can never appear in published data because someone flipped a status field by accident.

## To finish the sync

1. **Build the Airtable base.** Fields must cover everything in [../schema/ao.schema.json](../schema/ao.schema.json) — a field that doesn't exist in the base can never be populated in the data. Airtable's multi-select options must match the schema enums exactly, or the sync becomes a translation layer nobody wants to maintain.
2. **Write `sync_from_airtable.py`.** Read the Registry table where a `Published` checkbox is true, map fields to schema keys, write one YAML per record named `<id>.yml`, and write `data/registry.json` as `{"generated": "<date>", "schema_version": "0.1", "organizations": [...]}`. Delete YAML files whose records are no longer published — but see the safety note below. Write deterministically: stable key order, stable list order, no timestamps inside individual records, or every run produces a diff.
3. **Write `intake_to_airtable.py`.** Parse the issue body (GitHub issue forms render as predictable `### Heading` sections), create an Intake record, and store the issue number so an edited issue updates its record instead of creating a second one.
4. **Set the repository variables and secret**, then flip `SYNC_ENABLED` / `INTAKE_ENABLED` to `true`:

   | Name | Kind | Value |
   |---|---|---|
   | `AIRTABLE_TOKEN` | secret | Personal access token, scoped to the registry base only — never the CRM base |
   | `AIRTABLE_BASE_ID` | variable | `app...` |
   | `AIRTABLE_TABLE_ID` | variable | Registry table |
   | `AIRTABLE_INTAKE_TABLE_ID` | variable | Intake table |
   | `SYNC_ENABLED` | variable | `true` |
   | `INTAKE_ENABLED` | variable | `true` |

## Two things to get right

**Scope the token to the registry base only.** A token with workspace-wide access sitting in a *public* repository's Actions secrets is one workflow-injection bug away from reading the CRM. The blast radius should be data that is already public.

**Make deletion safe.** The sync opens a pull request rather than pushing to `main`, so a bad run is reviewable rather than published. Beyond that, have the script refuse to proceed if it would remove more than a small fraction of existing records — an Airtable filter typo or an API returning an empty page should not silently empty the registry.

## Why not bidirectional

Two writable sides need per-field conflict resolution and a reconciliation loop, and the failure mode is silent divergence: two records that disagree, with no principled way to say which is right. One-way generation plus an issue-based intake path gets open contribution without that cost. The trade is that non-maintainers can't edit records directly — which is the correct trade for a registry whose value is that its claims are checked.
