"""GET /api/deployments — list and detail deployments."""
import logging

from fastapi import APIRouter, Depends, Path, Query
from kubernetes.client import ApiClient

from ..k8s_client import _header_dep, apps_v1, core_v1

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/deployments", tags=["deployments"])


def _dep_dict(d) -> dict:
    spec   = d.spec or {}
    status = d.status or {}
    return {
        "name":              d.metadata.name,
        "namespace":         d.metadata.namespace,
        "desired":           spec.replicas or 0,
        "ready":             status.ready_replicas or 0,
        "available":         status.available_replicas or 0,
        "updated":           status.updated_replicas or 0,
        "unavailable":       status.unavailable_replicas or 0,
        "strategy":          (spec.strategy.type if spec.strategy else ""),
        "labels":            d.metadata.labels or {},
        "selector":          (spec.selector.match_labels if spec.selector else {}),
        "created":           str(d.metadata.creation_timestamp),
        "images":            list({
            c.image for c in (spec.template.spec.containers or [])
            if spec.template and spec.template.spec
        }),
    }


@router.get("")
def list_deployments(
    namespace: str = Query(default=""),
    ac: ApiClient  = Depends(_header_dep),
):
    appsv1 = apps_v1(ac)
    if namespace:
        items = appsv1.list_namespaced_deployment(namespace).items
    else:
        items = appsv1.list_deployment_for_all_namespaces().items
    return [_dep_dict(d) for d in items]


@router.get("/{namespace}/{name}")
def get_deployment(
    namespace: str = Path(...),
    name: str      = Path(...),
    ac: ApiClient  = Depends(_header_dep),
):
    appsv1 = apps_v1(ac)
    corev1 = core_v1(ac)
    d = appsv1.read_namespaced_deployment(name, namespace)

    # Fetch ReplicaSets owned by this deployment
    rs_list = appsv1.list_namespaced_replica_set(
        namespace,
        label_selector=",".join(f"{k}={v}" for k, v in
                                (d.spec.selector.match_labels if d.spec and d.spec.selector else {}).items()),
    ).items
    replica_sets = [
        {"name": rs.metadata.name, "desired": rs.spec.replicas or 0, "ready": rs.status.ready_replicas or 0}
        for rs in rs_list
    ]

    events = corev1.list_namespaced_event(
        namespace,
        field_selector=f"involvedObject.name={name}",
    ).items
    event_list = [
        {"type": e.type, "reason": e.reason, "message": e.message, "ts": str(e.last_timestamp)}
        for e in events
    ]

    base = _dep_dict(d)
    base.update({
        "replica_sets": replica_sets,
        "events":       event_list,
        "annotations":  {k: v for k, v in (d.metadata.annotations or {}).items()
                         if "kubectl.kubernetes.io/last-applied" not in k},
    })
    return base
