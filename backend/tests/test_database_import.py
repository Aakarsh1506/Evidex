"""A database export becomes reviewable records; its statements are never executed."""

import json
import sqlite3

import pytest

from backend.errors import APIError
from backend.services.database_import import import_database

DUMP = """--
-- PostgreSQL database dump
--
INSERT INTO persons (person_id, name, alias, dob, age, city, state, record_status)
  VALUES ('P001', 'Rohan Mehta', 'Ronny', '1997-04-02', 29, 'Nandipur', 'Maharashtra', 'Active'),
         ('P002', 'Kavita Rao', NULL, NULL, 27, 'Nandipur', 'Maharashtra', 'Active');
INSERT INTO crime_types (crime_id, crime_name) VALUES (7, 'Theft');
INSERT INTO locations (location_id, city, state) VALUES (3, 'Nandipur', 'Maharashtra');
INSERT INTO vehicles (vehicle_id, registration) VALUES (5, 'MH12AB4521');
INSERT INTO cases (case_id, crime_id, location_id, case_status) VALUES ('FIR-1', 7, 3, 'Open');
COPY case_people (case_id, person_id, role) FROM stdin;
FIR-1\tP001\tsuspect
FIR-1\tP002\twitness
\\.
"""


def by_kind(extraction):
    return {(entity.kind, entity.name) for entity in extraction.entities}


def links(extraction):
    names = {entity.ref: entity.name for entity in extraction.entities}
    return {(names[r.subject], r.predicate, names[r.object]) for r in extraction.relationships}


def test_sql_dump_rows_become_entities_and_key_columns_become_links():
    text, extraction = import_database(DUMP.encode(), ".sql")
    assert by_kind(extraction) == {
        ("Person", "Rohan Mehta"), ("Person", "Kavita Rao"), ("CrimeType", "Theft"),
        ("Location", "Nandipur"), ("Vehicle", "MH12AB4521"), ("Case", "FIR-1")}
    assert links(extraction) == {
        ("Rohan Mehta", "SUSPECT_IN", "FIR-1"), ("Kavita Rao", "WITNESS_IN", "FIR-1"),
        ("FIR-1", "OF_TYPE", "Theft"), ("FIR-1", "OCCURRED_AT", "Nandipur")}
    rohan = next(e for e in extraction.entities if e.name == "Rohan Mehta")
    assert {a.key: a.value for a in rohan.attributes} == {
        "alias": "Ronny", "dob": "1997-04-02", "age": "29", "city": "Nandipur",
        "state": "Maharashtra", "record_status": "Active"}
    assert rohan.identifier == "P001"
    # Every record cites the row it came from, exactly as the source text holds it.
    for entity in extraction.entities:
        assert entity.evidence in text
    for relation in extraction.relationships:
        assert relation.evidence in text


def test_sqlite_export_is_read_as_data(tmp_path):
    path = tmp_path / "export.sqlite"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE suspects (id INTEGER, name TEXT, city TEXT, phone TEXT)")
        connection.execute("INSERT INTO suspects VALUES (1, 'Sameer Qureshi', 'Thane', '9876501234')")
    _text, extraction = import_database(path.read_bytes(), ".sqlite")
    person = next(e for e in extraction.entities if e.kind == "Person")
    assert person.name == "Sameer Qureshi"
    assert {a.key: a.value for a in person.attributes} == {"city": "Thane", "phone": "9876501234"}


@pytest.mark.parametrize("payload,suffix,stem", [
    (b"name,city,age\nPriya Nair,Nandipur,31\n", ".csv", "witnesses"),
    (json.dumps({"witnesses": [{"name": "Priya Nair", "city": "Nandipur", "age": 31}]}).encode(), ".json", "export"),
    (json.dumps([{"name": "Priya Nair", "city": "Nandipur", "age": 31}]).encode(), ".json", "witnesses"),
])
def test_csv_and_json_exports(payload, suffix, stem):
    _text, extraction = import_database(payload, suffix, stem)
    assert by_kind(extraction) == {("Person", "Priya Nair")}


def test_dangerous_statements_are_data_not_commands():
    dump = ("DROP TABLE persons;\nDELETE FROM officers;\n"
            "INSERT INTO persons (person_id, name) VALUES ('P9', 'Alice');\n"
            "GRANT ALL ON persons TO attacker;\n")
    text, extraction = import_database(dump.encode(), ".sql")
    # Only the row is read. Nothing else is executed, kept, or turned into a record.
    assert by_kind(extraction) == {("Person", "Alice")}
    assert text == "persons: person_id=P9 | name=Alice"


def test_custom_format_dump_explains_how_to_export_plain_sql():
    with pytest.raises(APIError, match="plain SQL"):
        import_database(b"PGDMP\x00binary", ".dump")


@pytest.mark.parametrize("payload,suffix,message", [
    (b"", ".sql", "No table rows"),
    (b"\xff\xfe\x00bad", ".sql", "UTF-8"),
    (b"{not json}", ".json", "could not be read"),
    (b"not a database", ".sqlite", "SQLite"),
])
def test_unreadable_exports_are_rejected(payload, suffix, message):
    with pytest.raises(APIError, match=message):
        import_database(payload, suffix)


def test_oversized_export_is_rejected():
    rows = "".join(f"INSERT INTO persons (person_id, name) VALUES ('P{n}', 'Person {n}');\n" for n in range(250))
    with pytest.raises(APIError, match="smaller selection"):
        import_database(rows.encode(), ".sql")


