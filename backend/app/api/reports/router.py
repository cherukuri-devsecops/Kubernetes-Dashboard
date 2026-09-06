import csv
import io
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.auth.security import AuthenticatedUser, require_user
from app.config import Settings, get_settings
from app.services.kubernetes.client import KubernetesUnavailableError
from app.services.prometheus.client import PrometheusUnavailableError
from app.services.reports import generator
from app.services.reports.generator import UnknownReportError

router = APIRouter(prefix="/reports", tags=["reports"])


def _not_found(report_id: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Unknown report '{report_id}'",
    )


async def _generate(settings: Settings, report_id: str) -> dict[str, Any]:
    try:
        return await generator.generate(settings, report_id)
    except UnknownReportError as exc:
        raise _not_found(report_id) from exc
    except (KubernetesUnavailableError, PrometheusUnavailableError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Cannot build report from live cluster data: {exc}",
        ) from exc


@router.get("/templates")
async def templates(
    _user: AuthenticatedUser = Depends(require_user),
) -> list[dict[str, Any]]:
    return generator.TEMPLATES


@router.get("/{report_id}")
async def report(
    report_id: str,
    _user: AuthenticatedUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    return await _generate(settings, report_id)


@router.get("/{report_id}/download")
async def download(
    report_id: str,
    format: str = Query(default="csv", pattern="^(csv|json)$"),
    _user: AuthenticatedUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
) -> Response:
    """The real file, built from the same live query as the on-screen report."""
    result = await _generate(settings, report_id)
    stamp = result["generatedAt"][:19].replace(":", "").replace("-", "")
    filename = f"{report_id}-{stamp}.{format}"

    if format == "json":
        body = json.dumps(result, indent=2)
        media_type = "application/json"
    else:
        buffer = io.StringIO()
        columns = result["columns"]
        writer = csv.writer(buffer)
        writer.writerow([column["label"] for column in columns])
        for row in result["rows"]:
            writer.writerow([row.get(column["key"], "") for column in columns])
        body = buffer.getvalue()
        media_type = "text/csv"

    return Response(
        content=body,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
