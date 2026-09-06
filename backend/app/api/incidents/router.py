from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth.security import AuthenticatedUser, require_user
from app.config import Settings, get_settings
from app.services.postgres import incidents as repository
from app.services.postgres.client import PostgresUnavailableError

router = APIRouter(prefix="/incidents", tags=["incidents"])

IncidentSeverity = Literal["sev1", "sev2", "sev3"]
IncidentStatus = Literal["open", "investigating", "mitigated", "resolved"]

_STATUS_NOTES: dict[str, str] = {
    "investigating": "Acknowledged the incident",
    "mitigated": "Impact mitigated, monitoring",
    "resolved": "Incident resolved",
    "open": "Incident reopened",
}


class CreateIncidentRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    severity: IncidentSeverity = "sev3"
    service: str = Field(default="", max_length=200)
    namespace: str = Field(default="", max_length=200)
    assignee: str = Field(default="Unassigned", max_length=200)
    summary: str = Field(default="", max_length=4000)
    linkedAlerts: list[str] = Field(default_factory=list)


class UpdateStatusRequest(BaseModel):
    status: IncidentStatus
    note: str | None = Field(default=None, max_length=1000)


class AddUpdateRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


def _unavailable(exc: PostgresUnavailableError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=f"Incident store is unavailable: {exc}",
    )


def _not_found(incident_id: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Incident {incident_id} not found",
    )


@router.get("")
async def list_incidents(
    _user: AuthenticatedUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
) -> list[dict[str, Any]]:
    try:
        return await repository.list_incidents(settings)
    except PostgresUnavailableError as exc:
        raise _unavailable(exc) from exc


@router.get("/{incident_id}")
async def get_incident(
    incident_id: str,
    _user: AuthenticatedUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    try:
        incident = await repository.get_incident(settings, incident_id)
    except PostgresUnavailableError as exc:
        raise _unavailable(exc) from exc
    if incident is None:
        raise _not_found(incident_id)
    return incident


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_incident(
    payload: CreateIncidentRequest,
    user: AuthenticatedUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    try:
        return await repository.create_incident(
            settings,
            title=payload.title,
            severity=payload.severity,
            service=payload.service,
            namespace=payload.namespace,
            assignee=payload.assignee,
            summary=payload.summary,
            linked_alerts=payload.linkedAlerts,
            actor=user.name,
        )
    except PostgresUnavailableError as exc:
        raise _unavailable(exc) from exc


@router.patch("/{incident_id}/status")
async def update_status(
    incident_id: str,
    payload: UpdateStatusRequest,
    user: AuthenticatedUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    note = payload.note or _STATUS_NOTES.get(payload.status, f"Status changed to {payload.status}")
    try:
        incident = await repository.set_status(settings, incident_id, payload.status, user.name, note)
    except PostgresUnavailableError as exc:
        raise _unavailable(exc) from exc
    if incident is None:
        raise _not_found(incident_id)
    return incident


@router.post("/{incident_id}/updates", status_code=status.HTTP_201_CREATED)
async def add_update(
    incident_id: str,
    payload: AddUpdateRequest,
    user: AuthenticatedUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    try:
        incident = await repository.add_update(settings, incident_id, user.name, payload.text)
    except PostgresUnavailableError as exc:
        raise _unavailable(exc) from exc
    if incident is None:
        raise _not_found(incident_id)
    return incident
