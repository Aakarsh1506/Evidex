"""Run against an isolated database using CNA_TEST_PGHOST and CNA_TEST_PGPORT."""

import os
from dataclasses import replace

import pytest

from backend.db import Database
from backend.errors import APIError
from backend.services.extraction import Extraction
from backend.services.ingestion_store import persist_extraction

# Matches the supplied dump's columns and constraints; geometry is unused by ingestion.
BASE_SCHEMA = """
CREATE TABLE persons (person_id varchar(20) PRIMARY KEY, name varchar(100) NOT NULL,
 alias varchar(100), dob date, age integer, height_cm integer, state varchar(100),
 city varchar(100), last_seen date, family_known text, photo varchar(255),
 record_status varchar(100) NOT NULL);
CREATE TABLE crime_types (crime_id serial PRIMARY KEY, crime_name varchar(100) UNIQUE NOT NULL,
 description text);
CREATE TABLE locations (location_id serial PRIMARY KEY, city varchar(100) NOT NULL,
 state varchar(100) NOT NULL, latitude numeric(10,7), longitude numeric(10,7), geom text);
CREATE TABLE cases (case_id varchar(20) PRIMARY KEY, person_id varchar(20) NOT NULL REFERENCES persons,
 crime_id integer REFERENCES crime_types, case_month date, location_name varchar(150),
 case_status varchar(100), location_id integer REFERENCES locations);
"""


@pytest.fixture
async def real_db(settings):
    host = os.environ.get("CNA_TEST_PGHOST")
    if not host:
        pytest.skip("Set CNA_TEST_PGHOST to an isolated test database")
    from uuid import uuid4

    import psycopg
    from psycopg import sql

    database_name = "cna_test_" + uuid4().hex
    options = {
        "host": host,
        "port": int(os.environ["CNA_TEST_PGPORT"]),
        "user": os.environ.get("USER", "postgres"),
        "dbname": "postgres",
        "autocommit": True,
    }
    async with await psycopg.AsyncConnection.connect(**options) as conn:
        await conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))
    database = Database(
        replace(
            settings,
            pg_host=host,
            pg_port=options["port"],
            pg_user=options["user"],
            pg_database=database_name,
        )
    )
    await database.open()
    try:
        await database.query(BASE_SCHEMA)
        await database.ensure_schema()
        await database.ensure_schema()  # Startup migrations must be repeatable.
        await database.query(
            "INSERT INTO officers (officer_id,username,password_hash,name,org_name) VALUES (1,'tester','hash','Tester','Test')"
        )
        await database.query(
            "INSERT INTO persons (person_id,name,record_status) VALUES ('P001','Alice','Active')"
        )
        await database.query(
            "INSERT INTO crime_types (crime_id,crime_name) VALUES (1,'Robbery'),(10,'Fraud')"
        )
        yield database
    finally:
        await database.close()
        async with await psycopg.AsyncConnection.connect(**options) as conn:
            await conn.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database_name))
            )


def full_extraction():
    entities = [
        ("a", "Person", "Alice", "P001", []),
        ("b", "Person", "Bob", None, []),
        ("c", "Case", "FIR-2026-1", "FIR-2026-1", []),
        ("o", "Organization", "Acme", "ORG-10", []),
        ("v", "Vehicle", "AB123", "AB123", []),
        ("l", "Location", "Mumbai", None, []),
        ("t", "CrimeType", "Extortion", None, []),
        ("p", "PhoneNumber", "1234567890", "1234567890", []),
    ]
    relationships = [
        ("a", "WITNESS_IN", "c"),
        ("b", "SUSPECT_IN", "c"),
        ("o", "MENTIONED_IN", "c"),
        ("v", "MENTIONED_IN", "c"),
        ("c", "OCCURRED_AT", "l"),
        ("c", "OF_TYPE", "t"),
        ("a", "EMPLOYED_BY", "o"),
        ("o", "OWNS", "v"),
        ("a", "CONTACTED", "b"),
    ]
    return Extraction.model_validate(
        {
            "entities": [
                {"ref": r, "kind": k, "name": n, "identifier": i, "attributes": a, "evidence": n}
                for r, k, n, i, a in entities
            ],
            "relationships": [
                {"subject": s, "predicate": p, "object": o, "evidence": "source quote"}
                for s, p, o in relationships
            ],
        }
    )


