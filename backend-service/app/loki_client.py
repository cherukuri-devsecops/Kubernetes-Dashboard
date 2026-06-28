"""Loki client for the backend service — query and push."""
import json
import logging
import os
import time

import requests

logger = logging.getLogger(__name__)

LOKI_URL = os.environ.get("LOKI_URL", "http://loki:3100").rstrip("/")


def loki_ready() -> bool:
    return bool(LOKI_URL)


# ── Push ─────────────────────────────────────────────────────────────────────

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
    ts = ts_ns if ts_ns is not None else int(time.time() * 1e9)
    push_entries(job, labels, [(ts, json.dumps(data, default=str))])


def query_range(logql: str, hours: int = 1, limit: int = 500) -> list:
    if not LOKI_URL:
        return []
    end_ns = int(time.time() * 1e9)
    start_ns = end_ns - hours * 3600 * int(1e9)
    try:
        r = requests.get(
            f"{LOKI_URL}/loki/api/v1/query_range",
            params={"query": logql, "start": start_ns, "end": end_ns, "limit": limit},
            timeout=15,
        )
        r.raise_for_status()
        results = r.json().get("data", {}).get("result", [])
        entries = []
        for stream in results:
            labels = stream.get("stream", {})
            for ts_str, line in stream.get("values", []):
                entries.append({"ts": int(ts_str), "labels": labels, "line": line})
        entries.sort(key=lambda e: e["ts"], reverse=True)
        return entries
    except Exception as e:
        logger.warning("Loki query_range failed (%s): %s", logql[:80], e)
        return []


def pod_logs(namespace: str, pod: str, container: str = "", hours: int = 1, limit: int = 200) -> list:
    parts = [f'namespace="{namespace}"', f'pod="{pod}"']
    if container:
        parts.append(f'container="{container}"')
    logql = '{' + ",".join(parts) + '}'
    return query_range(logql, hours=hours, limit=limit)
