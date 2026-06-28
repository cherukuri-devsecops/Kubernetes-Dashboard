import hashlib
import logging
import os
import re
import tempfile
from pathlib import Path

import yaml as _yaml
from flask import (Blueprint, render_template, request, session,
                   redirect, url_for, jsonify)

from ..auth_utils import login_required
from ..cache import cache_invalidate
from ..config import KUBECONFIG_DIR
from ..database import (audit, db_ready, save_kubeconfig, get_kubeconfig,
                        list_kubeconfigs, delete_kubeconfig)
from .. import backend_client as _bc
def rbac_invalidate(): pass  # RBAC cache lives in backend-service; TTL auto-expires

logger = logging.getLogger(__name__)

setup_bp = Blueprint("setup", __name__)


# ── Local filesystem fallback for kubeconfig storage ─────────────────────────

def _safe_kubeconfig_name(name: str) -> str:
    """Validate kubeconfig name for safe filesystem use."""
    candidate = (name or "default").strip()
    if candidate in {".", ".."}:
        raise ValueError("Invalid kubeconfig name")
    if "/" in candidate or "\\" in candidate:
        raise ValueError("Invalid kubeconfig name")
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", candidate):
        raise ValueError("Invalid kubeconfig name")
    return candidate


def _kc_file_path(email: str, name: str = "default") -> Path:
    """Deterministic file path for a named kubeconfig, keyed by email hash."""
    safe_name = _safe_kubeconfig_name(name)
    uid = hashlib.sha256((email or "local").encode()).hexdigest()[:16]
    return Path(KUBECONFIG_DIR) / f"{uid}_{safe_name}.yaml"


