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

# How long a quiet pod's stream waits before emitting an SSE keepalive comment.
_KEEPALIVE_SECONDS = 15


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
    settings: Settings, namespace: str, pod: str, container: str | None, tail_lines: int
) -> AsyncIterator[str]:
    k8s_client.ensure_config_loaded(settings)
    core_api = client.CoreV1Api()
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[str | None] = asyncio.Queue()
    # follow=True blocks the reader thread indefinitely, so closing the response
    # is the only thing that can free it once the browser goes away.
    response_box: dict[str, Any] = {}
    stopped = threading.Event()

    def _read() -> None:
        kwargs: dict[str, Any] = {
            "name": pod,
            "namespace": namespace,
            "follow": True,
            "_preload_content": False,
            "tail_lines": tail_lines,
        }
        if container:
            kwargs["container"] = container
        try:
            response = core_api.read_namespaced_pod_log(**kwargs)
            response_box["response"] = response
            for raw_line in response:
                if stopped.is_set():
                    break
                line = raw_line.decode("utf-8", errors="replace").rstrip("\n")
                loop.call_soon_threadsafe(queue.put_nowait, line)
        except Exception as exc:
            # Expected on teardown: closing the response raises in mid-read.
            logger.info("pod log stream ended for %s/%s: %s", namespace, pod, exc)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    threading.Thread(target=_read, daemon=True).start()

    try:
        while True:
            try:
                line = await asyncio.wait_for(queue.get(), timeout=_KEEPALIVE_SECONDS)
            except asyncio.TimeoutError:
                # An SSE comment: ignored by clients, but it keeps proxies from
                # timing out a quiet pod's stream, and writing it is how a
                # disconnect gets noticed promptly rather than whenever the pod
                # next happens to log.
                yield ": keepalive\n\n"
                continue
            if line is None:
                break
            # Blank lines would terminate the SSE event early, so send a space.
            yield f"data: {line or ' '}\n\n"
    finally:
        # Runs when the client disconnects and FastAPI closes this generator.
        stopped.set()
        response = response_box.get("response")
        if response is not None:
            try:
                response.close()
                response.release_conn()
            except Exception as exc:
                logger.debug("closing pod log stream for %s/%s: %s", namespace, pod, exc)


@router.get("/stream")
async def stream(
    namespace: str = Query(...),
    pod: str = Query(...),
    container: str | None = Query(default=None),
    tailLines: int = Query(default=100, ge=1, le=2000),
    _user: AuthenticatedUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    return StreamingResponse(
        _pod_log_lines(settings, namespace, pod, container, tailLines),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # nginx fronts the SPA and would otherwise buffer the stream, so
            # nothing would reach the browser until the pod stopped logging.
            "X-Accel-Buffering": "no",
        },
    )
