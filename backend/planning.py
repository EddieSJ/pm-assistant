"""计划与资源智能调度引擎（课程3，F-63 ~ F-90）。

对齐《项目需求说明书-课程3》：
    F-63~F-66 计划材料接入 / 文件效力分级 / 效力判定四问 / 输入检查七问
    F-67~F-69 统一 WBS / 稳定 ID 联动 / 映射而非覆盖
    F-70~F-72 依赖关系 / 五类约束归集 / 确认状态标记
    F-73~F-75 工作日历 / 确定性排程引擎 / 排程可复核
    F-79~F-81 资源可用性 / 资源冲突识别 / 资源分配方案
    F-82      关键路径计算与可解释
    F-83~F-84 冲突预警六要素 / 预警状态流转
    F-85~F-88 版本冻结与恢复点 / 事件效力判定与追加式调整 / 方案比较 / 建议六要素与人工确认关卡
    F-89~F-90 证据与审计轨迹 / 自动停止

设计约束（对齐 PRD 第 7 节、N-16 ~ N-21）：
    * 规则算数字、Agent 做解释、人承担责任——本模块只做确定性计算与留痕，不做批准；
    * 原始材料只读；接入结果落库；追加读取不覆盖；
    * 版本派生而非覆盖：V1 冻结后由事件派生 V2 / S1 / S2 / S3，历史版本始终保留；
    * 五类约束（依赖 / 日历 / 资源容量 / 外部窗口 / 质量门）共同决定日期；
    * 质量门不可作为进度优化代价。
"""
import csv
import hashlib
import json
import re
import threading
import uuid
from datetime import date, timedelta
from pathlib import Path

import db
from config import Config

# ==================================================================
# 一、常量：材料分组、效力分级、工作日历、依赖解析规则
# ==================================================================

PROJECT_ID = "CY-DCM-2026-01"

# 材料分组目录 → 组代码
GROUP_DIRS = {
    "01_计划基线": "A",
    "02_资源与日历": "B",
    "03_外部条件与协同": "C",
    "04_动态事件（暂不授权）": "D",
}

# 材料效力定位（F-64）：基线 / 预测 / 专业估算 / 容量基线 / 申请 / 供应商承诺 / 窗口通知 / 会议讨论 / 事件
#   approved：是否已获正式批准（效力四问之三）  traceable：能否被历史记录追溯（效力四问之四）
MATERIAL_META = {
    "A01": ("基线/预测", "项目控制团队", 1, 1),
    "A02": ("专业估算", "各专业负责人", 0, 1),
    "B01a": ("容量基线", "资源经理", 1, 1),
    "B01b": ("容量基线", "资源经理", 1, 1),
    "B01c": ("专业估算", "各专业负责人", 0, 1),
    "B02": ("申请（未批准）", "测试与质量部", 0, 1),
    "C01": ("供应商承诺", "供应商", 0, 1),
    "C02": ("窗口通知", "运维管理部门", 1, 1),
    "C03": ("会议讨论", "项目经理", 0, 1),
    "D01": ("事件（条件生效）", "供应商项目经理", 0, 1),
    "D02": ("事件（立即生效）", "运维管理部门", 1, 1),
    "D03": ("事件（仅情景模拟）", "业务方", 0, 1),
    "D04": ("事件（仅形成比对任务）", "项目经理", 0, 1),
}

# 八类日期效力分级（F-64 / PRD 6.3）：效力强弱 → 能否进入 V1 正式排程
EFFECTIVENESS_LEVELS = [
    ("强", "基线日期", "已经批准的控制参照", "可以"),
    ("强", "实际日期", "已经发生的历史事实", "可以"),
    ("中", "当前预测", "按现状推算的可能结果", "可以（标注为预测）"),
    ("中", "专业估算", "团队提交的候选工期", "需人工确认后可以"),
    ("中", "供应商承诺", "附带前置条件的外部承诺", "需确认前置条件"),
    ("中", "窗口通知", "已经发布的可用时间边界", "作为边界约束"),
    ("弱", "申请日期", "待批准情景", "不可以（仅进入批准情景）"),
    ("弱", "会议讨论", "需逐条区分决定、行动与待决事项", "不可以（需先确认为决定）"),
]

# 五类约束（F-71 / PRD 6.4）
CONSTRAINT_KINDS = [
    ("依赖关系", "决定最早开始时间"),
    ("工作日历", "决定可用工作时间"),
    ("资源容量", "决定并行执行能力"),
    ("外部窗口", "决定可交付时机"),
    ("质量门", "确保质量合规通过"),
]

# 质量门（N-21 / 7.6）：不可作为进度优化代价
QUALITY_GATES = [
    ("P1/P2 缺陷", "= 0", "UAT 签署前置"),
    ("总体通过率", "≥ 95%", "验收测试"),
    ("数据准确率", "≥ 99.5%", "数据治理"),
    ("Go/No-Go", "责任人决定", "人工确认"),
    ("UAT 签署 / 最终验收", "人工完成", "人工确认"),
]

# 人工确认关卡（F-88 / N-19）五类责任动作
HUMAN_ACTIONS = ["资源批准", "正式变更", "生产切换", "UAT 签署", "最终验收"]

# 工作日历（教学设定，非真实放假安排）：周一至周五，扣除节假日
HOLIDAYS = {
    date(2027, 4, 5),   # 清明
    date(2027, 5, 1), date(2027, 5, 2), date(2027, 5, 3),   # 劳动节
    date(2027, 6, 9),   # 端午
}

# 条件型依赖的解析规则（F-70）：
#   A02 的 dependency_statement 里除显式 "Axxx 完成" 外的条件语句，按下列规则解析为具体前置活动；
#   未列入且无法解析的（自然语言候选）→ 不建边，标记待确认（正好演示「漏掉一条依赖」的危害）。
DEP_RESOLUTION = {
    "A415": ("A413", "“集成测试通过（M07）后开展” → 解析为上线验证链尾 A413", "里程碑/质量门"),
    "A417": ("A416", "“P1/P2 缺陷为 0 方可签署” → 解析为缺陷修复与复测 A416", "质量门"),
    "A422": ("A417", "“UAT 签署后可开始” → 解析为 UAT 签署 A417", "依赖关系"),
}
# 明确的确认关卡型依赖（不算前置活动，只记录约束）：方案须经技术与运维共同确认
CONFIRM_GATE_ONLY = {"A411": "方案须经技术与运维共同确认（确认关卡，非前置活动）"}
# 受外部窗口限制（记录为约束，不作为前置边）
WINDOW_CONSTRAINTS = {"A412": "受生产窗口限制", "A423": "须在批准窗口内执行（W-01）"}

TABLE_EXTS = {".csv"}

_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()
# 按项目的重算锁（N-18 全程留痕与可恢复）：禁止同一项目并发重算，
# 否则两轮 run_planning 的 DELETE/INSERT 会交错产生重复行。
_pipeline_locks: dict[int, threading.Lock] = {}
_pipeline_locks_guard = threading.Lock()


def _project_lock(project_id: int) -> threading.Lock:
    with _pipeline_locks_guard:
        return _pipeline_locks.setdefault(project_id, threading.Lock())


# ==================================================================
# 二、通用工具：工作日历与日期运算
# ==================================================================
def is_workday(d: date) -> bool:
    return d.weekday() < 5 and d not in HOLIDAYS


def next_workday(d: date) -> date:
    while not is_workday(d):
        d += timedelta(days=1)
    return d


def add_workdays(start: date, n: int) -> date:
    """从 start（需为工作日）往后推 n 个工作日；n=0 返回 start。"""
    d = next_workday(start)
    c = 0
    while c < n:
        d += timedelta(days=1)
        if is_workday(d):
            c += 1
    return d


def shift_back_workdays(start: date, n: int) -> date:
    """从 start 往前推 n 个工作日。"""
    d = start
    c = 0
    while c < n:
        d -= timedelta(days=1)
        if is_workday(d):
            c += 1
    return d


def workdays_between(a: date, b: date) -> int:
    """a（不含）到 b（含）之间的工作日数；b<=a 返回 0。"""
    if b <= a:
        return 0
    d, c = a, 0
    while d < b:
        d += timedelta(days=1)
        if is_workday(d):
            c += 1
    return c


