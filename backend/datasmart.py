"""数据智能与决策引擎：数据接入 / 清洗 / EVM 指标 / 看板 / 预测 / 预警 / 建议。

对齐《项目需求说明书-课程2》F-41~F-62：
- 七类数据源连接（真实目录名 + PPT 概念名 + 关键词三重匹配）
- CSV/XLSX 结构化解析（parsers.parse_table）
- 清洗标准化：进度（%）、金额（元）、日期、状态；缺失/重复/单位异常留痕
- EVM 指标（PV/EV/AC/BAC/SPI/CPI/EAC…）+ 指标溯源（formula / source_ref）
- 多时间节点快照（按 data_date 分组，T1/T2/T3，历史节点不覆盖）
- 预警（阈值触发 + 落到对象/原因/责任人/期限）

设计约束：纯函数 + 守护线程；原始文件只读；所有表操作走 db.execute/db.query。
数据源 CSV/XLSX 常见英文列名（planned_progress / actual_progress / budget_value …），
故列识别同时支持中英文（见 _col / 各指标关键词）。
"""
import json
import re
import threading
import uuid
from pathlib import Path

import db
import parsers

# ------------------------------------------------------------------
# 分类规则：目录名 → 语义标签
# ------------------------------------------------------------------
# 顺序敏感：更具体的目录名规则在前。
# 同时覆盖三类命名：真实数据包目录名（01_工作进度…）、PPT 概念名（计划数据…）、
# 旧关键词（计划/成本/人工质量…），保证向后兼容。
CATEGORY_RULES: list[tuple[tuple[str, ...], str]] = [
    (("工作进度", "计划"), "计划"),
    (("工程与里程碑", "里程碑"), "计划"),
    (("人员与工时", "人工与质量", "人工质量", "人员", "工时", "人力"), "人工质量"),
    (("财务与成本", "成本", "预算", "费用", "支出"), "成本"),
    (("质量与缺陷", "质量检查", "质量", "缺陷", "测试"), "质量检查"),
    (("风险与变更", "风险", "变更", "问题"), "风险"),
    (("采购与交付", "采购", "交付", "供应"), "采购"),
    (("合同",), "合同"),
]

# 保留原 CATEGORIES 常量（键→标签），避免外部引用失效
CATEGORIES = [(k, label) for keys, label in CATEGORY_RULES for k in keys]

TABLE_EXTS = {".csv", ".xlsx"}

_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()
_watch_threads: dict[int, threading.Thread] = {}
_watch_state: dict[int, dict] = {}  # project_id -> {path: mtime}
_watch_lock = threading.Lock()


# ------------------------------------------------------------------
# 通用工具
# ------------------------------------------------------------------
def _extract_date(name: str) -> str:
    m = re.search(r"(\d{4})[-_/]?(\d{2})[-_/]?(\d{2})", name)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.search(r"(\d{4})[-/_](\d{1,2})[-/_](\d{1,2})", name)
    if m:
        y, mo, d = m.group(1), m.group(2), m.group(3)
        return f"{y}-{int(mo):02d}-{int(d):02d}"
    return ""


def _match_category(dir_name: str) -> str | None:
    """目录名匹配语义标签（真实目录名 / PPT 概念名 / 旧关键词）。"""
    for keys, label in CATEGORY_RULES:
        for k in keys:
            if k in dir_name:
                return label
    return None


def _iter_data_files(folder: Path):
    """遍历项目文件夹，yield (category, path)。子目录名含关键词即匹配；无子目录时全目录兜底。"""
    subdirs = [d for d in folder.iterdir() if d.is_dir() and not d.name.startswith(".")]
    if subdirs:
        for d in sorted(subdirs, key=lambda x: x.name):
            cat = _match_category(d.name)
            for f in sorted(d.iterdir(), key=lambda x: x.name):
                if f.is_file() and f.suffix.lower() in TABLE_EXTS:
                    yield cat, f
    else:
        for f in sorted(folder.iterdir(), key=lambda x: x.name):
            if f.is_file() and f.suffix.lower() in TABLE_EXTS:
                yield None, f


def _col(table: dict, *names) -> int | None:
    """在 columns 中模糊找列名（含任一关键词，大小写不敏感），返回索引。

    支持中英文列名：先做小写化子串匹配，兼顾 planned_progress / 计划进度 等。
    """
    cols = table.get("columns", [])
    low = [(str(c) or "").lower() for c in cols]
    for n in names:
        nl = str(n).lower()
        for i, c in enumerate(low):
            if nl and nl in c:
                return i
    return None


def _num(v) -> float | None:
    if v is None:
        return None
    s = str(v).strip().replace(",", "").replace("%", "").replace("￥", "").replace("¥", "").strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _to_ratio(v) -> float | None:
    """把进度/概率值统一为 0~1 的比例（支持 '80%' / 0.8 / 80 / '100.0 %'）。"""
    raw = str(v or "").strip()
    if not raw:
        return None
    n = _num(raw)
    if n is None:
        return None
    if "%" in raw:
        return n / 100.0 if n > 1 else n
    if n <= 1:
        return n
    if n <= 100:
        return n / 100.0
    return None


