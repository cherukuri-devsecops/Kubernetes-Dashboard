import asyncio
import logging
from typing import Any, Callable, TypeVar

import urllib3
from kubernetes import client, config
from kubernetes.client import ApiException

from app.config import Settings

logger = logging.getLogger("kubernetes-dashboard")

T = TypeVar("T")

_config_loaded = False

# The kubernetes client raises these (unwrapped) for connection-level failures,
# as opposed to ApiException which it raises for HTTP-level error responses.
_CONNECTION_EXCEPTIONS = (urllib3.exceptions.HTTPError, OSError)
_MAX_ATTEMPTS = 3
_RETRY_DELAY_SECONDS = 0.5


class KubernetesUnavailableError(RuntimeError):
    """Raised when the Kubernetes API cannot be reached or is not configured."""


def _load_config(settings: Settings) -> None:
    global _config_loaded
    if _config_loaded:
        return

    try:
        config.load_incluster_config()
    except config.ConfigException:
        try:
            config.load_kube_config(
                config_file=settings.kubeconfig_path or None,
                context=settings.kubeconfig_context or None,
            )
        except config.ConfigException as exc:
            raise KubernetesUnavailableError(
                "No in-cluster config or kubeconfig found"
            ) from exc

    _config_loaded = True


def ensure_config_loaded(settings: Settings) -> None:
    """Public entry point for callers outside this module (e.g. streaming log reads)
    that need kubeconfig loaded before constructing their own API client."""
    _load_config(settings)


async def _call(settings: Settings, fn: Callable[[], T]) -> T:
    _load_config(settings)

    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            return await asyncio.to_thread(fn)
        except ApiException as exc:
            logger.warning("kubernetes API error: %s", exc.reason)
            raise KubernetesUnavailableError(exc.reason or "Kubernetes API error") from exc
        except _CONNECTION_EXCEPTIONS as exc:
            if attempt < _MAX_ATTEMPTS:
                logger.warning(
                    "kubernetes API unreachable (attempt %d/%d), retrying: %s", attempt, _MAX_ATTEMPTS, exc
                )
                await asyncio.sleep(_RETRY_DELAY_SECONDS)
                continue
            logger.warning("kubernetes API unreachable: %s", exc)
            raise KubernetesUnavailableError("Could not reach the Kubernetes API") from exc

    raise KubernetesUnavailableError("Could not reach the Kubernetes API")


def _age(obj: Any) -> str | None:
    timestamp = getattr(obj.metadata, "creation_timestamp", None)
    return timestamp.isoformat() if timestamp else None


def _quantity_to_str(value: str | None) -> str | None:
    return value


def _node_summary(node: Any) -> dict[str, Any]:
    conditions = {c.type: c.status for c in (node.status.conditions or [])}
    ready = conditions.get("Ready") == "True"
    roles = [
        label.split("node-role.kubernetes.io/", 1)[1] or "master"
        for label in (node.metadata.labels or {})
        if label.startswith("node-role.kubernetes.io/")
    ]
    addresses = {a.type: a.address for a in (node.status.addresses or [])}
    capacity = node.status.capacity or {}
    allocatable = node.status.allocatable or {}

    return {
        "name": node.metadata.name,
        "status": "Ready" if ready else "NotReady",
        "roles": roles or ["worker"],
        "kubeletVersion": node.status.node_info.kubelet_version if node.status.node_info else None,
        "osImage": node.status.node_info.os_image if node.status.node_info else None,
        "internalIp": addresses.get("InternalIP"),
        "cpuCapacity": _quantity_to_str(capacity.get("cpu")),
        "memoryCapacity": _quantity_to_str(capacity.get("memory")),
        "cpuAllocatable": _quantity_to_str(allocatable.get("cpu")),
        "memoryAllocatable": _quantity_to_str(allocatable.get("memory")),
        "podCapacity": _quantity_to_str(capacity.get("pods")),
        "createdAt": _age(node),
    }


def _namespace_summary(namespace: Any) -> dict[str, Any]:
    return {
        "name": namespace.metadata.name,
        "status": namespace.status.phase if namespace.status else "Unknown",
        "createdAt": _age(namespace),
    }


def _pod_summary(pod: Any) -> dict[str, Any]:
    container_statuses = pod.status.container_statuses or []
    ready_count = sum(1 for c in container_statuses if c.ready)
    restarts = sum(c.restart_count for c in container_statuses)

    return {
        "name": pod.metadata.name,
        "namespace": pod.metadata.namespace,
        "status": pod.status.phase if pod.status else "Unknown",
        "ready": f"{ready_count}/{len(container_statuses)}",
        "restarts": restarts,
        "node": pod.spec.node_name if pod.spec else None,
        "podIp": pod.status.pod_ip if pod.status else None,
        "containers": [c.image for c in (pod.spec.containers or [])] if pod.spec else [],
        "createdAt": _age(pod),
    }


