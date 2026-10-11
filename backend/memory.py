"""三层记忆体：工作记忆 / 任务记忆 / 长期记忆。

- 工作记忆：当前会话上下文（memories_working 表）
- 任务记忆：对齐 05_当前任务记忆体/memory_schema.json（memories_task 表 + 同步回 JSON 文件）
- 长期记忆：沉淀的项目知识/结论/标准（memories_longterm 表）

安全：敏感信息不落库（见 07_任务记忆更新约束.md）。
"""
import json

import db
from config import Config


# ---------- 工作记忆 ----------
def save_working(project_id: int, session_id: str, role: str, content: str) -> int:
    return db.execute(
        "INSERT INTO memories_working (project_id, session_id, role, content, created_at) VALUES (?,?,?,?,?)",
        (project_id, session_id, role, content, db.now()),
    )


def get_working(project_id: int, session_id: str | None = None, limit: int = 40) -> list[dict]:
    if session_id:
        rows = db.query(
            "SELECT * FROM memories_working WHERE project_id=? AND session_id=? ORDER BY id DESC LIMIT ?",
            (project_id, session_id, limit),
        )
    else:
        rows = db.query(
            "SELECT * FROM memories_working WHERE project_id=? ORDER BY id DESC LIMIT ?",
            (project_id, limit),
        )
    return list(reversed(rows))


# ---------- 任务记忆 ----------
def save_task_memory(project_id: int, task_id: str, objective: str, as_of_date: str, data: dict) -> None:
    db.execute("DELETE FROM memories_task WHERE project_id=?", (project_id,))
    db.execute(
        "INSERT INTO memories_task (project_id, task_id, objective, as_of_date, json_data, updated_at) VALUES (?,?,?,?,?,?)",
        (project_id, task_id, objective, as_of_date, json.dumps(data, ensure_ascii=False), db.now()),
    )


def get_task_memory(project_id: int) -> dict | None:
    rows = db.query("SELECT * FROM memories_task WHERE project_id=? ORDER BY id DESC LIMIT 1", (project_id,))
    if not rows:
        return None
    try:
        return json.loads(rows[0]["json_data"])
    except Exception:
        return None


def sync_task_memory_to_file(data: dict) -> None:
    """把任务记忆同步回 05_当前任务记忆体/current_task_memory.json（对齐 schema）。"""
    data = dict(data)
    data["sensitive_data_stored"] = False
    try:
        Config.memory_file.parent.mkdir(parents=True, exist_ok=True)
        Config.memory_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[memory] 同步任务记忆文件失败: {e}")


# ---------- 长期记忆（含记忆治理：可更新 / 可纠错 / 可失效） ----------
def save_longterm(project_id: int, key: str, value: str, category: str = "",
                  note: str = "") -> int:
    return db.execute(
        "INSERT INTO memories_longterm (project_id, key, value, category, status, note,"
        " created_at, updated_at) VALUES (?,?,?,?,'active',?,?,?)",
        (project_id, key, value, category, note, db.now(), db.now()),
    )


def get_longterm(project_id: int, category: str | None = None,
                 include_inactive: bool = False) -> list[dict]:
    """长期记忆列表。默认只返回 active（失效记忆不参与召回）。"""
    sql = "SELECT * FROM memories_longterm WHERE project_id=?"
    params: list = [project_id]
    if not include_inactive:
        sql += " AND status='active'"
    if category:
        sql += " AND category=?"
        params.append(category)
    sql += " ORDER BY id DESC"
    return db.query(sql, tuple(params))


def _audit(project_id: int, memory_id: int, action: str, before: str, after: str, reason: str = "") -> int:
    return db.execute(
        "INSERT INTO memory_audit (project_id, memory_id, action, before, after, reason, created_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (project_id, memory_id, action, before, after, reason, db.now()),
    )


def _get_one(memory_id: int) -> dict | None:
    rows = db.query("SELECT * FROM memories_longterm WHERE id=?", (memory_id,))
    return rows[0] if rows else None


def update_longterm(memory_id: int, value: str, key: str | None = None,
                    note: str = "", reason: str = "") -> dict:
    """可更新：修正记忆内容。返回更新后的记录。"""
    old = _get_one(memory_id)
    if not old:
        raise ValueError("记忆不存在")
    new_key = key if key is not None else old["key"]
    db.execute(
        "UPDATE memories_longterm SET key=?, value=?, note=?, updated_at=? WHERE id=?",
        (new_key, value, note or old.get("note", ""), db.now(), memory_id),
    )
    _audit(old["project_id"], memory_id, "update",
           f"{old['key']}={old['value']}", f"{new_key}={value}", reason)
    return _get_one(memory_id)


def correct_longterm(memory_id: int, value: str, reason: str = "") -> dict:
    """可纠错：写入纠正后的新记忆，并把旧记忆置为 superseded（不继续引用）。"""
    old = _get_one(memory_id)
    if not old:
        raise ValueError("记忆不存在")
    new_id = db.execute(
        "INSERT INTO memories_longterm (project_id, key, value, category, status, note,"
        " supersedes, created_at, updated_at) VALUES (?,?,?,?,'active',?,?,?,?)",
        (old["project_id"], old["key"], value, old["category"],
         f"纠错自 #{memory_id}", memory_id, db.now(), db.now()),
    )
    db.execute("UPDATE memories_longterm SET status='superseded', updated_at=? WHERE id=?",
               (db.now(), memory_id))
    _audit(old["project_id"], memory_id, "correct",
           f"{old['key']}={old['value']}", f"{old['key']}={value}", reason or "纠错")
    return _get_one(new_id)


def invalidate_longterm(memory_id: int, reason: str = "") -> dict:
    """可失效：把过时 / 被推翻的记忆置为失效，不再参与后续召回。"""
    old = _get_one(memory_id)
    if not old:
        raise ValueError("记忆不存在")
    db.execute("UPDATE memories_longterm SET status='inactive', note=?, updated_at=? WHERE id=?",
               (reason or old.get("note", ""), db.now(), memory_id))
    _audit(old["project_id"], memory_id, "invalidate",
           f"{old['key']}={old['value']}", "inactive", reason)
    return _get_one(memory_id)


def list_audit(project_id: int) -> list[dict]:
    return db.query(
        "SELECT * FROM memory_audit WHERE project_id=? ORDER BY id DESC LIMIT 200", (project_id,))


def get_longterm_text(project_id: int) -> str:
    """注入用文本：仅 active 记忆参与召回（失效 / 被取代的记忆不再出现）。"""
    rows = get_longterm(project_id)
    return "\n".join(f"- [{r['category']}] {r['key']}: {r['value']}" for r in rows)
