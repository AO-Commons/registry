# AO Commons — Registry

A public registry of **autonomous organizations**: organizations in which AI agents hold meaningful operational or governance roles alongside humans.

Maintained by [AO Commons](https://github.com/AO-Commons), under Stanford Open Lab.

## What counts as an AO

Agents must hold an organizational *function* — governance, treasury, operations, research, development, moderation, or external representation — not merely produce content that humans then use. The line is authority, not tooling. An organization that runs its writing through a model is not in scope; one that lets agents allocate a budget is.

Each record states how much authority agents actually exercise (`autonomy_level`) and what keeps humans in control (`human_oversight`), sourced field by field. Organizations routinely describe themselves as more autonomous than they are — the registry records what the evidence supports, and marks the gap when sources conflict.

## Using the data

| Path | What it is |
|---|---|
| [data/aos/](data/aos/) | One YAML file per organization, named `<id>.yml` |
| [data/registry.json](data/) | All records in a single JSON file, for programmatic use |
| [schema/ao.schema.json](schema/ao.schema.json) | JSON Schema every record validates against |
| [schema/README.md](schema/README.md) | What each field means and how to read it |

Record `id`s are stable and safe to cite. They never change, even when an organization renames itself — the old name moves to `aliases`.

Data is licensed [CC BY 4.0](LICENSE). Use it, build on it, cite it.

## Adding or correcting an entry

Open an issue — there are forms for both:

- **[Add an organization](../../issues/new?template=new-ao.yml)** — including your own. Self-submissions are welcome and are labelled `self-reported` rather than treated as lesser.
- **[Correct an entry](../../issues/new?template=correction.yml)** — especially where we've overstated or understated autonomy. Corrections with sources are the most useful thing you can send us.

See [CONTRIBUTING.md](CONTRIBUTING.md) for what happens next.

## How this repository is maintained

**Airtable is the source of truth. The files in `data/` are a generated mirror.**

```
issue form  →  review  →  Airtable base  →  sync job  →  data/*.yml  →  this repo
```

Pull requests editing `data/` will not be merged — a sync would overwrite them at the next run. Send corrections as issues and they land in the base, which is where they stick. Everything outside `data/` (schema, docs, workflows) is edited here normally.

Every record links back to its Airtable record via `airtable_record_id`, so any published row can be traced to its origin.

> **Status: the sync is not yet wired up.** The schema, intake forms, and validation are in place; the Airtable connection is the next piece of work. Until then, `data/` is empty and records are being collected in the base. See [scripts/README.md](scripts/README.md) for the design.

## Companion repository

**research** — memos and landscape analyses that draw on this data. Registry entries are cited there by `id`.

## Caveats

This registry is incomplete and will stay that way; the space moves faster than verification does. Entries reflect the last `verification.verified_on` date and may be stale. Listing is not endorsement, and nothing here is diligence — several listed organizations custody real money on claims we have not independently audited.
