"""Demo incidents for a freshly created database.

Only runs when SEED_DEMO_DATA is enabled and the incidents table is empty, so it
never overwrites real data. The docker-compose dev stack turns it on; production
should leave it off and let incidents arrive from the alerting pipeline.
"""

import logging
from datetime import datetime, timedelta, timezone

from app.config import Settings
from app.services.postgres import client as db
from app.services.postgres import incidents as repository

logger = logging.getLogger("kubernetes-dashboard")


def _minutes_ago(minutes: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(minutes=minutes)


_DEMO_INCIDENTS: list[dict] = [
    {
        "id": "INC-1042",
        "title": "Checkout API returning 5xx for 12% of requests",
        "severity": "sev1",
        "status": "investigating",
        "service": "api-gateway",
        "namespace": "payments",
        "assignee": "Priya N.",
        "opened_minutes_ago": 38,
        "resolved_minutes_ago": None,
        "summary": (
            "Error rate on POST /v1/checkout rose from 0.2% to 12%. Elevated p95 latency on "
            "payments-worker began three minutes earlier, pointing at a downstream dependency."
        ),
        "root_cause": "postgres connection pool saturation on payments-worker (20/20 in use).",
        "linked_alerts": ["HighRequestLatency", "PodCrashLooping"],
        "updates": [
            (38, "Alertmanager", "Incident opened from alert HighRequestLatency"),
            (34, "Priya N.", "Acknowledged - checking payments-worker saturation"),
            (21, "AI Assistant", "Root cause analysis: postgres connection pool exhausted"),
        ],
    },
    {
        "id": "INC-1041",
        "title": "auth-service pods crash looping after config rollout",
        "severity": "sev2",
        "status": "mitigated",
        "service": "auth-service",
        "namespace": "default",
        "assignee": "Marco B.",
        "opened_minutes_ago": 126,
        "resolved_minutes_ago": None,
        "summary": "auth-service restarted 4 times in 5 minutes with OOMKilled after a config map change.",
        "root_cause": "Session cache size raised to 512Mi against a 256Mi container memory limit.",
        "linked_alerts": ["PodCrashLooping"],
        "updates": [
            (126, "Alertmanager", "Incident opened from alert PodCrashLooping"),
            (96, "Marco B.", "Rolled back auth-config to the previous revision - pods stable"),
        ],
    },
    {
        "id": "INC-1040",
        "title": "Disk pressure on node worker-1",
        "severity": "sev3",
        "status": "open",
        "service": "platform",
        "namespace": "kube-system",
        "assignee": "Unassigned",
        "opened_minutes_ago": 212,
        "resolved_minutes_ago": None,
        "summary": "Available disk on worker-1 has been under 15% for three hours.",
        "root_cause": None,
        "linked_alerts": ["DiskPressure"],
        "updates": [(212, "Alertmanager", "Incident opened from alert DiskPressure")],
    },
    {
        "id": "INC-1039",
        "title": "Ingest pipeline lag above 10 minutes",
        "severity": "sev2",
        "status": "resolved",
        "service": "ingest-controller",
        "namespace": "platform",
        "assignee": "Dana K.",
        "opened_minutes_ago": 1490,
        "resolved_minutes_ago": 1370,
        "summary": "Consumer lag grew to 11 minutes after a broker restart, delaying metrics ingestion.",
        "root_cause": "Consumer group rebalance stalled on a partition owned by a terminated pod.",
        "linked_alerts": ["IngestLagHigh"],
        "updates": [
            (1490, "Alertmanager", "Incident opened from alert IngestLagHigh"),
            (1370, "Dana K.", "Lag back under 30s - resolved"),
        ],
    },
]


async def seed_demo_incidents(settings: Settings) -> None:
    if not settings.seed_demo_data:
        return

    if await repository.count_incidents(settings) > 0:
        return

    pool = await db.ensure_pool(settings)
    async with pool.acquire() as connection:
        async with connection.transaction():
            for incident in _DEMO_INCIDENTS:
                await connection.execute(
                    """
                    INSERT INTO incidents
                        (id, title, severity, status, service, namespace, assignee,
                         opened_at, resolved_at, summary, root_cause, linked_alerts)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                    """,
                    incident["id"],
                    incident["title"],
                    incident["severity"],
                    incident["status"],
                    incident["service"],
                    incident["namespace"],
                    incident["assignee"],
                    _minutes_ago(incident["opened_minutes_ago"]),
                    _minutes_ago(incident["resolved_minutes_ago"])
                    if incident["resolved_minutes_ago"] is not None
                    else None,
                    incident["summary"],
                    incident["root_cause"],
                    incident["linked_alerts"],
                )
                for minutes, actor, body in incident["updates"]:
                    await connection.execute(
                        "INSERT INTO incident_updates (incident_id, at, actor, body) VALUES ($1, $2, $3, $4)",
                        incident["id"],
                        _minutes_ago(minutes),
                        actor,
                        body,
                    )

            # Keep generated ids clear of the seeded ones.
            await connection.execute("SELECT setval('incident_number_seq', 1043, false)")

    logger.info("seeded %d demo incidents", len(_DEMO_INCIDENTS))
