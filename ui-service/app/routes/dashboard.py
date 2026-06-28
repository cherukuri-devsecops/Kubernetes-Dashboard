"""
Flask routes for all dashboard pages.

All data fetching and K8s connections go through backend-service.
The UI has zero direct Kubernetes access.
"""
import concurrent.futures
import json
import logging
import os
import re
import time
from datetime import datetime, timezone

import gevent
import requests as _requests
import websocket as _wsclient
import yaml as _yaml
from flask import (Blueprint, render_template, request, session,
                   Response, stream_with_context, redirect, url_for, abort, jsonify,
                   copy_current_request_context)

from ..auth_utils import cluster_required
from ..cache import _cache_scope
from ..config import BACKEND_SERVICE_URL
from ..database import audit, _annotations_for
from ..loki_client import query_range as _loki_query
from ..formatters import (age, phase_cls, ready_count, restarts,
                          node_ready, node_roles, fmt_cpu, fmt_mem,
                          parse_cpu, parse_memory, log_cls, fmt_log_ts, clean_logs,
                          log_level_badge)
from ..k8s_obj import k8s_obj
from .. import backend_client as _bc

logger = logging.getLogger(__name__)

dashboard_bp = Blueprint("dashboard", __name__)

_CNI_PATTERNS = [
    ("cilium",       "Cilium"),
    ("calico-node",  "Calico"),
    ("kube-flannel", "Flannel"),
    ("weave-net",    "Weave Net"),
    ("antrea-agent", "Antrea"),
    ("canal",        "Canal"),
    ("kindnet",      "Kindnet"),
    ("kube-router",  "Kube-router"),
    ("multus",       "Multus"),
]


def _detect_cni(pods) -> str:
    sys_pods = [p.metadata.name for p in pods if p.metadata.namespace == "kube-system"]
    for pattern, label in _CNI_PATTERNS:
        if any(pattern in (name or "") for name in sys_pods):
            return label
    return "—"


def _parallel(tasks: dict) -> dict:
    """Fetch multiple backend endpoints concurrently. tasks = {key: callable}."""
    out = {}
    wrapped = {key: copy_current_request_context(fn) for key, fn in tasks.items()}
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(12, len(tasks))) as pool:
        futs = {pool.submit(fn): key for key, fn in wrapped.items()}
        for fut in concurrent.futures.as_completed(futs):
            key = futs[fut]
            try:
                out[key] = fut.result()
            except Exception as e:
                logger.warning("parallel fetch %s failed: %s", key, e)
                out[key] = []
    return out


# ── Overview ──────────────────────────────────────────────────────────────────

@dashboard_bp.route("/")
@cluster_required
def overview():
    data = _parallel({
        "pods":        _bc.raw_pods,
        "nodes":       _bc.raw_nodes,
        "namespaces":  _bc.raw_namespaces,
        "services":    _bc.raw_services,
        "deployments": _bc.raw_deployments,
        "statefulsets":_bc.raw_statefulsets,
        "daemonsets":  _bc.raw_daemonsets,
        "jobs":        _bc.raw_jobs,
        "cronjobs":    _bc.raw_cronjobs,
        "events":      _bc.raw_events,
        "node_metrics":_bc.raw_node_metrics,
    })

    pods  = k8s_obj(data["pods"])
    nodes = k8s_obj(data["nodes"])
    nss   = k8s_obj(data["namespaces"])
    svcs  = k8s_obj(data["services"])
    deps  = k8s_obj(data["deployments"])
    sts   = k8s_obj(data["statefulsets"])
    ds    = k8s_obj(data["daemonsets"])
    jobs  = k8s_obj(data["jobs"])
    crons = k8s_obj(data["cronjobs"])
    evts  = k8s_obj(data["events"])

    pod_running = sum(1 for p in pods if p.status.phase == "Running")
    pod_pending = sum(1 for p in pods if p.status.phase == "Pending")
    pod_failed  = sum(1 for p in pods if p.status.phase == "Failed")
    pod_unknown = sum(1 for p in pods
                      if p.status.phase not in ("Running","Pending","Failed","Succeeded"))

    cpu_pct = mem_pct = 0
    cpu_used_cores = cpu_total_cores = mem_used_gib = mem_total_gib = 0
    total_cpu_m = sum(parse_cpu((n.status.allocatable or {}).get("cpu", "0")) for n in nodes)
    total_mem_b = sum(parse_memory((n.status.allocatable or {}).get("memory", "0")) for n in nodes)

    nm_items   = data.get("node_metrics") or []
    node_metrics_list = []
    if nm_items:
        used_cpu_m = sum(parse_cpu(i["usage"]["cpu"])    for i in nm_items)
        used_mem_b = sum(parse_memory(i["usage"]["memory"]) for i in nm_items)
        cpu_pct = round(used_cpu_m / total_cpu_m * 100) if total_cpu_m else 0
        mem_pct = round(used_mem_b / total_mem_b * 100) if total_mem_b else 0
        cpu_used_cores  = round(used_cpu_m / 1000, 1)
        cpu_total_cores = round(total_cpu_m / 1000)
        mem_used_gib    = round(used_mem_b / 1024**3, 1)
        mem_total_gib   = round(total_mem_b / 1024**3, 1)
        per = {i["metadata"]["name"]: i for i in nm_items}
        for n in nodes:
            nm = per.get(n.metadata.name, {})
            ncpu = parse_cpu(nm.get("usage", {}).get("cpu", "0"))
            ncap = parse_cpu((n.status.allocatable or {}).get("cpu", "0"))
            node_metrics_list.append({
                "name":    n.metadata.name,
                "ready":   node_ready(n),
                "version": (n.status.node_info.kubelet_version if n.status.node_info else "—"),
                "cpu_pct": round(ncpu / ncap * 100) if ncap else 0,
            })
    else:
        for n in nodes:
            node_metrics_list.append({
                "name":    n.metadata.name,
                "ready":   node_ready(n),
                "version": (n.status.node_info.kubelet_version if n.status.node_info else "—"),
                "cpu_pct": 0,
            })

    wl = []
    for d in deps:
        r = d.status.ready_replicas or 0; des = d.spec.replicas or 0
        wl.append({"name": d.metadata.name, "ns": d.metadata.namespace,
                   "type": "Deployment", "ready": r, "desired": des,
                   "status": "Running" if r == des and des > 0 else "Degraded",
                   "age": age(d.metadata.creation_timestamp),
                   "avail_pct": round(r / des * 100) if des else 0})
    for s in sts:
        r = s.status.ready_replicas or 0; des = s.spec.replicas or 0
        wl.append({"name": s.metadata.name, "ns": s.metadata.namespace,
                   "type": "StatefulSet", "ready": r, "desired": des,
                   "status": "Running" if r == des else "Degraded",
                   "age": age(s.metadata.creation_timestamp),
                   "avail_pct": round(r / des * 100) if des else 0})
    for d in ds:
        r = d.status.number_ready or 0; des = d.status.desired_number_scheduled or 0
        wl.append({"name": d.metadata.name, "ns": d.metadata.namespace,
                   "type": "DaemonSet", "ready": r, "desired": des,
                   "status": "Running" if r == des else "Degraded",
                   "age": age(d.metadata.creation_timestamp),
                   "avail_pct": round(r / des * 100) if des else 0})
    for j in jobs:
        r = j.status.succeeded or 0; des = j.spec.completions or 1
        wl.append({"name": j.metadata.name, "ns": j.metadata.namespace,
                   "type": "Job", "ready": r, "desired": des,
                   "status": "Complete" if r >= des else "Running",
                   "age": age(j.metadata.creation_timestamp),
                   "avail_pct": round(r / des * 100) if des else 0})
    for c in crons:
        wl.append({"name": c.metadata.name, "ns": c.metadata.namespace,
                   "type": "CronJob", "ready": 0, "desired": 0,
                   "status": "Active" if not (c.spec.suspend) else "Suspended",
                   "age": age(c.metadata.creation_timestamp), "avail_pct": 0})
    wl.sort(key=lambda w: (
        0 if w["status"] in ("Running", "Complete", "Active") else 1, w["name"]))

    sorted_evts = sorted(
        evts,
        key=lambda e: age(e.last_timestamp or "") if (e.last_timestamp or "") else "",
        reverse=False,
    )[:6]

    kube_version      = session.get("cluster_version", "—")
    container_runtime = "—"
    if nodes:
        ni = nodes[0].status.node_info
        if ni:
            container_runtime = ni.container_runtime_version or "—"

    cn = session.get("cluster_token", {}).get("server", "") or "local-cluster"
    if cn.startswith("https://") or cn.startswith("http://"):
        cn = re.sub(r"https?://|:\d+", "", cn).split(".")[0] or "local-cluster"

    return render_template("overview.html", title="Overview",
        cluster_name=cn, kube_version=kube_version,
        container_runtime=container_runtime, cni_plugin=_detect_cni(pods),
        node_count=len(nodes),
        nodes_ready=sum(1 for n in nodes if node_ready(n)),
        pod_count=len(pods), pod_running=pod_running, pod_pending=pod_pending,
        pod_failed=pod_failed, pod_unknown=pod_unknown,
        dep_count=len(deps), svc_count=len(svcs),
        cpu_pct=cpu_pct, mem_pct=mem_pct,
        cpu_used_cores=cpu_used_cores, cpu_total_cores=cpu_total_cores,
        mem_used_gib=mem_used_gib, mem_total_gib=mem_total_gib,
        node_metrics=node_metrics_list,
        workloads=wl[:6], events=sorted_evts, age=age)


