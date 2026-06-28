"""GET /api/logs — query pod logs from Loki or directly from K8s."""
import logging

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from kubernetes.client import ApiClient

from ..k8s_client import _header_dep, core_v1
from ..loki_client import pod_logs, query_range

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("")
def get_logs(
    namespace: str  = Query(..., description="Pod namespace"),
    pod: str        = Query(..., description="Pod name"),
    container: str  = Query(default="", description="Container name"),
    lines: int      = Query(default=100, ge=1, le=5000),
    hours: int      = Query(default=1, ge=1, le=168),
    source: str     = Query(default="auto", description="loki | k8s | auto"),
    ac: ApiClient   = Depends(_header_dep),
):
    """
    Return log lines for a pod. Tries Loki first (when source=auto or loki),
    falls back to K8s API streaming.
    """
    entries = []

    if source in ("auto", "loki"):
        entries = pod_logs(namespace, pod, container=container, hours=hours, limit=lines)

    if not entries and source in ("auto", "k8s"):
        try:
            core = core_v1(ac)
            kwargs = dict(namespace=namespace, tail_lines=lines, timestamps=True)
            if container:
                kwargs["container"] = container
            raw = core.read_namespaced_pod_log(pod, **kwargs) or ""
            entries = [{"ts": 0, "labels": {}, "line": line} for line in raw.splitlines()]
        except Exception as e:
            logger.warning("K8s log fetch failed %s/%s: %s", namespace, pod, e)

    return {"pod": pod, "namespace": namespace, "entries": entries}


@router.get("/search")
def search_logs(
    q: str          = Query(..., description="LogQL query string"),
    hours: int      = Query(default=1, ge=1, le=168),
    limit: int      = Query(default=200, ge=1, le=2000),
):
    """Run an arbitrary LogQL query against Loki."""
    entries = query_range(q, hours=hours, limit=limit)
    return {"query": q, "entries": entries}
