"""Agent 编排核心：找、核、写、追 + 四道门 + 授权-停下。

数据链路：文件 -> 证据 -> 事实 -> 判断 -> 行动 -> 记忆沉淀。

关键函数：
- start_analyze / get_job：后台分析项目文件夹（识别类型 + 提取关键信息 + 写入记忆）
- answer：聊天回答（检索事实 -> 生成 -> 四道门 -> 敏感信息过滤 -> 记忆）
"""
import re
import threading
import uuid
from pathlib import Path

import db
import llm_client
import memory as mem
import parsers
from config import Config
from knowledge import constraints_text, knowledge_text

# 后台任务进度（进程内内存态）
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()

MAX_FILE_TEXT = 12000  # 单文件注入 LLM 的文本上限（字符）


# ============================================================
# 系统提示构建（知识库 + 约束库 + 四道门 + 授权-停下）
# ============================================================
def build_system_prompt() -> str:
    return f"""你是一名严谨的项目管理智能助手，服务于上海澄岳智能装备有限公司（课程虚构企业）。

## 企业知识库
{knowledge_text()}

## 文件处理约束库（必须严格遵守）
{constraints_text()}

## 输出纪律（四道门）
你的每一次回答必须依次通过四道门：
1. 事实门：结论必须基于已确认的事实/证据，并标注来源；严格区分「事实 / 推断 / 待确认」。
2. 结构门：结构完整、条理清晰，遵循上述约束库的格式要求。
3. 可用性门：输出可直接用于项目管理决策与执行（可落地）。
4. 风险门：不越权、不替授权审批，财务/合同/人事结论明确标记「需人工复核」。

## 授权-停下机制
遇到以下任一情况，必须主动停下并如实说明，绝不编造：
- 缺关键材料；
- 结论不可验证；
- 权限不足；
- 事项未获确认。

## 输出要求
- 每个关键结论标注来源，格式：[来源: 文件名/章节]。
- 财务金额保留原始口径（含税/不含税、当期/累计）。
- 人名保留原文，疑似错字不得擅自合并。
- 不得生成不存在的人员、联系方式、金额、日期、审批或签章。
"""


# ============================================================
# 敏感信息过滤
# ============================================================
_SENSITIVE = [
    re.compile(r"\b\d{17}[\dXx]\b"),          # 身份证
    re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),  # 手机号
    re.compile(r"\b\d{16,19}\b"),             # 银行卡/长数字
    re.compile(r"sk-[A-Za-z0-9_-]{10,}"),     # API Key 前缀
]


def sanitize(text: str) -> str:
    for pat in _SENSITIVE:
        text = pat.sub("[敏感信息已隐藏]", text)
    return text


# ============================================================
# 单文件分析：LLM 识别类型 + 提取结构化信息
# ============================================================
_ANALYZE_PROMPT = """请分析下面的项目文件，判断其类型并提取关键信息。

文件内容：
---
{content}
---

请严格输出 JSON（不要输出任何其他文字），结构如下：
{{
  "file_type": "招标文件|投标响应|合同及补充协议|项目管理计划|团队与人员清单|干系人清单|会议邮件记录|财务资料|问题风险变更|其他",
  "project_type_hint": "该文件体现的项目类型（如：非标智能装备交付项目）",
  "facts": [
    {{"category": "项目|人员|财务|干系人|其他", "field": "字段名", "value": "值", "status": "confirmed|provisional|needs_confirmation", "original_excerpt": "原文关键句"}}
  ],
  "stakeholders": [
    {{"name": "", "organization": "", "role": "", "influence": "", "concern": "", "channel": "", "frequency": "", "owner": ""}}
  ],
  "finance": [
    {{"category": "预算|合同|应付|开票|支付|成本", "item": "", "amount": "", "tax_inclusive": "含税|不含税|未说明", "period": "当期|累计|未说明", "note": ""}}
  ],
  "actions": [
    {{"action": "", "owner": "", "due_date": "", "status": "open", "source": ""}}
  ],
  "conflicts": [
    {{"category": "", "description": "", "source_a": "", "source_b": ""}}
  ]
}}

严格要求：
1. 只有文件明确写明的才标 confirmed；合理推测标 provisional；无法确定标 needs_confirmation。
2. 不得编造文件中不存在的人员、金额、日期、联系方式、审批或签章。
3. 财务金额保留原始口径（含税/不含税、当期/累计）。
4. 人名保留原文，疑似错字不要擅自合并。
5. 没有对应内容时，对应数组留空 []。"""