def signed_float(es: date, ls: date) -> int:
    """带符号总时差：LS ≥ ES 为正（有余量），LS < ES 为负（超出交付边界）。"""
    if ls >= es:
        return workdays_between(es, ls)
    return -workdays_between(ls, es)


def parse_date(s) -> date | None:
    if not s:
        return None
    m = re.search(r"(\d{4})\s*[-/年.]\s*(\d{1,2})\s*[-/月.]\s*(\d{1,2})", str(s))
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def fs(d: date | None) -> str:
    return d.strftime("%Y-%m-%d") if d else ""


def _num(v, default=0.0) -> float:
    try:
        return float(str(v).strip().replace(",", "").replace("%", ""))
    except (ValueError, TypeError):
        return default


def _read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return [r for r in csv.DictReader(f)]


def _dataset_dir() -> Path:
    return Path(Config.plan_dataset_dir)


# ==================================================================
# 三、材料接入（F-63）与效力判定（F-64 / F-65）
# ==================================================================
def ingest_materials(project_id: int) -> list[dict]:
    """只读接入课程3 新增授权材料（A/B/C 三组）；D 组本期不授权，仅登记。"""
    db.execute("DELETE FROM plan_materials WHERE project_id=?", (project_id,))
    root = _dataset_dir()
    out: list[dict] = []
    if not root.exists():
        return out
    for sub in sorted(root.iterdir()):
        if not sub.is_dir():
            continue
        group = GROUP_DIRS.get(sub.name)
        if not group:
            continue
        for f in sorted(sub.iterdir()):
            if not f.is_file() or f.suffix.lower() not in TABLE_EXTS:
                continue
            code = f.name.split("_")[0]
            eff, issuer, approved, traceable = MATERIAL_META.get(
                code, ("未分类", "", 0, 0))
            access = "本期不授权" if group == "D" else "只读接入"
            rows = _read_csv(f)
            db.execute(
                "INSERT INTO plan_materials (project_id, group_code, material_code, material_name,"
                " file_path, effectiveness, access_mode, issuer, effective_at, approved, traceable,"
                " record_count, loaded_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (project_id, group, code, f.stem, str(f), eff, access, issuer,
                 "2027-03-31" if group != "D" else "V1 冻结后", approved, traceable,
                 len(rows), db.now()))
            out.append({"group_code": group, "material_code": code, "material_name": f.stem,
                        "effectiveness": eff, "access_mode": access, "record_count": len(rows)})
    return out


def four_questions(project_id: int) -> list[dict]:
    """效力判定四问（F-65）：谁发布 / 何时生效 / 是否已批准 / 能否追溯 → 能否进入 V1。"""
    rows = db.query("SELECT * FROM plan_materials WHERE project_id=? ORDER BY group_code, material_code",
                    (project_id,))
    out = []
    for r in rows:
        can_enter = "可以" if (r["approved"] and r["traceable"] and r["access_mode"] == "只读接入") else \
                    ("仅情景/待确认" if r["access_mode"] == "只读接入" else "不可（本期不授权）")
        out.append({
            "material_code": r["material_code"],
            "material_name": r["material_name"],
            "q1_issuer": r["issuer"] or "—（未标注发布主体）",
            "q2_effective": r["effective_at"] or "—",
            "q3_approved": "已批准" if r["approved"] else "未批准 / 待确认",
            "q4_traceable": "可追溯" if r["traceable"] else "不可追溯",
            "can_enter_v1": can_enter,
            "effectiveness": r["effectiveness"],
        })
    return out


def _parse_dep(succ: str, statement: str, dtype: str):
    """把依赖描述解析为前置活动编号（F-70）。

    返回 (predecessor|None, category, is_structured)
    """
    st = (statement or "").strip()
    if "可立即开始" in st or "无（" in st or st in ("", "无"):
        return None, "无前置", dtype == "已结构化"
    m = re.search(r"(A\d{3})", st)
    if m:
        return m.group(1), "依赖关系", dtype == "已结构化"
    if succ in DEP_RESOLUTION:
        pred, _rationale, cat = DEP_RESOLUTION[succ]
        return pred, cat, dtype == "已结构化"
    # 无法解析 → 自然语言候选，须人工确认
    return None, "自然语言候选", False


def input_check_seven(project_id: int) -> list[dict]:
    """输入检查七问（F-66）：输出问题清单、拟处理规则、影响范围与待确认事项。"""
    root = _dataset_dir()
    issues: list[dict] = []

    def add(no, name, obj, problem, rule, impact, pending, level="待确认"):
        issues.append({"no": no, "check": name, "object": obj, "problem": problem,
                       "rule": rule, "impact": impact, "pending": pending, "level": level})

    # ① project_id 一致性
    bad = set()
    for f in sorted(root.rglob("*.csv")):
        for r in _read_csv(f):
            pid = r.get("project_id", "")
            if pid and pid != PROJECT_ID:
                bad.add(f"{f.name}:{pid}")
    if bad:
        add(1, "project_id 一致性", "；".join(sorted(bad)), "存在与项目不一致的 project_id",
            "剔除或人工确认归属", "错误归属会污染排程输入", "确认材料归属", "阻塞")
    else:
        add(1, "project_id 一致性", "全部材料", f"全部为 {PROJECT_ID}", "无需处理", "无", "无", "通过")

    # ② 日期类别（基线/预测/估算/承诺）
    a01 = _read_csv(root / "01_计划基线/A01_项目总控进度计划.csv") if (
        root / "01_计划基线/A01_项目总控进度计划.csv").exists() else []
    mixed = [r["activity_id"] for r in a01 if r.get("baseline_start") and r.get("forecast_start")
             and r["baseline_start"] == r["forecast_start"]]
    add(2, "日期类别", f"A01 共 {len(a01)} 项活动",
        "基线、预测、估算分列存放（baseline_* / forecast_* / duration_estimate_days）",
        "按效力分别进入排程：基线为控制参照、预测为当前推算",
        f"其中 {len(mixed)} 项基线=预测（尚无偏差）", "无", "通过")

    # ③ 文件状态（批准 / 通知 / 申请 / 讨论）
    b02p = root / "02_资源与日历/B02_关键测试资源借调申请.csv"
    if b02p.exists():
        for r in _read_csv(b02p):
            if r.get("approval_status") == "审批中":
                add(3, "文件状态", f"{r['request_id']} / {r['resource_id']} {r['resource_name']}",
                    "借调申请处于「审批中」，申请不等于批准",
                    "正式容量按 0 计入 V1，仅进入「批准情景」",
                    f"影响 {r['impact_note']}", "资源批准（资源经理）", "阻塞")
                break

    # ④ 稳定 ID 存在且唯一
    all_ids = [r.get("activity_id", "") for r in a01]
    dup = {i for i in all_ids if i and all_ids.count(i) > 1}
    add(4, "稳定 ID", f"A01 / A02 / B01c（活动 {len(all_ids)} 项）",
        "活动使用 activity_id（A401—A427），父任务 task_id（T05—T15）",
        "禁止用姓名、描述或行号作跨表主键",
        f"重复 ID：{sorted(dup) if dup else '无'}", "无", "通过")

    # ⑤ 依赖完整性
    a02p = root / "01_计划基线/A02_各专业剩余工作反馈.csv"
    unstruct = []
    if a02p.exists():
        for r in _read_csv(a02p):
            if r.get("dependency_type") != "已结构化":
                unstruct.append(f"{r['local_id']}→{r['mapped_activity_id']}")
    if unstruct:
        add(5, "依赖完整性", "；".join(unstruct), "依赖仍为自然语言候选，未结构化",
            "须人工转为结构化依赖，不得直接参与排程计算（否则会误判为可并行）",
            "漏掉依赖会导致资源重复占用、关键路径转移、窗口或验收节点错失",
            "人工确认依赖", "阻塞")

    # ⑥ 资源容量按日期区间有效
    add(6, "容量有效性", "B01b 资源每日容量与承诺",
        "容量按「日期区间容量 − 其他已承诺工作」逐日计算",
        "名单里有人 ≠ 那一天有容量", "P004 / P012 等存在既有承诺需扣除", "无", "通过")

    # ⑦ 来源与确认人可追溯
    add(7, "来源可追溯", "全部材料", "每条记录保留 source_material / 提交人",
        "证据索引保留原值、标准值、规则与来源", "无", "无", "通过")

    # 补充：C03 讨论项与待决事项
    c03p = root / "03_外部条件与协同/C03_协调会纪要.csv"
    if c03p.exists():
        soft = [r["item_id"] for r in _read_csv(c03p) if r.get("item_type") in ("讨论项", "待决事项")]
        if soft:
            add(8, "会议效力", "；".join(soft), "协调会纪要含讨论项 / 待决事项",
                "讨论项与待决事项不得当作正式决定；待决事项不得作为已获批容量",
                "若当作决定执行，执行时会被推翻", "人工确认为决定", "阻塞")

    # 补充：C01 供应商承诺带前置条件
    c01p = root / "03_外部条件与协同/C01_供应商进场计划.csv"
    if c01p.exists():
        for r in _read_csv(c01p):
            if r.get("precondition") and "未确认" not in r.get("note", ""):
                add(9, "前置条件", f"{r['vendor_id']} {r['vendor_name']}",
                    f"承诺附带前置条件：{r['precondition']}",
                    "前置条件未确认前不进入 V1 正式排程",
                    f"影响 {r['scope']}", "确认现场前置条件", "待确认")
                break
    return issues