# ── Cluster ───────────────────────────────────────────────────────────────────

@dashboard_bp.route("/cluster")
@cluster_required
def cluster_view():
    data = _parallel({
        "pods":        _bc.raw_pods,
        "nodes":       _bc.raw_nodes,
        "statefulsets":_bc.raw_statefulsets,
        "daemonsets":  _bc.raw_daemonsets,
        "jobs":        _bc.raw_jobs,
        "cronjobs":    _bc.raw_cronjobs,
        "pvs":         _bc.raw_pvs,
        "pvcs":        _bc.raw_pvcs,
        "ingresses":   _bc.raw_ingresses,
        "configmaps":  _bc.raw_configmaps,
        "secrets":     _bc.raw_secrets,
        "quotas":      _bc.raw_quotas,
        "node_metrics":_bc.raw_node_metrics,
    })

    live_nodes = {}
    for item in (data.get("node_metrics") or []):
        live_nodes[item["metadata"]["name"]] = {
            "cpu": parse_cpu(item["usage"]["cpu"]),
            "mem": parse_memory(item["usage"]["memory"]),
        }

    return render_template("cluster.html", title="Cluster",
        pods=k8s_obj(data["pods"]),       nodes=k8s_obj(data["nodes"]),
        sts=k8s_obj(data["statefulsets"]), ds=k8s_obj(data["daemonsets"]),
        jobs=k8s_obj(data["jobs"]),        crons=k8s_obj(data["cronjobs"]),
        pvs=k8s_obj(data["pvs"]),          pvcs=k8s_obj(data["pvcs"]),
        ingresses=k8s_obj(data["ingresses"]),
        configmaps=k8s_obj(data["configmaps"]),
        secrets=k8s_obj(data["secrets"]),
        quotas=k8s_obj(data["quotas"]),
        live_nodes=live_nodes,
        age=age, phase_cls=phase_cls, fmt_cpu=fmt_cpu, fmt_mem=fmt_mem,
        parse_cpu=parse_cpu, parse_memory=parse_memory)


# ── Nodes ─────────────────────────────────────────────────────────────────────

@dashboard_bp.route("/nodes")
@cluster_required
def nodes_view():
    nodes = k8s_obj(_bc.raw_nodes())
    return render_template("nodes.html", title="Nodes",
        nodes=nodes, age=age, node_ready=node_ready, node_roles=node_roles)


