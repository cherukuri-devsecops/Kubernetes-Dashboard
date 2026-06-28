"""
Background pollers — push K8s events, metrics, pod lifecycle and log samples to Loki.

Runs as asyncio tasks started from the FastAPI lifespan. Uses the backend's own
K8s credentials (local kubeconfig or in-cluster). No per-user session needed.
"""
import asyncio
import json
import logging
import os
import re
import time

from kubernetes import client, config

from .loki_client import loki_ready, push_entries
from .utils import parse_cpu as _parse_cpu, parse_mem as _parse_mem

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

POLLER_ENABLED        = os.environ.get("DB_POLLER_ENABLED", "1") == "1"
CLUSTER_SCOPE         = os.environ.get("CLUSTER_SCOPE", "local")
EVENT_POLL_INTERVAL   = int(os.environ.get("EVENT_POLL_INTERVAL",   "30"))
METRIC_POLL_INTERVAL  = int(os.environ.get("METRIC_POLL_INTERVAL",  "60"))
LIFECYCLE_POLL_INTERVAL = int(os.environ.get("LIFECYCLE_POLL_INTERVAL", "20"))
LOG_POLL_INTERVAL     = int(os.environ.get("LOG_POLL_INTERVAL",     "60"))
LOG_ARCHIVE_TAIL      = int(os.environ.get("LOG_ARCHIVE_TAIL",      "50"))
LOG_ARCHIVE_MAX_PODS  = int(os.environ.get("LOG_ARCHIVE_MAX_PODS",  "50"))

_LOG_LINE_RE = re.compile(r"^(?P<ts>\S+)\s+(?P<rest>.*)$")

# ── K8s client (server-level, not per-user) ───────────────────────────────────

def _build_client():
    try:
        c = client.Configuration()
        config.load_kube_config(client_configuration=c)
        return client.ApiClient(c)
    except Exception:
        config.load_incluster_config()
        return client.ApiClient()


def _apis():
    ac = _build_client()
    return {
        "core":   client.CoreV1Api(ac),
        "custom": client.CustomObjectsApi(ac),
    }


# ── Poll functions (sync — run via run_in_executor) ──────────────────────────

_restart_baseline: dict = {}


def _poll_events(apis: dict) -> None:
    try:
        evts = apis["core"].list_event_for_all_namespaces().items
    except Exception as e:
        logger.warning("event poller list failed: %s", e)
        return
    entries = []
    now_ns  = int(time.time() * 1e9)
    for e in evts:
        uid = e.metadata.uid
        if not uid:
            continue
        entries.append((now_ns, json.dumps({
            "uid":         uid,
            "ns":          e.metadata.namespace or "",
            "type":        e.type or "",
            "reason":      e.reason or "",
            "kind":        (e.involved_object.kind or "") if e.involved_object else "",
            "object_name": (e.involved_object.name or "") if e.involved_object else "",
            "message":     (e.message or "")[:4000],
            "count":       e.count or 0,
            "first_seen":  str(e.first_timestamp or e.event_time or ""),
            "last_seen":   str(e.last_timestamp  or e.event_time or ""),
        }, default=str)))
    if entries:
        push_entries("k8s-events", {"cluster": CLUSTER_SCOPE}, entries)
        logger.debug("event poller: pushed %d entries", len(entries))


def _poll_metrics(apis: dict) -> None:
    now_ns  = int(time.time() * 1e9)
    entries = []
    try:
        nm = apis["custom"].list_cluster_custom_object(
            "metrics.k8s.io", "v1beta1", "nodes")
        for item in nm.get("items", []):
            u = item.get("usage", {})
            entries.append((now_ns, json.dumps({
                "kind":    "node",
                "name":    item["metadata"]["name"],
                "ns":      "",
                "cpu_m":   round(_parse_cpu(u.get("cpu", "0"))),
                "mem_mib": round(_parse_mem(u.get("memory", "0")) / 1024**2),
            })))
    except Exception:
        pass
    try:
        pm = apis["custom"].list_cluster_custom_object(
            "metrics.k8s.io", "v1beta1", "pods")
        for item in pm.get("items", []):
            ctrs = item.get("containers", [])
            cpu  = round(sum(_parse_cpu(c["usage"]["cpu"])   for c in ctrs))
            mem  = round(sum(_parse_mem(c["usage"]["memory"]) for c in ctrs) / 1024**2)
            entries.append((now_ns, json.dumps({
                "kind":    "pod",
                "name":    item["metadata"]["name"],
                "ns":      item["metadata"]["namespace"],
                "cpu_m":   cpu,
                "mem_mib": mem,
            })))
    except Exception:
        pass
    if entries:
        push_entries("k8s-metrics", {"cluster": CLUSTER_SCOPE}, entries)
        logger.debug("metric poller: pushed %d samples", len(entries))