# ==================================================================
# 四、WBS 映射与稳定 ID（F-67 ~ F-69）
# ==================================================================
def build_wbs(project_id: int, version: str = "V1") -> int:
    """建立统一 WBS：A02 本地工作项 → 活动编号 A401—A427（映射而非覆盖）。"""
    root = _dataset_dir()
    a01 = _read_csv(root / "01_计划基线/A01_项目总控进度计划.csv")
    a02 = _read_csv(root / "01_计划基线/A02_各专业剩余工作反馈.csv")
    local_map: dict[str, list[str]] = {}
    for r in a02:
        local_map.setdefault(r["mapped_activity_id"], []).append(r["local_id"])
    mapped_ok: dict[str, bool] = {}
    for r in a02:
        mapped_ok[r["mapped_activity_id"]] = (
            r.get("dependency_type") == "已结构化"
            and all(c.strip() and _num(r.get("duration_estimate_days")) > 0
                    for c in (r.get("candidate_resource_ids") or "").split(";")))
    db.execute("DELETE FROM plan_activities WHERE project_id=? AND version=?", (project_id, version))
    n = 0
    for r in a01:
        aid = r["activity_id"]
        db.execute(
            "INSERT INTO plan_activities (project_id, version, activity_id, task_id, wbs_path,"
            " activity_name, discipline, owner_resource_id, owner_name, baseline_start, baseline_finish,"
            " forecast_start, forecast_finish, duration_days, is_milestone, milestone_id, quality_gate,"
            " status, actual_progress, approval_status, source_material, local_ids, mapping_confirmed,"
            " updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (project_id, version, aid, r["task_id"], r["wbs_path"], r["activity_name"],
             r["discipline"], r["owner_resource_id"], r["owner_name"],
             r["baseline_start"], r["baseline_finish"], r["forecast_start"], r["forecast_finish"],
             _num(r["duration_days"]), r["is_milestone"], r["milestone_id"], r["quality_gate"],
             r["status"], r["actual_progress"], r["approval_status"], r["source_material"],
             ";".join(local_map.get(aid, [])), 1 if mapped_ok.get(aid) else 0, db.now()))
        n += 1
    return n


def build_dependencies(project_id: int, version: str = "V1") -> dict:
    """建立依赖关系（F-70）：默认 Finish-to-Start；未结构化的标待确认、不建边。"""
    root = _dataset_dir()
    a02 = _read_csv(root / "01_计划基线/A02_各专业剩余工作反馈.csv")
    db.execute("DELETE FROM plan_dependencies WHERE project_id=? AND version=?", (project_id, version))
    stats = {"structured": 0, "unstructured": 0, "gate_only": 0, "window": 0}
    for r in a02:
        succ = r["mapped_activity_id"]
        st = r.get("dependency_statement", "")
        dtype = r.get("dependency_type", "")
        pred, cat, is_struct = _parse_dep(succ, st, dtype)
        if pred:
            db.execute(
                "INSERT INTO plan_dependencies (project_id, version, predecessor_id, successor_id,"
                " dep_type, statement, is_structured, confirm_status, source) VALUES (?,?,?,?,?,?,?,?,?)",
                (project_id, version, pred, succ, "FS", st, 1 if is_struct else 0,
                 "已确认" if is_struct else "待确认", f"A02 {r['local_id']}"))
            stats["structured" if is_struct else "unstructured"] += 1
        elif dtype != "已结构化":
            stats["unstructured"] += 1
        if succ in CONFIRM_GATE_ONLY:
            stats["gate_only"] += 1
        if succ in WINDOW_CONSTRAINTS:
            stats["window"] += 1
    return stats


# ==================================================================
# 五、资源与日历（F-71 / F-79）
# ==================================================================
def build_resources(project_id: int) -> dict:
    root = _dataset_dir()
    b01a = _read_csv(root / "02_资源与日历/B01a_资源池与能力.csv")
    b01b = _read_csv(root / "02_资源与日历/B01b_资源每日容量与承诺.csv")
    b01c = _read_csv(root / "02_资源与日历/B01c_活动资源需求.csv")
    b02p = root / "02_资源与日历/B02_关键测试资源借调申请.csv"
    b02 = _read_csv(b02p) if b02p.exists() else []

    db.execute("DELETE FROM plan_resources WHERE project_id=?", (project_id,))
    db.execute("DELETE FROM plan_resource_capacity WHERE project_id=?", (project_id,))
    db.execute("DELETE FROM plan_activity_demand WHERE project_id=?", (project_id,))

    # 借调申请：已批准才计入正式容量（F-72「申请不等于批准」）
    approved_borrow: dict[str, tuple[float, str, str]] = {}
    for r in b02:
        if r.get("approval_status") == "已批准":
            approved_borrow[r["resource_id"]] = (
                _num(r.get("approved_capacity_hours_per_day")),
                r.get("requested_period_start", ""), r.get("requested_period_end", ""))

    for r in b01a:
        rid = r["resource_id"]
        status = r.get("resource_status", "")
        approved_cap = 0.0
        if rid in approved_borrow:
            approved_cap = approved_borrow[rid][0]
        elif status == "待批准":
            approved_cap = 0.0
        db.execute(
            "INSERT INTO plan_resources (project_id, resource_id, resource_name, department, role,"
            " discipline, skills, capacity_hours_per_day, availability_start, availability_end,"
            " employment_type, resource_status, source_material, approval_status,"
            " approved_capacity_hours_per_day, note) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (project_id, rid, r["resource_name"], r["department"], r["role"], r["discipline"],
             r["skills"], _num(r.get("capacity_hours_per_day")), r["availability_start"],
             r["availability_end"], r["employment_type"], status, r["source_material"],
             "审批中" if status == "待批准" else "正式可用", approved_cap,
             r.get("note", "")))

    # 每日容量：有效容量 = 可用容量 +（已批准借调在窗口内的小时数）
    for r in b01b:
        rid = r["resource_id"]
        d = parse_date(r["work_date"])
        avail = _num(r.get("available_hours"))
        eff = avail
        if rid in approved_borrow:
            cap, s, e = approved_borrow[rid]
            ds, de = parse_date(s), parse_date(e)
            if d and ds and de and ds <= d <= de:
                eff = avail + cap
        db.execute(
            "INSERT INTO plan_resource_capacity (project_id, resource_id, work_date, capacity_hours,"
            " committed_hours, available_hours, effective_capacity_hours, commitment_source, note)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (project_id, rid, r["work_date"], _num(r.get("capacity_hours")),
             _num(r.get("committed_hours")), avail, eff, r.get("commitment_source", ""),
             r.get("note", "")))

    for r in b01c:
        db.execute(
            "INSERT INTO plan_activity_demand (project_id, version, activity_id, resource_id,"
            " demand_role, demand_hours_per_day, demand_start, demand_end, source_material,"
            " confirmation_status, note) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (project_id, "V1", r["activity_id"], r["resource_id"], r["demand_role"],
             _num(r.get("demand_hours_per_day")), r["demand_start"], r["demand_end"],
             r["source_material"], r.get("confirmation_status", "已确认"), r.get("note", "")))
    return {"resources": len(b01a), "capacity_rows": len(b01b), "demand_rows": len(b01c),
            "approved_borrow": list(approved_borrow.keys())}


