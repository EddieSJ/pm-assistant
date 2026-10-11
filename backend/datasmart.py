"""数据智能与决策引擎：数据接入 / 清洗 / EVM 指标 / 看板 / 预测 / 预警 / 建议。

纯函数 + 守护线程，不修改原始文件；所有表操作走 db.execute/db.query。
"""
import json
import re
import threading
import uuid
from pathlib import Path

import db
import parsers

# 七类数据目录关键词
CATEGORIES = [
    ("计划", "计划"),
    ("成本", "成本"),
    ("人工质量", "人工质量"),
    ("风险", "风险"),
    ("质量检查", "质量检查"),
    ("采购", "采购"),
    ("合同", "合同"),
]

TABLE_EXTS = {".csv", ".xlsx"}

_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()
_watch_threads: dict[int, threading.Thread] = {}
_watch_state: dict[int, dict] = {}  # project_id -> {path: mtime}
_watch_lock = threading.Lock()


# ---------- 工具 ----------

def _extract_date(name: str) -> str:
    m = re.search(r"(\d{4})(\d{2})(\d{2})", name)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.search(r"(\d{4}-\d{1,2}-\d{1,2})", name)
    if m:
        y, mo, d = m.group(1).split("-")
        return f"{y}-{int(mo):02d}-{int(d):02d}"
    return ""


def _match_category(dir_name: str) -> str | None:
    for key, label in CATEGORIES:
        if key in dir_name:
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
    """在 columns 中模糊找列名（含任一关键词），返回索引。"""
    cols = table.get("columns", [])
    for i, c in enumerate(cols):
        cs = str(c)
        for n in names:
            if n in cs:
                return i
    return None


def _num(v) -> float | None:
    if v is None:
        return None
    s = str(v).strip().replace(",", "").replace("%", "").replace("￥", "").replace("¥", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _log_clean(project_id, snapshot_id, table_name, row_key, field,
               original, standard, rule, source_file, status="auto"):
    db.execute(
        "INSERT INTO clean_logs (project_id, snapshot_id, table_name, row_key, field,"
        " original_value, standard_value, rule, source_file, status, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (project_id, snapshot_id, table_name, row_key, field, str(original), str(standard),
         rule, source_file, status, db.now()),
    )


# ---------- 1. 数据接入 ----------

def ingest(project_id: int) -> dict:
    rows = db.query("SELECT * FROM projects WHERE id=?", (project_id,))
    if not rows:
        return {"error": "项目不存在"}
    folder = Path(rows[0]["folder_path"])
    if not folder.exists():
        return {"error": f"文件夹不存在: {folder}"}

    result = {"loaded": 0, "failed": 0, "missing_field": 0, "unsupported": 0, "files": []}
    for cat, f in _iter_data_files(folder):
        rel = str(f)
        data_date = _extract_date(f.name)
        status = "loaded"
        if f.suffix.lower() not in TABLE_EXTS:
            status = "unsupported"
        else:
            table = parsers.parse_table(f)
            if table.get("error"):
                status = "parse_failed"
            elif not table.get("columns"):
                status = "missing_field"
        # 登记或更新 data_sources（同文件 revision+1）
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


def _amount_unit_factors(table: dict) -> dict[int, tuple]:
    """金额列单位判定（严格列级）：返回 {列索引: (mode, how)}。

    mode: 'wan' 该金额列名含"万" / 'qian' 该金额列名含"千元" / 'row' 按该行备注/单位单元格判断 / None 无依据。
    只依据该金额列自身列名或该行对应的备注/单位单元格，绝不从表内其他金额列连带推断。"""
    cols = [str(c) for c in table.get("columns", [])]
    hint_idx = [i for i, c in enumerate(cols) if any(k in c for k in ("备注", "单位", "说明"))]
    factors = {}
    for i, c in enumerate(cols):
        if not any(k in c for k in ("金额", "费用", "预算", "成本", "支出")):
            continue
        if "万" in c:
            factors[i] = ("wan", "列名含'万'")
        elif "千元" in c:
            factors[i] = ("qian", "列名含'千元'")
        elif hint_idx:
            factors[i] = ("row", "按该行备注/单位单元格判断")
        else:
            factors[i] = (None, "")
    return factors