async def add_document(db, confirmed=True):
    rows = await db.query("""INSERT INTO officer_documents
        (officer_id,original_name,stored_name,mime_type,size_bytes,source_type,processing_status)
        VALUES (1,'source.txt','source.txt','text/plain',5,'fir','processing') RETURNING document_id""")
    if confirmed:
        await db.query(
            "UPDATE officer_documents SET confirmed_at=now(), confirmed_by=1 WHERE document_id=%s",
            (rows[0]["document_id"],),
        )
    return rows[0]["document_id"]


async def test_persistence_maps_all_kinds_roles_and_repairs_sequence(real_db):
    doc_id = await add_document(real_db)
    result = full_extraction()
    payload = await persist_extraction(real_db, doc_id, result)
    assert len(payload["nodes"]) == 8 and len(payload["edges"]) == 9
    assert (await real_db.query("SELECT COUNT(*) AS n FROM persons"))[0]["n"] == 2
    assert (await real_db.query("SELECT record_status FROM persons WHERE person_id='P001'"))[0][
        "record_status"
    ] == "Active"
    case = (await real_db.query("SELECT * FROM cases"))[0]
    assert case["person_id"] is None  # The witness was not made the primary suspect.
    assert case["crime_id"] > 10  # Supplied dump has a stale sequence.
    assert case["location_id"] is not None
    roles = await real_db.query("SELECT role FROM case_people ORDER BY role")
    assert [row["role"] for row in roles] == ["SUSPECT_IN", "WITNESS_IN"]
    assert (await real_db.query("SELECT state FROM locations"))[0]["state"] is None
    assert payload == await persist_extraction(real_db, doc_id, result)
    assert (await real_db.query("SELECT COUNT(*) AS n FROM extracted_relationships"))[0]["n"] == 9
    second_doc = await add_document(real_db)
    await persist_extraction(real_db, second_doc, result)
    assert (await real_db.query("SELECT COUNT(*) AS n FROM cases"))[0]["n"] == 1
    assert (await real_db.query("SELECT COUNT(*) AS n FROM vehicles"))[0]["n"] == 1
    # Names alone do not merge people from different documents.
    assert (await real_db.query("SELECT COUNT(*) AS n FROM persons WHERE name='Bob'"))[0]["n"] == 2


@pytest.mark.parametrize("source", ["financial fraud", "FINANCIAL FRAUD"])
async def test_crime_type_is_saved_in_sentence_case(real_db, source):
    doc_id = await add_document(real_db)
    result = full_extraction()
    crime = next(e for e in result.entities if e.kind == "CrimeType")
    crime.name = crime.evidence = source
    payload = await persist_extraction(real_db, doc_id, result)
    rows = await real_db.query("SELECT crime_name FROM crime_types WHERE crime_id > 10")
    assert [row["crime_name"] for row in rows] == ["Financial fraud"]
    saved = await real_db.query("SELECT name, evidence FROM extracted_entities WHERE kind='CrimeType'")
    assert saved == [{"name": "Financial fraud", "evidence": source}]
    node = next(n for n in payload["nodes"] if n["kind"] == "CrimeType")
    assert node["properties"]["crime_name"] == "Financial fraud"
    assert crime.name == source  # The reviewed snapshot is not modified.

