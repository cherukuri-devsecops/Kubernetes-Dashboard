"""
Loki client:
  - push_entry / push_entries  → direct HTTP to Loki  (used by audit)
  - query_range                → proxied via backend-service /api/logs/search
  - label_values               → direct HTTP to Loki  (lightweight metadata call)
"""
import json
import logging
import time
from datetime import datetime, timezone

import requests

from .config import LOKI_URL, BACKEND_SERVICE_URL

logger = logging.getLogger(__name__)


def loki_ready() -> bool:
    return bool(LOKI_URL)


# ── Direct push (audit) ──────────────────────────────────────────────────────

def push_entries(job: str, labels: dict, entries: list):
    """Push [(ts_ns: int, line: str), ...] to a Loki stream."""
    if not LOKI_URL or not entries:
        return
    payload = {
        "streams": [{
            "stream": {"job": job, **labels},
            "values": [[str(ts), line] for ts, line in entries],
        }]
    }
    try:
        r = requests.post(f"{LOKI_URL}/loki/api/v1/push", json=payload, timeout=5)
        if r.status_code not in (200, 204):
            logger.warning("Loki push failed (%s): %s", r.status_code, r.text[:200])
    except Exception as e:
        logger.warning("Loki push error: %s", e)


def push_entry(job: str, labels: dict, data: dict, ts_ns: int = None):
    """Push a single JSON entry to Loki."""
    if not LOKI_URL:
        return
    ts = ts_ns if ts_ns is not None else int(time.time() * 1e9)
    push_entries(job, labels, [(ts, json.dumps(data, default=str))])


# ── Query via backend-service (avoids duplicate Loki client logic) ────────────

def query_range(logql: str, hours: int = 24, limit: int = 500) -> list:
    """
    Query Loki via the backend-service /api/logs/search endpoint.
    Returns list of dicts — each is the parsed JSON log line with '_ts' added.
    Falls back to direct Loki query if the backend is unreachable.
    """
    try:
        url = BACKEND_SERVICE_URL.rstrip("/") + "/api/logs/search"
        r = requests.get(url, params={"q": logql, "hours": hours, "limit": limit}, timeout=15)
        r.raise_for_status()
        rows = []
        for e in r.json().get("entries", []):
            line = e.get("line", "")
            try:
                d = json.loads(line)
            except (json.JSONDecodeError, TypeError):
                d = {"line": line}
            if "ts" not in d:
                ts_ns = e.get("ts", 0)
                d["ts"] = datetime.fromtimestamp(ts_ns / 1e9, tz=timezone.utc) if ts_ns else None
            rows.append(d)
        return rows
    except Exception as be:
        logger.warning("backend loki query failed, falling back to direct: %s", be)
        return _query_range_direct(logql, hours, limit)


def _query_range_direct(logql: str, hours: int, limit: int) -> list:
    """Direct Loki query — fallback only."""
    if not LOKI_URL:
        return []
    end_ns   = int(time.time() * 1e9)
    start_ns = end_ns - int(hours * 3600 * 1e9)
    try:
        r = requests.get(
            f"{LOKI_URL}/loki/api/v1/query_range",
            params={"query": logql, "start": start_ns, "end": end_ns,
                    "limit": limit, "direction": "backward"},
            timeout=10,
        )
        if r.status_code != 200:
            return []
        rows = []
        for stream in r.json().get("data", {}).get("result", []):
            for ts_ns_str, line in stream.get("values", []):
                try:
                    d = json.loads(line)
                    if "ts" not in d:
                        d["ts"] = datetime.fromtimestamp(int(ts_ns_str) / 1e9, tz=timezone.utc)
                    rows.append(d)
                except Exception:
                    pass
        return rows
    except Exception as e:
        logger.warning("Loki direct query error: %s", e)
        return []


def label_values(label: str, match: str = None) -> list:
    """Fetch distinct label values directly from Loki (lightweight metadata)."""
    if not LOKI_URL:
        return []
    try:
        r = requests.get(
            f"{LOKI_URL}/loki/api/v1/label/{label}/values",
            params={"query": match} if match else {},
            timeout=5,
        )
        if r.status_code == 200:
            return r.json().get("data", [])
    except Exception as e:
        logger.warning("Loki label values error: %s", e)
    return []
