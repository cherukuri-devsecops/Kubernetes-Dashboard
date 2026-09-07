"""Interactive `kubectl exec` over a WebSocket.

This is the one endpoint in the dashboard that can change the cluster, so it is
deliberately gated: it does nothing unless `exec_enabled` is set, it refuses any
namespace outside `exec_allowed_namespaces` when that is configured, and every
session is written to the audit log with the user who opened it.
"""

import asyncio
import json
import logging
import threading
from typing import Any

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from kubernetes import client
from kubernetes.stream import stream

from app.auth.security import AuthenticatedUser, authenticate_websocket
from app.config import Settings, get_settings
from app.services.kubernetes import client as k8s_client

logger = logging.getLogger("kubernetes-dashboard")

router = APIRouter(prefix="/exec", tags=["exec"])

# Close codes: 1008 is "policy violation", which is what a refusal is here.
_CLOSE_POLICY = 1008
_CLOSE_ERROR = 1011

# RFC 6455 caps a close frame's reason at 123 bytes; anything longer makes the
# peer drop the connection with a protocol error instead of showing the reason.
_MAX_CLOSE_REASON_BYTES = 123


def _close_reason(text: str) -> str:
    encoded = text.encode("utf-8")[:_MAX_CLOSE_REASON_BYTES]
    # Trim a codepoint that the byte-slice split in half.
    return encoded.decode("utf-8", errors="ignore")

# How long the reader thread waits on the pod before re-checking that the
# browser is still attached.
_READ_TIMEOUT_SECONDS = 0.5


class ExecDisabledError(RuntimeError):
    pass


def _shell_command(shells: list[str]) -> list[str]:
    """Picks the best shell present in the image.

    Tested with `-x` before exec rather than chained with `||`: a failed `exec`
    ends a non-interactive shell outright, so the fallback would never run and a
    distroless or busybox image would just drop the session.
    """
    attempts = "; ".join(f"[ -x {shell} ] && exec {shell}" for shell in shells)
    return ["/bin/sh", "-c", f"{attempts}; echo 'no usable shell in this container' >&2; exit 1"]


def _check_allowed(settings: Settings, namespace: str) -> None:
    if not settings.exec_enabled:
        raise ExecDisabledError("Pod exec is disabled on this deployment")
    allowed = settings.exec_allowed_namespace_list
    if allowed and namespace not in allowed:
        raise ExecDisabledError(f"Pod exec is not allowed in namespace '{namespace}'")


@router.get("/config")
async def exec_config(
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Lets the UI hide the terminal rather than offer a button that cannot work."""
    return {
        "enabled": settings.exec_enabled,
        "allowedNamespaces": settings.exec_allowed_namespace_list,
        "shells": settings.exec_shell_list,
    }


def _open_stream(
    settings: Settings, namespace: str, pod: str, container: str | None, command: list[str]
) -> Any:
    k8s_client.ensure_config_loaded(settings)
    core_api = client.CoreV1Api()
    kwargs: dict[str, Any] = {
        "name": pod,
        "namespace": namespace,
        "command": command,
        "stderr": True,
        "stdin": True,
        "stdout": True,
        "tty": True,
        "_preload_content": False,
    }
    if container:
        kwargs["container"] = container
    return stream(core_api.connect_get_namespaced_pod_exec, **kwargs)


@router.websocket("/pod")
async def exec_pod(
    websocket: WebSocket,
    namespace: str = Query(...),
    pod: str = Query(...),
    container: str | None = Query(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    user: AuthenticatedUser | None = await authenticate_websocket(websocket, settings)
    if user is None:
        # authenticate_websocket has already closed the socket.
        return

    try:
        _check_allowed(settings, namespace)
    except ExecDisabledError as exc:
        logger.warning("exec refused for %s (%s/%s): %s", user.email, namespace, pod, exc)
        await websocket.close(code=_CLOSE_POLICY, reason=_close_reason(str(exc)))
        return

    command = _shell_command(settings.exec_shell_list)

    logger.info(
        "exec session opened by %s into %s/%s container=%s",
        user.email,
        namespace,
        pod,
        container or "default",
    )

    try:
        resp = await asyncio.to_thread(_open_stream, settings, namespace, pod, container, command)
    except Exception as exc:
        logger.warning("exec could not attach to %s/%s: %s", namespace, pod, exc)
        await websocket.close(code=_CLOSE_ERROR, reason=_close_reason(f"Could not attach: {exc}"))
        return

    loop = asyncio.get_running_loop()
    outbound: asyncio.Queue[str | None] = asyncio.Queue()
    stopped = threading.Event()

    def _pump() -> None:
        """Reads the pod's output on a thread; the k8s stream API is blocking."""
        try:
            while resp.is_open() and not stopped.is_set():
                resp.update(timeout=_READ_TIMEOUT_SECONDS)
                if resp.peek_stdout():
                    loop.call_soon_threadsafe(outbound.put_nowait, resp.read_stdout())
                if resp.peek_stderr():
                    loop.call_soon_threadsafe(outbound.put_nowait, resp.read_stderr())
        except Exception as exc:
            logger.info("exec stream ended for %s/%s: %s", namespace, pod, exc)
        finally:
            loop.call_soon_threadsafe(outbound.put_nowait, None)

    reader = threading.Thread(target=_pump, daemon=True)
    reader.start()

    async def _to_browser() -> None:
        while True:
            chunk = await outbound.get()
            if chunk is None:
                break
            if chunk:
                await websocket.send_text(chunk)

    async def _from_browser() -> None:
        while True:
            message = await websocket.receive_text()
            try:
                payload = json.loads(message)
            except json.JSONDecodeError:
                continue
            kind = payload.get("type")
            if kind == "stdin":
                resp.write_stdin(payload.get("data", ""))
            elif kind == "resize":
                # The API server takes terminal resizes on channel 4 as JSON.
                rows, cols = int(payload.get("rows", 24)), int(payload.get("cols", 80))
                resp.write_channel(4, json.dumps({"Height": rows, "Width": cols}))

    to_browser = asyncio.create_task(_to_browser())
    from_browser = asyncio.create_task(_from_browser())

    try:
        # Either direction finishing ends the session: the pod's shell exited, or
        # the browser went away.
        _, pending = await asyncio.wait(
            {to_browser, from_browser}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
    except WebSocketDisconnect:
        pass
    finally:
        stopped.set()
        try:
            resp.close()
        except Exception as exc:
            logger.debug("closing exec stream for %s/%s: %s", namespace, pod, exc)
        logger.info("exec session closed by %s into %s/%s", user.email, namespace, pod)
        try:
            await websocket.close()
        except RuntimeError:
            # Already closed by the peer.
            pass
