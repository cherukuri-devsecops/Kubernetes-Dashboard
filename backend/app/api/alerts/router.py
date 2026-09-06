from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.security import AuthenticatedUser, require_user
from app.config import Settings, get_settings
from app.services.prometheus import client as prom_client
from app.services.prometheus.client import PrometheusUnavailableError

router = APIRouter(prefix="/alerts", tags=["alerts"])


def _unavailable(exc: PrometheusUnavailableError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=f"Prometheus is unavailable: {exc}",
    )


@router.get("")
async def alerts(
    _user: AuthenticatedUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Live alerts plus every configured rule. The UI needs both: alerts alone
    cannot tell a quiet cluster from one with no alerting configured."""
    try:
        active = await prom_client.active_alerts(settings)
        rules = await prom_client.alert_rules(settings)
    except PrometheusUnavailableError as exc:
        raise _unavailable(exc) from exc

    return {
        "alerts": active,
        "rules": rules,
        "ruleCount": len(rules),
        "firingCount": sum(1 for alert in active if alert["state"] == "firing"),
        "pendingCount": sum(1 for alert in active if alert["state"] == "pending"),
    }


@router.get("/rules")
async def rules(
    _user: AuthenticatedUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
) -> list[dict[str, Any]]:
    try:
        return await prom_client.alert_rules(settings)
    except PrometheusUnavailableError as exc:
        raise _unavailable(exc) from exc
