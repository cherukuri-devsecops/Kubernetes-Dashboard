import concurrent.futures as _cf
from flask import Blueprint, render_template, request, session, redirect, url_for
from ..backend_client import (
    apm_metrics, apm_breakdown_metrics, apm_traces, apm_trace_detail,
    apm_transactions, apm_errors, apm_timeseries,
    raw_pods, raw_deployments, raw_namespaces,
)

apm_bp = Blueprint("apm", __name__)


def _safe(fn, *args, default=None, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception:
        return default


def _build_namespace_list(pods, breakdown, all_namespaces=None):
    ns_data = {}

    # Seed from the full namespace list so empty namespaces always appear
    for ns_obj in (all_namespaces or []):
        ns = (ns_obj.get("metadata") or {}).get("name", "")
        if ns and ns not in ns_data:
            ns_data[ns] = {"name": ns, "total": 0, "running": 0, "failed": 0,
                           "pending": 0, "cpu_pct": 0.0, "mem_b": 0,
                           "_cpu_m_agg": 0, "_mem_b_agg": 0}

    prom_ns_cpu  = breakdown.get("namespace_cpu", {})
    prom_ns_mem  = breakdown.get("namespace_mem", {})
    prom_pod_cpu = breakdown.get("pod_cpu", {})
    prom_pod_mem = breakdown.get("pod_mem", {})

    for pod in pods:
        meta     = pod.get("metadata", {})
        status   = pod.get("status", {})
        ns       = meta.get("namespace", "")
        pod_name = meta.get("name", "")
        if not ns:
            continue
        if ns not in ns_data:
            ns_data[ns] = {"name": ns, "total": 0, "running": 0, "failed": 0,
                           "pending": 0, "cpu_pct": 0.0, "mem_b": 0,
                           "_cpu_m_agg": 0, "_mem_b_agg": 0}
        ns_data[ns]["total"] += 1
        phase = status.get("phase", "")
        if phase == "Running":
            ns_data[ns]["running"] += 1
        elif phase == "Failed":
            ns_data[ns]["failed"] += 1
        elif phase == "Pending":
            ns_data[ns]["pending"] += 1

        # Accumulate per-pod metrics as fallback when Prometheus/cAdvisor is unavailable
        pk  = f"{ns}/{pod_name}"
        ms  = pod.get("_metrics", {})
        cpu_m = int(prom_pod_cpu.get(pk, 0) * 1000) or ms.get("cpu_m", 0)
        mem_b = prom_pod_mem.get(pk, 0) or ms.get("mem_b", 0)
        ns_data[ns]["_cpu_m_agg"] += cpu_m
        ns_data[ns]["_mem_b_agg"] += mem_b

    for ns, d in ns_data.items():
        # Prometheus namespace-level data preferred; fall back to aggregated pod metrics
        if prom_ns_cpu.get(ns):
            d["cpu_pct"] = prom_ns_cpu[ns]
        elif d["_cpu_m_agg"]:
            # millicores → "% of 1 CPU" to match Prometheus representation
            d["cpu_pct"] = round(d["_cpu_m_agg"] / 10.0, 2)
        else:
            d["cpu_pct"] = 0.0

        if prom_ns_mem.get(ns):
            d["mem_b"] = prom_ns_mem[ns]
        else:
            d["mem_b"] = d["_mem_b_agg"]

    return sorted(ns_data.values(), key=lambda x: x["name"])


def _build_deployment_list(pods, deployments, breakdown):
    prom_pod_cpu = breakdown.get("pod_cpu", {})   # {ns/pod: cores (float)}
    prom_pod_mem = breakdown.get("pod_mem", {})   # {ns/pod: bytes}

    dep_map = {}
    for dep in deployments:
        meta   = dep.get("metadata", {})
        spec   = dep.get("spec", {})
        status = dep.get("status", {})
        ns, name = meta.get("namespace", ""), meta.get("name", "")
        dep_map[f"{ns}/{name}"] = {
            "name":      name,
            "namespace": ns,
            "desired":   spec.get("replicas") or 0,
            "ready":     status.get("ready_replicas") or 0,
            "available": status.get("available_replicas") or 0,
            "cpu_m":     0,
            "mem_b":     0,
            "pod_count": 0,
        }

    for pod in pods:
        meta    = pod.get("metadata", {})
        pod_ns  = meta.get("namespace", "")
        pod_name = meta.get("name", "")
        pk      = f"{pod_ns}/{pod_name}"

        # Pod → ReplicaSet → Deployment (strip RS hash from RS name)
        dep_name = ""
        for ref in (meta.get("owner_references") or []):
            if ref.get("kind") == "ReplicaSet":
                parts = ref.get("name", "").rsplit("-", 1)
                if len(parts) == 2:
                    dep_name = parts[0]
                break

        if not dep_name:
            continue

        key = f"{pod_ns}/{dep_name}"
        if key not in dep_map:
            dep_map[key] = {
                "name": dep_name, "namespace": pod_ns,
                "desired": 0, "ready": 0, "available": 0,
                "cpu_m": 0, "mem_b": 0, "pod_count": 0,
            }

        dep_map[key]["pod_count"] += 1
        ms_metrics = pod.get("_metrics", {})
        dep_map[key]["cpu_m"] += int(prom_pod_cpu.get(pk, 0) * 1000) or ms_metrics.get("cpu_m", 0)
        dep_map[key]["mem_b"] += prom_pod_mem.get(pk, 0) or ms_metrics.get("mem_b", 0)

    return sorted(dep_map.values(), key=lambda x: (x["namespace"], x["name"]))


def _build_pod_list(pods, breakdown):
    prom_pod_cpu = breakdown.get("pod_cpu", {})
    prom_pod_mem = breakdown.get("pod_mem", {})
    result = []
    for pod in pods:
        meta    = pod.get("metadata", {})
        status  = pod.get("status", {})
        spec    = pod.get("spec", {})
        pod_ns  = meta.get("namespace", "")
        pod_name = meta.get("name", "")
        pk      = f"{pod_ns}/{pod_name}"
        ms      = pod.get("_metrics", {})

        restarts = sum(
            (cs.get("restart_count") or 0)
            for cs in (status.get("container_statuses") or [])
        )

        result.append({
            "name":      pod_name,
            "namespace": pod_ns,
            "node":      spec.get("node_name", ""),
            "phase":     status.get("phase", "Unknown"),
            "cpu_m":     int(prom_pod_cpu.get(pk, 0) * 1000) or ms.get("cpu_m", 0),
            "mem_b":     prom_pod_mem.get(pk, 0) or ms.get("mem_b", 0),
            "restarts":  restarts,
            "created":   (meta.get("creation_timestamp") or "")[:19].replace("T", " "),
        })

    return sorted(result, key=lambda x: (x["namespace"], x["name"]))


@apm_bp.route("/apm")
def apm_overview():
    if not session.get("user"):
        return redirect(url_for("auth.login_page"))
    cluster_ok = bool(session.get("cluster_ok"))

    hours = int(request.args.get("hours", 1))
    tab   = request.args.get("tab", "overview")

    # Sequential calls avoid gevent + Flask context issues that cause
    # session to be inaccessible inside ThreadPoolExecutor workers.
    metrics      = _safe(apm_metrics,           default={})
    breakdown    = _safe(apm_breakdown_metrics, default={})
    traces       = _safe(apm_traces, "", hours, 50, default={})
    transactions = _safe(apm_transactions, hours, 30, default={})
    errors_data  = _safe(apm_errors,  hours, default={})
    timeseries   = _safe(apm_timeseries, hours, default={})
    pods         = _safe(raw_pods,              default=[])
    deployments  = _safe(raw_deployments,       default=[])
    namespaces   = _safe(raw_namespaces,        default=[])

    metrics      = metrics      if isinstance(metrics,      dict) else {}
    breakdown    = breakdown    if isinstance(breakdown,    dict) else {}
    traces       = traces       if isinstance(traces,       dict) else {}
    transactions = transactions if isinstance(transactions, dict) else {}
    errors_data  = errors_data  if isinstance(errors_data,  dict) else {}
    timeseries   = timeseries   if isinstance(timeseries,   dict) else {}
    pods         = pods         if isinstance(pods,         list) else []
    deployments  = deployments  if isinstance(deployments,  list) else []
    namespaces   = namespaces   if isinstance(namespaces,   list) else []

    ns_list  = _build_namespace_list(pods, breakdown, all_namespaces=namespaces)
    dep_list = _build_deployment_list(pods, deployments, breakdown)
    pod_list = _build_pod_list(pods, breakdown)

    namespaces_all = sorted({p["namespace"] for p in pod_list if p["namespace"]})

    return render_template("apm.html",
        metrics      = metrics,
        traces       = traces,
        transactions = transactions.get("transactions", []),
        errors       = errors_data.get("errors", []),
        timeseries   = timeseries,
        ns_list      = ns_list,
        dep_list     = dep_list,
        pod_list     = pod_list,
        namespaces   = namespaces_all,
        hours        = hours,
        tab          = tab,
        cluster_ok   = cluster_ok,
    )


@apm_bp.route("/apm/trace/<trace_id>")
def apm_trace(trace_id):
    if not session.get("user"):
        return redirect(url_for("auth.login_page"))
    trace = _safe(apm_trace_detail, trace_id, default={})
    return render_template("apm_trace.html", trace=trace, trace_id=trace_id)
