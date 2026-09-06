"""Cluster assistant.

Answers are derived from live cluster data — the Kubernetes API, Prometheus,
Loki, and Tempo — rather than generated text. A question is matched to an
intent, the intent runs the real queries that answer it, and the reply states
what those queries returned. Every number in an answer came from the cluster.
"""

import logging
import re
import time
from typing import Any, Awaitable, Callable

from app.config import Settings
from app.services.kubernetes import client as k8s_client
from app.services.kubernetes.client import KubernetesUnavailableError
from app.services.loki import client as loki_client
from app.services.loki.client import LokiUnavailableError
from app.services.prometheus import client as prom_client
from app.services.prometheus.client import PrometheusUnavailableError
from app.services.tempo import client as tempo_client
from app.services.tempo.client import TempoUnavailableError

logger = logging.getLogger("kubernetes-dashboard")

GIB = 1024**3


def _gib(value: float) -> float:
    return round(value / GIB, 2)


def _bullets(lines: list[str]) -> str:
    return "\n".join(f"• {line}" for line in lines)


async def _restarts(settings: Settings) -> dict[str, Any]:
    pods = await k8s_client.list_pods(settings, None)
    restarting = sorted((pod for pod in pods if pod["restarts"] > 0), key=lambda pod: pod["restarts"], reverse=True)
    unhealthy = [pod for pod in pods if pod["status"] not in ("Running", "Succeeded")]

    if not restarting and not unhealthy:
        return {
            "answer": f"No pods are restarting. All {len(pods)} pods across the cluster are Running or Succeeded.",
            "sources": ["Kubernetes API"],
            "data": {"pods": []},
        }

    events = await k8s_client.list_events(settings, None, 400)
    reasons: dict[str, str] = {}
    for event in events:
        if event["type"] == "Warning" and event["object"].startswith("pod/"):
            key = f"{event['namespace']}/{event['object'].split('/', 1)[1]}"
            reasons.setdefault(key, f"{event['reason']}: {event['message']}")

    top = restarting[:5]
    lines = []
    for pod in top:
        key = f"{pod['namespace']}/{pod['name']}"
        reason = reasons.get(key)
        detail = f" — {reason[:140]}" if reason else ""
        lines.append(f"{key}: {pod['restarts']} restarts, status {pod['status']}{detail}")

    headline = (
        f"{len(restarting)} pod(s) have restarted and {len(unhealthy)} are not in a Running state."
        if restarting
        else f"No restarts, but {len(unhealthy)} pod(s) are not Running."
    )
    return {
        "answer": f"{headline}\n\n{_bullets(lines)}" if lines else headline,
        "sources": ["Kubernetes API (pods, events)"],
        "data": {"pods": top, "unhealthy": unhealthy[:5]},
    }


async def _cpu(settings: Settings) -> dict[str, Any]:
    cluster = await prom_client.cluster_usage(settings)
    namespaces = await prom_client.namespace_usage(settings)
    nodes = await prom_client.node_usage(settings)

    percent = cluster["cpuCores"] / cluster["cpuTotalCores"] * 100 if cluster["cpuTotalCores"] else 0
    top = sorted(namespaces, key=lambda item: item["cpuCores"], reverse=True)[:5]
    hottest = max(nodes, key=lambda item: item["cpuPercent"], default=None)

    lines = [f"{item['namespace']}: {item['cpuCores']:.3f} cores" for item in top]
    answer = (
        f"Cluster CPU is {cluster['cpuCores']:.2f} of {cluster['cpuTotalCores']:.0f} cores ({percent:.1f}%)."
    )
    if hottest:
        answer += f" The busiest node is {hottest['name']} at {hottest['cpuPercent']}%."
    if lines:
        answer += f"\n\nTop namespaces by CPU:\n{_bullets(lines)}"

    return {"answer": answer, "sources": ["Prometheus"], "data": {"cluster": cluster, "namespaces": top, "nodes": nodes}}


