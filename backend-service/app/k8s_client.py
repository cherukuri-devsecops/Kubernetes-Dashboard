"""
K8s API client factory — reads auth credentials from request headers.

Headers accepted (set by ui-service):
  X-Auth-Mode       : kubeconfig | token | incluster | local
  X-Kubeconfig-B64  : base64-encoded kubeconfig YAML  (kubeconfig mode)
  X-K8s-Token       : bearer token                    (token mode)
  X-K8s-Server      : API server URL                  (token mode)
  X-K8s-Context     : context name to activate        (kubeconfig / local)
"""
import base64
import logging

import yaml
from fastapi import Header, HTTPException
from kubernetes import client, config
from kubernetes.client import ApiClient

logger = logging.getLogger(__name__)


def _api_client(
    x_auth_mode: str = "local",
    x_kubeconfig_b64: str = "",
    x_k8s_token: str = "",
    x_k8s_server: str = "",
    x_k8s_context: str = "",
) -> ApiClient:
    mode = (x_auth_mode or "local").lower()

    if mode == "incluster":
        config.load_incluster_config()
        return ApiClient()

    if mode == "token":
        if not x_k8s_token or not x_k8s_server:
            raise HTTPException(status_code=400, detail="X-K8s-Token and X-K8s-Server required for token mode")
        c = client.Configuration()
        c.host = x_k8s_server
        c.api_key = {"authorization": f"Bearer {x_k8s_token}"}
        c.verify_ssl = False
        return ApiClient(c)

    if mode == "kubeconfig":
        if not x_kubeconfig_b64:
            raise HTTPException(status_code=400, detail="X-Kubeconfig-B64 required for kubeconfig mode")
        try:
            content = base64.b64decode(x_kubeconfig_b64).decode()
            config_dict = yaml.safe_load(content)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid kubeconfig: {e}")
        c = client.Configuration()
        config.load_kube_config_from_dict(
            config_dict,
            context=x_k8s_context or None,
            persist_config=False,
            client_configuration=c,
        )
        return ApiClient(c)

    # local — use ~/.kube/config or in-cluster
    try:
        c = client.Configuration()
        config.load_kube_config(
            context=x_k8s_context or None,
            client_configuration=c,
        )
        return ApiClient(c)
    except Exception:
        config.load_incluster_config()
        return ApiClient()


# FastAPI dependency factories

def _header_dep(x_auth_mode: str = Header(default="local"),
                x_kubeconfig_b64: str = Header(default=""),
                x_k8s_token: str = Header(default=""),
                x_k8s_server: str = Header(default=""),
                x_k8s_context: str = Header(default="")) -> ApiClient:
    return _api_client(x_auth_mode, x_kubeconfig_b64, x_k8s_token, x_k8s_server, x_k8s_context)


def core_v1(ac: ApiClient) -> client.CoreV1Api:
    return client.CoreV1Api(ac)


def apps_v1(ac: ApiClient) -> client.AppsV1Api:
    return client.AppsV1Api(ac)


def batch_v1(ac: ApiClient) -> client.BatchV1Api:
    return client.BatchV1Api(ac)


def net_v1(ac: ApiClient) -> client.NetworkingV1Api:
    return client.NetworkingV1Api(ac)


def custom_api(ac: ApiClient) -> client.CustomObjectsApi:
    return client.CustomObjectsApi(ac)


def version_api(ac: ApiClient) -> client.VersionApi:
    return client.VersionApi(ac)
