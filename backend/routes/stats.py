import asyncio

from fastapi import APIRouter, Depends, Request
from psycopg.errors import UndefinedTable

from ..errors import api_errors
from ..security import require_auth

router = APIRouter(prefix="/api/stats", tags=["Statistics"], dependencies=[Depends(require_auth)])


@router.get("/", include_in_schema=False)
@router.get("")
async def get_stats(request: Request):
    db = request.app.state.db
    with api_errors("Failed to load stats"):
        # Fetch independent dashboard totals concurrently. Counts are per case, not per person.
        cases, people, tags, cities, statuses, documents = await asyncio.gather(
            db.query("SELECT COUNT(*)::int AS count FROM cases"),
            db.query("SELECT COUNT(*)::int AS count FROM persons"),
            db.query("""SELECT ct.crime_name, COUNT(DISTINCT c.case_id)::int AS count
                        FROM cases c JOIN crime_types ct ON ct.crime_id = c.crime_id
                        GROUP BY ct.crime_name ORDER BY count DESC"""),
            # Cases with no recorded location are counted in the total, not shown as a blank place.
            db.query("""SELECT l.city, COUNT(*)::int AS count
                        FROM cases c JOIN locations l ON l.location_id = c.location_id
                        WHERE btrim(COALESCE(l.city, '')) <> ''
                        GROUP BY l.city ORDER BY count DESC"""),
            db.query("""SELECT COALESCE(NULLIF(btrim(case_status), ''), 'Not recorded') AS status,
                               COUNT(*)::int AS count
                        FROM cases GROUP BY status ORDER BY count DESC"""),
            db.query("SELECT COUNT(DISTINCT document_id)::int AS count FROM case_documents"),
        )
        traced = 0
        try:
            graph_rows = await request.app.state.graph.run(
                "MATCH ()-[r]->() RETURN count(r) AS count"
            )
            if graph_rows:
                traced = int(graph_rows[0].get("count", 0))
        except Exception:
            try:
                rows = await db.query("SELECT COUNT(*)::int AS count FROM associations")
                traced = rows[0]["count"]
            except UndefinedTable:
                # Older databases may not have the optional associations table.
                pass
        return {
            "totalCases": cases[0]["count"],
            "totalPeople": people[0]["count"],
            "totalDocuments": documents[0]["count"],
            "tracedConnections": traced,
            "tagCounts": [[row["crime_name"], row["count"]] for row in tags],
            "cityCounts": [[row["city"], row["count"]] for row in cities],
            "statusCounts": [[row["status"], row["count"]] for row in statuses],
        }