async def test_same_person_in_three_firs_is_offered_or_reused_not_silently_duplicated(real_db):
    from backend.services.entity_resolution import person_suggestions

    def fir(case, phone=None):
        attributes = [{"key": "phone", "value": phone}] if phone else []
        return Extraction.model_validate({"entities": [
            {"ref": "r", "kind": "Person", "name": "Rohan Mehta", "identifier": None,
             "attributes": attributes, "evidence": "Rohan Mehta"},
            {"ref": "c", "kind": "Case", "name": case, "identifier": case, "attributes": [],
             "evidence": case},
        ], "relationships": [{"subject": "r", "predicate": "SUSPECT_IN", "object": "c",
                              "evidence": "Rohan Mehta " + case}]})

    graph = type("Graph", (), {"run": staticmethod(lambda *args: _no_rows())})()
    first = await persist_extraction(real_db, await add_document(real_db), fir("FIR-1", "9876543210"))
    rohan = next(n["id"] for n in first["nodes"] if n["kind"] == "Person")
    # No phone: the officer is offered the existing person instead of a silent duplicate.
    second = fir("FIR-2")
    assert [s["personId"] for s in await person_suggestions(real_db, graph, second)] == [rohan]
    # The same recorded phone number identifies the same person automatically.
    third = await persist_extraction(real_db, await add_document(real_db), fir("FIR-3", "+91 98765 43210"))
    assert next(n["id"] for n in third["nodes"] if n["kind"] == "Person") == rohan
    rows = await real_db.query("SELECT person_id FROM persons WHERE name='Rohan Mehta'")
    assert [row["person_id"] for row in rows] == [rohan]


async def _no_rows():
    return []

async def test_any_backend_processes_a_file_stored_in_the_shared_database(real_db, settings, tmp_path):
    from backend.services.document_files import load_document_file
    from backend.services.document_text import extract_text_from_bytes

    doc_id = await add_document(real_db, confirmed=False)
    await real_db.query("INSERT INTO officer_document_files (document_id, content) VALUES (%s, %s)",
                        (doc_id, b"FIR/2026/1\r\nName: Rohan Mehta"))
    other_computer_uploads = tmp_path / "empty-uploads"  # This backend never saw the upload.
    other_computer_uploads.mkdir()
    doc = (await real_db.query("SELECT * FROM officer_documents WHERE document_id=%s", (doc_id,)))[0]
    content = await load_document_file(real_db, other_computer_uploads, doc)
    assert extract_text_from_bytes(content, ".txt") == "FIR/2026/1\nName: Rohan Mehta"
    await real_db.query("DELETE FROM officer_documents WHERE document_id=%s", (doc_id,))
    assert await real_db.query("SELECT 1 FROM officer_document_files WHERE document_id=%s", (doc_id,)) == []

async def test_sql_failure_rolls_back_entities_and_outbox(real_db):
    doc_id = await add_document(real_db)
    result = full_extraction()
    result.entities[1].attributes = []
    # The second named record deliberately conflicts with an existing explicit ID.
    result.entities[1].identifier = "P001"
    with pytest.raises(APIError, match="conflicts"):
        await persist_extraction(real_db, doc_id, result)
    assert (await real_db.query("SELECT COUNT(*) AS n FROM extracted_entities"))[0]["n"] == 0
    assert (await real_db.query("SELECT graph_payload FROM officer_documents"))[0][
        "graph_payload"
    ] is None