@dashboard_bp.route("/nodes/<name>")
@cluster_required
def node_detail(name):
    try:
        data = _bc.raw_node(name)
    except Exception:
        abort(404)

    node      = k8s_obj(data)
    raw_pods  = data.get("_pods", [])
    pod_metrics = data.get("_pod_metrics", {})
    live_metrics = data.get("_metrics", {})
    pods      = k8s_obj(raw_pods)

    cap   = dict(node.status.allocatable or {})
    nc    = parse_cpu(cap.get("cpu", "0"))
    nm_b  = parse_memory(cap.get("memory", "0"))
    npp   = int(cap.get("pods", 110))

    cpu_req_m = cpu_lim_m = mem_req_b = mem_lim_b = 0
    for pod in pods:
        for c in (pod.spec.containers or []):
            req = (c.resources.requests or {}) if c.resources else {}
            lim = (c.resources.limits   or {}) if c.resources else {}
            cpu_req_m += parse_cpu(req.get("cpu", "0"))
            cpu_lim_m += parse_cpu(lim.get("cpu", "0"))
            mem_req_b += parse_memory(req.get("memory", "0"))
            mem_lim_b += parse_memory(lim.get("memory", "0"))

    cpu_req_pct   = round(cpu_req_m / nc * 100, 1)   if nc   else 0
    cpu_lim_pct   = round(cpu_lim_m / nc * 100, 1)   if nc   else 0
    mem_req_pct   = round(mem_req_b / nm_b * 100, 1) if nm_b else 0
    mem_lim_pct   = round(mem_lim_b / nm_b * 100, 1) if nm_b else 0
    pod_alloc_pct = round(len(pods) / npp * 100, 1)  if npp  else 0

    live_cpu_m = parse_cpu(live_metrics.get("cpu", "0")) if live_metrics else None
    live_mem_b = parse_memory(live_metrics.get("memory", "0")) if live_metrics else None

    conditions = sorted(node.status.conditions or [], key=lambda c: c.type or "")
    return render_template("node_detail.html", title=name, node=node,
        pods=pods, pod_metrics=pod_metrics, conditions=conditions,
        cpu_req_pct=cpu_req_pct, cpu_lim_pct=cpu_lim_pct,
        cpu_req_cores=round(cpu_req_m / 1000, 2),
        cpu_lim_cores=round(cpu_lim_m / 1000, 2),
        mem_req_pct=mem_req_pct, mem_lim_pct=mem_lim_pct,
        mem_req_mib=round(mem_req_b / 1024**2),
        mem_lim_mib=round(mem_lim_b / 1024**2),
        pod_alloc_pct=pod_alloc_pct, pod_count=len(pods), pods_max=npp,
        live_cpu_m=live_cpu_m, live_mem_b=live_mem_b,
        age=age, phase_cls=phase_cls, ready_count=ready_count,
        restarts=restarts, fmt_cpu=fmt_cpu, fmt_mem=fmt_mem,
        node_ready=node_ready, node_roles=node_roles)


# ── Namespaces ────────────────────────────────────────────────────────────────

@dashboard_bp.route("/namespaces")
@cluster_required
def namespaces_view():
    nss = k8s_obj(_bc.raw_namespaces())
    return render_template("namespaces.html", title="Namespaces",
                           namespaces=nss, age=age)


# ── Pods list ─────────────────────────────────────────────────────────────────

@dashboard_bp.route("/pods")
@cluster_required
def pods_view():
    ns  = request.args.get("ns", "")
    data = _parallel({
        "namespaces":  _bc.raw_namespaces,
        "pods":        lambda: _bc.raw_pods(namespace=ns),
        "pod_metrics": lambda: _bc.raw_pod_metrics(namespace=ns),
    })

    pods    = k8s_obj(data["pods"])
    nss_list = k8s_obj(data["namespaces"])
    all_ns  = [n.metadata.name for n in nss_list]

    # Build pod_metrics map {ns/name: {cpu_m, mem_b}}
    pod_metrics: dict = {}
    for item in (data.get("pod_metrics") or []):
        meta = item.get("metadata", {})
        key  = f"{meta.get('namespace','')}/{meta.get('name','')}"
        ctrs = item.get("containers", [])
        pod_metrics[key] = {
            "cpu_m": round(sum(parse_cpu(c.get("usage", {}).get("cpu", "0"))    for c in ctrs)),
            "mem_b":       sum(parse_memory(c.get("usage", {}).get("memory", "0")) for c in ctrs),
        }

    # Include inline _metrics from raw_pods if present
    for p in data["pods"]:
        m = p.get("_metrics")
        if m:
            key = f"{p.get('metadata',{}).get('namespace','')}/{p.get('metadata',{}).get('name','')}"
            pod_metrics.setdefault(key, m)

    from ..cache import pod_state_signature
    signature = pod_state_signature(pods)

    if request.headers.get("HX-Request"):
        return render_template("partials/pod_table.html",
            pods=pods, ns=ns, pod_signature=signature,
            pod_metrics=pod_metrics,
            age=age, phase_cls=phase_cls,
            ready_count=ready_count, restarts=restarts,
            fmt_cpu=fmt_cpu, fmt_mem=fmt_mem)
    return render_template("pods.html", title="Pods",
        pods=pods, namespaces=all_ns, selected_ns=ns,
        pod_signature=signature, pod_metrics=pod_metrics,
        age=age, phase_cls=phase_cls,
        ready_count=ready_count, restarts=restarts,
        fmt_cpu=fmt_cpu, fmt_mem=fmt_mem)


# ── Pod detail ────────────────────────────────────────────────────────────────

