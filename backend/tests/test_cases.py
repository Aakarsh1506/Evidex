"""Cases are the primary record: list/search, case file assembly and the AI case summary."""

import json
from dataclasses import replace
from datetime import date

import httpx
import pytest

from backend.services.case_summary import CATEGORIES, collect_facts, generate_case_summary
from backend.services.cases import load_case, map_case, matches
from backend.services.network import CASE_NETWORK_QUERY


def with_ai(settings):
    """Summary generation needs a configured provider."""
    return replace(settings, groq_api_key="test-api-key")

CASE_ROW = {
    "case_id": "FIR-2026-0142",
    "reference": "FIR/142/2026",
    "title": "Harbour Road theft",
    "case_status": "Under investigation",
    "case_month": date(2026, 6, 1),
    "opened_on": date(2026, 6, 4),
    "crime_name": "Theft",
    "city": "Nandipur",
    "state": "Maharashtra",
    "has_summary": False,
    "summary_generated_at": None,
    "person_ids": ["P001", "P002", None],
    "document_count": 2,
}
PERSON_ROW = {
    "person_id": "P001",
    "name": "Rohan Mehta",
    "alias": "Ronny",
    "dob": date(1997, 4, 2),
    "age": 29,
    "height_cm": 175,
    "city": "Nandipur",
    "state": "Maharashtra",
    "family_known": None,
    "record_status": "Extracted (unverified)",
    "last_seen": None,
    "roles": ["suspect", None],
}


def test_map_case_counts_people_and_prefers_the_source_reference():
    case = map_case(CASE_ROW)
    assert case["id"] == "FIR-2026-0142"
    # The FIR number as written in the document wins over the internal id.
    assert case["reference"] == "FIR/142/2026"
    assert case["month"] == "2026-06-01" and case["openedOn"] == "2026-06-04"
    # A NULL from the left join must not inflate the participant count.
    assert case["peopleCount"] == 2
    assert case["documentCount"] == 2
    assert case["crimeTags"] == ["Theft"]
    assert case["hasSummary"] is False


def test_map_case_without_a_reference_falls_back_to_the_case_id():
    case = map_case({**CASE_ROW, "reference": None, "crime_name": None, "person_ids": []})
    assert case["reference"] == "FIR-2026-0142"
    assert case["crimeTags"] == [] and case["peopleCount"] == 0


@pytest.mark.parametrize(
    "query,tags,expected",
    [
        ("fir/142", [], True),
        ("harbour", [], True),          # title
        ("theft", [], True),            # crime category
        ("nandipur", [], True),         # city
        ("maharashtra", [], True),      # state
        ("fir-2026-0142", [], True),    # internal id still findable
        ("bengaluru", [], False),
        ("", ["theft"], True),
        ("", ["fraud"], False),
        ("nomatch", ["fraud"], False),
        # OR semantics: a matching tag is enough even when the text does not match.
        ("nomatch", ["theft"], True),
    ],
)
def test_search_matches_reference_title_category_and_place(query, tags, expected):
    assert matches(map_case(CASE_ROW), query, tags) is expected


def test_search_ignores_a_missing_title_without_raising():
    assert matches(map_case({**CASE_ROW, "title": None}), "harbour", []) is False


async def test_load_case_folds_in_people_documents_and_overlaps(db):
    async def query(sql, params=()):
        if "FROM cases c" in sql and "case_documents doc" in sql:
            return [CASE_ROW]
        if "FROM case_people cp" in sql:
            return [PERSON_ROW]
        if "FROM case_documents" in sql:
            return [{"document_id": 3, "original_name": "fir.pdf", "mime_type": "application/pdf",
                     "source_type": "fir", "uploaded_at": None, "confirmed_at": None}]
        if "JOIN case_people theirs" in sql:
            return [{"case_id": "FIR-2026-0198", "reference": "FIR/198/2026", "title": None,
                     "case_status": "Under investigation", "crime_name": "Financial fraud",
                     "city": "Vashi", "state": "Maharashtra", "shared_people": ["Rohan Mehta"]}]
        return [{"summary": None}]

    db.query.side_effect = query
    case = await load_case("FIR-2026-0142", db, officer_id=7)
    # The person's own details are on the case now; there is no separate profile page.
    assert [p["name"] for p in case["people"]] == ["Rohan Mehta"]
    assert case["people"][0]["roles"] == ["suspect"]
    assert case["people"][0]["age"] == 29 and case["people"][0]["dob"] == "1997-04-02"
    # mimeType travels with the document so the viewer knows how to render the original.
    assert case["documents"] == [{"id": 3, "name": "fir.pdf", "mimeType": "application/pdf",
                                 "sourceType": "fir", "uploadedAt": None, "confirmedAt": None}]
    assert case["relatedCases"][0]["sharedPeople"] == ["Rohan Mehta"]
    assert case["summary"] is None


async def test_load_case_returns_none_for_an_unknown_case(db):
    db.query.return_value = []
    assert await load_case("nope", db, officer_id=7) is None


def test_case_network_is_rooted_at_the_case_node():
    assert "(root:Case {case_id: $id})" in CASE_NETWORK_QUERY
    assert "Person" not in CASE_NETWORK_QUERY


# --- AI case summary ---------------------------------------------------------

