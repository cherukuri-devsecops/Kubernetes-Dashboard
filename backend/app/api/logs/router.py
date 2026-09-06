import asyncio
import logging
import threading
import time
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from kubernetes import client

from app.auth.security import AuthenticatedUser, require_user
from app.config import Settings, get_settings
from app.services.kubernetes import client as k8s_client
from app.services.loki import client as loki_client
from app.services.loki.client import LokiUnavailableError

logger = logging.getLogger("kubernetes-dashboard")

router = APIRouter(prefix="/logs", tags=["logs"])


@router.get("/search")
async def search(
    namespace: str | None = Query(default=None),
    pod: str | None = Query(default=None),
    container: str | None = Query(default=None),
    query: str | None = Query(default=None),
    rangeMinutes: int = Query(default=60, ge=1, le=10080),
    limit: int = Query(default=200, ge=1, le=1000),
    _user: AuthenticatedUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    logql = loki_client.pod_logql(namespace, pod, container, query)
    end_ns = int(time.time() * 1_000_000_000)
    start_ns = end_ns - rangeMinutes * 60 * 1_000_000_000
    try:
        entries = await loki_client.query_range(settings, logql, start_ns, end_ns, limit)
    except LokiUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Loki is unavailable: {exc}",
        ) from exc
    return {"entries": entries}


async def _pod_log_lines(
    settings: Settings, namespace: str, pod: str, container: str | None
) -> AsyncIterator[str]:
    k8s_client.ensure_config_loaded(settings)
    core_api = client.CoreV1Api()
    loop = asyncio.get_event_loop()
    queue: asyncio.Queue[str | None] = asyncio.Queue()

    def _read() -> None:
        kwargs: dict[str, Any] = {
            "name": pod,
            "namespace": namespace,
            "follow": True,
            "_preload_content": False,
            "tail_lines": 100,
        }
        if container:
            kwargs["container"] = container
        try:
            response = core_api.read_namespaced_pod_log(**kwargs)
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").rstrip("\n")
                loop.call_soon_threadsafe(queue.put_nowait, line)
        except Exception as exc:
            logger.info("pod log stream ended for %s/%s: %s", namespace, pod, exc)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    threading.Thread(target=_read, daemon=True).start()

    while True:
        line = await queue.get()
        if line is None:
            break
        yield f"data: {line}\n\n"


@router.get("/stream")
async def stream(
    namespace: str = Query(...),
    pod: str = Query(...),
    container: str | None = Query(default=None),
    _user: AuthenticatedUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    return StreamingResponse(
        _pod_log_lines(settings, namespace, pod, container),
        media_type="text/event-stream",
    )