def _analyze_single_file(file_path: Path, file_name: str) -> dict:
    """分析单个文件，返回结构化 dict（失败时返回空结构）。"""
    empty = {"file_type": "其他", "project_type_hint": "", "facts": [], "stakeholders": [],
             "finance": [], "actions": [], "conflicts": []}
    try:
        text, ext = parsers.parse_file(file_path)
    except Exception as e:
        return {**empty, "file_type": "解析失败", "conflicts": [
            {"category": "解析", "description": f"文件解析失败: {e}", "source_a": file_name, "source_b": ""}]}
    if not text.strip():
        return {**empty, "file_type": "空文件"}

    truncated = len(text) > MAX_FILE_TEXT
    content = text[:MAX_FILE_TEXT]
    if truncated:
        content += "\n...(内容过长，已截断)"

    prompt = _ANALYZE_PROMPT.format(content=content)
    try:
        raw = llm_client.chat(
            [{"role": "system", "content": build_system_prompt()},
             {"role": "user", "content": prompt}],
            temperature=0.1,
        )
    except Exception as e:
        return {**empty, "file_type": "识别失败", "conflicts": [
            {"category": "识别", "description": f"LLM 调用失败: {e}", "source_a": file_name, "source_b": ""}]}

    data = llm_client.extract_json(raw)
    if not isinstance(data, dict):
        return {**empty, "file_type": "识别结果异常", "conflicts": [
            {"category": "识别", "description": "LLM 返回非 JSON 结构", "source_a": file_name, "source_b": raw[:200]}]}
    # 保证字段齐全
    for k in empty:
        data.setdefault(k, empty[k])
    return data


def _analyze_worker(project_id: int, job_id: str) -> None:
    """后台分析 worker：遍历项目文件夹，逐文件分析，写入各类表与记忆。"""
    def log(msg: str):
        with _jobs_lock:
            if job_id in _jobs:
                _jobs[job_id]["logs"].append(msg)

    proj = db.query("SELECT * FROM projects WHERE id=?", (project_id,))
    if not proj:
        _finish(job_id, "项目不存在", error="项目不存在")
        return
    folder = Path(proj[0]["folder_path"])
    if not folder.exists():
        _finish(job_id, "项目文件夹不存在", error=f"文件夹不存在: {folder}")
        return

    files = [f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in parsers.SUPPORTED_EXTS]
    files.sort(key=lambda f: f.name)
    total = len(files)
    with _jobs_lock:
        _jobs[job_id]["total"] = total
    log(f"发现 {total} 个可解析文件")

    project_type_hints: list[str] = []
    for i, f in enumerate(files, 1):
        with _jobs_lock:
            _jobs[job_id]["current"] = f.name
            _jobs[job_id]["done"] = i - 1
        log(f"[{i}/{total}] 分析 {f.name} ...")
        result = _analyze_single_file(f, f.name)

        # 写入 sources 表（原文留存，用于证据追溯）
        try:
            text, ext = parsers.parse_file(f)
            content = text[:MAX_FILE_TEXT] if text else ""
        except Exception:
            content = ""
        db.execute(
            "INSERT INTO sources (project_id, file, file_type, version_or_date, loaded_at, content) VALUES (?,?,?,?,?,?)",
            (project_id, f.name, result.get("file_type", ""), "", db.now(), content),
        )

        # 写入 facts
        for fact in result.get("facts", []):
            if not fact.get("field"):
                continue
            db.execute(
                "INSERT INTO facts (project_id, category, field, value, source, status, original_excerpt, created_at) VALUES (?,?,?,?,?,?,?,?)",
                (project_id, fact.get("category", ""), fact.get("field", ""), str(fact.get("value", "")),
                 f.name, fact.get("status", "provisional"), fact.get("original_excerpt", ""), db.now()),
            )
        # 写入 stakeholders
        for s in result.get("stakeholders", []):
            if not s.get("name"):
                continue
            db.execute(
                "INSERT INTO stakeholders (project_id, name, organization, role, influence, concern, channel, frequency, owner, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (project_id, s.get("name", ""), s.get("organization", ""), s.get("role", ""), s.get("influence", ""),
                 s.get("concern", ""), s.get("channel", ""), s.get("frequency", ""), s.get("owner", ""), db.now()),
            )
        # 写入 finance
        for fin in result.get("finance", []):
            if not fin.get("item") and not fin.get("amount"):
                continue
            db.execute(
                "INSERT INTO finance (project_id, category, item, amount, tax_inclusive, period, source, note, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (project_id, fin.get("category", ""), fin.get("item", ""), str(fin.get("amount", "")),
                 fin.get("tax_inclusive", ""), fin.get("period", ""), f.name, fin.get("note", ""), db.now()),
            )
        # 写入 actions
        for a in result.get("actions", []):
            if not a.get("action"):
                continue
            db.execute(
                "INSERT INTO actions (project_id, action, owner, due_date, status, source, created_at) VALUES (?,?,?,?,?,?,?)",
                (project_id, a.get("action", ""), a.get("owner", ""), a.get("due_date", ""), a.get("status", "open"),
                 f.name, db.now()),
            )
        # 写入 conflicts
        for c in result.get("conflicts", []):
            db.execute(
                "INSERT INTO conflicts (project_id, category, description, source_a, source_b, status, created_at) VALUES (?,?,?,?,?,?,?)",
                (project_id, c.get("category", ""), c.get("description", ""), c.get("source_a", ""), c.get("source_b", ""),
                 "open", db.now()),
            )

        hint = result.get("project_type_hint", "")
        if hint:
            project_type_hints.append(hint)

    # 综合项目类型判断
    project_type = ""
    if project_type_hints:
        try:
            joined = "；".join(project_type_hints)
            raw = llm_client.chat(
                [{"role": "system", "content": build_system_prompt()},
                 {"role": "user", "content": f"根据以下各文件的项目类型提示，综合判断本项目的统一类型（一句话，10字以内）：{joined}"}],
                temperature=0.1, max_tokens=100,
            )
            project_type = raw.strip().strip('"').strip("。")
        except Exception:
            project_type = project_type_hints[0]

    db.execute("UPDATE projects SET project_type=?, updated_at=? WHERE id=?", (project_type, db.now(), project_id))
    mem.save_longterm(project_id, "项目类型", project_type, "项目")

    # 汇总任务记忆（对齐 schema）
    _rebuild_task_memory(project_id)

    with _jobs_lock:
        _jobs[job_id]["done"] = total
        _jobs[job_id]["status"] = "completed"
        _jobs[job_id]["project_type"] = project_type
    log(f"分析完成，项目类型：{project_type or '未识别'}")


