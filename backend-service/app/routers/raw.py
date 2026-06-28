"""/api/raw — full K8s objects serialized as snake_case JSON dicts."""
import re
import logging
import threading
import time

from fastapi import APIRouter, Depends, Path, Query, HTTPException, Request
from kubernetes import client
from kubernetes.client import ApiClient
from pydantic import BaseModel

from ..k8s_client import _header_dep, core_v1, apps_v1, batch_v1, net_v1, custom_api
from ..utils import parse_cpu as _parse_cpu, parse_mem as _parse_mem

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/raw", tags=["raw"])

_ser = ApiClient()
_KW_RENAMES = {"exec": "_exec"}

# ── Simple per-cluster TTL cache ──────────────────────────────────────────────
_cache: dict = {}
_cache_lock = threading.Lock()


def _cache_key(ac: ApiClient, tag: str) -> str:
    cfg = ac.configuration
    return f"{tag}|{getattr(cfg, 'host', 'local')}"


def _cached(ac: ApiClient, tag: str, ttl: int, fn):
    key = _cache_key(ac, tag)
    now = time.monotonic()
    with _cache_lock:
        entry = _cache.get(key)
        if entry and now - entry[0] < ttl:
            return entry[1]
    try:
        result = fn()
    except Exception as e:
        logger.warning("K8s fetch error (%s): %s", tag, e)
        raise HTTPException(status_code=502, detail=f"Kubernetes API error: {e}")
    with _cache_lock:
        _cache[key] = (now, result)
    return result


def _snake(name: str) -> str:
    s = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1_\2', name)
    s = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', s).lower()
    return _KW_RENAMES.get(s, s)


def _to_snake(d):
    if isinstance(d, dict):
        return {_snake(k): _to_snake(v) for k, v in d.items()}
    if isinstance(d, list):
        return [_to_snake(i) for i in d]
    return d


def _raw(obj) -> dict:
    return _to_snake(_ser.sanitize_for_serialization(obj))


def _raw_list(items) -> list:
    return [_raw(i) for i in items]


# ── Pods ──────────────────────────────────────────────────────────────────────

@router.get("/pods")
def raw_pods(
    namespace: str = Query(default=""),
    node: str      = Query(default=""),
    ac: ApiClient  = Depends(_header_dep),
):
    core = core_v1(ac)
    cust = custom_api(ac)

    field_sel = f"spec.nodeName={node}" if node else None
    cache_tag = f"pods:{namespace}:{node}"

    def _fetch():
        if namespace:
            items = core.list_namespaced_pod(namespace, field_selector=field_sel).items
        else:
            items = core.list_pod_for_all_namespaces(field_selector=field_sel).items

        pm_map: dict = {}
        try:
            pm = cust.list_cluster_custom_object("metrics.k8s.io", "v1beta1", "pods")
            for item in pm.get("items", []):
                k = f"{item['metadata']['namespace']}/{item['metadata']['name']}"
                pm_map[k] = item
        except Exception:
            pass

        result = []
        for p in items:
            d = _raw(p)
            k = f"{p.metadata.namespace}/{p.metadata.name}"
            if k in pm_map:
                ctrs = pm_map[k].get("containers", [])
                cpu_m = sum(_parse_cpu(c["usage"]["cpu"])    for c in ctrs if "usage" in c)
                mem_b = sum(_parse_mem(c["usage"]["memory"]) for c in ctrs if "usage" in c)
                d["_metrics"] = {"cpu_m": round(cpu_m), "mem_b": mem_b}
            result.append(d)
        return result

    return _cached(ac, cache_tag, 10, _fetch)