async def test_uploaded_text_flows_through_ai_sql_and_graph(real_db, settings, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock

    import httpx

    from backend.services import ingestion
    from backend.services.criminals import load_profile
    from backend.services.extraction import validate_extraction

    source = "Alice (P001) witnessed case C100."
    result = Extraction.model_validate(
        {
            "entities": [
                {
                    "ref": "p",
                    "kind": "Person",
                    "name": "Alice",
                    "identifier": "P001",
                    "attributes": [],
                    "evidence": "Alice (P001)",
                },
                {
                    "ref": "c",
                    "kind": "Case",
                    "name": "C100",
                    "identifier": "C100",
                    "attributes": [],
                    "evidence": "case C100",
                },
            ],
            "relationships": [
                {"subject": "p", "predicate": "WITNESS_IN", "object": "c", "evidence": source}
            ],
        }
    )
    validate_extraction(result, source)
    doc_id = await add_document(real_db)
    settings.upload_dir.mkdir(parents=True)
    (settings.upload_dir / "source.txt").write_text(source)
    provider = AsyncMock()
    provider.post.return_value = httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": result.model_dump_json()}, "finish_reason": "stop"}]
        },
    )
    graph = SimpleNamespace(driver=MagicMock(), run=AsyncMock(return_value=[]))
    tx = AsyncMock()
    session = AsyncMock()

    async def write(callback):
        await callback(tx)

    session.execute_write.side_effect = write
    graph.driver.session.return_value.__aenter__.return_value = session
    state = SimpleNamespace(
        db=real_db,
        graph=graph,
        http_client=provider,
        settings=replace(settings, groq_api_key="fake"),
    )
    doc = (await real_db.query("SELECT * FROM officer_documents WHERE document_id=%s", (doc_id,)))[
        0
    ]
    await ingestion.process_document(state, doc)
    saved = (
        await real_db.query("SELECT * FROM officer_documents WHERE document_id=%s", (doc_id,))
    )[0]
    assert saved["processing_status"] == "complete"
    assert saved["extracted_text"] == source
    # A file saved in uploads/ before database storage is copied in for other backends.
    stored = await real_db.query("SELECT content FROM officer_document_files WHERE document_id=%s", (doc_id,))
    assert bytes(stored[0]["content"]) == source.encode()
    assert len(saved["extraction"]["entities"]) == 2
    assert "WITNESS_IN" in tx.run.call_args.args[0]
    profile = await load_profile("P001", real_db, graph)
    assert len(profile["criminal"]["cases"]) == 1
    assert len([call for call in provider.post.call_args_list if call.args[0].endswith("/chat/completions")]) == 1
    assert len([call for call in provider.post.call_args_list if call.args[0].endswith("/api/embed")]) == 1


async def test_review_gate_then_exact_confirmation(real_db, settings):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    import httpx
    from psycopg.types.json import Jsonb

    from backend.app import create_app
    from backend.security import sign_officer_token
    from backend.services.ingestion import process_document

    doc_id = await add_document(real_db, confirmed=False)
    result = full_extraction()
    await real_db.query(
        "UPDATE officer_documents SET extraction=%s, extracted_text='source' WHERE document_id=%s",
        (Jsonb(result.model_dump()), doc_id),
    )
    doc = (await real_db.query("SELECT * FROM officer_documents WHERE document_id=%s", (doc_id,)))[
        0
    ]
    state = SimpleNamespace(settings=settings, db=real_db, graph=AsyncMock())
    await process_document(state, doc)
    assert (await real_db.query("SELECT processing_status FROM officer_documents"))[0][
        "processing_status"
    ] == "awaiting_review"
    assert (await real_db.query("SELECT COUNT(*) AS n FROM extracted_entities"))[0]["n"] == 0
    assert (await real_db.query("SELECT COUNT(*) AS n FROM cases"))[0]["n"] == 0
    with pytest.raises(APIError, match="Review and confirm"):
        await persist_extraction(real_db, doc_id, result)
    app = create_app(settings, database=real_db, graph=state.graph, initialize_schema=False)
    profile = {
        "officerId": 1,
        "username": "tester",
        "name": "Tester",
        "orgName": "Test",
        "role": "officer",
    }
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            client.cookies.set(
                settings.cookie_name, sign_officer_token({**profile, "officerId": 2}, settings)
            )
            assert (
                await client.post(
                    f"/api/documents/{doc_id}/confirm", json={"extraction": result.model_dump()}
                )
            ).status_code == 409
            client.cookies.set(settings.cookie_name, sign_officer_token(profile, settings))
            changed = result.model_dump()
            changed["entities"][0]["name"] = "Changed"
            assert (
                await client.post(f"/api/documents/{doc_id}/confirm", json={"extraction": changed})
            ).status_code == 409
            response = await client.post(
                f"/api/documents/{doc_id}/confirm", json={"extraction": result.model_dump()}
            )
            assert response.status_code == 200 and response.json()["confirmedAt"]
            assert (
                await client.post(
                    f"/api/documents/{doc_id}/confirm", json={"extraction": result.model_dump()}
                )
            ).status_code == 409
    # Confirmation schedules the write; it does not race the queue by writing here.
    assert (await real_db.query("SELECT COUNT(*) AS n FROM extracted_entities"))[0]["n"] == 0
    payload = await persist_extraction(real_db, doc_id, result)
    assert len(payload["nodes"]) == 8


