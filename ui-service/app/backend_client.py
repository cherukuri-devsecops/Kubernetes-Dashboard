"""
HTTP client used by the Flask ui-service to call the FastAPI backend-service.

Reads the current session and adds the required X-* auth headers on every request.
All Kubernetes data fetching goes through here — the UI has no direct K8s connection
for page rendering (only streaming routes keep a direct connection).
"""
import base64
import logging

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from flask import session

from .config import BACKEND_SERVICE_URL
from .storage import get_kubeconfig

logger = logging.getLogger(__name__)

_TIMEOUT = 30

# Persistent session with connection pooling — avoids TCP handshake on every call.
# pool_connections=4 = 4 connection pools (one per unique host); pool_maxsize=20
# means up to 20 idle keep-alive connections per pool (enough for parallel fan-out).
_session = requests.Session()
_adapter = HTTPAdapter(
    pool_connections=4,
    pool_maxsize=20,
    max_retries=Retry(total=0),  # no retries — let callers decide
)
_session.mount("http://", _adapter)
_session.mount("https://", _adapter)


def _auth_headers() -> dict:
    mode = session.get("cluster_mode", "local")
    headers: dict = {"X-Auth-Mode": mode}

    if mode == "incluster":
        pass

    elif mode == "token":
        cfg = session.get("cluster_token") or {}
        headers["X-K8s-Token"]  = cfg.get("token", "")
        headers["X-K8s-Server"] = cfg.get("server", "")

    elif mode == "kubeconfig":
        email   = (session.get("user") or {}).get("email", "")
        kc_name = session.get("active_kubeconfig", "default")
        content = get_kubeconfig(email, kc_name)
        if content:
            headers["X-Kubeconfig-B64"] = base64.b64encode(content.encode()).decode()

    ctx = session.get("context")
    if ctx:
        headers["X-K8s-Context"] = ctx

    return headers


