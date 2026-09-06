from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth.security import AuthenticatedUser, require_user
from app.config import Settings, get_settings
from app.services.tempo import client as tempo_client
from app.services.tempo.client import TempoUnavailableError

router = APIRouter(prefix="/traces", tags=["traces"])


def _unavailable(exc: TempoUnavailableError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=f"Tempo is unavailable: {exc}",
    )


@router.get("")
async def traces(
    limit: int = Query(default=20, ge=1, le=100),
    rangeMinutes: int = Query(default=60, ge=1, le=10080),
    service: str | None = Query(default=None),
    minDurationMs: int = Query(default=0, ge=0),
    _user: AuthenticatedUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
) -> list[dict[str, Any]]:
    try:
        return await tempo_client.search_traces_summarised(
            settings, limit, rangeMinutes, service, minDurationMs
        )
    except TempoUnavailableError as exc:
        raise _unavailable(exc) from exc


@router.get("/services")
async def services(
    _user: AuthenticatedUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
) -> list[str]:
    try:
        return await tempo_client.list_services(settings)
    except TempoUnavailableError as exc:
        raise _unavailable(exc) from exc


@router.get("/{trace_id}")
async def trace(
    trace_id: str,
    _user: AuthenticatedUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    try:
        return await tempo_client.get_trace(settings, trace_id)
    except TempoUnavailableError as exc:
        raise _unavailable(exc) from exc
