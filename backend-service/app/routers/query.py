"""GET /api/query — SQL-like query engine over live K8s + Loki data."""
import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Query as QParam
from kubernetes.client import ApiClient

from ..k8s_client import _header_dep, core_v1, apps_v1, batch_v1, net_v1, custom_api
from ..loki_client import query_range as _loki_query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/query", tags=["query"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _age_str(ts) -> str:
    if ts is None:
        return ""
    from datetime import datetime, timezone
    if isinstance(ts, str):
        try:
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            return str(ts)
    now = datetime.now(timezone.utc)
    diff = now - ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else now - ts
    s = int(diff.total_seconds())
    if s < 60:   return f"{s}s"
    if s < 3600: return f"{s // 60}m"
    if s < 86400: return f"{s // 3600}h"
    return f"{s // 86400}d"


def _parse_cpu(val: str) -> int:
    val = (val or "0").strip()
    if val.endswith("m"): return int(val[:-1])
    return int(float(val) * 1000)


def _parse_mem(val: str) -> int:
    val = (val or "0").strip()
    for s, m in [("Ki", 1024), ("Mi", 1024**2), ("Gi", 1024**3)]:
        if val.endswith(s): return int(val[:-len(s)]) * m
    return int(val or 0)


# ── Row builders ──────────────────────────────────────────────────────────────

def _rows_pods(ac):
    core = core_v1(ac); cust = custom_api(ac)
    items = core.list_pod_for_all_namespaces().items
    pm: dict = {}
    try:
        data = cust.list_cluster_custom_object("metrics.k8s.io", "v1beta1", "pods")
        for it in data.get("items", []):
            k = f"{it['metadata']['namespace']}/{it['metadata']['name']}"
            pm[k] = {
                "cpu": sum(_parse_cpu(c["usage"]["cpu"]) for c in it.get("containers", [])),
                "mem": sum(_parse_mem(c["usage"]["memory"]) for c in it.get("containers", [])),
            }
    except Exception:
        pass
    rows = []
    for p in items:
        cs = p.status.container_statuses or []
        rc = sum(1 for c in cs if c.ready)
        rs = sum(c.restart_count for c in cs)
        usage = pm.get(f"{p.metadata.namespace}/{p.metadata.name}", {})
        rows.append({
            "name": p.metadata.name, "ns": p.metadata.namespace,
            "status": p.status.phase or "", "node": p.spec.node_name or "",
            "ready": f"{rc}/{len(cs)}", "ready_n": rc, "ready_d": len(cs),
            "restarts": rs, "ip": p.status.pod_ip or "",
            "image": (p.spec.containers[0].image if p.spec.containers else ""),
            "age": _age_str(p.metadata.creation_timestamp),
            "cpu_m": round(usage.get("cpu", 0)),
            "mem_mib": round(usage.get("mem", 0) / 1024**2),
            "labels": ",".join(f"{k}={v}" for k, v in (p.metadata.labels or {}).items()),
        })
    return rows


def _rows_nodes(ac):
    core = core_v1(ac); cust = custom_api(ac)
    nodes = core.list_node().items
    nm: dict = {}
    try:
        data = cust.list_cluster_custom_object("metrics.k8s.io", "v1beta1", "nodes")
        nm = {it["metadata"]["name"]: it for it in data.get("items", [])}
    except Exception:
        pass
    rows = []
    for n in nodes:
        alloc = n.status.allocatable or {}
        ncap  = _parse_cpu(alloc.get("cpu", "0"))
        nmcap = _parse_mem(alloc.get("memory", "0"))
        u     = nm.get(n.metadata.name, {}).get("usage", {})
        ncpu  = _parse_cpu(u.get("cpu", "0"))
        nmem  = _parse_mem(u.get("memory", "0"))
        ready = any(c.type == "Ready" and c.status == "True" for c in (n.status.conditions or []))
        roles = ",".join(k.split("/")[1] for k in (n.metadata.labels or {}) if k.startswith("node-role.kubernetes.io/")) or "worker"
        rows.append({
            "name": n.metadata.name, "ready": ready, "roles": roles,
            "version": (n.status.node_info.kubelet_version if n.status.node_info else ""),
            "age": _age_str(n.metadata.creation_timestamp),
            "cpu_cap_m": round(ncap), "mem_cap_mib": round(nmcap / 1024**2),
            "cpu_used_m": round(ncpu), "mem_used_mib": round(nmem / 1024**2),
            "cpu_pct": round(ncpu / ncap * 100) if ncap else 0,
            "mem_pct": round(nmem / nmcap * 100) if nmcap else 0,
        })
    return rows