def sample_case():
    return {
        "id": "FIR-2026-0142", "reference": "FIR/142/2026", "title": "Harbour Road theft",
        "crime": "Theft", "status": "Under investigation", "month": "2026-06-01",
        "openedOn": "2026-06-04", "location": {"city": "Nandipur", "state": "Maharashtra"},
        "people": [{"id": "P001", "name": "Rohan Mehta", "roles": ["suspect"], "alias": "Ronny",
                    "age": 29, "dob": "1997-04-02", "recordStatus": "Extracted (unverified)",
                    "location": {"city": "Nandipur"}}],
        "documents": [{"id": 3, "name": "fir.pdf"}],
        "relatedCases": [{"id": "FIR-2026-0198", "reference": "FIR/198/2026",
                          "crime": "Financial fraud", "sharedPeople": ["Rohan Mehta"]}],
        "crimeTags": ["Theft"],
    }


def test_collect_facts_records_roles_and_uses_only_case_categories():
    facts = collect_facts(sample_case())
    assert {fact["category"] for fact in facts} <= set(CATEGORIES)
    person = next(fact for fact in facts if fact["id"] == "person-P001")
    # The recorded role must travel with the person: a witness is not a suspect.
    assert "recorded role(s): suspect" in person["text"]
    assert person["category"] == "people"
    assert any(fact["id"] == "case-status" and fact["category"] == "status" for fact in facts)
    assert any(fact["id"] == "case-location" and "Nandipur, Maharashtra" in fact["text"]
               for fact in facts)
    assert all(fact["source"] == "case" for fact in facts)


async def test_generate_case_summary_keeps_only_cited_sections(db, settings, monkeypatch):
    monkeypatch.setattr("backend.services.case_summary.retrieve_context",
                        AsyncReturn([]))
    body = {"sections": [
        {"category": "overview", "items": [{"text": "Theft reported at Harbour Road.",
                                            "sources": ["case"]}]},
        # An item citing a source that was never supplied is dropped, not trusted.
        {"category": "evidence", "items": [{"text": "Invented seizure.", "sources": ["chunk-99"]}]},
        # An unknown category is dropped too.
        {"category": "recommendations", "items": [{"text": "Arrest him.", "sources": ["case"]}]},
    ]}
    client = FakeProvider(body)
    summary = await generate_case_summary(sample_case(), db, client, with_ai(settings), officer_id=7)
    assert [section["category"] for section in summary["sections"]] == ["overview"]
    assert summary["retrievalMode"] == "stored_records"
    assert summary["coverage"]["documents"] == 1
    assert {source["id"] for source in summary["sources"]} == {"case"}


async def test_generate_case_summary_refuses_a_case_with_nothing_confirmed(db, settings):
    from backend.errors import APIError

    empty = {**sample_case(), "people": [], "documents": []}
    with pytest.raises(APIError) as caught:
        await generate_case_summary(empty, db, FakeProvider({}), with_ai(settings), officer_id=7)
    assert caught.value.status == 400


async def test_summary_route_stores_the_generated_payload(officer_client, db, monkeypatch):
    stored = {}

    async def query(sql, params=()):
        if sql.strip().startswith("UPDATE cases SET summary"):
            stored["payload"] = json.loads(params[0])
            stored["language"] = params[1]
            stored["officer_id"] = params[2]
            return []
        if "summary_generated_at, summary_generated_by" in sql:
            return [{"summary": stored.get("payload"), "summary_language": "en",
                     "summary_generated_at": None, "summary_generated_by": 7,
                     "officer_name": "Test Officer"}]
        if "FROM cases c" in sql and "case_documents doc" in sql:
            return [CASE_ROW]
        if "FROM case_people cp" in sql:
            return [PERSON_ROW]
        if "FROM case_documents" in sql:
            return [{"document_id": 3, "original_name": "fir.pdf", "mime_type": "application/pdf",
                     "source_type": "fir", "uploaded_at": None, "confirmed_at": None}]
        return []

    db.query.side_effect = query
    monkeypatch.setattr(
        "backend.routes.cases.generate_case_summary",
        AsyncReturn({"sections": [{"category": "overview",
                                   "items": [{"text": "Ok", "sources": ["case"]}]}],
                     "sources": [{"id": "case", "label": "Case record FIR/142/2026"}],
                     "coverage": {}, "retrievalMode": "stored_records"}),
    )
    response = await officer_client.post("/api/cases/FIR-2026-0142/summary", json={})
    assert response.status_code == 200
    assert response.json()["generatedBy"] == "Test Officer"
    assert stored["language"] == "en" and stored["officer_id"] == 7
    assert stored["payload"]["sections"][0]["category"] == "overview"


async def test_summary_route_rejects_an_unsupported_language(officer_client):
    response = await officer_client.post("/api/cases/FIR-2026-0142/summary", json={"language": "fr"})
    assert response.status_code == 400


class AsyncReturn:
    """Minimal awaitable stub: returns the same value for any call."""

    def __init__(self, value):
        self.value = value

    async def __call__(self, *args, **kwargs):
        return self.value


class FakeProvider:
    def __init__(self, body):
        self.body = body

    async def post(self, *args, **kwargs):
        return httpx.Response(200, json={"choices": [
            {"message": {"content": json.dumps(self.body)}, "finish_reason": "stop"}
        ]})
