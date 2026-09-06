import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth.security import AuthenticatedUser, require_user
from app.config import Settings, get_settings
from app.services.prometheus import client as prom_client
from app.services.prometheus.client import PrometheusUnavailableError

router = APIRouter(prefix="/metrics", tags=["metrics"])


async def _run(coro: Any) -> Any:
    try:
        return await coro
    except PrometheusUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Prometheus is unavailable: {exc}",
        ) from exc


@router.get("/cluster")
async def cluster(
    _user: AuthenticatedUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
) -> dict[str, float]:
    return await _run(prom_client.cluster_usage(settings))


@router.get("/cluster/range")
async def cluster_range(
    rangeMinutes: int = Query(default=60, ge=1, le=10080),
    stepSeconds: int = Query(default=30, ge=5, le=3600),
    _user: AuthenticatedUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
) -> dict[str, list[dict[str, Any]]]:
    end = time.time()
    start = end - rangeMinutes * 60
    return await _run(prom_client.cluster_usage_range(settings, start, end, f"{stepSeconds}s"))


@router.get("/nodes")
async def nodes(
    _user: AuthenticatedUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
) -> list[dict[str, Any]]:
    return await _run(prom_client.node_usage(settings))


@router.get("/nodes/range")
async def node_range(
    node: str = Query(...),
    rangeMinutes: int = Query(default=60, ge=1, le=10080),
    stepSeconds: int = Query(default=30, ge=5, le=3600),
    _user: AuthenticatedUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
) -> dict[str, list[dict[str, Any]]]:
    end = time.time()
    start = end - rangeMinutes * 60
    return await _run(prom_client.node_usage_range(settings, node, start, end, f"{stepSeconds}s"))


@router.get("/namespaces")
async def namespaces(
    _user: AuthenticatedUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
) -> list[dict[str, Any]]:
    return await _run(prom_client.namespace_usage(settings))


@router.get("/namespaces/range")
async def namespace_range(
    namespace: str = Query(...),
    rangeMinutes: int = Query(default=60, ge=1, le=10080),
    stepSeconds: int = Query(default=30, ge=5, le=3600),
    _user: AuthenticatedUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
) -> dict[str, list[dict[str, Any]]]:
    end = time.time()
    start = end - rangeMinutes * 60
    return await _run(prom_client.namespace_usage_range(settings, namespace, start, end, f"{stepSeconds}s"))


@router.get("/pods")
async def pods(
    namespace: str = Query(...),
    _user: AuthenticatedUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
) -> list[dict[str, Any]]:
    return await _run(prom_client.pod_usage(settings, namespace))


@router.get("/pods/range")
async def pod_range(
    namespace: str = Query(...),
    pod: str = Query(...),
    rangeMinutes: int = Query(default=60, ge=1, le=10080),
    stepSeconds: int = Query(default=30, ge=5, le=3600),
    _user: AuthenticatedUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
) -> dict[str, list[dict[str, Any]]]:
    end = time.time()
    start = end - rangeMinutes * 60
    return await _run(prom_client.pod_usage_range(settings, namespace, pod, start, end, f"{stepSeconds}s"))