async def _memory(settings: Settings) -> dict[str, Any]:
    cluster = await prom_client.cluster_usage(settings)
    namespaces = await prom_client.namespace_usage(settings)
    nodes = await prom_client.node_usage(settings)

    percent = cluster["memoryBytes"] / cluster["memoryTotalBytes"] * 100 if cluster["memoryTotalBytes"] else 0
    top = sorted(namespaces, key=lambda item: item["memoryBytes"], reverse=True)[:5]
    hottest = max(nodes, key=lambda item: item["memoryPercent"], default=None)

    lines = [f"{item['namespace']}: {_gib(item['memoryBytes'])} GiB" for item in top]
    answer = f"Cluster memory is {_gib(cluster['memoryBytes'])} of {_gib(cluster['memoryTotalBytes'])} GiB ({percent:.1f}%)."
    if hottest:
        answer += f" The most loaded node is {hottest['name']} at {hottest['memoryPercent']}%."
    if lines:
        answer += f"\n\nTop namespaces by memory:\n{_bullets(lines)}"

    return {"answer": answer, "sources": ["Prometheus"], "data": {"cluster": cluster, "namespaces": top, "nodes": nodes}}


async def _alerts(settings: Settings) -> dict[str, Any]:
    active = await prom_client.active_alerts(settings)
    rules = await prom_client.alert_rules(settings)

    if not rules:
        return {
            "answer": "No alerting rules are configured in Prometheus, so nothing can fire yet.",
            "sources": ["Prometheus"],
            "data": {"alerts": [], "rules": []},
        }
    if not active:
        return {
            "answer": f"Nothing is firing. All {len(rules)} configured alerting rules are inactive.",
            "sources": ["Prometheus"],
            "data": {"alerts": [], "rules": rules},
        }

    lines = [f"{alert['name']} ({alert['severity']}) on {alert['resource']} — {alert['message'][:140]}" for alert in active[:6]]
    firing = sum(1 for alert in active if alert["state"] == "firing")
    return {
        "answer": f"{firing} alert(s) firing and {len(active) - firing} pending, out of {len(rules)} rules.\n\n{_bullets(lines)}",
        "sources": ["Prometheus"],
        "data": {"alerts": active, "rules": rules},
    }


async def _logs(settings: Settings) -> dict[str, Any]:
    end_ns = int(time.time() * 1_000_000_000)
    start_ns = end_ns - 30 * 60 * 1_000_000_000
    logql = '{job="fluent-bit"} |~ "(?i)(error|exception|fatal|panic)"'
    entries = await loki_client.query_range(settings, logql, start_ns, end_ns, 200)

    if not entries:
        return {
            "answer": "No error-level log lines in the last 30 minutes.",
            "sources": ["Loki"],
            "data": {"entries": []},
        }

    by_pod: dict[str, int] = {}
    for entry in entries:
        key = f"{entry.get('namespace', '?')}/{entry.get('pod', '?')}"
        by_pod[key] = by_pod.get(key, 0) + 1
    ranked = sorted(by_pod.items(), key=lambda item: item[1], reverse=True)[:5]

    lines = [f"{pod}: {count} matching line(s)" for pod, count in ranked]
    # query_range returns oldest-first, so the newest line is at the end.
    sample = entries[-1].get("line", "")[:200]
    return {
        "answer": (
            f"{len(entries)} error-like log lines in the last 30 minutes.\n\n"
            f"{_bullets(lines)}\n\nMost recent: {sample}"
        ),
        "sources": ["Loki"],
        "data": {"entries": entries[-20:], "byPod": ranked},
    }


async def _nodes(settings: Settings) -> dict[str, Any]:
    nodes = await k8s_client.list_nodes(settings)
    info = await k8s_client.get_cluster_info(settings)
    try:
        usage = {item["name"]: item for item in await prom_client.node_usage(settings)}
    except PrometheusUnavailableError:
        usage = {}

    lines = []
    for node in nodes:
        metrics = usage.get(node["name"])
        detail = (
            f" — CPU {metrics['cpuPercent']}%, memory {metrics['memoryPercent']}%, disk {metrics['diskPercent']}%"
            if metrics
            else ""
        )
        lines.append(f"{node['name']} ({', '.join(node['roles']) or 'worker'}): {node['status']}{detail}")

    return {
        "answer": (
            f"{info['readyNodeCount']} of {info['nodeCount']} nodes are Ready on Kubernetes {info['gitVersion']}.\n\n"
            f"{_bullets(lines)}"
        ),
        "sources": ["Kubernetes API", "Prometheus"],
        "data": {"nodes": nodes, "cluster": info},
    }