def _rows_deploys(ac):
    items = apps_v1(ac).list_deployment_for_all_namespaces().items
    rows = []
    for d in items:
        r = d.status.ready_replicas or 0; des = d.spec.replicas or 0
        rows.append({
            "name": d.metadata.name, "ns": d.metadata.namespace,
            "ready": r, "desired": des, "available": d.status.available_replicas or 0,
            "status": "Running" if r == des and des > 0 else "Degraded",
            "age": _age_str(d.metadata.creation_timestamp),
        })
    return rows


def _rows_simple(items, extra=None):
    rows = []
    for o in items:
        md = o.metadata
        row = {"name": md.name, "ns": md.namespace or "", "age": _age_str(md.creation_timestamp)}
        if extra:
            for k, fn in extra.items():
                try: row[k] = fn(o)
                except Exception: row[k] = ""
        rows.append(row)
    return rows


def _fetch_rows(src: str, ac: ApiClient) -> list:
    c = core_v1(ac); a = apps_v1(ac); b = batch_v1(ac); n = net_v1(ac)
    if src == "pods":        return _rows_pods(ac)
    if src == "nodes":       return _rows_nodes(ac)
    if src == "deployments": return _rows_deploys(ac)
    if src == "statefulsets":
        items = a.list_stateful_set_for_all_namespaces().items
        return _rows_simple(items, {"ready": lambda s: s.status.ready_replicas or 0, "desired": lambda s: s.spec.replicas or 0})
    if src == "daemonsets":
        items = a.list_daemon_set_for_all_namespaces().items
        return _rows_simple(items, {"ready": lambda d: d.status.number_ready or 0, "desired": lambda d: d.status.desired_number_scheduled or 0})
    if src == "services":
        items = c.list_service_for_all_namespaces().items
        return _rows_simple(items, {"type": lambda s: s.spec.type or "", "cluster_ip": lambda s: s.spec.cluster_ip or ""})
    if src == "namespaces":
        items = c.list_namespace().items
        return _rows_simple(items, {"phase": lambda ns: ns.status.phase or ""})
    if src == "jobs":
        items = b.list_job_for_all_namespaces().items
        return _rows_simple(items, {"succeeded": lambda j: j.status.succeeded or 0, "completions": lambda j: j.spec.completions or 1})
    if src == "cronjobs":
        items = b.list_cron_job_for_all_namespaces().items
        return _rows_simple(items, {"schedule": lambda c: c.spec.schedule or "", "suspend": lambda c: bool(c.spec.suspend)})
    if src == "events":
        items = c.list_event_for_all_namespaces().items
        return [{"ns": e.metadata.namespace, "type": e.type or "", "reason": e.reason or "",
                 "kind": (e.involved_object.kind or "") if e.involved_object else "",
                 "object": (e.involved_object.name or "") if e.involved_object else "",
                 "message": e.message or "", "count": e.count or 0,
                 "age": _age_str(e.last_timestamp or e.metadata.creation_timestamp)} for e in items]
    if src == "pvs":
        items = c.list_persistent_volume().items
        return _rows_simple(items, {"phase": lambda p: p.status.phase or "", "capacity": lambda p: (p.spec.capacity or {}).get("storage", "")})
    if src == "pvcs":
        items = c.list_persistent_volume_claim_for_all_namespaces().items
        return _rows_simple(items, {"phase": lambda p: p.status.phase or "", "storage_class": lambda p: p.spec.storage_class_name or ""})
    if src == "configmaps":
        return _rows_simple(c.list_config_map_for_all_namespaces().items)
    if src == "secrets":
        items = c.list_secret_for_all_namespaces().items
        return _rows_simple(items, {"type": lambda s: s.type or ""})
    if src == "ingresses":
        try: items = n.list_ingress_for_all_namespaces().items
        except Exception: items = []
        return _rows_simple(items)
    raise ValueError(f"unknown resource: {src}")


def _fetch_loki(src: str, scope: str) -> list:
    logql_map = {
        "pod_lifecycle":  f'{{job="pod-lifecycle", cluster="{scope}"}}',
        "log_archive":    f'{{job="pod-logs", cluster="{scope}"}}',
        "event_history":  f'{{job="k8s-events", cluster="{scope}"}}',
        "metric_history": f'{{job="k8s-metrics", cluster="{scope}"}}',
        "audit":          '{job="k8s-audit"}',
    }
    if src not in logql_map:
        raise ValueError(f"unknown loki source: {src}")
    rows = list(_loki_query(logql_map[src], hours=24, limit=5000))
    if src == "pod_lifecycle":
        for r in rows:
            r.setdefault("pod", r.get("pod_name", "")); r.setdefault("type", r.get("event_type", ""))
    if src == "audit":
        for r in rows:
            r.setdefault("user", r.get("user_email", ""))
    return rows


