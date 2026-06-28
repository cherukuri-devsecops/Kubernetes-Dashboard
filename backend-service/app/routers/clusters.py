"""GET /api/clusters — list available K8s contexts from the provided kubeconfig."""
import base64
import logging

import yaml
from fastapi import APIRouter, Header, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/clusters", tags=["clusters"])


@router.get("")
def list_clusters(
    x_auth_mode: str = Header(default="local"),
    x_kubeconfig_b64: str = Header(default=""),
    x_k8s_context: str = Header(default=""),
):
    """Return available contexts and the currently active one."""
    if x_auth_mode == "kubeconfig" and x_kubeconfig_b64:
        try:
            content = base64.b64decode(x_kubeconfig_b64).decode()
            cfg = yaml.safe_load(content) or {}
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid kubeconfig: {e}")

        contexts = [c["name"] for c in cfg.get("contexts", [])]
        current = x_k8s_context or cfg.get("current-context", "")
        return {
            "mode": "kubeconfig",
            "contexts": contexts,
            "active": current,
        }

    if x_auth_mode == "token":
        return {"mode": "token", "contexts": ["token-cluster"], "active": "token-cluster"}

    if x_auth_mode == "incluster":
        return {"mode": "incluster", "contexts": ["in-cluster"], "active": "in-cluster"}

    # local — read ~/.kube/config
    try:
        from kubernetes import config as kconf
        contexts, active = kconf.list_kube_config_contexts()
        names = [c["name"] for c in contexts]
        active_name = active["name"] if active else ""
        return {"mode": "local", "contexts": names, "active": x_k8s_context or active_name}
    except Exception as e:
        logger.warning("list_clusters local: %s", e)
        return {"mode": "local", "contexts": [], "active": ""}