@router.get("/pods/{namespace}/{name}")
def raw_pod(
    namespace: str = Path(...),
    name: str      = Path(...),
    ac: ApiClient  = Depends(_header_dep),
):
    core = core_v1(ac)
    cust = custom_api(ac)
    apps = apps_v1(ac)

    try:
        p = core.read_namespaced_pod(name, namespace)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

    d = _raw(p)

    # Per-container metrics from metrics-server
    try:
        pm = cust.get_namespaced_custom_object(
            "metrics.k8s.io", "v1beta1", namespace, "pods", name)
        d["_ctr_metrics"] = {
            c["name"]: {
                "cpu_m": round(_parse_cpu(c["usage"]["cpu"])),
                "mem_b": _parse_mem(c["usage"]["memory"]),
            }
            for c in pm.get("containers", [])
        }
    except Exception:
        d["_ctr_metrics"] = {}

    # Sibling pods (same owner)
    d["_siblings"] = []
    try:
        refs = p.metadata.owner_references or []
        if refs:
            ref = refs[0]
            owner_uid = ref.uid
            # Resolve ReplicaSet → Deployment owner
            if ref.kind == "ReplicaSet":
                try:
                    rs = apps.read_namespaced_replica_set(ref.name, namespace)
                    rs_owners = rs.metadata.owner_references or []
                    if rs_owners:
                        d["_owner_controller_kind"] = rs_owners[0].kind
                        d["_owner_controller_name"] = rs_owners[0].name
                except Exception:
                    pass
            # List sibling pods — use cached pod list to avoid extra K8s call
            all_pods = _cached(ac, f"pods:{namespace}:", 10,
                               lambda: core.list_namespaced_pod(namespace).items)
            siblings = []
            for sp in all_pods:
                if sp.metadata.name == name:
                    continue
                for o in (sp.metadata.owner_references or []):
                    if o.uid == owner_uid:
                        siblings.append(_raw(sp))
                        break
            d["_siblings"] = siblings
    except Exception:
        pass

    # Static log tail (for pod_detail page)
    return d


@router.get("/pods/{namespace}/{name}/logs")
def raw_pod_logs(
    namespace: str  = Path(...),
    name: str       = Path(...),
    container: str  = Query(default=""),
    tail: int       = Query(default=300),
    previous: bool  = Query(default=False),
    ac: ApiClient   = Depends(_header_dep),
):
    core = core_v1(ac)
    try:
        txt = core.read_namespaced_pod_log(
            name=name, namespace=namespace,
            container=container or None,
            tail_lines=tail,
            previous=previous,
            timestamps=True,
        )
        return {"logs": txt or ""}
    except Exception as e:
        return {"logs": f"[error: {e}]"}


# ── Namespaces ────────────────────────────────────────────────────────────────

@router.get("/namespaces")
def raw_namespaces(ac: ApiClient = Depends(_header_dep)):
    return _cached(ac, "namespaces", 60,
                   lambda: _raw_list(core_v1(ac).list_namespace().items))


# ── Nodes ─────────────────────────────────────────────────────────────────────

@router.get("/nodes")
def raw_nodes(ac: ApiClient = Depends(_header_dep)):
    def _fetch():
        core = core_v1(ac)
        cust = custom_api(ac)
        nodes = core.list_node().items
        nm_map: dict = {}
        try:
            nm = cust.list_cluster_custom_object("metrics.k8s.io", "v1beta1", "nodes")
            nm_map = {item["metadata"]["name"]: item for item in nm.get("items", [])}
        except Exception:
            pass
        result = []
        for n in nodes:
            d = _raw(n)
            nm_item = nm_map.get(n.metadata.name, {})
            d["_metrics"] = {
                "cpu":    nm_item.get("usage", {}).get("cpu", "0"),
                "memory": nm_item.get("usage", {}).get("memory", "0"),
            }
            result.append(d)
        return result

    return _cached(ac, "nodes", 20, _fetch)


@router.get("/nodes/{name}")
def raw_node(name: str = Path(...), ac: ApiClient = Depends(_header_dep)):
    core = core_v1(ac)
    cust = custom_api(ac)

    try:
        n = core.read_node(name)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

    d = _raw(n)

    # Live metrics from metrics-server
    try:
        nm = cust.get_cluster_custom_object("metrics.k8s.io", "v1beta1", "nodes", name)
        d["_metrics"] = {
            "cpu":    nm.get("usage", {}).get("cpu", "0"),
            "memory": nm.get("usage", {}).get("memory", "0"),
        }
    except Exception:
        d["_metrics"] = {}

    # Pods running on this node + their metrics
    try:
        pods = core.list_pod_for_all_namespaces(
            field_selector=f"spec.nodeName={name}").items
        pm_map: dict = {}
        try:
            pm_resp = cust.list_cluster_custom_object("metrics.k8s.io", "v1beta1", "pods")
            for item in pm_resp.get("items", []):
                k = f"{item['metadata']['namespace']}/{item['metadata']['name']}"
                ctrs = item.get("containers", [])
                pm_map[k] = {
                    "cpu_m": round(sum(_parse_cpu(c["usage"]["cpu"])    for c in ctrs if "usage" in c)),
                    "mem_b":       sum(_parse_mem(c["usage"]["memory"]) for c in ctrs if "usage" in c),
                }
        except Exception:
            pass
        d["_pods"]        = _raw_list(pods)
        d["_pod_metrics"] = pm_map
    except Exception:
        d["_pods"]        = []
        d["_pod_metrics"] = {}

    return d


