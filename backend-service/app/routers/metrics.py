"""GET /api/metrics — cluster-wide and per-resource metrics from Prometheus."""
import logging

from fastapi import APIRouter, Query

import concurrent.futures as _cf

from ..prom_client import (
    cluster_cpu_usage, cluster_mem_usage_bytes,
    node_cpu_usage, node_mem_usage,
    pod_cpu_usage,
    cpu_over_time, mem_over_time,
    http_request_rate, http_error_rate, http_p95_latency,
    namespace_cpu_usage, namespace_mem_usage, pod_mem_usage,
    apdex_score, top_transactions, error_breakdown,
    rps_over_time, error_rate_over_time, p95_over_time, apdex_over_time,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


@router.get("")
def cluster_metrics():
    """Return current cluster-wide CPU and memory utilisation."""
    cpu_pct   = cluster_cpu_usage()
    mem_bytes = cluster_mem_usage_bytes()
    return {
        "cpu_pct":    cpu_pct,
        "mem_bytes":  mem_bytes,
    }


@router.get("/nodes")
def node_metrics():
    """Return per-node CPU and memory utilisation from Prometheus."""
    cpu = node_cpu_usage()
    mem = node_mem_usage()
    nodes = set(cpu) | set(mem)
    return [
        {"node": n, "cpu_pct": cpu.get(n, 0), "mem_bytes": mem.get(n, 0)}
        for n in sorted(nodes)
    ]


@router.get("/pods")
def pod_metrics(namespace: str = Query(default="")):
    """Return per-pod CPU usage (in cores) from Prometheus."""
    usage = pod_cpu_usage()
    if namespace:
        usage = {k: v for k, v in usage.items() if k.startswith(f"{namespace}/")}
    return [{"pod": k, "cpu_cores": v} for k, v in sorted(usage.items())]


@router.get("/apm/breakdown")
def apm_breakdown():
    """Per-namespace and per-pod CPU/memory from Prometheus for the APM breakdown view."""
    with _cf.ThreadPoolExecutor(max_workers=4) as pool:
        ns_cpu_f  = pool.submit(namespace_cpu_usage)
        ns_mem_f  = pool.submit(namespace_mem_usage)
        pod_cpu_f = pool.submit(pod_cpu_usage)
        pod_mem_f = pool.submit(pod_mem_usage)
        return {
            "namespace_cpu": ns_cpu_f.result(),
            "namespace_mem": ns_mem_f.result(),
            "pod_cpu":       pod_cpu_f.result(),
            "pod_mem":       pod_mem_f.result(),
        }


@router.get("/apm")
def apm_metrics():
    """Return HTTP golden signals + Apdex for the APM overview cards."""
    with _cf.ThreadPoolExecutor(max_workers=4) as pool:
        rr_f   = pool.submit(http_request_rate)
        er_f   = pool.submit(http_error_rate)
        p95_f  = pool.submit(http_p95_latency)
        apd_f  = pool.submit(apdex_score)
    return {
        "request_rate":   rr_f.result(),
        "error_rate_pct": er_f.result(),
        "p95_latency_s":  p95_f.result(),
        "apdex":          apd_f.result(),
    }


@router.get("/apm/transactions")
def apm_transactions(
    hours: int = Query(default=1, ge=1, le=168),
    limit: int = Query(default=30, ge=1, le=100),
):
    """Top HTTP endpoints ranked by average latency, with throughput and error rate."""
    return {"transactions": top_transactions(hours=hours, limit=limit)}


@router.get("/apm/errors")
def apm_errors(hours: int = Query(default=1, ge=1, le=168)):
    """Per-endpoint HTTP error breakdown (4xx/5xx) with rates and percentages."""
    return {"errors": error_breakdown(hours=hours)}


@router.get("/apm/timeseries")
def apm_timeseries(hours: int = Query(default=1, ge=1, le=168)):
    """Time-series data for all four APM golden signals (rps, error %, p95 ms, apdex)."""
    with _cf.ThreadPoolExecutor(max_workers=4) as pool:
        rps_f  = pool.submit(rps_over_time,         hours)
        err_f  = pool.submit(error_rate_over_time,  hours)
        p95_f  = pool.submit(p95_over_time,         hours)
        apd_f  = pool.submit(apdex_over_time,       hours)
    return {
        "rps":        rps_f.result(),
        "error_rate": err_f.result(),
        "p95_ms":     p95_f.result(),
        "apdex":      apd_f.result(),
    }


@router.get("/history")
def metrics_history(hours: int = Query(default=1, ge=1, le=72)):
    """Return cluster CPU and memory time-series for charting."""
    cpu_series = cpu_over_time(hours=hours)
    mem_series = mem_over_time(hours=hours)
    return {
        "hours":      hours,
        "cpu_series": [{"ts": ts, "pct": v} for ts, v in cpu_series],
        "mem_series": [{"ts": ts, "bytes": v} for ts, v in mem_series],
    }