def _to_percent(v) -> float | None:
    """把进度值统一为百分数（0~100）。"""
    r = _to_ratio(v)
    return None if r is None else round(r * 100, 2)


_DATE_COL_HINT = ("_date", "_finish", "_start", "_delivery", "日期", "截止")
_DATETIME_COL_HINT = ("_at", "时间")


def _norm_date(v: str) -> str:
    """日期标准化：2027/1/31、2027年1月31日 → 2027-01-31；ISO 时间戳保留日期部分。"""
    s = str(v or "").strip()
    if not s:
        return s
    m = re.search(r"(\d{4})\s*[-/年.]\s*(\d{1,2})\s*[-/月.]\s*(\d{1,2})", s)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})[ T]", s)
    if m:
        return m.group(0)[:10]
    return s


# 状态归一化映射（列名关键词 → {原值关键词: 标准值}）
_STATUS_MAPS = [
    (("acceptance", "验收"), {"已验收": "已验收", "验收通过": "已验收", "通过": "已验收",
                              "待验收": "待验收", "未验收": "待验收", "延期": "延期", "逾期": "延期"}),
    (("payment", "付款", "支付"), {"已付款": "已付款", "已支付": "已付款", "paid": "已付款",
                                   "未付款": "未付款", "未支付": "未付款"}),
    (("reopen",), {}),
    (("status", "状态"), {"已完成": "已完成", "完成": "已完成", "done": "已完成", "closed": "已完成",
                          "已关闭": "已关闭", "关闭": "已关闭", "进行中": "进行中",
                          "in progress": "进行中", "未开始": "未开始", "开放": "开放", "open": "开放",
                          "应对中": "应对中", "延期": "延期", "延迟": "延期"}),
]


def _norm_status(col_name: str, value: str) -> str | None:
    """按列名匹配状态映射；无匹配返回 None（不改值）。"""
    cl = col_name.lower()
    v = str(value or "").strip()
    if not v:
        return None
    for keys, mapping in _STATUS_MAPS:
        if any(k in cl for k in keys):
            for k, std in mapping.items():
                if k and k in v.lower():
                    return std
    return None


def _amount_cols(table: dict) -> list[int]:
    """识别金额列索引（中英文）。"""
    keys = ("budget_value", "actual_cost_value", "committed_value", "paid_value",
            "amount_value", "forecast_remaining", "cost_impact_value",
            "金额", "费用", "预算", "成本", "支出", "付款")
    out = []
    for i, c in enumerate(table.get("columns", [])):
        cl = str(c).lower()
        if any(k in cl for k in keys):
            out.append(i)
    return out


def _unit_factor(unit: str) -> tuple[float | None, str]:
    """单位 → (换算系数, 规则)。判不出返回 (None, '')。"""
    u = str(unit or "")
    if "万" in u:
        return 10000.0, "万元转元(×10000)"
    if "千元" in u:
        return 1000.0, "千元转元(×1000)"
    if "元" in u:
        return 1.0, ""
    return None, ""