# ── Services ──────────────────────────────────────────────────────────────────

@router.get("/services")
def raw_services(namespace: str = Query(default=""), ac: ApiClient = Depends(_header_dep)):
    def _fetch():
        core = core_v1(ac)
        items = (core.list_namespaced_service(namespace).items if namespace
                 else core.list_service_for_all_namespaces().items)
        return _raw_list(items)
    return _cached(ac, f"services:{namespace}", 30, _fetch)


# ── Deployments ───────────────────────────────────────────────────────────────

@router.get("/deployments")
def raw_deployments(namespace: str = Query(default=""), ac: ApiClient = Depends(_header_dep)):
    def _fetch():
        a = apps_v1(ac)
        items = (a.list_namespaced_deployment(namespace).items if namespace
                 else a.list_deployment_for_all_namespaces().items)
        return _raw_list(items)
    return _cached(ac, f"deployments:{namespace}", 30, _fetch)


class _ScaleBody(BaseModel):
    replicas: int


@router.post("/deployments/{namespace}/{name}/scale")
def scale_deployment(
    namespace: str    = Path(...),
    name: str         = Path(...),
    body: _ScaleBody  = ...,
    ac: ApiClient     = Depends(_header_dep),
):
    if body.replicas < 0:
        raise HTTPException(status_code=400, detail="replicas must be >= 0")
    apps = apps_v1(ac)
    try:
        patch = {"spec": {"replicas": body.replicas}}
        d = apps.patch_namespaced_deployment_scale(name, namespace, patch)
        return {"replicas": d.spec.replicas}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/deployments/{namespace}/{name}")
def raw_deployment(
    namespace: str = Path(...),
    name: str      = Path(...),
    ac: ApiClient  = Depends(_header_dep),
):
    apps = apps_v1(ac)
    core = core_v1(ac)

    try:
        d = apps.read_namespaced_deployment(name, namespace)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

    result = _raw(d)

    # ReplicaSets owned by this deployment
    try:
        selector = d.spec.selector.match_labels if (d.spec and d.spec.selector) else {}
        label_sel = ",".join(f"{k}={v}" for k, v in selector.items())
        rs_items = apps.list_namespaced_replica_set(namespace, label_selector=label_sel).items
        result["_replica_sets"] = _raw_list(rs_items)
    except Exception:
        result["_replica_sets"] = []

    # Pods owned by this deployment (via matching selector)
    try:
        selector = d.spec.selector.match_labels if (d.spec and d.spec.selector) else {}
        label_sel = ",".join(f"{k}={v}" for k, v in selector.items())
        pod_items = core.list_namespaced_pod(namespace, label_selector=label_sel).items
        result["_pods"] = _raw_list(pod_items)
    except Exception:
        result["_pods"] = []

    # Events for this deployment
    try:
        evts = core.list_namespaced_event(
            namespace, field_selector=f"involvedObject.name={name}").items
        result["_events"] = _raw_list(evts)
    except Exception:
        result["_events"] = []

    return result


# ── StatefulSets ──────────────────────────────────────────────────────────────

@router.get("/statefulsets")
def raw_statefulsets(namespace: str = Query(default=""), ac: ApiClient = Depends(_header_dep)):
    def _fetch():
        a = apps_v1(ac)
        items = (a.list_namespaced_stateful_set(namespace).items if namespace
                 else a.list_stateful_set_for_all_namespaces().items)
        return _raw_list(items)
    return _cached(ac, f"statefulsets:{namespace}", 30, _fetch)


# ── DaemonSets ────────────────────────────────────────────────────────────────

@router.get("/daemonsets")
def raw_daemonsets(namespace: str = Query(default=""), ac: ApiClient = Depends(_header_dep)):
    def _fetch():
        a = apps_v1(ac)
        items = (a.list_namespaced_daemon_set(namespace).items if namespace
                 else a.list_daemon_set_for_all_namespaces().items)
        return _raw_list(items)
    return _cached(ac, f"daemonsets:{namespace}", 30, _fetch)


