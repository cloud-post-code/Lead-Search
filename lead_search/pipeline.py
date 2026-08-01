"""Discover -> Verify -> Research -> Contacts pipeline over the Claude API."""

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from .claude_client import ClaudeRunner, RefusalError
from .schemas import (
    Contact,
    DiscoveryResult,
    EmailHuntResult,
    OrgDetail,
    VerificationResult,
)
from .storage import slugify

log = logging.getLogger("lead_search")


@dataclass
class RunConfig:
    org_type: str
    area: str
    purpose: str = ""
    sender: str = ""
    model: str = "claude-opus-5"
    workers: int = 4
    deep_email_hunt: bool = True


def discover(runner: ClaudeRunner, cfg: RunConfig) -> list:
    prompt = (
        f'Find organizations matching this description: "{cfg.org_type}" — located in or '
        f"genuinely serving {cfg.area}.\n\n"
        "Use web search as your primary discovery tool: run at least 6-8 distinct queries "
        "combining the org type with the area, synonyms for the org type, directory-style "
        'queries ("list of ...", "directory ..."), and umbrella/association bodies that '
        "maintain member lists for this org type. Fetch each candidate org's own website "
        "(or an authoritative directory page) to confirm it before including it.\n\n"
        "Interpret the org type generously enough to catch close variants (e.g. programs run "
        "inside a larger parent institution that function as this org type), but do NOT pad "
        "the list with orgs that merely mention the topic. Every org must come with an "
        "evidence URL you actually saw that shows it exists and plausibly matches the type.\n\n"
        "List every org you find with its name, a guess at its subtype, whether it seems "
        f"specific to {cfg.area} or broader (regional/statewide/national), and why it is "
        "relevant. Aim for thoroughness."
    )
    result = runner.research_and_extract(prompt, DiscoveryResult)
    return result.orgs


def verify(runner: ClaudeRunner, cfg: RunConfig, candidates: list, known: list) -> list:
    existing = json.dumps(known, indent=2) if known else "No existing registry — first run."
    prompt = (
        f'You are the verification/dedup gate for an org registry. Requested org type: '
        f'"{cfg.org_type}". Target area: {cfg.area}.\n\n'
        f"Existing registry (JSON list of {{org_id, org_name, geographic_scope, areas_served}}):\n"
        f"{existing}\n\n"
        f"Candidate orgs just discovered:\n"
        f"{json.dumps([c.model_dump() for c in candidates], indent=2)}\n\n"
        "MANDATORY FIRST STEP per candidate: scan the ENTIRE existing registry and ask "
        '"is this the same real-world organization as any entry?" Treat orgs as the SAME '
        "even if the name differs slightly (punctuation, abbreviations, parentheticals, "
        "location suffixes). If in doubt, they usually are the same — lean toward matching. "
        "Record closest_registry_match_org_id and same_organization_as_match BEFORE deciding.\n\n"
        "THEN decide exactly one of:\n"
        f'- "already_known_same_scope": same org, areas_served already covers {cfg.area}.\n'
        f'- "already_known_new_area": same org, genuinely multi-area, {cfg.area} is NEW for it. '
        "Set matched_existing_org_id.\n"
        '- "new_org_confirmed": no registry match AND verified (via the org\'s own '
        f"description/service-area language, not just search proximity) that it serves {cfg.area}.\n"
        '- "false_positive_wrong_area": belongs to a different area (similarly-named org '
        "elsewhere, or a neighbor that surfaced from search proximity) with no real evidence "
        f"it serves {cfg.area}. Watch for same-name/different-state traps.\n\n"
        "Be conservative: only mark is_multi_area=true when the org's own materials say so.\n\n"
        "ADDITIONALLY, for every candidate judge genuinely_matches_org_type: does it actually "
        f'fit "{cfg.org_type}" as its real mission/activity — not keyword overlap? Default '
        "true; only mark false with a clear reason. Explain reasoning per org."
    )
    result = runner.extract(prompt, VerificationResult)
    return result.verdicts