@dashboard_bp.route("/pods/<namespace>/<name>")
@cluster_required
def pod_detail(namespace, name):
    sel_ctr  = request.args.get("container", "")
    tail     = int(request.args.get("tail", 300))
    previous = request.args.get("previous") == "1"
    _scope   = _cache_scope()

    # Fan out all slow calls in parallel
    data = _parallel({
        "pod":       lambda: _bc.raw_pod(namespace, name),
        "logs":      lambda: _bc.raw_pod_logs(namespace, name,
                                              container=sel_ctr, tail=tail, previous=previous),
        "events":    lambda: _bc.raw_events(namespace=namespace, kind="Pod", name=name),
        "lifecycle": lambda: _loki_query(
            f'{{job="pod-lifecycle", cluster="{_scope}"}}', hours=72, limit=200),
        "notes":     lambda: _annotations_for("pod", namespace, name),
    })

    raw = data.get("pod") or {}
    if not raw:
        abort(404)

    pod = k8s_obj(raw)
    ctr_metrics = raw.get("_ctr_metrics", {})
    siblings    = k8s_obj(raw.get("_siblings", []))

    containers      = [c.name for c in (pod.spec.containers or [])]
    init_containers = [c.name for c in (pod.spec.init_containers or [])]
    all_containers  = containers + init_containers
    if not sel_ctr:
        sel_ctr = containers[0] if containers else ""

    logs = clean_logs(data.get("logs") or "")

    try:
        ev = sorted(k8s_obj(data.get("events") or []),
                    key=lambda e: e.last_timestamp or "",
                    reverse=True)
    except Exception:
        ev = []

    annotations = data.get("notes") or []
    _all_lc = data.get("lifecycle") or []
    lifecycle = [r for r in _all_lc
                 if r.get("pod_name") == name and r.get("ns") == namespace][:50]

    pod_cpu_m = sum(m.get("cpu_m", 0) for m in ctr_metrics.values())
    pod_mem_b = sum(m.get("mem_b", 0) for m in ctr_metrics.values())
    pod_cpu_lim_m = sum(
        parse_cpu((c.resources.limits or {}).get("cpu", "0"))
        for c in (pod.spec.containers or []) if c.resources and c.resources.limits
    )
    pod_mem_lim_b = sum(
        parse_memory((c.resources.limits or {}).get("memory", "0"))
        for c in (pod.spec.containers or []) if c.resources and c.resources.limits
    )
    cpu_bar_pct = min(round(pod_cpu_m / pod_cpu_lim_m * 100) if pod_cpu_lim_m else 0, 100)
    mem_bar_pct = min(round(pod_mem_b / pod_mem_lim_b * 100) if pod_mem_lim_b else 0, 100)

    # Owner
    owner = None
    refs  = pod.metadata.owner_references or []
    if refs:
        ref = refs[0]
        owner = {
            "kind": ref.kind, "name": ref.name, "ns": namespace,
            "uid":  ref.uid,
            "controller_kind": raw.get("_owner_controller_kind", ref.kind),
            "controller_name": raw.get("_owner_controller_name", ref.name),
        }

    try:
        import yaml as _y
        manifest_yaml = _y.safe_dump(
            {k: v for k, v in raw.items() if not k.startswith("_")},
            sort_keys=False, default_flow_style=False, width=120)
    except Exception as e:
        manifest_yaml = f"# error: {e}"

    return render_template("pod_detail.html", title=name, pod=pod,
        containers=containers, init_containers=init_containers,
        all_containers=all_containers,
        sel_ctr=sel_ctr, tail=tail, previous=previous,
        logs=logs, events=ev,
        annotations=annotations, lifecycle=lifecycle,
        ctr_metrics=ctr_metrics, owner=owner, siblings=siblings,
        manifest_yaml=manifest_yaml,
        pod_cpu_m=pod_cpu_m, pod_mem_b=pod_mem_b,
        pod_cpu_lim_m=pod_cpu_lim_m, pod_mem_lim_b=pod_mem_lim_b,
        cpu_bar_pct=cpu_bar_pct, mem_bar_pct=mem_bar_pct,
        age=age, phase_cls=phase_cls, ready_count=ready_count,
        restarts=restarts, fmt_cpu=fmt_cpu, fmt_mem=fmt_mem, log_cls=log_cls,
        fmt_log_ts=fmt_log_ts, log_level_badge=log_level_badge)


# ── Pod log stream (SSE — proxies backend) ───────────────────────────────────

