"""Case records: the primary browsable entity. People fold in as case participants."""

import asyncio
import logging

from ..utils.avatar import color_for_id, initials_avatar
from ..utils.map_coordinates import coordinates_for_city
from .criminals import date_string

logger = logging.getLogger(__name__)

# The source identifier (the FIR number as written in the document) is shown in place of the
# internal case_id whenever the confirmed extraction recorded one.
CASES_SQL = """
  SELECT c.case_id,
         COALESCE((SELECT e.properties->>'source_identifier' FROM extracted_entities e
          WHERE e.kind='Case' AND e.canonical_id=c.case_id
            AND e.properties->>'source_identifier' IS NOT NULL
          ORDER BY e.entity_id LIMIT 1), c.case_id) AS reference,
         c.title, c.case_status, c.case_month, c.opened_on,
         ct.crime_name, l.city, l.state,
         (c.summary IS NOT NULL) AS has_summary,
         c.summary_generated_at,
         array_remove(array_agg(DISTINCT cp.person_id), NULL) AS person_ids,
         count(DISTINCT doc.document_id)::int AS document_count
  FROM cases c
  LEFT JOIN crime_types ct ON ct.crime_id = c.crime_id
  LEFT JOIN locations l ON l.location_id = c.location_id
  LEFT JOIN case_people cp ON cp.case_id = c.case_id
  LEFT JOIN case_documents doc ON doc.case_id = c.case_id
  {where_clause}
  GROUP BY c.case_id, c.title, c.case_status, c.case_month, c.opened_on,
           ct.crime_name, l.city, l.state, c.summary, c.summary_generated_at
  ORDER BY c.case_month DESC NULLS LAST, c.case_id
"""

# Every person on the case, with the role the source recorded. A person may hold
# several roles on one case, so roles are aggregated rather than picked.
CASE_PEOPLE_SQL = """
  SELECT p.person_id, p.name, p.alias, p.dob, p.age, p.height_cm, p.city, p.state,
         p.family_known, p.record_status, p.last_seen,
         array_remove(array_agg(DISTINCT cp.role), NULL) AS roles
  FROM case_people cp
  JOIN persons p ON p.person_id = cp.person_id
  WHERE cp.case_id = %s
  GROUP BY p.person_id
  ORDER BY p.name
"""

# Documents stay officer-scoped, as everywhere else in the app: a case record is shared,
# but one officer's uploads are not readable through another officer's session.
CASE_DOCUMENTS_SQL = """
  SELECT document_id, original_name, mime_type, source_type, uploaded_at, confirmed_at
  FROM case_documents WHERE case_id = %s AND officer_id = %s
  ORDER BY uploaded_at DESC, document_id
"""

# Other cases reachable through a shared participant: the case-level equivalent of
# the person-level associate lookup. A shared person is an overlap, not a conclusion.
RELATED_CASES_SQL = """
  SELECT other.case_id,
         COALESCE((SELECT e.properties->>'source_identifier' FROM extracted_entities e
          WHERE e.kind='Case' AND e.canonical_id=other.case_id
            AND e.properties->>'source_identifier' IS NOT NULL
          ORDER BY e.entity_id LIMIT 1), other.case_id) AS reference,
         other.title, other.case_status, ct.crime_name, l.city, l.state,
         array_remove(array_agg(DISTINCT shared.name), NULL) AS shared_people
  FROM case_people mine
  JOIN case_people theirs ON theirs.person_id = mine.person_id AND theirs.case_id <> mine.case_id
  JOIN persons shared ON shared.person_id = mine.person_id
  JOIN cases other ON other.case_id = theirs.case_id
  LEFT JOIN crime_types ct ON ct.crime_id = other.crime_id
  LEFT JOIN locations l ON l.location_id = other.location_id
  WHERE mine.case_id = %s
  GROUP BY other.case_id, other.title, other.case_status, ct.crime_name, l.city, l.state
  ORDER BY other.case_id
  LIMIT 25
"""