# ------------------------------------------------------------------
# 标准化（清洗与指标共用同一套规则，避免两处逻辑漂移）
# ------------------------------------------------------------------
def _standardize(table: dict) -> tuple[list[list], list[dict]]:
    """返回 (标准化后的行, 日志列表)。

    日志项：{row_key, field, original, standard, rule, status}
    """
    rows = [list(r) for r in table.get("rows", [])]
    cols = [str(c) for c in table.get("columns", [])]
    logs: list[dict] = []
    amount_idx = set(_amount_cols(table))
    # 每张表的单位列（预算/金额单位）
    unit_idx = [i for i, c in enumerate(cols) if "unit" in c.lower() or "单位" in c]

    def unit_for(r, i) -> str:
        # 优先同一行的单位列；退化到金额列名自带的单位
        for ui in unit_idx:
            if ui < len(r) and str(r[ui]).strip():
                return str(r[ui]).strip()
        return cols[i] if i < len(cols) else ""

    for r in rows:
        row_key = str(r[0]) if r else ""
        for i, c in enumerate(cols):
            if i >= len(r):
                continue
            cl = c.lower()
            val = r[i]
            # 1) 进度列：统一为百分数
            if any(k in cl for k in ("进度", "progress", "完成率", "完成比例")):
                pct = _to_percent(val)
                if pct is not None and str(val).strip() not in (f"{pct:.2f}", f"{pct}"):
                    orig = str(val).strip()
                    std = f"{pct:.2f}"
                    if orig and orig != std:
                        logs.append({"row_key": row_key, "field": c, "original": orig,
                                     "standard": std, "rule": "进度统一为百分数", "status": "auto"})
                    r[i] = std
            # 2) 金额列：统一为元
            if i in amount_idx:
                n = _num(val)
                if n is not None:
                    factor, rule = _unit_factor(unit_for(r, i))
                    if factor is not None:
                        std_val = n * factor
                        if factor != 1.0 or str(val).strip() != f"{std_val:.2f}":
                            logs.append({"row_key": row_key, "field": c, "original": str(val).strip(),
                                         "standard": f"{std_val:.2f}",
                                         "rule": rule or "单位统一为元", "status": "auto"})
                            r[i] = f"{std_val:.2f}"
                    else:
                        logs.append({"row_key": row_key, "field": c, "original": str(val).strip(),
                                     "standard": str(val).strip(),
                                     "rule": "金额单位无法判断，待人工确认", "status": "needs_confirm"})
            # 3) 日期列：标准化
            if any(h in cl for h in _DATE_COL_HINT) and not any(h in cl for h in _DATETIME_COL_HINT):
                nd = _norm_date(val)
                if nd and nd != str(val).strip():
                    logs.append({"row_key": row_key, "field": c, "original": str(val).strip(),
                                 "standard": nd, "rule": "日期标准化 YYYY-MM-DD", "status": "auto"})
                    r[i] = nd
            # 4) 状态列：归一化
            ns = _norm_status(c, val)
            if ns is not None and ns != str(val).strip():
                logs.append({"row_key": row_key, "field": c, "original": str(val).strip(),
                             "standard": ns, "rule": "状态归一化", "status": "auto"})
                r[i] = ns

    # 5) 缺失：主键/关键字段为空
    key_idx = _key_col_index(cols)
    for r in rows:
        for i, c in enumerate(cols):
            if i >= len(r):
                continue
            cl = c.lower()
            if any(k in cl for k in ("_id", "编号", "name", "名称")) and not str(r[i]).strip():
                logs.append({"row_key": str(r[0]) if r else "", "field": c, "original": "",
                             "standard": "", "rule": "关键字段缺失，待人工确认", "status": "needs_confirm"})

    # 6) 重复：按业务主键列判重（而非首列，首列多为快照日期）
    if key_idx is not None:
        seen: set[str] = set()
        for r in rows:
            if key_idx >= len(r):
                continue
            key = str(r[key_idx]).strip()
            if not key:
                continue
            if key in seen:
                logs.append({"row_key": key, "field": cols[key_idx], "original": key,
                             "standard": key, "rule": "重复记录，待人工确认", "status": "needs_confirm"})
            seen.add(key)
    return rows, logs


def _key_col_index(cols: list[str]) -> int | None:
    """业务主键列：优先 *_id（排除 project_id/snapshot_date 等公共列），其次 '编号'。"""
    for i, c in enumerate(cols):
        cl = str(c).lower()
        if cl.endswith("_id") and cl not in ("project_id",):
            return i
    for i, c in enumerate(cols):
        if "编号" in str(c):
            return i
    return None


def _std_rows(table: dict) -> list[list]:
    """按 clean 的规则重放标准化（读时转换，不落盘）。"""
    return _standardize(table)[0]


# ------------------------------------------------------------------
# 1. 数据接入
# ------------------------------------------------------------------
def _log_clean(project_id, snapshot_id, table_name, row_key, field,
               original, standard, rule, source_file, status="auto"):
    db.execute(
        "INSERT INTO clean_logs (project_id, snapshot_id, table_name, row_key, field,"
        " original_value, standard_value, rule, source_file, status, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (project_id, snapshot_id, table_name, row_key, field, str(original), str(standard),
         rule, source_file, status, db.now()),
    )


def ingest(project_id: int) -> dict:
    rows = db.query("SELECT * FROM projects WHERE id=?", (project_id,))
    if not rows:
        return {"error": "项目不存在"}
    folder = Path(rows[0]["folder_path"])
    if not folder.exists():
        return {"error": f"文件夹不存在: {folder}"}

    result = {"loaded": 0, "failed": 0, "missing_field": 0, "unsupported": 0, "files": [],
              "uncategorized": 0}
    for cat, f in _iter_data_files(folder):
        rel = str(f)
        data_date = _extract_date(f.name)
        status = "loaded"
        if f.suffix.lower() not in TABLE_EXTS:  # 理论上不会命中（已过滤）
            status = "unsupported"
        else:
            table = parsers.parse_table(f)
            if table.get("error"):
                status = "parse_failed"
            elif not table.get("columns"):
                status = "missing_field"
        if cat is None:
            result["uncategorized"] += 1
        exist = db.query(
            "SELECT id, revision FROM data_sources WHERE project_id=? AND file_name=? AND folder_path=?",
            (project_id, f.name, str(f.parent)),
        )
        if exist:
            db.execute(
                "UPDATE data_sources SET category=?, data_date=?, status=?, revision=revision+1, loaded_at=? WHERE id=?",
                (cat or exist[0].get("category", "") or "未分类", data_date, status, db.now(), exist[0]["id"]),
            )
            ds_id = exist[0]["id"]
        else:
            ds_id = db.execute(
                "INSERT INTO data_sources (project_id, category, folder_path, file_name, data_date,"
                " status, revision, loaded_at) VALUES (?,?,?,?,?,?,1,?)",
                (project_id, cat or "未分类", str(f.parent), f.name, data_date, status, db.now()),
            )
        key = {"loaded": "loaded", "parse_failed": "failed", "missing_field": "missing_field",
               "unsupported": "unsupported"}[status]
        result[key] += 1
        result["files"].append({"id": ds_id, "file": rel, "category": cat or "未分类", "status": status})
    return result