def _save_kubeconfig_local(content: str, email: str, name: str = "default") -> str:
    """Write kubeconfig YAML to filesystem. Returns the file path."""
    path = _kc_file_path(email, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    logger.info("Setup: kubeconfig saved locally → %s", path)
    return str(path)


def _get_kubeconfig_local(email: str, name: str = "default") -> str | None:
    """Read a locally stored kubeconfig. Returns content string or None."""
    path = _kc_file_path(email, name)
    if path.exists():
        return path.read_text(encoding="utf-8")
    return None


def _delete_kubeconfig_local(email: str, name: str = "default"):
    path = _kc_file_path(email, name)
    path.unlink(missing_ok=True)


def _get_kc_content(email: str, name: str = "default") -> str | None:
    """Get kubeconfig content from DB if available, then file fallback."""
    if db_ready():
        return get_kubeconfig(email, name)
    return _get_kubeconfig_local(email, name)


def _save_kc(email: str, content: str, name: str = "default") -> str | None:
    """Save kubeconfig to DB if available, else filesystem. Returns file path or None."""
    if db_ready():
        save_kubeconfig(email, content, name)
        return None
    return _save_kubeconfig_local(content, email, name)


def _list_kcs_local(email: str) -> list[dict]:
    """List locally stored kubeconfigs for this user."""
    uid = hashlib.sha256((email or "local").encode()).hexdigest()[:16]
    kc_dir = Path(KUBECONFIG_DIR)
    result = []
    if kc_dir.exists():
        for p in sorted(kc_dir.glob(f"{uid}_*.yaml")):
            name = p.stem[len(uid) + 1:]  # strip uid_ prefix
            result.append({"name": name, "updated_at": None, "_path": str(p)})
    return result


def _try_auto_connect():
    """Auto-connect using a saved kubeconfig (DB or local file).
    Returns True if the session was set up successfully."""
    email   = (session.get("user") or {}).get("email", "")
    kc_name = session.get("active_kubeconfig", "default")
    content = _get_kc_content(email, kc_name)
    if not content:
        return False
    session["cluster_mode"] = "kubeconfig"
    session["context"] = None
    try:
        v = _bc.raw_version()
        session["cluster_ok"]       = True
        session["cluster_version"]  = v.get("git_version", "—")
        session["cluster_platform"] = v.get("platform", "—")
        storage = "db" if db_ready() else "file"
        logger.info("Setup: auto-connected from %s kubeconfig (email=%s, version=%s)",
                    storage, email, v.get("git_version"))
        audit("cluster.auto_connect", target=f"{storage}-kubeconfig", version=v.get("git_version"))
        return True
    except Exception as e:
        logger.warning("Setup: auto-connect failed: %s", e)
        session.pop("cluster_mode", None)
        return False


@setup_bp.route("/setup", methods=["GET", "POST"])
@login_required
def setup_page():
    if request.method == "GET":
        # Auto-connect if this user already has a kubeconfig stored in the DB
        if not session.get("cluster_ok") and _try_auto_connect():
            return redirect(url_for("dashboard.overview"))
        error = request.args.get("error")
        return render_template("setup.html", title="Cluster Setup", error=error)

    # ── POST ──────────────────────────────────────────────────────────────────
    mode = request.form.get("mode")

    if mode == "kubeconfig":
        f = request.files.get("kubeconfig")
        if not f or not f.filename:
            return render_template("setup.html", title="Setup",
                                   error="Please select a kubeconfig file.")
        content = f.read().decode("utf-8", errors="replace")
        email   = (session.get("user") or {}).get("email", "")
        kc_path = _save_kc(email, content)   # DB if available, else file
        if kc_path:
            session["kubeconfig_path"] = kc_path
        session["cluster_mode"]      = "kubeconfig"
        session["active_kubeconfig"] = "default"

    elif mode == "token":
        server  = request.form.get("server", "").strip()
        token   = request.form.get("token", "").strip()
        ca_cert = request.form.get("ca_cert", "").strip()
        if not server or not token:
            return render_template("setup.html", title="Setup",
                                   error="Server URL and token are required.")
        ca_path = None
        if ca_cert:
            fd, ca_path = tempfile.mkstemp(suffix=".crt", prefix="kube_ca_")
            try:
                os.write(fd, ca_cert.encode())
            finally:
                os.close(fd)
        session["cluster_token"] = {"server": server, "token": token,
                                    "ca_path": ca_path}
        session["cluster_mode"]  = "token"

    elif mode == "incluster":
        session["cluster_mode"] = "incluster"

    else:
        session["cluster_mode"] = "local"

    # Validate context against the kubeconfig YAML
    ctx = (request.form.get("context") or "").strip()
    if ctx and session.get("cluster_mode") == "kubeconfig":
        try:
            email   = (session.get("user") or {}).get("email", "")
            kc_name = session.get("active_kubeconfig", "default")
            content = _get_kc_content(email, kc_name)
            config_dict = _yaml.safe_load(content or "") or {}
            valid = [c["name"] for c in config_dict.get("contexts", [])]
            if ctx not in valid:
                logger.warning("Setup: context %r not in kubeconfig (available: %s)",
                               ctx, valid)
                return render_template("setup.html", title="Setup",
                    error=f"Context '{ctx}' not found in kubeconfig. "
                          f"Available: {', '.join(valid) or '(none)'}")
        except Exception as e:
            logger.error("Setup: could not parse kubeconfig: %s", e, exc_info=True)
            return render_template("setup.html", title="Setup",
                                   error=f"Could not read kubeconfig: {e}")
    session["context"] = ctx or None

    try:
        v = _bc.raw_version()
        session["cluster_ok"]       = True
        session["cluster_version"]  = v.get("git_version", "—")
        session["cluster_platform"] = v.get("platform", "—")
        logger.info("Setup: connected to cluster (mode=%s, version=%s, context=%s)",
                    session.get("cluster_mode"), v.get("git_version"), ctx or "<default>")
        audit("cluster.setup", target=ctx or "<default>",
              mode=session.get("cluster_mode"), version=v.get("git_version"))
    except Exception as e:
        logger.error("Setup: cluster connection failed (mode=%s): %s",
                     session.get("cluster_mode"), e, exc_info=True)
        return render_template("setup.html", title="Setup",
                               error=f"Cannot connect to cluster: {e}")

    return redirect(url_for("dashboard.overview"))


@setup_bp.route("/ctx", methods=["POST"])
@login_required
def switch_ctx():
    ctx = request.form.get("ctx")
    if ctx:
        session["context"] = ctx
        cache_invalidate()
        rbac_invalidate()
    return redirect(request.referrer or url_for("dashboard.overview"))


@setup_bp.route("/refresh", methods=["POST", "GET"])
@login_required
def refresh_cache():
    cache_invalidate()
    return redirect(request.referrer or url_for("dashboard.overview"))


# ── Multi-cluster management ──────────────────────────────────────────────────

@setup_bp.route("/clusters")
@login_required
def clusters_list():
    """List all saved kubeconfigs / cluster connections for this user."""
    email = (session.get("user") or {}).get("email", "")
    configs = list_kubeconfigs(email) if db_ready() else _list_kcs_local(email)
    active_kc = session.get("active_kubeconfig", "default")
    return render_template("clusters.html", title="Clusters",
                           configs=configs, active_kc=active_kc,
                           cluster_mode=session.get("cluster_mode"),
                           db_available=db_ready())


@setup_bp.route("/clusters/add", methods=["POST"])
@login_required
def cluster_add():
    """Add (or replace) a named kubeconfig and optionally activate it."""
    email  = (session.get("user") or {}).get("email", "")
    name   = (request.form.get("cluster_name") or "").strip()
    f      = request.files.get("kubeconfig")
    activate = request.form.get("activate") == "1"

    if not name:
        return redirect(url_for("setup.clusters_list") + "?error=Name+is+required")
    if not f or not f.filename:
        return redirect(url_for("setup.clusters_list") + "?error=No+file+selected")

    content = f.read().decode("utf-8", errors="replace")
    try:
        _yaml.safe_load(content)
    except Exception as e:
        return redirect(url_for("setup.clusters_list") + f"?error=Invalid+kubeconfig:+{e}")

    kc_path = _save_kc(email, content, name)  # DB or file
    audit("cluster.kubeconfig_saved", target=name)

    if activate:
        session["cluster_mode"]        = "kubeconfig"
        session["active_kubeconfig"]   = name
        session["context"]             = None
        if kc_path:
            session["kubeconfig_path"] = kc_path
        cache_invalidate(); rbac_invalidate()
        try:
            v = _bc.raw_version()
            session["cluster_ok"]       = True
            session["cluster_version"]  = v.get("git_version", "—")
            session["cluster_platform"] = v.get("platform", "—")
        except Exception as e:
            return redirect(url_for("setup.clusters_list") + f"?error=Connect+failed:+{e}")

    return redirect(url_for("setup.clusters_list"))


@setup_bp.route("/clusters/<name>/activate", methods=["POST"])
@login_required
def cluster_activate(name):
    """Switch the active kubeconfig by name."""
    email   = (session.get("user") or {}).get("email", "")
    content = _get_kc_content(email, name)
    if not content:
        return redirect(url_for("setup.clusters_list") + "?error=Cluster+not+found")

    session["cluster_mode"]      = "kubeconfig"
    session["active_kubeconfig"] = name
    session["context"]           = None
    # If file-based, refresh path in session
    if not db_ready():
        kc_path = str(_kc_file_path(email, name))
        session["kubeconfig_path"] = kc_path
    cache_invalidate(); rbac_invalidate()
    try:
        v = _bc.raw_version()
        session["cluster_ok"]       = True
        session["cluster_version"]  = v.get("git_version", "—")
        session["cluster_platform"] = v.get("platform", "—")
        audit("cluster.activated", target=name)
    except Exception as e:
        return redirect(url_for("setup.clusters_list") + f"?error=Connect+failed:+{e}")
    return redirect(url_for("dashboard.overview"))


@setup_bp.route("/clusters/<name>/delete", methods=["POST"])
@login_required
def cluster_delete(name):
    """Remove a saved kubeconfig."""
    email = (session.get("user") or {}).get("email", "")
    if db_ready():
        delete_kubeconfig(email, name)
    else:
        _delete_kubeconfig_local(email, name)
    audit("cluster.kubeconfig_deleted", target=name)
    if session.get("active_kubeconfig") == name:
        session.pop("active_kubeconfig", None)
        session.pop("cluster_ok", None)
        session.pop("cluster_mode", None)
        session.pop("kubeconfig_path", None)
        cache_invalidate(); rbac_invalidate()
    return redirect(url_for("setup.clusters_list"))
