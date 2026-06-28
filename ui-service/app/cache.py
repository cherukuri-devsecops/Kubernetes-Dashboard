import hashlib
import logging

from flask import session

from .config import CLUSTER_SCOPE as _DEFAULT_SCOPE
from .formatters import ready_count, restarts

logger = logging.getLogger(__name__)


def _cache_scope() -> str:
    """Stable cluster-scope label for Loki queries.

    Must match the label used by backend pollers (CLUSTER_SCOPE env var).
    For kubeconfig mode with DB storage, kubeconfig_path is not set in the
    session, so we fall back to CLUSTER_SCOPE rather than returning 'kc::'.
    """
    mode = session.get("cluster_mode", "local")
    ctx  = session.get("context") or ""
    if mode == "kubeconfig":
        kc_id = session.get("kubeconfig_path") or session.get("active_kubeconfig", "")
        if kc_id:
            return f"kc:{kc_id}:{ctx}"
        return _DEFAULT_SCOPE
    if mode == "token":
        server = (session.get("cluster_token") or {}).get("server", "")
        return f"tk:{server}" if server else _DEFAULT_SCOPE
    return f"{mode}:{ctx}" if ctx else mode


def pod_state_signature(pods) -> str:
    """Stable hash of pod list state used by HTMX polling to detect changes."""
    parts = []
    for p in pods:
        rc, tc = ready_count(p)
        dt = p.metadata.deletion_timestamp
        deletion_ts = dt if isinstance(dt, str) else (dt.isoformat() if dt else "")
        parts.append("|".join((
            p.metadata.namespace or "",
            p.metadata.name or "",
            p.status.phase or "",
            str(rc), str(tc),
            str(restarts(p)),
            p.spec.node_name or "",
            p.status.pod_ip or "",
            deletion_ts,
        )))
    raw = "\n".join(sorted(parts)).encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:16]


def cache_invalidate():
    """No-op — K8s data is no longer cached in the UI; backend handles caching."""
    pass