def collect_constraints(project_id: int) -> list[dict]:
    """五类约束归集（F-71）：任一约束缺失，日期都只是「看起来合理」。"""
    root = _dataset_dir()
    dep_rows = db.query("SELECT * FROM plan_dependencies WHERE project_id=?", (project_id,))
    caps = db.query("SELECT COUNT(*) n FROM plan_resource_capacity WHERE project_id=?", (project_id,))
    c02p = root / "03_外部条件与协同/C02_生产环境与变更窗口通知.csv"
    c02 = _read_csv(c02p) if c02p.exists() else []
    gates = db.query("SELECT COUNT(*) n FROM plan_activities WHERE project_id=? AND quality_gate!='无'",
                     (project_id,))
    return [
        {"kind": "依赖关系", "role": "决定最早开始时间",
         "detail": f"已结构化依赖 {sum(1 for d in dep_rows if d['is_structured'])} 条，"
                   f"待确认（自然语言候选）{sum(1 for d in dep_rows if not d['is_structured'])} 条",
         "status": "部分待确认" if any(not d["is_structured"] for d in dep_rows) else "已确认"},
        {"kind": "工作日历", "role": "决定可用工作时间",
         "detail": f"周一至周五；节假日 {len(HOLIDAYS)} 天；计算区间 2027-04-01 ~ 2027-05-14",
         "status": "已确认"},
        {"kind": "资源容量", "role": "决定并行执行能力",
         "detail": f"资源 {len(db.query('SELECT id FROM plan_resources WHERE project_id=?', (project_id,)))} 人；"
                   f"逐日容量记录 {caps[0]['n']} 条；按日期区间有效",
         "status": "已确认"},
        {"kind": "外部窗口", "role": "决定可交付时机",
         "detail": "；".join(f"{r['window_name']} {r['window_start']} ~ {r['window_end']}"
                            for r in c02) or "无窗口通知",
         "status": "已发布（作为边界约束）"},
        {"kind": "质量门", "role": "确保质量合规通过",
         "detail": f"关联质量门的活动 {gates[0]['n']} 项（G-UAT / G-FAT）；质量门不可压缩",
         "status": "不可放松"},
    ]


def confirm_status(project_id: int) -> list[dict]:
    """确认状态标记（F-72）：区分已确认 / 待确认 / 待批准。"""
    out: list[dict] = []
    for d in db.query("SELECT * FROM plan_dependencies WHERE project_id=? AND is_structured=0",
                      (project_id,)):
        out.append({"object": f"{d['successor_id']} ← {d['statement']}", "kind": "依赖",
                    "status": "待确认", "detail": "自然语言候选，不得直接参与排程计算"})
    for r in db.query("SELECT * FROM plan_resources WHERE project_id=? AND approval_status='审批中'",
                      (project_id,)):
        out.append({"object": f"{r['resource_id']} {r['resource_name']}", "kind": "资源",
                    "status": "待批准", "detail": "姓名已出现但审批未完成，正式容量按 0 计"})
    for d in db.query("SELECT * FROM plan_activity_demand WHERE project_id=? AND confirmation_status!='已确认'",
                      (project_id,)):
        out.append({"object": f"{d['activity_id']} 对 {d['resource_id']} 的资源需求", "kind": "资源需求",
                    "status": "待确认", "detail": f"来源 {d['source_material']}，进入 V1 前需人工确认"})
    for a in db.query("SELECT * FROM plan_activities WHERE project_id=? AND mapping_confirmed=0",
                      (project_id,)):
        out.append({"object": f"{a['activity_id']}（本地编号 {a['local_ids']}）", "kind": "WBS 映射",
                    "status": "待确认", "detail": "映射结果需人工确认后方可进入排程"})
    return out


# ==================================================================
# 六、确定性排程（F-73 ~ F-75）与关键路径（F-82）
# ==================================================================
def schedule(project_id: int, version: str = "V1") -> dict:
    """确定性排程引擎（F-74 / F-75）。

    输入六项：计划起点、工作日历、确认工期、依赖类型（FS）、资源日期区间容量、质量门。
    输出：开始 / 完成日期、最早 / 最晚开始、总时差、关键路径、里程碑偏差，并全量留痕。

    算法（可复核、不含主观判断）：
      1) 正推：无已确认前置的活动以「计划输入开始日（当前预测）」为最早开始；
              有前置者取 max(各前置完成日 + 1 工作日)；
      2) 完成日 = 开始日 +（工期 − 1）工作日；
      3) 逆推：交付边界 = 最终验收（A427）完成日；无后继者以交付边界为最晚完成；
      4) 总时差 = 最晚开始 − 最早开始（工作日）；总时差 ≈ 0 判为关键活动。
    """
    acts = {a["activity_id"]: a for a in db.query(
        "SELECT * FROM plan_activities WHERE project_id=? AND version=?", (project_id, version))}
    deps = db.query("SELECT * FROM plan_dependencies WHERE project_id=? AND version=? AND is_structured=1",
                    (project_id, version))
    preds: dict[str, set] = {k: set() for k in acts}
    succs: dict[str, set] = {k: set() for k in acts}
    for d in deps:
        p, s = d["predecessor_id"], d["successor_id"]
        if p in acts and s in acts:
            preds[s].add(p)
            succs[p].add(s)

    plan_start = min((parse_date(a["baseline_start"]) for a in acts.values()
                      if a["baseline_start"]), default=date(2027, 4, 1))

    # ---- 拓扑排序（Kahn）：正推按拓扑序，逆推按反拓扑序，否则时差会算错 ----
    indeg = {k: len(preds[k] & set(acts)) for k in acts}
    from collections import deque
    dq = deque([k for k in sorted(acts) if indeg[k] == 0])
    topo: list[str] = []
    while dq:
        n = dq.popleft()
        topo.append(n)
        for s in sorted(succs.get(n, ())):
            if s in indeg:
                indeg[s] -= 1
                if indeg[s] == 0:
                    dq.append(s)
    # 兜底：若存在环（异常数据），按活动编号补齐，避免丢项
    for k in sorted(acts):
        if k not in topo:
            topo.append(k)

    # ---- 正推（按拓扑序）----
    ES: dict[str, date] = {}
    EF: dict[str, date] = {}
    recheck: list[dict] = []
    for aid in topo:
        a = acts[aid]
        dur = max(1, int(_num(a["duration_days"], 1)))
        cand = [add_workdays(EF[p], 1) for p in preds[aid] if p in EF]
        if cand:
            es = max(cand)
        else:
            es = parse_date(a["forecast_start"]) or next_workday(plan_start)
        ES[aid] = es
        EF[aid] = add_workdays(es, dur - 1)
        # 复核：排程开始日 vs 计划输入开始日
        fin = parse_date(a["forecast_start"])
        if fin and fin != es:
            recheck.append({
                "activity_id": aid, "activity_name": a["activity_name"],
                "kind": "依赖复核",
                "detail": f"计划输入开始 {fs(fin)}，按前置依赖重算为 {fs(es)}"
                          f"（前置 {sorted(preds[aid])}）",
                "impact": "排程结果与当前预测不一致，须确认是依赖遗漏还是预测已过期"})

    # ---- 交付边界与逆推（按反拓扑序）----
    # 交付边界 = 最终验收（A427）完成日。完成日晚于交付边界的活动（试运行观察、培训执行等
    # 上线后尾链）不参与逆推传播，避免其负时差反向污染验收链的关键路径判断；单列提示。
    boundary = EF.get("A427") or max(EF.values())
    excluded = {aid for aid in acts if EF[aid] > boundary}
    LS: dict[str, date] = {}
    LF: dict[str, date] = {}
    for aid in reversed(topo):
        dur = max(1, int(_num(acts[aid]["duration_days"], 1)))
        cand = [shift_back_workdays(LS[s], 1) for s in succs[aid]
                if s in LS and s not in excluded]
        lf = min(cand) if cand else boundary
        LF[aid] = lf
        LS[aid] = shift_back_workdays(lf, dur - 1) if dur > 1 else lf

    # ---- 落库 ----
    db.execute("DELETE FROM plan_evidence WHERE project_id=? AND version=? AND category='排程'",
               (project_id, version))
    beyond: list[dict] = []
    for aid, a in acts.items():
        fl = signed_float(ES[aid], LS[aid])
        crit = 1 if fl == 0 else 0
        if fl < 0:
            beyond.append({"activity_id": aid, "activity_name": a["activity_name"],
                           "over_days": -fl, "scheduled_finish": fs(EF[aid]),
                           "boundary": fs(boundary),
                           "note": "完成日晚于交付边界（最终验收）；该链依赖待确认，暂不纳入 V1 关键路径"})
        db.execute(
            "UPDATE plan_activities SET scheduled_start=?, scheduled_finish=?, earliest_start=?,"
            " latest_start=?, float_days=?, is_critical=? WHERE project_id=? AND version=? AND activity_id=?",
            (fs(ES[aid]), fs(EF[aid]), fs(ES[aid]), fs(LS[aid]), fl, crit,
             project_id, version, aid))
        db.execute(
            "INSERT INTO plan_evidence (project_id, version, step, category, ref_key, original_value,"
            " standard_value, rule, source, confirm_status, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (project_id, version, "6 确定性排程", "排程", aid,
             f"预测 {a['forecast_start']}~{a['forecast_finish']}",
             f"{fs(ES[aid])}~{fs(EF[aid])}",
             f"工期 {a['duration_days']} 工作日，前置 {sorted(preds[aid]) or '无'}，总时差 {fl} 天",
             a["source_material"], "已计算", db.now()))

    # 快照（输入 + 参数 + 结果）
    payload = {
        "plan_start": fs(plan_start), "boundary": fs(boundary),
        "calendar": "周一至周五，扣除节假日：" + ", ".join(fs(h) for h in sorted(HOLIDAYS)),
        "activities": [{"activity_id": a, "duration": _num(acts[a]["duration_days"]),
                        "preds": sorted(preds[a]), "es": fs(ES[a]), "ef": fs(EF[a]),
                        "ls": fs(LS[a]), "lf": fs(LF[a]),
                        "float": signed_float(ES[a], LS[a]),
                        "critical": 1 if signed_float(ES[a], LS[a]) == 0 else 0}
                       for a in sorted(acts)],
    }
    db.execute("DELETE FROM plan_snapshots WHERE project_id=? AND version=? AND label='排程输入快照'",
               (project_id, version))
    db.execute(
        "INSERT INTO plan_snapshots (project_id, version, payload, checksum, label, created_at)"
        " VALUES (?,?,?,?,?,?)",
        (project_id, version, json.dumps(payload, ensure_ascii=False),
         hashlib.md5(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12],
         "排程输入快照", db.now()))

    crit_chain = sorted([a for a in acts if signed_float(ES[a], LS[a]) == 0], key=lambda x: ES[x])
    be = [{"activity_id": a["activity_id"], "activity_name": a["activity_name"],
           "scheduled_finish": fs(EF[a["activity_id"]]), "baseline_finish": a["baseline_finish"],
           "forecast_finish": a["forecast_finish"],
           "milestone_id": a["milestone_id"]} for a in acts.values() if a["is_milestone"] == "是"]
    return {"version": version, "plan_start": fs(plan_start), "boundary": fs(boundary),
            "critical_chain": crit_chain, "boundary_activity": "A427",
            "milestone_deviation": be, "recheck": recheck, "beyond_boundary": beyond,
            "count": len(acts)}


