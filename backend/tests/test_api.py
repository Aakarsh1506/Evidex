import json
import re
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import jwt
import pytest
from psycopg.errors import UndefinedTable, UniqueViolation

from backend.security import verify_password

from .conftest import PROFILE

FIXTURES = Path(__file__).parent / "fixtures"
PERSON = {
    "person_id": "P001",
    "name": "Mohit Chawla",
    "alias": "MC",
    "dob": date(1990, 1, 2),
    "age": 36,
    "height_cm": 180,
    "city": "Mumbai",
    "state": "Maharashtra",
    "last_seen": date(2025, 9, 8),
    "family_known": True,
    "record_status": "Active",
    "crime_tags": ["Fraud", None],
    "photo": None,
}


def test_route_inventory_matches_express(app):
    expected = json.loads((FIXTURES / "express_routes.json").read_text())
    actual = sorted(
        [method.upper(), re.sub(r"\{\w+\}", "{id}", path)]
        for path, methods in app.openapi()["paths"].items()
        for method in methods
        if method in {"get", "post", "put", "patch", "delete"}
    )
    assert actual == sorted(
        expected
        + [
            ["GET", "/api/criminals/{id}/activity"],
                ["GET", "/api/criminals/{id}/record"],
                ["POST", "/api/criminals/{id}/record/generate"],
            # Cases are the primary browsable record; the person routes above stay
            # for the folded-in participant details and the document review flow.
            ["GET", "/api/cases"],
                ["GET", "/api/cases/{id}"],
                ["GET", "/api/cases/{id}/network"],
                ["POST", "/api/cases/{id}/summary"],
                ["POST", "/api/cases/{id}/explain"],
            ["GET", "/api/documents/source-types"],
            ["GET", "/api/documents/{id}"],
            ["POST", "/api/documents/{id}/process"],
                ["POST", "/api/documents/{id}/identity-suggestions"],
                ["POST", "/api/documents/{id}/confirm"],
                ["POST", "/api/documents/{id}/cancel"],
        ]
    )