def _cell_amount_unit(mode, how, row, cols) -> tuple[float | None, str]:
    """返回 (换算系数, 规则文本)；单位无法判断时返回 (None, "")。"""
    if mode == "wan":
        return 10000.0, "万元转元(×10000)"
    if mode == "qian":
        return 1000.0, "千元转元(×1000)"
    if mode == "row":
        hints = "".join(str(row[j]) for j, c in enumerate(cols)
                        if j < len(row) and any(k in str(c) for k in ("备注", "单位", "说明")))
        if "千元" in hints:
            return 1000.0, "千元转元(×1000)"
        if "万" in hints:
            return 10000.0, "万元转元(×10000)"
    return None, ""


# ---------- 2. 清洗 ----------

def clean(project_id: int, snapshot_id: int) -> list:
    """对已 loaded 的表做标准化：人员主数据 / 进度百分数 / 金额元。不改原始文件，只写 clean_logs。"""
    logs_count = 0
    sources = db.query(
        "SELECT * FROM data_sources WHERE project_id=? AND status='loaded'", (project_id,))
    staff_registry: dict[str, list] = {}  # 全项目：姓名 -> [记录]

    for ds in sources:
        path = Path(ds["folder_path"]) / ds["file_name"]
        if not path.exists():
            continue
        table = parsers.parse_table(path)
        if table.get("error") or not table.get("columns"):
            continue
        cols, rows = table["columns"], table["rows"]
        # 金额列单位判定（严格列级）：仅看该金额列名 / 该行备注·单位单元格
        unit_factors = _amount_unit_factors(table)

        # 人员主数据：姓名/编号去重合并
        name_i, emp_i = _col(table, "姓名", "名字"), _col(table, "编号", "工号", "员工号")
        if name_i is not None:
            for r in rows:
                name = str(r[name_i]).strip() if name_i < len(r) else ""
                if not name:
                    continue
                emp = str(r[emp_i]).strip() if (emp_i is not None and emp_i < len(r)) else ""
                staff_registry.setdefault(name, []).append({"emp": emp, "source": ds["file_name"]})

        for r in rows:
            row_key = str(r[0]) if r else ""
            for i, col in enumerate(cols):
                col_s = str(col)
                val = r[i] if i < len(r) else ""
                # 进度统一为百分数
                if any(k in col_s for k in ("进度", "完成率", "完成比例")):
                    n = _num(val)
                    if n is not None:
                        if n <= 1:
                            std = round(n * 100, 2)
                            rule = "比例转百分数(×100)"
                        elif n > 100:
                            std = None
                            rule = ""
                        else:
                            std = round(n, 2)
                            rule = "统一为百分数"
                        if std is not None and abs(std - n) > 1e-9:
                            _log_clean(project_id, snapshot_id, ds["file_name"], row_key, col_s,
                                       val, f"{std:.2f}", rule, ds["file_name"])
                            r[i] = f"{std:.2f}"
                            logs_count += 1
                # 金额统一为元（严格列级单位判定；判不了记 needs_confirm 不改值）
                if i in unit_factors:
                    n = _num(val)
                    if n is not None:
                        mode, how = unit_factors[i]
                        factor, rule = _cell_amount_unit(mode, how, r, cols)
                        if factor is not None:
                            std = n * factor
                            _log_clean(project_id, snapshot_id, ds["file_name"], row_key, col_s,
                                       val, f"{std:.2f}", rule, ds["file_name"])
                            r[i] = f"{std:.2f}"
                            logs_count += 1
                        else:
                            _log_clean(project_id, snapshot_id, ds["file_name"], row_key, col_s,
                                       val, str(val), "单位无法判断，待人工确认", ds["file_name"],
                                       status="needs_confirm")

    # 人员去重合并：同姓名多条 -> 生成稳定人员ID，写合并日志
    for name, recs in staff_registry.items():
        emps = [x["emp"] for x in recs if x["emp"]]
        if len(recs) > 1 and len(set(emps)) > 1:
            pid = f"STAFF-{abs(hash(name)) % 100000:05d}"
            _log_clean(project_id, snapshot_id, "人员主数据", name, "人员ID",
                       "/".join(emps), pid, "同表内姓名/编号去重合并，生成稳定人员ID",
                       recs[0]["source"])
            logs_count += 1

    # 清洗结果缓存到内存（供 compute_metrics 聚合），以 snapshot 为键
    _cleaned_cache[snapshot_id] = {"sources": sources}
    return db.query("SELECT * FROM clean_logs WHERE project_id=? AND snapshot_id=? ORDER BY id",
                    (project_id, snapshot_id))


