import concurrent.futures
import os
import time
from datetime import datetime, timezone

import requests as _req
from flask import Blueprint, jsonify

from ..config import BACKEND_SERVICE_URL, LOKI_URL

health_bp = Blueprint("health", __name__)

_TIMEOUT     = 4
_PROM_URL    = os.environ.get("PROMETHEUS_URL",  "http://prometheus:9090").rstrip("/")
_FLUENT_URL  = os.environ.get("FLUENT_BIT_URL",  "http://fluent-bit:2020")
_SQLITE_PATH = os.environ.get("SQLITE_PATH",     "/data/dashboard.db")


def _probe(label: str, url: str, ok_statuses=(200, 204)) -> dict:
    t0 = time.monotonic()
    try:
        r = _req.get(url, timeout=_TIMEOUT, allow_redirects=True)
        ms = round((time.monotonic() - t0) * 1000)
        up = r.status_code in ok_statuses
        return {"name": label, "status": "up" if up else "degraded",
                "latency_ms": ms, "code": r.status_code}
    except _req.exceptions.ConnectionError:
        return {"name": label, "status": "down",
                "latency_ms": round((time.monotonic() - t0) * 1000),
                "error": "Connection refused"}
    except _req.exceptions.Timeout:
        return {"name": label, "status": "down",
                "latency_ms": round((time.monotonic() - t0) * 1000),
                "error": f"Timeout after {_TIMEOUT}s"}
    except Exception as e:
        return {"name": label, "status": "down",
                "latency_ms": round((time.monotonic() - t0) * 1000),
                "error": str(e)[:120]}


def _check_sqlite() -> dict:
    t0 = time.monotonic()
    try:
        import sqlite3
        con = sqlite3.connect(_SQLITE_PATH, timeout=2)
        con.execute("SELECT 1").fetchone()
        con.close()
        return {"name": "SQLite", "status": "up",
                "latency_ms": round((time.monotonic() - t0) * 1000),
                "detail": _SQLITE_PATH}
    except Exception as e:
        return {"name": "SQLite", "status": "down",
                "latency_ms": round((time.monotonic() - t0) * 1000),
                "error": str(e)[:120]}


def _gather_status() -> dict:
    probes = {
        "Backend":    lambda: _probe("Backend",    f"{BACKEND_SERVICE_URL}/health"),
        "Loki":       lambda: _probe("Loki",       f"{LOKI_URL}/ready"),
        "Prometheus": lambda: _probe("Prometheus", f"{_PROM_URL}/-/healthy"),
        "Fluent Bit": lambda: _probe("Fluent Bit", f"{_FLUENT_URL}/api/v1/health"),
        "SQLite":     _check_sqlite,
    }
    results: dict[str, dict] = {
        "UI": {"name": "UI (Flask)", "status": "up", "latency_ms": 0},
    }
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(probes)) as pool:
        futs = {pool.submit(fn): key for key, fn in probes.items()}
        for fut in concurrent.futures.as_completed(futs):
            key = futs[fut]
            try:
                results[key] = fut.result()
            except Exception as e:
                results[key] = {"name": key, "status": "down", "error": str(e)[:120]}

    ordered  = ["UI", "Backend", "Loki", "Prometheus", "Fluent Bit", "SQLite"]
    services = [results[k] for k in ordered if k in results]
    up       = sum(1 for s in services if s["status"] == "up")
    down     = sum(1 for s in services if s["status"] == "down")
    overall  = "up" if down == 0 else "degraded" if up > 0 else "down"
    return {"overall": overall, "services": services,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")}


@health_bp.route("/health")
def health():
    return jsonify(_gather_status())
