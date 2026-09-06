import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth.security import AuthenticatedUser, require_user
from app.config import Settings, get_settings
from app.services.kubernetes import client as k8s_client
from app.services.kubernetes.client import KubernetesUnavailableError

router = APIRouter(prefix="/search", tags=["search"])

# Which page a hit on each kind should open.
_ROUTES = {
    "Pod": "/kubernetes",
    "Deployment": "/kubernetes",
    "Service": "/kubernetes",
    "StatefulSet": "/kubernetes",
    "DaemonSet": "/kubernetes",
    "Node": "/metrics",
    "Namespace": "/kubernetes",
}


@router.get("")
async def search(
    q: str = Query(default="", max_length=200),
    limit: int = Query(default=20, ge=1, le=100),
    _user: AuthenticatedUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
) -> list[dict[str, Any]]:
    """Name search across the real objects in the cluster."""
    try:
        pods, deployments, services, nodes, namespaces = await asyncio.gather(
            k8s_client.list_pods(settings, None),
            k8s_client.list_deployments(settings, None),
            k8s_client.list_services(settings, None),
            k8s_client.list_nodes(settings),
            k8s_client.list_namespaces(settings),
        )
    except KubernetesUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Kubernetes API is unavailable: {exc}",
        ) from exc

    candidates: list[dict[str, Any]] = []
    for kind, items in (
        ("Pod", pods),
        ("Deployment", deployments),
        ("Service", services),
        ("Node", nodes),
        ("Namespace", namespaces),
    ):
        for item in items:
            namespace = item.get("namespace")
            candidates.append(
                {
                    "id": f"{kind}:{namespace or ''}/{item['name']}",
                    "label": item["name"],
                    "category": kind,
                    "namespace": namespace,
                    "href": _ROUTES.get(kind, "/kubernetes"),
                }
            )

    needle = q.strip().lower()
    if needle:
        matches = [item for item in candidates if needle in item["label"].lower() or needle in item["category"].lower()]
        # Prefix matches are what the user usually means, so float them up.
        matches.sort(key=lambda item: (not item["label"].lower().startswith(needle), item["label"]))
    else:
        matches = sorted(candidates, key=lambda item: (item["category"], item["label"]))

    return matches[:limit]