_cleaned_cache: dict[int, dict] = {}


def _load_cleaned_tables(project_id: int) -> list[dict]:
    """读取项目下已 loaded 的表（清洗逻辑重放），返回 [{category, file, columns, rows}]。"""
    out = []
    for ds in db.query("SELECT * FROM data_sources WHERE project_id=? AND status='loaded'",
                       (project_id,)):
        path = Path(ds["folder_path"]) / ds["file_name"]
        if not path.exists():
            continue
        table = parsers.parse_table(path)
        if table.get("error") or not table.get("columns"):
            continue
        out.append({"category": ds["category"], "file": ds["file_name"],
                    "columns": table["columns"], "rows": table["rows"], "data_date": ds["data_date"]})
    return out


def _std_rows(table: dict) -> list[list]:
    """按 clean 的规则重放标准化（读时转换，不落盘）。单位判定与 clean 同源：严格列级。"""
    rows = [list(r) for r in table["rows"]]
    cols = [str(c) for c in table["columns"]]
    unit_factors = _amount_unit_factors(table)
    for r in rows:
        for i, col in enumerate(cols):
            col_s = str(col)
            val = r[i] if i < len(r) else ""
            if any(k in col_s for k in ("进度", "完成率", "完成比例")):
                n = _num(val)
                if n is not None and n <= 1:
                    r[i] = f"{round(n * 100, 2):.2f}"
                elif n is not None and n <= 100:
                    r[i] = f"{round(n, 2):.2f}"
            if i in unit_factors:
                n = _num(val)
                if n is not None:
                    mode, how = unit_factors[i]
                    factor, rule = _cell_amount_unit(mode, how, r, cols)
                    if factor is not None:
                        r[i] = f"{n * factor:.2f}"
                    # 判不了单位：保持原值（clean 已记 needs_confirm，不改值）
    return rows


# ---------- 3. EVM 指标 ----------

def _sum_column(table: dict, keywords: tuple) -> float | None:
    idx = _col(table, *keywords)
    if idx is None:
        return None
    total, found = 0.0, False
    for r in _std_rows(table):
        if idx < len(r):
            n = _num(r[idx])
            if n is not None:
                total += n
                found = True
    return total if found else None


def _avg_column(table: dict, keywords: tuple) -> float | None:
    idx = _col(table, *keywords)
    if idx is None:
        return None
    vals = []
    for r in _std_rows(table):
        if idx < len(r):
            n = _num(r[idx])
            if n is not None:
                vals.append(n)
    return sum(vals) / len(vals) if vals else None


