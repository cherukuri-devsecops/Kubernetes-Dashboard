import logging
import urllib.parse as _urlparse
import os

import jwt as _jwt
from flask import (Blueprint, render_template, request, session,
                   redirect, url_for)

from ..config import AUTH_SERVICE_URL, AUTH_JWT_SECRET, ALLOWED_EMAILS
from ..database import audit

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login")
def login_page():
    if session.get("user"):
        dest = "dashboard.overview" if session.get("cluster_ok") else "setup.setup_page"
        return redirect(url_for(dest))
    error = request.args.get("error")
    return render_template("login.html", title="Sign in", error=error)


@auth_bp.route("/auth/google")
def auth_google():
    if not AUTH_SERVICE_URL:
        return redirect(url_for("auth.login_page",
                                error="Auth service is not configured (missing AUTH_SERVICE_URL)."))
    callback_url = os.environ.get(
        "OAUTH_REDIRECT_URI",
        request.url_root.rstrip("/") + "/auth/callback")
    params = _urlparse.urlencode({"redirect_after": callback_url})
    logger.info("Auth: redirecting to auth service, redirect_after=%s", callback_url)
    return redirect(f"{AUTH_SERVICE_URL}?{params}")


@auth_bp.route("/auth/callback")
def auth_callback():
    if not AUTH_JWT_SECRET:
        logger.error("Auth callback: AUTH_JWT_SECRET is not configured; rejecting login")
        return redirect(url_for("auth.login_page",
                                error="Auth service is not configured."))

    token = request.args.get("access_token") or request.args.get("token")
    if not token:
        logger.error("Auth callback: no token in request args: %s",
                     list(request.args.keys()))
        return redirect(url_for("auth.login_page",
                                error="Login failed: no token received."))

    try:
        payload = _jwt.decode(token, AUTH_JWT_SECRET, algorithms=["HS256"])
        email   = (payload.get("email") or payload.get("sub") or "").strip()
        if not email:
            logger.error("Auth callback: no email in JWT payload")
            return redirect(url_for("auth.login_page",
                                    error="Login failed: no email in token."))

        session.clear()

        if ALLOWED_EMAILS and email.lower() not in ALLOWED_EMAILS:
            logger.warning("Auth: rejected %s (not in ALLOWED_EMAILS)", email)
            return redirect(url_for("auth.login_page",
                                    error=f"{email} is not on the allowed list."))

        session["user"] = {
            "email":   email,
            "name":    payload.get("name") or payload.get("given_name") or email,
            "picture": payload.get("picture") or "",
        }
        logger.info("Auth: %s signed in", email)
        audit("login", target=email)
        dest = "dashboard.overview" if session.get("cluster_ok") else "setup.setup_page"
        return redirect(url_for(dest))

    except _jwt.ExpiredSignatureError:
        logger.error("Auth callback: JWT expired")
        return redirect(url_for("auth.login_page",
                                error="Login session expired. Please try again."))
    except _jwt.InvalidTokenError as e:
        logger.error("Auth callback: invalid JWT: %s", e)
        return redirect(url_for("auth.login_page",
                                error="Login failed: invalid token."))
    except Exception as e:
        logger.error("Auth callback error: %s", e)
        return redirect(url_for("auth.login_page",
                                error="Login failed. Please try again."))


@auth_bp.route("/logout")
def logout():
    from pathlib import Path
    email = (session.get("user") or {}).get("email", "")
    kpath = session.get("kubeconfig_path")
    if kpath and Path(kpath).exists():
        try: Path(kpath).unlink()
        except Exception: pass
    audit("logout", target=email)
    session.clear()
    return redirect(url_for("auth.login_page"))