async def test_health_and_cors(client):
    response = await client.get("/api/health", headers={"Origin": "http://localhost:3000"})
    assert response.json() == {"ok": True}
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert response.headers["access-control-allow-credentials"] == "true"
    response = await client.options(
        "/api/documents",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    response = await client.get("/api/health", headers={"Origin": "https://untrusted.example"})
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize(
    "path",
    [
        "/api/criminals",
        "/api/crime-types",
        "/api/stats",
        "/api/workspace",
        "/api/officers",
        "/api/documents",
        "/api/auth/me",
        "/api/criminals/P001/network",
        "/api/criminals/P001/activity",
    ],
)
async def test_protected_routes_require_cookie(client, db, path):
    response = await client.get(path)
    assert response.status_code == 401
    assert response.json() == {"error": "Not authenticated"}
    db.query.assert_not_called()


async def test_node_jwt_and_profile_shape(client, settings):
    fixture = json.loads((FIXTURES / "express_auth.json").read_text())
    client.cookies.set(settings.cookie_name, fixture["token"])
    response = await client.get("/api/auth/me")
    assert response.status_code == 200
    assert response.json() == fixture["profile"]


@pytest.mark.parametrize("token", ["invalid", "expired", "wrong-signature"])
async def test_bad_cookie_is_cleared(client, settings, token):
    if token == "expired":
        token = jwt.encode(
            {**PROFILE, "exp": datetime.now(timezone.utc) - timedelta(hours=1)},
            settings.jwt_secret,
            algorithm="HS256",
        )
    elif token == "wrong-signature":
        token = jwt.encode(PROFILE, "different-secret-long-enough-for-hmac", algorithm="HS256")
    client.cookies.set(settings.cookie_name, token)
    response = await client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json()["error"].startswith("Session expired")
    assert "Max-Age=0" in response.headers["set-cookie"]


@pytest.mark.parametrize("body", [{}, {"username": "officer"}, {"username": 1, "password": []}])
async def test_login_bad_input(client, body):
    response = await client.post("/api/auth/login", json=body)
    assert response.status_code == 400
    assert "error" in response.json()


async def test_officer_login_node_bcrypt_and_logout(client, db, settings):
    fixture = json.loads((FIXTURES / "express_auth.json").read_text())
    db.query.return_value = [
        {
            "officer_id": 7,
            "username": "officer",
            "name": "Test Officer",
            "org_name": "Test Police",
            "role": "officer",
            "is_active": True,
            "password_hash": fixture["passwordHash"],
        }
    ]
    response = await client.post(
        "/api/auth/login", json={"username": "officer", "password": "password123"}
    )
    assert response.status_code == 200
    assert response.json() == PROFILE
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie and "Max-Age=43200" in cookie
    assert (await client.get("/api/auth/me")).json() == PROFILE
    assert "password_hash" not in response.text
    assert (await client.post("/api/auth/logout")).json() == {"ok": True}
    assert (await client.get("/api/auth/me")).status_code == 401
    assert verify_password("é" * 40, fixture["longPasswordHash"])


async def test_invalid_inactive_and_database_login(client, db):
    response = await client.post(
        "/api/auth/login", json={"username": "missing", "password": "password123"}
    )
    assert response.status_code == 401
    db.query.return_value = [{"is_active": False}]
    assert (
        await client.post(
            "/api/auth/login", json={"username": "inactive", "password": "password123"}
        )
    ).status_code == 401
    db.query.side_effect = RuntimeError("private connection details")
    response = await client.post(
        "/api/auth/login", json={"username": "officer", "password": "password123"}
    )
    assert response.status_code == 500
    assert response.json() == {"error": "Login failed"}


async def test_admin_login_cookie_security(client, app, settings, db):
    app.state.settings = replace(
        settings, admin_username="admin", admin_password="admin-password", production=True
    )
    response = await client.post(
        "/api/auth/login", json={"username": "admin", "password": "admin-password"}
    )
    assert response.status_code == 200
    assert response.json()["role"] == "admin" and response.json()["officerId"] is None
    assert "Secure" in response.headers["set-cookie"]
    db.query.assert_not_called()


async def test_admin_routes_reject_officers(officer_client, db):
    for method, path, body in [
        ("GET", "/api/officers", None),
        ("POST", "/api/officers", {}),
        ("PATCH", "/api/officers/7/deactivate", None),
    ]:
        response = await officer_client.request(method, path, json=body)
        assert response.status_code == 403
        assert response.json() == {"error": "Admin access required"}
    db.query.assert_not_called()


async def test_create_officer_ignores_requested_admin_role(admin_client, db):
    db.query.return_value = [
        {"officer_id": 10, "username": "new", "role": "officer", "dob": date(1991, 5, 4)}
    ]
    response = await admin_client.post(
        "/api/officers",
        json={
            "username": "new",
            "password": "password123",
            "name": "New Officer",
            "orgName": "Police",
            "dob": "1991-05-04",
            "role": "admin",
        },
    )
    assert response.status_code == 201
    assert response.json()["role"] == "officer"
    sql, params = db.query.call_args.args
    assert "'officer'" in sql and "admin" not in params
    assert verify_password("password123", params[1])
    assert params[3] == date(1991, 5, 4)
    assert response.json()["dob"] == "1991-05-04"


async def test_officer_validation_duplicate_list_deactivate(admin_client, db):
    assert (await admin_client.post("/api/officers", json={})).status_code == 400
    body = {"username": "new", "password": "short", "name": "New", "orgName": "Police"}
    assert (await admin_client.post("/api/officers", json=body)).json() == {
        "error": "Password must be at least 8 characters"
    }
    db.query.side_effect = UniqueViolation()
    assert (
        await admin_client.post("/api/officers", json={**body, "password": "password123"})
    ).status_code == 409
    db.query.side_effect = None
    db.query.return_value = [{"officer_id": 7, "username": "officer"}]
    assert (await admin_client.get("/api/officers")).json() == db.query.return_value
    db.query.return_value = []
    assert (await admin_client.patch("/api/officers/999/deactivate")).status_code == 404
    db.query.return_value = [{"officer_id": 7, "username": "officer", "is_active": False}]
    assert (await admin_client.patch("/api/officers/7/deactivate")).json()["is_active"] is False


async def test_criminal_search_and_shape(officer_client, db):
    db.query.return_value = [
        PERSON,
        {
            **PERSON,
            "person_id": "P002",
            "name": "Jane Doe",
            "alias": None,
            "crime_tags": ["Robbery"],
        },
    ]
    assert (await officer_client.get("/api/criminals")).json() == []
    all_people = (await officer_client.get("/api/criminals?all=true")).json()
    assert len(all_people) == 2
    assert all_people[0]["location"] == {"city": "Mumbai", "state": "Maharashtra", "x": 22, "y": 62}
    assert all_people[0]["dob"] == "1990-01-02"
    assert all_people[0]["lastSeen"] == "Mumbai — 08 Sept 2025"
    assert all_people[0]["crimeTags"] == ["Fraud"]
    for query in ["q=mohit", "q=MC", "q=fra", "tags=FRAUD"]:
        assert [
            row["id"] for row in (await officer_client.get(f"/api/criminals?{query}")).json()
        ] == ["P001"]
    assert len((await officer_client.get("/api/criminals?q=mohit&tags=robbery")).json()) == 2
    assert (await officer_client.get("/api/criminals/", follow_redirects=False)).status_code == 200


async def test_profile_cases_and_neo4j_fallback(officer_client, db, graph):
    async def query(sql, params=()):
        assert params == ("P001",)
        if "SELECT p.*" in sql:
            return [PERSON]
        return [
            {
                "case_id": "C1",
                "case_month": date(2025, 1, 1),
                "case_status": "Open",
                "city": "Mumbai",
                "state": "Maharashtra",
                "crime_name": "Fraud",
            }
        ]

    db.query.side_effect = query
    graph.run.side_effect = RuntimeError("offline")
    response = await officer_client.get("/api/criminals/P001")
    assert response.status_code == 200
    profile = response.json()
    assert profile["relations"] == []
    assert profile["criminal"]["cases"] == [
        {
            "caseId": "C1",
            "crime": "Fraud",
            "location": "Mumbai, Maharashtra",
            "status": "Open",
            "month": "2025-01-01",
        }
    ]
    db.query.side_effect = None
    db.query.return_value = []
    assert (await officer_client.get("/api/criminals/missing")).status_code == 404
    assert (await officer_client.get("/api/criminals/missing/network")).status_code == 500
    graph.run.side_effect = None
    graph.run.return_value = []
    assert (await officer_client.get("/api/criminals/missing/network")).status_code == 404


async def test_stats_optional_associations_and_crime_types(officer_client, db):
    async def query(sql, params=()):
        if "FROM associations" in sql:
            raise UndefinedTable()
        if "GROUP BY ct.crime_name" in sql:
            return [{"crime_name": "Fraud", "count": 4}]
        if "GROUP BY l.city" in sql:
            return [{"city": "Mumbai", "count": 3}]
        if "GROUP BY status" in sql:
            return [{"status": "Under investigation", "count": 6}]
        if "FROM case_documents" in sql:
            return [{"count": 12}]
        if "FROM persons" in sql:
            return [{"count": 5}]
        return [{"count": 10}]

    db.query.side_effect = query
    # Totals are per case now: people and documents are counted as case context, not as the subject.
    assert (await officer_client.get("/api/stats")).json() == {
        "totalCases": 10,
        "totalPeople": 5,
        "totalDocuments": 12,
        "tracedConnections": 0,
        "tagCounts": [["Fraud", 4]],
        "cityCounts": [["Mumbai", 3]],
        "statusCounts": [["Under investigation", 6]],
    }
    db.query.side_effect = None
    db.query.return_value = [{"crime_name": "Fraud"}]
    assert (await officer_client.get("/api/crime-types")).json() == ["Fraud"]


async def test_workspace_scopes_every_query_to_cookie(officer_client, db):
    async def query(sql, params=()):
        assert params[0] == 7
        if "SELECT case_id FROM officer_pinned_case" in sql:
            return [{"case_id": "FIR-2026-0142"}]
        if "FROM officer_case_list" in sql:
            return [{"case_id": "FIR-2026-0142", "reference": "FIR/142/2026",
                     "title": "Harbour Road theft", "case_status": "Under investigation",
                     "crime_name": "Theft"}]
        return []

    db.query.side_effect = query
    assert (await officer_client.get("/api/workspace")).json() == {
        "pinnedId": "FIR-2026-0142",
        "workingList": [{"id": "FIR-2026-0142", "reference": "FIR/142/2026",
                         "title": "Harbour Road theft", "status": "Under investigation",
                         "crimeTags": ["Theft"]}],
    }
    assert (await officer_client.put("/api/workspace/pin", json={})).status_code == 400
    body = {"caseId": "FIR-2026-0142", "officerId": 999}
    assert (await officer_client.put("/api/workspace/pin", json=body)).json() == {
        "pinnedId": "FIR-2026-0142"
    }
    assert (await officer_client.delete("/api/workspace/pin")).json() == {"pinnedId": None}
    assert (await officer_client.post("/api/workspace/list", json=body)).status_code == 201
    assert (await officer_client.post("/api/workspace/list", json={})).status_code == 400
    assert (await officer_client.delete("/api/workspace/list/FIR-2026-0142")).json() == {"ok": True}


@pytest.mark.parametrize(
    "path,error",
    [
        ("/api/criminals", "Failed to load criminals"),
        ("/api/stats", "Failed to load stats"),
        ("/api/workspace", "Failed to load workspace"),
        ("/api/crime-types", "Failed to load crime types"),
        ("/api/documents", "Failed to load documents"),
    ],
)
async def test_database_errors_keep_public_shape(officer_client, db, path, error):
    db.query.side_effect = RuntimeError("private postgres credentials")
    response = await officer_client.get(path)
    assert response.status_code == 500
    assert response.json() == {"error": error}
