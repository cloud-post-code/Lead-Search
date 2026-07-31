# Feature: Lead-Search CLI

A UI-free CLI that runs a four-stage org-search pipeline (Discover → Verify → Research → Contacts) for any user-supplied org type and target area, using the Claude API with server-side web search, and appends denormalized results to a flat `registry.csv`.

## Requirements

- `lead-search "<org type>" --area "<area>"` runs the full pipeline end to end.
- Verify stage dedupes against an existing registry snapshot and rejects wrong-area / wrong-type candidates before research budget is spent.
- Contacts join to orgs via a stable `org_id` slug echoed through the contact stage (no free-text name joins).
- Contacts without email/phone are kept with a `contact_method` classification, never silently dropped.
- Outreach drafting is optional, gated on `--purpose`.
- Refusals (`stop_reason == "refusal"`) and `pause_turn` continuations are handled; a declined item is skipped with a warning, not a crash.
- No UI of any kind; output is CSV + JSON run logs + terminal summary.
