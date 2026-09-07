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


A = TypeVar("A")


def _api(settings: Settings, api_class: Callable[[], A]) -> A:
    """Build an API client with the cluster config guaranteed to be loaded.

    The generated clients capture the default Configuration at construction time,
    so one built before the config is loaded binds to localhost:80 and fails —
    which is what happened to whichever endpoint was hit first after a restart,
    since _call() only loads the config once the client already exists."""
    _load_config(settings)
    return api_class()


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
        # "containers" has always carried images; container names are what the
        # log tail needs, so they are reported separately rather than by
        # redefining a field the API already returns.
        "containers": [c.image for c in (pod.spec.containers or [])] if pod.spec else [],
        "containerNames": [c.name for c in (pod.spec.containers or [])] if pod.spec else [],
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
    core_api = _api(settings, client.CoreV1Api)
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
    version_api = _api(settings, client.VersionApi)
    core_api = _api(settings, client.CoreV1Api)

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
    core_api = _api(settings, client.CoreV1Api)
    result = await _call(settings, core_api.list_node)
    return [_node_summary(node) for node in result.items]


async def list_namespaces(settings: Settings) -> list[dict[str, Any]]:
    core_api = _api(settings, client.CoreV1Api)
    result = await _call(settings, core_api.list_namespace)
    return [_namespace_summary(ns) for ns in result.items]


async def list_pods(settings: Settings, namespace: str | None) -> list[dict[str, Any]]:
    core_api = _api(settings, client.CoreV1Api)
    if namespace:
        result = await _call(settings, lambda: core_api.list_namespaced_pod(namespace))
    else:
        result = await _call(settings, core_api.list_pod_for_all_namespaces)
    return [_pod_summary(pod) for pod in result.items]


async def list_deployments(settings: Settings, namespace: str | None) -> list[dict[str, Any]]:
    apps_api = _api(settings, client.AppsV1Api)
    if namespace:
        result = await _call(settings, lambda: apps_api.list_namespaced_deployment(namespace))
    else:
        result = await _call(settings, apps_api.list_deployment_for_all_namespaces)
    return [_deployment_summary(dep) for dep in result.items]


async def list_services(settings: Settings, namespace: str | None) -> list[dict[str, Any]]:
    core_api = _api(settings, client.CoreV1Api)
    if namespace:
        result = await _call(settings, lambda: core_api.list_namespaced_service(namespace))
    else:
        result = await _call(settings, core_api.list_service_for_all_namespaces)
    return [_service_summary(svc) for svc in result.items]


async def list_statefulsets(settings: Settings, namespace: str | None) -> list[dict[str, Any]]:
    apps_api = _api(settings, client.AppsV1Api)
    if namespace:
        result = await _call(settings, lambda: apps_api.list_namespaced_stateful_set(namespace))
    else:
        result = await _call(settings, apps_api.list_stateful_set_for_all_namespaces)
    return [_statefulset_summary(sts) for sts in result.items]


async def list_daemonsets(settings: Settings, namespace: str | None) -> list[dict[str, Any]]:
    apps_api = _api(settings, client.AppsV1Api)
    if namespace:
        result = await _call(settings, lambda: apps_api.list_namespaced_daemon_set(namespace))
    else:
        result = await _call(settings, apps_api.list_daemon_set_for_all_namespaces)
    return [_daemonset_summary(ds) for ds in result.items]


async def list_jobs(settings: Settings, namespace: str | None) -> list[dict[str, Any]]:
    batch_api = _api(settings, client.BatchV1Api)
    if namespace:
        result = await _call(settings, lambda: batch_api.list_namespaced_job(namespace))
    else:
        result = await _call(settings, batch_api.list_job_for_all_namespaces)
    return [_job_summary(job) for job in result.items]


async def list_pvcs(settings: Settings, namespace: str | None) -> list[dict[str, Any]]:
    core_api = _api(settings, client.CoreV1Api)
    if namespace:
        result = await _call(settings, lambda: core_api.list_namespaced_persistent_volume_claim(namespace))
    else:
        result = await _call(settings, core_api.list_persistent_volume_claim_for_all_namespaces)
    return [_pvc_summary(pvc) for pvc in result.items]


def _service_account_summary(account: Any) -> dict[str, Any]:
    return {
        "name": account.metadata.name,
        "namespace": account.metadata.namespace,
        "secrets": [secret.name for secret in (account.secrets or []) if secret.name],
        "imagePullSecrets": [ref.name for ref in (account.image_pull_secrets or []) if ref.name],
        # None means "defaulted to true" in the API, which is what actually happens.
        "automountToken": account.automount_service_account_token is not False,
        "createdAt": _age(account),
    }


def _policy_rule_summary(rule: Any) -> dict[str, Any]:
    return {
        "apiGroups": list(rule.api_groups or []),
        "resources": list(rule.resources or []),
        "verbs": list(rule.verbs or []),
        "resourceNames": list(rule.resource_names or []),
        "nonResourceUrls": list(rule.non_resource_ur_ls or []),
    }


# Verbs that mutate, used to label a role read-only vs. write in the UI.
_WRITE_VERBS = {"create", "update", "patch", "delete", "deletecollection", "*"}


