import logging
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field, StrictInt
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.responses import Response

from ..errors import APIError, api_errors
from ..security import require_auth
from ..services.document_files import legacy_path, load_document_file
from ..services.document_removal import remove_document_records
from ..services.document_text import FORMATS
from ..services.entity_resolution import person_suggestions
from ..services.extraction import SOURCE_TYPES, ExcludedEntity, ExcludedRelationship, Extraction

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/documents", tags=["Documents"])
MAX_FILE_SIZE = 20 * 1024 * 1024

# Types the browser can display in place, so "view original" does not force a download.
# Deliberately excludes anything the browser would execute as markup: every entry is either
# a plain image, a PDF, or text served with X-Content-Type-Options: nosniff below.
# TIFF, DOCX and SQLite exports stay downloads — a browser cannot render them.
VIEWABLE_INLINE = frozenset({
    "application/pdf", "image/png", "image/jpeg",
    "text/plain", "text/csv", "application/json", "application/sql",
})


def map_document(row):
    return {
        "id": row["document_id"],
        "name": row["original_name"],
        "type": row["mime_type"],
        "size": row["size_bytes"],
        "uploadedAt": row["uploaded_at"],
        "sourceType": row.get("source_type"),
        "status": row.get("processing_status", "stored"),
        "processingError": row.get("processing_error"),
        "confirmedAt": row.get("confirmed_at"),
        "progress": row.get("processing_progress"),
    }


def remove_legacy_file(directory, filename):
    """Delete a copy saved in uploads/ before contents moved to the database, if any."""
    path = legacy_path(directory, filename)
    try:
        if path is not None:
            path.unlink(missing_ok=True)
    except OSError:
        logger.warning("Could not remove uploaded file %s", path.name)


def read_upload(source):
    # Read in chunks and enforce the limit before the whole file is held in memory.
    chunks, size = [], 0
    while chunk := source.read(64 * 1024):
        size += len(chunk)
        if size > MAX_FILE_SIZE:
            raise APIError("File too large", 400)
        chunks.append(chunk)
    return b"".join(chunks)


@router.get("/source-types")
async def source_types(officer=Depends(require_auth)):
    return {"sourceTypes": SOURCE_TYPES, "extensions": list(FORMATS)}


@router.get("/", include_in_schema=False)
@router.get("")
async def list_documents(request: Request, officer=Depends(require_auth)):
    with api_errors("Failed to load documents"):
        rows = await request.app.state.db.query(
            """SELECT document_id, original_name, mime_type, size_bytes, uploaded_at,
               source_type, processing_status, processing_error, confirmed_at,
               processing_progress FROM officer_documents
               WHERE officer_id = %s ORDER BY uploaded_at DESC""",
            (officer["officerId"],),
        )
        return [map_document(row) for row in rows]


@router.post("/", status_code=201, include_in_schema=False)
@router.post(
    "",
    status_code=201,
    openapi_extra={
        "requestBody": {
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "file": {"type": "string", "format": "binary"},
                            "sourceType": {"type": "string", "enum": list(SOURCE_TYPES)},
                        },
                        "required": ["file"],
                    }
                }
            }
        },
    },
)
async def upload_document(request: Request, officer=Depends(require_auth)):
    # Parse after authentication, and close the parser's temporary files on all paths.
    async with request.form(max_files=1, max_fields=20) as form:
        file = form.get("file")
        if any(
            isinstance(value, UploadFile) and key != "file" for key, value in form.multi_items()
        ):
            raise APIError("Unexpected field", 400)
        if not isinstance(file, UploadFile) or not file.filename:
            raise APIError("No file provided", 400)
        if len(file.filename) > 255:
            raise APIError("Filename must be 255 characters or fewer", 400)
        source_type = form.get("sourceType", "fir")
        if not isinstance(source_type, str) or source_type not in SOURCE_TYPES:
            raise APIError("Select a valid document source type", 400)
        suffix = Path(file.filename).suffix.lower()
        if suffix not in FORMATS:
            raise APIError("Upload a PDF, image, TXT, CSV, JSON, or DOCX file", 400)
        if officer.get("officerId") is None:
            raise APIError("An officer account is required to upload documents", 403)
        if file.size is not None and file.size > MAX_FILE_SIZE:
            raise APIError("File too large", 400)
        filename = f"{uuid4()}{suffix}"
        with api_errors("Failed to save document"):
            content = await run_in_threadpool(read_upload, file.file)
            # One statement stores metadata and contents together: every backend sharing this
            # database can process and serve the file, and neither is saved without the other.
            rows = await request.app.state.db.query(
                """WITH document AS (
                     INSERT INTO officer_documents
                       (officer_id, original_name, stored_name, mime_type, size_bytes,
                        source_type, processing_status)
                     VALUES (%s, %s, %s, %s, %s, %s, 'queued') RETURNING *
                   ), stored AS (
                     INSERT INTO officer_document_files (document_id, content)
                     SELECT document_id, %s FROM document
                   )
                   SELECT * FROM document""",
                (
                    officer["officerId"],
                    file.filename,
                    filename,
                    FORMATS[suffix],
                    len(content),
                    source_type,
                    content,
                ),
            )
            return map_document(rows[0])


