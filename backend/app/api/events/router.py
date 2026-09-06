from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth.security import AuthenticatedUser, require_user
from app.config import Settings, get_settings
from app.services.kubernetes import client as k8s_client
from app.services.kubernetes.client import KubernetesUnavailableError

router = APIRouter(prefix="/events", tags=["events"])


@router.get("")
async def events(
    namespace: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    _user: AuthenticatedUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
) -> list[dict[str, Any]]:
    try:
        return await k8s_client.list_events(settings, namespace, limit)
    except KubernetesUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Kubernetes API is unavailable: {exc}",
        ) from exc