def _poll_lifecycle(apis: dict) -> None:
    try:
        pods = apis["core"].list_pod_for_all_namespaces().items
    except Exception as e:
        logger.warning("lifecycle poller list failed: %s", e)
        return
    entries = []
    now_ns  = int(time.time() * 1e9)
    for p in pods:
        ns   = p.metadata.namespace or ""
        name = p.metadata.name
        for cs in (p.status.container_statuses or []):
            key = (ns, name, cs.name)
            prior = _restart_baseline.get(key)
            _restart_baseline[key] = cs.restart_count
            if prior is None or cs.restart_count <= prior:
                continue
            last     = cs.last_state.terminated if cs.last_state else None
            reason   = (last.reason if last else "") or ""
            ev_type  = ("oom" if reason == "OOMKilled" else
                        "crash" if reason in ("Error", "ContainerCannotRun") else
                        "terminate" if reason == "Completed" else "restart")
            entries.append((now_ns, json.dumps({
                "ns":            ns,
                "pod_name":      name,
                "container":     cs.name,
                "event_type":    ev_type,
                "reason":        reason,
                "exit_code":     last.exit_code if last else None,
                "restart_count": cs.restart_count,
                "message":       ((last.message or "") if last else "")[:2000],
            }, default=str)))
    if entries:
        push_entries("pod-lifecycle", {"cluster": CLUSTER_SCOPE}, entries)
        logger.debug("lifecycle poller: pushed %d events", len(entries))


_log_cursor: dict = {}


def _classify_line(line: str) -> str | None:
    lo = line.lower()
    if any(x in lo for x in ("error", "fatal", "critical", "exception", "panic")):
        return "error"
    if "warn" in lo:
        return "warn"
    if "info" in lo:
        return "info"
    return None


def _poll_logs(apis: dict) -> None:
    try:
        pods = [p for p in apis["core"].list_pod_for_all_namespaces().items
                if p.status.phase == "Running"][:LOG_ARCHIVE_MAX_PODS]
    except Exception as e:
        logger.warning("log poller list failed: %s", e)
        return
    for p in pods:
        ns   = p.metadata.namespace or ""
        name = p.metadata.name
        for c in (p.spec.containers or []):
            key    = (ns, name, c.name)
            cursor = _log_cursor.get(key, "")
            try:
                text = apis["core"].read_namespaced_pod_log(
                    name=name, namespace=ns, container=c.name,
                    tail_lines=LOG_ARCHIVE_TAIL, timestamps=True,
                    _request_timeout=5)
            except Exception:
                continue
            entries    = []
            new_cursor = cursor
            for line in (text or "").splitlines():
                if not line:
                    continue
                m = _LOG_LINE_RE.match(line)
                if not m:
                    continue
                ts_str = m.group("ts")
                rest   = m.group("rest")
                if cursor and ts_str <= cursor:
                    continue
                sev = _classify_line(rest)
                if not sev:
                    continue
                entries.append((int(time.time() * 1e9), json.dumps({
                    "ns":        ns,
                    "pod_name":  name,
                    "container": c.name,
                    "severity":  sev,
                    "line":      rest[:4000],
                })))
                if ts_str > new_cursor:
                    new_cursor = ts_str
            if entries:
                push_entries("pod-logs", {"cluster": CLUSTER_SCOPE}, entries)
            if new_cursor != cursor:
                _log_cursor[key] = new_cursor


# ── Async driver ──────────────────────────────────────────────────────────────

async def _run_in_thread(fn, *args):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, fn, *args)


async def start_pollers():
    if not POLLER_ENABLED or not loki_ready():
        logger.info("pollers disabled (POLLER_ENABLED=%s, loki_ready=%s)",
                    POLLER_ENABLED, loki_ready())
        return

    logger.info("pollers starting (cluster_scope=%s)", CLUSTER_SCOPE)

    try:
        apis = await _run_in_thread(_apis)
    except Exception as e:
        logger.error("pollers: cannot build K8s client, polling disabled: %s", e)
        return

    last: dict = {"event": 0, "metric": 0, "lifecycle": 0, "log": 0}

    while True:
        now = time.time()
        try:
            if now - last["event"]     >= EVENT_POLL_INTERVAL:
                await _run_in_thread(_poll_events,    apis)
                last["event"] = now
            if now - last["metric"]    >= METRIC_POLL_INTERVAL:
                await _run_in_thread(_poll_metrics,   apis)
                last["metric"] = now
            if now - last["lifecycle"] >= LIFECYCLE_POLL_INTERVAL:
                await _run_in_thread(_poll_lifecycle, apis)
                last["lifecycle"] = now
            if now - last["log"]       >= LOG_POLL_INTERVAL:
                await _run_in_thread(_poll_logs,      apis)
                last["log"] = now
        except Exception as e:
            logger.warning("poller iteration error: %s", e)

        await asyncio.sleep(5)