STAR_COLS = {
    "pods":          ["name","ns","status","node","ready","restarts","ip","image","age","cpu_m","mem_mib","labels"],
    "nodes":         ["name","ready","roles","version","age","cpu_cap_m","mem_cap_mib","cpu_used_m","mem_used_mib","cpu_pct","mem_pct"],
    "deployments":   ["name","ns","ready","desired","available","status","age"],
    "statefulsets":  ["name","ns","ready","desired","age"],
    "services":      ["name","ns","type","cluster_ip","age"],
    "events":        ["ns","type","reason","kind","object","message","count","age"],
    "namespaces":    ["name","phase","age"],
    "daemonsets":    ["name","ns","ready","desired","age"],
    "jobs":          ["name","ns","succeeded","completions","age"],
    "cronjobs":      ["name","ns","schedule","suspend","age"],
    "pvs":           ["name","phase","capacity","age"],
    "pvcs":          ["name","ns","phase","storage_class","age"],
    "configmaps":    ["name","ns","age"],
    "secrets":       ["name","ns","type","age"],
    "ingresses":     ["name","ns","age"],
    "pod_lifecycle": ["ts","ns","pod","container","type","reason","exit_code","restart_count","message"],
    "log_archive":   ["ts","ns","pod","container","severity","line"],
    "event_history": ["ts","ns","type","reason","kind","object","message","count"],
    "metric_history":["ts","kind","name","ns","cpu_m","mem_mib"],
    "audit":         ["ts","user","action","target"],
}

_LOKI_SOURCES = {"pod_lifecycle", "log_archive", "event_history", "metric_history", "audit"}
_K8S_SOURCES  = set(STAR_COLS) - _LOKI_SOURCES


# ── Tokenizer / parser ────────────────────────────────────────────────────────

_TOKEN_RE = re.compile(r"""
    \s*(?:
        (?P<str>"[^"]*"|'[^']*')   |
        (?P<num>-?\d+(?:\.\d+)?)   |
        (?P<op>!=|>=|<=|!~|=|~|>|<|,|\(|\)|\*) |
        (?P<word>[A-Za-z_][A-Za-z0-9_]*)
    )
""", re.VERBOSE)


def _tokenize(q):
    pos = 0; toks = []
    while pos < len(q):
        m = _TOKEN_RE.match(q, pos)
        if not m: raise ValueError(f"unexpected char at {pos}: {q[pos]!r}")
        pos = m.end()
        if m.group("str"):   toks.append(("STR",  m.group("str")[1:-1]))
        elif m.group("num"): toks.append(("NUM",  float(m.group("num")) if "." in m.group("num") else int(m.group("num"))))
        elif m.group("op"):  toks.append(("OP",   m.group("op")))
        elif m.group("word"):toks.append(("WORD", m.group("word")))
    return toks


def _parse_query(q):
    toks = _tokenize(q); i = 0

    def peek(off=0):
        return toks[i + off] if i + off < len(toks) else (None, None)

    def eat(*kinds):
        nonlocal i
        t, v = peek()
        if kinds and t not in kinds and v not in kinds:
            raise ValueError(f"expected {kinds}, got {t}:{v}")
        i += 1; return v

    def kw(*words):
        t, v = peek()
        return t == "WORD" and v.upper() in words

    if not kw("SELECT"): raise ValueError("query must start with SELECT")
    eat(); cols = []
    while True:
        t, v = peek()
        if t == "OP" and v == "*": cols.append({"col": "*", "agg": None}); i += 1
        elif t == "WORD" and peek(1) == ("OP", "(") and v.lower() == "count":
            i += 1; eat("(")
            inner_t, inner_v = peek()
            if inner_t == "OP" and inner_v == "*": i += 1
            else: eat("WORD")
            eat(")"); cols.append({"col": "*", "agg": "count"})
        elif t == "WORD": cols.append({"col": v, "agg": None}); i += 1
        else: raise ValueError(f"bad column at token {i}")
        if peek() == ("OP", ","): i += 1; continue
        break

    if not kw("FROM"): raise ValueError("expected FROM")
    eat()
    src_t, src_v = peek()
    if src_t != "WORD": raise ValueError("expected resource name after FROM")
    src = src_v.lower(); i += 1
    if src not in STAR_COLS: raise ValueError(f"unknown resource: {src}")

    where = None
    if kw("WHERE"):
        eat(); where, i = _parse_or(toks, i)

    group_by = None
    if kw("GROUP"):
        eat()
        if not kw("BY"): raise ValueError("expected BY after GROUP")
        eat(); gt, gv = peek()
        if gt != "WORD": raise ValueError("expected column after GROUP BY")
        group_by = gv; i += 1

    order_by = None; order_desc = False
    if kw("ORDER"):
        eat()
        if not kw("BY"): raise ValueError("expected BY after ORDER")
        eat(); ot, ov = peek()
        if ot != "WORD": raise ValueError("expected column after ORDER BY")
        order_by = ov; i += 1
        if kw("DESC"): order_desc = True; eat()
        elif kw("ASC"): eat()

    limit = None
    if kw("LIMIT"):
        eat(); lt, lv = peek()
        if lt != "NUM": raise ValueError("expected number after LIMIT")
        limit = int(lv); i += 1

    return {"cols": cols, "from": src, "where": where,
            "group_by": group_by, "order_by": order_by,
            "order_desc": order_desc, "limit": limit}


