"""GET /api/nodes — list and detail nodes."""
import logging

from fastapi import APIRouter, Depends, Path
from kubernetes.client import ApiClient

from ..k8s_client import _header_dep, core_v1, custom_api
from ..prom_client import node_cpu_usage, node_mem_usage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/nodes", tags=["nodes"])


def _parse_cpu(val: str) -> int:
    """Return millicores."""
    val = (val or "0").strip()
    if val.endswith("m"):
        return int(val[:-1])
    return int(float(val) * 1000)


def _parse_mem(val: str) -> int:
    """Return bytes."""
    val = (val or "0").strip()
    for suffix, mult in [("Ki", 1024), ("Mi", 1024**2), ("Gi", 1024**3), ("Ti", 1024**4)]:
        if val.endswith(suffix):
            return int(val[:-len(suffix)]) * mult
    return int(val)


def _node_ready(node) -> bool:
    for c in (node.status.conditions or []):
        if c.type == "Ready":
            return c.status == "True"
    return False


def _node_roles(node) -> str:
    labels = node.metadata.labels or {}
    roles = [k.split("/")[1] for k in labels if k.startswith("node-role.kubernetes.io/")]
    return ",".join(roles) if roles else "worker"


@router.get("")
def list_nodes(ac: ApiClient = Depends(_header_dep)):
    core = core_v1(ac)
    cust = custom_api(ac)
    nodes = core.list_node().items

    prom_cpu = {}
    prom_mem = {}
    try:
        prom_cpu = node_cpu_usage()
        prom_mem = node_mem_usage()
    except Exception:
        pass

    nm_by_name: dict = {}
    try:
        nm = cust.list_cluster_custom_object("metrics.k8s.io", "v1beta1", "nodes")
        nm_by_name = {item["metadata"]["name"]: item for item in nm.get("items", [])}
    except Exception:
        pass

    result = []
    for n in nodes:
        name = n.metadata.name
        alloc = n.status.allocatable or {}
        cap   = n.status.capacity or {}
        cpu_alloc_m = _parse_cpu(alloc.get("cpu", "0"))
        mem_alloc_b = _parse_mem(alloc.get("memory", "0"))

        nm_item = nm_by_name.get(name, {})
        cpu_used_m = _parse_cpu((nm_item.get("usage") or {}).get("cpu", "0"))
        mem_used_b = _parse_mem((nm_item.get("usage") or {}).get("memory", "0"))
        cpu_pct = round(cpu_used_m / cpu_alloc_m * 100) if cpu_alloc_m else 0
        mem_pct = round(mem_used_b / mem_alloc_b * 100) if mem_alloc_b else 0

        # Prefer Prometheus data if available
        if name in prom_cpu:
            cpu_pct = prom_cpu[name]
        if name in prom_mem and mem_alloc_b:
            mem_pct = round(prom_mem[name] / mem_alloc_b * 100)

        result.append({
            "name": name,
            "ready": _node_ready(n),
            "roles": _node_roles(n),
            "version": (n.status.node_info.kubelet_version if n.status.node_info else ""),
            "os": (n.status.node_info.os_image if n.status.node_info else ""),
            "arch": (n.status.node_info.architecture if n.status.node_info else ""),
            "cpu_allocatable": alloc.get("cpu", ""),
            "mem_allocatable": alloc.get("memory", ""),
            "cpu_capacity": cap.get("cpu", ""),
            "mem_capacity": cap.get("memory", ""),
            "cpu_pct": cpu_pct,
            "mem_pct": mem_pct,
            "labels": n.metadata.labels or {},
            "taints": [{"key": t.key, "effect": t.effect} for t in (n.spec.taints or [])],
            "created": str(n.metadata.creation_timestamp),
            "unschedulable": bool(n.spec.unschedulable),
        })
    return result


@router.get("/{name}")
def get_node(name: str = Path(...), ac: ApiClient = Depends(_header_dep)):
    core = core_v1(ac)
    n = core.read_node(name)
    pods = core.list_pod_for_all_namespaces(field_selector=f"spec.nodeName={name}").items

    conditions = [
        {"type": c.type, "status": c.status, "message": c.message or ""}
        for c in (n.status.conditions or [])
    ]
    addresses = [{"type": a.type, "address": a.address} for a in (n.status.addresses or [])]

    return {
        "name": name,
        "ready": _node_ready(n),
        "roles": _node_roles(n),
        "labels": n.metadata.labels or {},
        "annotations": {k: v for k, v in (n.metadata.annotations or {}).items()
                        if "kubectl.kubernetes.io/last-applied" not in k},
        "conditions": conditions,
        "addresses": addresses,
        "node_info": {
            "kubelet_version":   n.status.node_info.kubelet_version if n.status.node_info else "",
            "os_image":          n.status.node_info.os_image if n.status.node_info else "",
            "container_runtime": n.status.node_info.container_runtime_version if n.status.node_info else "",
            "architecture":      n.status.node_info.architecture if n.status.node_info else "",
        },
        "allocatable": n.status.allocatable or {},
        "capacity":    n.status.capacity or {},
        "taints":      [{"key": t.key, "effect": t.effect, "value": t.value or ""} for t in (n.spec.taints or [])],
        "unschedulable": bool(n.spec.unschedulable),
        "pod_count":   len(pods),
        "created":     str(n.metadata.creation_timestamp),
    }