# ------------------------------------------------------------------
# 2. 清洗
# ------------------------------------------------------------------
def clean(project_id: int, snapshot_id: int, data_date: str | None = None) -> list:
    """对已 loaded 的表做标准化：进度/金额/日期/状态统一，缺失/重复/单位异常留痕。

    原始文件只读，不覆盖、不删除；模糊问题标「待确认」并保留原值。
    """
    sources = _loaded_sources(project_id, data_date)
    for ds in sources:
        path = Path(ds["folder_path"]) / ds["file_name"]
        if not path.exists():
            continue
        table = parsers.parse_table(path)
        if table.get("error") or not table.get("columns"):
            continue
        _, logs = _standardize(table)
        for lg in logs:
            _log_clean(project_id, snapshot_id, ds["file_name"], lg["row_key"], lg["field"],
                       lg["original"], lg["standard"], lg["rule"], ds["file_name"], lg["status"])
    return db.query("SELECT * FROM clean_logs WHERE project_id=? AND snapshot_id=? ORDER BY id",
                    (project_id, snapshot_id))


def _loaded_sources(project_id: int, data_date: str | None = None) -> list[dict]:
    sql = "SELECT * FROM data_sources WHERE project_id=? AND status='loaded'"
    params: tuple = (project_id,)
    if data_date is not None:
        sql += " AND data_date=?"
        params += (data_date,)
    return db.query(sql, params)


def _load_cleaned_tables(project_id: int, data_date: str | None = None) -> list[dict]:
    """读取项目下已 loaded 的表，返回 [{category, file, columns, rows, data_date}]。"""
    out = []
    for ds in _loaded_sources(project_id, data_date):
        path = Path(ds["folder_path"]) / ds["file_name"]
        if not path.exists():
            continue
        table = parsers.parse_table(path)
        if table.get("error") or not table.get("columns"):
            continue
        out.append({"category": ds["category"], "file": ds["file_name"],
                    "columns": table["columns"], "rows": table["rows"], "data_date": ds["data_date"]})
    return out


# ------------------------------------------------------------------
# 3. EVM 指标
# ------------------------------------------------------------------
def _agg_sum(tables: list[dict], *names) -> float | None:
    total, found = 0.0, False
    for t in tables:
        i = _col(t, *names)
        if i is None:
            continue
        for r in _std_rows(t):
            if i < len(r):
                n = _num(r[i])
                if n is not None:
                    total += n
                    found = True
    return total if found else None


def _agg_avg(tables: list[dict], *names) -> float | None:
    vals = []
    for t in tables:
        i = _col(t, *names)
        if i is None:
            continue
        for r in _std_rows(t):
            if i < len(r):
                n = _num(r[i])
                if n is not None:
                    vals.append(n)
    return sum(vals) / len(vals) if vals else None


def _agg_count(tables: list[dict], pred) -> int:
    cnt = 0
    for t in tables:
        for r in _std_rows(t):
            if pred(t, r):
                cnt += 1
    return cnt


def _weighted_value(tables: list[dict], *progress_names) -> float | None:
    """按「预算 × 进度%」逐行加权求和（EVM 的 PV/EV 均以此计算）。

    PV=Σ预算×计划进度%；EV=Σ预算×实际进度%。
    """
    total, found = 0.0, False
    for t in tables:
        bi = _col(t, "budget_value", "预算", "计划价值")
        pi = _col(t, *progress_names)
        if bi is None or pi is None:
            continue
        for r in _std_rows(t):
            b = _num(r[bi]) if bi < len(r) else None
            p = _num(r[pi]) if pi < len(r) else None
            if b is not None and p is not None:
                total += b * p / 100.0
                found = True
    return total if found else None


def _cell(table: dict, row: list, *names) -> str:
    i = _col(table, *names)
    if i is None or i >= len(row):
        return ""
    return str(row[i]).strip()


