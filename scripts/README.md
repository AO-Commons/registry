# scripts/

| Script | Purpose |
|---|---|
| [setup_airtable_base.py](setup_airtable_base.py) | Builds the three tables in an empty base. Run once |
| [check_airtable_base.py](check_airtable_base.py) | Compares the live base against what the scripts expect. Read-only; worth re-running periodically |
| [validate.py](validate.py) | Validates records against the schema and checks id/filename/bundle invariants. Runs in CI |
| [sync_from_airtable.py](sync_from_airtable.py) | Regenerates `data/` from the Airtable base |
| [intake_to_airtable.py](intake_to_airtable.py) | Forwards issue-form submissions into the Airtable Intake table |
| [airtable_fields.py](airtable_fields.py) | The Airtable-field ↔ schema-key mapping the other scripts import |

The sync workflows ([sync-from-airtable.yml](../.github/workflows/sync-from-airtable.yml), [intake-to-airtable.yml](../.github/workflows/intake-to-airtable.yml)) are gated off by repository variables until the base and credentials exist, so nothing runs half-configured.

**The base structure is code, not clicks.** [setup_airtable_base.py](setup_airtable_base.py) derives every select field's options from [../schema/ao.schema.json](../schema/ao.schema.json) at runtime, so the Airtable vocabulary cannot drift from the schema enums — not "be compatible with" them, *equal* them. Anything less turns the sync into a translation layer, and translation layers rot.

[airtable_fields.py](airtable_fields.py) is the other half of that seam: **a field renamed in Airtable is a change there**, and nowhere else.

[../tests/test_mapping.py](../tests/test_mapping.py) runs in CI and checks the whole seam holds — that select options equal schema enums, that every field the scripts read or write exists in the base definition, and that every option the intake form offers is a value the schema accepts. These are the failures that don't raise errors when they happen; they just produce records that quietly say the wrong thing.

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

## Turning it on

0. **Build the base.** Create an empty Airtable base, then run the setup script against it with a **temporary** token carrying `schema.bases:write`:

   ```sh
   export AIRTABLE_TOKEN=...        # temporary, schema.bases:write
   export AIRTABLE_BASE_ID=app...   # from the base URL
   python3 scripts/setup_airtable_base.py
   ```

   Delete that token afterwards. The runtime sync token must not be able to alter the base structure — reading and writing records is all it ever needs.

   The script is safe to re-run: existing tables are reported and skipped, never overwritten.

   Then confirm the base matches the scripts:

   ```sh
   python3 scripts/check_airtable_base.py
   ```

   Re-run that check whenever someone has been editing the base by hand. Renaming a field or retyping a select option doesn't make the sync fail — it makes the sync silently stop populating that field, which is worse.

1. **Create the runtime personal access token.** Scope it to the **registry base only** — never the CRM base — with `data.records:read`, `data.records:write`, and `schema.bases:read`. Set an expiry and a calendar reminder to rotate it.
2. **Add the secret and variables** to `AO-Commons/registry`. Pipe the token from your clipboard rather than pasting it into a command, so it never lands in shell history:

   ```sh
   pbpaste | gh secret set AIRTABLE_TOKEN --repo AO-Commons/registry --app actions
   gh variable set AIRTABLE_BASE_ID --repo AO-Commons/registry --body "app..."
   ```

3. **Flip the gates** once you've confirmed a manual run works:

   ```sh
   gh variable set SYNC_ENABLED   --repo AO-Commons/registry --body true
   gh variable set INTAKE_ENABLED --repo AO-Commons/registry --body true
   ```

   | Name | Kind | Value |
   |---|---|---|
   | `AIRTABLE_TOKEN` | secret | PAT scoped to the registry base only |
   | `AIRTABLE_BASE_ID` | variable | `app...` |
   | `SYNC_ENABLED` | variable | `true` |
   | `INTAKE_ENABLED` | variable | `true` |

   Table names are constants in [airtable_fields.py](airtable_fields.py) rather than variables — they're part of the schema contract, not deployment configuration.

4. **Dry-run the sync locally first**, against a base with one or two records, before letting the schedule touch `main`:

   ```sh
   export AIRTABLE_TOKEN=...   # from your password manager, not a committed file
   export AIRTABLE_BASE_ID=app...
   python3 scripts/sync_from_airtable.py && python3 scripts/validate.py
   ```

## The one piece that isn't code

Airtable automations have no public REST API, so this is set up by hand — once, in about a minute. It enforces that **Published can't stay ticked on an incomplete record**:

> **Trigger:** When record matches conditions
> — Table `Registry`, conditions: `Published` is checked **AND** `Publish Blockers` is not empty
>
> **Action:** Update record (the triggering record)
> — `Published` → unchecked
> — `Review State` → `Insufficient information`

`Publish Blockers` is a formula field listing the required fields still empty; it's blank exactly when a record is publishable. Required fields are marked with a trailing `*` in their names, so the requirement is visible in the grid without consulting docs.

Note what `Review State` is *not*: it is not the schema's `status`. `status` describes the organization (`active`, `dormant`, `sunset`); `Review State` describes our confidence in the record. Putting "insufficient information" into `status` would emit records that fail validation, and [check_airtable_base.py](check_airtable_base.py) would report it as drift. The two vocabularies are asserted disjoint in [../tests/test_mapping.py](../tests/test_mapping.py).

This automation is defence in depth rather than the primary guard — the sync already refuses to publish a record that fails validation, and would do so even if the automation were deleted. It exists so the failure surfaces in Airtable, at the moment someone ticks the box, instead of hours later in a sync log.

## Two things this gets right, deliberately

**The token is scoped to the registry base only.** A workspace-wide token sitting in a *public* repository's Actions secrets is one workflow-injection bug away from reading the CRM. The blast radius should be data that is already public.

**Deletion is guarded.** The sync opens a pull request rather than pushing to `main`, so a bad run is reviewable rather than published. On top of that, `sync_from_airtable.py` refuses to run if it would remove more than a quarter of existing records — an Airtable filter typo or an API page returning empty should not silently empty the registry. Override with `SYNC_ALLOW_DELETIONS=1` once you've confirmed the removal is intended.

A record that fails schema validation is skipped and named in the run summary rather than written, so one malformed row doesn't block every other update — but the skip is always visible, never silent.

## Why not bidirectional

Two writable sides need per-field conflict resolution and a reconciliation loop, and the failure mode is silent divergence: two records that disagree, with no principled way to say which is right. One-way generation plus an issue-based intake path gets open contribution without that cost. The trade is that non-maintainers can't edit records directly — which is the correct trade for a registry whose value is that its claims are checked.
