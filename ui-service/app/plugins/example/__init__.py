"""
Example plugin — Resource Summary.

Adds a page at /plugins/resource-summary that shows a simple count of all
resource types in the cluster.  This file demonstrates the plugin contract:

  blueprint  : Flask Blueprint
  PLUGIN_META: dict with name, description, icon, nav_url, nav_section
"""
from flask import Blueprint, render_template_string

from app.auth_utils import cluster_required
from app import backend_client as _bc

blueprint = Blueprint(
    "plugin_resource_summary",
    __name__,
    url_prefix="/plugins/resource-summary",
)

PLUGIN_META = {
    "name":        "Resource Summary",
    "description": "Shows a count breakdown of every resource kind in the cluster.",
    "icon":        "ti-chart-bar",
    "nav_url":     "/plugins/resource-summary",
    "nav_section": "Plugins",
    "version":     "1.0.0",
    "author":      "Example Plugin",
}

_TEMPLATE = """
{% extends "base.html" %}
{% block content %}
<div class="page-head">
  <h1><i class="ti ti-chart-bar" style="color:var(--teal)"></i> Resource Summary
    <span style="font-size:13px;color:var(--faint);margin-left:8px">Plugin · example</span>
  </h1>
</div>
<div class="card-grid" style="grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:16px;margin-top:24px">
  {% for item in summary %}
  <div class="card" style="padding:20px;text-align:center">
    <div style="font-size:32px;font-weight:800;color:var(--blue)">{{ item.count }}</div>
    <div style="font-size:12px;color:var(--muted);margin-top:4px;text-transform:capitalize">{{ item.kind }}</div>
  </div>
  {% endfor %}
</div>
{% endblock %}
"""

_FETCHERS = {
    "pods":        _bc.raw_pods,
    "deployments": _bc.raw_deployments,
    "statefulsets":_bc.raw_statefulsets,
    "daemonsets":  _bc.raw_daemonsets,
    "jobs":        _bc.raw_jobs,
    "services":    _bc.raw_services,
    "configmaps":  _bc.raw_configmaps,
    "secrets":     _bc.raw_secrets,
    "ingresses":   _bc.raw_ingresses,
    "pvcs":        _bc.raw_pvcs,
}


@blueprint.route("/")
@cluster_required
def index():
    summary = []
    for kind, fetch in _FETCHERS.items():
        try:
            summary.append({"kind": kind, "count": len(fetch())})
        except Exception:
            summary.append({"kind": kind, "count": "—"})
    return render_template_string(_TEMPLATE, summary=summary, title="Resource Summary")