def _deployment_summary(deployment: Any) -> dict[str, Any]:
    status = deployment.status
    spec = deployment.spec
    return {
        "name": deployment.metadata.name,
        "namespace": deployment.metadata.namespace,
        "replicas": spec.replicas if spec else 0,
        "readyReplicas": status.ready_replicas or 0 if status else 0,
        "updatedReplicas": status.updated_replicas or 0 if status else 0,
        "availableReplicas": status.available_replicas or 0 if status else 0,
        "images": [c.image for c in (spec.template.spec.containers or [])] if spec else [],
        "createdAt": _age(deployment),
    }


def _service_summary(service: Any) -> dict[str, Any]:
    spec = service.spec
    ports = [
        f"{p.port}:{p.target_port}/{p.protocol}" for p in (spec.ports or [])
    ] if spec else []
    external_ips = []
    if service.status and service.status.load_balancer and service.status.load_balancer.ingress:
        external_ips = [
            ing.ip or ing.hostname for ing in service.status.load_balancer.ingress if ing.ip or ing.hostname
        ]
    return {
        "name": service.metadata.name,
        "namespace": service.metadata.namespace,
        "type": spec.type if spec else "Unknown",
        "clusterIp": spec.cluster_ip if spec else None,
        "externalIps": external_ips or (spec.external_i_ps if spec else None) or [],
        "ports": ports,
        "createdAt": _age(service),
    }


def _statefulset_summary(sts: Any) -> dict[str, Any]:
    status = sts.status
    return {
        "name": sts.metadata.name,
        "namespace": sts.metadata.namespace,
        "replicas": sts.spec.replicas if sts.spec else 0,
        "readyReplicas": status.ready_replicas or 0 if status else 0,
        "currentReplicas": status.current_replicas or 0 if status else 0,
        "serviceName": sts.spec.service_name if sts.spec else None,
        "createdAt": _age(sts),
    }


def _daemonset_summary(ds: Any) -> dict[str, Any]:
    status = ds.status
    return {
        "name": ds.metadata.name,
        "namespace": ds.metadata.namespace,
        "desiredScheduled": status.desired_number_scheduled or 0 if status else 0,
        "currentScheduled": status.current_number_scheduled or 0 if status else 0,
        "numberReady": status.number_ready or 0 if status else 0,
        "numberAvailable": status.number_available or 0 if status else 0,
        "createdAt": _age(ds),
    }


def _job_summary(job: Any) -> dict[str, Any]:
    status = job.status
    spec = job.spec
    return {
        "name": job.metadata.name,
        "namespace": job.metadata.namespace,
        "completions": spec.completions if spec else None,
        "succeeded": status.succeeded or 0 if status else 0,
        "failed": status.failed or 0 if status else 0,
        "active": status.active or 0 if status else 0,
        "startTime": status.start_time.isoformat() if status and status.start_time else None,
        "completionTime": status.completion_time.isoformat() if status and status.completion_time else None,
        "createdAt": _age(job),
    }


def _pvc_summary(pvc: Any) -> dict[str, Any]:
    spec = pvc.spec
    status = pvc.status
    capacity = status.capacity.get("storage") if status and status.capacity else None
    return {
        "name": pvc.metadata.name,
        "namespace": pvc.metadata.namespace,
        "status": status.phase if status else "Unknown",
        "volumeName": spec.volume_name if spec else None,
        "capacity": capacity,
        "accessModes": spec.access_modes if spec else [],
        "storageClass": spec.storage_class_name if spec else None,
        "createdAt": _age(pvc),
    }


def _event_timestamps(event: Any) -> tuple[str | None, str | None]:
    """Core v1 events carry first/last timestamps, but events emitted through the
    newer events.k8s.io path only set event_time, so fall back through both."""
    fallback = getattr(event, "event_time", None) or getattr(event.metadata, "creation_timestamp", None)
    first = event.first_timestamp or fallback
    last = event.last_timestamp or event.first_timestamp or fallback
    return (
        first.isoformat() if first else None,
        last.isoformat() if last else None,
    )


def _event_summary(event: Any) -> dict[str, Any]:
    involved = event.involved_object
    kind = (involved.kind or "object").lower() if involved else "object"
    name = involved.name if involved else "unknown"
    source = event.source.component if event.source and event.source.component else None
    first_seen, last_seen = _event_timestamps(event)

    return {
        "id": event.metadata.uid,
        "type": event.type or "Normal",
        "reason": event.reason or "Unknown",
        "object": f"{kind}/{name}",
        "namespace": (involved.namespace if involved else None) or event.metadata.namespace,
        "source": source or getattr(event, "reporting_component", None) or "unknown",
        "message": event.message or "",
        "count": event.count or 1,
        "firstSeen": first_seen,
        "lastSeen": last_seen,
    }


