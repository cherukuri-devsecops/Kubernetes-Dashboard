"""Thin Prometheus HTTP API client."""
import logging
import os
from datetime import datetime, timedelta, timezone

import requests

logger = logging.getLogger(__name__)

PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://prometheus:9090").rstrip("/")


def _query(promql: str) -> list:
    try:
        r = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query",
            params={"query": promql},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        return data.get("data", {}).get("result", [])
    except Exception as e:
        logger.warning("Prometheus query failed (%s): %s", promql[:80], e)
        return []


def _query_range(promql: str, hours: int = 1, step: str = "60s") -> list:
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=hours)
    try:
        r = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query_range",
            params={
                "query": promql,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "step": step,
            },
            timeout=15,
        )
        r.raise_for_status()
        return r.json().get("data", {}).get("result", [])
    except Exception as e:
        logger.warning("Prometheus range query failed (%s): %s", promql[:80], e)
        return []


def cluster_cpu_usage() -> float:
    """Return cluster-wide CPU usage as a 0-100 percentage."""
    results = _query('sum(rate(container_cpu_usage_seconds_total{container!=""}[5m]))')
    if results:
        return round(float(results[0]["value"][1]) * 100, 1)
    return 0.0


def cluster_mem_usage_bytes() -> int:
    results = _query('sum(container_memory_working_set_bytes{container!=""})')
    if results:
        return int(float(results[0]["value"][1]))
    return 0


def node_cpu_usage() -> dict:
    """Return per-node CPU usage percentage keyed by node name."""
    out = {}
    for r in _query('sum by(node)(rate(node_cpu_seconds_total{mode!="idle"}[5m])) / sum by(node)(rate(node_cpu_seconds_total[5m]))'):
        node = r["metric"].get("node", "")
        out[node] = round(float(r["value"][1]) * 100, 1)
    return out


def node_mem_usage() -> dict:
    """Return per-node memory usage bytes keyed by node name."""
    out = {}
    for r in _query("node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes"):
        node = r["metric"].get("instance", "").split(":")[0]
        out[node] = int(float(r["value"][1]))
    return out


def pod_cpu_usage() -> dict:
    """Return per-pod CPU usage (rate, in cores) keyed by namespace/pod."""
    out = {}
    for r in _query('sum by(namespace,pod)(rate(container_cpu_usage_seconds_total{container!=""}[5m]))'):
        key = f"{r['metric'].get('namespace','')}/{r['metric'].get('pod','')}"
        out[key] = round(float(r["value"][1]), 4)
    return out


def cpu_over_time(hours: int = 1) -> list:
    """Return [(ts, pct), ...] for cluster CPU over time."""
    out = []
    for series in _query_range(
        'sum(rate(container_cpu_usage_seconds_total{container!=""}[5m])) * 100',
        hours=hours,
    ):
        out = [(int(ts), round(float(v), 1)) for ts, v in series.get("values", [])]
        break
    return out


def mem_over_time(hours: int = 1) -> list:
    out = []
    for series in _query_range(
        'sum(container_memory_working_set_bytes{container!=""})',
        hours=hours,
    ):
        out = [(int(ts), int(float(v))) for ts, v in series.get("values", [])]
        break
    return out


def namespace_cpu_usage() -> dict:
    """CPU usage percentage per namespace (5m rate)."""
    out = {}
    for r in _query('sum by(namespace)(rate(container_cpu_usage_seconds_total{container!=""}[5m]))'):
        ns = r["metric"].get("namespace", "")
        if ns:
            out[ns] = round(float(r["value"][1]) * 100, 2)
    return out


def namespace_mem_usage() -> dict:
    """Memory bytes per namespace."""
    out = {}
    for r in _query('sum by(namespace)(container_memory_working_set_bytes{container!=""})'):
        ns = r["metric"].get("namespace", "")
        if ns:
            out[ns] = int(float(r["value"][1]))
    return out


def pod_mem_usage() -> dict:
    """Memory bytes per namespace/pod."""
    out = {}
    for r in _query('sum by(namespace, pod)(container_memory_working_set_bytes{container!=""})'):
        ns  = r["metric"].get("namespace", "")
        pod = r["metric"].get("pod", "")
        if ns and pod:
            out[f"{ns}/{pod}"] = int(float(r["value"][1]))
    return out