def _finish(job_id: str, msg: str, error: str = "") -> None:
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id]["status"] = "failed"
            _jobs[job_id]["error"] = error or msg
            _jobs[job_id]["logs"].append(msg)


def _rebuild_task_memory(project_id: int) -> None:
    """根据当前项目数据重建任务记忆（对齐 memory_schema.json）。"""
    proj = db.query("SELECT * FROM projects WHERE id=?", (project_id,))
    if not proj:
        return
    facts = db.query("SELECT * FROM facts WHERE project_id=?", (project_id,))
    sources = db.query("SELECT * FROM sources WHERE project_id=?", (project_id,))
    conflicts = db.query("SELECT * FROM conflicts WHERE project_id=?", (project_id,))
    actions = db.query("SELECT * FROM actions WHERE project_id=?", (project_id,))

    data = {
        "task_id": f"project-{project_id}",
        "project_code": proj[0]["project_code"] or proj[0]["name"],
        "objective": "使用私人 Agent 整理项目事实、责任、干系人、会议行动项、财务数据和待确认事项",
        "as_of_date": db.now()[:10],
        "loaded_sources": [
            {"file": s["file"], "version_or_date": s["version_or_date"], "loaded_at": s["loaded_at"]}
            for s in sources
        ],
        "confirmed_facts": [
            {"field": f["field"], "value": f["value"], "source": f["source"], "status": f["status"]}
            for f in facts
        ],
        "conflicts": [{"category": c["category"], "description": c["description"], "source_a": c["source_a"], "source_b": c["source_b"]} for c in conflicts],
        "actions": [{"action": a["action"], "owner": a["owner"], "due_date": a["due_date"], "status": a["status"], "source": a["source"]} for a in actions],
        "outputs": [],
        "next_steps": [],
        "sensitive_data_stored": False,
    }
    mem.save_task_memory(project_id, data["task_id"], data["objective"], data["as_of_date"], data)
    mem.sync_task_memory_to_file(data)


def start_analyze(project_id: int) -> str:
    job_id = str(uuid.uuid4())
    with _jobs_lock:
        _jobs[job_id] = {"status": "running", "total": 0, "done": 0, "current": "", "logs": [], "project_type": ""}
    t = threading.Thread(target=_analyze_worker, args=(project_id, job_id), daemon=True)
    t.start()
    return job_id


