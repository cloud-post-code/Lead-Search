# Lead-Search

A UI-free command-line pipeline that discovers, verifies, and researches organizations of **any type you name** in a target area, finds key people with public contact info, and (optionally) drafts personalized outreach messages. Results accumulate in a flat `registry.csv`.

Ported from a Claude Code multi-agent Workflow into a standalone tool built on the Claude API with server-side web search.

## Pipeline

1. **Discover** — web-searches for orgs matching your description in the target area (6-8+ distinct queries, each candidate confirmed against its own site; every org requires a real evidence URL).
2. **Verify** — dedupes candidates against the existing registry (tolerant name matching), rejects wrong-area false positives (same-name/different-state traps), and gates on whether each org genuinely matches the requested type.
3. **Research** — per new org, in parallel: official website, refined type, geographic scope, a description written from the org's own site content, and 1-3 key people.
4. **Contacts** — per person, in parallel: publicly listed email/phone (never guessed, never de-obfuscated), LinkedIn profile with honest confidence rating, and an optional custom outreach draft.

## Install

```bash
pip install .
export ANTHROPIC_API_KEY=sk-ant-...
```

## Usage

```bash
# Basic: build a registry of food banks serving Worcester
lead-search "food banks and mutual aid groups" --area "Worcester, Massachusetts"

# With outreach drafting
lead-search "youth sports leagues" --area "Medford, Massachusetts" \
  --purpose "invite them to a community field day event" \
  --sender "Chris from the Mainstreet initiative"
```

Options:

| Flag | Default | Meaning |
|---|---|---|
| `--area` | (required) | Town, city, county, region, or state |
| `--purpose` | off | Enables outreach message drafting |
| `--sender` | `[Your name]` | Signature for outreach messages |
| `--registry` | `registry.csv` | Registry to dedupe against and append to |
| `--out` | `runs/` | Raw JSON run logs |
| `--model` | `claude-opus-5` | Claude model ID |
| `--workers` | `4` | Parallel research/contact lookups |

Re-running with the same registry is safe: the Verify stage loads a snapshot of known orgs and skips or extends them instead of re-researching.

## Output

- `registry.csv` — one row per contact, org fields repeated (orgs with no kept contacts get one row with blank contact fields). Contacts join to orgs via a stable `org_id` slug echoed through the contact stage, not fragile name matching.
- `runs/<timestamp>-<slug>.json` — full raw output of every stage for auditing.

Contacts are never dropped for lacking email/phone — each carries a `contact_method` field (`email` / `phone` / `linkedin_only` / `org_contact_form` / `none_found`) so you decide downstream what to keep.

## Tests

```bash
python3 -m unittest discover -s tests
```

## Notes

- Requires an `ANTHROPIC_API_KEY` (or an `ant auth login` profile).
- Uses server-side `web_search` / `web_fetch` tools — no scraping infrastructure needed.
- Contact lookup only reports plainly published info; masked/obfuscated addresses are treated as not found.