def critical_path(project_id: int, version: str = "V1") -> dict:
    """关键路径计算与可解释（F-82）：回答「它为什么关键」。"""
    acts = {a["activity_id"]: a for a in db.query(
        "SELECT * FROM plan_activities WHERE project_id=? AND version=?", (project_id, version))}
    chain = [a for a in acts.values() if a["is_critical"]]
    chain.sort(key=lambda x: x["scheduled_start"] or "")
    reasons = [
        "前置关系连续：链路上一环的完成日紧接下一环的开始日",
        "总时差接近 0：任何延迟都会直接推移交付日期",
        "关键测试与 UAT 质量门不可压缩（G-UAT / G-FAT）",
        "生产切换与最终验收受窗口与签署限制（W-01 窗口、人工确认）",
        "资源受限时关键链可能发生局部变化（见资源负荷与冲突预警）",
    ]
    nodes = []
    for a in chain:
        preds = [d["predecessor_id"] for d in db.query(
            "SELECT * FROM plan_dependencies WHERE project_id=? AND successor_id=?",
            (project_id, a["activity_id"]))]
        nodes.append({
            "activity_id": a["activity_id"], "activity_name": a["activity_name"],
            "wbs_path": a["wbs_path"], "predecessors": preds,
            "duration_days": a["duration_days"], "float_days": a["float_days"],
            "scheduled_start": a["scheduled_start"], "scheduled_finish": a["scheduled_finish"],
            "quality_gate": a["quality_gate"], "milestone_id": a["milestone_id"],
            "owner_name": a["owner_name"], "version": a["version"], "source": a["source_material"],
        })
    return {"chain": nodes, "reasons": reasons,
            "length_days": len(chain), "boundary": acts.get("A427", {}).get("scheduled_finish", "")}


def resource_load(project_id: int, version: str = "V1") -> list[dict]:
    """资源可用性计算（F-79）：逐日 capacity / committed / available / demand / utilization。"""
    caps = db.query("SELECT * FROM plan_resource_capacity WHERE project_id=? ORDER BY resource_id, work_date",
                    (project_id,))
    demands = db.query("SELECT * FROM plan_activity_demand WHERE project_id=? AND version=?",
                       (project_id, version))
    by_day: dict[tuple, list] = {}
    for d in demands:
        ds, de = parse_date(d["demand_start"]), parse_date(d["demand_end"])
        if not ds or not de:
            continue
        cur = ds
        while cur <= de:
            if is_workday(cur):
                by_day.setdefault((d["resource_id"], fs(cur)), []).append(d)
            cur += timedelta(days=1)
    out = []
    for c in caps:
        key = (c["resource_id"], c["work_date"])
        ds = by_day.get(key, [])
        demand = round(sum(_num(x["demand_hours_per_day"]) for x in ds), 2)
        eff = c["effective_capacity_hours"] or c["available_hours"]
        util = round(demand / eff * 100, 1) if eff else 0.0
        out.append({
            "resource_id": c["resource_id"], "work_date": c["work_date"],
            "capacity_hours": c["capacity_hours"], "committed_hours": c["committed_hours"],
            "available_hours": c["available_hours"], "effective_capacity_hours": eff,
            "demand_hours": demand, "utilization": util,
            "over": demand > eff,
            "activities": sorted({x["activity_id"] for x in ds}),
            "commitment_source": c["commitment_source"],
        })
    return out


def detect_conflicts(project_id: int, version: str = "V1") -> list[dict]:
    """资源冲突识别（F-80）与冲突预警六要素（F-83）。"""
    loads = resource_load(project_id, version)
    res = {r["resource_id"]: r for r in db.query(
        "SELECT * FROM plan_resources WHERE project_id=?", (project_id,))}
    db.execute("DELETE FROM plan_conflicts WHERE project_id=? AND version=?", (project_id, version))
    over = [l for l in loads if l["over"]]
    # 按（资源, 连续日期）分组，合并为一条预警
    groups: dict[str, list[dict]] = {}
    for l in over:
        groups.setdefault(l["resource_id"], []).append(l)
    # 按最严重利用率降序编号，保证课件锚点（P004 = CF-01）编号稳定
    groups = dict(sorted(groups.items(),
                         key=lambda kv: -max(x["utilization"] for x in kv[1])))
    out = []
    idx = 0
    for rid, items in groups.items():
        idx += 1
        cid = f"CF-{idx:02d}"
        items = sorted(items, key=lambda x: x["work_date"])
        acts = sorted({a for it in items for a in it["activities"]})
        dates = [it["work_date"] for it in items]
        worst = max(items, key=lambda x: x["utilization"])
        r = res.get(rid, {})
        opts = ["错峰排开并发需求", "分配替代资源（如 P010 王楠，外部测试顾问）",
                "在获批情景中使用待批准资源（如 P011 何嘉悦）", "调整里程碑以吸收冲突"]
        db.execute(
            "INSERT INTO plan_conflicts (project_id, version, conflict_id, conflict_type, object_id,"
            " object_name, conflict_date, reason, evidence, impact, options, owner, pending, level,"
            " status, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (project_id, version, cid, "资源超载",
             f"{rid};{';'.join(acts)}", f"{r.get('resource_name','')}（{r.get('role','')}）",
             f"{dates[0]}" + (f" ~ {dates[-1]}" if len(dates) > 1 else ""),
             f"同一资源并发需求 {worst['demand_hours']}h 超过有效容量 {worst['effective_capacity_hours']}h，"
             f"利用率 {worst['utilization']}%",
             f"B01b 资源日历 + B01c 活动资源需求 + {version} 计算记录",
             "影响关键测试 A411 及后续 UAT、切换与验收链",
             "；".join(opts), "项目经理 / 测试负责人 / 资源经理",
             "P011 借调审批与 P010 远程协同时段待确认", "超载预警", "未确认", db.now(), db.now()))
        out.append({"conflict_id": cid, "resource_id": rid, "activities": acts,
                    "dates": dates, "worst_utilization": worst["utilization"]})
    return out