def test_sample_export_in_docs_imports_cleanly():
    """The file offered to users must keep working: docs/sample_database_export.sql."""
    from pathlib import Path

    sample = Path(__file__).resolve().parents[2] / "docs" / "sample_database_export.sql"
    text, extraction = import_database(sample.read_bytes(), ".sql", sample.stem)
    assert len(extraction.entities) == 15 and not extraction.excluded_relationships
    assert links(extraction) >= {
        ("Rohan Mehta", "SUSPECT_IN", "FIR-SYN-2026-0142"),
        ("Kavita Rao", "WITNESS_IN", "FIR-SYN-2026-0142"),
        ("Arjun Deshmukh", "MENTIONED_IN", "FIR-SYN-2026-0142"),
        ("FIR-SYN-2026-0198", "OF_TYPE", "Financial fraud"),
        ("FIR-SYN-2026-0198", "OCCURRED_AT", "Vashi"),
    }
    assert all(entity.evidence in text for entity in extraction.entities)


def test_fifty_criminal_sample_imports_cleanly():
    """docs/sample_50_criminals.sql is offered to users; keep it importable."""
    from collections import Counter
    from pathlib import Path

    sample = Path(__file__).resolve().parents[2] / "docs" / "sample_50_criminals.sql"
    text, extraction = import_database(sample.read_bytes(), ".sql", sample.stem)
    kinds = Counter(entity.kind for entity in extraction.entities)
    assert kinds["Person"] == 50 and kinds["Case"] == 18
    assert not extraction.excluded_relationships
    predicates = Counter(relation.predicate for relation in extraction.relationships)
    assert predicates["SUSPECT_IN"] and predicates["WITNESS_IN"] and predicates["OF_TYPE"]
    assert all(entity.evidence in text for entity in extraction.entities)
    # Crime types arrive in the sentence case the database now uses.
    assert sorted(e.name for e in extraction.entities if e.kind == "CrimeType") == [
        "Burglary", "Cheating", "Extortion", "Financial fraud", "Forgery", "Theft"]


def test_insert_without_column_names_uses_the_create_table_columns():
    """pg_dump --inserts omits the column list; the schema in the same file supplies it."""
    dump = ("CREATE TABLE public.persons (\n"
            "    person_id character varying(20) NOT NULL,\n"
            "    name character varying(100) NOT NULL,\n"
            "    alias character varying(100),\n"
            "    dob date,\n"
            "    age integer,\n"
            "    city character varying(100),\n"
            "    CONSTRAINT persons_pkey PRIMARY KEY (person_id)\n"
            ");\n"
            "CREATE TABLE public.case_people (case_id varchar(20), person_id varchar(20), role text);\n"
            "INSERT INTO public.persons VALUES ('P001', 'Rohan Mehta', 'Ronny', '1997-04-02', 29, 'Nandipur');\n"
            "COPY public.case_people FROM stdin;\n"
            "FIR-1\tP001\tsuspect\n\\.\n")
    _text, extraction = import_database(dump.encode(), ".sql")
    person = next(e for e in extraction.entities if e.kind == "Person")
    assert person.name == "Rohan Mehta" and person.identifier == "P001"
    assert {a.key: a.value for a in person.attributes} == {
        "alias": "Ronny", "dob": "1997-04-02", "age": "29", "city": "Nandipur"}


def test_export_without_any_column_names_explains_how_to_re_export():
    dump = "INSERT INTO persons VALUES ('P001', 'Rohan Mehta', 29);\n"
    with pytest.raises(APIError, match="column-inserts"):
        import_database(dump.encode(), ".sql")


def test_other_schema_names_columns_and_keys_are_followed():
    """docs/sample_cybercrime_export.sql: different table/column names, backticks, COPY via schema."""
    from collections import Counter
    from pathlib import Path

    sample = Path(__file__).resolve().parents[2] / "docs" / "sample_cybercrime_export.sql"
    text, extraction = import_database(sample.read_bytes(), ".sql", sample.stem)
    kinds = Counter(entity.kind for entity in extraction.entities)
    # "firms" is an organization table, not an FIR table.
    assert kinds == {"Person": 5, "Case": 3, "CrimeType": 3, "Location": 3, "Organization": 2}
    assert not extraction.excluded_relationships
    farhan = next(e for e in extraction.entities if e.name == "Farhan Ali")
    assert farhan.identifier == "CY-01"  # The record ID, never the phone number.
    assert {a.key: a.value for a in farhan.attributes} == {
        "alias": "Fizz", "dob": "1994-03-11", "age": "32", "city": "Bengaluru",
        "state": "Karnataka", "phone": "9845012345"}
    assert links(extraction) >= {
        ("Farhan Ali", "SUSPECT_IN", "FIR-CY-2026-071"),
        ("Suresh Gowda", "WITNESS_IN", "FIR-CY-2026-071"),
        # offence_id and place_id are followed by what they point at, not by their names.
        ("FIR-CY-2026-099", "OF_TYPE", "Money laundering"),
        ("FIR-CY-2026-084", "OCCURRED_AT", "Whitefield")}
    assert all(entity.evidence in text for entity in extraction.entities)


def test_shared_key_values_do_not_create_wrong_links():
    """crime 3 and location 3 are different records; an ambiguous key links to neither."""
    dump = ("INSERT INTO crime_types (crime_id, crime_name) VALUES (3, 'Theft');\n"
            "INSERT INTO locations (location_id, city) VALUES (3, 'Nandipur');\n"
            "INSERT INTO cases (case_id, crime_id, location_id) VALUES ('FIR-9', 3, 3);\n")
    _text, extraction = import_database(dump.encode(), ".sql")
    assert links(extraction) == {("FIR-9", "OF_TYPE", "Theft"), ("FIR-9", "OCCURRED_AT", "Nandipur")}
