"""文件识别（分析）与看板数据路由。"""
from fastapi import APIRouter, HTTPException

import agent
import db

router = APIRouter(prefix="/api/projects", tags=["analysis"])


@router.post("/{pid}/analyze")
def analyze_project(pid: int):
    rows = db.query("SELECT * FROM projects WHERE id=?", (pid,))
    if not rows:
        raise HTTPException(404, "项目不存在")
    job_id = agent.start_analyze(pid)
    return {"job_id": job_id, "folder": rows[0]["folder_path"]}


@router.get("/analyze/status/{job_id}")
def analyze_status(job_id: str):
    job = agent.get_job(job_id)
    if not job:
        raise HTTPException(404, "任务不存在")
    return job


@router.get("/{pid}/board")
def board(pid: int):
    rows = db.query("SELECT * FROM projects WHERE id=?", (pid,))
    if not rows:
        raise HTTPException(404, "项目不存在")
    return {
        "project": rows[0],
        "facts": db.query("SELECT * FROM facts WHERE project_id=? ORDER BY id", (pid,)),
        "stakeholders": db.query("SELECT * FROM stakeholders WHERE project_id=? ORDER BY id", (pid,)),
        "finance": db.query("SELECT * FROM finance WHERE project_id=? ORDER BY id", (pid,)),
        "actions": db.query("SELECT * FROM actions WHERE project_id=? ORDER BY id", (pid,)),
        "conflicts": db.query("SELECT * FROM conflicts WHERE project_id=? ORDER BY id", (pid,)),
        "sources": db.query("SELECT * FROM sources WHERE project_id=? ORDER BY id", (pid,)),
        "documents": db.query("SELECT * FROM documents WHERE project_id=? ORDER BY id DESC", (pid,)),
    }
