"""数据智能与决策 REST 路由。"""
from fastapi import APIRouter, HTTPException

import datasmart
import db

router = APIRouter(prefix="/api/projects", tags=["datasmart"])

BOARD_KINDS = {"progress", "cost", "staff", "risk", "quality", "procurement", "trend", "custom"}


def _project_or_404(pid: int) -> dict:
    rows = db.query("SELECT * FROM projects WHERE id=?", (pid,))
    if not rows:
        raise HTTPException(404, "项目不存在")
    return rows[0]


def _latest_snapshot(pid: int) -> dict | None:
    rows = db.query("SELECT * FROM snapshots WHERE project_id=? ORDER BY id DESC LIMIT 1", (pid,))
    return rows[0] if rows else None


@router.post("/{pid}/datasmart/run")
def run_datasmart(pid: int):
    _project_or_404(pid)
    job_id = datasmart.start_run(pid)
    return {"job_id": job_id}


@router.get("/{pid}/datasmart/run/status/{job_id}")
def run_status(pid: int, job_id: str):
    job = datasmart.get_job(job_id)
    if not job:
        raise HTTPException(404, "任务不存在")
    return job


@router.get("/{pid}/datasmart/overview")
def overview(pid: int):
    _project_or_404(pid)
    sources = db.query("SELECT * FROM data_sources WHERE project_id=?", (pid,))
    snap = _latest_snapshot(pid)
    metrics_count = 0
    clean_done = 0
    if snap:
        metrics_count = len(db.query(
            "SELECT id FROM metrics WHERE project_id=? AND snapshot_id=?", (pid, snap["id"])))
        clean_logs = db.query(
            "SELECT id, status FROM clean_logs WHERE project_id=? AND snapshot_id=?", (pid, snap["id"]))
        auto = sum(1 for c in clean_logs if c["status"] == "auto")
        clean_done = round(auto / len(clean_logs) * 100, 1) if clean_logs else 100.0
    return {
        "sources_count": len(sources),
        "sources": sources,
        "clean_done": clean_done,
        "metrics_count": metrics_count,
        "latest_snapshot": snap,
        "updated_at": snap["created_at"] if snap else "",
    }


@router.get("/{pid}/datasmart/board/{kind}")
def board(pid: int, kind: str):
    _project_or_404(pid)
    if kind not in BOARD_KINDS:
        raise HTTPException(400, f"看板类型不支持: {kind}")
    snap = _latest_snapshot(pid)
    if not snap:
        return {"kind": kind, "snapshot": None, "empty": True, "message": "暂无快照，请先运行数据管道"}
    sid = snap["id"]
    metrics = db.query("SELECT * FROM metrics WHERE project_id=? AND snapshot_id=?", (pid, sid))
    alerts = db.query(
        "SELECT * FROM alerts WHERE project_id=? AND snapshot_id=? AND status='open' ORDER BY id",
        (pid, sid))
    snaps = db.query("SELECT * FROM snapshots WHERE project_id=? ORDER BY id", (pid,))
    trend = []
    for s in snaps:
        m = {r["code"]: r["value"] for r in db.query(
            "SELECT code, value FROM metrics WHERE project_id=? AND snapshot_id=?", (pid, s["id"]))}
        trend.append({"node": s["node_label"], "date": s["data_date"], "revision": s["revision"],
                      "progress_plan": m.get("progress_plan"), "progress_actual": m.get("progress_actual"),
                      "progress_dev": m.get("progress_dev"), "spi": m.get("SPI"),
                      "cpi": m.get("CPI"), "eac": m.get("EAC")})
    return {"kind": kind, "snapshot": snap, "metrics": metrics, "alerts": alerts,
            "trend": trend, "empty": False}


@router.get("/{pid}/datasmart/snapshots")
def snapshots(pid: int):
    _project_or_404(pid)
    return db.query("SELECT * FROM snapshots WHERE project_id=? ORDER BY id", (pid,))


@router.post("/{pid}/datasmart/advise")
def advise(pid: int):
    _project_or_404(pid)
    snap = _latest_snapshot(pid)
    if not snap:
        raise HTTPException(400, "暂无快照，请先运行数据管道")
    datasmart.advise(pid, snap["id"])
    rows = db.query("SELECT * FROM advices WHERE project_id=? AND snapshot_id=? ORDER BY id DESC",
                    (pid, snap["id"]))
    return {"snapshot_id": snap["id"], "advices": rows}


@router.get("/{pid}/datasmart/alerts")
def alerts(pid: int):
    _project_or_404(pid)
    return db.query("SELECT * FROM alerts WHERE project_id=? ORDER BY id DESC", (pid,))


@router.get("/{pid}/datasmart/cleanlogs")
def cleanlogs(pid: int):
    _project_or_404(pid)
    return db.query("SELECT * FROM clean_logs WHERE project_id=? ORDER BY id DESC LIMIT 500", (pid,))


@router.get("/{pid}/datasmart/forecast")
def forecast(pid: int):
    _project_or_404(pid)
    return datasmart.forecast(pid)
