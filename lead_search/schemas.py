"""Pydantic schemas for each pipeline stage's structured output."""

from typing import List, Optional

from pydantic import BaseModel


class Candidate(BaseModel):
    org_name: str
    likely_subtype: Optional[str] = None
    geographic_scope_guess: Optional[str] = None
    why_relevant: str
    evidence_url: Optional[str] = None


class DiscoveryResult(BaseModel):
    orgs: List[Candidate]


class Verdict(BaseModel):
    org_name: str
    closest_registry_match_org_id: str
    same_organization_as_match: bool
    decision: str  # already_known_same_scope | already_known_new_area | new_org_confirmed | false_positive_wrong_area
    matched_existing_org_id: Optional[str] = None
    is_multi_area: bool
    genuinely_matches_org_type: bool
    type_fit_reasoning: str
    reasoning: str


class VerificationResult(BaseModel):
    verdicts: List[Verdict]


class KeyPerson(BaseModel):
    name: str
    title: str
    relevance_reason: str


class OrgDetail(BaseModel):
    org_name: str
    org_type: str
    org_type_notes: Optional[str] = None
    geographic_scope: str  # neighborhood | town | multi-town | county | regional | statewide | national
    areas_served: List[str]
    website: str
    description: str
    source_urls: List[str]
    status: str  # researched | needs_review | no_website_found
    key_people: List[KeyPerson]


class Contact(BaseModel):
    name: str
    org_id_hint: str
    org_name: str
    title: str
    email: Optional[str] = None
    phone: Optional[str] = None
    contact_method: str  # email | phone | email_and_phone | linkedin_only | org_contact_form | none_found
    linkedin_url: Optional[str] = None
    linkedin_confidence: str  # confirmed | likely | not_found
    outreach_message: Optional[str] = None
