"""沟通与成果输出（课程1 F-39 / F-40）。

- F-39 干系人分层简报：基于同一事实底稿，按 6 类干系人切换信息切面。
- F-40 多成果模板输出：周报 / 风险清单 / 成本说明 / RACI 职责表 / 会议纪要 / 干系人简报。

约定（对齐《项目需求说明书-课程1》）：
- 统一事实底稿为唯一来源，各切面不各说各话；
- 关键结论标注 [来源: 文件名]；
- Agent 只起草，正式外发须经人工确认（文末附确认清单）。
"""
import db

# 模板注册表：(code, 名称)
TEMPLATES: list[tuple[str, str]] = [
    ("weekly", "周报"),
    ("risk", "风险清单"),
    ("cost", "成本说明"),
    ("raci", "RACI 职责表"),
    ("minutes", "会议纪要"),
    ("stakeholder", "干系人简报"),
]

# 6 类干系人切面：(code, 名称, 关注切面)
AUDIENCES: list[tuple[str, str, tuple[str, ...]]] = [
    ("owner", "项目负责人", ("总体进展", "风险", "决策点")),
    ("team", "执行团队", ("任务分工", "时间节点", "协同事项")),
    ("finance", "财务", ("金额", "台账", "付款状态")),
    ("client", "客户/甲方", ("里程碑", "交付状态", "待确认事项")),
    ("exec", "管理层", ("关键问题", "资源需求", "下一步")),
    ("partner", "合作方", ("接口事项", "依赖关系", "截止时间")),
]

_AUDIENCE_INDEX = {c: (n, sec) for c, n, sec in AUDIENCES}
_CONFIRM_NOTE = (
    "\n---\n"
    "> 人工确认关卡：本文档由 Agent 起草，仅作内部准备，不自动外发。"
    "正式外发前须人工确认：① 检查事实 ② 修改措辞 ③ 确认附件与对象 ④ 批准发送。\n"
    "> 财务 / 合同 / 人事相关结论一律标记「需人工复核」。\n"
)


# ------------------------------------------------------------------
# 事实底稿（唯一来源）
# ------------------------------------------------------------------
def load_board(project_id: int) -> dict:
    """加载项目事实底稿：项目 + 七类台账 + 最新数据智能快照。"""
    proj = db.query("SELECT * FROM projects WHERE id=?", (project_id,))
    if not proj:
        return {}
    snap = db.query("SELECT * FROM snapshots WHERE project_id=? ORDER BY id DESC LIMIT 1",
                    (project_id,))
    metrics, alerts = {}, []
    if snap:
        sid = snap[0]["id"]
        metrics = {m["code"]: m["value"] for m in db.query(
            "SELECT * FROM metrics WHERE project_id=? AND snapshot_id=?", (project_id, sid))}
        alerts = db.query(
            "SELECT * FROM alerts WHERE project_id=? AND snapshot_id=? AND status='open' ORDER BY id",
            (project_id, sid))
    return {
        "project": proj[0],
        "facts": db.query("SELECT * FROM facts WHERE project_id=? ORDER BY id", (project_id,)),
        "stakeholders": db.query("SELECT * FROM stakeholders WHERE project_id=? ORDER BY id", (project_id,)),
        "finance": db.query("SELECT * FROM finance WHERE project_id=? ORDER BY id", (project_id,)),
        "actions": db.query("SELECT * FROM actions WHERE project_id=? ORDER BY id", (project_id,)),
        "conflicts": db.query("SELECT * FROM conflicts WHERE project_id=? ORDER BY id", (project_id,)),
        "sources": db.query("SELECT * FROM sources WHERE project_id=? ORDER BY id", (project_id,)),
        "snapshot": snap[0] if snap else None,
        "metrics": metrics,
        "alerts": alerts,
    }


def _fm(v, suffix="") -> str:
    """数值格式化为可读文本（None → '—'）。"""
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:,.2f}{suffix}"
    return f"{v}{suffix}"


