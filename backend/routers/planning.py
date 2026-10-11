"""计划与资源智能调度 REST 路由（课程3，F-63 ~ F-90）。"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import db
import planning

router = APIRouter(prefix="/api/projects", tags=["planning"])

# 预警状态流转允许的目标状态（F-84）
CONFLICT_STATUSES = {"未确认", "处理中", "已接受", "已关闭"}


def _project_or_404(pid: int) -> dict:
    rows = db.query("SELECT * FROM projects WHERE id=?", (pid,))
    if not rows:
        raise HTTPException(404, "项目不存在")
    return rows[0]


def _guard(pid: int) -> dict:
    """读接口统一前置：校验项目存在 + 等待在途重算结束。

    重算过程是「先 DELETE 再逐条 INSERT」，中途读取会拿到残缺数据集
    （例如材料只写了几条、容量表只写了一半）。这里等待重算结束（通常 1~2 秒，
    超时 30 秒后放弃等待、绝不挂住请求），使所有读接口看到的都是一次完整运行的结果。
    """
    proj = _project_or_404(pid)
    planning.wait_until_idle(pid)
    return proj


def _empty(pid: int) -> bool:
    return not db.query("SELECT id FROM plan_activities WHERE project_id=? LIMIT 1", (pid,))


# ---------------- 运行全流程 ----------------
@router.post("/{pid}/planning/run")
def run(pid: int):
    _guard(pid)
    return {"job_id": planning.start_run(pid)}


@router.get("/{pid}/planning/run/status/{job_id}")
def run_status(pid: int, job_id: str):
    job = planning.get_job(job_id)
    if not job:
        raise HTTPException(404, "任务不存在")
    return job


@router.get("/{pid}/planning/overview")
def overview(pid: int):
    _guard(pid)
    ov = planning.overview(pid)
    ov["empty"] = _empty(pid)
    return ov


# ---------------- F-63 ~ F-66 材料与效力 ----------------
@router.get("/{pid}/planning/materials")
def materials(pid: int):
    _guard(pid)
    return {
        "materials": db.query("SELECT * FROM plan_materials WHERE project_id=? ORDER BY group_code, material_code",
                              (pid,)),
        "empty": _empty(pid),
    }


@router.get("/{pid}/planning/checks")
def checks(pid: int):
    _guard(pid)
    return {"issues": planning.input_check_seven(pid)}


@router.get("/{pid}/planning/effectiveness")
def effectiveness(pid: int):
    _guard(pid)
    return {
        "levels": [{"strength": s, "date_type": t, "meaning": m, "enter_v1": v}
                   for s, t, m, v in planning.EFFECTIVENESS_LEVELS],
        "four_questions": planning.four_questions(pid),
    }


# ---------------- F-67 ~ F-72 WBS / 依赖 / 约束 ----------------
@router.get("/{pid}/planning/wbs")
def wbs(pid: int):
    _guard(pid)
    acts = db.query("SELECT * FROM plan_activities WHERE project_id=? AND version='V1' ORDER BY activity_id",
                    (pid,))
    deps = db.query("SELECT * FROM plan_dependencies WHERE project_id=? AND version='V1'", (pid,))
    # 按父任务聚合 WBS 树
    tree: dict[str, list] = {}
    for a in acts:
        tree.setdefault(a["task_id"], []).append(a)
    return {
        "activities": acts,
        "dependencies": deps,
        "tree": [{"task_id": k, "activities": v} for k, v in sorted(tree.items())],
        "empty": _empty(pid),
    }


@router.get("/{pid}/planning/constraints")
def constraints(pid: int):
    _guard(pid)
    return {"constraints": planning.collect_constraints(pid),
            "confirm_status": planning.confirm_status(pid),
            "quality_gates": [{"item": i, "rule": r, "scope": s}
                              for i, r, s in planning.QUALITY_GATES],
            "empty": _empty(pid)}


# ---------------- F-73 ~ F-75 日历与排程 ----------------
@router.get("/{pid}/planning/calendar")
def calendar(pid: int):
    _guard(pid)
    return {
        "workdays": "周一至周五",
        "holidays": sorted(planning.fs(h) for h in planning.HOLIDAYS),
        "plan_start": "2027-04-01",
        "plan_end": "2027-05-14",
    }


@router.get("/{pid}/planning/schedule")
def schedule(pid: int, version: str = "V1"):
    _guard(pid)
    if _empty(pid):
        return {"empty": True, "message": "尚未运行计划流程，请先点击「运行计划流程」"}
    acts = db.query("SELECT * FROM plan_activities WHERE project_id=? AND version=? ORDER BY activity_id",
                    (pid, version))
    snaps = db.query("SELECT id, version, checksum, label, created_at FROM plan_snapshots"
                     " WHERE project_id=? AND version=? ORDER BY id DESC LIMIT 1", (pid, version))
    recheck = [{"activity_id": a["activity_id"], "activity_name": a["activity_name"], "kind": "依赖复核",
                "detail": f"计划输入开始 {a['forecast_start']}，排程开始 {a['scheduled_start']}"
                          f"（{'一致' if a['forecast_start'] == a['scheduled_start'] else '不一致'}）"}
               for a in acts if a["forecast_start"] != a["scheduled_start"]]
    beyond = [{"activity_id": a["activity_id"], "activity_name": a["activity_name"],
               "scheduled_finish": a["scheduled_finish"], "float_days": a["float_days"],
               "note": "完成日晚于交付边界（最终验收），该链依赖待确认，暂不纳入 V1 关键路径"}
              for a in acts if _num(a["float_days"]) < 0]
    dev = [{"activity_id": a["activity_id"], "activity_name": a["activity_name"],
            "baseline_finish": a["baseline_finish"], "scheduled_finish": a["scheduled_finish"],
            "deviation_days": planning.workdays_between(planning.parse_date(a["baseline_finish"]),
                                                        planning.parse_date(a["scheduled_finish"]))
            if planning.parse_date(a["baseline_finish"]) and planning.parse_date(a["scheduled_finish"]) else 0}
           for a in acts if a["is_milestone"] == "是"]
    return {"version": version, "activities": acts, "snapshot": snaps[0] if snaps else None,
            "recheck": recheck, "beyond_boundary": beyond, "milestone_deviation": dev,
            "boundary": next((a["scheduled_finish"] for a in acts if a["activity_id"] == "A427"), ""),
            "empty": False}


def _num(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


@router.get("/{pid}/planning/critical-path")
def critical_path(pid: int, version: str = "V1"):
    _guard(pid)
    if _empty(pid):
        return {"empty": True, "message": "尚未运行计划流程"}
    data = planning.critical_path(pid, version)
    data["empty"] = False
    return data


# ---------------- F-79 ~ F-81 资源 ----------------
@router.get("/{pid}/planning/resource-load")
def resource_load(pid: int, version: str = "V1"):
    _guard(pid)
    if _empty(pid):
        return {"empty": True, "message": "尚未运行计划流程"}
    loads = planning.resource_load(pid, version)
    resources = db.query("SELECT * FROM plan_resources WHERE project_id=? ORDER BY resource_id", (pid,))
    demands = db.query("SELECT * FROM plan_activity_demand WHERE project_id=? AND version=?"
                       " ORDER BY activity_id, resource_id", (pid, version))
    return {"resources": resources, "demands": demands, "loads": loads, "empty": False}


@router.get("/{pid}/planning/allocation")
def allocation(pid: int):
    _guard(pid)
    return {"options": planning.allocation_options(pid)}


# ---------------- F-83 ~ F-84 冲突预警 ----------------
@router.get("/{pid}/planning/conflicts")
def conflicts(pid: int):
    _guard(pid)
    return {"conflicts": planning.conflict_flow(pid), "empty": _empty(pid)}


class ConflictUpdate(BaseModel):
    status: str


@router.post("/{pid}/planning/conflicts/{cid}/status")
def conflict_status(pid: int, cid: str, body: ConflictUpdate):
    _guard(pid)
    if body.status not in CONFLICT_STATUSES:
        raise HTTPException(400, f"不支持的状态: {body.status}")
    rows = db.query("SELECT * FROM plan_conflicts WHERE project_id=? AND conflict_id=?", (pid, cid))
    if not rows:
        raise HTTPException(404, "预警不存在")
    db.execute("UPDATE plan_conflicts SET status=?, updated_at=? WHERE id=?",
               (body.status, db.now(), rows[0]["id"]))
    return {"ok": True, "conflict_id": cid, "status": body.status}


# ---------------- F-85 ~ F-88 版本 / 事件 / 方案 / 建议 ----------------
@router.get("/{pid}/planning/versions")
def versions(pid: int):
    _guard(pid)
    vs = db.query("SELECT * FROM plan_versions WHERE project_id=? ORDER BY id", (pid,))
    return {"versions": vs, "snapshots": db.query(
        "SELECT id, version, checksum, label, created_at FROM plan_snapshots WHERE project_id=? ORDER BY id",
        (pid,))}


@router.get("/{pid}/planning/events")
def events(pid: int):
    _guard(pid)
    return {"events": db.query("SELECT * FROM plan_events WHERE project_id=? ORDER BY event_id", (pid,))}


@router.post("/{pid}/planning/events/{event_id}/apply")
def apply_event(pid: int, event_id: str):
    _guard(pid)
    res = planning.apply_event(pid, event_id)
    if not res.get("ok", True):
        raise HTTPException(404, res.get("error", "事件不存在"))
    return res


@router.get("/{pid}/planning/scenarios")
def scenarios(pid: int):
    _guard(pid)
    return planning.compare_scenarios(pid)


@router.get("/{pid}/planning/advices")
def advices(pid: int):
    _guard(pid)
    return {"advices": db.query("SELECT * FROM plan_advices WHERE project_id=? ORDER BY id", (pid,))}


@router.get("/{pid}/planning/confirmations")
def confirmations(pid: int):
    _guard(pid)
    return {"confirmations": db.query("SELECT * FROM plan_confirmations WHERE project_id=? ORDER BY id", (pid,)),
            "human_actions": planning.HUMAN_ACTIONS}


# ---------------- F-89 ~ F-90 证据与停止 ----------------
@router.get("/{pid}/planning/evidence")
def evidence(pid: int):
    _guard(pid)
    return {"evidence": db.query("SELECT * FROM plan_evidence WHERE project_id=? ORDER BY id DESC LIMIT 500",
                                 (pid,))}


@router.get("/{pid}/planning/stops")
def stops(pid: int):
    _guard(pid)
    return {"stops": db.query("SELECT * FROM plan_stops WHERE project_id=? ORDER BY id", (pid,))}


# ---------------- 汇总看板（前端一次拉取） ----------------
@router.get("/{pid}/planning/board")
def board(pid: int):
    # _guard 已等待在途重算结束，保证下面这一批读操作看到的是同一次运行的完整结果。
    _guard(pid)
    if _empty(pid):
        return {"empty": True, "message": "尚未运行计划流程，请先点击「运行计划流程」"}
    acts = db.query("SELECT * FROM plan_activities WHERE project_id=? AND version='V1'"
                    " ORDER BY activity_id", (pid,))
    tree: dict[str, list] = {}
    for a in acts:
        tree.setdefault(a["task_id"], []).append(a)
    return {
        "overview": planning.overview(pid),
        "materials": db.query("SELECT * FROM plan_materials WHERE project_id=? ORDER BY group_code, material_code",
                              (pid,)),
        "checks": planning.input_check_seven(pid),
        "effectiveness": {
            "levels": [{"strength": s, "date_type": t, "meaning": m, "enter_v1": v}
                       for s, t, m, v in planning.EFFECTIVENESS_LEVELS],
            "four_questions": planning.four_questions(pid),
        },
        "activities": acts,
        "wbs_tree": [{"task_id": k, "activities": v} for k, v in sorted(tree.items())],
        "dependencies": db.query("SELECT * FROM plan_dependencies WHERE project_id=? AND version='V1'", (pid,)),
        "constraints": planning.collect_constraints(pid),
        "confirm_status": planning.confirm_status(pid),
        "critical": planning.critical_path(pid, "V1"),
        "resources": db.query("SELECT * FROM plan_resources WHERE project_id=? ORDER BY resource_id", (pid,)),
        "loads": planning.resource_load(pid, "V1"),
        "demands": db.query("SELECT * FROM plan_activity_demand WHERE project_id=? AND version='V1'"
                            " ORDER BY activity_id, resource_id", (pid,)),
        "conflicts": planning.conflict_flow(pid),
        "allocation": planning.allocation_options(pid),
        "versions": db.query("SELECT * FROM plan_versions WHERE project_id=? ORDER BY id", (pid,)),
        "scenarios": planning.compare_scenarios(pid),
        "events": db.query("SELECT * FROM plan_events WHERE project_id=? ORDER BY event_id", (pid,)),
        "advices": db.query("SELECT * FROM plan_advices WHERE project_id=? ORDER BY id", (pid,)),
        "confirmations": db.query("SELECT * FROM plan_confirmations WHERE project_id=? ORDER BY id", (pid,)),
        "evidence": db.query("SELECT * FROM plan_evidence WHERE project_id=? ORDER BY id DESC LIMIT 200", (pid,)),
        "stops": db.query("SELECT * FROM plan_stops WHERE project_id=? ORDER BY id", (pid,)),
        "empty": False,
    }