def compute_metrics(project_id: int, snapshot_id: int) -> dict:
    tables = _load_cleaned_tables(project_id)
    plan_tables = [t for t in tables if t["category"] in ("计划", "未分类")]
    cost_tables = [t for t in tables if t["category"] in ("成本", "未分类")]

    def agg(tlist, fn, *kw):
        vals = [fn(t, kw) for t in tlist]
        vals = [v for v in vals if v is not None]
        return sum(vals) if vals else None

    PV = agg(plan_tables, _sum_column, "计划价值", "PV", "计划工作量", "计划成本")
    EV = agg(plan_tables, _sum_column, "挣值", "EV", "实际完成", "已完成价值", "完成价值")
    AC = agg(cost_tables, _sum_column, "实际成本", "AC", "实际支出", "实际费用")
    BAC = agg(tables, _sum_column, "预算", "BAC", "总预算")
    plan_hours = agg(plan_tables, _sum_column, "计划工时")
    actual_hours = agg(tables, _sum_column, "实际工时")
    plan_progress = agg(plan_tables, _avg_column, "计划进度", "计划完成率")
    actual_progress = agg(tables, _avg_column, "进度", "完成率", "实际进度")

    missing = []
    results = []

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

    if PV is not None and EV is not None and PV != 0:
        save("SPI", EV / PV, "SPI=EV/PV", "计划/成本数据表")
    elif EV is None or PV is None:
        missing.append("SPI")
    if AC is not None and EV is not None and AC != 0:
        save("CPI", EV / AC, "CPI=EV/AC", "计划/成本数据表")
    elif EV is None or AC is None:
        missing.append("CPI")
    if BAC is not None and "CPI" in [m["code"] for m in results]:
        cpi = [m["value"] for m in results if m["code"] == "CPI"][0]
        if cpi != 0:
            save("EAC", BAC / cpi, "EAC=BAC/CPI", "计划/成本数据表")
        else:
            missing.append("EAC")
        if BAC is not None:
            eac = [m["value"] for m in results if m["code"] == "EAC"]
            if eac:
                save("completion_dev", BAC - eac[0], "完工偏差=BAC-EAC", "计划/成本数据表")
    else:
        missing.append("EAC")
    if plan_progress is not None and actual_progress is not None:
        save("progress_dev", actual_progress - plan_progress, "进度偏差=实际-计划(百分点)",
             "计划/成本数据表")
    else:
        missing.append("progress_dev")
    if plan_hours and actual_hours is not None and plan_hours != 0:
        save("hours_util", actual_hours / plan_hours, "工时利用率=实际/计划工时", "计划/成本数据表")
    if actual_progress is not None:
        save("progress_actual", actual_progress, "实际进度%=计划/成本表进度均值", "计划/成本数据表")
    else:
        missing.append("progress_actual")
    # 缺失指标不落 metrics 表（避免污染看板指标与趋势序列），随返回值单独返回
    return {"metrics": results, "missing": sorted(set(missing))}


# ---------- 4. 预测 ----------

def forecast(project_id: int) -> dict:
    snaps = db.query(
        "SELECT * FROM snapshots WHERE project_id=? ORDER BY id", (project_id,))
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
    return {
        "next_node": f"{last_label}+1",
        "predicted": round(predicted, 2),
        "slope": round(slope, 4),
        "r2": round(r2, 4),
        "confidence": confidence,
        "method": "线性外推(最小二乘)",
        "baseline": f"基于 {n} 个快照的实际进度(progress_actual)序列",
        "limitation": "线性假设，节点突变更(范围变更/资源注入)时不适用",
    }


# ---------- 5. 预警 ----------