def conflict_flow(project_id: int) -> list[dict]:
    """预警状态流转（F-84）：未确认 → 处理中 → 已接受 / 已关闭。"""
    return db.query("SELECT * FROM plan_conflicts WHERE project_id=? ORDER BY conflict_id", (project_id,))


def allocation_options(project_id: int) -> list[dict]:
    """资源分配方案（F-81）：待批准资源只能进入「批准情景」，不得进入 V1 正式容量。"""
    return [
        {"option": "错峰", "detail": "把 A408 / A410 / A411 对 P004 的并发需求错开到不同日期",
         "precondition": "各专业接受调整后的窗口", "affects_v1": "是（重排日期）"},
        {"option": "替代资源", "detail": "使用 P010 王楠（外部测试顾问，已批准，4h/日）分担关键测试",
         "precondition": "确认远程协同时段", "affects_v1": "是（容量计入 V1）"},
        {"option": "批准情景内使用待批准资源", "detail": "P011 何嘉悦借调（4h/日），仅进入 S2 批准情景",
         "precondition": "资源批准（资源经理）", "affects_v1": "否（正式容量仍为 0）"},
        {"option": "调整里程碑", "detail": "把 UAT 与最终验收节点整体后移以吸收资源冲突",
         "precondition": "正式变更批准 + 质量门不放松", "affects_v1": "是（里程碑偏差扩大）"},
    ]


# ==================================================================
# 七、版本、事件与方案比较（F-85 ~ F-87）
# ==================================================================
SCENARIOS = [
    {"version": "S1", "label": "资源稳定优先", "kind": "备选情景", "status": "情景（未批准）",
     "condition": "不新增批准、不降低质量门",
     "result": "确定性最早约 5 月 5 日；管理预测约 5 月 7 日",
     "cost": "新增成本 0；延期风险持续", "schedule_impact_days": 1, "cost_impact_value": 0,
     "is_formal": 0, "basis_event": ""},
    {"version": "S2", "label": "工期优先", "kind": "备选情景", "status": "情景（未批准）",
     "condition": "P011 获批 4 小时/日 + P010 远程支持确认",
     "result": "向 5 月 4—5 日收敛", "cost": "P011 约 48 小时 = 6 人日；内部机会成本约 6,600 元（估算）",
     "schedule_impact_days": 0, "cost_impact_value": 6600, "is_formal": 0, "basis_event": "D03"},
    {"version": "S3", "label": "业务分阶段", "kind": "备选情景", "status": "情景（未批准）",
     "condition": "CHG-CY-2027-004 正式批准",
     "result": "降低一次切换风险；最终验收仍依赖二阶段与证据",
     "cost": "+4 工作日；增量成本 45,000 元（估算）",
     "schedule_impact_days": 4, "cost_impact_value": 45000, "is_formal": 0, "basis_event": "D03"},
]


def freeze_v1(project_id: int) -> dict:
    """版本冻结与恢复点（F-85）：冻结输入快照、计算参数、日期结果、资源分配。"""
    db.execute("DELETE FROM plan_versions WHERE project_id=? AND version='V1'", (project_id,))
    acts = db.query("SELECT * FROM plan_activities WHERE project_id=? AND version='V1'", (project_id,))
    loads = resource_load(project_id, "V1")
    payload = {
        "activities": [{"activity_id": a["activity_id"], "scheduled_start": a["scheduled_start"],
                        "scheduled_finish": a["scheduled_finish"], "float": a["float_days"],
                        "critical": a["is_critical"]} for a in acts],
        "resource_load": [l for l in loads if l["demand_hours"] > 0],
    }
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    db.execute(
        "INSERT INTO plan_versions (project_id, version, kind, label, status, is_formal, frozen_at,"
        " created_at) VALUES (?,?,?,?,?,?,?,?)",
        (project_id, "V1", "冻结基准", "计划 V1（冻结）", "已冻结", 1, db.now(), db.now()))
    db.execute("DELETE FROM plan_snapshots WHERE project_id=? AND version='V1' AND label='版本恢复点'",
               (project_id,))
    db.execute(
        "INSERT INTO plan_snapshots (project_id, version, payload, checksum, label, created_at)"
        " VALUES (?,?,?,?,?,?)",
        (project_id, "V1", body, hashlib.md5(body.encode()).hexdigest()[:12], "版本恢复点", db.now()))
    return {"version": "V1", "checksum": hashlib.md5(body.encode()).hexdigest()[:12],
            "activities": len(acts), "frozen_at": db.now()}


def ingest_events(project_id: int) -> list[dict]:
    """接入 D01—D04（本期不授权，仅登记，不参与 V1 计算）。"""
    root = _dataset_dir()
    db.execute("DELETE FROM plan_events WHERE project_id=?", (project_id,))
    out = []
    ddir = root / "04_动态事件（暂不授权）"
    if not ddir.exists():
        return out
    for f in sorted(ddir.iterdir()):
        if f.suffix.lower() != ".csv":
            continue
        for r in _read_csv(f):
            db.execute(
                "INSERT INTO plan_events (project_id, event_id, event_type, issuer, issued_at,"
                " event_authority, approval_status, required_action, payload, applied)"
                " VALUES (?,?,?,?,?,?,?,?,?,0)",
                (project_id, r["event_id"], r["event_type"], r.get("issuer", ""), r.get("issued_at", ""),
                 r.get("event_authority", ""), r.get("approval_status", ""),
                 r.get("required_action", ""), json.dumps(r, ensure_ascii=False)))
            out.append({"event_id": r["event_id"], "event_type": r["event_type"],
                        "event_authority": r.get("event_authority", ""),
                        "approval_status": r.get("approval_status", ""),
                        "required_action": r.get("required_action", "")})
    return out


