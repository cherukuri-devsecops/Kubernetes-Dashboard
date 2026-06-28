"""
SSE and WebSocket streaming endpoints — all K8s connections live here.

  GET  /api/stream/pods/{namespace}/{name}/logs   — SSE live log tail
  GET  /api/stream/events                         — SSE K8s event watch
  WS   /api/ws/pods/{namespace}/{name}/exec       — WebSocket pod exec
"""
import asyncio
import json
import logging
import queue
import threading
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from kubernetes import watch
from kubernetes.client import ApiClient
from kubernetes.client.rest import ApiException
from kubernetes.stream import stream as k8s_stream

from ..k8s_client import _api_client, _header_dep, core_v1

logger = logging.getLogger(__name__)
router = APIRouter(tags=["streaming"])


# ── SSE helper ────────────────────────────────────────────────────────────────

def _sse_response(generator) -> StreamingResponse:
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Log stream ────────────────────────────────────────────────────────────────

@router.get("/api/stream/pods/{namespace}/{name}/logs")
def stream_pod_logs(
    namespace: str,
    name: str,
    container: str  = Query(default=""),
    tail: int       = Query(default=100),
    previous: bool  = Query(default=False),
    ac: ApiClient   = Depends(_header_dep),
):
    v1 = core_v1(ac)

    def generate():
        try:
            resp = v1.read_namespaced_pod_log(
                name=name, namespace=namespace,
                container=container or None,
                follow=True, _preload_content=False,
                tail_lines=tail, previous=previous, timestamps=True,
            )
            for chunk in resp.stream(decode_content=False):
                if not chunk:
                    continue
                for line in chunk.decode("utf-8", errors="replace").splitlines():
                    if line:
                        yield f"data: {line}\n\n"
        except ApiException as e:
            yield f"data: [log error: {e.reason}]\n\n"
        except GeneratorExit:
            return
        except Exception as e:
            yield f"data: [stream error: {e}]\n\n"

    return _sse_response(generate())


# ── Events stream ─────────────────────────────────────────────────────────────

@router.get("/api/stream/events")
def stream_events(
    namespace: str  = Query(default=""),
    ac: ApiClient   = Depends(_header_dep),
):
    v1 = core_v1(ac)

    def generate():
        w = watch.Watch()
        try:
            stream = (
                w.stream(v1.list_namespaced_event, namespace, timeout_seconds=300)
                if namespace else
                w.stream(v1.list_event_for_all_namespaces, timeout_seconds=300)
            )
            for ev in stream:
                obj    = ev["object"]
                etype  = obj.type or "Normal"
                ns_    = obj.metadata.namespace or ""
                kind   = obj.involved_object.kind or ""
                oname  = obj.involved_object.name or ""
                reason = obj.reason or ""
                msg    = (obj.message or "").replace('"', "'")
                line   = f"{etype}|||{ns_}|||{kind}/{oname}|||{reason}|||{msg}"
                yield f"data: {line}\n\n"
        except GeneratorExit:
            w.stop()
        except Exception as e:
            yield f"data: Warning|||system|||system|||Error|||{e}\n\n"

    return _sse_response(generate())


# ── WebSocket exec ────────────────────────────────────────────────────────────

@router.websocket("/api/ws/pods/{namespace}/{name}/exec")
async def exec_pod(
    websocket: WebSocket,
    namespace: str,
    name: str,
    container: str = Query(default=""),
    cmd: str       = Query(default="/bin/sh"),
):
    await websocket.accept()

    # WebSocket headers carry auth (same X-* headers the UI sets for HTTP calls)
    hdrs = websocket.headers
    ac = _api_client(
        x_auth_mode      = hdrs.get("x-auth-mode",      "local"),
        x_kubeconfig_b64 = hdrs.get("x-kubeconfig-b64", ""),
        x_k8s_token      = hdrs.get("x-k8s-token",      ""),
        x_k8s_server     = hdrs.get("x-k8s-server",     ""),
        x_k8s_context    = hdrs.get("x-k8s-context",    ""),
    )
    v1 = core_v1(ac)

    loop = asyncio.get_event_loop()
    try:
        resp = await loop.run_in_executor(
            None,
            lambda: k8s_stream(
                v1.connect_get_namespaced_pod_exec,
                name, namespace,
                command=[cmd],
                container=container or None,
                stderr=True, stdin=True, stdout=True, tty=True,
                _preload_content=False,
            ),
        )
    except Exception as e:
        logger.error("exec ws open %s/%s: %s", namespace, name, e)
        try:
            await websocket.send_text(json.dumps({"type": "error", "msg": str(e)}))
        except Exception:
            pass
        await websocket.close()
        return

    # Background thread: reads pod stdout/stderr, queues output for the coroutine
    out_q: queue.Queue = queue.Queue()

    def _pod_reader():
        try:
            while resp.is_open():
                resp.update(timeout=1)
                if resp.peek_stdout():
                    out_q.put(resp.read_stdout())
                if resp.peek_stderr():
                    out_q.put(resp.read_stderr())
        except Exception as e:
            logger.debug("pod reader ended: %s", e)
        finally:
            out_q.put(None)  # sentinel

    reader_thread = threading.Thread(target=_pod_reader, daemon=True,
                                     name=f"exec-reader-{namespace}/{name}")
    reader_thread.start()

    async def _dequeue():
        while True:
            item = await loop.run_in_executor(None, out_q.get)
            if item is None:
                break
            try:
                await websocket.send_text(item)
            except Exception:
                break

    dequeue_task = asyncio.create_task(_dequeue())

    try:
        while resp.is_open():
            try:
                msg = await asyncio.wait_for(websocket.receive_text(), timeout=0.2)
            except asyncio.TimeoutError:
                continue
            except WebSocketDisconnect:
                break
            try:
                data = json.loads(msg)
            except (json.JSONDecodeError, TypeError):
                resp.write_stdin(msg)
                continue
            if data.get("type") == "data":
                resp.write_stdin(data.get("data", ""))
            elif data.get("type") == "resize":
                resp.write_channel(4, json.dumps({
                    "Height": int(data.get("rows", 24)),
                    "Width":  int(data.get("cols", 80)),
                }))
    except Exception as e:
        logger.debug("exec ws read loop ended: %s", e)
    finally:
        dequeue_task.cancel()
        try:
            resp.close()
        except Exception:
            pass
        logger.info("exec ws closed: %s/%s", namespace, name)
