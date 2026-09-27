from datetime import datetime, timezone
from contextlib import asynccontextmanager

import pytest

from backend.routes.documents import MAX_FILE_SIZE


@pytest.fixture(autouse=True)
def document_transactions(db):
    @asynccontextmanager
    async def transaction():
        yield db
    db.transaction = transaction


async def test_upload_list_download_delete_preserves_contract(officer_client, db, settings):
    files, contents = {}, {}
    now = datetime(2026, 9, 8, 12, tzinfo=timezone.utc)

    async def query(sql, params=()):
        if "pg_advisory_xact_lock" in sql or "extracted_entities" in sql or "extracted_relationships" in sql:
            return []
        if "FROM officer_document_files" in sql:
            return [{"content": contents[params[0]]}] if params[0] in contents else []
        if sql.lstrip().startswith("WITH document AS"):
            officer_id, original, stored, mime, size, source_type, content = params
            assert officer_id == 7 and "INSERT INTO officer_document_files" in sql
            files[1] = {
                "document_id": 1,
                "officer_id": officer_id,
                "original_name": original,
                "stored_name": stored,
                "mime_type": mime,
                "size_bytes": size,
                "uploaded_at": now,
                "source_type": source_type,
                "processing_status": "queued",
            }
            contents[1] = content
            return [files[1]]
        if "ORDER BY uploaded_at" in sql:
            assert params == (7,)
            return list(files.values())
        assert params == (1, 7)
        assert "officer_id = %s" in sql
        if sql.lstrip().startswith("DELETE"):
            contents.pop(1, None)  # ON DELETE CASCADE
            return [files.pop(1)] if 1 in files else []
        return [files[1]] if 1 in files else []

    db.query.side_effect = query
    content = b"%PDF-1.7\nTest PDF content"
    response = await officer_client.post(
        "/api/documents", files={"file": ('report "one".pdf', content, "application/pdf")}
    )
    assert response.status_code == 201
    document = response.json()
    assert set(document) == {
        "id",
        "name",
        "type",
        "size",
        "uploadedAt",
        "sourceType",
        "status",
        "processingError",
        "confirmedAt",
        "progress",
    }
    assert document["status"] == "queued"
    assert document["id"] == 1 and document["size"] == len(content)
    assert document["type"] == "application/pdf"
    stored = files[1]["stored_name"]
    assert stored != document["name"] and stored.endswith(".pdf")
    # Contents are stored in the shared database, not on this computer's disk.
    assert contents[1] == content
    assert list(settings.upload_dir.iterdir()) == []
    assert (await officer_client.get("/api/documents")).json() == [document]
    download = await officer_client.get("/api/documents/1/file")
    assert download.status_code == 200 and download.content == content
    assert download.headers["content-type"] == "application/pdf"
    assert download.headers["content-disposition"].startswith("inline;")
    assert download.headers["x-content-type-options"] == "nosniff"
    files[1]["processing_status"] = "awaiting_review"
    assert (await officer_client.delete("/api/documents/1")).json() == {"ok": True}
    assert 1 not in contents
    assert (await officer_client.get("/api/documents/1/file")).status_code == 404


async def test_other_officer_cannot_read_or_delete(officer_client, db, settings):
    path = settings.upload_dir / "private.pdf"
    path.write_bytes(b"private document")
    db.query.return_value = []
    for method, url in [("GET", "/api/documents/10/file"), ("DELETE", "/api/documents/10")]:
        response = await officer_client.request(method, url)
        assert response.status_code == 404
        sql, params = db.query.call_args.args
        assert "officer_id = %s" in sql and params == (10, 7)
    assert path.exists()


async def test_remove_review_draft_deletes_file(officer_client, db, settings):
    path = settings.upload_dir / "draft.txt"
    path.write_text("Draft evidence")
    db.query.side_effect = lambda sql, params=(): (
        [{"stored_name": "draft.txt", "processing_status": "awaiting_review"}]
        if sql.startswith("SELECT * FROM officer_documents") else []
    )
    response = await officer_client.delete("/api/documents/3")
    assert response.status_code == 200
    assert not path.exists()
    sql, params = db.query.call_args.args
    assert "DELETE FROM officer_documents" in sql
    assert params == (3, 7)


async def test_remove_processing_document_keeps_file(officer_client, db, settings):
    path = settings.upload_dir / "retained.txt"
    path.write_text("Saved evidence")
    db.query.side_effect = [[], [{"document_id": 3, "processing_status": "processing"}]]
    response = await officer_client.delete("/api/documents/3")
    assert response.status_code == 409
    assert path.exists()