async def _storage(settings: Settings) -> dict[str, Any]:
    pvcs = await k8s_client.list_pvcs(settings, None)
    cluster = await prom_client.cluster_usage(settings)

    percent = cluster["diskUsedBytes"] / cluster["diskTotalBytes"] * 100 if cluster["diskTotalBytes"] else 0
    unbound = [pvc for pvc in pvcs if pvc["status"] != "Bound"]
    lines = [f"{pvc['namespace']}/{pvc['name']}: {pvc['capacity'] or '?'} ({pvc['status']})" for pvc in pvcs[:6]]

    answer = (
        f"Node filesystems are {_gib(cluster['diskUsedBytes'])} of {_gib(cluster['diskTotalBytes'])} GiB used ({percent:.1f}%). "
        f"There are {len(pvcs)} PVC(s), {len(unbound)} not Bound."
    )
    if lines:
        answer += f"\n\n{_bullets(lines)}"
    return {"answer": answer, "sources": ["Kubernetes API", "Prometheus"], "data": {"pvcs": pvcs, "cluster": cluster}}


async def _traces(settings: Settings) -> dict[str, Any]:
    traces = await tempo_client.search_traces_summarised(settings, 20, 60)
    if not traces:
        return {
            "answer": "No traces were recorded in the last hour.",
            "sources": ["Tempo"],
            "data": {"traces": []},
        }

    slowest = sorted(traces, key=lambda trace: trace["durationMs"], reverse=True)[:5]
    errors = [trace for trace in traces if trace["status"] == "error"]
    lines = [f"{trace['rootService']} → {trace['operation']}: {trace['durationMs']:.1f}ms" for trace in slowest]
    average = sum(trace["durationMs"] for trace in traces) / len(traces)

    return {
        "answer": (
            f"{len(traces)} traces in the last hour, averaging {average:.1f}ms, with {len(errors)} in error.\n\n"
            f"Slowest:\n{_bullets(lines)}"
        ),
        "sources": ["Tempo"],
        "data": {"traces": slowest, "errorCount": len(errors)},
    }


async def _workloads(settings: Settings) -> dict[str, Any]:
    deployments = await k8s_client.list_deployments(settings, None)
    degraded = [item for item in deployments if item["readyReplicas"] != item["replicas"]]
    lines = [
        f"{item['namespace']}/{item['name']}: {item['readyReplicas']}/{item['replicas']} ready"
        for item in degraded[:6]
    ]
    if not degraded:
        return {
            "answer": f"All {len(deployments)} deployments have their full replica count ready.",
            "sources": ["Kubernetes API"],
            "data": {"deployments": []},
        }
    return {
        "answer": f"{len(degraded)} of {len(deployments)} deployments are not fully available.\n\n{_bullets(lines)}",
        "sources": ["Kubernetes API"],
        "data": {"deployments": degraded},
    }


async def _rbac(settings: Settings) -> dict[str, Any]:
    subjects = await k8s_client.list_subjects(settings, None)
    roles = await k8s_client.list_roles(settings, None)
    custom = [subject for subject in subjects if not subject["isDefault"]]
    cluster_wide = [subject for subject in custom if subject["clusterWide"]]

    lines = [
        f"{subject['kind']} {subject['name']}: {subject['roleCount']} binding(s)"
        + (" (cluster-wide)" if subject["clusterWide"] else "")
        for subject in custom[:6]
    ]
    answer = (
        f"{len(subjects)} RBAC subject(s) hold bindings, {len(custom)} of them outside the built-in "
        f"system defaults. {len(cluster_wide)} have cluster-wide access, across {len(roles)} defined roles."
    )
    if lines:
        answer += f"\n\n{_bullets(lines)}"
    return {"answer": answer, "sources": ["Kubernetes API (RBAC)"], "data": {"subjects": custom, "roleCount": len(roles)}}


