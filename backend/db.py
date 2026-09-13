"""数据库层：SQLite 建表与连接管理。

贴合 05_当前任务记忆体/memory_schema.json 的结构，
并承载 项目/来源/事实/冲突/行动/干系人/财务/三层记忆/文档/聊天 数据。
"""
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from config import Config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL,
    folder_path  TEXT NOT NULL,
    project_type TEXT DEFAULT '',
    project_code TEXT DEFAULT '',
    description  TEXT DEFAULT '',
    created_at   TEXT DEFAULT '',
    updated_at   TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS sources (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      INTEGER NOT NULL,
    file            TEXT NOT NULL,
    file_type       TEXT DEFAULT '',
    version_or_date TEXT DEFAULT '',
    loaded_at       TEXT DEFAULT '',
    content         TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS facts (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id       INTEGER NOT NULL,
    category         TEXT DEFAULT '',
    field            TEXT NOT NULL,
    value            TEXT DEFAULT '',
    source           TEXT DEFAULT '',
    status           TEXT DEFAULT 'provisional',
    original_excerpt TEXT DEFAULT '',
    created_at       TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS conflicts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER NOT NULL,
    category    TEXT DEFAULT '',
    description TEXT DEFAULT '',
    source_a    TEXT DEFAULT '',
    source_b    TEXT DEFAULT '',
    status      TEXT DEFAULT 'open',
    created_at  TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS actions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    action     TEXT DEFAULT '',
    owner      TEXT DEFAULT '',
    due_date   TEXT DEFAULT '',
    status     TEXT DEFAULT 'open',
    source     TEXT DEFAULT '',
    created_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS stakeholders (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id   INTEGER NOT NULL,
    name         TEXT DEFAULT '',
    organization TEXT DEFAULT '',
    role         TEXT DEFAULT '',
    influence    TEXT DEFAULT '',
    concern      TEXT DEFAULT '',
    channel      TEXT DEFAULT '',
    frequency    TEXT DEFAULT '',
    owner        TEXT DEFAULT '',
    created_at   TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS finance (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id    INTEGER NOT NULL,
    category      TEXT DEFAULT '',
    item          TEXT DEFAULT '',
    amount        TEXT DEFAULT '',
    tax_inclusive TEXT DEFAULT '',
    period        TEXT DEFAULT '',
    source        TEXT DEFAULT '',
    note          TEXT DEFAULT '',
    created_at    TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS memories_working (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    session_id TEXT DEFAULT '',
    role       TEXT DEFAULT '',
    content    TEXT DEFAULT '',
    created_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS memories_task (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    task_id    TEXT DEFAULT '',
    objective  TEXT DEFAULT '',
    as_of_date TEXT DEFAULT '',
    json_data  TEXT DEFAULT '',
    updated_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS memories_longterm (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    key        TEXT DEFAULT '',
    value      TEXT DEFAULT '',
    category   TEXT DEFAULT '',
    created_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS documents (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    title      TEXT DEFAULT '',
    version    TEXT DEFAULT 'v1.0',
    file_path  TEXT DEFAULT '',
    created_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    role       TEXT DEFAULT '',
    content    TEXT DEFAULT '',
    sources    TEXT DEFAULT '',
    created_at TEXT DEFAULT ''
);
"""

_lock = threading.Lock()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(Config.db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with _lock:
        conn = _connect()
        try:
            conn.executescript(_SCHEMA)
            _migrate(conn)
            conn.commit()
        finally:
            conn.close()


def _migrate(conn) -> None:
    """向后兼容的轻量迁移：为已存在的表补充新字段。"""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(documents)").fetchall()]
    if "version" not in cols:
        conn.execute("ALTER TABLE documents ADD COLUMN version TEXT DEFAULT 'v1.0'")


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def query(sql: str, params: tuple = ()) -> list[dict]:
    """读查询，返回 dict 列表。"""
    conn = _connect()
    try:
        cur = conn.execute(sql, params)
        rows = cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def execute(sql: str, params: tuple = ()) -> int:
    """写操作，返回 lastrowid。"""
    with _lock:
        conn = _connect()
        try:
            cur = conn.execute(sql, params)
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()


init_db()