async def test_location_sentence_and_person_links_survive_saving(real_db):
    result = full_extraction()
    sentence = "Bob resides in Mumbai."
    location = next(e for e in result.entities if e.kind == "Location")
    location.evidence = sentence
    from backend.services.extraction import Relationship

    result.relationships.extend(
        [
            Relationship(
                subject="b", predicate="RESIDES_IN", object=location.ref, evidence=sentence
            ),
            Relationship(
                subject="a",
                predicate="SEEN_AT",
                object=location.ref,
                evidence="Alice was seen in Mumbai.",
            ),
        ]
    )
    payload = await persist_extraction(real_db, await add_document(real_db), result)
    assert {e["predicate"] for e in payload["edges"]} >= {"RESIDES_IN", "SEEN_AT"}
    assert all(row["city"] == "Mumbai" for row in await real_db.query("SELECT city FROM persons"))
    assert all(node["properties"]["city"] == "Mumbai" for node in payload["nodes"] if node["kind"] == "Person")
    assert (await real_db.query("SELECT evidence FROM extracted_entities WHERE kind='Location'"))[
        0
    ]["evidence"] == sentence
    await real_db.ensure_schema()
    rows = await real_db.query(
        "SELECT predicate, evidence FROM extracted_relationships WHERE predicate IN ('RESIDES_IN','SEEN_AT') ORDER BY predicate"
    )
    assert rows == [
        {"predicate": "RESIDES_IN", "evidence": sentence},
        {"predicate": "SEEN_AT", "evidence": "Alice was seen in Mumbai."},
    ]


async def test_rejected_relationships_never_enter_sql_or_graph_payload(real_db):
    from types import SimpleNamespace

    from backend.routes.documents import ConfirmBody, confirm_document

    result = full_extraction()
    original = result.model_dump()
    doc_id = await add_document(real_db, confirmed=False)
    from psycopg.types.json import Jsonb

    await real_db.query(
        "UPDATE officer_documents SET processing_status='awaiting_review', extraction=%s WHERE document_id=%s",
        (Jsonb(original), doc_id),
    )
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(db=real_db)))
    await confirm_document(
        doc_id,
        ConfirmBody(extraction=result, rejected_relationship_indices=[0, 1]),
        request,
        {"officerId": 1},
    )
    stored = (
        await real_db.query(
            "SELECT extraction FROM officer_documents WHERE document_id=%s", (doc_id,)
        )
    )[0]["extraction"]
    assert len(stored["excluded_relationships"]) == 2
    assert result.model_dump() == original
    payload = await persist_extraction(real_db, doc_id, Extraction.model_validate(stored))
    assert len(payload["edges"]) == len(result.relationships) - 2
    assert not any(e["predicate"] in {"WITNESS_IN", "SUSPECT_IN"} for e in payload["edges"])
    assert not await real_db.query(
        "SELECT * FROM extracted_relationships WHERE predicate IN ('WITNESS_IN','SUSPECT_IN')"
    )
    with pytest.raises(APIError, match="Draft changed"):
        await confirm_document(doc_id, ConfirmBody(extraction=result), request, {"officerId": 1})


@pytest.fixture
def removal_graph():
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock
    tx = AsyncMock()
    session = AsyncMock()

    async def write(callback):
        await callback(tx)

    session.execute_write.side_effect = write
    graph = SimpleNamespace(driver=MagicMock(), run=AsyncMock(return_value=[]), tx=tx)
    graph.driver.session.return_value.__aenter__.return_value = session
    return graph


