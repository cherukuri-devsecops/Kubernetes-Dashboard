"""
Observability backend: replaces PostgreSQL with Loki (logs/events/audit)
and SQLite (user config data).

Public API is kept stable so existing routes need minimal changes.
"""
import json
import logging

from flask import session

from .loki_client import push_entry
from .storage import (
    storage_init,
    save_kubeconfig, get_kubeconfig, list_kubeconfigs, delete_kubeconfig,
    get_annotations,
)

logger = logging.getLogger(__name__)


def db_init():
    storage_init()


def db_ready() -> bool:
    """Always True — SQLite is the user-data backend and requires no external service."""
    return True


# ── Audit ─────────────────────────────────────────────────────────────────────

def audit(action: str, target: str = None, **details):
    """Fire-and-forget: push an audit entry to Loki."""
    try:
        user_email = ""
        try:
            user_email = (session.get("user") or {}).get("email", "")
        except Exception:
            pass
        push_entry("k8s-audit", {}, {
            "user_email": user_email,
            "action":     action,
            "target":     target or "",
            "details":    json.dumps(details) if details else None,
        })
    except Exception as e:
        logger.debug("audit push failed: %s", e)


# ── Annotations (delegated to SQLite) ─────────────────────────────────────────

def _annotations_for(kind: str, ns: str, name: str):
    from .cache import _cache_scope
    return get_annotations(_cache_scope(), kind, ns or "", name)
