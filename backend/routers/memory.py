"""三层记忆与记忆治理路由（课程1 F-36~F-38 展示 + N-11 治理）。"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import db
import memory as mem

router = APIRouter(prefix="/api/projects", tags=["memory"])


class MemoryCreate(BaseModel):
    key: str
    value: str
    category: str = ""
    note: str = ""


class MemoryUpdate(BaseModel):
    value: str
    key: str | None = None
    note: str = ""
    reason: str = ""


class ReasonBody(BaseModel):
    reason: str = ""


class CorrectBody(BaseModel):
    value: str
    reason: str = ""


def _project_or_404(pid: int) -> None:
    if not db.query("SELECT id FROM projects WHERE id=?", (pid,)):
        raise HTTPException(404, "项目不存在")


@router.get("/{pid}/memory/longterm")
def list_longterm(pid: int, include_inactive: bool = True):
    _project_or_404(pid)
    return mem.get_longterm(pid, include_inactive=include_inactive)


@router.post("/{pid}/memory/longterm")
def create_longterm(pid: int, body: MemoryCreate):
    _project_or_404(pid)
    if not body.key.strip():
        raise HTTPException(400, "key 不能为空")
    mid = mem.save_longterm(pid, body.key.strip(), body.value, body.category, body.note)
    mem._audit(pid, mid, "create", "", f"{body.key}={body.value}", "手动新增")
    return {"id": mid}


@router.put("/{pid}/memory/longterm/{mid}")
def update_longterm(pid: int, mid: int, body: MemoryUpdate):
    _project_or_404(pid)
    try:
        return mem.update_longterm(mid, body.value, body.key, body.note, body.reason)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/{pid}/memory/longterm/{mid}/correct")
def correct_longterm(pid: int, mid: int, body: CorrectBody):
    _project_or_404(pid)
    try:
        return mem.correct_longterm(mid, body.value, body.reason)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/{pid}/memory/longterm/{mid}/invalidate")
def invalidate_longterm(pid: int, mid: int, body: ReasonBody):
    _project_or_404(pid)
    try:
        return mem.invalidate_longterm(mid, body.reason)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/{pid}/memory/audit")
def audit(pid: int):
    _project_or_404(pid)
    return mem.list_audit(pid)


@router.get("/{pid}/memory/task")
def task_memory(pid: int):
    _project_or_404(pid)
    data = mem.get_task_memory(pid)
    return data or {}
