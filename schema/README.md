# schema/

| File | Purpose |
|---|---|
| [ao.schema.json](ao.schema.json) | Schema (draft 2020-12) for `data/aos/` — autonomous organizations |


## The fields that carry the weight

Most of the schema is bookkeeping. Four fields are the reason the registry exists, and they are the ones to get right.

**`agent_roles`** — which organizational functions agents actually hold. This is the membership criterion: an organization where agents write marketing copy is not an AO in the sense we mean, and one where agents allocate a treasury is. Where a claim can't be substantiated, `none-claimed` keeps the record listed while the investigation continues.

**`autonomy_level`** — how much authority agents exercise, from `advisory` through `autonomous`. This is where the registry earns or loses its credibility. Organizations describe themselves as more autonomous than they are, because autonomy is the interesting part of the story. **Record what the evidence supports, not what the organization claims.** A press release saying "fully autonomous" alongside a governance document requiring human signatures is `delegated` or `supervised-autonomous`, not `autonomous`. When sources genuinely conflict, `undetermined` is the honest answer and is always better than a guess.

**`human_oversight`** — the prose counterpart to `autonomy_level`: the specific mechanisms (thresholds, vetoes, review cadence, kill switches) that make the level a fact rather than an adjective. If this field is hard to write, the `autonomy_level` is probably not yet known.

An AO need not have humans in it, so "none" is a legitimate value — but write it explicitly. Omitting the field reads as "not yet researched", which is a materially different claim from "we looked, and there is no human checkpoint."

**`sources`** — at least one, required. An unsourced entry is a rumor. `supports` names which fields each source is evidence for, which is what makes a claim auditable by a reader who doubts it.

## Self-reported records

We list them. `verification.method: self-reported` is not a lesser tier of membership, it is an accurate label — the alternative, quietly excluding organizations we haven't independently confirmed, would make the registry less complete without making it more honest. Readers can filter on the field.

## Changing the schema

The schema is public infrastructure; other people's tooling reads it.

1. Open an issue describing the change and what it breaks.
2. Update this file and `ao.schema.json` together with the Airtable base's field definitions — the base is the source of truth for records, so a field that exists here but not there can never be populated.
3. Additive, optional fields are a minor version. Removing a field, renaming one, tightening an enum, or making an optional field required is breaking.
4. `id` values never change once published. Downstream citations depend on them. An organization that renames itself keeps its slug and gains an entry in `aliases`.
