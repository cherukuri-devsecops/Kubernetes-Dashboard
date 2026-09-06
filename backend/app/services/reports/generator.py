"""Report generation from live cluster state.

Every report here is computed at request time from the Kubernetes API and
Prometheus — there is no stored catalog and nothing is precomputed, so a report
is always a snapshot of the cluster as it is when it is asked for.
"""

from datetime import datetime, timezone
from typing import Any, Callable, Awaitable

from app.config import Settings
from app.services.kubernetes import client as k8s_client
from app.services.prometheus import client as prom_client
from app.services.prometheus.client import PrometheusUnavailableError

GIB = 1024**3


class UnknownReportError(ValueError):
    """Raised when a report id does not match a known template."""


def _gib(value: float) -> float:
    return round(value / GIB, 2)


async def _cluster_health(settings: Settings) -> dict[str, Any]:
    nodes = await k8s_client.list_nodes(settings)
    pods = await k8s_client.list_pods(settings, None)
    info = await k8s_client.get_cluster_info(settings)

    # Node metrics are a best-effort overlay: the report is still worth producing
    # from the API alone if Prometheus is down.
    try:
        metrics = {item["name"]: item for item in await prom_client.node_usage(settings)}
    except PrometheusUnavailableError:
        metrics = {}

    pods_by_node: dict[str, int] = {}
    for pod in pods:
        if pod["node"]:
            pods_by_node[pod["node"]] = pods_by_node.get(pod["node"], 0) + 1

    rows = []
    for node in nodes:
        usage = metrics.get(node["name"], {})
        rows.append(
            {
                "node": node["name"],
                "status": node["status"],
                "roles": ", ".join(node["roles"]) or "worker",
                "kubeletVersion": node["kubeletVersion"] or "",
                "cpuPercent": usage.get("cpuPercent", ""),
                "memoryPercent": usage.get("memoryPercent", ""),
                "diskPercent": usage.get("diskPercent", ""),
                "podsScheduled": pods_by_node.get(node["name"], 0),
                "podCapacity": node["podCapacity"] or "",
            }
        )

    not_ready = sum(1 for node in nodes if node["status"] != "Ready")
    restarting = sum(1 for pod in pods if pod["restarts"] > 0)
    return {
        "columns": [
            {"key": "node", "label": "Node"},
            {"key": "status", "label": "Status"},
            {"key": "roles", "label": "Roles"},
            {"key": "kubeletVersion", "label": "Kubelet"},
            {"key": "cpuPercent", "label": "CPU %"},
            {"key": "memoryPercent", "label": "Memory %"},
            {"key": "diskPercent", "label": "Disk %"},
            {"key": "podsScheduled", "label": "Pods"},
            {"key": "podCapacity", "label": "Pod capacity"},
        ],
        "rows": rows,
        "summary": [
            {"label": "Kubernetes version", "value": info["gitVersion"]},
            {"label": "Nodes ready", "value": f"{info['readyNodeCount']} / {info['nodeCount']}"},
            {"label": "Nodes not ready", "value": not_ready},
            {"label": "Pods running", "value": sum(1 for pod in pods if pod["status"] == "Running")},
            {"label": "Pods with restarts", "value": restarting},
            {"label": "Namespaces", "value": info["namespaceCount"]},
        ],
    }


async def _resource_utilization(settings: Settings) -> dict[str, Any]:
    namespaces = await prom_client.namespace_usage(settings)
    cluster = await prom_client.cluster_usage(settings)
    pods = await k8s_client.list_pods(settings, None)

    pods_by_namespace: dict[str, int] = {}
    for pod in pods:
        pods_by_namespace[pod["namespace"]] = pods_by_namespace.get(pod["namespace"], 0) + 1

    rows = [
        {
            "namespace": item["namespace"],
            "cpuCores": round(item["cpuCores"], 4),
            "memoryGiB": _gib(item["memoryBytes"]),
            "networkRxKbps": round(item["networkRxBytesPerSec"] / 1024, 2),
            "networkTxKbps": round(item["networkTxBytesPerSec"] / 1024, 2),
            "pods": pods_by_namespace.get(item["namespace"], 0),
        }
        for item in namespaces
    ]
    rows.sort(key=lambda row: row["cpuCores"], reverse=True)

    cpu_percent = (
        round(cluster["cpuCores"] / cluster["cpuTotalCores"] * 100, 1) if cluster["cpuTotalCores"] else 0
    )
    memory_percent = (
        round(cluster["memoryBytes"] / cluster["memoryTotalBytes"] * 100, 1)
        if cluster["memoryTotalBytes"]
        else 0
    )
    return {
        "columns": [
            {"key": "namespace", "label": "Namespace"},
            {"key": "cpuCores", "label": "CPU cores"},
            {"key": "memoryGiB", "label": "Memory GiB"},
            {"key": "networkRxKbps", "label": "Net RX KB/s"},
            {"key": "networkTxKbps", "label": "Net TX KB/s"},
            {"key": "pods", "label": "Pods"},
        ],
        "rows": rows,
        "summary": [
            {"label": "Cluster CPU", "value": f"{cluster['cpuCores']:.2f} / {cluster['cpuTotalCores']:.0f} cores ({cpu_percent}%)"},
            {"label": "Cluster memory", "value": f"{_gib(cluster['memoryBytes'])} / {_gib(cluster['memoryTotalBytes'])} GiB ({memory_percent}%)"},
            {"label": "Cluster disk", "value": f"{_gib(cluster['diskUsedBytes'])} / {_gib(cluster['diskTotalBytes'])} GiB"},
            {"label": "Namespaces with usage", "value": len(rows)},
        ],
    }