def get_job(job_id: str) -> dict | None:
    with _jobs_lock:
        return dict(_jobs[job_id]) if job_id in _jobs else None


# ============================================================
# 聊天：找 -> 核 -> 写 -> 追 -> 四道门
# ============================================================
_SOURCE_PATTERN = re.compile(r"[\w\u4e00-\u9fff]+\.(?:md|docx|xlsx|pdf|txt|doc)\b")


def _extract_sources(text: str) -> list[str]:
    """从回答正文提取实际引用的来源文件（去重，保持出现顺序）。"""
    seen = []
    for m in _SOURCE_PATTERN.finditer(text):
        name = m.group(0)
        if name not in seen:
            seen.append(name)
    return seen


def _facts_to_text(facts: list[dict]) -> str:
    if not facts:
        return "（暂无已确认事实）"
    lines = []
    for f in facts:
        status_map = {"confirmed": "已确认", "provisional": "待核实", "needs_confirmation": "待确认"}
        s = status_map.get(f["status"], f["status"])
        lines.append(f"[{f['category']}] {f['field']}: {f['value']}  【{s}】[来源:{f['source']}]")
    return "\n".join(lines)


def answer(project_id: int, question: str, session_id: str = "default") -> dict:
    """聊天回答。返回 {answer, sources, stopped}。"""
    proj = db.query("SELECT * FROM projects WHERE id=?", (project_id,))
    if not proj:
        return {"answer": "项目不存在。", "sources": [], "stopped": False}

    # 1. 找：检索项目事实 + 长期记忆 + 干系人 + 财务 + 行动项
    facts = db.query("SELECT * FROM facts WHERE project_id=? ORDER BY id", (project_id,))
    longterm = mem.get_longterm_text(project_id)
    stakeholders = db.query("SELECT * FROM stakeholders WHERE project_id=?", (project_id,))
    finance = db.query("SELECT * FROM finance WHERE project_id=?", (project_id,))
    actions = db.query("SELECT * FROM actions WHERE project_id=?", (project_id,))
    conflicts = db.query("SELECT * FROM conflicts WHERE project_id=?", (project_id,))

    stake_text = "\n".join(f"- {s['name']}({s['organization']}/{s['role']})" for s in stakeholders) or "（无）"
    fin_text = "\n".join(f"- [{f['category']}] {f['item']}: {f['amount']} ({f['tax_inclusive']}/{f['period']}) [来源:{f['source']}]" for f in finance) or "（无）"
    act_text = "\n".join(f"- {a['action']} 负责人:{a['owner']} 期限:{a['due_date']} 状态:{a['status']}" for a in actions) or "（无）"
    conf_text = "\n".join(f"- [{c['category']}] {c['description']}" for c in conflicts) or "（无）"

    context = f"""## 项目：{proj[0]['name']}（类型：{proj[0]['project_type'] or '未识别'}）

## 已确认事实（证据台账）
{_facts_to_text(facts)}

## 干系人
{stake_text}

## 财务
{fin_text}

## 行动项
{act_text}

## 冲突/待确认
{conf_text}

## 长期记忆
{longterm or '（无）'}"""

    user_msg = f"{context}\n\n用户问题：{question}"

    # 保存工作记忆（用户消息）
    mem.save_working(project_id, session_id, "user", question)

    # 2-4. 核+写+追：生成回答
    try:
        raw = llm_client.chat(
            [{"role": "system", "content": build_system_prompt()},
             {"role": "user", "content": user_msg}],
        )
    except Exception as e:
        return {"answer": f"调用大模型失败：{e}", "sources": [], "stopped": False}

    answer_text = sanitize(raw)

    # 5. 追：记忆沉淀（保存助手回答到工作记忆 + 聊天记录）
    mem.save_working(project_id, session_id, "assistant", answer_text)
    sources = _extract_sources(answer_text)
    db.execute(
        "INSERT INTO chat_messages (project_id, role, content, sources, created_at) VALUES (?,?,?,?,?)",
        (project_id, "user", question, "", db.now()),
    )
    db.execute(
        "INSERT INTO chat_messages (project_id, role, content, sources, created_at) VALUES (?,?,?,?,?)",
        (project_id, "assistant", answer_text, "；".join(sources), db.now()),
    )

    return {"answer": answer_text, "sources": sources, "stopped": False}
