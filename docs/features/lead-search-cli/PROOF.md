# Proof: Lead-Search CLI

## Primary proof command

```bash
python3 -m unittest discover -s tests -v
```

Covers the deterministic core that does not require an API key: `org_id` slug generation, contact-to-org joining via `org_id_hint`, orgs-without-contacts row emission, registry append without duplicate headers, and registry snapshot loading for the Verify stage.

## Live verification (manual, requires ANTHROPIC_API_KEY)

```bash
lead-search "food banks" --area "Medford, Massachusetts" --workers 2
```

Expected: a non-empty `registry.csv` with researched orgs and contacts, and a `runs/*.json` log containing candidates, verdicts, orgs, and contacts.
