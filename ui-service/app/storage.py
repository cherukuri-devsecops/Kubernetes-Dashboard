"""SQLite storage for user-owned config data: kubeconfigs, saved queries, annotations."""
import logging
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

from .config import SQLITE_PATH

logger = logging.getLogger(__name__)

_lock = threading.Lock()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS user_kubeconfig (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_email  TEXT NOT NULL,
    name        TEXT NOT NULL DEFAULT 'default',
    content     TEXT NOT NULL,
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now')),
    UNIQUE (user_email, name)
);

CREATE TABLE IF NOT EXISTS saved_query (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_email  TEXT NOT NULL,
    name        TEXT NOT NULL,
    q           TEXT NOT NULL,
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now')),
    UNIQUE (user_email, name)
);

CREATE TABLE IF NOT EXISTS annotation (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    cluster        TEXT NOT NULL,
    resource_kind  TEXT NOT NULL,
    resource_ns    TEXT NOT NULL DEFAULT '',
    resource_name  TEXT NOT NULL,
    body           TEXT NOT NULL,
    author_email   TEXT,
    pinned         INTEGER DEFAULT 0,
    created_at     TEXT DEFAULT (datetime('now')),
    updated_at     TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_ann_target
    ON annotation (cluster, resource_kind, resource_ns, resource_name);

CREATE TABLE IF NOT EXISTS user_pref (
    user_email  TEXT NOT NULL,
    k           TEXT NOT NULL,
    v           TEXT,
    updated_at  TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (user_email, k)
);
"""


@contextmanager
def _conn():
    Path(SQLITE_PATH).parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        conn = sqlite3.connect(SQLITE_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def storage_init():
    with _conn() as conn:
        conn.executescript(_SCHEMA)
    logger.info("SQLite storage ready: %s", SQLITE_PATH)


def _rows(sql, params=()):
    with _conn() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def _run(sql, params=()):
    with _conn() as conn:
        conn.execute(sql, params)


# ── Kubeconfigs ───────────────────────────────────────────────────────────────

def save_kubeconfig(user_email: str, content: str, name: str = "default"):
    with _conn() as conn:
        conn.execute("""
            INSERT INTO user_kubeconfig (user_email, name, content) VALUES (?,?,?)
            ON CONFLICT (user_email, name)
            DO UPDATE SET content = excluded.content, updated_at = datetime('now')
        """, (user_email, name, content))


def get_kubeconfig(user_email: str, name: str = "default"):
    rows = _rows(
        "SELECT content FROM user_kubeconfig WHERE user_email=? AND name=?",
        (user_email, name))
    return rows[0]["content"] if rows else None


def list_kubeconfigs(user_email: str):
    return _rows(
        "SELECT name, updated_at FROM user_kubeconfig WHERE user_email=? ORDER BY name",
        (user_email,))


def delete_kubeconfig(user_email: str, name: str):
    _run("DELETE FROM user_kubeconfig WHERE user_email=? AND name=?", (user_email, name))


# ── Saved queries ─────────────────────────────────────────────────────────────

def get_saved_queries(user_email: str):
    return _rows(
        "SELECT id, name, q, updated_at FROM saved_query"
        " WHERE user_email=? ORDER BY updated_at DESC",
        (user_email,))


def upsert_saved_query(user_email: str, name: str, q: str):
    with _conn() as conn:
        conn.execute("""
            INSERT INTO saved_query (user_email, name, q) VALUES (?,?,?)
            ON CONFLICT (user_email, name)
            DO UPDATE SET q = excluded.q, updated_at = datetime('now')
        """, (user_email, name, q))


def delete_saved_query(user_email: str, qid: int):
    _run("DELETE FROM saved_query WHERE id=? AND user_email=?", (qid, user_email))


# ── Annotations ───────────────────────────────────────────────────────────────

def add_annotation(cluster: str, kind: str, ns: str, name: str,
                   body: str, author: str, pinned: bool):
    with _conn() as conn:
        conn.execute("""
            INSERT INTO annotation
              (cluster, resource_kind, resource_ns, resource_name, body, author_email, pinned)
            VALUES (?,?,?,?,?,?,?)
        """, (cluster, kind, ns or "", name, body, author, int(pinned)))


def delete_annotation(cluster: str, ann_id: int):
    _run("DELETE FROM annotation WHERE id=? AND cluster=?", (ann_id, cluster))


def get_annotations(cluster: str, kind: str, ns: str, name: str):
    return _rows("""
        SELECT id, body, author_email, pinned, created_at, updated_at
        FROM annotation
        WHERE cluster=? AND resource_kind=? AND resource_ns=? AND resource_name=?
        ORDER BY pinned DESC, updated_at DESC
    """, (cluster, kind, ns or "", name))


def get_all_annotations(cluster: str):
    return _rows("""
        SELECT resource_kind AS kind, resource_ns AS ns, resource_name AS name,
               body, author_email AS author, pinned, updated_at AS ts
        FROM annotation WHERE cluster=? ORDER BY updated_at DESC
    """, (cluster,))
