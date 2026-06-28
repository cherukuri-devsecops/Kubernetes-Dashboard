"""GET /api/events — list K8s events."""
import logging

from fastapi import APIRouter, Depends, Query
from kubernetes.client import ApiClient

from ..k8s_client import _header_dep, core_v1

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("")
def list_events(
    namespace: str  = Query(default="", description="Filter by namespace (empty = all)"),
    kind: str       = Query(default="", description="Filter by involvedObject.kind"),
    name: str       = Query(default="", description="Filter by involvedObject.name"),
    event_type: str = Query(default="", description="Warning | Normal"),
    limit: int      = Query(default=200, ge=1, le=2000),
    ac: ApiClient   = Depends(_header_dep),
):
    core = core_v1(ac)

    field_selectors = []
    if name:
        field_selectors.append(f"involvedObject.name={name}")
    if kind:
        field_selectors.append(f"involvedObject.kind={kind}")
    if event_type:
        field_selectors.append(f"type={event_type}")
    field_sel = ",".join(field_selectors) or None

    if namespace:
        items = core.list_namespaced_event(namespace, field_selector=field_sel).items
    else:
        items = core.list_event_for_all_namespaces(field_selector=field_sel).items

    items.sort(key=lambda e: (e.last_timestamp or e.event_time or ""), reverse=True)
    items = items[:limit]

    return [
        {
            "type":      e.type or "Normal",
            "reason":    e.reason or "",
            "message":   e.message or "",
            "namespace": e.metadata.namespace,
            "object":    f"{e.involved_object.kind}/{e.involved_object.name}",
            "count":     e.count or 1,
            "first_ts":  str(e.first_timestamp),
            "last_ts":   str(e.last_timestamp),
            "source":    e.source.component if e.source else "",
        }
        for e in items
    ]