def compute_metrics(project_id: int, snapshot_id: int, data_date: str | None = None) -> dict:
    tables = _load_cleaned_tables(project_id, data_date)
    plan = [t for t in tables if t["category"] in ("计划", "未分类")]
    cost = [t for t in tables if t["category"] == "成本"]
    hr = [t for t in tables if t["category"] == "人工质量"]
    qual = [t for t in tables if t["category"] == "质量检查"]
    risk = [t for t in tables if t["category"] == "风险"]
    proc = [t for t in tables if t["category"] == "采购"]

    PV = _weighted_value(plan, "planned_progress", "计划进度", "计划完成率")
    EV = _weighted_value(plan, "actual_progress", "实际进度", "完成率")
    AC = _agg_sum(cost, "actual_cost_value", "实际成本", "实际支出") \
        or _agg_sum(plan, "actual_cost_value", "实际成本")
    BAC = _agg_sum(cost, "budget_value", "预算", "总预算") \
        or _agg_sum(plan, "budget_value", "预算", "总预算")
    plan_progress = _agg_avg(plan, "planned_progress", "计划进度", "计划完成率")
    actual_progress = _agg_avg(plan, "actual_progress", "实际进度", "完成率")
    plan_hours = _agg_sum(hr, "planned_hours", "计划工时")
    actual_hours = _agg_sum(hr, "actual_hours", "实际工时")
    overtime_hours = _agg_sum(hr, "overtime_hours", "加班")

    missing: list[str] = []
    results: list[dict] = []

    def save(code, value, formula, source_ref):
        if value is None:
            missing.append(code)
            return
        db.execute(
            "INSERT INTO metrics (project_id, snapshot_id, code, value, formula, source_ref, computed_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (project_id, snapshot_id, code, round(value, 4), formula, source_ref, db.now()),
        )
        results.append({"code": code, "value": round(value, 4), "formula": formula,
                        "source_ref": source_ref})

    # ---- 进度 ----
    save("PV", PV, "PV=Σ计划价值(budget_value)", "01 工作进度")
    save("EV", EV, "EV=Σ预算×实际进度%", "01 工作进度")
    if PV and EV is not None and PV != 0:
        save("SPI", EV / PV, "SPI=EV/PV", "01 工作进度")
    else:
        missing.append("SPI")
    save("progress_plan", plan_progress, "计划进度=计划进度列均值", "01 工作进度")
    save("progress_actual", actual_progress, "实际进度=实际进度列均值", "01 工作进度")
    if plan_progress is not None and actual_progress is not None:
        save("progress_dev", actual_progress - plan_progress, "进度偏差=实际-计划(百分点)", "01 工作进度")
    else:
        missing.append("progress_dev")

    # ---- 成本 ----
    save("AC", AC, "AC=Σ实际成本(actual_cost_value)", "03 财务与成本")
    save("BAC", BAC, "BAC=Σ预算(budget_value)", "03 财务与成本")
    if AC and EV is not None and AC != 0:
        save("CPI", EV / AC, "CPI=EV/AC", "03 财务与成本")
    else:
        missing.append("CPI")
    if BAC is not None and "CPI" in [m["code"] for m in results]:
        cpi = [m["value"] for m in results if m["code"] == "CPI"][0]
        if cpi:
            eac = BAC / cpi
            save("EAC", eac, "EAC=BAC/CPI", "03 财务与成本")
            save("completion_dev", BAC - eac, "完工偏差=BAC-EAC", "03 财务与成本")
        else:
            missing.append("EAC")
    else:
        missing.append("EAC")

    # ---- 人员 ----
    save("plan_hours", plan_hours, "计划工时=Σplanned_hours", "02 人员与工时")
    save("actual_hours", actual_hours, "实际工时=Σactual_hours", "02 人员与工时")
    save("overtime_hours", overtime_hours, "加班工时=Σovertime_hours", "02 人员与工时")
    if plan_hours and actual_hours is not None and plan_hours != 0:
        save("hours_util", actual_hours / plan_hours, "工时利用率=实际/计划工时", "02 人员与工时")
    else:
        missing.append("hours_util")

    # ---- 质量与风险 ----
    high_defects = _agg_count(qual, lambda t, r: (
        _cell(t, r, "severity", "等级", "严重", "级别") in ("P1", "P2", "p1", "p2")
        and "关闭" not in _cell(t, r, "status", "状态")))
    save("high_defects", float(high_defects), "高级缺陷数=P1/P2 且未关闭", "05 质量与缺陷")

    open_risks = _agg_count(risk, lambda t, r: _cell(t, r, "status", "状态") in ("开放", "应对中"))
    save("open_risks", float(open_risks), "开放风险数=状态为开放/应对中", "06 风险与变更")

    risk_scores = []
    for t in risk:
        i = _col(t, "risk_score", "风险分")
        pi = _col(t, "probability", "概率")
        ii = _col(t, "impact_level", "影响")
        for r in _std_rows(t):
            s = _num(r[i]) if (i is not None and i < len(r)) else None
            if s is None and pi is not None and ii is not None:
                p = _to_ratio(r[pi]) if pi < len(r) else None
                im = _num(r[ii]) if ii < len(r) else None
                if p is not None and im is not None:
                    s = p * im
            if s is not None:
                risk_scores.append(s)
    save("risk_score", sum(risk_scores) if risk_scores else None,
         "风险分=Σ(概率×影响)或Σrisk_score", "06 风险与变更")

    # ---- 工程与采购 ----
    delayed_ms = _agg_count(plan, lambda t, r: (
        _cell(t, r, "acceptance_status", "验收状态") in ("延期", "待验收")
        or ("里程碑" in _cell(t, r, "milestone_name", "里程碑") and _cell(t, r, "status", "状态") == "延期")))
    save("delayed_milestones", float(delayed_ms), "延期里程碑数=验收状态延期/待验收", "04 工程与里程碑")

    delayed_po = _agg_count(proc, lambda t, r: (
        (_num(_cell(t, r, "delay_days", "延期天数")) or 0) > 0
        or _cell(t, r, "acceptance_status", "验收状态") in ("延期", "待验收")))
    save("delayed_deliveries", float(delayed_po), "延期交付数=delay_days>0 或验收延期", "07 采购与交付")

    return {"metrics": results, "missing": sorted(set(missing))}


