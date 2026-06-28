import json
import logging
from collections import Counter
from datetime import datetime

from flask import (Blueprint, render_template, request, session,
                   redirect, url_for, jsonify, copy_current_request_context)

from ..auth_utils import cluster_required
from ..cache import _cache_scope
from ..config import CLUSTER_SCOPE
from ..database import audit
from ..formatters import age
from ..loki_client import query_range as loki_query
from ..storage import add_annotation, delete_annotation
from .. import backend_client as _bc

logger = logging.getLogger(__name__)

history_bp = Blueprint("history", __name__)


def _parse_dt(s):
    """Convert a stored datetime string to a datetime object, or None."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s))
    except (ValueError, TypeError):
        return None


# ── Historical events ─────────────────────────────────────────────────────────

@history_bp.route("/events/history")
@cluster_required
def events_history():
    ns    = (request.args.get("ns") or "").strip()
    type_ = (request.args.get("type") or "").strip()
    hours = int(request.args.get("hours", "24"))

    rows = loki_query(f'{{job="k8s-events", cluster="{CLUSTER_SCOPE}"}}',
                      hours=hours, limit=500)
    for r in rows:
        r["last_seen"]  = _parse_dt(r.get("last_seen"))
        r["first_seen"] = _parse_dt(r.get("first_seen"))
    if ns:    rows = [r for r in rows if r.get("ns") == ns]
    if type_: rows = [r for r in rows if r.get("type") == type_]
    all_ns = sorted({r.get("ns", "") for r in rows if r.get("ns")})

    return render_template("events_history.html", title="Events History",
                           rows=rows, namespaces=all_ns,
                           selected_ns=ns, selected_type=type_,
                           hours=hours, total=len(rows))


# ── Audit log ─────────────────────────────────────────────────────────────────

@history_bp.route("/audit")
@cluster_required
def audit_view():
    rows = loki_query('{job="k8s-audit"}', hours=168, limit=500)
    return render_template("audit.html", title="Audit Log", rows=rows)


# ── Pod lifecycle ─────────────────────────────────────────────────────────────

@history_bp.route("/lifecycle")
@cluster_required
def lifecycle_view():
    ns    = (request.args.get("ns") or "").strip()
    typ   = (request.args.get("type") or "").strip()
    hours = int(request.args.get("hours", "24"))

    rows = loki_query(f'{{job="pod-lifecycle", cluster="{CLUSTER_SCOPE}"}}',
                      hours=hours, limit=500)
    if ns:  rows = [r for r in rows if r.get("ns") == ns]
    if typ: rows = [r for r in rows if r.get("event_type") == typ]

    counts = Counter((r.get("ns", ""), r.get("pod_name", "")) for r in rows)
    top    = [{"ns": n, "pod_name": p, "events": c}
              for (n, p), c in counts.most_common(10)]
    nss    = sorted({r.get("ns", "") for r in rows if r.get("ns")})

    return render_template("lifecycle.html", title="Pod Lifecycle",
                           rows=rows, top=top, namespaces=nss,
                           selected_ns=ns, selected_type=typ, hours=hours)


# ── Log archive ───────────────────────────────────────────────────────────────

@history_bp.route("/logs/archive")
@cluster_required
def logs_archive_view():
    ns       = (request.args.get("ns") or "").strip()
    pod      = (request.args.get("pod") or "").strip()
    severity = (request.args.get("severity") or "").strip()
    search   = (request.args.get("q") or "").strip()
    hours    = int(request.args.get("hours", "24"))

    logql = f'{{job="pod-logs", cluster="{CLUSTER_SCOPE}"}}'
    if search:
        logql += f" |= {json.dumps(search)}"
    rows = loki_query(logql, hours=hours, limit=500)

    if ns:       rows = [r for r in rows if r.get("ns") == ns]
    if pod:      rows = [r for r in rows if r.get("pod_name") == pod]
    if severity: rows = [r for r in rows if r.get("severity") == severity]

    nss = sorted({r.get("ns", "") for r in rows if r.get("ns")})
    return render_template("logs_archive.html", title="Log Archive",
                           rows=rows, namespaces=nss, selected_ns=ns,
                           selected_pod=pod, selected_severity=severity,
                           search=search, hours=hours)


# ── Annotations ───────────────────────────────────────────────────────────────

@history_bp.route("/annotations/<kind>/<path:ref>", methods=["POST"])
@cluster_required
def annotation_add(kind, ref):
    if kind not in ("pod", "node", "namespace", "deployment", "service"):
        return ("bad kind", 400)
    ns, _, name = ref.partition("/")
    if not name:
        ns, name = "", ref
    body   = (request.form.get("body") or "").strip()
    pinned = request.form.get("pinned") == "1"
    if not body:
        return ("empty", 400)
    author = (session.get("user") or {}).get("email", "")
    add_annotation(_cache_scope(), kind, ns, name, body[:4000], author, pinned)
    audit("annotation.add", target=f"{kind}:{ns}/{name}")
    return redirect(request.referrer or url_for("dashboard.overview"))


@history_bp.route("/annotations/delete/<int:aid>", methods=["POST"])
@cluster_required
def annotation_delete(aid):
    delete_annotation(_cache_scope(), aid)
    audit("annotation.delete", target=str(aid))
    return redirect(request.referrer or url_for("dashboard.overview"))


# ── Search ────────────────────────────────────────────────────────────────────

@history_bp.route("/search")
@cluster_required
def search():
    from flask import current_app
    from ..k8s_obj import k8s_obj
    import concurrent.futures
    q = request.args.get("q", "").strip().lower()
    if not q or len(q) < 2:
        return ""
    results = []
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            f_pods  = pool.submit(copy_current_request_context(_bc.raw_pods))
            f_svcs  = pool.submit(copy_current_request_context(_bc.raw_services))
            f_deps  = pool.submit(copy_current_request_context(_bc.raw_deployments))
        pods = k8s_obj(f_pods.result())
        svcs = k8s_obj(f_svcs.result())
        deps = k8s_obj(f_deps.result())
        for p in pods:
            if q in (p.metadata.name or "").lower() or q in (p.metadata.namespace or "").lower():
                results.append({
                    "type": "Pod", "ns": p.metadata.namespace,
                    "name": p.metadata.name,
                    "url": f"/pods/{p.metadata.namespace}/{p.metadata.name}"})
        for s in svcs:
            if q in (s.metadata.name or "").lower():
                results.append({
                    "type": "Service", "ns": s.metadata.namespace,
                    "name": s.metadata.name, "url": "/services"})
        for d in deps:
            if q in (d.metadata.name or "").lower():
                results.append({
                    "type": "Deployment", "ns": d.metadata.namespace,
                    "name": d.metadata.name, "url": "/deployments"})
    except Exception as e:
        current_app.logger.exception("search failed for q=%r: %s", q, e)
    return render_template("partials/search_results.html", results=results[:12])



