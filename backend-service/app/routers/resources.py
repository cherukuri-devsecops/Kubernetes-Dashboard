"""
/api/resources — generic K8s resource CRUD (YAML get / apply / delete).
Moved from ui-service so the UI has no direct K8s connection for writes either.
"""
import json
import logging

import yaml as _yaml
from fastapi import APIRouter, Depends, Path, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from kubernetes import dynamic
from kubernetes.client import ApiClient
from kubernetes.client.rest import ApiException

from ..k8s_client import _header_dep

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/resources", tags=["resources"])

KIND_TO_PLURAL: dict[str, str] = {
    "Pod": "pods", "Deployment": "deployments", "StatefulSet": "statefulsets",
    "DaemonSet": "daemonsets", "ReplicaSet": "replicasets", "Job": "jobs",
    "CronJob": "cronjobs", "Service": "services", "Ingress": "ingresses",
    "ConfigMap": "configmaps", "Secret": "secrets", "Namespace": "namespaces",
    "Node": "nodes", "PersistentVolumeClaim": "pvcs", "PersistentVolume": "pvs",
    "ServiceAccount": "serviceaccounts",
}

_KIND_META: dict[str, tuple[str, bool]] = {
    "Pod":                   ("v1", True),
    "Deployment":            ("apps/v1", True),
    "StatefulSet":           ("apps/v1", True),
    "DaemonSet":             ("apps/v1", True),
    "ReplicaSet":            ("apps/v1", True),
    "Job":                   ("batch/v1", True),
    "CronJob":               ("batch/v1", True),
    "Service":               ("v1", True),
    "ConfigMap":             ("v1", True),
    "Secret":                ("v1", True),
    "ServiceAccount":        ("v1", True),
    "Ingress":               ("networking.k8s.io/v1", True),
    "PersistentVolumeClaim": ("v1", True),
    "PersistentVolume":      ("v1", False),
    "Namespace":             ("v1", False),
    "Node":                  ("v1", False),
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


def _plural_for(kind: str) -> str:
    return KIND_TO_PLURAL.get(kind, kind.lower() + "s")


def _clean_for_editor(obj_dict: dict) -> dict:
    meta = obj_dict.get("metadata", {})
    for f in ("managedFields", "selfLink"):
        meta.pop(f, None)
    obj_dict.pop("status", None)
    obj_dict["metadata"] = meta
    return obj_dict


# ── GET YAML ──────────────────────────────────────────────────────────────────

@router.get("/{kind}/{ns}/{name}/yaml")
def get_resource_yaml(
    kind: str     = Path(...),
    ns: str       = Path(...),
    name: str     = Path(...),
    ac: ApiClient = Depends(_header_dep),
):
    plural = _plural_for(kind)
    try:
        dyn_client = dynamic.DynamicClient(ac)
        api_ver, namespaced = _KIND_META.get(kind, ("v1", True))
        resource = dyn_client.resources.get(api_version=api_ver, kind=kind)

        if namespaced and ns and ns != "_":
            obj = resource.get(name=name, namespace=ns)
        else:
            obj = resource.get(name=name)

        obj_dict = obj.to_dict()
        _clean_for_editor(obj_dict)
        yaml_text = _yaml.safe_dump(obj_dict, sort_keys=False,
                                    default_flow_style=False, width=120)
        return {"yaml": yaml_text, "kind": kind, "name": name, "ns": ns}

    except ApiException as e:
        raise HTTPException(status_code=e.status, detail=e.reason or str(e))
    except Exception as e:
        logger.error("get_resource_yaml %s/%s/%s: %s", kind, ns, name, e)
        raise HTTPException(status_code=500, detail=str(e))


# ── APPLY ─────────────────────────────────────────────────────────────────────

class ApplyBody(BaseModel):
    yaml: str


@router.post("/apply")
def apply_resource(body: ApplyBody, ac: ApiClient = Depends(_header_dep)):
    yaml_text = body.yaml.strip()
    if not yaml_text:
        raise HTTPException(status_code=400, detail="No YAML provided")

    try:
        obj_dict = _yaml.safe_load(yaml_text)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid YAML: {e}")

    if not isinstance(obj_dict, dict):
        raise HTTPException(status_code=400, detail="YAML must be a mapping (object)")

    kind    = obj_dict.get("kind", "")
    api_ver = obj_dict.get("apiVersion", "v1")
    meta    = obj_dict.get("metadata", {})
    name    = meta.get("name", "")
    ns      = meta.get("namespace", "")

    if not kind or not name:
        raise HTTPException(status_code=400, detail="kind and metadata.name are required")

    try:
        dyn_client = dynamic.DynamicClient(ac)
        resource   = dyn_client.resources.get(api_version=api_ver, kind=kind)
        action = "created"
        try:
            existing = resource.get(name=name, namespace=ns or None)
            rv = (existing.metadata or {}).resource_version
            if rv and not meta.get("resourceVersion"):
                obj_dict.setdefault("metadata", {})["resourceVersion"] = rv
            result = (resource.replace(body=obj_dict, name=name, namespace=ns)
                      if ns else resource.replace(body=obj_dict, name=name))
            action = "updated"
        except (ApiException, Exception) as inner:
            if getattr(inner, "status", None) == 404 or "Not Found" in str(inner):
                result = (resource.create(body=obj_dict, namespace=ns)
                          if ns else resource.create(body=obj_dict))
            else:
                raise

        return {"ok": True, "action": action, "kind": kind, "name": name}

    except ApiException as e:
        msg = ""
        try:
            bd  = json.loads(e.body or "{}")
            msg = bd.get("message", "")
        except Exception:
            msg = str(e.body or "")
        raise HTTPException(status_code=e.status, detail=msg or e.reason or str(e))
    except Exception as e:
        logger.error("apply_resource %s/%s: %s", kind, name, e)
        raise HTTPException(status_code=500, detail=str(e))


# ── DELETE ────────────────────────────────────────────────────────────────────

@router.post("/{kind}/{ns}/{name}/delete")
def delete_resource(
    kind: str     = Path(...),
    ns: str       = Path(...),
    name: str     = Path(...),
    ac: ApiClient = Depends(_header_dep),
):
    ns_ = "" if ns == "_" else ns
    try:
        dyn_client = dynamic.DynamicClient(ac)
        api_ver, namespaced = _KIND_META.get(kind, ("v1", True))
        resource = dyn_client.resources.get(api_version=api_ver, kind=kind)

        if namespaced and ns_:
            resource.delete(name=name, namespace=ns_)
        else:
            resource.delete(name=name)

        return {"ok": True}

    except ApiException as e:
        raise HTTPException(status_code=e.status, detail=e.reason or str(e))
    except Exception as e:
        logger.error("delete_resource %s/%s/%s: %s", kind, ns, name, e)
        raise HTTPException(status_code=500, detail=str(e))


# ── DOCS URL ─────────────────────────────────────────────────────────────────

@router.get("/docs/{kind}")
def resource_docs(kind: str = Path(...)):
    path = _KIND_DOCS.get(kind, "")
    return {"url": _DOCS_BASE + path if path else _DOCS_BASE, "kind": kind}