# ------------------------------------------------------------------
# 4. 预测
# ------------------------------------------------------------------
def forecast(project_id: int) -> dict:
    snaps = db.query("SELECT * FROM snapshots WHERE project_id=? ORDER BY id", (project_id,))
    pts = []
    for s in snaps:
        rows = db.query(
            "SELECT value FROM metrics WHERE project_id=? AND snapshot_id=? AND code='progress_actual'",
            (project_id, s["id"]))
        if rows:
            pts.append((s["id"], rows[0]["value"]))
    if len(pts) < 2:
        return {"error": "快照不足 2 个，无法预测", "next_node": "", "predicted": None,
                "slope": None, "confidence": "低", "method": "线性外推(最小二乘)",
                "baseline": "", "limitation": "需要 ≥2 个含实际进度(progress_actual)指标的快照"}
    n = len(pts)
    xs = list(range(n))
    ys = [p[1] for p in pts]
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    slope = sxy / sxx if sxx else 0.0
    intercept = my - slope * mx
    predicted = intercept + slope * n
    ss_res = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys))
    ss_tot = sum((y - my) ** 2 for y in ys)
    r2 = 1 - ss_res / ss_tot if ss_tot else 0.0
    confidence = "高" if r2 > 0.9 else ("中" if r2 > 0.7 else "低")
    last_label = snaps[-1]["node_label"] or f"S{snaps[-1]['id']}"
    # 三维度趋势判断
    direction = "上行" if slope > 0.5 else ("下行" if slope < -0.5 else "持平")
    base_rows = db.query(
        "SELECT value FROM metrics WHERE project_id=? AND snapshot_id=? AND code='progress_plan'",
        (project_id, snaps[-1]["id"]))
    baseline = base_rows[0]["value"] if base_rows else None
    baseline_note = ""
    if baseline is not None:
        if predicted < baseline:
            baseline_note = f"预测进度({predicted:.1f}%)仍低于计划基线({baseline:.1f}%)"
        else:
            baseline_note = f"预测进度({predicted:.1f}%)已达/超计划基线({baseline:.1f}%)"
    return {
        "next_node": f"{last_label}+1",
        "predicted": round(predicted, 2),
        "slope": round(slope, 4),
        "r2": round(r2, 4),
        "confidence": confidence,
        "method": "线性外推(最小二乘)",
        "direction": direction,
        "baseline": f"基于 {n} 个快照的实际进度(progress_actual)序列；{baseline_note}".strip("；"),
        "limitation": "线性假设，节点突变更(范围变更/资源注入)时不适用；预测为参考值，须人工复核",
    }


