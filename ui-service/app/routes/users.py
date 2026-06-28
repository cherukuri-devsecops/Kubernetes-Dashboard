"""User Management — list users who have stored kubeconfigs, manage access."""
import logging

from flask import Blueprint, render_template, request, jsonify, session

from ..auth_utils import login_required
from ..database import audit
from ..storage import list_kubeconfigs, delete_kubeconfig, _rows

logger = logging.getLogger(__name__)

users_bp = Blueprint("users", __name__)


def _all_users() -> list:
    """Return distinct user emails that have at least one kubeconfig stored."""
    return _rows("SELECT DISTINCT user_email, COUNT(*) AS kc_count FROM user_kubeconfig GROUP BY user_email ORDER BY user_email")


@users_bp.route("/users")
@login_required
def users_page():
    current_user = (session.get("user") or {}).get("email", "")
    users = _all_users()
    for u in users:
        u["kubeconfigs"] = list_kubeconfigs(u["user_email"])
        u["is_self"] = u["user_email"] == current_user
    return render_template(
        "users.html",
        title="User Management",
        users=users,
        current_user=current_user,
    )


@users_bp.route("/users/<email>/kubeconfigs/<name>/delete", methods=["POST"])
@login_required
def delete_user_kubeconfig(email: str, name: str):
    current_user = (session.get("user") or {}).get("email", "")
    try:
        delete_kubeconfig(email, name)
        audit("user.kubeconfig.delete", target=f"{email}/{name}", actor=current_user)
        return jsonify({"ok": True})
    except Exception as e:
        logger.error("delete_user_kubeconfig %s/%s: %s", email, name, e)
        return jsonify({"error": str(e)}), 500