def http_request_rate() -> list:
    """Per-handler request rate (reqs/sec, last 5m) from prometheus_fastapi_instrumentator."""
    return [
        {
            "handler": r["metric"].get("handler", ""),
            "method":  r["metric"].get("method", ""),
            "status":  r["metric"].get("status", r["metric"].get("status_code", "")),
            "rate":    round(float(r["value"][1]), 6),
        }
        for r in _query("rate(http_requests_total[5m])")
    ]


def http_error_rate() -> float:
    """Fraction of 4xx/5xx responses over total in last 5m, as a percentage."""
    # prometheus_fastapi_instrumentator uses 'status' label with values like '4xx','5xx'
    errors = _query('sum(rate(http_requests_total{status=~"[45]xx"}[5m]))')
    if not errors:
        errors = _query('sum(rate(http_requests_total{status_code=~"[45].."}[5m]))')
    total  = _query("sum(rate(http_requests_total[5m]))")
    e = float(errors[0]["value"][1]) if errors else 0.0
    t = float(total[0]["value"][1])  if total  else 0.0
    return round(e / t * 100, 2) if t > 0 else 0.0


def http_p95_latency() -> float:
    """P95 request latency in seconds (last 5m)."""
    results = _query(
        "histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))"
    )
    return round(float(results[0]["value"][1]), 6) if results else 0.0


def apdex_score(t: float = 0.5) -> float:
    """Apdex score (0–1). t = satisfied threshold in seconds (default 500 ms).

    Formula: (satisfied + tolerating/2) / total
      satisfied  = requests finishing in ≤ t seconds
      tolerating = requests finishing in ≤ 4t seconds (minus satisfied)
    """
    le_t   = _query(f'sum(rate(http_request_duration_seconds_bucket{{le="{t}"}}[5m]))')
    le_4t  = _query(f'sum(rate(http_request_duration_seconds_bucket{{le="{t * 4}"}}[5m]))')
    total  = _query('sum(rate(http_request_duration_seconds_count[5m]))')

    s  = float(le_t[0]["value"][1])  if le_t  else 0.0
    t4 = float(le_4t[0]["value"][1]) if le_4t else 0.0
    n  = float(total[0]["value"][1]) if total  else 0.0
    if n == 0:
        return 0.0
    # (satisfied + tolerating * 0.5) / total  ==  (le_t + (le_4t - le_t) * 0.5) / total
    return round((s + (t4 - s) * 0.5) / n, 3)


def top_transactions(hours: int = 1, limit: int = 30) -> list[dict]:
    """Return top endpoints sorted by average latency, merged with throughput and error rate."""
    window = f"{hours}h" if hours > 1 else "5m"

    avg_rows = _query(
        f'sum by(handler,method)(rate(http_request_duration_seconds_sum[{window}])) / '
        f'sum by(handler,method)(rate(http_request_duration_seconds_count[{window}]))'
    )
    p95_rows = _query(
        f'histogram_quantile(0.95, sum by(handler,method,le)'
        f'(rate(http_request_duration_seconds_bucket[{window}])))'
    )
    rps_rows = _query(
        f'sum by(handler,method)(rate(http_requests_total[{window}]))'
    )
    err_rows = _query(
        f'sum by(handler,method)(rate(http_requests_total{{status=~"[45].."}}[{window}]))'
    )
    # some instrumentators use status_code label instead of status
    if not err_rows:
        err_rows = _query(
            f'sum by(handler,method)(rate(http_requests_total{{status_code=~"[45].."}}[{window}]))'
        )

    def _key(m: dict) -> str:
        return f"{m.get('handler','')}\x00{m.get('method','')}"

    avg_map: dict[str, float] = {}
    for r in avg_rows:
        v = float(r["value"][1])
        if v == v:  # filter NaN
            avg_map[_key(r["metric"])] = round(v * 1000, 2)  # → ms

    p95_map: dict[str, float] = {}
    for r in p95_rows:
        v = float(r["value"][1])
        if v == v:
            p95_map[_key(r["metric"])] = round(v * 1000, 2)

    rps_map: dict[str, float] = {}
    for r in rps_rows:
        rps_map[_key(r["metric"])] = round(float(r["value"][1]), 6)

    err_map: dict[str, float] = {}
    for r in err_rows:
        err_map[_key(r["metric"])] = float(r["value"][1])

    keys = set(avg_map) | set(rps_map)
    rows = []
    for k in keys:
        handler, method = k.split("\x00", 1)
        if not handler:
            continue
        rps   = rps_map.get(k, 0.0)
        errs  = err_map.get(k, 0.0)
        rows.append({
            "handler":     handler,
            "method":      method,
            "avg_ms":      avg_map.get(k, 0.0),
            "p95_ms":      p95_map.get(k, 0.0),
            "rps":         round(rps, 6),
            "rpm":         round(rps * 60, 2),
            "error_rate":  round(errs / rps * 100, 2) if rps > 0 else 0.0,
        })

    rows.sort(key=lambda x: -x["avg_ms"])
    return rows[:limit]


