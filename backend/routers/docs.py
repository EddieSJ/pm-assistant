"""文档生成、下载与删除路由。"""
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

import db
import doc_gen
from config import Config

router = APIRouter(prefix="/api/projects", tags=["docs"])


class DocRequest(BaseModel):
    title: str
    content: str
    filename: str | None = None


def _next_version(project_id: int, title: str) -> str:
    """同一标题文档的版本递增：v1.0 -> v1.1 -> v1.2 ..."""
    rows = db.query(
        "SELECT version FROM documents WHERE project_id=? AND title=? ORDER BY id DESC LIMIT 1",
        (project_id, title),
    )
    latest = rows[0].get("version") if rows else ""
    m = re.match(r"v(\d+)\.(\d+)", latest or "")
    if m:
        return f"v{int(m.group(1))}.{int(m.group(2)) + 1}"
    return "v1.0"


@router.post("/{pid}/documents/generate")
def generate_doc(pid: int, body: DocRequest):
    rows = db.query("SELECT * FROM projects WHERE id=?", (pid,))
    if not rows:
        raise HTTPException(404, "项目不存在")
    version = _next_version(pid, body.title)
    path = doc_gen.markdown_to_word(body.title, body.content, body.filename, version=version)
    doc_id = db.execute(
        "INSERT INTO documents (project_id, title, version, file_path, created_at) VALUES (?,?,?,?,?)",
        (pid, body.title, version, str(path), db.now()),
    )
    return {"id": doc_id, "filename": path.name, "title": body.title, "version": version}


@router.post("/{pid}/documents/summary")
def generate_summary(pid: int):
    """基于看板数据生成项目综合整理报告 Word。"""
    rows = db.query("SELECT * FROM projects WHERE id=?", (pid,))
    if not rows:
        raise HTTPException(404, "项目不存在")
    proj = rows[0]
    facts = db.query("SELECT * FROM facts WHERE project_id=?", (pid,))
    stakeholders = db.query("SELECT * FROM stakeholders WHERE project_id=?", (pid,))
    finance = db.query("SELECT * FROM finance WHERE project_id=?", (pid,))
    actions = db.query("SELECT * FROM actions WHERE project_id=?", (pid,))
    conflicts = db.query("SELECT * FROM conflicts WHERE project_id=?", (pid,))

    title = f"{proj['name']} 综合整理报告"
    md = doc_gen.build_summary_markdown(proj, facts, stakeholders, finance, actions, conflicts)
    version = _next_version(pid, title)
    path = doc_gen.markdown_to_word(title, md, version=version)
    doc_id = db.execute(
        "INSERT INTO documents (project_id, title, version, file_path, created_at) VALUES (?,?,?,?,?)",
        (pid, title, version, str(path), db.now()),
    )
    return {"id": doc_id, "filename": path.name, "title": title, "version": version}


@router.get("/documents/download/{filename}")
def download(filename: str):
    path = Config.output_dir / "documents" / filename
    if not path.exists():
        raise HTTPException(404, "文件不存在")
    return FileResponse(str(path), filename=filename)


@router.delete("/documents/{doc_id}")
def delete_doc(doc_id: int):
    rows = db.query("SELECT * FROM documents WHERE id=?", (doc_id,))
    if not rows:
        raise HTTPException(404, "文档不存在")
    doc = rows[0]
    path = Path(doc["file_path"])
    if path.exists():
        try:
            path.unlink()
        except OSError:
            pass
    db.execute("DELETE FROM documents WHERE id=?", (doc_id,))
    return {"deleted": True, "id": doc_id, "title": doc["title"]}