def map_person(row):
    """A case participant. Same fields the person profile showed, now shown on the case."""
    city = row.get("city")
    return {
        "id": row["person_id"],
        "name": row["name"],
        "alias": row.get("alias"),
        "roles": [role for role in (row.get("roles") or []) if role],
        "dob": date_string(row.get("dob")),
        "age": row.get("age"),
        "heightCm": row.get("height_cm"),
        "location": {"city": city, "state": row.get("state"), **coordinates_for_city(city)},
        "lastSeenDate": date_string(row.get("last_seen")),
        "familyKnown": row.get("family_known"),
        "recordStatus": row.get("record_status"),
        "photo": initials_avatar(row["name"], color_for_id(row["person_id"])),
    }


def map_case(row):
    """Convert a case row into the shape the frontend case list and case file consume."""
    city = row.get("city")
    return {
        "id": row["case_id"],
        "reference": row.get("reference") or row["case_id"],
        "title": row.get("title"),
        "crime": row.get("crime_name"),
        "status": row.get("case_status"),
        "month": date_string(row.get("case_month")),
        "openedOn": date_string(row.get("opened_on")),
        "location": {"city": city, "state": row.get("state"), **coordinates_for_city(city)},
        "peopleCount": len([pid for pid in (row.get("person_ids") or []) if pid]),
        "documentCount": row.get("document_count") or 0,
        "hasSummary": bool(row.get("has_summary")),
        "summaryGeneratedAt": row.get("summary_generated_at"),
        # Crime type doubles as the case's category tag, so one case carries one tag.
        "crimeTags": [row["crime_name"]] if row.get("crime_name") else [],
    }


async def list_cases(db):
    rows = await db.query(CASES_SQL.format(where_clause=""))
    return [map_case(row) for row in rows]


def matches(case, query, wanted_tags):
    """Search a case by reference, title, crime category or city. OR semantics, as before."""
    if query:
        haystack = " ".join(
            str(value).lower()
            for value in (case["reference"], case["id"], case["title"], case["crime"],
                          case["location"].get("city"), case["location"].get("state"))
            if value
        )
        if query in haystack:
            return True
    return bool(wanted_tags) and any(tag.lower() in wanted_tags for tag in case["crimeTags"])


async def load_case(case_id, db, officer_id):
    rows = await db.query(CASES_SQL.format(where_clause="WHERE c.case_id = %s"), (case_id,))
    if not rows:
        return None
    case = map_case(rows[0])
    # Participants, source documents and case overlaps load independently.
    people, documents, related = await asyncio.gather(
        db.query(CASE_PEOPLE_SQL, (case_id,)),
        db.query(CASE_DOCUMENTS_SQL, (case_id, officer_id)),
        db.query(RELATED_CASES_SQL, (case_id,)),
    )
    case["people"] = [map_person(row) for row in people]
    case["documents"] = [
        {
            "id": row["document_id"],
            "name": row["original_name"],
            "mimeType": row.get("mime_type"),
            "sourceType": row.get("source_type"),
            "uploadedAt": row.get("uploaded_at"),
            "confirmedAt": row.get("confirmed_at"),
        }
        for row in documents
    ]
    case["relatedCases"] = [
        {
            "id": row["case_id"],
            "reference": row.get("reference") or row["case_id"],
            "title": row.get("title"),
            "crime": row.get("crime_name"),
            "status": row.get("case_status"),
            "location": ", ".join(filter(None, (row.get("city"), row.get("state")))) or None,
            "sharedPeople": [name for name in (row.get("shared_people") or []) if name],
        }
        for row in related
    ]
    case["summary"] = await load_summary(case_id, db)
    return case


async def load_summary(case_id, db):
    rows = await db.query(
        """SELECT summary, summary_language, summary_generated_at, summary_generated_by,
                  o.name AS officer_name
           FROM cases c LEFT JOIN officers o ON o.officer_id = c.summary_generated_by
           WHERE c.case_id = %s""",
        (case_id,),
    )
    if not rows or not rows[0]["summary"]:
        return None
    row = rows[0]
    return {
        **row["summary"],
        "language": row.get("summary_language") or "en",
        "generatedAt": row.get("summary_generated_at"),
        "generatedBy": row.get("officer_name"),
    }