# ------------------------------------------------------------------
# 5. 预警
# ------------------------------------------------------------------
def detect_alerts(project_id: int, snapshot_id: int, data_date: str | None = None) -> list:
    # 本轮已存在的预警先标记 resolved（重跑视为刷新）
    db.execute("UPDATE alerts SET status='resolved' WHERE project_id=? AND snapshot_id=?",
               (project_id, snapshot_id))
    metrics = {m["code"]: m["value"] for m in db.query(
        "SELECT * FROM metrics WHERE project_id=? AND snapshot_id=?", (project_id, snapshot_id))}
    tables = _load_cleaned_tables(project_id, data_date)
    alerts = []

    def add(alert_type, object_id, object_name, level, source_file, owner="待指派", due_date="待定"):
        aid = db.execute(
            "INSERT INTO alerts (project_id, snapshot_id, object_id, alert_type, object_name,"
            " owner, due_date, level, source_file, status, created_at) VALUES (?,?,?,?,?,?,?,?,?,'open',?)",
            (project_id, snapshot_id, object_id, alert_type, object_name, owner, due_date,
             level, source_file, db.now()))
        alerts.append({"id": aid, "alert_type": alert_type, "object_name": object_name,
                       "level": level, "source_file": source_file})

    # ---- 指标级阈值 ----
    if "SPI" in metrics and metrics["SPI"] < 0.9:
        add("进度滞后", "PROJECT", f"项目整体 SPI={metrics['SPI']:.2f} < 0.9", "high", "EVM 指标")
    if "CPI" in metrics and metrics["CPI"] < 0.9:
        add("成本超支", "PROJECT", f"项目整体 CPI={metrics['CPI']:.2f} < 0.9", "high", "EVM 指标")
    bac = metrics.get("BAC")
    if "EAC" in metrics and bac and metrics["EAC"] > bac:
        add("超预算", "PROJECT", f"EAC({metrics['EAC']:.0f}) > BAC({bac:.0f})", "watch", "EVM 指标")
    if "hours_util" in metrics and metrics["hours_util"] > 1.1:
        add("超负荷", "PROJECT", f"工时利用率 {metrics['hours_util'] * 100:.0f}% > 110%", "watch", "EVM 指标")

    for t in tables:
        cat = t["category"]
        for r in _std_rows(t):
            # 质量：P1/P2 未关闭缺陷
            if cat == "质量检查":
                sev = _cell(t, r, "severity", "等级", "严重", "级别")
                st = _cell(t, r, "status", "状态")
                if sev in ("P1", "P2", "p1", "p2") and "关闭" not in st:
                    add("质量积压", _cell(t, r, "defect_id", "缺陷", "编号") or "UNKNOWN",
                        f"缺陷 {_cell(t, r, 'defect_id')} 级别 {sev}（{st or '未关闭'}）",
                        "high", t["file"], _cell(t, r, "owner", "责任人") or "待指派",
                        _cell(t, r, "closed_date", "计划关闭") or "待定")
            # 风险：高风险分 / 开放高影响
            if cat == "风险":
                st = _cell(t, r, "status", "状态")
                rs = _num(_cell(t, r, "risk_score", "风险分"))
                im = _num(_cell(t, r, "impact_level", "影响"))
                if st in ("开放", "应对中") and ((rs or 0) >= 4 or (im or 0) >= 5):
                    add("高风险", _cell(t, r, "record_id", "记录", "编号") or "UNKNOWN",
                        f"{_cell(t, r, 'category')}：{_cell(t, r, 'description', '描述')}",
                        "high", t["file"], _cell(t, r, "owner", "责任人") or "待指派",
                        _cell(t, r, "due_date", "截止") or "待定")
            # 里程碑：验收延期
            if cat == "计划" and _cell(t, r, "milestone_name", "里程碑"):
                ast = _cell(t, r, "acceptance_status", "验收状态")
                if ast in ("延期",):
                    add("里程碑延期", _cell(t, r, "milestone_id", "里程碑", "编号") or "UNKNOWN",
                        f"里程碑 {_cell(t, r, 'milestone_name')} 验收状态：{ast}",
                        "watch", t["file"], _cell(t, r, "owner", "责任人") or "待指派")
            # 采购：交付延期
            if cat == "采购":
                ddays = _num(_cell(t, r, "delay_days", "延期天数")) or 0
                ast = _cell(t, r, "acceptance_status", "验收状态")
                if ddays > 0 or ast == "延期":
                    add("交付延期", _cell(t, r, "purchase_order_id", "采购", "编号") or "UNKNOWN",
                        f"{_cell(t, r, 'item_name', '物料')} 延期 {int(ddays)} 天（{ast or '未验收'}）",
                        "watch", t["file"], _cell(t, r, "owner", "责任人") or "待指派",
                        _cell(t, r, "actual_or_forecast_delivery", "交付") or "待定")
    return alerts


# ------------------------------------------------------------------
# 6. 决策建议
# ------------------------------------------------------------------
def advise(project_id: int, snapshot_id: int) -> str:
    import llm_client
    alerts = db.query("SELECT * FROM alerts WHERE project_id=? AND snapshot_id=? AND status='open'",
                      (project_id, snapshot_id))
    metrics = db.query("SELECT * FROM metrics WHERE project_id=? AND snapshot_id=?",
                       (project_id, snapshot_id))
    fc = forecast(project_id)
    payload = {
        "metrics": [{"code": m["code"], "value": m["value"]} for m in metrics],
        "alerts": [{"type": a["alert_type"], "object": a["object_name"], "level": a["level"],
                    "owner": a["owner"], "due": a["due_date"]} for a in alerts],
        "forecast": fc,
    }
    sys_prompt = (
        "你是资深项目管理专家。根据给定预警、指标与预测，输出行动草案 JSON："
        '{"advices":[{"anomaly":"异常","evidence":"证据","action":"动作","owner":"责任","due_date":"期限","confirm_point":"确认点"}]}。'
        "只输出 JSON，不要解释。"
    )
    user_prompt = json.dumps(payload, ensure_ascii=False)
    try:
        raw = llm_client.chat(
            [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}])
        data = llm_client.extract_json(raw)
        items = data.get("advices", []) if isinstance(data, dict) else []
    except Exception:
        items = []
    if not items:
        # 兜底：基于预警直接生成草案
        items = [{"anomaly": a["alert_type"] + "：" + a["object_name"],
                  "evidence": f"来源 {a['source_file']}，等级 {a['level']}",
                  "action": "请负责人核实并制定纠偏措施", "owner": a["owner"] or "待指派",
                  "due_date": a["due_date"] or "待定", "confirm_point": "措施落地后指标回归阈值内"}
                 for a in alerts]
        if not items:
            items = [{"anomaly": "当前无活跃预警", "evidence": "指标均在阈值内",
                      "action": "保持现有节奏，持续观测", "owner": "项目经理",
                      "due_date": "待定", "confirm_point": "下一快照指标仍正常"}]
    for it in items:
        db.execute(
            "INSERT INTO advices (project_id, snapshot_id, anomaly, evidence, action, owner,"
            " due_date, confirm_point, status, created_at) VALUES (?,?,?,?,?,?,?,?,'pending_confirm',?)",
            (project_id, snapshot_id, it.get("anomaly", ""), it.get("evidence", ""),
             it.get("action", ""), it.get("owner", "待指派"), it.get("due_date", "待定"),
             it.get("confirm_point", ""), db.now()))
    return json.dumps(items, ensure_ascii=False)