def apply_event(project_id: int, event_id: str) -> dict:
    """事件效力判定与追加式调整（F-86）：先判效力，再决定重算 / 模拟 / 记录 / 等待确认。"""
    rows = db.query("SELECT * FROM plan_events WHERE project_id=? AND event_id=?", (project_id, event_id))
    if not rows:
        return {"ok": False, "error": "事件不存在"}
    ev = rows[0]
    auth = ev["event_authority"]
    result = {"event_id": event_id, "event_authority": auth, "v1_unchanged": True, "actions": []}

    if auth == "立即生效":
        # D02：把 P004 在生效期内的有效容量降为 2h/日，重算冲突
        payload = json.loads(ev["payload"] or "{}")
        rid = payload.get("resource_id", "P004")
        s, e = payload.get("effective_start", ""), payload.get("effective_end", "")
        new_cap = _num(payload.get("new_capacity_hours_per_day"))
        ds, de = parse_date(s), parse_date(e)
        for c in db.query("SELECT * FROM plan_resource_capacity WHERE project_id=? AND resource_id=?",
                          (project_id, rid)):
            d = parse_date(c["work_date"])
            if ds and de and d and ds <= d <= de:
                db.execute(
                    "UPDATE plan_resource_capacity SET effective_capacity_hours=? WHERE id=?",
                    (new_cap, c["id"]))
        cf = detect_conflicts(project_id, "V2")
        result["actions"].append(f"已批准 → 立即把 {rid} 在 {s} 至 {e} 的有效容量降为 {new_cap}h/日，并重算冲突")
        result["v1_unchanged"] = False
        result["conflicts_v2"] = [c["conflict_id"] for c in cf]
        _derive_version(project_id, "V2", "派生版本", f"追加事件 {event_id}（立即生效）",
                        "已派生（资源容量变化，日期不变）", event_id, "")
    elif auth == "条件生效":
        result["actions"].append("已通知待甲方确认 → 保留原承诺，追加 P010 可用性条件；不直接重算 V1")
        result["v1_unchanged"] = True
        result["pending"] = "甲方确认现场电力验收单签署后条件生效"
    elif auth == "仅情景模拟":
        payload = json.loads(ev["payload"] or "{}")
        for sc in SCENARIOS:
            if sc["version"] == "S3":
                _derive_version(project_id, "S3", "备选情景", sc["label"], sc["status"], event_id,
                                sc["condition"], sc["result"], sc["cost"],
                                _num(payload.get("schedule_impact_days", 4)),
                                _num(payload.get("cost_impact_value", 45000)), 0)
        result["actions"].append("待批准 → 只创建 S3 情景，记录 +4 工作日与增量成本 45,000 元；不得进入 V1")
    elif auth == "仅形成比对任务":
        for sc in SCENARIOS:
            if sc["version"] in ("S1", "S2"):
                _derive_version(project_id, sc["version"], sc["kind"], sc["label"], sc["status"],
                                event_id, sc["condition"], sc["result"], sc["cost"],
                                sc["schedule_impact_days"], sc["cost_impact_value"], 0)
        result["actions"].append("已分发无批准决定 → 比较工期、成本与资源稳定方案，形成待确认事项；不修改 V1")

    db.execute("UPDATE plan_events SET applied=1, applied_at=?, derived_version=? WHERE id=?",
               (db.now(), ",".join(result.get("conflicts_v2", [])) or auth, ev["id"]))
    return result


def _derive_version(project_id, version, kind, label, status, basis_event, condition="",
                    result_summary="", cost_summary="", impact_days=0, cost_value=0, is_formal=0):
    db.execute("DELETE FROM plan_versions WHERE project_id=? AND version=?", (project_id, version))
    db.execute(
        "INSERT INTO plan_versions (project_id, version, kind, label, status, basis_event, condition,"
        " result_summary, cost_summary, schedule_impact_days, cost_impact_value, is_formal, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (project_id, version, kind, label, status, basis_event, condition, result_summary,
         cost_summary, impact_days, cost_value, is_formal, db.now()))


def compare_scenarios(project_id: int) -> dict:
    """方案比较（F-87）：条件 / 结果 / 代价三维，说清「放松了什么、获得了什么、由谁确认」。"""
    vs = db.query("SELECT * FROM plan_versions WHERE project_id=? ORDER BY id", (project_id,))
    rows = []
    for v in vs:
        rows.append({
            "version": v["version"], "label": v["label"], "kind": v["kind"], "status": v["status"],
            "condition": v["condition"] or "—", "result": v["result_summary"] or "—",
            "cost": v["cost_summary"] or "—",
            "schedule_impact_days": v["schedule_impact_days"], "cost_impact_value": v["cost_impact_value"],
            "is_formal": v["is_formal"], "basis_event": v["basis_event"],
            "confirm_by": "项目经理 / 资源经理" + ("（正式变更）" if v["version"] == "S3" else ""),
        })
    return {"versions": rows, "quality_gate_unchanged": True,
            "note": "三类方案均保持质量门不变；情景不等于已批准计划"}


