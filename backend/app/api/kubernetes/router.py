from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth.security import AuthenticatedUser, require_user
from app.config import Settings, get_settings
from app.services.kubernetes import client as k8s_client
from app.services.kubernetes.client import KubernetesUnavailableError

router = APIRouter(prefix="/k8s", tags=["kubernetes"])


async def _run(coro: Any) -> Any:
    try:
        return await coro
    except KubernetesUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Kubernetes API is unavailable: {exc}",
        ) from exc


@router.get("/cluster")
async def cluster_info(
    _user: AuthenticatedUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    return await _run(k8s_client.get_cluster_info(settings))


@router.get("/nodes")
async def nodes(
    _user: AuthenticatedUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
) -> list[dict[str, Any]]:
    return await _run(k8s_client.list_nodes(settings))


@router.get("/namespaces")
async def namespaces(
    _user: AuthenticatedUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
) -> list[dict[str, Any]]:
    return await _run(k8s_client.list_namespaces(settings))


@router.get("/pods")
async def pods(
    namespace: str | None = Query(default=None),
    _user: AuthenticatedUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
) -> list[dict[str, Any]]:
    return await _run(k8s_client.list_pods(settings, namespace))


@router.get("/deployments")
async def deployments(
    namespace: str | None = Query(default=None),
    _user: AuthenticatedUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
) -> list[dict[str, Any]]:
    return await _run(k8s_client.list_deployments(settings, namespace))


@router.get("/services")
async def services(
    namespace: str | None = Query(default=None),
    _user: AuthenticatedUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
) -> list[dict[str, Any]]:
    return await _run(k8s_client.list_services(settings, namespace))


@router.get("/statefulsets")
async def statefulsets(
    namespace: str | None = Query(default=None),
    _user: AuthenticatedUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
) -> list[dict[str, Any]]:
    return await _run(k8s_client.list_statefulsets(settings, namespace))


@router.get("/daemonsets")
async def daemonsets(
    namespace: str | None = Query(default=None),
    _user: AuthenticatedUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
) -> list[dict[str, Any]]:
    return await _run(k8s_client.list_daemonsets(settings, namespace))


@router.get("/jobs")
async def jobs(
    namespace: str | None = Query(default=None),
    _user: AuthenticatedUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
) -> list[dict[str, Any]]:
    return await _run(k8s_client.list_jobs(settings, namespace))


@router.get("/pvcs")
async def pvcs(
    namespace: str | None = Query(default=None),
    _user: AuthenticatedUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
) -> list[dict[str, Any]]:
    return await _run(k8s_client.list_pvcs(settings, namespace))


@router.get("/serviceaccounts")
async def service_accounts(
    namespace: str | None = Query(default=None),
    _user: AuthenticatedUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
) -> list[dict[str, Any]]:
    return await _run(k8s_client.list_service_accounts(settings, namespace))


@router.get("/roles")
async def roles(
    namespace: str | None = Query(default=None),
    _user: AuthenticatedUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
) -> list[dict[str, Any]]:
    return await _run(k8s_client.list_roles(settings, namespace))


@router.get("/rolebindings")
async def role_bindings(
    namespace: str | None = Query(default=None),
    _user: AuthenticatedUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
) -> list[dict[str, Any]]:
    return await _run(k8s_client.list_role_bindings(settings, namespace))


@router.get("/subjects")
async def subjects(
    namespace: str | None = Query(default=None),
    _user: AuthenticatedUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
) -> list[dict[str, Any]]:
    return await _run(k8s_client.list_subjects(settings, namespace))