@router.get("/{document_id}")
async def document_details(document_id: int, request: Request, officer=Depends(require_auth)):
    with api_errors("Failed to load document"):
        rows = await request.app.state.db.query(
            "SELECT * FROM officer_documents WHERE document_id=%s AND officer_id=%s",
            (document_id, officer["officerId"]),
        )
        if not rows:
            raise APIError("Document not found", 404)
        row = rows[0]
        return {
            **map_document(row),
            "text": row.get("extracted_text"),
            "extraction": row.get("extraction"),
        }


@router.post("/{document_id}/process")
async def retry_document(document_id: int, request: Request, officer=Depends(require_auth)):
    with api_errors("Failed to queue document"):
        rows = await request.app.state.db.query(
            """UPDATE officer_documents SET processing_status='queued', processing_error=NULL,
               processing_progress=NULL,
               extraction=CASE WHEN graph_payload IS NULL AND confirmed_at IS NULL THEN NULL ELSE extraction END,
               source_type=COALESCE(source_type,'fir'), lease_until=NULL
               WHERE document_id=%s AND officer_id=%s
                 AND processing_status IN ('stored','failed','sync_failed','cancelled') RETURNING *""",
            (document_id, officer["officerId"]),
        )
        if not rows:
            raise APIError("Document unavailable or already processing/completed", 409)
        return map_document(rows[0])


@router.post("/{document_id}/cancel")
async def cancel_document(document_id: int, request: Request, officer=Depends(require_auth)):
    """Stop a queued or active extraction at the next safe checkpoint."""
    with api_errors("Failed to stop document processing"):
        rows = await request.app.state.db.query(
            """UPDATE officer_documents SET processing_status='cancelled',
               processing_error=NULL, lease_until=NULL,
               processing_progress='{"percent":0,"label":"Processing stopped by officer"}'::jsonb
               WHERE document_id=%s AND officer_id=%s
                 AND processing_status IN ('queued','processing','syncing')
                 AND confirmed_at IS NULL RETURNING *""",
            (document_id, officer["officerId"]),
        )
        if rows:
            return map_document(rows[0])
        existing = await request.app.state.db.query(
            "SELECT document_id, processing_status FROM officer_documents WHERE document_id=%s AND officer_id=%s",
            (document_id, officer["officerId"]),
        )
        if not existing:
            raise APIError("Document not found", 404)
        raise APIError("Document is not currently processing or is already confirmed.", 409)


class ConfirmBody(BaseModel):
    extraction: Extraction
    person_matches: dict[str, str] = Field(default_factory=dict, max_length=200)
    rejected_relationship_indices: list[StrictInt] = Field(default_factory=list, max_length=400)
    rejected_entity_indices: list[StrictInt] = Field(default_factory=list, max_length=200)


def reviewed_extraction(body):
    rejected = set(body.rejected_relationship_indices)
    if len(rejected) != len(body.rejected_relationship_indices) or any(
        index < 0 or index >= len(body.extraction.relationships) for index in rejected
    ):
        raise APIError("Rejected relationship selections are invalid. Reload the draft.", 400)
    reviewed = body.extraction.model_copy(deep=True)
    rejected_entities = set(body.rejected_entity_indices)
    if len(rejected_entities) != len(body.rejected_entity_indices) or any(
        index < 0 or index >= len(body.extraction.entities) for index in rejected_entities
    ):
        raise APIError("Rejected entity selections are invalid. Reload the draft.", 400)
    rejected_refs = {
        entity.ref for index, entity in enumerate(body.extraction.entities)
        if index in rejected_entities
    }
    reviewed.entities = []
    for index, entity in enumerate(body.extraction.entities):
        if index in rejected_entities:
            reviewed.excluded_entities.append(ExcludedEntity(
                **entity.model_dump(), reason="Rejected by reviewer during confirmation."
            ))
        else:
            reviewed.entities.append(entity)
    reviewed.relationships = []
    for index, relation in enumerate(body.extraction.relationships):
        endpoint_rejected = relation.subject in rejected_refs or relation.object in rejected_refs
        if index in rejected or endpoint_rejected:
            reviewed.excluded_relationships.append(
                ExcludedRelationship(
                    **relation.model_dump(),
                    reason="An endpoint entity was rejected by the reviewer."
                    if endpoint_rejected else "Rejected by reviewer during confirmation."
                )
            )
        else:
            reviewed.relationships.append(relation)
    return reviewed


