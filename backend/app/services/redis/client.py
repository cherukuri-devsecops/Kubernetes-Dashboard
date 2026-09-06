import logging

from redis.asyncio import Redis, from_url
from redis.exceptions import RedisError

from app.config import Settings

logger = logging.getLogger("kubernetes-dashboard")

_client: Redis | None = None


async def init_client(settings: Settings) -> Redis | None:
    """Open the shared client. Redis is a cache, never the source of truth, so a
    failure here is logged and the app runs without it."""
    global _client
    if _client is not None:
        return _client

    try:
        client = from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        await client.ping()
    except (RedisError, OSError) as exc:
        logger.warning("redis unavailable: %s", exc)
        _client = None
        return None

    _client = client
    logger.info("redis client ready")
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def get_client() -> Redis | None:
    return _client


async def cache_get(key: str) -> str | None:
    if _client is None:
        return None
    try:
        return await _client.get(key)
    except (RedisError, OSError) as exc:
        logger.warning("redis GET failed: %s", exc)
        return None


async def cache_set(key: str, value: str, ttl_seconds: int) -> None:
    if _client is None:
        return
    try:
        await _client.set(key, value, ex=ttl_seconds)
    except (RedisError, OSError) as exc:
        logger.warning("redis SET failed: %s", exc)


async def cache_delete(key: str) -> None:
    if _client is None:
        return
    try:
        await _client.delete(key)
    except (RedisError, OSError) as exc:
        logger.warning("redis DEL failed: %s", exc)


async def ping(settings: Settings) -> None:
    client = _client or await init_client(settings)
    if client is None:
        raise RedisError("Redis is not connected")
    await client.ping()
