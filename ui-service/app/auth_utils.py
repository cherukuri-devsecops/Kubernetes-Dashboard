import logging
from functools import wraps

from flask import session, redirect, url_for, request, abort

logger = logging.getLogger(__name__)


def _check_login():
    if not session.get("user"):
        return redirect(url_for("auth.login_page"))


def login_required(f):
    @wraps(f)
    def _wrap(*a, **kw):
        r = _check_login()
        if r: return r
        return f(*a, **kw)
    return _wrap


def cluster_required(f):
    @wraps(f)
    def _wrap(*a, **kw):
        r = _check_login()
        if r: return r
        if not session.get("cluster_ok"):
            return redirect(url_for("setup.setup_page"))
        return f(*a, **kw)
    return _wrap


def csrf_protect():
    if "csrf_token" not in session:
        import secrets
        session["csrf_token"] = secrets.token_hex(32)

    if request.method in ("POST", "PUT", "DELETE"):
        if request.path == "/auth/callback":
            return
        token = (request.form.get("csrf_token")
                 or request.headers.get("X-CSRF-Token"))
        if not token or token != session.get("csrf_token"):
            logger.warning("CSRF validation failed for path: %s", request.path)
            abort(400, "CSRF token missing or invalid")


def log_request(response):
    if request.path.startswith("/static") or request.path.startswith("/health"):
        return response
    user_email = ""
    try:
        user_email = (session.get("user") or {}).get("email", "") or "anon"
    except Exception:
        user_email = "anon"
    logger.info("%-6s %-45s %d  user=%s",
                request.method, request.path, response.status_code, user_email)
    return response