@dashboard_bp.route("/pods/<namespace>/<name>/logs/stream")
@cluster_required
def log_stream(namespace, name):
    container = request.args.get("container", "")
    tail      = int(request.args.get("tail", 100))
    previous  = request.args.get("previous") == "1"
    hdrs      = _bc._auth_headers()
    params    = {"tail": tail, "previous": str(previous).lower()}
    if container:
        params["container"] = container
    url = f"{BACKEND_SERVICE_URL.rstrip('/')}/api/stream/pods/{namespace}/{name}/logs"

    def generate():
        try:
            with _requests.get(url, headers=hdrs, params=params,
                               stream=True, timeout=3600) as resp:
                for raw_line in resp.iter_lines():
                    if not raw_line:
                        continue
                    line = raw_line.decode("utf-8", errors="replace")
                    if line.startswith("data: "):
                        line = line[6:]
                    if line:
                        yield f"data: {log_cls(line)}|||{line}\n\n"
        except GeneratorExit:
            return
        except Exception as e:
            yield f"data: log-err|||[stream error: {e}]\n\n"

    return Response(stream_with_context(generate()),
                    mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── Pod delete ────────────────────────────────────────────────────────────────

@dashboard_bp.route("/pods/<namespace>/<name>/delete", methods=["POST"])
@cluster_required
def delete_pod(namespace, name):
    try:
        _bc.resource_delete("Pod", namespace, name)
    except Exception:
        pass
    audit("pod.delete", target=f"{namespace}/{name}")
    return redirect(url_for("dashboard.pods_view", ns=namespace))


# ── Pod shell ─────────────────────────────────────────────────────────────────

@dashboard_bp.route("/pods/<namespace>/<name>/shell")
@cluster_required
def pod_shell(namespace, name):
    try:
        raw = _bc.raw_pod(namespace, name)
    except Exception:
        abort(404)
    pod = k8s_obj(raw)
    containers = [c.name for c in (pod.spec.containers or [])]
    sel_ctr    = request.args.get("container", containers[0] if containers else "")
    return render_template("pod_shell.html",
                           title=f"Shell · {name}", pod=pod,
                           containers=containers, sel_ctr=sel_ctr)


# ── Pod exec WebSocket (proxies backend) ─────────────────────────────────────

def pod_exec_ws(ws, namespace, name):
    """WebSocket handler — registered in main.py via sock.route().
    Proxies the browser WebSocket through to the backend-service exec endpoint."""
    if not session.get("user") or not session.get("cluster_ok"):
        logger.warning("exec ws: unauthenticated %s/%s", namespace, name)
        ws.close()
        return

    container = request.args.get("container") or ""
    shell_cmd = request.args.get("cmd", "/bin/sh")
    audit("pod.exec", target=f"{namespace}/{name}",
          container=container, cmd=shell_cmd)

    # Capture auth headers while we have request context
    hdrs = _bc._auth_headers()

    ws_url = BACKEND_SERVICE_URL.rstrip("/").replace("http://", "ws://").replace("https://", "wss://")
    backend_url = (f"{ws_url}/api/ws/pods/{namespace}/{name}/exec"
                   f"?container={container}&cmd={shell_cmd}")
    header = [f"{k}: {v}" for k, v in hdrs.items()]

    try:
        backend_ws = _wsclient.create_connection(backend_url, header=header, timeout=10)
    except Exception as e:
        logger.error("exec ws: backend connect failed %s/%s: %s", namespace, name, e)
        try:
            ws.send(json.dumps({"type": "error", "msg": f"exec failed: {e}"}))
        except Exception:
            pass
        ws.close()
        return

    def backend_to_browser():
        try:
            while True:
                msg = backend_ws.recv()
                ws.send(msg)
        except Exception as e:
            logger.debug("exec ws: backend→browser ended: %s", e)

    reader = gevent.spawn(backend_to_browser)
    try:
        while True:
            msg = ws.receive()
            if msg is None:
                break
            backend_ws.send(msg)
    except Exception as e:
        logger.debug("exec ws: browser→backend ended: %s", e)
    finally:
        reader.kill()
        try:
            backend_ws.close()
        except Exception:
            pass
        logger.info("exec ws: closed %s/%s", namespace, name)


# ── Metrics JSON API ──────────────────────────────────────────────────────────

@dashboard_bp.route("/metrics")
@cluster_required
def metrics_api():
    data = _parallel({
        "nodes":       _bc.raw_nodes,
        "node_metrics":_bc.raw_node_metrics,
        "pod_metrics": _bc.raw_pod_metrics,
    })

    nodes    = k8s_obj(data.get("nodes") or [])
    nm_items = data.get("node_metrics") or []
    pm_items = data.get("pod_metrics")  or []

    nm_by_name = {i["metadata"]["name"]: i for i in nm_items}
    total_cpu_m = sum(parse_cpu((n.status.allocatable or {}).get("cpu", "0"))  for n in nodes)
    total_mem_b = sum(parse_memory((n.status.allocatable or {}).get("memory", "0")) for n in nodes)
    used_cpu_m  = sum(parse_cpu(i["usage"]["cpu"])     for i in nm_items)
    used_mem_b  = sum(parse_memory(i["usage"]["memory"]) for i in nm_items)

    node_rows = []
    for n in nodes:
        nm  = nm_by_name.get(n.metadata.name, {})
        u   = nm.get("usage", {})
        cap = n.status.allocatable or {}
        ncpu  = parse_cpu(u.get("cpu", "0"))
        nmem  = parse_memory(u.get("memory", "0"))
        ncap  = parse_cpu(cap.get("cpu", "0"))
        nmcap = parse_memory(cap.get("memory", "0"))
        node_rows.append({
            "name":        n.metadata.name,
            "cpu_m":       round(ncpu),
            "cpu_cap_m":   round(ncap),
            "cpu_pct":     round(ncpu / ncap * 100) if ncap else 0,
            "mem_mib":     round(nmem / 1024**2),
            "mem_cap_mib": round(nmcap / 1024**2),
            "mem_pct":     round(nmem / nmcap * 100) if nmcap else 0,
        })

    pod_rows = []
    for it in pm_items:
        meta = it.get("metadata", {})
        ctrs = it.get("containers", [])
        cpu  = sum(parse_cpu(c["usage"]["cpu"])       for c in ctrs)
        mem  = sum(parse_memory(c["usage"]["memory"]) for c in ctrs)
        pod_rows.append({
            "namespace": meta.get("namespace", ""),
            "name":      meta.get("name", ""),
            "cpu_m":     round(cpu),
            "mem_mib":   round(mem / 1024**2),
        })

    return jsonify({
        "summary": {
            "cpu_pct":         round(used_cpu_m / total_cpu_m * 100) if total_cpu_m else 0,
            "mem_pct":         round(used_mem_b / total_mem_b * 100) if total_mem_b else 0,
            "cpu_used_cores":  round(used_cpu_m / 1000, 2),
            "cpu_total_cores": round(total_cpu_m / 1000, 2),
            "mem_used_gib":    round(used_mem_b  / 1024**3, 2),
            "mem_total_gib":   round(total_mem_b / 1024**3, 2),
            "metrics_available": bool(nm_items),
        },
        "nodes": node_rows,
        "pods":  pod_rows,
    })


# ── Pod metrics graphs API (Prometheus range queries) ─────────────────────────

@dashboard_bp.route("/api/metrics/pod-graphs")
@cluster_required
def pod_graphs_api():
    ns  = request.args.get("namespace", "")
    dep = request.args.get("deployment", "")
    rng = request.args.get("range", "30m")

    prom_url = os.environ.get("PROMETHEUS_URL", "http://prometheus:9090").rstrip("/")

    rng_seconds = {"5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "3h": 10800}
    seconds = rng_seconds.get(rng, 1800)
    end   = int(time.time())
    start = end - seconds
    step  = max(15, seconds // 120)

    def _prom_range(query):
        try:
            resp = _requests.get(
                f"{prom_url}/api/v1/query_range",
                params={"query": query, "start": start, "end": end, "step": step},
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json().get("data", {}).get("result", [])
        except Exception as exc:
            logger.warning("pod-graphs prom query failed: %s", exc)
            return []

    pod_re    = f"{dep}-[a-z0-9]+-[a-z0-9]+" if dep else ".*"
    label_sel = f'namespace="{ns}",pod=~"{pod_re}",container!="",container!="POD"'

    cpu_results = _prom_range(
        f'sum by (pod) (rate(container_cpu_usage_seconds_total{{{label_sel}}}[2m]))'
    )
    mem_results = _prom_range(
        f'sum by (pod) (container_memory_working_set_bytes{{{label_sel}}})'
    )
    cpu_lim_results = _prom_range(
        f'sum by (pod) (kube_pod_container_resource_limits{{namespace="{ns}",pod=~"{pod_re}",resource="cpu"}})'
    )
    mem_lim_results = _prom_range(
        f'sum by (pod) (kube_pod_container_resource_limits{{namespace="{ns}",pod=~"{pod_re}",resource="memory"}})'
    )

    return jsonify({
        "step":      step,
        "start":     start,
        "cpu_cores": cpu_results,
        "mem_bytes": mem_results,
        "cpu_limit": cpu_lim_results,
        "mem_limit": mem_lim_results,
    })


# ── Services ──────────────────────────────────────────────────────────────────

@dashboard_bp.route("/services")
@cluster_required
def services_view():
    svcs = k8s_obj(_bc.raw_services())

    def svc_ports(s):
        return ",".join(f"{p.port}/{p.protocol}"
                        for p in (s.spec.ports or [])) or "—"

    def svc_ext(s):
        if s.status.load_balancer and s.status.load_balancer.ingress:
            return ",".join(
                (i.ip or i.hostname or "")
                for i in s.status.load_balancer.ingress)
        return "—"

    return render_template("services.html", title="Services",
                           services=svcs, age=age,
                           svc_ports=svc_ports, svc_external=svc_ext)


@dashboard_bp.route("/services/<namespace>/<name>")
@cluster_required
def service_detail(namespace, name):
    raw = _bc.raw_service(namespace, name)
    if not raw: abort(404)
    svc = k8s_obj(raw)
    pods = k8s_obj(raw.get("_pods", []))
    ev = sorted(k8s_obj(raw.get("_events", [])), key=lambda e: e.last_timestamp or "", reverse=True)
    try:
        import yaml as _y
        manifest_yaml = _y.safe_dump({k: v for k, v in raw.items() if not k.startswith("_")}, sort_keys=False, default_flow_style=False, width=120)
    except Exception as exc:
        manifest_yaml = f"# error: {exc}"
    return render_template("service_detail.html", title=name, svc=svc, pods=pods, events=ev, manifest_yaml=manifest_yaml, age=age, phase_cls=phase_cls, ready_count=ready_count, restarts=restarts)


# ── Deployments ───────────────────────────────────────────────────────────────

@dashboard_bp.route("/deployments")
@cluster_required
def deployments_view():
    deps = k8s_obj(_bc.raw_deployments())
    return render_template("deployments.html", title="Deployments",
                           deployments=deps, age=age)


@dashboard_bp.route("/deployments/<namespace>/<name>")
@cluster_required
def deployment_detail(namespace, name):
    data = _parallel({
        "deployment": lambda: _bc.raw_deployment(namespace, name),
        "events":     lambda: _bc.raw_events(namespace=namespace, kind="Deployment", name=name),
    })

    raw = data.get("deployment") or {}
    if not raw:
        abort(404)

    dep         = k8s_obj(raw)
    replica_sets = k8s_obj(raw.get("_replica_sets", []))
    pods        = k8s_obj(raw.get("_pods", []))
    ev_raw      = raw.get("_events", []) or data.get("events") or []
    try:
        ev = sorted(k8s_obj(ev_raw), key=lambda e: e.last_timestamp or "", reverse=True)
    except Exception:
        ev = []

    try:
        import yaml as _y
        manifest_yaml = _y.safe_dump(
            {k: v for k, v in raw.items() if not k.startswith("_")},
            sort_keys=False, default_flow_style=False, width=120)
    except Exception as exc:
        manifest_yaml = f"# error: {exc}"

    return render_template("deployment_detail.html", title=name,
        dep=dep, replica_sets=replica_sets, pods=pods, events=ev,
        manifest_yaml=manifest_yaml,
        age=age, phase_cls=phase_cls, ready_count=ready_count,
        restarts=restarts, fmt_cpu=fmt_cpu, fmt_mem=fmt_mem)


@dashboard_bp.route("/deployments/<namespace>/<name>/scale", methods=["POST"])
@cluster_required
def deployment_scale(namespace, name):
    data = request.get_json(silent=True) or {}
    replicas = data.get("replicas")
    if replicas is None or not isinstance(replicas, int) or replicas < 0:
        return jsonify({"error": "replicas must be a non-negative integer"}), 400
    try:
        result = _bc.scale_deployment(namespace, name, replicas)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Ingresses ─────────────────────────────────────────────────────────────────

@dashboard_bp.route("/ingresses")
@cluster_required
def ingresses_view():
    ings = k8s_obj(_bc.raw_ingresses())
    return render_template("ingresses.html", title="Ingresses",
                           ingresses=ings, age=age)


@dashboard_bp.route("/ingresses/<namespace>/<name>")
@cluster_required
def ingress_detail(namespace, name):
    raw = _bc.raw_ingress(namespace, name)
    if not raw: abort(404)
    ing = k8s_obj(raw)
    ev = sorted(k8s_obj(raw.get("_events", [])), key=lambda e: e.last_timestamp or "", reverse=True)
    try:
        import yaml as _y
        manifest_yaml = _y.safe_dump({k: v for k, v in raw.items() if not k.startswith("_")}, sort_keys=False, default_flow_style=False, width=120)
    except Exception as exc:
        manifest_yaml = f"# error: {exc}"
    return render_template("ingress_detail.html", title=name, ing=ing, events=ev, manifest_yaml=manifest_yaml, age=age)


# ── Jobs ─────────────────────────────────────────────────────────────────────

@dashboard_bp.route("/jobs")
@cluster_required
def jobs_view():
    data = _parallel({"jobs": _bc.raw_jobs, "cronjobs": _bc.raw_cronjobs})
    return render_template("jobs.html", title="Jobs & CronJobs",
                           jobs=k8s_obj(data["jobs"]),
                           crons=k8s_obj(data["cronjobs"]), age=age)


@dashboard_bp.route("/jobs/<namespace>/<name>")
@cluster_required
def job_detail(namespace, name):
    raw = _bc.raw_job(namespace, name)
    if not raw: abort(404)
    job = k8s_obj(raw)
    pods = k8s_obj(raw.get("_pods", []))
    ev = sorted(k8s_obj(raw.get("_events", [])), key=lambda e: e.last_timestamp or "", reverse=True)
    try:
        import yaml as _y
        manifest_yaml = _y.safe_dump({k: v for k, v in raw.items() if not k.startswith("_")}, sort_keys=False, default_flow_style=False, width=120)
    except Exception as exc:
        manifest_yaml = f"# error: {exc}"
    return render_template("job_detail.html", title=name, job=job, pods=pods, events=ev, manifest_yaml=manifest_yaml, age=age, phase_cls=phase_cls, ready_count=ready_count, restarts=restarts)

@dashboard_bp.route("/cronjobs/<namespace>/<name>")
@cluster_required
def cronjob_detail(namespace, name):
    raw = _bc.raw_cronjob(namespace, name)
    if not raw: abort(404)
    cj = k8s_obj(raw)
    child_jobs = k8s_obj(raw.get("_jobs", []))
    ev = sorted(k8s_obj(raw.get("_events", [])), key=lambda e: e.last_timestamp or "", reverse=True)
    try:
        import yaml as _y
        manifest_yaml = _y.safe_dump({k: v for k, v in raw.items() if not k.startswith("_")}, sort_keys=False, default_flow_style=False, width=120)
    except Exception as exc:
        manifest_yaml = f"# error: {exc}"
    return render_template("cronjob_detail.html", title=name, cj=cj, child_jobs=child_jobs, events=ev, manifest_yaml=manifest_yaml, age=age)


# ── Workloads ─────────────────────────────────────────────────────────────────

@dashboard_bp.route("/workloads")
@cluster_required
def workloads_view():
    data = _parallel({"statefulsets": _bc.raw_statefulsets, "daemonsets": _bc.raw_daemonsets})
    return render_template("workloads.html", title="StatefulSets & DaemonSets",
                           sts=k8s_obj(data["statefulsets"]),
                           ds=k8s_obj(data["daemonsets"]), age=age)


@dashboard_bp.route("/statefulsets/<namespace>/<name>")
@cluster_required
def statefulset_detail(namespace, name):
    raw = _bc.raw_statefulset(namespace, name)
    if not raw: abort(404)
    sts = k8s_obj(raw)
    pods = k8s_obj(raw.get("_pods", []))
    ev = sorted(k8s_obj(raw.get("_events", [])), key=lambda e: e.last_timestamp or "", reverse=True)
    try:
        import yaml as _y
        manifest_yaml = _y.safe_dump({k: v for k, v in raw.items() if not k.startswith("_")}, sort_keys=False, default_flow_style=False, width=120)
    except Exception as exc:
        manifest_yaml = f"# error: {exc}"
    return render_template("statefulset_detail.html", title=name, sts=sts, pods=pods, events=ev, manifest_yaml=manifest_yaml, age=age, phase_cls=phase_cls, ready_count=ready_count, restarts=restarts, fmt_cpu=fmt_cpu, fmt_mem=fmt_mem)

@dashboard_bp.route("/statefulsets/<namespace>/<name>/scale", methods=["POST"])
@cluster_required
def statefulset_scale(namespace, name):
    data = request.get_json(silent=True) or {}
    replicas = data.get("replicas")
    if replicas is None or not isinstance(replicas, int) or replicas < 0:
        return jsonify({"error": "replicas must be a non-negative integer"}), 400
    try:
        return jsonify(_bc.scale_statefulset(namespace, name, replicas))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@dashboard_bp.route("/daemonsets/<namespace>/<name>")
@cluster_required
def daemonset_detail(namespace, name):
    raw = _bc.raw_daemonset(namespace, name)
    if not raw: abort(404)
    ds = k8s_obj(raw)
    pods = k8s_obj(raw.get("_pods", []))
    ev = sorted(k8s_obj(raw.get("_events", [])), key=lambda e: e.last_timestamp or "", reverse=True)
    try:
        import yaml as _y
        manifest_yaml = _y.safe_dump({k: v for k, v in raw.items() if not k.startswith("_")}, sort_keys=False, default_flow_style=False, width=120)
    except Exception as exc:
        manifest_yaml = f"# error: {exc}"
    return render_template("daemonset_detail.html", title=name, ds=ds, pods=pods, events=ev, manifest_yaml=manifest_yaml, age=age, phase_cls=phase_cls, ready_count=ready_count, restarts=restarts)


# ── Storage ───────────────────────────────────────────────────────────────────

@dashboard_bp.route("/storage")
@cluster_required
def storage_view():
    data = _parallel({"pvs": _bc.raw_pvs, "pvcs": _bc.raw_pvcs})
    return render_template("storage.html", title="Persistent Volumes",
                           pvs=k8s_obj(data["pvs"]),
                           pvcs=k8s_obj(data["pvcs"]), age=age)


@dashboard_bp.route("/pvs/<name>")
@cluster_required
def pv_detail(name):
    raw = _bc.raw_pv(name)
    if not raw: abort(404)
    pv = k8s_obj(raw)
    ev = sorted(k8s_obj(raw.get("_events", [])), key=lambda e: e.last_timestamp or "", reverse=True)
    try:
        import yaml as _y
        manifest_yaml = _y.safe_dump({k: v for k, v in raw.items() if not k.startswith("_")}, sort_keys=False, default_flow_style=False, width=120)
    except Exception as exc:
        manifest_yaml = f"# error: {exc}"
    return render_template("pv_detail.html", title=name, pv=pv, events=ev, manifest_yaml=manifest_yaml, age=age)

@dashboard_bp.route("/pvcs/<namespace>/<name>")
@cluster_required
def pvc_detail(namespace, name):
    raw = _bc.raw_pvc(namespace, name)
    if not raw: abort(404)
    pvc = k8s_obj(raw)
    ev = sorted(k8s_obj(raw.get("_events", [])), key=lambda e: e.last_timestamp or "", reverse=True)
    try:
        import yaml as _y
        manifest_yaml = _y.safe_dump({k: v for k, v in raw.items() if not k.startswith("_")}, sort_keys=False, default_flow_style=False, width=120)
    except Exception as exc:
        manifest_yaml = f"# error: {exc}"
    return render_template("pvc_detail.html", title=name, pvc=pvc, events=ev, manifest_yaml=manifest_yaml, age=age)


# ── Config ────────────────────────────────────────────────────────────────────

@dashboard_bp.route("/config")
@cluster_required
def config_view():
    data = _parallel({"configmaps": _bc.raw_configmaps, "secrets": _bc.raw_secrets})
    return render_template("config.html", title="Config & Secrets",
                           configmaps=k8s_obj(data["configmaps"]),
                           secrets=k8s_obj(data["secrets"]), age=age)


@dashboard_bp.route("/configmaps/<namespace>/<name>")
@cluster_required
def configmap_detail(namespace, name):
    raw = _bc.raw_configmap(namespace, name)
    if not raw: abort(404)
    cm = k8s_obj(raw)
    try:
        import yaml as _y
        manifest_yaml = _y.safe_dump({k: v for k, v in raw.items() if not k.startswith("_")}, sort_keys=False, default_flow_style=False, width=120)
    except Exception as exc:
        manifest_yaml = f"# error: {exc}"
    return render_template("configmap_detail.html", title=name, cm=cm, manifest_yaml=manifest_yaml, age=age)

@dashboard_bp.route("/secrets/<namespace>/<name>")
@cluster_required
def secret_detail(namespace, name):
    raw = _bc.raw_secret(namespace, name)
    if not raw: abort(404)
    sec = k8s_obj(raw)
    try:
        import yaml as _y
        manifest_yaml = _y.safe_dump({k: v for k, v in raw.items() if not k.startswith("_")}, sort_keys=False, default_flow_style=False, width=120)
    except Exception as exc:
        manifest_yaml = f"# error: {exc}"
    return render_template("secret_detail.html", title=name, sec=sec, manifest_yaml=manifest_yaml, age=age)


# ── Events list ───────────────────────────────────────────────────────────────

@dashboard_bp.route("/events")
@cluster_required
def events_view():
    ns       = request.args.get("ns", "")
    data = _parallel({
        "events":     lambda: _bc.raw_events(namespace=ns),
        "namespaces": _bc.raw_namespaces,
    })
    all_evts = k8s_obj(data["events"])
    all_ns   = [n.metadata.name for n in k8s_obj(data["namespaces"])]
    evts = sorted(all_evts,
                  key=lambda e: e.last_timestamp or "",
                  reverse=True)
    return render_template("events.html", title="Events",
                           events=evts, namespaces=all_ns,
                           selected_ns=ns, age=age)


# ── Events stream (SSE — proxies backend) ────────────────────────────────────

@dashboard_bp.route("/events/stream")
@cluster_required
def events_stream():
    ns   = request.args.get("ns", "")
    hdrs = _bc._auth_headers()
    params = {"namespace": ns} if ns else {}
    url  = f"{BACKEND_SERVICE_URL.rstrip('/')}/api/stream/events"

    def generate():
        try:
            with _requests.get(url, headers=hdrs, params=params,
                               stream=True, timeout=360) as resp:
                for raw_line in resp.iter_lines():
                    if not raw_line:
                        continue
                    line = raw_line.decode("utf-8", errors="replace")
                    if line.startswith("data: "):
                        line = line[6:]
                    if line:
                        yield f"data: {line}\n\n"
        except GeneratorExit:
            return
        except Exception as e:
            yield f"data: Warning|||system|||system|||Error|||{e}\n\n"

    return Response(stream_with_context(generate()),
                    mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── Logs view ─────────────────────────────────────────────────────────────────

@dashboard_bp.route("/logs")
@cluster_required
def logs_view():
    ns     = request.args.get("ns", "")
    data   = _parallel({
        "namespaces": _bc.raw_namespaces,
        "pods":       lambda: _bc.raw_pods(namespace=ns),
    })
    all_ns = [n.metadata.name for n in k8s_obj(data["namespaces"])]
    pods   = k8s_obj(data["pods"])
    running       = [p for p in pods if p.status.phase == "Running"]
    selected_pods = request.args.getlist("pod")
    tail          = int(request.args.get("tail", 100))
    agg_logs      = []

    if selected_pods:
        def fetch(pod_name, pod_ns):
            try:
                txt   = _bc.raw_pod_logs(pod_ns, pod_name, tail=tail)
                return [(pod_name, log_cls(l), l) for l in txt.splitlines() if l]
            except Exception:
                return [(pod_name, "log-err", "[could not fetch logs]")]

        ctx_fetch = copy_current_request_context(fetch)
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            futs = {}
            for p in running:
                if p.metadata.name in selected_pods:
                    futs[pool.submit(ctx_fetch, p.metadata.name,
                                     p.metadata.namespace)] = p
            for fut in concurrent.futures.as_completed(futs):
                agg_logs.extend(fut.result())
        agg_logs.sort(key=lambda x: x[2][:30] if x[2] else "")

    return render_template("logs.html", title="Logs",
        namespaces=all_ns, selected_ns=ns, running_pods=running,
        selected_pods=selected_pods, tail=tail, agg_logs=agg_logs,
        log_cls=log_cls)


# ── Multi-pod log stream (SSE — proxies backend) ─────────────────────────────

@dashboard_bp.route("/logs/stream")
@cluster_required
def logs_stream():
    pod_name = request.args.get("pod", "")
    pod_ns   = request.args.get("ns", "")
    tail     = int(request.args.get("tail", 100))
    if not pod_name or not pod_ns:
        def _empty():
            yield "data: log-err|||[no pod specified]\n\n"
        return Response(stream_with_context(_empty()), mimetype="text/event-stream")

    hdrs   = _bc._auth_headers()
    params = {"tail": tail}
    url    = f"{BACKEND_SERVICE_URL.rstrip('/')}/api/stream/pods/{pod_ns}/{pod_name}/logs"

    def generate():
        try:
            with _requests.get(url, headers=hdrs, params=params,
                               stream=True, timeout=3600) as resp:
                for raw_line in resp.iter_lines():
                    if not raw_line:
                        continue
                    line = raw_line.decode("utf-8", errors="replace")
                    if line.startswith("data: "):
                        line = line[6:]
                    if line:
                        yield f"data: {pod_name}|||{log_cls(line)}|||{line}\n\n"
        except GeneratorExit:
            return
        except Exception as e:
            yield f"data: {pod_name}|||log-err|||[stream error: {e}]\n\n"

    return Response(stream_with_context(generate()),
                    mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
