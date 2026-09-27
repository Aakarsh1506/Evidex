import asyncio
import logging
from contextlib import AsyncExitStack, asynccontextmanager, suppress
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from .config import Settings
from .db import Database
from .errors import APIError
from .neo4j_driver import GraphDatabase
from .routes import auth, cases, crime_types, criminals, documents, officers, stats, workspace
from .security import token_lifetime
from .services.ingestion import worker

logger = logging.getLogger(__name__)


class APIJSONResponse(JSONResponse):
    def render(self, content):
        # Match the frontend's UTC timestamp format, including milliseconds.
        return super().render(
            jsonable_encoder(
                content,
                custom_encoder={
                    datetime: lambda value: (
                        value.replace(tzinfo=value.tzinfo or timezone.utc)
                        .astimezone(timezone.utc)
                        .isoformat(timespec="milliseconds")
                        .replace("+00:00", "Z")
                    ),
                },
            )
        )


def create_app(
    settings=None, *, database=None, graph=None, http_client=None, initialize_schema=True
):
    settings = settings or Settings.from_env()
    token_lifetime(settings.jwt_expires_in)

    @asynccontextmanager
    async def lifespan(app):
        # Close resources created here when the app stops or startup fails.
        async with AsyncExitStack() as stack:
            if database is None:
                db = Database(settings)
                stack.push_async_callback(db.close)
                await db.open()
            else:
                db = database
            graph_db = graph
            if graph_db is None:
                graph_db = GraphDatabase(settings)
                stack.push_async_callback(graph_db.close)
            client = http_client
            if client is None:
                client = await stack.enter_async_context(httpx.AsyncClient())
            settings.upload_dir.mkdir(parents=True, exist_ok=True)
            app.state.db = db
            app.state.graph = graph_db
            app.state.http_client = client
            if initialize_schema:
                try:
                    await db.ensure_schema()
                except Exception:
                    # Same degraded-start behavior as Express; health/login can
                    # still respond, and database routes return controlled errors.
                    logger.exception("Failed to ensure workspace/documents tables")
            task = asyncio.create_task(worker(app.state)) if initialize_schema else None
            try:
                yield
            finally:
                if task:
                    task.cancel()
                    with suppress(asyncio.CancelledError):
                        await task

    app = FastAPI(
        title="Secure Document Management System API",
        version="1.0.0",
        lifespan=lifespan,
        default_response_class=APIJSONResponse,
    )
    app.state.settings = settings
    app.state.active_explanations = 0
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.exception_handler(APIError)
    async def api_error(request: Request, exc: APIError):
        response = APIJSONResponse({"error": exc.message}, status_code=exc.status)
        if exc.clear_cookie:
            response.delete_cookie(settings.cookie_name)
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        # Keep invalid-body responses compatible with the original API.
        return APIJSONResponse({"error": "Invalid request"}, status_code=400)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return APIJSONResponse(
            {"error": str(exc.detail)}, status_code=exc.status_code, headers=exc.headers
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        logger.error("Unhandled API error", exc_info=exc)
        return APIJSONResponse({"error": "Internal server error"}, status_code=500)

    for router in (
        auth.router,
        cases.router,
        criminals.router,
        crime_types.router,
        stats.router,
        workspace.router,
        officers.router,
        documents.router,
    ):
        app.include_router(router)

    @app.get("/api/health", tags=["Health"])
    async def health():
        return {"ok": True}

    return app