# ==================================================================
# 八、建议六要素与人工确认关卡（F-88）
# ==================================================================
def build_confirmations(project_id: int) -> list[dict]:
    """五类人工确认关卡（N-19）：Agent 不执行责任动作。"""
    root = _dataset_dir()
    c02 = _read_csv(root / "03_外部条件与协同/C02_生产环境与变更窗口通知.csv")
    win = c02[0]["window_start"] if c02 else "2027-04-29 22:00"
    items = [
        ("资源批准", "P011 何嘉悦有限期借调（4 小时/日）", "P011", "测试与质量部经理 / 项目交付部负责人",
         "2027-04-07", "B02 借调申请 + B01 资源池 + CF-01"),
        ("正式变更", "CHG-CY-2027-004 分阶段上线变更申请", "CHG-CY-2027-004", "变更控制委员会",
         "2027-04-07", "D03 变更申请"),
        ("生产切换", "A423 生产切换（须在批准窗口内执行）", "A423", "上线与切换负责人（P013 李承泽）",
         "2027-04-29", f"W-01 窗口 {win}"),
        ("UAT 签署", "A417 UAT 签署（P1/P2 缺陷 = 0）", "A417", "质量与验收负责人（P012 张维汉）",
         "2027-04-27", "G-UAT 质量门 + UAT 执行结果"),
        ("最终验收", "A427 最终验收（验收证据须齐备）", "A427", "质量与验收负责人（P012 张维汉）",
         "2027-05-04", "G-FAT 质量门 + 证据索引"),
    ]
    db.execute("DELETE FROM plan_confirmations WHERE project_id=?", (project_id,))
    for act, title, obj, owner, due, ev in items:
        db.execute(
            "INSERT INTO plan_confirmations (project_id, version, action_type, title, object_id, owner,"
            " due_date, evidence, status, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (project_id, "V1", act, title, obj, owner, due, ev, "待确认", db.now()))
    return db.query("SELECT * FROM plan_confirmations WHERE project_id=? ORDER BY id", (project_id,))


def build_advices(project_id: int) -> list[dict]:
    """建议六要素（F-88）：具体对象 / 证据 / 责任人 / 期限 / 替代方案 / 待确认事项。"""
    db.execute("DELETE FROM plan_advices WHERE project_id=?", (project_id,))
    items = [
        ("资源批准", "P011 测试资源（有限期借调 4 小时/日）",
         "B02 借调申请 + B01 资源池 + CF-01 资源超载预警",
         "测试与质量部经理 / 项目交付部负责人", "2027-04-07",
         "错峰并延后验收", "每日投入上限、有效期、对其他项目的影响"),
        ("正式变更", "CHG-CY-2027-004（生产切换拆分为两阶段）",
         "D03 变更申请 + W-01 变更窗口", "变更控制委员会", "2027-04-07",
         "维持一次切换（S1 资源稳定优先）", "增量成本 45,000 元与 +4 工作日的批准"),
        ("生产切换", "A423 生产切换（W-01 窗口内执行）",
         "W-01 窗口通知 + A422 验收准备完成", "P013 李承泽（上线与切换负责人）", "2027-04-29",
         "启用 W-02 备份窗口（2027-05-07）", "窗口内并发操作限制与回退预案"),
    ]
    for act, obj, ev, owner, due, alt, pend in items:
        db.execute(
            "INSERT INTO plan_advices (project_id, version, action_type, object, evidence, owner,"
            " due_date, alternative, pending, status, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (project_id, "V1", act, obj, ev, owner, due, alt, pend, "草案", db.now()))
    return db.query("SELECT * FROM plan_advices WHERE project_id=? ORDER BY id", (project_id,))


# ==================================================================
# 九、证据、审计与自动停止（F-89 / F-90）
# ==================================================================
def build_evidence(project_id: int, version: str = "V1") -> list[dict]:
    """证据与审计轨迹（F-89）：原值 / 标准值 / 规则 / 来源 / 版本 / 确认状态。"""
    db.execute("DELETE FROM plan_evidence WHERE project_id=? AND version=? AND category IN"
               " ('效力判定','WBS 映射','约束归集')", (project_id, version))

    def add(step, cat, key, orig, std, rule, src, conf):
        db.execute(
            "INSERT INTO plan_evidence (project_id, version, step, category, ref_key, original_value,"
            " standard_value, rule, source, confirm_status, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (project_id, version, step, cat, key, orig, std, rule, src, conf, db.now()))

    # 效力判定
    for r in db.query("SELECT * FROM plan_materials WHERE project_id=? ORDER BY material_code",
                      (project_id,)):
        add("2 判断文件角色与效力", "效力判定", r["material_code"], r["effectiveness"],
            f"效力={r['effectiveness']}；批准={'是' if r['approved'] else '否'}；接入={r['access_mode']}",
            "效力四问：谁发布 / 何时生效 / 是否批准 / 能否追溯", r["material_name"],
            "已批准" if r["approved"] else "待确认")
    # WBS 映射
    for a in db.query("SELECT * FROM plan_activities WHERE project_id=? ORDER BY activity_id",
                      (project_id,)):
        if a["local_ids"]:
            add("4 建立统一 WBS", "WBS 映射", a["activity_id"], a["local_ids"],
                f"{a['local_ids']} → {a['activity_id']} → {a['task_id']}",
                "映射而非覆盖：保留原始 ID 与描述", a["source_material"],
                "已确认" if a["mapping_confirmed"] else "待确认")
    # 约束归集
    for c in collect_constraints(project_id):
        add("5 人工确认约束与假设", "约束归集", c["kind"], c["detail"], c["status"],
            "五类约束共同决定日期", "B01 / A02 / C02 / 质量门", c["status"])
    return db.query("SELECT * FROM plan_evidence WHERE project_id=? ORDER BY id", (project_id,))


def auto_stops(project_id: int) -> list[dict]:
    """自动停止（F-90）：来源不足 / 解析失败 / 关键假设未确认 / 责任动作即将发生。"""
    db.execute("DELETE FROM plan_stops WHERE project_id=?", (project_id,))
    stops: list[dict] = []

    def add(t, reason, impact, ref):
        db.execute(
            "INSERT INTO plan_stops (project_id, version, stop_type, reason, impact, ref_key, status,"
            " created_at) VALUES (?,?,?,?,?,?,?,?)",
            (project_id, "V1", t, reason, impact, ref, "open", db.now()))
        stops.append({"stop_type": t, "reason": reason, "impact": impact, "ref": ref})

    # ① 来源不足
    miss = [m for m in db.query("SELECT * FROM plan_materials WHERE project_id=?", (project_id,))
            if not m["issuer"] and m["access_mode"] == "只读接入"]
    if miss:
        add("来源不足", f"{len(miss)} 份材料未标注发布主体", "效力四问不齐，不得进入正式排程",
            "；".join(m["material_code"] for m in miss))
    # ② 解析失败 / 关键假设未确认
    un = db.query("SELECT * FROM plan_dependencies WHERE project_id=? AND is_structured=0", (project_id,))
    if un:
        add("关键假设未确认",
            f"{len(un)} 条依赖为自然语言候选，未能解析为结构化依赖",
            "相关活动可能被误判为可并行，导致资源重复占用与关键路径转移",
            "；".join(f"{d['successor_id']}" for d in un))
    ap = db.query("SELECT * FROM plan_resources WHERE project_id=? AND approval_status='审批中'", (project_id,))
    if ap:
        add("关键假设未确认",
            f"{len(ap)} 项资源处于审批中（申请不等于批准）",
            "正式容量按 0 计；若按已批准排程，里程碑将不可达",
            "；".join(r["resource_id"] for r in ap))
    # ④ 责任动作即将发生
    add("责任动作即将发生",
        "生产切换（A423）、UAT 签署（A417）、最终验收（A427）等责任动作等待人工确认",
        "Agent 不执行责任动作，流程停在人工确认前", "A417 / A423 / A427")
    return stops


# ==================================================================
# 十、总览与全流程
# ==================================================================
def overview(project_id: int) -> dict:
    acts = db.query("SELECT * FROM plan_activities WHERE project_id=? AND version='V1'", (project_id,))
    crit = [a for a in acts if a["is_critical"]]
    cf = db.query("SELECT * FROM plan_conflicts WHERE project_id=?", (project_id,))
    ver = db.query("SELECT * FROM plan_versions WHERE project_id=?", (project_id,))
    loads = resource_load(project_id, "V1")
    over_days = [l for l in loads if l["over"]]
    materials = db.query("SELECT * FROM plan_materials WHERE project_id=?", (project_id,))
    return {
        "project_id": project_id,
        "project_code": PROJECT_ID,
        "materials_count": len(materials),
        "materials_authorized": sum(1 for m in materials if m["access_mode"] == "只读接入"),
        "materials_pending": sum(1 for m in materials if m["access_mode"] != "只读接入"),
        "activities_count": len(acts),
        "milestones_count": sum(1 for a in acts if a["is_milestone"] == "是"),
        "critical_count": len(crit),
        "conflicts_open": sum(1 for c in cf if c["status"] in ("未确认", "处理中")),
        "resource_over_days": len(over_days),
        "versions": [{"version": v["version"], "label": v["label"], "status": v["status"],
                      "is_formal": v["is_formal"]} for v in ver],
        "boundary": next((a["scheduled_finish"] for a in acts if a["activity_id"] == "A427"), ""),
        "plan_start": min((a["scheduled_start"] for a in acts if a["scheduled_start"]), default=""),
        "running": is_running(project_id),
        "latest": db.query("SELECT created_at FROM plan_snapshots WHERE project_id=? ORDER BY id DESC LIMIT 1",
                           (project_id,)),
    }


def run_planning(project_id: int) -> dict:
    """阶段1 全流程：接入 → 效力 → 检查 → WBS → 依赖 → 资源 → 排程 → 冲突 → 冻结 → 建议 → 停止。

    同一项目的多次调用串行执行（互斥锁），避免重复行与脏快照。
    """
    with _project_lock(project_id):
        return _run_planning(project_id)


def _run_planning(project_id: int) -> dict:
    ingest_materials(project_id)
    checks = input_check_seven(project_id)
    build_wbs(project_id)
    dep_stats = build_dependencies(project_id)
    res_stats = build_resources(project_id)
    sch = schedule(project_id)
    confs = detect_conflicts(project_id)
    freeze = freeze_v1(project_id)
    ingest_events(project_id)
    build_confirmations(project_id)
    build_advices(project_id)
    build_evidence(project_id)
    stops = auto_stops(project_id)
    return {"checks": len(checks), "issues": sum(1 for c in checks if c["level"] == "阻塞"),
            "dep_stats": dep_stats, "res_stats": res_stats, "schedule": sch,
            "conflicts": len(confs), "freeze": freeze, "stops": len(stops)}


# ==================================================================
# 十一、异步任务（与 datasmart 一致的守护线程模式）
# ==================================================================
def start_run(project_id: int) -> str:
    job_id = uuid.uuid4().hex[:12]
    with _jobs_lock:
        # 记录 project_id：/board 需要据此判断「该项目是否有运行中的任务」，
        # 避免前端在重算中途读到半成品数据（材料/活动/容量行可能只写入了一部分）。
        _jobs[job_id] = {"status": "running", "progress": 0, "result": None,
                         "error": None, "project_id": project_id}

    def _worker():
        try:
            res = run_planning(project_id)
            with _jobs_lock:
                _jobs[job_id].update({"status": "completed", "progress": 100, "result": res})
        except Exception as e:  # noqa: BLE001
            with _jobs_lock:
                _jobs[job_id].update({"status": "failed", "error": str(e)})

    threading.Thread(target=_worker, daemon=True).start()
    return job_id


def get_job(job_id: str) -> dict | None:
    with _jobs_lock:
        return _jobs.get(job_id)


def is_running(project_id: int) -> bool:
    """该项目是否存在尚未结束（running）的计划任务。

    重算期间各表会被 DELETE + 逐条 INSERT，此时读取会得到残缺数据；
    前端据此提示「正在重算」，而不是把一个中间态当成结果展示。
    """
    with _jobs_lock:
        return any(j.get("project_id") == project_id and j.get("status") == "running"
                   for j in _jobs.values())


def wait_until_idle(project_id: int, timeout: float = 30.0) -> bool:
    """等待该项目的在途重算结束，返回是否已空闲。

    读接口（/board、/schedule 等）在读取前调用，可保证读到的是一个完整结果集，
    而不是 DELETE / INSERT 之间被截断的中间态。重算本身只需 1~2 秒，
    因此这里的等待通常极短；超时则放弃等待（返回 False），绝不阻塞请求不返回。
    """
    if not is_running(project_id):
        return True
    lock = _project_lock(project_id)
    got = lock.acquire(timeout=timeout)
    if got:
        lock.release()
    return got
