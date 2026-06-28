"""
k8s Observability Dashboard — entry point
"""
import logging
import os
import sys
from pathlib import Path

from flask import Flask, session, request, redirect, url_for
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_sock import Sock

# ── OpenTelemetry (no-op when OTEL_EXPORTER_OTLP_ENDPOINT is unset) ──────────
_otel_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
if _otel_endpoint:
    try:
        from opentelemetry import trace as _otel_trace
        from opentelemetry.sdk.trace import TracerProvider as _TP
        from opentelemetry.sdk.trace.export import BatchSpanProcessor as _BSP
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter as _OE
        from opentelemetry.instrumentation.requests import RequestsInstrumentor as _RI
        _provider = _TP()
        _provider.add_span_processor(_BSP(_OE(endpoint=_otel_endpoint, insecure=True)))
        _otel_trace.set_tracer_provider(_provider)
        _RI().instrument()
    except Exception as _otel_err:
        print(f"[otel] init failed (non-fatal): {_otel_err}", file=sys.stderr)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── Logging ───────────────────────────────────────────────────────────────────
from .config import LOG_LEVEL, KUBECONFIG_DIR, AUTH_SERVICE_URL, AUTH_JWT_SECRET

_log_fmt     = "[%(asctime)s] %(levelname)-7s %(name)s: %(message)s"
_log_datefmt = "%Y-%m-%d %H:%M:%S"
logging.basicConfig(level=LOG_LEVEL, format=_log_fmt, datefmt=_log_datefmt,
                    stream=sys.stdout, force=True)
logger = logging.getLogger("kube-dashboard")

# ── Flask app ─────────────────────────────────────────────────────────────────
app = Flask(__name__)

if _otel_endpoint:
    try:
        from opentelemetry.instrumentation.flask import FlaskInstrumentor as _FI
        _FI().instrument_app(app)
    except Exception as _otel_err:
        print(f"[otel] flask instrumentation failed (non-fatal): {_otel_err}", file=sys.stderr)

_DEFAULT_SECRET_KEY = "change-me-in-production"
app.secret_key = os.environ.get("SECRET_KEY") or _DEFAULT_SECRET_KEY
app.config.update(
    SESSION_COOKIE_SAMESITE=os.environ.get("SESSION_COOKIE_SAMESITE", "Lax"),
    SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "0") == "1",
)
if os.environ.get("TRUST_PROXY_HEADERS", "0") == "1":
    app.wsgi_app = ProxyFix(app.wsgi_app,
                            x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1)

sock = Sock(app)

app.logger.handlers = logging.getLogger().handlers
app.logger.setLevel(LOG_LEVEL)
logger.info("Starting kube-dashboard (log level: %s)", LOG_LEVEL)

Path(KUBECONFIG_DIR).mkdir(parents=True, exist_ok=True)
logger.debug("Kubeconfig directory: %s", KUBECONFIG_DIR)

if app.secret_key == _DEFAULT_SECRET_KEY:
    logger.warning("SECRET_KEY is using the built-in default; set SECRET_KEY for stable sessions")
if not AUTH_SERVICE_URL:
    logger.warning("AUTH_SERVICE_URL is not set — /auth/google will not redirect anywhere")
if not AUTH_JWT_SECRET:
    logger.warning("AUTH_JWT_SECRET is not set — /auth/callback will reject all logins")

# ── Request hooks ─────────────────────────────────────────────────────────────
from .auth_utils import csrf_protect, log_request

app.before_request(csrf_protect)
app.after_request(log_request)

# ── Blueprints ────────────────────────────────────────────────────────────────
from .routes.auth import auth_bp
from .routes.setup import setup_bp
from .routes.dashboard import dashboard_bp
from .routes.query import query_bp
from .routes.history import history_bp
from .routes.resources import resources_bp
from .routes.users import users_bp
from .routes.health import health_bp
from .routes.apm import apm_bp