async def require_review_draft(db, document_id, officer_id, extraction):
    rows = await db.query(
        """SELECT document_id FROM officer_documents WHERE document_id=%s AND officer_id=%s
           AND processing_status='awaiting_review' AND confirmed_at IS NULL
           AND graph_payload IS NULL AND extraction=%s""",
        (document_id, officer_id, Jsonb(extraction.model_dump())),
    )
    if not rows:
        raise APIError("Draft changed or is unavailable. Reload it before reviewing identities.", 409)


@router.post("/{document_id}/identity-suggestions")
async def identity_suggestions(document_id: int, body: ConfirmBody, request: Request, officer=Depends(require_auth)):
    with api_errors("Failed to check existing identities"):
        await require_review_draft(request.app.state.db, document_id, officer["officerId"], body.extraction)
        reviewed = reviewed_extraction(body)
        return {"suggestions": await person_suggestions(request.app.state.db, request.app.state.graph, reviewed)}


@router.post("/{document_id}/confirm")
async def confirm_document(
    document_id: int, body: ConfirmBody, request: Request, officer=Depends(require_auth)
):
    with api_errors("Failed to confirm extraction"):
        reviewed = reviewed_extraction(body)
        if body.person_matches:
            await require_review_draft(request.app.state.db, document_id, officer["officerId"], body.extraction)
            suggestions = await person_suggestions(request.app.state.db, request.app.state.graph, reviewed)
            allowed = {(item["ref"], item["personId"]) for item in suggestions}
            if any((ref, person_id) not in allowed for ref, person_id in body.person_matches.items()):
                raise APIError("A person match changed or is unsupported. Review the shared connections again.", 409)
        # JSON equality prevents approval of a different or stale draft.
        rows = await request.app.state.db.query(
            """UPDATE officer_documents SET processing_status='queued',
               confirmed_at=now(), confirmed_by=%s, processing_error=NULL, lease_until=NULL,
               processing_progress=NULL,
               extraction=%s, person_matches=%s
               WHERE document_id=%s AND officer_id=%s AND processing_status='awaiting_review'
                 AND confirmed_at IS NULL AND graph_payload IS NULL AND extraction=%s
               RETURNING *""",
            (
                officer["officerId"],
                Jsonb(reviewed.model_dump()),
                Jsonb(body.person_matches),
                document_id,
                officer["officerId"],
                Jsonb(body.extraction.model_dump()),
            ),
        )
        if not rows:
            raise APIError("Draft changed or is unavailable. Reload it before confirming.", 409)
        return {**map_document(rows[0]), "extraction": reviewed.model_dump()}


@router.get("/{document_id}/file")
async def get_document(document_id: int, request: Request, officer=Depends(require_auth)):
    with api_errors("Failed to load document"):
        # Check ownership in the query before serving any file.
        rows = await request.app.state.db.query(
            """SELECT document_id, stored_name, mime_type, original_name FROM officer_documents
               WHERE document_id = %s AND officer_id = %s""",
            (document_id, officer["officerId"]),
        )
        if not rows:
            raise APIError("Document not found", 404)
        doc = rows[0]
        content = await load_document_file(request.app.state.db, request.app.state.settings.upload_dir, doc)
        if content is None:
            raise APIError("Document not found", 404)
        disposition = "inline" if doc["mime_type"] in VIEWABLE_INLINE else "attachment"
        name = doc["original_name"]
        encoded = quote(name)
        return Response(
            content,
            media_type=doc["mime_type"],
            headers={
                "Content-Disposition": f"{disposition}; filename*=utf-8''{encoded}" if encoded != name
                else f'{disposition}; filename="{name}"',
                "X-Content-Type-Options": "nosniff",
            },
        )


@router.delete("/{document_id}")
async def delete_document(document_id: int, request: Request, officer=Depends(require_auth)):
    with api_errors("Failed to delete document"):
        stored_name = await remove_document_records(
            request.app.state.db, request.app.state.graph, document_id, officer["officerId"],
        )
        # Database contents are removed with the document row; also tidy any old local copy.
        await run_in_threadpool(remove_legacy_file, request.app.state.settings.upload_dir, stored_name)
        return {"ok": True}