async def test_upload_requires_auth_before_saving(client, db, settings):
    response = await client.post(
        "/api/documents", files={"file": ("test.pdf", b"%PDF", "application/pdf")}
    )
    assert response.status_code == 401
    assert list(settings.upload_dir.iterdir()) == []
    db.query.assert_not_called()


@pytest.mark.parametrize(
    "files,message",
    [
        (None, "No file provided"),
        (
            {"file": ("test.exe", b"text", "text/plain")},
            "Upload a PDF, image, TXT, CSV, JSON, or DOCX file",
        ),
        ({"wrong": ("test.pdf", b"%PDF", "application/pdf")}, "Unexpected field"),
    ],
)
async def test_bad_uploads(officer_client, db, settings, files, message):
    response = await officer_client.post("/api/documents", files=files)
    assert response.status_code == 400
    assert response.json() == {"error": message}
    assert list(settings.upload_dir.iterdir()) == []
    db.query.assert_not_called()


async def test_file_size_limit_and_duplicate_files(officer_client, db, settings):
    response = await officer_client.post(
        "/api/documents",
        files={"file": ("large.pdf", b"x" * (MAX_FILE_SIZE + 1), "application/pdf")},
    )
    assert response.status_code == 400 and response.json() == {"error": "File too large"}
    assert list(settings.upload_dir.iterdir()) == []
    response = await officer_client.post(
        "/api/documents",
        files=[
            ("file", ("a.pdf", b"a", "application/pdf")),
            ("file", ("b.pdf", b"b", "application/pdf")),
        ],
    )
    assert response.status_code == 400
    assert "error" in response.json()
    db.query.assert_not_called()


async def test_failed_insert_removes_saved_pdf(officer_client, db, settings):
    db.query.side_effect = RuntimeError("database down")
    response = await officer_client.post(
        "/api/documents", files={"file": ("report.pdf", b"%PDF", "application/pdf")}
    )
    assert response.status_code == 500
    assert response.json() == {"error": "Failed to save document"}
    assert list(settings.upload_dir.iterdir()) == []


async def test_missing_file_and_path_escape(officer_client, db, settings):
    document = {"document_id": 1, "stored_name": "missing.pdf", "mime_type": "application/pdf",
                "original_name": "missing.pdf"}
    db.query.side_effect = lambda sql, params=(): [] if "officer_document_files" in sql else [document]
    assert (await officer_client.get("/api/documents/1/file")).status_code == 404
    document["stored_name"] = "../outside.pdf"
    (settings.upload_dir.parent / "outside.pdf").write_bytes(b"outside the upload folder")
    assert (await officer_client.get("/api/documents/1/file")).status_code == 404


async def test_file_saved_before_database_storage_is_served_and_shared(officer_client, db, settings):
    (settings.upload_dir / "legacy.pdf").write_bytes(b"%PDF legacy")
    document = {"document_id": 4, "stored_name": "legacy.pdf", "mime_type": "application/pdf",
                "original_name": "Old FIR.pdf"}
    db.query.side_effect = lambda sql, params=(): [] if "officer_document_files" in sql else [document]
    download = await officer_client.get("/api/documents/4/file")
    assert download.status_code == 200 and download.content == b"%PDF legacy"
    assert "filename*=utf-8''Old%20FIR.pdf" in download.headers["content-disposition"]
    copy = next(call for call in db.query.call_args_list if call.args[0].lstrip().startswith("INSERT INTO officer_document_files"))
    assert copy.args[1] == (4, b"%PDF legacy")


@pytest.mark.parametrize("mime_type,expected", [
    # Displayable in place, so "view original" shows the source instead of downloading it.
    ("application/pdf", "inline"),
    ("image/png", "inline"),
    ("image/jpeg", "inline"),
    ("text/plain", "inline"),
    ("text/csv", "inline"),
    ("application/json", "inline"),
    ("application/sql", "inline"),
    # A browser cannot render these, so they stay downloads.
    ("image/tiff", "attachment"),
    ("application/vnd.sqlite3", "attachment"),
    ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", "attachment"),
])
async def test_viewable_documents_are_served_inline(officer_client, db, mime_type, expected):
    document = {"document_id": 9, "stored_name": "source.bin", "mime_type": mime_type,
                "original_name": "source.bin"}
    body = b"FIRST INFORMATION REPORT"
    db.query.side_effect = lambda sql, params=(): (
        [{"content": body}] if "officer_document_files" in sql else [document]
    )
    response = await officer_client.get("/api/documents/9/file")
    assert response.status_code == 200 and response.content == body
    assert response.headers["content-disposition"].startswith(f"{expected};")
    # Inline text must never be sniffed into something executable.
    assert response.headers["x-content-type-options"] == "nosniff"