app.register_blueprint(auth_bp)
app.register_blueprint(setup_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(query_bp)
app.register_blueprint(history_bp)
app.register_blueprint(users_bp)
app.register_blueprint(resources_bp)
app.register_blueprint(health_bp)
app.register_blueprint(apm_bp)

# ── Plugins ───────────────────────────────────────────────────────────────────
from .plugin_loader import load_plugins, get_plugin_nav, get_loaded_plugins

load_plugins(app)
logger.info("Plugins loaded: %s", [p["name"] for p in get_loaded_plugins()])

# ── WebSocket (needs the sock object defined above) ───────────────────────────
from .routes.dashboard import pod_exec_ws

sock.route("/ws/pods/<namespace>/<name>/exec")(pod_exec_ws)

# ── Context processor ─────────────────────────────────────────────────────────
import concurrent.futures as _cf

from .formatters import node_ready
from .k8s_obj import k8s_obj as _k8s_obj
from .backend_client import rbac_matrix_cached
from . import backend_client as _bc_nav
from .plugin_loader import get_plugin_nav


@app.context_processor
def inject_globals():
    user = session.get("user")
    nav, contexts, current = [], [], None
    plugin_nav: list = []
    can = lambda *_a, **_kw: True  # noqa: E731 — permissive default before cluster

    if user and session.get("cluster_ok"):
        _matrix = rbac_matrix_cached()
        can = lambda verb, kind, ns="": _matrix.get(kind.lower(), {}).get(verb, True)  # noqa: E731
        try:
            _tasks = {
                "pods":        _bc_nav.raw_pods,
                "nodes":       _bc_nav.raw_nodes,
                "namespaces":  _bc_nav.raw_namespaces,
                "services":    _bc_nav.raw_services,
                "deployments": _bc_nav.raw_deployments,
                "events":      _bc_nav.raw_events,
            }
            _out: dict = {}
            with _cf.ThreadPoolExecutor(max_workers=6) as _pool:
                _futs = {_pool.submit(fn): key for key, fn in _tasks.items()}
                for _fut in _cf.as_completed(_futs):
                    _out[_futs[_fut]] = _fut.result()

            pods  = _k8s_obj(_out.get("pods", []))
            nodes = _k8s_obj(_out.get("nodes", []))
            nss   = _k8s_obj(_out.get("namespaces", []))
            svcs  = _k8s_obj(_out.get("services", []))
            deps  = _k8s_obj(_out.get("deployments", []))
            evts  = _k8s_obj(_out.get("events", []))
            running = sum(1 for p in pods if p.status.phase == "Running")
            wrn     = sum(1 for e in evts if e.type == "Warning")
            rn      = sum(1 for n in nodes if node_ready(n))
            nav = [
                {"url": "/",            "icon": "ti-layout-dashboard", "label": "Overview",    "count": None,               "cls": ""},
                {"url": "/cluster",     "icon": "ti-topology-star",    "label": "Cluster",     "count": None,               "cls": ""},
                {"url": "/nodes",       "icon": "ti-server",           "label": "Nodes",       "count": f"{rn}/{len(nodes)}","cls": "" if rn == len(nodes) else "warn"},
                {"url": "/namespaces",  "icon": "ti-box-multiple",     "label": "Namespaces",  "count": len(nss),           "cls": ""},
                {"url": "/pods",        "icon": "ti-circles-relation", "label": "Pods",        "count": f"{running}/{len(pods)}", "cls": ""},
                {"url": "/deployments", "icon": "ti-stack-2",          "label": "Deployments", "count": len(deps),          "cls": ""},
                {"url": "/services",    "icon": "ti-network",          "label": "Services",    "count": len(svcs),          "cls": ""},
                {"url": "/events",      "icon": "ti-bell",             "label": "Events",      "count": wrn or None,        "cls": "err" if wrn else ""},
                {"url": "/logs",        "icon": "ti-file-text",        "label": "Logs",        "count": None,               "cls": ""},
            ]
        except Exception:
            pass
        if session.get("cluster_mode") == "kubeconfig":
            try:
                import yaml as _yaml
                from .database import get_kubeconfig
                kc_name = session.get("active_kubeconfig", "default")
                email   = (user or {}).get("email", "")
                content = get_kubeconfig(email, kc_name)
                if content:
                    cfg_dict     = _yaml.safe_load(content) or {}
                    contexts     = [c["name"] for c in cfg_dict.get("contexts", [])]
                    default_ctx  = cfg_dict.get("current-context")
                    current      = session.get("context") or default_ctx
            except Exception:
                pass
        plugin_nav = get_plugin_nav()

    active = request.path.rstrip("/") or "/"
    for item in nav:
        item["active"] = (item["url"] == active or
                          (item["url"] != "/" and active.startswith(item["url"])))
    css_path = os.path.join(app.static_folder or "static", "style.css")
    asset_v  = int(os.path.getmtime(css_path)) if os.path.exists(css_path) else 0
    return {
        "user": user, "nav": nav, "contexts": contexts,
        "current_ctx": current, "page_path": active, "asset_v": asset_v,
        "can": can, "plugin_nav": plugin_nav,
        "active_cluster": session.get("active_kubeconfig", "default"),
        "cluster_mode": session.get("cluster_mode", ""),
    }


# ── Database init ─────────────────────────────────────────────────────────────
from .database import db_init

db_init()

# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True, threaded=True)