# ── Jobs ──────────────────────────────────────────────────────────────────────

@router.get("/jobs")
def raw_jobs(namespace: str = Query(default=""), ac: ApiClient = Depends(_header_dep)):
    def _fetch():
        b = batch_v1(ac)
        items = (b.list_namespaced_job(namespace).items if namespace
                 else b.list_job_for_all_namespaces().items)
        return _raw_list(items)
    return _cached(ac, f"jobs:{namespace}", 30, _fetch)


# ── CronJobs ──────────────────────────────────────────────────────────────────

@router.get("/cronjobs")
def raw_cronjobs(namespace: str = Query(default=""), ac: ApiClient = Depends(_header_dep)):
    def _fetch():
        b = batch_v1(ac)
        items = (b.list_namespaced_cron_job(namespace).items if namespace
                 else b.list_cron_job_for_all_namespaces().items)
        return _raw_list(items)
    return _cached(ac, f"cronjobs:{namespace}", 60, _fetch)


# ── PersistentVolumes ─────────────────────────────────────────────────────────

@router.get("/pvs")
def raw_pvs(ac: ApiClient = Depends(_header_dep)):
    return _cached(ac, "pvs", 60,
                   lambda: _raw_list(core_v1(ac).list_persistent_volume().items))


# ── PersistentVolumeClaims ────────────────────────────────────────────────────

@router.get("/pvcs")
def raw_pvcs(namespace: str = Query(default=""), ac: ApiClient = Depends(_header_dep)):
    def _fetch():
        core = core_v1(ac)
        items = (core.list_namespaced_persistent_volume_claim(namespace).items if namespace
                 else core.list_persistent_volume_claim_for_all_namespaces().items)
        return _raw_list(items)
    return _cached(ac, f"pvcs:{namespace}", 60, _fetch)


# ── ConfigMaps ────────────────────────────────────────────────────────────────

@router.get("/configmaps")
def raw_configmaps(namespace: str = Query(default=""), ac: ApiClient = Depends(_header_dep)):
    def _fetch():
        core = core_v1(ac)
        items = (core.list_namespaced_config_map(namespace).items if namespace
                 else core.list_config_map_for_all_namespaces().items)
        return _raw_list(items)
    return _cached(ac, f"configmaps:{namespace}", 30, _fetch)


# ── Secrets ───────────────────────────────────────────────────────────────────

@router.get("/secrets")
def raw_secrets(namespace: str = Query(default=""), ac: ApiClient = Depends(_header_dep)):
    def _fetch():
        core = core_v1(ac)
        items = (core.list_namespaced_secret(namespace).items if namespace
                 else core.list_secret_for_all_namespaces().items)
        return _raw_list(items)
    return _cached(ac, f"secrets:{namespace}", 30, _fetch)


# ── Ingresses ─────────────────────────────────────────────────────────────────

@router.get("/ingresses")
def raw_ingresses(namespace: str = Query(default=""), ac: ApiClient = Depends(_header_dep)):
    def _fetch():
        try:
            net = net_v1(ac)
            items = (net.list_namespaced_ingress(namespace).items if namespace
                     else net.list_ingress_for_all_namespaces().items)
            return _raw_list(items)
        except Exception:
            return []
    return _cached(ac, f"ingresses:{namespace}", 30, _fetch)


# ── Events ────────────────────────────────────────────────────────────────────

@router.get("/events")
def raw_events(
    namespace: str = Query(default=""),
    kind: str      = Query(default=""),
    name: str      = Query(default=""),
    ac: ApiClient  = Depends(_header_dep),
):
    def _fetch():
        core = core_v1(ac)
        fields = []
        if kind: fields.append(f"involvedObject.kind={kind}")
        if name: fields.append(f"involvedObject.name={name}")
        field_sel = ",".join(fields) or None
        if namespace:
            items = core.list_namespaced_event(namespace, field_selector=field_sel).items
        else:
            items = core.list_event_for_all_namespaces(field_selector=field_sel).items
        return _raw_list(items)
    return _cached(ac, f"events:{namespace}:{kind}:{name}", 15, _fetch)


# ── Single-item detail endpoints ─────────────────────────────────────────────

