"""沟通与成果输出路由（课程1 F-39 / F-40）。"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import db
import deliverables
import doc_gen

router = APIRouter(prefix="/api/projects", tags=["deliverables"])

_VALID_TEMPLATES = {c for c, _ in deliverables.TEMPLATES}
_VALID_AUDIENCES = {c for c, _, _ in deliverables.AUDIENCES}


class DeliverableRequest(BaseModel):
    template: str
    audience: str = "owner"


def _next_version(project_id: int, title: str) -> str:
    """同一标题文档的版本递增：v1.0 -> v1.1 -> v1.2 ..."""
    import re
    rows = db.query(
        "SELECT version FROM documents WHERE project_id=? AND title=? ORDER BY id DESC LIMIT 1",
        (project_id, title),
    )
    latest = rows[0].get("version") if rows else ""
    m = re.match(r"v(\d+)\.(\d+)", latest or "")
    if m:
        return f"v{int(m.group(1))}.{int(m.group(2)) + 1}"
    return "v1.0"


@router.get("/{pid}/deliverables/templates")
def templates(pid: int):
    db_rows = db.query("SELECT id FROM projects WHERE id=?", (pid,))
    if not db_rows:
        raise HTTPException(404, "项目不存在")
    return {
        "templates": [{"code": c, "name": n} for c, n in deliverables.TEMPLATES],
        "audiences": [{"code": c, "name": n, "sections": list(s)}
                      for c, n, s in deliverables.AUDIENCES],
        "confirm_required": True,
    }


@router.post("/{pid}/deliverables/generate")
def generate(pid: int, body: DeliverableRequest):
    db_rows = db.query("SELECT id FROM projects WHERE id=?", (pid,))
    if not db_rows:
        raise HTTPException(404, "项目不存在")
    if body.template not in _VALID_TEMPLATES:
        raise HTTPException(400, f"不支持的模板: {body.template}")
    if body.template == "stakeholder" and body.audience not in _VALID_AUDIENCES:
        raise HTTPException(400, f"不支持的干系人对象: {body.audience}")
    try:
        title, md = deliverables.build(pid, body.template, body.audience)
    except ValueError as e:
        raise HTTPException(400, str(e))
    version = _next_version(pid, title)
    path = doc_gen.markdown_to_word(title, md, version=version)
    doc_id = db.execute(
        "INSERT INTO documents (project_id, title, version, file_path, created_at) VALUES (?,?,?,?,?)",
        (pid, title, version, str(path), db.now()),
    )
    return {"id": doc_id, "title": title, "version": version, "filename": path.name,
            "template": body.template, "confirm_required": True}
