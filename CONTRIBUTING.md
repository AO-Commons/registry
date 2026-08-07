# Contributing

The registry is only as good as the corrections it receives. Both are welcome and both go through issues.

- **[Add an organization](../../issues/new?template=new-ao.yml)** — including your own
- **[Correct an entry](../../issues/new?template=correction.yml)** — especially our autonomy assessments

## Why not a pull request?

Because `data/` is generated. Airtable is the source of truth, and a sync run would overwrite any file you edited here — your change would disappear without failing loudly, which is the worst kind of change. Issues land in the base, which is where they stick.

Pull requests are welcome for everything *outside* `data/`: schema improvements, documentation, workflows, scripts.

## What we need from a submission

**At least one source.** An unsourced entry is a rumor and won't be listed. Governance documents, forum threads, contracts, and announcements all count; a landing page saying "AI-powered" does not.

**Specifics about oversight.** The mechanisms that keep humans in control — multisig thresholds, veto rights, spending limits, review cadence. "There is human oversight" tells us nothing and is the most common reason a submission stalls.

**Honesty about autonomy.** This is the field we care most about and the one most often overstated, because autonomy is the interesting part of the story. We record what sources support, so a launch post claiming full autonomy alongside a governance doc requiring signatures will be listed as `delegated` or `supervised-autonomous`. If you'd rather that read differently, the thing to change is the evidence, not the claim.

## Self-submissions

Encouraged. They're labelled `verification.method: self-reported`, which describes how the record was verified rather than ranking it below others. Readers can filter on the field and decide for themselves.

We hold self-submissions to the same source requirement, and we'll write the `summary` in neutral language even where your own copy is the only source available.

## What happens next

1. A maintainer reads the issue and checks the sources.
2. If something's missing we'll ask in the thread. If we can't verify a load-bearing claim, we may list the record with `undetermined` fields rather than not listing it.
3. Accepted records enter the Airtable base and appear in `data/` at the next sync.
4. We aim to respond within about two weeks. If we've gone quiet, a nudge is fair.

We may decline organizations where agents hold no organizational function — where models are used as tooling rather than holding authority. That's a scope judgment, not one about quality, and we'll say so plainly.

## Please don't include personal data

The registry tracks organizations. Founders' and staff members' names, emails, and handles are out of scope even when publicly available. We'll edit them out of issues.

## Terms

Contributions are licensed [CC BY 4.0](LICENSE). By contributing you confirm you have the right to license the material that way. Participation is governed by our [Code of Conduct](CODE_OF_CONDUCT.md).

Listing is not endorsement, and nothing here is diligence.