def get(path: str, **params) -> dict | list:
    url  = BACKEND_SERVICE_URL.rstrip("/") + path
    hdrs = _auth_headers()
    try:
        resp = _session.get(url, headers=hdrs, params=params, timeout=_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except requests.HTTPError as e:
        logger.error("backend GET %s → %s: %s", path, e.response.status_code, e.response.text[:300])
        raise
    except requests.RequestException as e:
        logger.error("backend GET %s failed: %s", path, e)
        raise


def post(path: str, json_body: dict | None = None) -> dict:
    url  = BACKEND_SERVICE_URL.rstrip("/") + path
    hdrs = _auth_headers()
    try:
        resp = _session.post(url, headers=hdrs, json=json_body, timeout=_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except requests.HTTPError as e:
        logger.error("backend POST %s → %s: %s", path, e.response.status_code, e.response.text[:300])
        raise
    except requests.RequestException as e:
        logger.error("backend POST %s failed: %s", path, e)
        raise


# ── /api/raw/* ── raw snake_case K8s objects ──────────────────────────────────

def raw_pods(namespace: str = "", node: str = "") -> list:
    params = {}
    if namespace: params["namespace"] = namespace
    if node:      params["node"]      = node
    return get("/api/raw/pods", **params)

def raw_pod(namespace: str, name: str) -> dict:
    return get(f"/api/raw/pods/{namespace}/{name}")

def raw_pod_logs(namespace: str, name: str, container: str = "",
                 tail: int = 300, previous: bool = False) -> str:
    params = {"tail": tail, "previous": previous}
    if container: params["container"] = container
    return get(f"/api/raw/pods/{namespace}/{name}/logs", **params).get("logs", "")

def raw_namespaces() -> list:
    return get("/api/raw/namespaces")

def raw_nodes() -> list:
    return get("/api/raw/nodes")

def raw_node(name: str) -> dict:
    return get(f"/api/raw/nodes/{name}")

def raw_services(namespace: str = "") -> list:
    params = {"namespace": namespace} if namespace else {}
    return get("/api/raw/services", **params)

def raw_deployments(namespace: str = "") -> list:
    params = {"namespace": namespace} if namespace else {}
    return get("/api/raw/deployments", **params)

def raw_deployment(namespace: str, name: str) -> dict:
    return get(f"/api/raw/deployments/{namespace}/{name}")

def scale_deployment(namespace: str, name: str, replicas: int) -> dict:
    return post(f"/api/raw/deployments/{namespace}/{name}/scale", json_body={"replicas": replicas})

def raw_service(namespace: str, name: str) -> dict:
    return get(f"/api/raw/services/{namespace}/{name}")

def raw_ingress(namespace: str, name: str) -> dict:
    return get(f"/api/raw/ingresses/{namespace}/{name}")

def raw_statefulset(namespace: str, name: str) -> dict:
    return get(f"/api/raw/statefulsets/{namespace}/{name}")

def scale_statefulset(namespace: str, name: str, replicas: int) -> dict:
    return post(f"/api/raw/statefulsets/{namespace}/{name}/scale", json_body={"replicas": replicas})

def raw_daemonset(namespace: str, name: str) -> dict:
    return get(f"/api/raw/daemonsets/{namespace}/{name}")

def raw_job(namespace: str, name: str) -> dict:
    return get(f"/api/raw/jobs/{namespace}/{name}")

def raw_cronjob(namespace: str, name: str) -> dict:
    return get(f"/api/raw/cronjobs/{namespace}/{name}")

def raw_pv(name: str) -> dict:
    return get(f"/api/raw/pvs/{name}")

def raw_pvc(namespace: str, name: str) -> dict:
    return get(f"/api/raw/pvcs/{namespace}/{name}")

def raw_configmap(namespace: str, name: str) -> dict:
    return get(f"/api/raw/configmaps/{namespace}/{name}")

def raw_secret(namespace: str, name: str) -> dict:
    return get(f"/api/raw/secrets/{namespace}/{name}")

def raw_statefulsets(namespace: str = "") -> list:
    params = {"namespace": namespace} if namespace else {}
    return get("/api/raw/statefulsets", **params)

def raw_daemonsets(namespace: str = "") -> list:
    params = {"namespace": namespace} if namespace else {}
    return get("/api/raw/daemonsets", **params)

def raw_jobs(namespace: str = "") -> list:
    params = {"namespace": namespace} if namespace else {}
    return get("/api/raw/jobs", **params)

def raw_cronjobs(namespace: str = "") -> list:
    params = {"namespace": namespace} if namespace else {}
    return get("/api/raw/cronjobs", **params)

def raw_pvs() -> list:
    return get("/api/raw/pvs")

def raw_pvcs(namespace: str = "") -> list:
    params = {"namespace": namespace} if namespace else {}
    return get("/api/raw/pvcs", **params)

def raw_configmaps(namespace: str = "") -> list:
    params = {"namespace": namespace} if namespace else {}
    return get("/api/raw/configmaps", **params)

def raw_secrets(namespace: str = "") -> list:
    params = {"namespace": namespace} if namespace else {}
    return get("/api/raw/secrets", **params)

def raw_ingresses(namespace: str = "") -> list:
    params = {"namespace": namespace} if namespace else {}
    return get("/api/raw/ingresses", **params)

def raw_events(namespace: str = "", kind: str = "", name: str = "") -> list:
    params = {}
    if namespace: params["namespace"] = namespace
    if kind:      params["kind"]      = kind
    if name:      params["name"]      = name
    return get("/api/raw/events", **params)

def raw_node_metrics() -> list:
    return get("/api/raw/node_metrics")

def raw_pod_metrics(namespace: str = "") -> list:
    params = {"namespace": namespace} if namespace else {}
    return get("/api/raw/pod_metrics", **params)

def raw_quotas(namespace: str = "") -> list:
    params = {"namespace": namespace} if namespace else {}
    return get("/api/raw/quotas", **params)

def raw_version() -> dict:
    return get("/api/raw/version")


# ── /api/resources/* ── YAML CRUD ─────────────────────────────────────────────

def resource_yaml(kind: str, ns: str, name: str) -> dict:
    return get(f"/api/resources/{kind}/{ns}/{name}/yaml")

def resource_apply(yaml_text: str) -> dict:
    return post("/api/resources/apply", json_body={"yaml": yaml_text})

def resource_delete(kind: str, ns: str, name: str) -> dict:
    return post(f"/api/resources/{kind}/{ns}/{name}/delete")

def resource_docs(kind: str) -> dict:
    return get(f"/api/resources/docs/{kind}")


def apm_metrics() -> dict:
    return get("/api/metrics/apm")

def apm_breakdown_metrics() -> dict:
    return get("/api/metrics/apm/breakdown")

def apm_transactions(hours: int = 1, limit: int = 30) -> dict:
    return get("/api/metrics/apm/transactions", hours=hours, limit=limit)

def apm_errors(hours: int = 1) -> dict:
    return get("/api/metrics/apm/errors", hours=hours)

def apm_timeseries(hours: int = 1) -> dict:
    return get("/api/metrics/apm/timeseries", hours=hours)

def apm_traces(service: str = "", hours: int = 1, limit: int = 50) -> dict:
    return get("/api/traces/search", service=service, hours=hours, limit=limit)

def apm_trace_detail(trace_id: str) -> dict:
    return get(f"/api/traces/{trace_id}")


def rbac_check(verb: str, kind: str, ns: str = "") -> bool:
    try:
        return get("/api/rbac/check", verb=verb, kind=kind, ns=ns).get("allowed", True)
    except Exception:
        return True

def rbac_matrix_cached() -> dict:
    try:
        return get("/api/rbac/matrix")
    except Exception:
        return {}