def error_breakdown(hours: int = 1) -> list[dict]:
    """Per-endpoint error rows with status code, count rate, and error percentage."""
    window = f"{hours}h" if hours > 1 else "5m"

    err_rows = _query(
        f'sum by(handler,method,status)(rate(http_requests_total{{status=~"[45].."}}[{window}]))'
    )
    if not err_rows:
        err_rows = _query(
            f'sum by(handler,method,status_code)'
            f'(rate(http_requests_total{{status_code=~"[45].."}}[{window}]))'
        )

    total_rows = _query(
        f'sum by(handler,method)(rate(http_requests_total[{window}]))'
    )
    total_map: dict[str, float] = {}
    for r in total_rows:
        m = r["metric"]
        k = f"{m.get('handler','')}\x00{m.get('method','')}"
        total_map[k] = float(r["value"][1])

    rows = []
    for r in err_rows:
        m       = r["metric"]
        handler = m.get("handler", "")
        method  = m.get("method", "")
        status  = m.get("status", m.get("status_code", ""))
        if not handler:
            continue
        rate_val = float(r["value"][1])
        total    = total_map.get(f"{handler}\x00{method}", 0.0)
        rows.append({
            "handler":    handler,
            "method":     method,
            "status":     str(status),
            "rate":       round(rate_val, 6),
            "error_pct":  round(rate_val / total * 100, 2) if total > 0 else 0.0,
        })

    rows.sort(key=lambda x: -x["rate"])
    return rows


def _step_for_hours(hours: int) -> str:
    """Pick a Prometheus step that yields ~60 data points for the given hour range."""
    return f"{max(60, hours * 60)}s"


def rps_over_time(hours: int = 1) -> list[tuple[int, float]]:
    """[(epoch_ms, rps), …] — cluster-wide HTTP request rate."""
    step = _step_for_hours(hours)
    for series in _query_range("sum(rate(http_requests_total[5m]))", hours=hours, step=step):
        return [
            (int(ts) * 1000, round(float(v), 4))
            for ts, v in series.get("values", [])
            if v != "NaN"
        ]
    return []


def error_rate_over_time(hours: int = 1) -> list[tuple[int, float]]:
    """[(epoch_ms, pct), …] — HTTP error rate percentage."""
    step = _step_for_hours(hours)
    # try the 'status' label variant first, fall back to 'status_code'
    for variant in (
        'sum(rate(http_requests_total{status=~"[45].."}[5m])) / sum(rate(http_requests_total[5m])) * 100',
        'sum(rate(http_requests_total{status_code=~"[45].."}[5m])) / sum(rate(http_requests_total[5m])) * 100',
    ):
        for series in _query_range(variant, hours=hours, step=step):
            return [
                (int(ts) * 1000, round(float(v), 2))
                for ts, v in series.get("values", [])
                if v != "NaN"
            ]
    return []


def p95_over_time(hours: int = 1) -> list[tuple[int, float]]:
    """[(epoch_ms, ms), …] — P95 request latency in milliseconds."""
    step = _step_for_hours(hours)
    for series in _query_range(
        "histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m])) * 1000",
        hours=hours,
        step=step,
    ):
        return [
            (int(ts) * 1000, round(float(v), 1))
            for ts, v in series.get("values", [])
            if v != "NaN"
        ]
    return []


def apdex_over_time(hours: int = 1, t: float = 0.5) -> list[tuple[int, float]]:
    """[(epoch_ms, apdex), …] — Apdex score time-series."""
    step = _step_for_hours(hours)
    promql = (
        f'(sum(rate(http_request_duration_seconds_bucket{{le="{t}"}}[5m])) + '
        f'sum(rate(http_request_duration_seconds_bucket{{le="{t * 4}"}}[5m]))) / '
        f'(2 * sum(rate(http_request_duration_seconds_count[5m])))'
    )
    for series in _query_range(promql, hours=hours, step=step):
        return [
            (int(ts) * 1000, round(float(v), 3))
            for ts, v in series.get("values", [])
            if v != "NaN"
        ]
    return []
