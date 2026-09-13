"""聊天路由（找核写追 + 四道门）。"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import agent
import db

router = APIRouter(prefix="/api/projects", tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"


@router.post("/{pid}/chat")
def chat(pid: int, body: ChatRequest):
    rows = db.query("SELECT * FROM projects WHERE id=?", (pid,))
    if not rows:
        raise HTTPException(404, "项目不存在")
    result = agent.answer(pid, body.message, body.session_id)
    return result


@router.get("/{pid}/chat/history")
def chat_history(pid: int, session_id: str = "default"):
    return db.query(
        "SELECT * FROM chat_messages WHERE project_id=? ORDER BY id DESC LIMIT 100",
        (pid,),
    )
