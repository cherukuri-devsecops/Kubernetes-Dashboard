from datetime import datetime, timezone
from typing import Any

import asyncpg

from app.config import Settings
from app.services.postgres import client as db

_INCIDENT_COLUMNS = """
    id, title, severity, status, service, namespace, assignee,
    opened_at, resolved_at, summary, root_cause, linked_alerts
"""

# Statuses that mean the incident is done; used to stamp resolved_at.
_CLOSED_STATUSES = {"resolved"}


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(timezone.utc).isoformat() if value else None


def _incident_row(row: asyncpg.Record, updates: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "title": row["title"],
        "severity": row["severity"],
        "status": row["status"],
        "service": row["service"],
        "namespace": row["namespace"],
        "assignee": row["assignee"],
        "openedAt": _iso(row["opened_at"]),
        "resolvedAt": _iso(row["resolved_at"]),
        "summary": row["summary"],
        "rootCause": row["root_cause"],
        "linkedAlerts": list(row["linked_alerts"] or []),
        "timeline": updates,
    }


def _update_row(row: asyncpg.Record) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "at": _iso(row["at"]),
        "actor": row["actor"],
        "text": row["body"],
    }


async def list_incidents(settings: Settings) -> list[dict[str, Any]]:
    incidents = await db.fetch(
        settings,
        f"SELECT {_INCIDENT_COLUMNS} FROM incidents ORDER BY opened_at DESC",
    )
    updates = await db.fetch(
        settings,
        "SELECT id, incident_id, at, actor, body FROM incident_updates ORDER BY at ASC",
    )

    # One query for every timeline instead of one per incident.
    by_incident: dict[str, list[dict[str, Any]]] = {}
    for update in updates:
        by_incident.setdefault(update["incident_id"], []).append(_update_row(update))

    return [_incident_row(row, by_incident.get(row["id"], [])) for row in incidents]


async def get_incident(settings: Settings, incident_id: str) -> dict[str, Any] | None:
    row = await db.fetchrow(
        settings,
        f"SELECT {_INCIDENT_COLUMNS} FROM incidents WHERE id = $1",
        incident_id,
    )
    if row is None:
        return None

    updates = await db.fetch(
        settings,
        "SELECT id, incident_id, at, actor, body FROM incident_updates WHERE incident_id = $1 ORDER BY at ASC",
        incident_id,
    )
    return _incident_row(row, [_update_row(update) for update in updates])


async def create_incident(
    settings: Settings,
    *,
    title: str,
    severity: str,
    service: str,
    namespace: str,
    assignee: str,
    summary: str,
    linked_alerts: list[str],
    actor: str,
) -> dict[str, Any]:
    pool = await db.ensure_pool(settings)
    async with pool.acquire() as connection:
        async with connection.transaction():
            number = await connection.fetchval("SELECT nextval('incident_number_seq')")
            incident_id = f"INC-{number}"
            await connection.execute(
                """
                INSERT INTO incidents
                    (id, title, severity, status, service, namespace, assignee, summary, linked_alerts)
                VALUES ($1, $2, $3, 'open', $4, $5, $6, $7, $8)
                """,
                incident_id,
                title,
                severity,
                service,
                namespace,
                assignee,
                summary,
                linked_alerts,
            )
            await connection.execute(
                "INSERT INTO incident_updates (incident_id, actor, body) VALUES ($1, $2, $3)",
                incident_id,
                actor,
                "Incident opened",
            )

    created = await get_incident(settings, incident_id)
    assert created is not None  # just inserted in the same transaction
    return created


async def set_status(
    settings: Settings, incident_id: str, status: str, actor: str, note: str
) -> dict[str, Any] | None:
    pool = await db.ensure_pool(settings)
    async with pool.acquire() as connection:
        async with connection.transaction():
            updated = await connection.fetchval(
                """
                UPDATE incidents
                   SET status = $2,
                       resolved_at = CASE
                           WHEN $2 = ANY($3::text[]) THEN COALESCE(resolved_at, now())
                           ELSE NULL
                       END
                 WHERE id = $1
                RETURNING id
                """,
                incident_id,
                status,
                list(_CLOSED_STATUSES),
            )
            if updated is None:
                return None
            await connection.execute(
                "INSERT INTO incident_updates (incident_id, actor, body) VALUES ($1, $2, $3)",
                incident_id,
                actor,
                note,
            )

    return await get_incident(settings, incident_id)


async def add_update(
    settings: Settings, incident_id: str, actor: str, body: str
) -> dict[str, Any] | None:
    exists = await db.fetchval(settings, "SELECT 1 FROM incidents WHERE id = $1", incident_id)
    if exists is None:
        return None

    await db.execute(
        settings,
        "INSERT INTO incident_updates (incident_id, actor, body) VALUES ($1, $2, $3)",
        incident_id,
        actor,
        body,
    )
    return await get_incident(settings, incident_id)


async def count_incidents(settings: Settings) -> int:
    return int(await db.fetchval(settings, "SELECT count(*) FROM incidents") or 0)