async def list_events(settings: Settings, namespace: str | None, limit: int) -> list[dict[str, Any]]:
    core_api = client.CoreV1Api()
    if namespace:
        result = await _call(settings, lambda: core_api.list_namespaced_event(namespace))
    else:
        result = await _call(settings, core_api.list_event_for_all_namespaces)

    summaries = [_event_summary(event) for event in result.items]
    # Sort here rather than passing limit to the API: the API's limit paginates
    # before any ordering, which would return an arbitrary slice, not the newest.
    summaries.sort(key=lambda item: item["lastSeen"] or "", reverse=True)
    return summaries[:limit]


async def get_cluster_info(settings: Settings) -> dict[str, Any]:
    version_api = client.VersionApi()
    core_api = client.CoreV1Api()

    version = await _call(settings, version_api.get_code)
    nodes = await _call(settings, core_api.list_node)
    namespaces = await _call(settings, core_api.list_namespace)
    pods = await _call(settings, lambda: core_api.list_pod_for_all_namespaces())

    ready_nodes = sum(
        1
        for node in nodes.items
        if any(c.type == "Ready" and c.status == "True" for c in (node.status.conditions or []))
    )

    return {
        "gitVersion": version.git_version,
        "platform": version.platform,
        "nodeCount": len(nodes.items),
        "readyNodeCount": ready_nodes,
        "namespaceCount": len(namespaces.items),
        "podCount": len(pods.items),
    }


async def list_nodes(settings: Settings) -> list[dict[str, Any]]:
    core_api = client.CoreV1Api()
    result = await _call(settings, core_api.list_node)
    return [_node_summary(node) for node in result.items]


async def list_namespaces(settings: Settings) -> list[dict[str, Any]]:
    core_api = client.CoreV1Api()
    result = await _call(settings, core_api.list_namespace)
    return [_namespace_summary(ns) for ns in result.items]


async def list_pods(settings: Settings, namespace: str | None) -> list[dict[str, Any]]:
    core_api = client.CoreV1Api()
    if namespace:
        result = await _call(settings, lambda: core_api.list_namespaced_pod(namespace))
    else:
        result = await _call(settings, core_api.list_pod_for_all_namespaces)
    return [_pod_summary(pod) for pod in result.items]


async def list_deployments(settings: Settings, namespace: str | None) -> list[dict[str, Any]]:
    apps_api = client.AppsV1Api()
    if namespace:
        result = await _call(settings, lambda: apps_api.list_namespaced_deployment(namespace))
    else:
        result = await _call(settings, apps_api.list_deployment_for_all_namespaces)
    return [_deployment_summary(dep) for dep in result.items]


async def list_services(settings: Settings, namespace: str | None) -> list[dict[str, Any]]:
    core_api = client.CoreV1Api()
    if namespace:
        result = await _call(settings, lambda: core_api.list_namespaced_service(namespace))
    else:
        result = await _call(settings, core_api.list_service_for_all_namespaces)
    return [_service_summary(svc) for svc in result.items]


async def list_statefulsets(settings: Settings, namespace: str | None) -> list[dict[str, Any]]:
    apps_api = client.AppsV1Api()
    if namespace:
        result = await _call(settings, lambda: apps_api.list_namespaced_stateful_set(namespace))
    else:
        result = await _call(settings, apps_api.list_stateful_set_for_all_namespaces)
    return [_statefulset_summary(sts) for sts in result.items]


async def list_daemonsets(settings: Settings, namespace: str | None) -> list[dict[str, Any]]:
    apps_api = client.AppsV1Api()
    if namespace:
        result = await _call(settings, lambda: apps_api.list_namespaced_daemon_set(namespace))
    else:
        result = await _call(settings, apps_api.list_daemon_set_for_all_namespaces)
    return [_daemonset_summary(ds) for ds in result.items]


async def list_jobs(settings: Settings, namespace: str | None) -> list[dict[str, Any]]:
    batch_api = client.BatchV1Api()
    if namespace:
        result = await _call(settings, lambda: batch_api.list_namespaced_job(namespace))
    else:
        result = await _call(settings, batch_api.list_job_for_all_namespaces)
    return [_job_summary(job) for job in result.items]


async def list_pvcs(settings: Settings, namespace: str | None) -> list[dict[str, Any]]:
    core_api = client.CoreV1Api()
    if namespace:
        result = await _call(settings, lambda: core_api.list_namespaced_persistent_volume_claim(namespace))
    else:
        result = await _call(settings, core_api.list_persistent_volume_claim_for_all_namespaces)
    return [_pvc_summary(pvc) for pvc in result.items]