def _head(project: dict, title: str, as_of: str) -> list[str]:
    return [
        f"# {project.get('name', '项目')} {title}",
        "",
        f"项目类型：{project.get('project_type') or '未识别'}　项目编码：{project.get('project_code') or '-'}",
        f"数据截止：{as_of or '-'}　生成时间：{db.now()}",
        "",
    ]


def _fact_lines(board: dict, limit: int = 40) -> list[str]:
    out = []
    for f in board["facts"][:limit]:
        out.append(f"- 【{f['category']}】{f['field']}：{f['value']}（{f['status']}）[来源: {f['source']}]")
    return out or ["- 暂无已提取事实"]


def _action_lines(board: dict) -> list[str]:
    out = []
    for a in board["actions"]:
        out.append(f"- {a['action']}（负责人：{a['owner'] or '待指派'}，期限：{a['due_date'] or '待定'}，"
                   f"状态：{a['status']}）[来源: {a['source']}]")
    return out or ["- 暂无行动项"]


def _conflict_lines(board: dict) -> list[str]:
    out = []
    for c in board["conflicts"]:
        out.append(f"- 【{c['category']}】{c['description']}（来源 A: {c['source_a'] or '-'}；"
                   f"来源 B: {c['source_b'] or '-'}）")
    return out or ["- 暂无冲突或待确认事项"]


def _alert_lines(board: dict) -> list[str]:
    out = []
    for a in board["alerts"]:
        out.append(f"- [{a['level']}] {a['alert_type']}：{a['object_name']}"
                   f"　责任人：{a['owner']}　期限：{a['due_date']}　[来源: {a['source_file']}]")
    return out


def _progress_lines(board: dict) -> list[str]:
    m = board["metrics"]
    if not m:
        return ["- 暂无指标快照，请先在「数据智能与决策」运行数据管道"]
    return [
        f"- 计划进度 {_fm(m.get('progress_plan'), '%')}　实际进度 {_fm(m.get('progress_actual'), '%')}"
        f"　进度偏差 {_fm(m.get('progress_dev'), ' 个百分点')}",
        f"- SPI（进度绩效）{_fm(m.get('SPI'))}　（EV/PV，<0.9 需关注）",
        f"- CPI（成本绩效）{_fm(m.get('CPI'))}　（EV/AC，<0.9 需关注）",
        f"- 预算 BAC {_fm(m.get('BAC'))}　实际成本 AC {_fm(m.get('AC'))}"
        f"　完工估算 EAC {_fm(m.get('EAC'))}　完工偏差 {_fm(m.get('completion_dev'))}",
    ]


def _finance_lines(board: dict) -> list[str]:
    out = []
    for f in board["finance"]:
        out.append(f"- 【{f['category']}】{f['item']}：{f['amount']}"
                   f"（{f['tax_inclusive']} / {f['period']}）[来源: {f['source']}]")
    return out or ["- 暂无财务信息"]


# ------------------------------------------------------------------
# F-40 模板构建
# ------------------------------------------------------------------
def build_weekly(board: dict) -> tuple[str, str]:
    p, as_of = board["project"], (board["snapshot"]["data_date"] if board["snapshot"] else "")
    lines = _head(p, "周报", as_of)
    lines += ["## 一、总体进展", *_progress_lines(board), ""]
    lines += ["## 二、关键事实", *_fact_lines(board, 20), ""]
    lines += ["## 三、行动计划与责任人", *_action_lines(board), ""]
    lines += ["## 四、风险与待确认", *_conflict_lines(board), ""]
    if board["alerts"]:
        lines += ["## 五、风险预警", *_alert_lines(board), ""]
    lines += ["## 六、下周计划建议",
              "- 围绕上述行动项与预警，由责任人制定纠偏措施并明确完成时间。",
              "- 跨表异常（进度/成本/风险叠加）须项目经理层面决策。", ""]
    return f"{p['name']} 周报", "\n".join(lines) + _CONFIRM_NOTE