async def test_document_removal_deletes_owned_records_and_graph_connections(real_db, removal_graph):
    from backend.services.document_removal import remove_document_records
    doc_id = await add_document(real_db)
    payload = await persist_extraction(real_db, doc_id, full_extraction())
    await real_db.query("UPDATE officer_documents SET processing_status='complete'")
    person_id = next(node['id'] for node in payload['nodes'] if node['kind'] == 'Person' and node['id'] != 'P001')
    await real_db.query("INSERT INTO officer_working_list (officer_id,person_id) VALUES (1,%s)", (person_id,))
    await real_db.query("INSERT INTO officer_pinned_criminal (officer_id,person_id) VALUES (1,%s)", (person_id,))
    await real_db.query("INSERT INTO document_chunks (document_id,chunk_text,source_start,source_end,search_vector) VALUES (%s,'test',0,4,to_tsvector('test'))", (doc_id,))
    assert await remove_document_records(real_db, removal_graph, doc_id, 1) == 'source.txt'
    for table in ('officer_documents','extracted_entities','extracted_relationships','cases','organizations','vehicles','locations','document_chunks','ingestion_owned_entities','officer_working_list','officer_pinned_criminal'):
        assert (await real_db.query(f'SELECT count(*) AS n FROM {table}'))[0]['n'] == 0, table
    assert [row['person_id'] for row in await real_db.query('SELECT person_id FROM persons')] == ['P001']
    assert len(await real_db.query('SELECT * FROM crime_types')) == 2  # Seed crimes remain.
    calls = removal_graph.tx.run.call_args_list
    assert 'r.document_id=$document' in calls[0].args[0]
    assert calls[0].kwargs['document'] == doc_id
    assert all('DETACH DELETE' not in call.args[0] for call in calls)
    assert any(person_id in call.kwargs.get('ids', []) for call in calls)
    assert all("n.source='document_extraction'" in call.args[0] for call in calls[1:])


async def test_removal_preserves_shared_entities_until_last_source(real_db, removal_graph):
    from backend.services.document_removal import remove_document_records
    first, second = await add_document(real_db), await add_document(real_db)
    result = full_extraction()
    result.entities[1].identifier = 'BOB-RECORD'
    await persist_extraction(real_db, first, result)
    await persist_extraction(real_db, second, result)
    await real_db.query("UPDATE officer_documents SET processing_status='complete'")
    await remove_document_records(real_db, removal_graph, first, 1)
    assert len(await real_db.query('SELECT * FROM persons')) == 2
    assert len(await real_db.query('SELECT * FROM cases')) == 1
    assert len(await real_db.query('SELECT * FROM extracted_relationships')) == 9
    await remove_document_records(real_db, removal_graph, second, 1)
    assert len(await real_db.query('SELECT * FROM persons')) == 1
    assert not await real_db.query('SELECT * FROM cases')
    assert not await real_db.query('SELECT * FROM locations')


async def test_neo4j_failure_rolls_back_removal_and_allows_retry(real_db, removal_graph):
    from backend.services.document_removal import remove_document_records
    doc_id = await add_document(real_db)
    await persist_extraction(real_db, doc_id, full_extraction())
    await real_db.query("UPDATE officer_documents SET processing_status='complete'")
    removal_graph.tx.run.side_effect = RuntimeError('Neo4j offline')
    with pytest.raises(APIError, match='document was retained'):
        await remove_document_records(real_db, removal_graph, doc_id, 1)
    assert len(await real_db.query('SELECT * FROM extracted_entities')) == 8
    assert len(await real_db.query('SELECT * FROM extracted_relationships')) == 9
    assert len(await real_db.query('SELECT * FROM persons')) == 2
    assert len(await real_db.query('SELECT * FROM officer_documents')) == 1
    removal_graph.tx.run.side_effect = None
    await remove_document_records(real_db, removal_graph, doc_id, 1)
    assert not await real_db.query('SELECT * FROM officer_documents')