def research_org(runner: ClaudeRunner, cfg: RunConfig, verdict, candidate) -> OrgDetail:
    people_guidance = (
        f'Identify 1-3 key people to reach out to given this purpose: "{cfg.purpose}". '
        "Prefer people whose role directly touches that purpose (program leads, directors, "
        "coordinators) over pure administrative/finance roles."
        if cfg.purpose
        else "Identify 1-3 key people who lead or represent the organization (executive "
        "director, program lead, founder, main public contact)."
    )
    evidence = f"Known evidence URL: {candidate.evidence_url}\n" if candidate and candidate.evidence_url else ""
    prompt = (
        f'Research this organization: "{verdict.org_name}" (org type sought: "{cfg.org_type}"), '
        f"verified relevant in/serving {cfg.area}. Context: "
        f"{(candidate.why_relevant if candidate else verdict.reasoning)}\n{evidence}\n"
        "Steps:\n"
        "1. Find and confirm its official website (web search, then fetch it).\n"
        f'2. Record org_type as "{cfg.org_type}" refined with a specific subtype if clear; '
        "use org_type_notes for anything ambiguous.\n"
        f"3. Determine geographic scope and list the areas it serves (include {cfg.area}).\n"
        "4. Fetch the site's about/mission page and write a 2-4 sentence description from the "
        "org's OWN content — not generic boilerplate. Record the page URLs used.\n"
        f"5. {people_guidance} Find them on the site's staff/team/leadership pages and explain "
        "why each is relevant.\n\n"
        'If no working website can be found, set status "no_website_found"; use '
        '"needs_review" if details are ambiguous or thin.'
    )
    return runner.research_and_extract(prompt, OrgDetail)


def find_contact(runner: ClaudeRunner, cfg: RunConfig, org: OrgDetail, person) -> Contact:
    org_id = slugify(org.org_name)
    outreach_step = (
        f"3. Draft a custom outreach message (under 150 words, warm, specific — reference "
        f"something REAL about the org's mission/programs from its own site). Purpose: "
        f"{cfg.purpose}. Sign off as: {cfg.sender or '[Your name]'}."
        if cfg.purpose
        else "3. Leave outreach_message empty — no outreach purpose was configured."
    )
    prompt = (
        f'Find contact information and LinkedIn for: {person.name}, {person.title} at '
        f'"{org.org_name}" (website: {org.website or "unknown"}). '
        f"Relevance: {person.relevance_reason}\n"
        f"org_id_hint (echo back verbatim): {org_id}\n\n"
        "Steps:\n"
        "1. Fetch the org's staff/team/about/contact pages for this person's email and/or "
        "phone. Only report info plainly published and directly readable — leave fields empty "
        "if not found; do not guess or fabricate. NEVER attempt to decode, un-obfuscate, or "
        "bypass an email-masking or anti-scraping mechanism — treat masked addresses as not "
        "found. Set contact_method to the best channel actually found (org_contact_form "
        "counts if the site only offers a form; none_found if nothing).\n"
        "2. LinkedIn: find/confirm the person's profile and rate confidence honestly "
        '("confirmed" only with strong matching evidence — org and role align; "likely" for '
        "a plausible but unconfirmed match).\n"
        f"{outreach_step}"
    )
    return runner.research_and_extract(prompt, Contact)