def _role_summary(role: Any, kind: str) -> dict[str, Any]:
    rules = [_policy_rule_summary(rule) for rule in (role.rules or [])]
    verbs = {verb for rule in rules for verb in rule["verbs"]}
    resources = sorted({resource for rule in rules for resource in rule["resources"]})
    return {
        "name": role.metadata.name,
        "kind": kind,
        "namespace": role.metadata.namespace,
        "scope": "Cluster" if kind == "ClusterRole" else (role.metadata.namespace or ""),
        "rules": rules,
        "ruleCount": len(rules),
        "resources": resources,
        "access": "write" if verbs & _WRITE_VERBS else "read",
        "isDefault": role.metadata.name.startswith("system:"),
        "createdAt": _age(role),
    }


def _binding_summary(binding: Any, kind: str) -> dict[str, Any]:
    role_ref = binding.role_ref
    subjects = [
        {
            "kind": subject.kind or "Unknown",
            "name": subject.name or "",
            "namespace": getattr(subject, "namespace", None),
        }
        for subject in (binding.subjects or [])
    ]
    return {
        "name": binding.metadata.name,
        "kind": kind,
        "namespace": binding.metadata.namespace,
        "scope": "Cluster" if kind == "ClusterRoleBinding" else (binding.metadata.namespace or ""),
        "roleKind": role_ref.kind if role_ref else "Unknown",
        "roleName": role_ref.name if role_ref else "unknown",
        "subjects": subjects,
        "isDefault": binding.metadata.name.startswith("system:"),
        "createdAt": _age(binding),
    }


async def list_service_accounts(settings: Settings, namespace: str | None) -> list[dict[str, Any]]:
    core_api = _api(settings, client.CoreV1Api)
    if namespace:
        result = await _call(settings, lambda: core_api.list_namespaced_service_account(namespace))
    else:
        result = await _call(settings, core_api.list_service_account_for_all_namespaces)
    return [_service_account_summary(account) for account in result.items]


async def list_roles(settings: Settings, namespace: str | None) -> list[dict[str, Any]]:
    """ClusterRoles and (namespaced) Roles as one list — the UI shows them together
    and distinguishes them by their `scope`."""
    rbac_api = _api(settings, client.RbacAuthorizationV1Api)
    cluster_roles = await _call(settings, rbac_api.list_cluster_role)
    if namespace:
        roles = await _call(settings, lambda: rbac_api.list_namespaced_role(namespace))
    else:
        roles = await _call(settings, rbac_api.list_role_for_all_namespaces)

    summaries = [_role_summary(role, "ClusterRole") for role in cluster_roles.items]
    summaries += [_role_summary(role, "Role") for role in roles.items]
    summaries.sort(key=lambda item: (item["isDefault"], item["name"]))
    return summaries


async def list_role_bindings(settings: Settings, namespace: str | None) -> list[dict[str, Any]]:
    rbac_api = _api(settings, client.RbacAuthorizationV1Api)
    cluster_bindings = await _call(settings, rbac_api.list_cluster_role_binding)
    if namespace:
        bindings = await _call(settings, lambda: rbac_api.list_namespaced_role_binding(namespace))
    else:
        bindings = await _call(settings, rbac_api.list_role_binding_for_all_namespaces)

    summaries = [_binding_summary(binding, "ClusterRoleBinding") for binding in cluster_bindings.items]
    summaries += [_binding_summary(binding, "RoleBinding") for binding in bindings.items]
    summaries.sort(key=lambda item: (item["isDefault"], item["name"]))
    return summaries


async def list_subjects(settings: Settings, namespace: str | None) -> list[dict[str, Any]]:
    """Every identity that RBAC actually grants access to, folded together across
    bindings. This is the cluster's answer to "who are the users" — Kubernetes has
    no User object, so a subject only exists by virtue of the bindings naming it."""
    bindings = await list_role_bindings(settings, namespace)

    subjects: dict[str, dict[str, Any]] = {}
    for binding in bindings:
        for subject in binding["subjects"]:
            key = f"{subject['kind']}/{subject.get('namespace') or ''}/{subject['name']}"
            entry = subjects.setdefault(
                key,
                {
                    "id": key,
                    "kind": subject["kind"],
                    "name": subject["name"],
                    "namespace": subject.get("namespace"),
                    "roles": [],
                    "namespaces": set(),
                    "isDefault": True,
                },
            )
            entry["roles"].append(
                {"role": binding["roleName"], "kind": binding["roleKind"], "binding": binding["name"], "scope": binding["scope"]}
            )
            entry["namespaces"].add(binding["scope"])
            # An identity is only "default" if every binding granting it is.
            entry["isDefault"] = entry["isDefault"] and binding["isDefault"]

    result = []
    for entry in subjects.values():
        entry["namespaces"] = sorted(ns for ns in entry["namespaces"] if ns)
        entry["roleCount"] = len(entry["roles"])
        entry["clusterWide"] = any(role["scope"] == "Cluster" for role in entry["roles"])
        result.append(entry)

    result.sort(key=lambda item: (item["isDefault"], item["kind"], item["name"]))
    return result