async def test_removal_preserves_independent_sql_and_graph_links(real_db, removal_graph):
    from backend.services.document_removal import remove_document_records
    doc_id = await add_document(real_db)
    payload = await persist_extraction(real_db, doc_id, full_extraction())
    await real_db.query("UPDATE officer_documents SET processing_status='complete'")
    person_id = next(n['id'] for n in payload['nodes'] if n['kind'] == 'Person' and n['id'] != 'P001')
    org_id = next(n['id'] for n in payload['nodes'] if n['kind'] == 'Organization')
    await real_db.query('CREATE TABLE independent_links (person_id varchar(20) REFERENCES persons ON DELETE CASCADE)')
    await real_db.query('INSERT INTO independent_links VALUES (%s)', (person_id,))
    removal_graph.run.side_effect = lambda query, params: [{'id': org_id}] if 'n:Organization' in query else []
    await remove_document_records(real_db, removal_graph, doc_id, 1)
    assert len(await real_db.query('SELECT * FROM persons')) == 2
    assert len(await real_db.query('SELECT * FROM independent_links')) == 1
    assert len(await real_db.query('SELECT * FROM organizations')) == 1


async def test_old_import_ownership_backfill_is_safe_and_repeatable(real_db, removal_graph):
    from backend.services.document_removal import remove_document_records
    doc_id = await add_document(real_db)
    await persist_extraction(real_db, doc_id, full_extraction())
    await real_db.query('DELETE FROM ingestion_owned_entities')
    await real_db.ensure_schema()
    await real_db.ensure_schema()
    await real_db.query("UPDATE officer_documents SET processing_status='complete'")
    await remove_document_records(real_db, removal_graph, doc_id, 1)
    assert len(await real_db.query('SELECT * FROM persons')) == 1
    assert not await real_db.query('SELECT * FROM cases')
    # Older numeric IDs cannot prove whether the lookup record predated the import.
    assert len(await real_db.query('SELECT * FROM locations')) == 1
    assert any('n:Location' in call.args[0] for call in removal_graph.tx.run.call_args_list)


async def test_profile_activity_uses_connections_and_disappears_with_source(real_db, removal_graph):
    from backend.services.document_removal import remove_document_records
    from backend.services.profile_activity import load_activity
    doc_id = await add_document(real_db)
    await persist_extraction(real_db, doc_id, full_extraction())
    # Alice is linked to the case in Mumbai, without a direct residence/sighting edge.
    person = (await real_db.query("SELECT * FROM persons WHERE person_id='P001'"))[0]
    assert person['city'] == 'Mumbai'
    assert person['last_seen'] is None
    data = await load_activity('P001', real_db, 1)
    assert data['location']['city'] == 'Mumbai'
    assert {entry['kind'] for entry in data['entries']} == {'PERSON_RECORD','WITNESS_IN','EMPLOYED_BY','CONTACTED'}
    assert all(entry['canOpenSource'] for entry in data['entries'])
    await real_db.query("UPDATE officer_documents SET processing_status='complete'")
    await remove_document_records(real_db, removal_graph, doc_id, 1)
    assert await load_activity('P001', real_db, 1) == {'entries': [], 'location': None}