def hunt_email(runner: ClaudeRunner, contact: Contact) -> EmailHuntResult:
    """Search legitimate public sources for a genuinely PUBLISHED email — never guessed."""
    prompt = (
        f"Find a publicly PUBLISHED email address (and phone, if published) for: "
        f"{contact.name}, {contact.title} at {contact.org_name}. "
        f"LinkedIn: {contact.linkedin_url or 'unknown'}\n\n"
        "STRICT RULES:\n"
        "- Only report an email you can see VERBATIM on a page you actually fetched. Record "
        "the exact URL and quote the surrounding context. If you did not see the literal "
        'address on a fetched page, email_status is not "found".\n'
        "- NO pattern guessing: never construct addresses from name/company format "
        "conventions.\n"
        "- NO enrichment or contact-scraping services (Hunter, Apollo, RocketReach, "
        "ZoomInfo, ContactOut, Lusha, or similar) — their data is aggregated/guessed.\n"
        "- NO de-obfuscation of script- or image-protected addresses; transcribing a "
        'deliberate "name [at] domain" spelling the person published themselves is fine. '
        'Set email_status "only_masked_found" when only protected addresses exist.\n\n'
        "WHERE TO LOOK: personal website/blog contact pages; GitHub profile page or profile "
        "README (profile only — do not mine commit metadata); academic papers (arXiv, ACM, "
        "IEEE author blocks); conference speaker bios; university/guest-lecturer pages; "
        "press releases with a direct contact; podcast/newsletter about-pages; social "
        "profile bios where the person lists an address themselves.\n\n"
        "IDENTITY CHECK: confirm the address belongs to THIS person (name + role/company "
        "context align), not a namesake; set identity_confidence honestly. If the source is "
        "old or a previous employer, still report it but set email_is_stale_risk true.\n"
        "Prefer current-company > personal > stale old-employer address. If nothing is "
        'genuinely published, return email_status "not_published" — an honest, valid result.'
    )
    return runner.research_and_extract(prompt, EmailHuntResult)


def _apply_email_hunt(contact: Contact, hunt: EmailHuntResult) -> None:
    if hunt.email_status != "found" or not hunt.email:
        return
    contact.email = hunt.email
    contact.email_source_url = hunt.email_source_url
    if hunt.phone and not contact.phone:
        contact.phone = hunt.phone
    contact.contact_method = "email_and_phone" if contact.phone else "email"


def run_pipeline(cfg: RunConfig, known_registry: list) -> dict:
    runner = ClaudeRunner(model=cfg.model)

    log.info("Discover: searching for %r in %s", cfg.org_type, cfg.area)
    candidates = discover(runner, cfg)
    log.info("Discover: %d candidates found", len(candidates))

    verdicts = verify(runner, cfg, candidates, known_registry)
    by_name = {c.org_name: c for c in candidates}
    to_research = [
        v for v in verdicts
        if v.decision == "new_org_confirmed" and v.genuinely_matches_org_type
    ]
    log.info(
        "Verify: %d new to research, %d already known, %d wrong-area, %d wrong-type",
        len(to_research),
        sum(v.decision.startswith("already_known") for v in verdicts),
        sum(v.decision == "false_positive_wrong_area" for v in verdicts),
        sum(v.decision == "new_org_confirmed" and not v.genuinely_matches_org_type for v in verdicts),
    )

    def safe_research(v):
        try:
            return research_org(runner, cfg, v, by_name.get(v.org_name))
        except RefusalError:
            log.warning("Research declined for %s — skipping", v.org_name)
            return None

    with ThreadPoolExecutor(max_workers=cfg.workers) as pool:
        orgs = [o for o in pool.map(safe_research, to_research) if o]
    log.info("Research: %d orgs researched", len(orgs))

    contact_work = [(org, person) for org in orgs for person in org.key_people]

    def safe_contact(work):
        org, person = work
        try:
            return find_contact(runner, cfg, org, person)
        except RefusalError:
            log.warning("Contact lookup declined for %s — skipping", person.name)
            return None

    with ThreadPoolExecutor(max_workers=cfg.workers) as pool:
        contacts = [c for c in pool.map(safe_contact, contact_work) if c]
    log.info("Contacts: %d contacts found", len(contacts))

    if cfg.deep_email_hunt:
        needy = [c for c in contacts if not c.email]
        log.info("Email hunt: %d contacts lack a published email, deep-searching", len(needy))

        def safe_hunt(contact):
            try:
                return contact, hunt_email(runner, contact)
            except RefusalError:
                log.warning("Email hunt declined for %s — skipping", contact.name)
                return contact, None

        with ThreadPoolExecutor(max_workers=cfg.workers) as pool:
            for contact, hunt in pool.map(safe_hunt, needy):
                if hunt:
                    _apply_email_hunt(contact, hunt)
        found = sum(1 for c in needy if c.email)
        log.info("Email hunt: %d/%d published emails found", found, len(needy))

    return {"candidates": candidates, "verdicts": verdicts, "orgs": orgs, "contacts": contacts}
