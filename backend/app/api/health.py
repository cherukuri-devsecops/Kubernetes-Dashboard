import asyncio
from typing import Any

from fastapi import APIRouter, Depends

from app.config import Settings, get_settings

router = APIRouter(tags=["health"])


async def check_postgres(settings: Settings) -> dict[str, Any]:
    from app.services.postgres import client as postgres_client

    try:
        await postgres_client.ping(settings)
        return {"status": "ok"}
    except Exception as exc:
        return {"status": "degraded", "detail": str(exc)}


async def check_redis(settings: Settings) -> dict[str, Any]:
    from app.services.redis import client as redis_client

    try:
        await redis_client.ping(settings)
        return {"status": "ok"}
    except Exception as exc:
        return {"status": "degraded", "detail": str(exc)}


async def check_kubernetes(settings: Settings) -> dict[str, Any]:
    from app.services.kubernetes import client as k8s_client

    try:
        info = await k8s_client.get_cluster_info(settings)
        return {"status": "ok", "detail": info["gitVersion"]}
    except Exception as exc:
        return {"status": "degraded", "detail": str(exc)}


async def build_health_response(settings: Settings) -> dict[str, Any]:
    postgres, redis, kubernetes = await asyncio.gather(
        check_postgres(settings),
        check_redis(settings),
        check_kubernetes(settings),
    )
    checks = {
        "api": {"status": "ok"},
        "postgres": postgres,
        "redis": redis,
        "kubernetes": kubernetes,
    }
    status = "ok"
    if any(check["status"] != "ok" for check in checks.values()):
        status = "degraded"
    return {
        "status": status,
        "service": settings.app_name,
        "environment": settings.environment,
        "checks": checks,
    }


@router.get("/health")
async def health(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    return await build_health_response(settings)
