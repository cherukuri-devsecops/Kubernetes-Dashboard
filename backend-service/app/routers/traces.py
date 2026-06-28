"""GET /api/traces — distributed trace queries (Jaeger / Tempo)."""
import logging
import os

import requests
from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/traces", tags=["traces"])

JAEGER_URL = os.environ.get("JAEGER_URL", "").rstrip("/")
TEMPO_URL  = os.environ.get("TEMPO_URL",  "").rstrip("/")


def _backend() -> tuple[str, str]:
    """Return (backend_type, base_url) or raise."""
    if JAEGER_URL:
        return "jaeger", JAEGER_URL
    if TEMPO_URL:
        return "tempo", TEMPO_URL
    raise HTTPException(status_code=503, detail="No trace backend configured. Set JAEGER_URL or TEMPO_URL.")


@router.get("")
def list_services():
    """List services that have traces in the backend."""
    backend, url = _backend()
    if backend == "jaeger":
        try:
            r = requests.get(f"{url}/api/services", timeout=10)
            r.raise_for_status()
            return {"backend": "jaeger", "services": r.json().get("data", [])}
        except Exception as e:
            raise HTTPException(status_code=502, detail=str(e))
    # Tempo doesn't have a services endpoint in the same way
    return {"backend": "tempo", "services": [], "note": "Use /api/traces/search to query Tempo"}


@router.get("/search")
def search_traces(
    service:   str = Query(default="", description="Service name"),
    operation: str = Query(default="", description="Operation name"),
    limit:     int = Query(default=20, ge=1, le=200),
    hours:     int = Query(default=1, ge=1, le=168),
):
    """Search traces by service and/or operation."""
    backend, url = _backend()
    if backend == "jaeger":
        params: dict = {"limit": limit, "lookback": f"{hours}h"}
        if service:
            params["service"] = service
        if operation:
            params["operation"] = operation
        try:
            r = requests.get(f"{url}/api/traces", params=params, timeout=15)
            r.raise_for_status()
            return {"backend": "jaeger", "traces": r.json().get("data", [])}
        except Exception as e:
            raise HTTPException(status_code=502, detail=str(e))

    # Tempo — use TraceQL or tag search
    try:
        import time
        end_ns   = int(time.time() * 1e9)
        start_ns = end_ns - hours * 3600 * int(1e9)
        params = {"start": start_ns, "end": end_ns, "limit": limit}
        if service:
            params["tags"] = f"service.name={service}"
        r = requests.get(f"{url}/api/search", params=params, timeout=15)
        r.raise_for_status()
        return {"backend": "tempo", "traces": r.json().get("traces", [])}
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/{trace_id}")
def get_trace(trace_id: str):
    """Fetch a single trace by ID."""
    backend, url = _backend()
    if backend == "jaeger":
        try:
            r = requests.get(f"{url}/api/traces/{trace_id}", timeout=10)
            r.raise_for_status()
            return {"backend": "jaeger", "trace": r.json().get("data", [])}
        except Exception as e:
            raise HTTPException(status_code=502, detail=str(e))
    try:
        r = requests.get(f"{url}/api/traces/{trace_id}", timeout=10)
        r.raise_for_status()
        return {"backend": "tempo", "trace": r.json()}
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
