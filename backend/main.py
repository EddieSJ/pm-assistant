"""FastAPI 主入口。"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import config
from routers import analysis, chat, docs, projects

app = FastAPI(title="项目管理智能助手", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router)
app.include_router(analysis.router)
app.include_router(chat.router)
app.include_router(docs.router)


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "model": config.Config.model,
        "has_api_key": config.has_api_key(),
        "require_human_approval": config.Config.require_human_approval,
        "source_trace": config.Config.enable_source_trace,
    }


# 若前端已构建，则托管静态产物
_dist = config.PROJECT_DIR / "frontend" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=str(_dist), html=True), name="frontend")
