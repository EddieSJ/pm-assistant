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


# ---------- 长期记忆 ----------
def save_longterm(project_id: int, key: str, value: str, category: str = "") -> int:
    return db.execute(
        "INSERT INTO memories_longterm (project_id, key, value, category, created_at) VALUES (?,?,?,?,?)",
        (project_id, key, value, category, db.now()),
    )


def get_longterm(project_id: int, category: str | None = None) -> list[dict]:
    if category:
        return db.query(
            "SELECT * FROM memories_longterm WHERE project_id=? AND category=? ORDER BY id DESC",
            (project_id, category),
        )
    return db.query("SELECT * FROM memories_longterm WHERE project_id=? ORDER BY id DESC", (project_id,))


def get_longterm_text(project_id: int) -> str:
    rows = get_longterm(project_id)
    return "\n".join(f"- [{r['category']}] {r['key']}: {r['value']}" for r in rows)