async def _summary(settings: Settings) -> dict[str, Any]:
    info = await k8s_client.get_cluster_info(settings)
    pods = await k8s_client.list_pods(settings, None)
    running = sum(1 for pod in pods if pod["status"] == "Running")
    restarting = sum(1 for pod in pods if pod["restarts"] > 0)

    parts = [
        f"Kubernetes {info['gitVersion']}, {info['readyNodeCount']}/{info['nodeCount']} nodes ready",
        f"{running}/{len(pods)} pods running across {info['namespaceCount']} namespaces",
        f"{restarting} pod(s) with restarts",
    ]

    try:
        cluster = await prom_client.cluster_usage(settings)
        cpu_pct = cluster["cpuCores"] / cluster["cpuTotalCores"] * 100 if cluster["cpuTotalCores"] else 0
        mem_pct = cluster["memoryBytes"] / cluster["memoryTotalBytes"] * 100 if cluster["memoryTotalBytes"] else 0
        parts.append(f"CPU {cpu_pct:.1f}%, memory {mem_pct:.1f}%")
    except PrometheusUnavailableError:
        parts.append("metrics unavailable (Prometheus unreachable)")

    try:
        active = await prom_client.active_alerts(settings)
        parts.append(f"{len(active)} active alert(s)")
    except PrometheusUnavailableError:
        pass

    return {
        "answer": (
            "Here is the current state of the cluster:\n\n"
            + _bullets(parts)
            + "\n\nAsk about pods, CPU, memory, alerts, logs, nodes, storage, traces, deployments, or RBAC "
            "for the live detail behind any of these."
        ),
        "sources": ["Kubernetes API", "Prometheus"],
        "data": {"cluster": info},
    }


Intent = Callable[[Settings], Awaitable[dict[str, Any]]]

# Ordered: the first pattern that matches the question wins, so the more
# specific intents are listed before the broad ones.
_INTENTS: list[tuple[re.Pattern[str], Intent]] = [
    (re.compile(r"restart|crash|crashloop|oom|killed|failing|unhealthy|not running", re.I), _restarts),
    (re.compile(r"\balert|firing|paging|severity", re.I), _alerts),
    (re.compile(r"\blog|error message|exception|stack ?trace", re.I), _logs),
    (re.compile(r"\btrace|latency|slow|span|duration|p95", re.I), _traces),
    (re.compile(r"\bnode|worker|control ?plane|kubelet", re.I), _nodes),
    (re.compile(r"disk|storage|volume|pvc|persistent", re.I), _storage),
    (re.compile(r"rbac|permission|role|who can|access|security|service ?account", re.I), _rbac),
    (re.compile(r"deployment|replica|rollout|workload|available", re.I), _workloads),
    (re.compile(r"\bcpu\b|processor|compute", re.I), _cpu),
    (re.compile(r"memory|\bram\b|working set", re.I), _memory),
    (re.compile(r"summary|overview|health|status|how is|what.s up", re.I), _summary),
]

SUGGESTIONS = [
    "Why are pods restarting?",
    "Show me error logs",
    "Top CPU consuming namespaces",
    "Which traces are slowest?",
    "Who has cluster-wide RBAC access?",
    "Are all nodes ready?",
]


async def answer(settings: Settings, question: str) -> dict[str, Any]:
    intent = next((handler for pattern, handler in _INTENTS if pattern.search(question)), _summary)

    try:
        result = await intent(settings)
    except (KubernetesUnavailableError, PrometheusUnavailableError, LokiUnavailableError, TempoUnavailableError) as exc:
        logger.info("assistant could not answer %r: %s", question, exc)
        return {
            "answer": f"I could not read the data needed to answer that: {exc}",
            "sources": [],
            "data": {},
            "degraded": True,
        }

    return {**result, "degraded": False}
