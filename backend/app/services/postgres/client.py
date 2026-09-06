import logging
from pathlib import Path
from typing import Any

import asyncpg

from app.config import Settings

logger = logging.getLogger("kubernetes-dashboard")

_SCHEMA_PATH = Path(__file__).with_name("schema.sql")

_pool: asyncpg.Pool | None = None


class PostgresUnavailableError(RuntimeError):
    """Raised when the database cannot be reached."""


async def init_pool(settings: Settings) -> asyncpg.Pool | None:
    """Open the shared pool and apply the schema.

    A database outage must not stop the API from serving the Kubernetes and
    Prometheus panels, so a failure here logs and leaves the pool unset; callers
    retry through ensure_pool().
    """
    global _pool
    if _pool is not None:
        return _pool

    try:
        _pool = await asyncpg.create_pool(
            settings.database_url,
            min_size=1,
            max_size=10,
            timeout=5,
            command_timeout=15,
        )
    except Exception as exc:  # asyncpg raises a wide range of connection errors
        logger.warning("postgres unavailable: %s", exc)
        _pool = None
        return None

    await _apply_schema(_pool)
    logger.info("postgres pool ready")
    return _pool


async def ensure_pool(settings: Settings) -> asyncpg.Pool:
    """Pool for request handlers, reconnecting if startup happened before the
    database was reachable."""
    pool = _pool or await init_pool(settings)
    if pool is None:
        raise PostgresUnavailableError("Could not connect to PostgreSQL")
    return pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def _apply_schema(pool: asyncpg.Pool) -> None:
    schema = _SCHEMA_PATH.read_text(encoding="utf-8")
    async with pool.acquire() as connection:
        await connection.execute(schema)


async def fetch(settings: Settings, query: str, *args: Any) -> list[asyncpg.Record]:
    pool = await ensure_pool(settings)
    async with pool.acquire() as connection:
        return await connection.fetch(query, *args)


async def fetchrow(settings: Settings, query: str, *args: Any) -> asyncpg.Record | None:
    pool = await ensure_pool(settings)
    async with pool.acquire() as connection:
        return await connection.fetchrow(query, *args)


async def fetchval(settings: Settings, query: str, *args: Any) -> Any:
    pool = await ensure_pool(settings)
    async with pool.acquire() as connection:
        return await connection.fetchval(query, *args)


async def execute(settings: Settings, query: str, *args: Any) -> str:
    pool = await ensure_pool(settings)
    async with pool.acquire() as connection:
        return await connection.execute(query, *args)


async def ping(settings: Settings) -> None:
    await fetchval(settings, "SELECT 1")
