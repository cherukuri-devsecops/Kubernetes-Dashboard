"""
Generic resource CRUD routes — all K8s operations proxied through backend-service.

  GET  /resources/<Kind>/<ns>/<name>/yaml   → fetch YAML for the editor
  POST /resources/apply                     → create or replace any resource
  POST /resources/<Kind>/<ns>/<name>/delete → delete any resource
  GET  /resources/docs/<Kind>               → return the K8s docs URL
  GET  /resources/rbac                      → per-kind RBAC matrix for this user
"""
import logging

import requests
import yaml as _yaml
from flask import Blueprint, jsonify, request

from ..auth_utils import cluster_required
from ..cache import cache_invalidate
from ..database import audit
from .. import backend_client as _bc

KIND_TO_PLURAL: dict[str, str] = {
    "Pod": "pods", "Deployment": "deployments", "StatefulSet": "statefulsets",
    "DaemonSet": "daemonsets", "ReplicaSet": "replicasets", "Job": "jobs",
    "CronJob": "cronjobs", "Service": "services", "Ingress": "ingresses",
    "ConfigMap": "configmaps", "Secret": "secrets", "Namespace": "namespaces",
    "Node": "nodes", "PersistentVolumeClaim": "pvcs", "PersistentVolume": "pvs",
    "ServiceAccount": "serviceaccounts",
}

_DOCS_BASE = "https://kubernetes.io/docs/reference/kubernetes-api/"
_KIND_DOCS: dict[str, str] = {
    "Pod":                   "workload-resources/pod-v1/",
    "Deployment":            "workload-resources/deployment-v1/",
    "StatefulSet":           "workload-resources/stateful-set-v1/",
    "DaemonSet":             "workload-resources/daemon-set-v1/",
    "ReplicaSet":            "workload-resources/replica-set-v1/",
    "Job":                   "workload-resources/job-v1/",
    "CronJob":               "workload-resources/cron-job-v1/",
    "Service":               "service-resources/service-v1/",
    "Ingress":               "service-resources/ingress-v1/",
    "ConfigMap":             "config-and-storage-resources/config-map-v1/",
    "Secret":                "config-and-storage-resources/secret-v1/",
    "PersistentVolume":      "config-and-storage-resources/persistent-volume-v1/",
    "PersistentVolumeClaim": "config-and-storage-resources/persistent-volume-claim-v1/",
    "Namespace":             "cluster-resources/namespace-v1/",
    "Node":                  "cluster-resources/node-v1/",
    "ServiceAccount":        "authentication-resources/service-account-v1/",
}

logger = logging.getLogger(__name__)

resources_bp = Blueprint("resources", __name__)


def _plural_for(kind: str) -> str:
    return KIND_TO_PLURAL.get(kind, kind.lower() + "s")


def _http_err(e: requests.HTTPError) -> tuple[dict, int]:
    status = e.response.status_code
    try:
        msg = e.response.json().get("detail", str(e))
    except Exception:
        msg = str(e)
    return {"error": msg}, status


# ── GET YAML ──────────────────────────────────────────────────────────────────

@resources_bp.route("/resources/<kind>/<ns>/<name>/yaml")
@cluster_required
def get_resource_yaml(kind: str, ns: str, name: str):
    ns_ = "" if ns == "_" else ns
    if not _bc.rbac_check("get", _plural_for(kind), ns_):
        return jsonify({"error": f"Permission denied: cannot get {kind}"}), 403
    try:
        return jsonify(_bc.resource_yaml(kind, ns, name))
    except requests.HTTPError as e:
        body, status = _http_err(e)
        return jsonify(body), status
    except Exception as e:
        logger.error("get_resource_yaml %s/%s/%s: %s", kind, ns, name, e)
        return jsonify({"error": str(e)}), 500


# ── APPLY (create / replace) ──────────────────────────────────────────────────

@resources_bp.route("/resources/apply", methods=["POST"])
@cluster_required
def apply_resource():
    data = request.get_json(silent=True) or {}
    yaml_text = data.get("yaml", "").strip()

    if not yaml_text:
        return jsonify({"error": "No YAML provided"}), 400

    try:
        obj_dict = _yaml.safe_load(yaml_text)
    except Exception as e:
        return jsonify({"error": f"Invalid YAML: {e}"}), 400

    if not isinstance(obj_dict, dict):
        return jsonify({"error": "YAML must be a mapping (object)"}), 400

    kind    = obj_dict.get("kind", "")
    api_ver = obj_dict.get("apiVersion", "v1")
    meta    = obj_dict.get("metadata", {})
    name    = meta.get("name", "")
    ns      = meta.get("namespace", "")

    if not kind or not name:
        return jsonify({"error": "kind and metadata.name are required"}), 400

    plural = _plural_for(kind)
    if not _bc.rbac_check("update", plural, ns) and not _bc.rbac_check("create", plural, ns):
        return jsonify({"error": f"Permission denied: cannot apply {kind}"}), 403

    try:
        result = _bc.resource_apply(yaml_text)
        action = result.get("action", "applied")
        target = f"{kind}/{ns}/{name}" if ns else f"{kind}/{name}"
        audit(f"resource.{action}", target=target, kind=kind, api_version=api_ver)
        cache_invalidate()
        return jsonify(result)
    except requests.HTTPError as e:
        body, status = _http_err(e)
        return jsonify(body), status
    except Exception as e:
        logger.error("apply_resource %s/%s: %s", kind, name, e)
        return jsonify({"error": str(e)}), 500


# ── DELETE ────────────────────────────────────────────────────────────────────

@resources_bp.route("/resources/<kind>/<ns>/<name>/delete", methods=["POST"])
@cluster_required
def delete_resource(kind: str, ns: str, name: str):
    ns_ = "" if ns == "_" else ns
    if not _bc.rbac_check("delete", _plural_for(kind), ns_):
        return jsonify({"error": f"Permission denied: cannot delete {kind}"}), 403
    try:
        result = _bc.resource_delete(kind, ns, name)
        target = f"{kind}/{ns_}/{name}" if ns_ else f"{kind}/{name}"
        audit("resource.delete", target=target, kind=kind)
        cache_invalidate()
        return jsonify(result)
    except requests.HTTPError as e:
        body, status = _http_err(e)
        return jsonify(body), status
    except Exception as e:
        logger.error("delete_resource %s/%s/%s: %s", kind, ns, name, e)
        return jsonify({"error": str(e)}), 500


# ── DOCS URL ─────────────────────────────────────────────────────────────────

@resources_bp.route("/resources/docs/<kind>")
@cluster_required
def resource_docs(kind: str):
    path = _KIND_DOCS.get(kind, "")
    url  = _DOCS_BASE + path if path else _DOCS_BASE
    return jsonify({"url": url, "kind": kind})


# ── RBAC MATRIX ───────────────────────────────────────────────────────────────

@resources_bp.route("/resources/rbac")
@cluster_required
def rbac_json():
    try:
        return jsonify(_bc.get("/api/rbac/matrix"))
    except Exception as e:
        logger.error("rbac_json backend call failed: %s", e)
        return jsonify({}), 502