# ------------------------------------------------------------------
# 快照流水线（按 data_date 分组，T1/T2/T3；历史节点不覆盖）
# ------------------------------------------------------------------
def _snapshot_dates(project_id: int) -> list[str]:
    rows = db.query(
        "SELECT DISTINCT data_date FROM data_sources WHERE project_id=? AND data_date!=''"
        " ORDER BY data_date", (project_id,))
    return [r["data_date"] for r in rows]


def _upsert_snapshot(project_id: int, data_date: str, idx: int) -> int:
    existing = db.query("SELECT * FROM snapshots WHERE project_id=? AND data_date=? ORDER BY id",
                        (project_id, data_date))
    if existing:
        sid = existing[0]["id"]
        label = existing[0]["node_label"] or f"T{idx}"
        db.execute("UPDATE snapshots SET revision=revision+1, created_at=? WHERE id=?", (db.now(), sid))
        # 重跑视为刷新：清空本轮派生数据
        db.execute("DELETE FROM metrics WHERE project_id=? AND snapshot_id=?", (project_id, sid))
        db.execute("DELETE FROM clean_logs WHERE project_id=? AND snapshot_id=?", (project_id, sid))
        db.execute("UPDATE alerts SET status='resolved' WHERE project_id=? AND snapshot_id=?",
                   (project_id, sid))
        return sid
    return db.execute(
        "INSERT INTO snapshots (project_id, node_label, data_date, revision, created_at)"
        " VALUES (?,?,?,1,?)", (project_id, f"T{idx}", data_date, db.now()))


def run_pipeline(project_id: int) -> int:
    """数据管道：接入 → 按时间节点分组的清洗/指标/预警。返回最新快照 id。"""
    ingest_result = ingest(project_id)
    if "error" in ingest_result:
        raise RuntimeError(ingest_result["error"])
    dates = _snapshot_dates(project_id)
    if not dates:
        dates = [""]  # 无日期元数据时退化为单快照（使用全部数据源）
    last_sid = None
    for idx, d in enumerate(dates, 1):
        sid = _upsert_snapshot(project_id, d, idx)
        clean(project_id, sid, data_date=d)
        compute_metrics(project_id, sid, data_date=d)
        detect_alerts(project_id, sid, data_date=d)
        last_sid = sid
    return last_sid


# ------------------------------------------------------------------
# 7. 守护线程
# ------------------------------------------------------------------
def _snapshot_fingerprint(project_id: int) -> dict:
    rows = db.query("SELECT * FROM projects WHERE id=?", (project_id,))
    if not rows:
        return {}
    folder = Path(rows[0]["folder_path"])
    fp = {}
    if folder.exists():
        for _, f in _iter_data_files(folder):
            try:
                fp[str(f)] = f.stat().st_mtime
            except OSError:
                continue
    return fp


def watch_loop(project_id: int, interval: int = 5):
    def loop():
        while True:
            import time
            time.sleep(interval)
            try:
                fp = _snapshot_fingerprint(project_id)
                with _watch_lock:
                    prev = _watch_state.get(project_id, {})
                    changed = (set(fp) != set(prev)) or any(fp[k] != prev[k] for k in fp)
                    _watch_state[project_id] = fp
                if changed and prev:  # 首轮只记录基线不触发
                    run_pipeline(project_id)
            except Exception:
                continue

    with _watch_lock:
        if project_id in _watch_threads and _watch_threads[project_id].is_alive():
            return _watch_threads[project_id]
        t = threading.Thread(target=loop, daemon=True, name=f"datasmart-watch-{project_id}")
        _watch_threads[project_id] = t
        _watch_state.setdefault(project_id, _snapshot_fingerprint(project_id))
    t.start()
    return t


def start_watches():
    """FastAPI lifespan 调用：对已有项目各起一个守护线程。"""
    for p in db.query("SELECT id FROM projects"):
        try:
            watch_loop(p["id"])
        except Exception:
            continue


# ------------------------------------------------------------------
# 后台任务
# ------------------------------------------------------------------
def start_run(project_id: int) -> str:
    job_id = uuid.uuid4().hex[:12]
    with _jobs_lock:
        _jobs[job_id] = {"status": "running", "snapshot_id": None, "error": ""}

    def worker():
        try:
            sid = run_pipeline(project_id)
            with _jobs_lock:
                _jobs[job_id]["status"] = "completed"
                _jobs[job_id]["snapshot_id"] = sid
        except Exception as e:
            with _jobs_lock:
                _jobs[job_id]["status"] = "failed"
                _jobs[job_id]["error"] = str(e)

    threading.Thread(target=worker, daemon=True, name=f"datasmart-run-{job_id}").start()
    return job_id


def get_job(job_id: str) -> dict | None:
    with _jobs_lock:
        return dict(_jobs[job_id]) if job_id in _jobs else None
