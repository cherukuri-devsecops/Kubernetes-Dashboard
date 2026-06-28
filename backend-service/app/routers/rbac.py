"""GET /api/rbac — SelfSubjectAccessReview permission checks."""
import logging
import threading

from cachetools import TTLCache
from fastapi import APIRouter, Depends, Query
from kubernetes import client
from kubernetes.client import ApiClient

from ..k8s_client import _header_dep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/rbac", tags=["rbac"])

_cache = TTLCache(maxsize=2048, ttl=60)
_lock  = threading.Lock()

_KIND_TO_RESOURCE: dict[str, tuple[str, str]] = {
    "pods":               ("", "pods"),
    "deployments":        ("apps", "deployments"),
    "statefulsets":       ("apps", "statefulsets"),
    "daemonsets":         ("apps", "daemonsets"),
    "replicasets":        ("apps", "replicasets"),
    "jobs":               ("batch", "jobs"),
    "cronjobs":           ("batch", "cronjobs"),
    "services":           ("", "services"),
    "ingresses":          ("networking.k8s.io", "ingresses"),
    "configmaps":         ("", "configmaps"),
    "secrets":            ("", "secrets"),
    "namespaces":         ("", "namespaces"),
    "nodes":              ("", "nodes"),
    "pvs":                ("", "persistentvolumes"),
    "pvcs":               ("", "persistentvolumeclaims"),
    "events":             ("", "events"),
    "serviceaccounts":    ("", "serviceaccounts"),
    "roles":              ("rbac.authorization.k8s.io", "roles"),
    "rolebindings":       ("rbac.authorization.k8s.io", "rolebindings"),
    "clusterroles":       ("rbac.authorization.k8s.io", "clusterroles"),
    "clusterrolebindings": ("rbac.authorization.k8s.io", "clusterrolebindings"),
}

KIND_TO_PLURAL: dict[str, str] = {
    "Pod": "pods", "Deployment": "deployments", "StatefulSet": "statefulsets",
    "DaemonSet": "daemonsets", "ReplicaSet": "replicasets", "Job": "jobs",
    "CronJob": "cronjobs", "Service": "services", "Ingress": "ingresses",
    "ConfigMap": "configmaps", "Secret": "secrets", "Namespace": "namespaces",
    "Node": "nodes", "PersistentVolumeClaim": "pvcs", "PersistentVolume": "pvs",
    "ServiceAccount": "serviceaccounts",
}

_MATRIX_VERBS = ("create", "update", "delete", "get", "list")
_MATRIX_KINDS = (
    "pods", "deployments", "statefulsets", "daemonsets", "jobs",
    "services", "configmaps", "secrets", "ingresses",
    "namespaces", "nodes", "pvcs", "pvs",
)


def _can(verb: str, kind: str, namespace: str, ac: ApiClient) -> bool:
    group, resource = _KIND_TO_RESOURCE.get(kind.lower(), ("", kind.lower()))
    cache_key = (id(ac), verb, kind.lower(), namespace or "")
    with _lock:
        hit = _cache.get(cache_key)
    if hit is not None:
        return hit
    try:
        authz = client.AuthorizationV1Api(ac)
        sar = client.V1SelfSubjectAccessReview(
            spec=client.V1SelfSubjectAccessReviewSpec(
                resource_attributes=client.V1ResourceAttributes(
                    verb=verb, group=group, resource=resource,
                    namespace=namespace or None,
                )
            )
        )
        allowed = authz.create_self_subject_access_review(sar).status.allowed
    except Exception as e:
        logger.debug("rbac check failed (%s %s/%s): %s — defaulting allow", verb, kind, namespace, e)
        allowed = True
    with _lock:
        _cache[cache_key] = allowed
    return allowed


@router.get("/matrix")
def rbac_matrix(ac: ApiClient = Depends(_header_dep)):
    """Return full permission matrix: {kind: {verb: bool}}."""
    return {k: {v: _can(v, k, "", ac) for v in _MATRIX_VERBS} for k in _MATRIX_KINDS}


@router.get("/check")
def rbac_check(
    verb: str      = Query(...),
    kind: str      = Query(...),
    ns: str        = Query(default=""),
    ac: ApiClient  = Depends(_header_dep),
):
    """Check a single permission."""
    return {"allowed": _can(verb, kind, ns, ac)}