def _parse_or(toks, i):
    left, i = _parse_and(toks, i)
    while i < len(toks) and toks[i] == ("WORD", "OR"):
        i += 1; right, i = _parse_and(toks, i); left = ("or", left, right)
    return left, i


def _parse_and(toks, i):
    left, i = _parse_cmp(toks, i)
    while i < len(toks) and toks[i] == ("WORD", "AND"):
        i += 1; right, i = _parse_cmp(toks, i); left = ("and", left, right)
    return left, i


def _parse_cmp(toks, i):
    if i < len(toks) and toks[i] == ("OP", "("):
        i += 1; node, i = _parse_or(toks, i)
        if toks[i] != ("OP", ")"): raise ValueError("missing )")
        return node, i + 1
    t, v = toks[i]
    if t != "WORD": raise ValueError(f"expected column at {i}")
    col = v; i += 1
    op = toks[i][1]; i += 1
    rt, rv = toks[i]
    if rt not in ("STR", "NUM", "WORD"): raise ValueError(f"bad rvalue at {i}")
    return ("cmp", col, op, rv), i + 1


def _match(row, node):
    if node is None: return True
    k = node[0]
    if k == "and": return _match(row, node[1]) and _match(row, node[2])
    if k == "or":  return _match(row, node[1]) or  _match(row, node[2])
    _, col, op, rv = node
    lv = row.get(col)
    if lv is None: return False
    try:
        if op in (">", "<", ">=", "<="):
            return {">": float(lv) > float(rv), "<": float(lv) < float(rv),
                    ">=": float(lv) >= float(rv), "<=": float(lv) <= float(rv)}[op]
    except (TypeError, ValueError): pass
    ls = str(lv); rs = str(rv)
    if op == "=":  return ls == rs
    if op == "!=": return ls != rs
    if op == "~":  return bool(re.search(rs, ls, re.IGNORECASE))
    if op == "!~": return not re.search(rs, ls, re.IGNORECASE)
    return False


# ── Route ─────────────────────────────────────────────────────────────────────

@router.get("")
def run_query(
    q:     str       = QParam(..., description="SQL-like query string"),
    scope: str       = QParam(default="", description="Cluster scope key (for Loki queries)"),
    ac:    ApiClient = Depends(_header_dep),
):
    try:
        plan = _parse_query(q)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    src = plan["from"]
    try:
        if src in _LOKI_SOURCES:
            rows = _fetch_loki(src, scope)
        else:
            rows = _fetch_rows(src, ac)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    if plan["where"] is not None:
        rows = [r for r in rows if _match(r, plan["where"])]

    if plan["group_by"]:
        groups: dict = {}
        for r in rows:
            key = r.get(plan["group_by"], "")
            groups[key] = groups.get(key, 0) + 1
        cols = [plan["group_by"], "count"]
        rows = [{plan["group_by"]: k, "count": v} for k, v in groups.items()]
    else:
        if any(c["agg"] == "count" for c in plan["cols"]) and not plan["group_by"]:
            rows = [{"count": len(rows)}]; cols = ["count"]
        else:
            requested = [c["col"] for c in plan["cols"]]
            cols = list(rows[0].keys()) if (requested == ["*"] and rows) else \
                   STAR_COLS.get(src, []) if requested == ["*"] else requested
            rows = [{c: r.get(c, "") for c in cols} for r in rows]

    if plan["order_by"]:
        rows.sort(key=lambda r: (r.get(plan["order_by"]) is None, r.get(plan["order_by"])),
                  reverse=plan["order_desc"])
    if plan["limit"]:
        rows = rows[:plan["limit"]]

    return {"cols": cols, "rows": rows, "total": len(rows)}
