import csv
import tempfile
import unittest
from pathlib import Path

from lead_search.schemas import Contact, KeyPerson, OrgDetail
from lead_search.storage import (
    append_to_registry,
    build_rows,
    load_registry_snapshot,
    slugify,
)


def make_org(name="Medford Food Bank", people=None):
    return OrgDetail(
        org_name=name,
        org_type="food bank",
        geographic_scope="town",
        areas_served=["Medford, MA"],
        website="https://example.org",
        description="A food bank.",
        source_urls=["https://example.org/about"],
        status="researched",
        key_people=people or [],
    )


def make_contact(org_id, name="Jane Doe"):
    return Contact(
        name=name,
        org_id_hint=org_id,
        org_name="Medford Food Bank",
        title="Director",
        email="jane@example.org",
        contact_method="email",
        linkedin_confidence="likely",
    )


class TestSlugify(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(slugify("Medford Food Bank"), "medford-food-bank")

    def test_punctuation_and_case(self):
        self.assertEqual(slugify("LEAF Fund (Local Enterprise)"), "leaf-fund-local-enterprise")

    def test_truncates_to_60(self):
        self.assertLessEqual(len(slugify("x" * 200)), 60)


class TestBuildRows(unittest.TestCase):
    def test_org_without_contacts_gets_one_row(self):
        rows = build_rows([make_org()], [])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["org_id"], "medford-food-bank")
        self.assertEqual(rows[0]["contact_name"], "")

    def test_contacts_join_on_org_id_hint(self):
        person = KeyPerson(name="Jane Doe", title="Director", relevance_reason="runs programs")
        org = make_org(people=[person])
        contact = make_contact("medford-food-bank")
        rows = build_rows([org], [contact])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["contact_name"], "Jane Doe")
        self.assertEqual(rows[0]["relevance_reason"], "runs programs")
        self.assertEqual(rows[0]["email"], "jane@example.org")

    def test_contact_with_unmatched_hint_is_not_attached(self):
        rows = build_rows([make_org()], [make_contact("some-other-org")])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["contact_name"], "")


class TestRegistryRoundtrip(unittest.TestCase):
    def test_append_and_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.csv"
            person = KeyPerson(name="Jane Doe", title="Director", relevance_reason="r")
            rows = build_rows([make_org(people=[person])], [make_contact("medford-food-bank")])
            append_to_registry(path, rows)
            append_to_registry(path, rows)  # second append must not duplicate the header

            with path.open(newline="") as f:
                all_rows = list(csv.DictReader(f))
            self.assertEqual(len(all_rows), 2)

            snapshot = load_registry_snapshot(path)
            self.assertEqual(len(snapshot), 1)  # distinct orgs only
            self.assertEqual(snapshot[0]["org_id"], "medford-food-bank")
            self.assertEqual(snapshot[0]["areas_served"], "Medford, MA")

    def test_missing_registry_returns_empty(self):
        self.assertEqual(load_registry_snapshot(Path("/nonexistent/registry.csv")), [])


if __name__ == "__main__":
    unittest.main()
