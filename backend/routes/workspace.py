import asyncio

from fastapi import APIRouter, Depends, Request

from ..errors import APIError, api_errors
from ..models import CaseBody
from ..security import require_auth

router = APIRouter(prefix="/api/workspace", tags=["Workspace"])
LIST_ITEMS_SQL = """
  SELECT c.case_id,
         COALESCE((SELECT e.properties->>'source_identifier' FROM extracted_entities e
          WHERE e.kind='Case' AND e.canonical_id=c.case_id
            AND e.properties->>'source_identifier' IS NOT NULL
          ORDER BY e.entity_id LIMIT 1), c.case_id) AS reference,
         c.title, c.case_status, ct.crime_name
  FROM officer_case_list w
  JOIN cases c ON c.case_id = w.case_id
  LEFT JOIN crime_types ct ON ct.crime_id = c.crime_id
  WHERE w.officer_id = %s
  ORDER BY w.added_at ASC
"""


@router.get("/", include_in_schema=False)
@router.get("")
async def get_workspace(request: Request, officer=Depends(require_auth)):
    # Scope both the pin and working list to the signed-in officer.
    with api_errors("Failed to load workspace"):
        pinned, rows = await asyncio.gather(
            request.app.state.db.query(
                "SELECT case_id FROM officer_pinned_case WHERE officer_id = %s",
                (officer["officerId"],),
            ),
            request.app.state.db.query(LIST_ITEMS_SQL, (officer["officerId"],)),
        )
        return {
            "pinnedId": pinned[0]["case_id"] if pinned else None,
            "workingList": [
                {
                    "id": row["case_id"],
                    "reference": row.get("reference") or row["case_id"],
                    "title": row.get("title"),
                    "status": row.get("case_status"),
                    "crimeTags": [row["crime_name"]] if row.get("crime_name") else [],
                }
                for row in rows
            ],
        }


@router.put("/pin")
async def pin(request: Request, body: CaseBody | None = None, officer=Depends(require_auth)):
    if body is None or not body.caseId:
        raise APIError("caseId is required", 400)
    with api_errors("Failed to pin case"):
        # Each officer has one pin; pinning again replaces it.
        await request.app.state.db.query(
            """INSERT INTO officer_pinned_case (officer_id, case_id, pinned_at)
               VALUES (%s, %s, now())
               ON CONFLICT (officer_id) DO UPDATE
               SET case_id = EXCLUDED.case_id, pinned_at = now()""",
            (officer["officerId"], body.caseId),
        )
        return {"pinnedId": body.caseId}


@router.delete("/pin")
async def unpin(request: Request, officer=Depends(require_auth)):
    with api_errors("Failed to unpin case"):
        await request.app.state.db.query(
            "DELETE FROM officer_pinned_case WHERE officer_id = %s",
            (officer["officerId"],),
        )
        return {"pinnedId": None}


@router.post("/list", status_code=201)
async def add_to_list(
    request: Request, body: CaseBody | None = None, officer=Depends(require_auth)
):
    if body is None or not body.caseId:
        raise APIError("caseId is required", 400)
    with api_errors("Failed to add to list"):
        # Repeated additions leave the existing list entry unchanged.
        await request.app.state.db.query(
            """INSERT INTO officer_case_list (officer_id, case_id) VALUES (%s, %s)
               ON CONFLICT (officer_id, case_id) DO NOTHING""",
            (officer["officerId"], body.caseId),
        )
        return {"ok": True}


@router.delete("/list/{case_id}")
async def remove_from_list(case_id: str, request: Request, officer=Depends(require_auth)):
    with api_errors("Failed to remove from list"):
        await request.app.state.db.query(
            "DELETE FROM officer_case_list WHERE officer_id = %s AND case_id = %s",
            (officer["officerId"], case_id),
        )
        return {"ok": True}
