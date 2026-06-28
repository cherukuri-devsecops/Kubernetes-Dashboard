import codecs
import re
from datetime import datetime, timezone

_ANSI_RE = re.compile(r'\x1b\[[0-9;]*[mGKHF]|\x1b\[[\?]?[0-9;]*[hl]|\x1b[()][AB012]')
_K8S_TS_RE = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}')


def clean_logs(raw: str) -> str:
    """Decode bytes-repr strings, unescape, and strip ANSI codes."""
    if not raw:
        return ""
    # K8s client sometimes returns str(bytes) — strip the b'...' wrapper
    s = raw.strip()
    if s.startswith("b'") and s.endswith("'"):
        s = s[2:-1]
    elif s.startswith('b"') and s.endswith('"'):
        s = s[2:-1]
    # decode Python string escape sequences (\n, \t, \xe2…)
    try:
        s = codecs.decode(s, 'unicode_escape').encode('latin-1').decode('utf-8', errors='replace')
    except Exception:
        pass
    # strip ANSI escape codes
    s = _ANSI_RE.sub('', s)
    return s


def fmt_log_ts(ts: str) -> str:
    """Convert ISO-8601 K8s timestamp to compact human-readable form."""
    if not ts:
        return ""
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%m-%d %H:%M:%S")
    except ValueError:
        return ts[:19].replace("T", " ")


def parse_cpu(s):
    s = str(s or "0").strip()
    if s.endswith("n"): return float(s[:-1]) / 1_000_000
    if s.endswith("u"): return float(s[:-1]) / 1_000
    if s.endswith("m"): return float(s[:-1])
    try:   return float(s) * 1000
    except: return 0.0


def parse_memory(s):
    s = str(s or "0").strip()
    for sfx, mult in [("Ki", 1024), ("Mi", 1024**2), ("Gi", 1024**3), ("Ti", 1024**4),
                      ("K", 1000), ("M", 1000**2), ("G", 1000**3)]:
        if s.endswith(sfx):
            try: return int(float(s[:-len(sfx)]) * mult)
            except: return 0
    try: return int(s)
    except: return 0


def fmt_cpu(m):
    return f"{m/1000:.2f} cores" if m >= 1000 else f"{int(m)}m"


def fmt_mem(b):
    if b >= 1024**3: return f"{b/1024**3:.1f} GiB"
    if b >= 1024**2: return f"{b/1024**2:.0f} MiB"
    if b >= 1024:    return f"{b/1024:.0f} KiB"
    return f"{b} B"


def age(ts):
    if not ts: return "—"
    if isinstance(ts, str):
        ts = ts.strip()
        if not ts or ts in ("None", "null"): return "—"
        try:
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            return "—"
    if ts is None: return "—"
    now = datetime.now(timezone.utc)
    ts_aware = ts if getattr(ts, "tzinfo", None) else ts.replace(tzinfo=timezone.utc)
    delta = now - ts_aware
    d, s = delta.days, delta.seconds
    if d >= 365: return f"{d//365}y"
    if d > 0:    return f"{d}d"
    if s >= 3600: return f"{s//3600}h"
    if s >= 60:   return f"{s//60}m"
    return f"{s}s"


def phase_cls(ph):
    return {"Running": "ok", "Succeeded": "ok", "Pending": "warn",
            "Failed": "err", "Unknown": "err"}.get(ph or "", "gray")


def ready_count(pod):
    cs = pod.status.container_statuses or []
    return sum(1 for c in cs if c.ready), len(cs)


def restarts(pod):
    return sum(c.restart_count for c in (pod.status.container_statuses or []))


def node_ready(n):
    return any(c.type == "Ready" and c.status == "True"
               for c in (n.status.conditions or []))


def node_roles(n):
    labels = n.metadata.labels or {}
    roles = [k.split("/")[-1] for k in labels
             if k.startswith("node-role.kubernetes.io/")]
    return ",".join(roles) or "worker"


def log_cls(line):
    # check only the message portion (after optional K8s timestamp)
    msg = line.split(" ", 1)[1] if _K8S_TS_RE.match(line) and " " in line else line
    lo = msg.lower()
    if any(x in lo for x in ("error", "fatal", "critical", "exception", "severe")): return "log-err"
    if any(x in lo for x in ("warn", "warning")): return "log-warn"
    if " info " in lo or lo.startswith("info") or "[info]" in lo: return "log-info"
    if " debug " in lo or lo.startswith("debug") or "[debug]" in lo: return "log-debug"
    return ""


def log_level_badge(line):
    """Return the log level string extracted from a log line."""
    msg = line.split(" ", 1)[1] if _K8S_TS_RE.match(line) and " " in line else line
    lo = msg.lower()
    if any(x in lo for x in ("error", "fatal", "critical", "exception", "severe")): return "ERR"
    if any(x in lo for x in ("warn", "warning")): return "WRN"
    if " info " in lo or lo.startswith("info") or "[info]" in lo: return "INF"
    if " debug " in lo or lo.startswith("debug") or "[debug]" in lo: return "DBG"
    return ""
