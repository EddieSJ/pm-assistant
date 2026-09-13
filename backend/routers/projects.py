"""项目 CRUD 路由 + 本地目录浏览。"""
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import db
from config import BASE_DIR

router = APIRouter(prefix="/api/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    name: str
    folder_path: str
    description: str = ""


class ProjectUpdate(BaseModel):
    name: str | None = None
    folder_path: str | None = None
    description: str | None = None


def _with_counts(p: dict) -> dict:
    p["facts_count"] = db.query("SELECT COUNT(*) c FROM facts WHERE project_id=?", (p["id"],))[0]["c"]
    p["stakeholders_count"] = db.query("SELECT COUNT(*) c FROM stakeholders WHERE project_id=?", (p["id"],))[0]["c"]
    p["finance_count"] = db.query("SELECT COUNT(*) c FROM finance WHERE project_id=?", (p["id"],))[0]["c"]
    p["actions_count"] = db.query("SELECT COUNT(*) c FROM actions WHERE project_id=?", (p["id"],))[0]["c"]
    p["conflicts_count"] = db.query("SELECT COUNT(*) c FROM conflicts WHERE project_id=?", (p["id"],))[0]["c"]
    p["sources_count"] = db.query("SELECT COUNT(*) c FROM sources WHERE project_id=?", (p["id"],))[0]["c"]
    return p


@router.get("")
def list_projects():
    rows = db.query("SELECT * FROM projects ORDER BY id DESC")
    return [_with_counts(r) for r in rows]


@router.get("/{pid}")
def get_project(pid: int):
    rows = db.query("SELECT * FROM projects WHERE id=?", (pid,))
    if not rows:
        raise HTTPException(404, "项目不存在")
    return _with_counts(rows[0])


@router.post("")
def create_project(body: ProjectCreate):
    folder = Path(body.folder_path)
    if not folder.exists() or not folder.is_dir():
        raise HTTPException(400, "项目文件夹不存在或不是目录")
    pid = db.execute(
        "INSERT INTO projects (name, folder_path, description, created_at, updated_at) VALUES (?,?,?,?,?)",
        (body.name.strip(), str(folder.resolve()), body.description, db.now(), db.now()),
    )
    return {"id": pid, "name": body.name.strip(), "folder_path": str(folder.resolve())}


@router.put("/{pid}")
def update_project(pid: int, body: ProjectUpdate):
    rows = db.query("SELECT * FROM projects WHERE id=?", (pid,))
    if not rows:
        raise HTTPException(404, "项目不存在")
    name = body.name if body.name is not None else rows[0]["name"]
    folder = rows[0]["folder_path"]
    if body.folder_path is not None:
        p = Path(body.folder_path)
        if not p.exists() or not p.is_dir():
            raise HTTPException(400, "项目文件夹不存在或不是目录")
        folder = str(p.resolve())
    desc = body.description if body.description is not None else rows[0]["description"]
    db.execute(
        "UPDATE projects SET name=?, folder_path=?, description=?, updated_at=? WHERE id=?",
        (name, folder, desc, db.now(), pid),
    )
    return {"id": pid, "updated": True}


@router.delete("/{pid}")
def delete_project(pid: int):
    rows = db.query("SELECT * FROM projects WHERE id=?", (pid,))
    if not rows:
        raise HTTPException(404, "项目不存在")
    for table in ("sources", "facts", "conflicts", "actions", "stakeholders", "finance",
                  "memories_working", "memories_task", "memories_longterm", "documents", "chat_messages"):
        db.execute(f"DELETE FROM {table} WHERE project_id=?", (pid,))
    db.execute("DELETE FROM projects WHERE id=?", (pid,))
    return {"deleted": True, "name": rows[0]["name"]}


# ---------- 目录浏览 ----------
@router.get("/browse/dirs")
def browse_dir(path: str = ""):
    """浏览本地目录，返回子目录与受支持文件，供前端选择项目文件夹。"""
    if not path:
        path = str(BASE_DIR)
    base = Path(path).expanduser()
    if not base.exists():
        base = BASE_DIR
    if not base.is_dir():
        raise HTTPException(400, "不是有效目录")

    dirs, files = [], []
    try:
        for entry in sorted(base.iterdir(), key=lambda e: e.name.lower()):
            if entry.name.startswith("."):
                continue
            try:
                if entry.is_dir():
                    dirs.append({"name": entry.name, "path": str(entry)})
                elif entry.is_file():
                    ext = entry.suffix.lower()
                    files.append({"name": entry.name, "path": str(entry), "ext": ext.lstrip(".")})
            except (PermissionError, OSError):
                continue
    except (PermissionError, OSError) as e:
        raise HTTPException(400, f"无法访问目录: {e}")

    return {
        "path": str(base),
        "parent": str(base.parent) if base != base.parent else None,
        "dirs": dirs,
        "files": files,
    }