# Services
@router.get("/services/{namespace}/{name}")
def raw_service(namespace: str = Path(...), name: str = Path(...), ac: ApiClient = Depends(_header_dep)):
    core = core_v1(ac)
    try:
        svc = core.read_namespaced_service(name, namespace)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
    d = _raw(svc)
    # pods matching selector
    try:
        sel = svc.spec.selector or {}
        label_sel = ",".join(f"{k}={v}" for k, v in sel.items())
        if label_sel:
            d["_pods"] = _raw_list(core.list_namespaced_pod(namespace, label_selector=label_sel).items)
        else:
            d["_pods"] = []
    except Exception:
        d["_pods"] = []
    try:
        d["_events"] = _raw_list(core.list_namespaced_event(namespace, field_selector=f"involvedObject.name={name}").items)
    except Exception:
        d["_events"] = []
    return d

# Ingresses
@router.get("/ingresses/{namespace}/{name}")
def raw_ingress(namespace: str = Path(...), name: str = Path(...), ac: ApiClient = Depends(_header_dep)):
    try:
        ing = net_v1(ac).read_namespaced_ingress(name, namespace)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
    d = _raw(ing)
    try:
        d["_events"] = _raw_list(core_v1(ac).list_namespaced_event(namespace, field_selector=f"involvedObject.name={name}").items)
    except Exception:
        d["_events"] = []
    return d

# StatefulSets
@router.get("/statefulsets/{namespace}/{name}")
def raw_statefulset(namespace: str = Path(...), name: str = Path(...), ac: ApiClient = Depends(_header_dep)):
    apps = apps_v1(ac); core = core_v1(ac)
    try:
        sts = apps.read_namespaced_stateful_set(name, namespace)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
    d = _raw(sts)
    try:
        sel = sts.spec.selector.match_labels if (sts.spec and sts.spec.selector) else {}
        label_sel = ",".join(f"{k}={v}" for k, v in sel.items())
        d["_pods"] = _raw_list(core.list_namespaced_pod(namespace, label_selector=label_sel).items)
    except Exception:
        d["_pods"] = []
    try:
        d["_events"] = _raw_list(core.list_namespaced_event(namespace, field_selector=f"involvedObject.name={name}").items)
    except Exception:
        d["_events"] = []
    return d

@router.post("/statefulsets/{namespace}/{name}/scale")
def scale_statefulset(namespace: str = Path(...), name: str = Path(...), body: _ScaleBody = ..., ac: ApiClient = Depends(_header_dep)):
    if body.replicas < 0:
        raise HTTPException(status_code=400, detail="replicas must be >= 0")
    try:
        d = apps_v1(ac).patch_namespaced_stateful_set_scale(name, namespace, {"spec": {"replicas": body.replicas}})
        return {"replicas": d.spec.replicas}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# DaemonSets
@router.get("/daemonsets/{namespace}/{name}")
def raw_daemonset(namespace: str = Path(...), name: str = Path(...), ac: ApiClient = Depends(_header_dep)):
    apps = apps_v1(ac); core = core_v1(ac)
    try:
        ds = apps.read_namespaced_daemon_set(name, namespace)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
    d = _raw(ds)
    try:
        sel = ds.spec.selector.match_labels if (ds.spec and ds.spec.selector) else {}
        label_sel = ",".join(f"{k}={v}" for k, v in sel.items())
        d["_pods"] = _raw_list(core.list_namespaced_pod(namespace, label_selector=label_sel).items)
    except Exception:
        d["_pods"] = []
    try:
        d["_events"] = _raw_list(core.list_namespaced_event(namespace, field_selector=f"involvedObject.name={name}").items)
    except Exception:
        d["_events"] = []
    return d

# Jobs
@router.get("/jobs/{namespace}/{name}")
def raw_job(namespace: str = Path(...), name: str = Path(...), ac: ApiClient = Depends(_header_dep)):
    core = core_v1(ac)
    try:
        job = batch_v1(ac).read_namespaced_job(name, namespace)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
    d = _raw(job)
    try:
        sel = job.spec.selector.match_labels if (job.spec and job.spec.selector) else {}
        label_sel = ",".join(f"{k}={v}" for k, v in sel.items())
        d["_pods"] = _raw_list(core.list_namespaced_pod(namespace, label_selector=label_sel).items) if label_sel else []
    except Exception:
        d["_pods"] = []
    try:
        d["_events"] = _raw_list(core.list_namespaced_event(namespace, field_selector=f"involvedObject.name={name}").items)
    except Exception:
        d["_events"] = []
    return d

