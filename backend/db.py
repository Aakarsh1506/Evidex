from contextlib import asynccontextmanager

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from .config import BASE_DIR


class Database:
    def __init__(self, settings):
        # DATABASE_URL (postgresql://user:password@host:port/db?sslmode=require) takes precedence
        # over the separate PG* settings. libpq tries SSL first by default either way.
        target = {} if settings.database_url else {
            "host": settings.pg_host,
            "port": settings.pg_port,
            "user": settings.pg_user,
            "password": settings.pg_password,
            "dbname": settings.pg_database,
        }
        self.pool = AsyncConnectionPool(
            conninfo=settings.database_url,
            kwargs={
                **target,
                "connect_timeout": 5,
                "row_factory": dict_row,
                "autocommit": True,
                "options": "-c timezone=UTC",
            },
            min_size=0,
            max_size=10,
            max_idle=30,
            timeout=5,
            open=False,
        )

    async def open(self):
        await self.pool.open()

    async def close(self):
        await self.pool.close()

    async def query(self, sql, params=()):
        # Borrow a pooled connection and return rows as dictionaries.
        async with self.pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(sql, params or None)
                return await cursor.fetchall() if cursor.description else []

    async def ensure_schema(self):
        # Create app-owned tables without replacing existing records.
        # cases.sql runs last: it extends tables that ingestion.sql creates or relaxes.
        for filename in ("officers.sql", "workspace.sql", "documents.sql", "ingestion.sql",
                         "cases.sql"):
            await self.query((BASE_DIR / "sql" / filename).read_text())

    @asynccontextmanager
    async def transaction(self):
        async with self.pool.connection() as connection:
            async with connection.transaction():
                yield Transaction(connection)


class Transaction:
    def __init__(self, connection):
        self.connection = connection

    async def query(self, sql, params=()):
        async with self.connection.cursor() as cursor:
            await cursor.execute(sql, params or None)
            return await cursor.fetchall() if cursor.description else []