def detect_alerts(project_id: int, snapshot_id: int) -> list:
    # 本轮已存在的预警先标记 resolved（重跑视为刷新）
    db.execute("UPDATE alerts SET status='resolved' WHERE project_id=? AND snapshot_id=?",
               (project_id, snapshot_id))
    metrics = {m["code"]: m["value"] for m in db.query(
        "SELECT * FROM metrics WHERE project_id=? AND snapshot_id=?", (project_id, snapshot_id))}
    tables = _load_cleaned_tables(project_id)
    alerts = []

    def add(alert_type, object_id, object_name, level, source_file, owner="待指派", due_date="待定"):
        aid = db.execute(
            "INSERT INTO alerts (project_id, snapshot_id, object_id, alert_type, object_name,"
            " owner, due_date, level, source_file, status, created_at) VALUES (?,?,?,?,?,?,?,?,?,'open',?)",
            (project_id, snapshot_id, object_id, alert_type, object_name, owner, due_date,
             level, source_file, db.now()))
        alerts.append({"id": aid, "alert_type": alert_type, "object_name": object_name,
                       "level": level, "source_file": source_file})

    if "SPI" in metrics and metrics["SPI"] < 0.9:
        add("进度滞后", "PROJECT", f"项目整体 SPI={metrics['SPI']:.2f} < 0.9", "high", "EVM 指标")
    if "CPI" in metrics and metrics["CPI"] < 0.9:
        add("成本超支", "PROJECT", f"项目整体 CPI={metrics['CPI']:.2f} < 0.9", "high", "EVM 指标")
    # EAC > BAC
    eac_rows = [m for m in db.query(
        "SELECT * FROM metrics WHERE project_id=? AND snapshot_id=?", (project_id, snapshot_id))
        if m["code"] == "EAC"]
    bac_val = None
    for t in tables:
        v = _sum_column(t, ("预算", "BAC", "总预算"))
        if v:
            bac_val = (bac_val or 0) + v
    if eac_rows and bac_val and eac_rows[0]["value"] > bac_val:
        add("超预算", "PROJECT", f"EAC({eac_rows[0]['value']:.0f}) > BAC({bac_val:.0f})", "watch", "EVM 指标")
    if "hours_util" in metrics and metrics["hours_util"] > 1.1:
        add("超负荷", "PROJECT", f"工时利用率 {metrics['hours_util'] * 100:.0f}% > 110%", "watch", "EVM 指标")
    # P1/P2 缺陷 / 里程碑延期：扫质量检查表与计划表
    for t in tables:
        cat = t["category"]
        for r in _std_rows(t):
            cols = [str(c) for c in t["columns"]]
            for i, c in enumerate(cols):
                v = str(r[i]) if i < len(r) else ""
                if cat == "质量检查" and ("等级" in c or "严重" in c or "级别" in c) and v.strip() in ("P1", "P2", "p1", "p2"):
                    add("质量积压", str(r[0]) if r else "UNKNOWN", f"缺陷 {r[0] if r else ''} 级别 {v.strip()}",
                        "high", t["file"])
                if cat == "计划" and "状态" in c and ("延期" in v or "延迟" in v or "滞后" in v):
                    add("里程碑延期", str(r[0]) if r else "UNKNOWN", f"里程碑 {r[0] if r else ''} {v.strip()}",
                        "watch", t["file"])
    return alerts


# ---------- 6. 决策建议 ----------

def advise(project_id: int, snapshot_id: int) -> str:
    import llm_client
    alerts = db.query("SELECT * FROM alerts WHERE project_id=? AND snapshot_id=? AND status='open'",
                      (project_id, snapshot_id))
    metrics = db.query("SELECT * FROM metrics WHERE project_id=? AND snapshot_id=?",
                       (project_id, snapshot_id))
    fc = forecast(project_id)
    payload = {
        "metrics": [{"code": m["code"], "value": m["value"]} for m in metrics],
        "alerts": [{"type": a["alert_type"], "object": a["object_name"], "level": a["level"]}
                   for a in alerts],
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


# ---------- 快照流水线 ----------

def run_pipeline(project_id: int) -> int:
    ingest_result = ingest(project_id)
    if "error" in ingest_result:
        raise RuntimeError(ingest_result["error"])
    # 快照：revision 递增，历史不覆盖
    last = db.query("SELECT * FROM snapshots WHERE project_id=? ORDER BY id DESC LIMIT 1",
                    (project_id,))
    revision = (last[0]["revision"] + 1) if last else 1
    prev_label = last[0]["node_label"] if last else ""
    node_label = f"T{revision}"
    # data_date 取本轮数据源里最新
    dates = [d["data_date"] for d in db.query(
        "SELECT data_date FROM data_sources WHERE project_id=? AND data_date!=''", (project_id,))]
    data_date = max(dates) if dates else ""
    snapshot_id = db.execute(
        "INSERT INTO snapshots (project_id, node_label, data_date, revision, created_at)"
        " VALUES (?,?,?,?,?)",
        (project_id, node_label, data_date, revision, db.now()))
    clean(project_id, snapshot_id)
    compute_metrics(project_id, snapshot_id)
    detect_alerts(project_id, snapshot_id)
    return snapshot_id


# ---------- 7. 守护线程 ----------

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


# ---------- 后台任务（复用 agent 的 _jobs 进度模式思路） ----------

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