# CronJobs
@router.get("/cronjobs/{namespace}/{name}")
def raw_cronjob(namespace: str = Path(...), name: str = Path(...), ac: ApiClient = Depends(_header_dep)):
    core = core_v1(ac)
    try:
        cj = batch_v1(ac).read_namespaced_cron_job(name, namespace)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
    d = _raw(cj)
    try:
        all_jobs = batch_v1(ac).list_namespaced_job(namespace).items
        owned = [j for j in all_jobs if any(o.name == name and o.kind == "CronJob" for o in (j.metadata.owner_references or []))]
        d["_jobs"] = _raw_list(owned)
    except Exception:
        d["_jobs"] = []
    try:
        d["_events"] = _raw_list(core.list_namespaced_event(namespace, field_selector=f"involvedObject.name={name}").items)
    except Exception:
        d["_events"] = []
    return d

# PersistentVolumes (cluster-scoped)
@router.get("/pvs/{name}")
def raw_pv(name: str = Path(...), ac: ApiClient = Depends(_header_dep)):
    try:
        pv = core_v1(ac).read_persistent_volume(name)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
    d = _raw(pv)
    try:
        d["_events"] = _raw_list(core_v1(ac).list_event_for_all_namespaces(field_selector=f"involvedObject.name={name}").items)
    except Exception:
        d["_events"] = []
    return d

# PersistentVolumeClaims
@router.get("/pvcs/{namespace}/{name}")
def raw_pvc(namespace: str = Path(...), name: str = Path(...), ac: ApiClient = Depends(_header_dep)):
    core = core_v1(ac)
    try:
        pvc = core.read_namespaced_persistent_volume_claim(name, namespace)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
    d = _raw(pvc)
    try:
        d["_events"] = _raw_list(core.list_namespaced_event(namespace, field_selector=f"involvedObject.name={name}").items)
    except Exception:
        d["_events"] = []
    return d

# ConfigMaps
@router.get("/configmaps/{namespace}/{name}")
def raw_configmap(namespace: str = Path(...), name: str = Path(...), ac: ApiClient = Depends(_header_dep)):
    try:
        cm = core_v1(ac).read_namespaced_config_map(name, namespace)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _raw(cm)

# Secrets
@router.get("/secrets/{namespace}/{name}")
def raw_secret(namespace: str = Path(...), name: str = Path(...), ac: ApiClient = Depends(_header_dep)):
    try:
        s = core_v1(ac).read_namespaced_secret(name, namespace)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _raw(s)


# ── Metrics-server: node & pod ────────────────────────────────────────────────

@router.get("/node_metrics")
def raw_node_metrics(ac: ApiClient = Depends(_header_dep)):
    def _fetch():
        try:
            nm = custom_api(ac).list_cluster_custom_object("metrics.k8s.io", "v1beta1", "nodes")
            return nm.get("items", [])
        except Exception:
            return []
    return _cached(ac, "node_metrics", 15, _fetch)


@router.get("/pod_metrics")
def raw_pod_metrics(namespace: str = Query(default=""), ac: ApiClient = Depends(_header_dep)):
    def _fetch():
        try:
            pm = custom_api(ac).list_cluster_custom_object("metrics.k8s.io", "v1beta1", "pods")
            items = pm.get("items", [])
            if namespace:
                items = [i for i in items if i.get("metadata", {}).get("namespace") == namespace]
            return items
        except Exception:
            return []
    return _cached(ac, f"pod_metrics:{namespace}", 15, _fetch)


# ── Quotas ────────────────────────────────────────────────────────────────────

@router.get("/quotas")
def raw_quotas(namespace: str = Query(default=""), ac: ApiClient = Depends(_header_dep)):
    def _fetch():
        try:
            core = core_v1(ac)
            items = (core.list_namespaced_resource_quota(namespace).items if namespace
                     else core.list_resource_quota_for_all_namespaces().items)
            return _raw_list(items)
        except Exception:
            return []
    return _cached(ac, f"quotas:{namespace}", 60, _fetch)


# ── Cluster version ───────────────────────────────────────────────────────────

@router.get("/version")
def raw_version(ac: ApiClient = Depends(_header_dep)):
    try:
        v = client.VersionApi(ac).get_code()
        return {"git_version": v.git_version, "platform": v.platform or ""}
    except Exception as e:
        logger.warning("version fetch failed: %s", e)
        return {"git_version": "unknown", "platform": ""}
