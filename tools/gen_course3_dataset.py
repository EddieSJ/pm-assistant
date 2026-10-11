#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成课程3「计划与资源智能调度」模拟数据包。

依据：
  - 课程3PPT.pdf（30 页）的活动锚点、资源锚点、日期锚点
  - 课程2 既有数据包（02_模拟数据包，状态日 2027-03-31）的任务 T01~T15、
    资源 P001~P010、里程碑 M01~M10 体系

输出：<项目根>/03_模拟数据包-课程3/
用法：python3 tools/gen_course3_dataset.py
"""
import csv
from datetime import date, timedelta
from pathlib import Path

PROJECT_ID = "CY-DCM-2026-01"
PROJ_ROOT = Path(__file__).resolve().parents[2]
OUT_ROOT = PROJ_ROOT / "03_模拟数据包-课程3"

# ---------- 工作日历（教学设定，非真实放假安排） ----------
HOLIDAYS = {
    date(2027, 4, 5),   # 清明节
    date(2027, 5, 1),   # 劳动节
    date(2027, 5, 2),
    date(2027, 5, 3),
    date(2027, 6, 9),   # 端午节
}


def is_workday(d: date) -> bool:
    return d.weekday() < 5 and d not in HOLIDAYS


def next_workday(d: date) -> date:
    d += timedelta(days=1)
    while not is_workday(d):
        d += timedelta(days=1)
    return d


def add_workdays(start: date, n: int) -> date:
    """从 start 起第 n 个工作日（start 计为第 1 个）。"""
    cur = start
    for _ in range(n - 1):
        cur = next_workday(cur)
    return cur


def shift_back_workdays(start: date, n: int) -> date:
    """从 start 往前推 n 个工作日。"""
    d = start
    for _ in range(n):
        d -= timedelta(days=1)
        while not is_workday(d):
            d -= timedelta(days=1)
    return d


def workdays_between(a: date, b: date) -> int:
    cnt, d = 0, a
    while d <= b:
        if is_workday(d):
            cnt += 1
        d += timedelta(days=1)
    return cnt


def workdays_span(a: date, b: date) -> list[date]:
    out, d = [], a
    while d <= b:
        if is_workday(d):
            out.append(d)
        d += timedelta(days=1)
    return out


def dt(y, m, d) -> date:
    return date(y, m, d)


def s(d: date) -> str:
    return d.strftime("%Y-%m-%d")


TS = "2027-03-31 18:30:00"          # 素材提交时间戳（课程2 状态日当天）
TS_APR = "2027-04-01 08:00:00"      # 计划起点当日

# ---------- 资源主数据（P001~P010 沿用课程2，P011~P013 为课程3 新增） ----------
RESOURCES = [
    ("P001", "唐明宇", "项目管理办公室", "项目经理", "PM", "项目统筹、进度治理、变更管理", "内部", "正式可用", "课程2 人员工时_2027-03-31"),
    ("P002", "高一川", "信息技术部", "集成负责人", "DG", "主数据迁移、接口集成、数据校验", "内部", "正式可用", "课程2 人员工时_2027-03-31"),
    ("P003", "赵睿", "产品开发部", "开发负责人", "DEV", "平台开发、缺陷修复、移动端", "内部", "正式可用", "课程2 人员工时_2027-03-31"),
    ("P004", "苏槿", "测试与质量部", "测试负责人", "QA", "集成测试、测试方案、缺陷分级", "内部", "正式可用", "课程2 人员工时_2027-03-31"),
    ("P005", "李珊", "业务运营部", "验收与培训负责人", "UAT", "UAT 组织、用户培训、业务演练", "内部", "正式可用", "课程2 人员工时_2027-03-31"),
    ("P006", "叶知行", "架构与安全部", "架构师", "DEV", "架构评审、安全合规", "内部", "正式可用", "课程2 人员工时_2027-03-31"),
    ("P007", "许清和", "数据分析部", "数据分析师", "DG", "指标口径、看板开发、数据核对", "内部", "正式可用", "课程2 人员工时_2027-03-31"),
    ("P008", "林若岚", "项目管理办公室", "需求与文档经理", "DOC", "需求管理、文档编制、交付物归档", "内部", "正式可用", "课程2 人员工时_2027-03-31"),
    ("P009", "周启航", "基础设施部", "运维工程师", "OPS", "环境部署、上线验证、回退演练", "内部", "正式可用", "课程2 人员工时_2027-03-31"),
    ("P010", "王楠", "外部服务商", "测试顾问", "QA", "回归测试、测试用例评审", "外部", "正式可用", "课程2 人员工时_2027-03-31"),
    ("P011", "何嘉悦", "外部服务商", "测试工程师（借调）", "QA", "关键测试支持、自动化脚本", "外部", "待批准", "B02 借调申请"),
    ("P012", "张维汉", "质量与验收部", "质量与验收负责人", "PM", "质量门、UAT 签署、最终验收", "内部", "正式可用", "B01 资源池"),
    ("P013", "李承泽", "上线与切换组", "上线与切换负责人", "OPS", "切换方案、生产切换、上线组织", "内部", "正式可用", "B01 资源池"),
]

# ---------- 活动清单（A401—A427，27 项） ----------
# (activity_id, 名称, task_id, wbs_path, owner_id, discipline, 预测开始(月,日), 工期工作日,
#  里程碑ID, 质量门, 状态, 实际完成率, 保留位（基线由 KEY_CHAIN 独立计算，见 main）)
ACTIVITIES = [
    ("A401", "数据治理遗留问题修复", "T05", "A1 > A11 > A401", "P002", "DG", (4, 1), 3, "", "", "NotStarted", 0, 0),
    ("A402", "主数据复核与确认", "T05", "A1 > A11 > A402", "P002", "DG", (4, 7), 3, "", "", "NotStarted", 0, 0),
    ("A403", "数据治理交付物归档", "T05", "A1 > A11 > A403", "P008", "DG", (4, 12), 2, "", "", "NotStarted", 0, 1),
    ("A404", "流程协同平台缺陷修复", "T06", "A1 > A12 > A404", "P003", "DEV", (4, 1), 5, "", "", "NotStarted", 0, 0),
    ("A405", "流程协同平台回归测试", "T06", "A1 > A12 > A405", "P010", "DEV", (4, 8), 2, "", "", "NotStarted", 0, 1),
    ("A406", "移动端遗留缺陷修复", "T07", "A1 > A13 > A406", "P003", "DEV", (4, 7), 3, "", "", "NotStarted", 0, 0),
    ("A407", "移动端回归测试", "T07", "A1 > A13 > A407", "P010", "DEV", (4, 12), 2, "", "", "NotStarted", 0, 1),
    ("A408", "经营看板指标口径校准", "T08", "A1 > A14 > A408", "P007", "DG", (4, 6), 3, "", "", "NotStarted", 0, 0),
    ("A409", "集成测试方案补充", "T10", "A2 > A21 > A409", "P004", "QA", (4, 1), 2, "", "", "NotStarted", 0, 0),
    ("A410", "集成测试用例补充与执行", "T10", "A2 > A21 > A410", "P004", "QA", (4, 6), 4, "", "", "NotStarted", 0, 1),
    ("A411", "切换方案确认", "T13", "A4 > A41 > A411", "P013", "OPS", (4, 8), 6, "MS-A411", "", "NotStarted", 0, 0),
    ("A412", "环境与系统切换", "T13", "A4 > A41 > A412", "P013", "OPS", (4, 16), 2, "", "", "NotStarted", 0, 1),
    ("A413", "上线验证与回退", "T13", "A4 > A41 > A413", "P009", "OPS", (4, 20), 2, "", "", "NotStarted", 0, 2),
    ("A414", "UAT 用例准备", "T11", "A2 > A22 > A414", "P005", "UAT", (4, 14), 3, "", "", "NotStarted", 0, 1),
    ("A415", "UAT 执行", "T11", "A2 > A22 > A415", "P005", "UAT", (4, 22), 2, "", "", "NotStarted", 0, 4),
    ("A416", "UAT 缺陷修复与复测", "T11", "A2 > A22 > A416", "P003", "UAT", (4, 26), 1, "", "", "NotStarted", 0, 5),
    ("A417", "UAT 签署", "T11", "A2 > A22 > A417", "P012", "UAT", (4, 27), 1, "", "G-UAT", "NotStarted", 0, 6),
    ("A418", "用户培训材料准备", "T12", "A3 > A31 > A418", "P005", "TRN", (4, 19), 3, "", "", "NotStarted", 0, 0),
    ("A419", "用户培训执行", "T12", "A3 > A31 > A419", "P005", "TRN", (5, 5), 3, "", "", "NotStarted", 0, 0),
    ("A420", "文档整理与移交", "T14", "A3 > A32 > A420", "P008", "DOC", (4, 12), 5, "", "", "NotStarted", 0, 0),
    ("A421", "项目文档评审", "T14", "A3 > A32 > A421", "P012", "DOC", (4, 19), 3, "", "", "NotStarted", 0, 0),
    ("A422", "验收准备与证据整理", "T15", "A4 > A43 > A422", "P012", "PM", (4, 28), 1, "", "", "NotStarted", 0, 8),
    ("A423", "生产切换", "T13", "A4 > A42 > A423", "P013", "OPS", (4, 29), 1, "MS-A423", "", "NotStarted", 0, 10),
    ("A424", "试运行观察", "T15", "A4 > A42 > A424", "P009", "OPS", (5, 5), 5, "", "", "NotStarted", 0, 0),
    ("A425", "试运行问题闭环", "T15", "A4 > A42 > A425", "P009", "OPS", (5, 12), 3, "", "", "NotStarted", 0, 0),
    ("A426", "最终验收测试与签署", "T15", "A4 > A43 > A426", "P012", "PM", (4, 30), 1, "", "G-FAT", "NotStarted", 0, 12),
    ("A427", "最终验收", "T15", "A4 > A43 > A427", "P012", "PM", (5, 4), 1, "MS-A427", "", "NotStarted", 0, 14),
]

# ---------- 各专业剩余工作反馈（本地工作项 → 活动映射） ----------
# (discipline, local_id, 本地工作项, activity_id, task_id, 工期估算, 候选资源, 依赖描述, 依赖类型)
A02_ROWS = [
    ("DG", "DG-01", "主数据遗留差异修复", "A401", "T05", 3, "P002", "无（可立即开始）", "已结构化"),
    ("DG", "DG-02", "主数据复核与业务确认", "A402", "T05", 3, "P002;P008", "A401 完成（Finish-to-Start）", "已结构化"),
    ("DG", "DG-03", "数据治理交付物归档", "A403", "T05", 2, "P008", "A402 完成（Finish-to-Start）", "已结构化"),
    ("DG", "DG-04", "经营看板指标口径校准", "A408", "T08", 3, "P007;P004", "需要在集成测试环境可用后开展", "自然语言候选"),
    ("DEV", "DEV-01", "流程协同平台遗留缺陷修复", "A404", "T06", 5, "P003", "无（可立即开始）", "已结构化"),
    ("DEV", "DEV-02", "流程协同平台回归测试", "A405", "T06", 2, "P010", "A404 完成（Finish-to-Start）", "已结构化"),
    ("DEV", "DEV-03", "移动端遗留缺陷修复", "A406", "T07", 3, "P003", "无（可立即开始）", "已结构化"),
    ("DEV", "DEV-04", "移动端回归测试", "A407", "T07", 2, "P010", "A406 完成（Finish-to-Start）", "已结构化"),
    ("QA", "QA-01", "集成测试方案补充", "A409", "T10", 2, "P004", "无（可立即开始）", "已结构化"),
    ("QA", "QA-02", "集成测试用例补充与执行", "A410", "T10", 4, "P004", "A409 完成；缺陷须在 UAT 前闭环", "已结构化"),
    ("UAT", "UAT-01", "UAT 用例准备", "A414", "T11", 3, "P005", "UAT 范围以合同验收条款为准", "自然语言候选"),
    ("UAT", "UAT-02", "UAT 执行", "A415", "T11", 2, "P005", "集成测试通过（M07）后开展", "已结构化"),
    ("UAT", "UAT-03", "UAT 缺陷修复与复测", "A416", "T11", 1, "P003", "A415 完成（Finish-to-Start）", "已结构化"),
    ("UAT", "UAT-04", "UAT 签署", "A417", "T11", 1, "P012", "P1/P2 缺陷为 0 方可签署", "已结构化"),
    ("TRN", "TRN-01", "用户培训材料准备", "A418", "T12", 3, "P005", "无（可立即开始）", "已结构化"),
    ("TRN", "TRN-02", "用户培训执行", "A419", "T12", 3, "P005", "生产切换完成后安排", "自然语言候选"),
    ("OPS", "OPS-01", "切换方案确认", "A411", "T13", 6, "P013;P004", "方案须经技术与运维共同确认", "已结构化"),
    ("OPS", "OPS-02", "环境与系统切换", "A412", "T13", 2, "P013;P009", "A411 完成；受生产窗口限制", "已结构化"),
    ("OPS", "OPS-03", "上线验证与回退", "A413", "T13", 2, "P009", "A412 完成（Finish-to-Start）", "已结构化"),
    ("OPS", "OPS-04", "生产切换", "A423", "T13", 1, "P013;P009", "A422 完成；须在批准窗口内执行", "已结构化"),
    ("OPS", "OPS-05", "试运行观察", "A424", "T15", 5, "P009", "A423 完成（Finish-to-Start）", "已结构化"),
    ("OPS", "OPS-06", "试运行问题闭环", "A425", "T15", 3, "P009", "A424 完成后按问题清单闭环", "自然语言候选"),
    ("DOC", "DOC-01", "文档整理与移交", "A420", "T14", 5, "P008", "无（可立即开始）", "已结构化"),
    ("DOC", "DOC-02", "项目文档评审", "A421", "T14", 3, "P012;P008", "A420 完成（Finish-to-Start）", "已结构化"),
    ("PM", "PM-01", "验收准备与证据整理", "A422", "T15", 1, "P012", "UAT 签署后可开始", "已结构化"),
    ("PM", "PM-02", "最终验收测试与签署", "A426", "T15", 1, "P012", "A423 完成（Finish-to-Start）", "已结构化"),
    ("PM", "PM-03", "最终验收", "A427", "T15", 1, "P012", "A426 完成；验收证据须齐备", "已结构化"),
]

# ---------- 活动资源需求（B01c） ----------
# (activity_id, resource_id, 需求角色, 每日需求小时, 起, 止, 确认状态)
B01C_ROWS = [
    ("A401", "P002", "责任", 4.0, (4, 1), (4, 6), "已确认"),
    ("A402", "P002", "责任", 4.0, (4, 7), (4, 9), "已确认"),
    ("A403", "P008", "责任", 3.0, (4, 12), (4, 13), "已确认"),
    ("A404", "P003", "责任", 5.0, (4, 1), (4, 8), "已确认"),
    ("A405", "P010", "责任", 6.0, (4, 8), (4, 9), "已确认"),
    ("A406", "P003", "责任", 5.0, (4, 7), (4, 9), "已确认"),
    ("A407", "P010", "责任", 6.0, (4, 12), (4, 13), "已确认"),
    # ★ 课件锚点：2027-04-06 三条并发需求合计 10.5h（3.5 + 4.0 + 3.0），可用 8h → 利用率 131%
    ("A408", "P004", "支持", 3.5, (4, 6), (4, 8), "已确认"),
    ("A410", "P004", "责任", 4.0, (4, 6), (4, 9), "已确认"),
    ("A411", "P004", "支持", 3.0, (4, 6), (4, 15), "待确认"),
    ("A409", "P004", "责任", 6.0, (4, 1), (4, 2), "已确认"),
    ("A411", "P013", "责任", 6.0, (4, 8), (4, 15), "已确认"),
    ("A412", "P013", "责任", 7.0, (4, 16), (4, 19), "已确认"),
    ("A412", "P009", "支持", 4.0, (4, 16), (4, 19), "已确认"),
    ("A413", "P009", "责任", 6.0, (4, 20), (4, 21), "已确认"),
    ("A414", "P005", "责任", 4.0, (4, 14), (4, 16), "已确认"),
    ("A415", "P005", "责任", 5.0, (4, 22), (4, 23), "已确认"),
    ("A416", "P003", "责任", 6.0, (4, 26), (4, 26), "已确认"),
    ("A417", "P012", "责任", 3.0, (4, 27), (4, 27), "已确认"),
    ("A418", "P005", "责任", 4.0, (4, 19), (4, 21), "已确认"),
    ("A419", "P005", "责任", 5.0, (5, 5), (5, 7), "已确认"),
    ("A420", "P008", "责任", 5.0, (4, 12), (4, 16), "已确认"),
    ("A421", "P012", "责任", 3.0, (4, 19), (4, 21), "已确认"),
    ("A422", "P012", "责任", 6.0, (4, 28), (4, 28), "已确认"),
    ("A423", "P013", "责任", 8.0, (4, 29), (4, 29), "已确认"),
    ("A423", "P009", "支持", 6.0, (4, 29), (4, 29), "已确认"),
    ("A424", "P009", "责任", 4.0, (5, 5), (5, 11), "已确认"),
    ("A425", "P009", "责任", 4.0, (5, 12), (5, 14), "已确认"),
    ("A426", "P012", "责任", 6.0, (4, 30), (4, 30), "已确认"),
    ("A427", "P012", "责任", 4.0, (5, 4), (5, 4), "已确认"),
]

# 既有承诺（B01b）：(resource_id, 说明, 适用规则)
COMMITMENTS = [
    ("P001", "项目管理例会", "每周一 2 小时"),
    ("P009", "运维值班与发布观察", "每周五 1 小时"),
    ("P012", "其他项目质量评审", "2027-04-19 至 04-21 每日 2 小时"),
    ("P002", "生产数据治理值守", "每周三 2 小时"),
]

WIN_START, WIN_END = dt(2027, 4, 1), dt(2027, 5, 14)
BASE_START = dt(2027, 4, 1)          # 基线链起点（V1 计划起点同日）
# V1 关键路径（课件第 22 页）
KEY_CHAIN = ["A411", "A412", "A413", "A415", "A416", "A417", "A422", "A423", "A426", "A427"]


def w(path: Path, header: list[str], rows: list[list]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(header)
        wr.writerows(rows)
    print(f"  ✓ {path.relative_to(PROJ_ROOT)}  ({len(rows)} 行)")


def main() -> None:
    rmap = {r[0]: r for r in RESOURCES}

    # ---------- 01_计划基线 / A01 项目总控进度计划 ----------
    # 先算「当前预测」日期（课件锚点基准）
    finfo = {}
    for (aid, _n, _t, _w, _o, _d, st, dur, *_rest) in ACTIVITIES:
        fs = dt(2027, st[0], st[1])
        finfo[aid] = {"fs": fs, "ff": add_workdays(fs, dur), "dur": dur}

    # 再算「基线日期」（已批准的控制参照）：关键路径自 BASE_START 起顺序排；
    # 非关键活动取预测日期前移 2 个工作日（不早于 BASE_START）
    base = {}
    cur = BASE_START
    for aid in KEY_CHAIN:
        d = finfo[aid]["dur"]
        base[aid] = (cur, add_workdays(cur, d))
        cur = next_workday(base[aid][1])
    for aid, v in finfo.items():
        if aid in base:
            continue
        bs = shift_back_workdays(v["fs"], 2)
        base[aid] = (max(bs, BASE_START), add_workdays(max(bs, BASE_START), v["dur"]))

    a01 = []
    for (aid, name, task, wbs, owner, disc, st, dur, ms, qg, status, prog, _hint) in ACTIVITIES:
        fs, ff = finfo[aid]["fs"], finfo[aid]["ff"]
        bs, bf = base[aid]
        a01.append([
            PROJECT_ID, aid, task, wbs, name, disc,
            owner, rmap[owner][1],
            "V1", s(bs), s(bf), s(fs), s(ff), dur,
            "是" if ms else "否", ms, qg or "无",
            status, f"{prog}%",
            "已批准" if ms else "待确认",
            "A01 项目总控进度计划", TS, "教学模拟数据",
        ])

    w(OUT_ROOT / "01_计划基线" / "A01_项目总控进度计划.csv",
      ["project_id", "activity_id", "task_id", "wbs_path", "activity_name", "discipline",
       "owner_resource_id", "owner_name", "plan_version", "baseline_start", "baseline_finish",
       "forecast_start", "forecast_finish", "duration_days", "is_milestone", "milestone_id",
       "quality_gate", "status", "actual_progress", "approval_status", "source_material",
       "updated_at", "note"],
      a01)

    # ---------- 01_计划基线 / A02 各专业剩余工作反馈 ----------
    a02 = []
    for (disc, lid, lname, aid, task, dur, cand, dep, dtype) in A02_ROWS:
        a02.append([
            PROJECT_ID, disc, lid, lname, aid, task, dur, cand, dep, dtype,
            "剩余工作量以专业反馈为准，未开工", "各专业负责人", TS,
            "已提交", "教学模拟数据",
        ])
    w(OUT_ROOT / "01_计划基线" / "A02_各专业剩余工作反馈.csv",
      ["project_id", "discipline", "local_id", "local_task_name", "mapped_activity_id",
       "mapped_task_id", "duration_estimate_days", "candidate_resource_ids",
       "dependency_statement", "dependency_type", "remaining_work_note", "source_owner",
       "submitted_at", "approval_status", "note"],
      a02)

    # ---------- 02_资源与日历 / B01a 资源池与能力 ----------
    b01a = [[PROJECT_ID, rid, name, dept, role, disc, skills, 8,
             s(WIN_START), s(WIN_END), etype, rstatus, src, "教学模拟数据"]
            for (rid, name, dept, role, disc, skills, etype, rstatus, src) in RESOURCES]
    w(OUT_ROOT / "02_资源与日历" / "B01a_资源池与能力.csv",
      ["project_id", "resource_id", "resource_name", "department", "role", "discipline",
       "skills", "capacity_hours_per_day", "availability_start", "availability_end",
       "employment_type", "resource_status", "source_material", "note"],
      b01a)

    # ---------- 02_资源与日历 / B01b 资源每日容量与承诺 ----------
    b01b = []
    for (rid, name, *_rest) in RESOURCES:
        for d in workdays_span(WIN_START, WIN_END):
            committed, src = 0.0, ""
            if rid == "P001" and d.weekday() == 0:
                committed, src = 2.0, "项目管理例会"
            elif rid == "P009" and d.weekday() == 4:
                committed, src = 1.0, "运维值班"
            elif rid == "P012" and dt(2027, 4, 19) <= d <= dt(2027, 4, 21):
                committed, src = 2.0, "其他项目质量评审"
            elif rid == "P002" and d.weekday() == 2:
                committed, src = 2.0, "生产数据治理值守"
            b01b.append([PROJECT_ID, rid, s(d), 8.0, committed, 8.0 - committed,
                         src or "无既有承诺", "" if src else "教学模拟数据"])
    w(OUT_ROOT / "02_资源与日历" / "B01b_资源每日容量与承诺.csv",
      ["project_id", "resource_id", "work_date", "capacity_hours", "committed_hours",
       "available_hours", "commitment_source", "note"],
      b01b)

    # ---------- 02_资源与日历 / B01c 活动资源需求 ----------
    b01c = []
    for (aid, rid, role, hrs, a, b, conf) in B01C_ROWS:
        b01c.append([PROJECT_ID, aid, rid, role, hrs, s(dt(2027, a[0], a[1])),
                     s(dt(2027, b[0], b[1])), "A02 各专业剩余工作反馈", conf,
                     "待确认：来自专业反馈的候选资源" if conf == "待确认" else "教学模拟数据"])
    b01c.sort(key=lambda r: (r[1], r[2]))
    w(OUT_ROOT / "02_资源与日历" / "B01c_活动资源需求.csv",
      ["project_id", "activity_id", "resource_id", "demand_role", "demand_hours_per_day",
       "demand_start", "demand_end", "source_material", "confirmation_status", "note"],
      b01c)

    # ---------- 02_资源与日历 / B02 关键测试资源借调申请 ----------
    b02 = [
        [PROJECT_ID, "REQ-2027-011", "P011", "何嘉悦", "测试与质量部", 4.0,
         "2027-04-05", "2027-04-16", "审批中", 0.0,
         "须在 2027-04-06 前完成审批方可计入正式容量", "资源经理", TS,
         "缓解 P004 在 04-06 至 04-08 的多活动并发超载", "姓名已出现但审批未完成，正式容量仍为 0"],
        [PROJECT_ID, "REQ-2027-012", "P010", "王楠", "测试与质量部", 4.0,
         "2027-04-05", "2027-04-16", "已批准", 4.0,
         "远程支持，需项目组确认每日协同时段", "资源经理", TS,
         "为关键测试提供远程支持", "外部顾问已批准，容量可计入 V1"],
    ]
    w(OUT_ROOT / "02_资源与日历" / "B02_关键测试资源借调申请.csv",
      ["project_id", "request_id", "resource_id", "resource_name", "requested_by_department",
       "requested_capacity_hours_per_day", "requested_period_start", "requested_period_end",
       "approval_status", "approved_capacity_hours_per_day", "effective_condition",
       "approver", "submitted_at", "impact_note", "note"],
      b02)

    # ---------- 03_外部条件与协同 / C01 供应商进场计划 ----------
    c01 = [
        [PROJECT_ID, "V-01", "华恒智能设备（虚构）", "现场设备安装与调试",
         "2027-04-12", "2027-04-23", "甲方完成现场电力与网络准备", "已承诺",
         "供应商项目经理", "C01 供应商进场计划", "进场前置条件未确认前不得进入 V1 正式排程"],
        [PROJECT_ID, "V-02", "远景检测服务（虚构）", "第三方检测与出证",
         "2027-04-19", "2027-04-30", "被测系统冻结版本可用", "已承诺",
         "供应商技术负责人", "C01 供应商进场计划", "教学模拟数据"],
    ]
    w(OUT_ROOT / "03_外部条件与协同" / "C01_供应商进场计划.csv",
      ["project_id", "vendor_id", "vendor_name", "scope", "committed_start", "committed_finish",
       "precondition", "commitment_status", "contact_person", "source_material", "note"],
      c01)

    # ---------- 03_外部条件与协同 / C02 生产环境与变更窗口通知 ----------
    c02 = [
        [PROJECT_ID, "W-01", "生产环境变更窗口（第一次）", "生产",
         "2027-04-26", "2027-04-29 22:00", "2027-04-30 02:00",
         "窗口内不得并行执行非本次变更操作", "已发布", "运维管理部门", "2027-03-20 09:00:00",
         "A423 生产切换须在本窗口内完成"],
        [PROJECT_ID, "W-02", "生产环境变更窗口（第二次·备份）", "生产",
         "2027-05-06", "2027-05-07 22:00", "2027-05-08 02:00",
         "须提前 3 个工作日报送材料", "已发布", "运维管理部门", "2027-03-20 09:05:00",
         "若第一次窗口不可用则启用"],
    ]
    w(OUT_ROOT / "03_外部条件与协同" / "C02_生产环境与变更窗口通知.csv",
      ["project_id", "window_id", "window_name", "environment", "material_deadline",
       "window_start", "window_end", "ops_constraint", "notice_status", "issuer",
       "issued_at", "note"],
      c02)

    # ---------- 03_外部条件与协同 / C03 协调会纪要 ----------
    c03 = [
        [PROJECT_ID, "MT-2027-0318", "2027-03-18", "决定", "DEC-01",
         "集成测试缺陷按 P1/P2/P3 分级管理，P1/P2 必须在 UAT 前清零",
         "已决：P1/P2 缺陷不得带入验收", "苏槿", "2027-04-23", "生效中",
         "项目经理、测试负责人、开发负责人", "C03 协调会纪要", "教学模拟数据"],
        [PROJECT_ID, "MT-2027-0318", "2027-03-18", "行动项", "ACT-01",
         "各专业在 3 月 31 日前提交剩余工作反馈与工期估算",
         "各专业负责人提交 A02 反馈", "各专业负责人", "2027-03-31", "已完成",
         "全体", "C03 协调会纪要", "教学模拟数据"],
        [PROJECT_ID, "MT-2027-0325", "2027-03-25", "讨论项", "DISC-01",
         "是否将用户培训调整至生产切换之后执行",
         "讨论中，未形成决定", "李珊", "", "讨论中",
         "项目组、业务方", "C03 协调会纪要", "讨论项不得视为正式决定"],
        [PROJECT_ID, "MT-2027-0325", "2027-03-25", "待决事项", "PEND-01",
         "关键测试资源借调（P011）的审批与投入上限",
         "待资源经理与项目交付部确认", "资源经理", "2027-04-06", "待决",
         "资源经理、测试负责人、项目交付部", "C03 协调会纪要", "未决事项不得当作已获批容量使用"],
        [PROJECT_ID, "MT-2027-0325", "2027-03-25", "决定", "DEC-02",
         "生产切换窗口按运维管理部门的窗口通知执行，不得自行调整",
         "已决：变更须在批准窗口内执行", "唐明宇", "2027-04-29", "生效中",
         "全体", "C03 协调会纪要", "教学模拟数据"],
    ]
    w(OUT_ROOT / "03_外部条件与协同" / "C03_协调会纪要.csv",
      ["project_id", "meeting_id", "meeting_date", "item_type", "item_id", "item_content",
       "conclusion", "owner", "deadline", "status", "participants", "source_material", "note"],
      c03)

    # ---------- 04_动态事件（暂不授权） ----------
    d_root = OUT_ROOT / "04_动态事件（暂不授权）"

    w(d_root / "D01_供应商进场延期通知.csv",
      ["project_id", "event_id", "event_type", "issuer", "issued_at", "vendor_id",
       "original_committed_start", "new_committed_start", "precondition_change",
       "event_authority", "approval_status", "required_action", "note"],
      [[PROJECT_ID, "D01", "供应商进场延期通知", "华恒智能设备（虚构）项目经理",
        "2027-04-05 10:20:00", "V-01", "2027-04-12", "2027-04-19",
        "甲方现场准备时间相应顺延，新增前置条件：现场电力验收单需先行签署",
        "条件生效", "已通知/待甲方确认",
        "保留 C01 原承诺，追加 P010 可用性事件与条件；不直接重算 V1",
        "V1 冻结后由教师发放"]])

    w(d_root / "D02_生产故障支援资源调用通知.csv",
      ["project_id", "event_id", "event_type", "issuer", "issued_at", "resource_id",
       "affected_activity_ids", "effective_start", "effective_end",
       "new_capacity_hours_per_day", "event_authority", "approval_status",
       "required_action", "note"],
      [[PROJECT_ID, "D02", "生产故障支援资源调用通知", "运维管理部门",
        "2027-04-05 14:00:00", "P004", "A408;A410;A411",
        "2027-04-06", "2027-04-07", 2.0,
        "立即生效", "已批准",
        "立即把 P004 在 04-06 至 04-07 的有效容量降为 2 小时/日，并重算冲突",
        "V1 冻结后由教师发放"]])

    w(d_root / "D03_分阶段上线变更申请.csv",
      ["project_id", "event_id", "event_type", "change_id", "issuer", "issued_at",
       "requested_scope", "schedule_impact_days", "cost_impact_value", "cost_currency",
       "event_authority", "approval_status", "required_action", "note"],
      [[PROJECT_ID, "D03", "分阶段上线变更申请", "CHG-CY-2027-004", "业务方",
        "2027-04-05 16:40:00", "生产切换拆分为两阶段执行，第一阶段先上线核心模块",
        4, 45000, "元", "仅情景模拟", "待批准",
        "只创建 S3 情景，记录 +4 工作日与增量成本 45,000 元；不得进入 V1",
        "V1 冻结后由教师发放；成本为估算值"]])

    w(d_root / "D04_计划调整协调会纪要.csv",
      ["project_id", "event_id", "event_type", "meeting_id", "issued_at", "item_type",
       "item_content", "conclusion", "owner", "deadline", "event_authority",
       "approval_status", "required_action", "note"],
      [[PROJECT_ID, "D04", "计划调整协调会纪要", "MT-2027-0405", "2027-04-05 17:30:00",
        "讨论项", "在资源稳定、工期优先、业务分阶段三类方案间比较取舍",
        "已分发，未形成批准决定；建议按 S1/S2/S3 三类情景并行比较",
        "唐明宇", "2027-04-07", "仅形成比对任务", "已分发/无批准决定",
        "比较工期、成本与资源稳定方案，形成待确认事项；不直接修改 V1",
        "V1 冻结后由教师发放"]])

    # ---------- 自检：关键锚点 ----------
    print("\n[自检] 关键路径：预测链逐日衔接 + 基线链单调递增")
    d = {r[1]: r for r in a01}
    prev_ff, prev_bf, ok = None, None, True
    for aid in KEY_CHAIN:
        row = d[aid]
        bs, bf, fs, ff, dur = row[9], row[10], row[11], row[12], row[13]
        m1 = ""
        if prev_ff is not None:
            exp = s(next_workday(dt(*[int(x) for x in prev_ff.split("-")])))
            m1 = "衔接" if fs == exp else f"断档(期望 {exp})"
            ok = ok and fs == exp
        m2 = ""
        if prev_bf is not None:
            m2 = "单调" if bf > prev_bf else "倒挂"
            ok = ok and bf > prev_bf
        print(f"  {aid}  基线 {bs} ~ {bf}   预测 {fs} ~ {ff}   工期 {dur}d   预测[{m1}] 基线[{m2}]")
        prev_ff, prev_bf = ff, bf
    print(f"  → 关键路径预测链{'全部衔接' if ok else '存在断档/倒挂'}")
    print(f"  A427 最终验收 = {d['A427'][12]}（课件锚点 2027-05-04）")
    print(f"  A423 生产切换 = {d['A423'][11]}（课件锚点 2027-04-29）")
    print(f"  A411 工期 {d['A411'][13]}d、预测 {d['A411'][11]} ~ {d['A411'][12]}（课件锚点 6 工作日 04-08 ~ 04-15）")

    # 资源冲突锚点
    per_day = {}
    for (aid, rid, role, hrs, a, b, conf) in B01C_ROWS:
        if rid != "P004":
            continue
        for dd in workdays_span(dt(2027, a[0], a[1]), dt(2027, b[0], b[1])):
            per_day.setdefault(dd, []).append((aid, hrs))
    print("\n  [P004 每日并发需求 vs 可用 8h]")
    for dd in sorted(per_day):
        tot = sum(h for _, h in per_day[dd])
        if tot > 8:
            detail = " + ".join(f"{a}({h})" for a, h in sorted(per_day[dd]))
            print(f"    {s(dd)}  需求 {tot}h  利用率 {tot/8*100:.1f}%   {detail}")
    print("\n完成。输出目录：", OUT_ROOT.relative_to(PROJ_ROOT))


if __name__ == "__main__":
    print(f"生成课程3 模拟数据包 → {OUT_ROOT}")
    main()