async def _workload_inventory(settings: Settings) -> dict[str, Any]:
    deployments = await k8s_client.list_deployments(settings, None)
    statefulsets = await k8s_client.list_statefulsets(settings, None)
    daemonsets = await k8s_client.list_daemonsets(settings, None)

    rows = []
    for item in deployments:
        rows.append(
            {
                "kind": "Deployment",
                "namespace": item["namespace"],
                "name": item["name"],
                "ready": f"{item['readyReplicas']}/{item['replicas']}",
                "healthy": "yes" if item["readyReplicas"] == item["replicas"] else "no",
                "images": ", ".join(item["images"]),
            }
        )
    for item in statefulsets:
        rows.append(
            {
                "kind": "StatefulSet",
                "namespace": item["namespace"],
                "name": item["name"],
                "ready": f"{item['readyReplicas']}/{item['replicas']}",
                "healthy": "yes" if item["readyReplicas"] == item["replicas"] else "no",
                "images": "",
            }
        )
    for item in daemonsets:
        rows.append(
            {
                "kind": "DaemonSet",
                "namespace": item["namespace"],
                "name": item["name"],
                "ready": f"{item['numberReady']}/{item['desiredScheduled']}",
                "healthy": "yes" if item["numberReady"] == item["desiredScheduled"] else "no",
                "images": "",
            }
        )
    rows.sort(key=lambda row: (row["healthy"] == "yes", row["namespace"], row["name"]))

    return {
        "columns": [
            {"key": "kind", "label": "Kind"},
            {"key": "namespace", "label": "Namespace"},
            {"key": "name", "label": "Name"},
            {"key": "ready", "label": "Ready"},
            {"key": "healthy", "label": "Fully available"},
            {"key": "images", "label": "Images"},
        ],
        "rows": rows,
        "summary": [
            {"label": "Deployments", "value": len(deployments)},
            {"label": "StatefulSets", "value": len(statefulsets)},
            {"label": "DaemonSets", "value": len(daemonsets)},
            {"label": "Not fully available", "value": sum(1 for row in rows if row["healthy"] == "no")},
        ],
    }


async def _pod_restarts(settings: Settings) -> dict[str, Any]:
    pods = await k8s_client.list_pods(settings, None)
    events = await k8s_client.list_events(settings, None, 500)

    # Latest warning event per pod, to explain the restarts where possible.
    reasons: dict[str, str] = {}
    for event in events:
        if event["type"] != "Warning" or not event["object"].startswith("pod/"):
            continue
        key = f"{event['namespace']}/{event['object'].split('/', 1)[1]}"
        reasons.setdefault(key, f"{event['reason']}: {event['message']}"[:200])

    rows = [
        {
            "namespace": pod["namespace"],
            "pod": pod["name"],
            "restarts": pod["restarts"],
            "status": pod["status"],
            "ready": pod["ready"],
            "node": pod["node"] or "",
            "lastWarning": reasons.get(f"{pod['namespace']}/{pod['name']}", ""),
        }
        for pod in pods
        if pod["restarts"] > 0
    ]
    rows.sort(key=lambda row: row["restarts"], reverse=True)

    return {
        "columns": [
            {"key": "namespace", "label": "Namespace"},
            {"key": "pod", "label": "Pod"},
            {"key": "restarts", "label": "Restarts"},
            {"key": "status", "label": "Status"},
            {"key": "ready", "label": "Ready"},
            {"key": "node", "label": "Node"},
            {"key": "lastWarning", "label": "Latest warning event"},
        ],
        "rows": rows,
        "summary": [
            {"label": "Pods with restarts", "value": len(rows)},
            {"label": "Total restarts", "value": sum(row["restarts"] for row in rows)},
            {"label": "Pods not running", "value": sum(1 for pod in pods if pod["status"] != "Running")},
            {"label": "Pods inspected", "value": len(pods)},
        ],
    }