def build_risk(board: dict) -> tuple[str, str]:
    p, as_of = board["project"], (board["snapshot"]["data_date"] if board["snapshot"] else "")
    lines = _head(p, "风险清单", as_of)
    lines += ["## 一、风险预警（数据智能）", *(_alert_lines(board) or ["- 暂无活跃预警"]), ""]
    lines += ["## 二、冲突与待确认事项", *_conflict_lines(board), ""]
    lines += ["## 三、风险相关事实", *_fact_lines(
        {"facts": [f for f in board["facts"] if "风险" in (f["category"] or "") or "问题" in (f["category"] or "")]}), ""]
    lines += ["## 四、应对建议",
              "- 高风险项由责任人限期制定应对方案并回填状态；",
              "- 跨表叠加风险（成本/进度/质量/采购同时恶化）须升级至项目负责人决策。", ""]
    return f"{p['name']} 风险清单", "\n".join(lines) + _CONFIRM_NOTE


def build_cost(board: dict) -> tuple[str, str]:
    p, as_of = board["project"], (board["snapshot"]["data_date"] if board["snapshot"] else "")
    lines = _head(p, "成本说明", as_of)
    lines += ["## 一、成本绩效（EVM）", *_progress_lines(board), ""]
    lines += ["## 二、财务台账", *_finance_lines(board), ""]
    lines += ["## 三、说明",
              "- 金额保留原始口径（含税 / 不含税、当期 / 累计）；",
              "- 上述成本结论为教学整理结果，**需财务复核**。", ""]
    return f"{p['name']} 成本说明", "\n".join(lines) + _CONFIRM_NOTE


def build_raci(board: dict) -> tuple[str, str]:
    p = board["project"]
    pm = _find_manager(board)
    lines = _head(p, "RACI 职责表", "")
    lines += ["## 一、职责矩阵（R 负责 / A 审批 / C 协作 / I 知会）", ""]
    if board["actions"]:
        for a in board["actions"]:
            owner = a["owner"] or "待指派"
            lines.append(f"- 事项：{a['action']}")
            lines.append(f"  - R（负责）：{owner}　A（审批）：{pm or '待确认'}"
                         f"　C（协作）：待确认　I（知会）：待确认")
            lines.append(f"  - 期限：{a['due_date'] or '待定'}　[来源: {a['source']}]")
    else:
        lines.append("- 暂无行动项，无法构建职责矩阵")
    lines += ["", "## 二、干系人一览", ""]
    for s in board["stakeholders"]:
        lines.append(f"- {s['name']}（{s['organization']} / {s['role']}，影响力：{s['influence'] or '-'}，"
                     f"关注点：{s['concern'] or '-'}）")
    lines += ["", "> 误判之门④（责任）：RACI 表已填写不代表责任清晰——错误对象或口径会导致行动落空，"
              "A/C/I 列须人工确认后生效。", ""]
    return f"{p['name']} RACI 职责表", "\n".join(lines) + _CONFIRM_NOTE


def _find_manager(board: dict) -> str:
    for s in board["stakeholders"]:
        role = (s["role"] or "") + (s["name"] or "")
        if any(k in role for k in ("项目经理", "项目负责人", "PM", "负责人", "经理")):
            return s["name"]
    return ""


def build_minutes(board: dict) -> tuple[str, str]:
    p, as_of = board["project"], (board["snapshot"]["data_date"] if board["snapshot"] else "")
    meeting_sources = [s["file"] for s in board["sources"]
                       if any(k in s["file"] for k in ("会议", "邮件", "纪要"))]
    lines = _head(p, "会议纪要（结构化转译）", as_of)
    lines += ["## 一、议题来源", *([f"- {f}" for f in meeting_sources] or ["- 未识别到会议 / 邮件类来源文件"]), ""]
    lines += ["## 二、行动项（行动 / 责任人 / 截止时间 / 状态）", *_action_lines(board), ""]
    lines += ["## 三、待确认事项", *_conflict_lines(board), ""]
    lines += ["## 四、说明",
              "- 会议纪要与往来邮件统一转译为「行动项 / 责任人 / 截止时间 / 状态」，"
              "并做归一化与去重；",
              "- 只有把信息转成行动、责任与期限，会议和邮件才会从「说过了」变成「做到了」。", ""]
    return f"{p['name']} 会议纪要", "\n".join(lines) + _CONFIRM_NOTE


