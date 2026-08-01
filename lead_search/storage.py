"""Registry CSV persistence: load snapshots for dedup, merge and write results."""

import csv
import json
import re
from datetime import date
from pathlib import Path

FIELDNAMES = [
    "org_id", "org_name", "org_type", "org_type_notes", "geographic_scope",
    "areas_served", "website", "description", "source_urls", "status",
    "last_updated", "contact_name", "contact_title", "relevance_reason",
    "email", "email_source_url", "phone", "contact_method", "linkedin_url",
    "linkedin_confidence", "outreach_message",
]


def slugify(name: str) -> str:
    return re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9]+", "-", name.lower())).strip("-")[:60]


def load_registry_snapshot(registry_path: Path) -> list[dict]:
    """Distinct known orgs (org_id, org_name, geographic_scope, areas_served) for the Verify stage."""
    if not registry_path.exists():
        return []
    seen: dict[str, dict] = {}
    with registry_path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            org_id = row.get("org_id", "")
            if org_id and org_id not in seen:
                seen[org_id] = {
                    "org_id": org_id,
                    "org_name": row.get("org_name", ""),
                    "geographic_scope": row.get("geographic_scope", ""),
                    "areas_served": row.get("areas_served", ""),
                }
    return list(seen.values())


def build_rows(orgs: list, contacts: list) -> list[dict]:
    """Denormalize: one row per contact, org fields repeated; orgs with no contacts get one row."""
    contacts_by_org: dict[str, list] = {}
    for c in contacts:
        contacts_by_org.setdefault(c.org_id_hint, []).append(c)

    today = date.today().isoformat()
    rows = []
    for org in orgs:
        org_id = slugify(org.org_name)
        base = {
            "org_id": org_id,
            "org_name": org.org_name,
            "org_type": org.org_type,
            "org_type_notes": org.org_type_notes or "",
            "geographic_scope": org.geographic_scope,
            "areas_served": "; ".join(org.areas_served),
            "website": org.website,
            "description": org.description,
            "source_urls": "; ".join(org.source_urls),
            "status": org.status,
            "last_updated": today,
        }
        org_contacts = contacts_by_org.get(org_id, [])
        if not org_contacts:
            rows.append({**base, **{k: "" for k in FIELDNAMES if k not in base}})
            continue
        relevance = {p.name: p.relevance_reason for p in org.key_people}
        for c in org_contacts:
            rows.append({
                **base,
                "contact_name": c.name,
                "contact_title": c.title,
                "relevance_reason": relevance.get(c.name, ""),
                "email": c.email or "",
                "email_source_url": c.email_source_url or "",
                "phone": c.phone or "",
                "contact_method": c.contact_method,
                "linkedin_url": c.linkedin_url or "",
                "linkedin_confidence": c.linkedin_confidence,
                "outreach_message": c.outreach_message or "",
            })
    return rows


def append_to_registry(registry_path: Path, rows: list[dict]) -> None:
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not registry_path.exists()
    with registry_path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if write_header:
            writer.writeheader()
        writer.writerows(rows)


def write_run_log(out_dir: Path, run_name: str, payload: dict) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{run_name}.json"
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path
