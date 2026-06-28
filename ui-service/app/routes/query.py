import logging

from flask import Blueprint, render_template, request, session, redirect, url_for, jsonify

from ..auth_utils import cluster_required
from ..cache import _cache_scope
from ..database import audit
from .. import backend_client as _bc
from ..storage import get_saved_queries, upsert_saved_query, delete_saved_query

logger = logging.getLogger(__name__)

query_bp = Blueprint("query", __name__)


def _saved_queries_for_user():
    email = (session.get("user") or {}).get("email", "")
    if not email:
        return []
    return get_saved_queries(email)


def _run_query(q: str) -> dict:
    """Delegate query execution to the backend service."""
    scope = _cache_scope()
    return _bc.get("/api/query", q=q, scope=scope)


@query_bp.route("/query", methods=["GET"])
@cluster_required
def query_page():
    q = request.args.get("q", "").strip()
    result = None; error = None
    examples = [
        'SELECT name, ns, status, restarts, age FROM pods WHERE status != "Running" LIMIT 50',
        'SELECT name, ns, ready, desired FROM deployments WHERE ns ~ "kube" ORDER BY ready ASC',
        'SELECT name, cpu_pct, mem_pct FROM nodes ORDER BY cpu_pct DESC',
        'SELECT ns, count(*) FROM pods GROUP BY ns ORDER BY count DESC LIMIT 20',
        'SELECT type, reason, kind, object, message, age FROM events WHERE type = "Warning" LIMIT 50',
        'SELECT ts, ns, pod, container, type, reason FROM pod_lifecycle WHERE type = "oom" LIMIT 50',
        'SELECT pod, count(*) FROM pod_lifecycle WHERE type = "restart" GROUP BY pod ORDER BY count DESC LIMIT 20',
        'SELECT ts, ns, pod, container, severity, line FROM log_archive WHERE severity = "error" LIMIT 100',
        'SELECT ts, name, cpu_m, mem_mib FROM metric_history WHERE kind = "node" ORDER BY ts DESC LIMIT 100',
        'SELECT ts, user, action, target FROM audit ORDER BY ts DESC LIMIT 50',
    ]
    if q:
        try:
            result = _run_query(q)
            audit("query.run", target=q[:200], rows=result.get("total", 0))
        except Exception as e:
            error = str(e)
            audit("query.error", target=q[:200], error=error)
    saved = _saved_queries_for_user()
    if request.headers.get("HX-Request"):
        return render_template("partials/query_results.html",
                               result=result, error=error, q=q)
    return render_template("query.html", title="Query",
                           q=q, result=result, error=error,
                           examples=examples, saved=saved, db_ready=True)


@query_bp.route("/api/query")
@cluster_required
def query_api():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"error": "missing q"}), 400
    try:
        result = _run_query(q)
        audit("query.run", target=q[:200], rows=result.get("total", 0))
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@query_bp.route("/query/save", methods=["POST"])
@cluster_required
def query_save():
    email = (session.get("user") or {}).get("email", "")
    name  = (request.form.get("name") or "").strip()
    q     = (request.form.get("q") or "").strip()
    if not email or not name or not q:
        return ("name and q required", 400)
    upsert_saved_query(email, name, q)
    audit("query.save", target=name)
    return redirect(url_for("query.query_page", q=q))


@query_bp.route("/query/delete/<int:qid>", methods=["POST"])
@cluster_required
def query_delete(qid):
    email = (session.get("user") or {}).get("email", "")
    delete_saved_query(email, qid)
    audit("query.delete", target=str(qid))
    return redirect(url_for("query.query_page"))