async def _rbac_audit(settings: Settings) -> dict[str, Any]:
    bindings = await k8s_client.list_role_bindings(settings, None)
    roles = await k8s_client.list_roles(settings, None)
    accounts = await k8s_client.list_service_accounts(settings, None)

    write_roles = {role["name"] for role in roles if role["access"] == "write"}

    rows = []
    for binding in bindings:
        for subject in binding["subjects"]:
            rows.append(
                {
                    "subjectKind": subject["kind"],
                    "subject": subject["name"],
                    "subjectNamespace": subject.get("namespace") or "",
                    "roleKind": binding["roleKind"],
                    "role": binding["roleName"],
                    "scope": binding["scope"],
                    "binding": binding["name"],
                    "access": "write" if binding["roleName"] in write_roles else "read",
                    "builtIn": "yes" if binding["isDefault"] else "no",
                }
            )
    rows.sort(key=lambda row: (row["builtIn"] == "yes", row["subject"]))

    custom = [row for row in rows if row["builtIn"] == "no"]
    return {
        "columns": [
            {"key": "subjectKind", "label": "Subject kind"},
            {"key": "subject", "label": "Subject"},
            {"key": "subjectNamespace", "label": "Subject namespace"},
            {"key": "roleKind", "label": "Role kind"},
            {"key": "role", "label": "Role"},
            {"key": "scope", "label": "Scope"},
            {"key": "binding", "label": "Binding"},
            {"key": "access", "label": "Access"},
            {"key": "builtIn", "label": "Built-in"},
        ],
        "rows": rows,
        "summary": [
            {"label": "Bindings", "value": len(bindings)},
            {"label": "Grants (subject × binding)", "value": len(rows)},
            {"label": "Non-system grants", "value": len(custom)},
            {"label": "Non-system grants with write access", "value": sum(1 for row in custom if row["access"] == "write")},
            {"label": "Roles defined", "value": len(roles)},
            {"label": "Service accounts", "value": len(accounts)},
        ],
    }


Generator = Callable[[Settings], Awaitable[dict[str, Any]]]

TEMPLATES: list[dict[str, Any]] = [
    {
        "id": "cluster-health",
        "name": "Cluster Health Summary",
        "description": "Node readiness, kubelet versions, per-node utilisation, and pod placement.",
        "category": "Operations",
        "source": "Kubernetes API + Prometheus",
    },
    {
        "id": "resource-utilization",
        "name": "Resource Utilization",
        "description": "CPU, memory, and network usage per namespace, against cluster capacity.",
        "category": "Capacity",
        "source": "Prometheus + Kubernetes API",
    },
    {
        "id": "workload-inventory",
        "name": "Workload Inventory",
        "description": "Every Deployment, StatefulSet, and DaemonSet with its ready replicas and images.",
        "category": "Operations",
        "source": "Kubernetes API",
    },
    {
        "id": "pod-restarts",
        "name": "Pod Restart Report",
        "description": "Pods that have restarted, ranked, with the latest warning event for each.",
        "category": "Reliability",
        "source": "Kubernetes API",
    },
    {
        "id": "rbac-audit",
        "name": "RBAC Audit",
        "description": "Every RBAC grant in the cluster: which subject holds which role, and where it can write.",
        "category": "Security",
        "source": "Kubernetes API",
    },
]

_GENERATORS: dict[str, Generator] = {
    "cluster-health": _cluster_health,
    "resource-utilization": _resource_utilization,
    "workload-inventory": _workload_inventory,
    "pod-restarts": _pod_restarts,
    "rbac-audit": _rbac_audit,
}

_TEMPLATES_BY_ID = {template["id"]: template for template in TEMPLATES}


async def generate(settings: Settings, report_id: str) -> dict[str, Any]:
    generator = _GENERATORS.get(report_id)
    template = _TEMPLATES_BY_ID.get(report_id)
    if generator is None or template is None:
        raise UnknownReportError(report_id)

    result = await generator(settings)
    return {
        "id": report_id,
        "name": template["name"],
        "description": template["description"],
        "category": template["category"],
        "source": template["source"],
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "rowCount": len(result["rows"]),
        **result,
    }