async def test_entity_reuse_and_reviewed_person_identity_survive_source_removal(real_db, removal_graph):
    from types import SimpleNamespace

    from psycopg.types.json import Jsonb

    from backend.routes.documents import ConfirmBody, confirm_document
    from backend.services.document_removal import remove_document_records
    from backend.services.entity_resolution import person_suggestions
    from backend.services.extraction import Relationship

    original = full_extraction()
    original.relationships += [
        Relationship(subject='b', predicate='EMPLOYED_BY', object='o', evidence='Bob works at Acme'),
        Relationship(subject='b', predicate='RESIDES_IN', object='l', evidence='Bob resides in Mumbai'),
    ]
    first = await add_document(real_db)
    payload = await persist_extraction(real_db, first, original)
    bob_id = next(n['id'] for n in payload['nodes'] if n['kind'] == 'Person' and n['properties']['name'] == 'Bob')
    second = await add_document(real_db, confirmed=False)
    # Alternate formatting should resolve to the original phone and organization.
    reviewed = original.model_copy(deep=True)
    phone = next(e for e in reviewed.entities if e.kind == 'PhoneNumber')
    phone.name = phone.identifier = '+91 12345 67890'
    organization = next(e for e in reviewed.entities if e.kind == 'Organization')
    organization.identifier = None
    organization.name = ' ACME '
    await real_db.query("UPDATE officer_documents SET processing_status='awaiting_review',extraction=%s WHERE document_id=%s",
                        (Jsonb(reviewed.model_dump()), second))
    graph = removal_graph
    suggestions = await person_suggestions(real_db, graph, reviewed)
    bob = next(s for s in suggestions if s['ref'] == 'b')
    assert bob['personId'] == bob_id
    assert len(bob['sharedConnections']) >= 3
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(db=real_db, graph=graph)))
    await confirm_document(second, ConfirmBody(extraction=reviewed, person_matches={'b': bob_id}), request, {'officerId': 1})
    second_payload = await persist_extraction(real_db, second, reviewed)
    assert {(n['kind'], n['id']) for n in second_payload['nodes']} == {(n['kind'], n['id']) for n in payload['nodes']}
    assert (await real_db.query('SELECT COUNT(*) AS n FROM persons'))[0]['n'] == 2
    assert len(await real_db.query('SELECT DISTINCT canonical_id FROM extracted_entities WHERE kind=\'PhoneNumber\'')) == 1
    await real_db.query("UPDATE officer_documents SET processing_status='complete' WHERE document_id IN (%s,%s)", (first, second))
    await remove_document_records(real_db, graph, first, 1)
    assert await real_db.query('SELECT 1 FROM persons WHERE person_id=%s', (bob_id,))
    assert len(await real_db.query('SELECT * FROM extracted_entities WHERE document_id=%s', (second,))) == len(reviewed.entities)
    await remove_document_records(real_db, graph, second, 1)
    assert not await real_db.query('SELECT 1 FROM persons WHERE person_id=%s', (bob_id,))
    assert await real_db.query("SELECT 1 FROM persons WHERE person_id='P001'")


async def test_hybrid_search_keeps_person_and_officer_scope_and_exact_offsets(real_db, settings):
    from unittest.mock import AsyncMock

    import httpx

    from backend.services.rag import index_document, retrieve_context

    client = AsyncMock()
    async def embeddings(*args, **kwargs):
        texts = kwargs['json']['input']
        return httpx.Response(200, json={'embeddings': [[1, 0, 0] for _ in texts]})
    client.post.side_effect = embeddings
    first = await add_document(real_db)
    second = await add_document(real_db)
    pending = await add_document(real_db, confirmed=False)
    await persist_extraction(real_db, first, full_extraction())
    different = full_extraction()
    different.entities[0].identifier = 'P009'
    different.entities[0].name = 'Other Person'
    await persist_extraction(real_db, second, different)
    source = '   Alice lives in Mumbai.\n\nAlice witnessed a case.  '
    for identifier in (first, second, pending):
        result = await index_document(real_db, identifier, source, settings=settings, client=client)
        assert result['embedded'] == result['chunks'] > 0
    chunks = await retrieve_context(real_db, 1, 'Where does Alice reside?', person_id='P001', settings=settings, client=client)
    assert {row['document_id'] for row in chunks} == {first}
    assert chunks[0]['retrieval_mode'] == 'hybrid'
    assert source[chunks[0]['source_start'] - 1:chunks[0]['source_end']] == chunks[0]['chunk_text']
    assert await retrieve_context(real_db, 99, 'Alice', person_id='P001', settings=settings, client=client) == []
    await index_document(real_db, first, source, settings=settings, client=client)
    assert (await real_db.query('SELECT count(*) AS n FROM document_chunks WHERE document_id=%s', (first,)))[0]['n'] == 1