def build_stakeholder(board: dict, audience: str) -> tuple[str, str]:
    """F-39 干系人分层简报：同一事实底稿，按对象切换信息切面。"""
    p = board["project"]
    name, sections = _AUDIENCE_INDEX.get(audience, _AUDIENCE_INDEX["owner"])
    as_of = board["snapshot"]["data_date"] if board["snapshot"] else ""
    lines = _head(p, f"{name}简报", as_of)
    lines += [f"> 本简报面向「{name}」，关注切面：{' / '.join(sections)}；"
              f"内容以统一事实底稿为唯一来源，不各说各话。", ""]

    if audience in ("owner", "exec"):
        lines += ["## 一、总体进展与关键指标", *_progress_lines(board), ""]
        lines += ["## 二、关键问题与风险预警", *(_alert_lines(board) or ["- 暂无活跃预警"]), ""]
        if audience == "owner":
            lines += ["## 三、决策点",
                      f"- 进度偏差 {_fm(board['metrics'].get('progress_dev'), ' 个百分点')}；"
                      f"EAC 与 BAC 差额 {_fm(board['metrics'].get('completion_dev'))}；",
                      "- 是否启动纠偏 / 追加资源 / 调整范围，须项目负责人决策。", ""]
        else:
            lines += ["## 三、资源需求与下一步",
                      "- 资源需求：见上述预警涉及的人员 / 采购事项；",
                      "- 下一步：由项目负责人牵头制定纠偏计划并定期回报。", ""]

    elif audience == "team":
        lines += ["## 一、任务分工与时间节点", *_action_lines(board), ""]
        lines += ["## 二、协同事项与依赖", *_conflict_lines(board), ""]
        lines += ["## 三、风险提示", *(_alert_lines(board)[:6] or ["- 暂无活跃预警"]), ""]

    elif audience == "finance":
        lines += ["## 一、金额与台账", *_finance_lines(board), ""]
        lines += ["## 二、成本绩效", *_progress_lines(board)[1:], ""]
        lines += ["## 三、付款状态与待确认",
                  "- 付款状态以财务台账口径为准，差异项标「待确认」；",
                  "- 上述结论**需财务复核**。", ""]

    elif audience == "client":
        lines += ["## 一、里程碑与交付状态", *_fact_lines(
            {"facts": [f for f in board["facts"]
                       if any(k in (f["field"] or "") + (f["category"] or "") for k in ("里程碑", "交付", "验收", "进度"))]}, 30), ""]
        lines += ["## 二、待确认事项", *_conflict_lines(board), ""]
        lines += ["## 三、需甲方配合事项", "- 详见上述待确认事项；接口与验收安排以双方确认结论为准。", ""]

    elif audience == "partner":
        lines += ["## 一、接口与依赖事项", *_fact_lines(
            {"facts": [f for f in board["facts"]
                       if any(k in (f["field"] or "") + (f["category"] or "") for k in ("接口", "依赖", "供应商", "采购", "合作"))]}, 30), ""]
        lines += ["## 二、截止时间与协同", *_action_lines(board), ""]
        lines += ["## 三、待确认事项", *_conflict_lines(board), ""]

    return f"{p['name']} {name}简报", "\n".join(lines) + _CONFIRM_NOTE


# ------------------------------------------------------------------
# 统一入口
# ------------------------------------------------------------------
def build(project_id: int, template: str, audience: str = "owner") -> tuple[str, str]:
    """返回 (title, markdown)。template ∈ TEMPLATES；audience 仅 stakeholder 使用。"""
    board = load_board(project_id)
    if not board:
        raise ValueError("项目不存在")
    if template == "stakeholder":
        return build_stakeholder(board, audience)
    builders = {
        "weekly": build_weekly,
        "risk": build_risk,
        "cost": build_cost,
        "raci": build_raci,
        "minutes": build_minutes,
    }
    if template not in builders:
        raise ValueError(f"未知模板: {template}")
    return builders[template](board)
