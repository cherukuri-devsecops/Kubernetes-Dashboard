"""GET /api/pods — list and detail pods."""
import logging

from fastapi import APIRouter, Depends, Path, Query
from kubernetes.client import ApiClient

from ..k8s_client import _header_dep, core_v1, custom_api

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/pods", tags=["pods"])


def _container_state(cs) -> str:
    if cs.state.running:
        return "Running"
    if cs.state.waiting:
        return cs.state.waiting.reason or "Waiting"
    if cs.state.terminated:
        return cs.state.terminated.reason or "Terminated"
    return "Unknown"


def _pod_dict(p, pm_map: dict = None) -> dict:
    ns   = p.metadata.namespace
    name = p.metadata.name
    cs   = p.status.container_statuses or []
    ready_count = sum(1 for c in cs if c.ready)
    restarts    = sum(c.restart_count for c in cs)

    containers = [
        {
            "name":     c.name,
            "image":    c.image,
            "ready":    c.ready,
            "restarts": c.restart_count,
            "state":    _container_state(c),
        }
        for c in cs
    ]

    cpu_usage = mem_usage = None
    if pm_map:
        key = f"{ns}/{name}"
        usage = pm_map.get(key, {})
        cpu_usage = usage.get("cpu")
        mem_usage = usage.get("mem")

    return {
        "name":        name,
        "namespace":   ns,
        "phase":       p.status.phase or "Unknown",
        "node":        p.spec.node_name or "",
        "ip":          p.status.pod_ip or "",
        "host_ip":     p.status.host_ip or "",
        "ready":       f"{ready_count}/{len(cs)}",
        "restarts":    restarts,
        "containers":  containers,
        "labels":      p.metadata.labels or {},
        "created":     str(p.metadata.creation_timestamp),
        "cpu_usage":   cpu_usage,
        "mem_usage":   mem_usage,
    }


@router.get("")
def list_pods(
    namespace: str = Query(default=""),
    node: str     = Query(default=""),
    ac: ApiClient = Depends(_header_dep),
):
    core = core_v1(ac)
    cust = custom_api(ac)

    field_sel = f"spec.nodeName={node}" if node else ""
    if namespace:
        items = core.list_namespaced_pod(namespace, field_selector=field_sel or None).items
    else:
        items = core.list_pod_for_all_namespaces(field_selector=field_sel or None).items

    pm_map: dict = {}
    try:
        pm = cust.list_cluster_custom_object("metrics.k8s.io", "v1beta1", "pods")
        for item in pm.get("items", []):
            key = f"{item['metadata']['namespace']}/{item['metadata']['name']}"
            containers = item.get("containers", [])
            pm_map[key] = {
                "cpu": containers[0]["usage"]["cpu"] if containers else None,
                "mem": containers[0]["usage"]["memory"] if containers else None,
            }
    except Exception:
        pass

    return [_pod_dict(p, pm_map) for p in items]


@router.get("/{namespace}/{name}")
def get_pod(
    namespace: str = Path(...),
    name: str      = Path(...),
    ac: ApiClient  = Depends(_header_dep),
):
    core = core_v1(ac)
    p = core.read_namespaced_pod(name, namespace)
    cs = p.status.container_statuses or []

    init_cs = [
        {"name": c.name, "image": c.image, "ready": c.ready, "state": _container_state(c)}
        for c in (p.status.init_container_statuses or [])
    ]
    containers_full = [
        {
            "name":      c.name,
            "image":     c.image,
            "ready":     c.ready,
            "restarts":  c.restart_count,
            "state":     _container_state(c),
            "resources": {
                "requests": {
                    "cpu":    (p.spec.containers[i].resources.requests or {}).get("cpu") if p.spec.containers and i < len(p.spec.containers) else None,
                    "memory": (p.spec.containers[i].resources.requests or {}).get("memory") if p.spec.containers and i < len(p.spec.containers) else None,
                },
                "limits": {
                    "cpu":    (p.spec.containers[i].resources.limits or {}).get("cpu") if p.spec.containers and i < len(p.spec.containers) else None,
                    "memory": (p.spec.containers[i].resources.limits or {}).get("memory") if p.spec.containers and i < len(p.spec.containers) else None,
                },
            } if p.spec.containers else {},
        }
        for i, c in enumerate(cs)
    ]

    events_resp = core.list_namespaced_event(
        namespace,
        field_selector=f"involvedObject.name={name}",
    )
    events = [
        {
            "type":    e.type,
            "reason":  e.reason,
            "message": e.message,
            "count":   e.count,
            "ts":      str(e.last_timestamp),
        }
        for e in (events_resp.items or [])
    ]

    return {
        "name":            name,
        "namespace":       namespace,
        "phase":           p.status.phase or "Unknown",
        "node":            p.spec.node_name or "",
        "ip":              p.status.pod_ip or "",
        "host_ip":         p.status.host_ip or "",
        "labels":          p.metadata.labels or {},
        "annotations":     {k: v for k, v in (p.metadata.annotations or {}).items()
                            if "kubectl.kubernetes.io/last-applied" not in k},
        "containers":      containers_full,
        "init_containers": init_cs,
        "volumes":         [{"name": v.name} for v in (p.spec.volumes or [])],
        "events":          events,
        "created":         str(p.metadata.creation_timestamp),
        "service_account": p.spec.service_account_name or "",
        "restart_policy":  p.spec.restart_policy or "",
        "qos_class":       p.status.qos_class or "",
    }
