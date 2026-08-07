# data/ — generated, do not edit

Everything in this folder is generated from the Airtable registry base. **Pull requests editing these files will be closed** — the next sync overwrites them, so the change would vanish without anyone noticing.

To fix a record, [open a correction issue](../../../issues/new?template=correction.yml). It lands in the base, which is where it sticks.

| Path | Contents |
|---|---|
| `aos/<id>.yml` | One organization per file. Filename always matches the record's `id` |
| `registry.json` | Every record in one file, for programmatic use |

Records validate against [../schema/ao.schema.json](../schema/ao.schema.json) — see [../schema/README.md](../schema/README.md) for what the fields mean and how to read `autonomy_level` in particular.

> **Empty for now.** The schema, intake forms, and validation are in place; the Airtable sync is not yet wired up. Records are being collected in the base. See [../scripts/README.md](../scripts/README.md).
