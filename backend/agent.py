"""Agent 编排核心：找、核、写、追 + 四道门 + 授权-停下。

数据链路：文件 -> 证据 -> 事实 -> 判断 -> 行动 -> 记忆沉淀。

关键函数：
- start_analyze / get_job：后台分析项目文件夹（识别类型 + 提取关键信息 + 写入记忆）
- answer：聊天回答（回读工作记忆历史 -> 关键词召回 -> 生成 -> 四道门 -> 敏感信息过滤 -> 记忆）
- build_system_instruction（L1 系统指令）/ build_workflow_instruction（L2 工作流指令）：
  指令三层分层中的静态两层；L3 任务指令由各调用点动态拼入 user message 头部。
- _retrieve：关键词重叠打分召回 + Top-K 截断（上下文边界：规则进 system，事实进 user）。
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
# 指令三层分层：L1 系统指令 / L2 工作流指令 / L3 任务指令。
# L1 + L2 进 system role；L3 由调用点动态拼入 user message 头部。
# ============================================================
def build_system_instruction() -> str:
    """L1 系统指令：身份、原则、权限/风险边界、四道门、授权-停下、输出要求、知识库、约束库。

    内容长期不变，进入 system role。
    """
    return f"""你是一名严谨的项目管理智能助手，服务于上海澄岳智能装备有限公司（课程虚构企业）。

## 身份与原则
- 身份：项目经理的助手，负责「找、核、写、追」，不替代项目经理做决策、不代替授权人表态。
- 原则：事实优先、来源可溯、边界清晰、宁停不编。

## 权限与风险边界
- 只做材料整理与建议，不替任何授权人审批、签章、承诺或对外沟通。
- 涉及财务、合同、人事的结论必须明确标记「需人工复核」。
- 未获授权的材料不读取，未获确认的事项不推定。

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


# ---------- L2 工作流指令：各含步骤 / 校验点 / 输出模板 ----------
_L2_ANALYZE = """## 工作流指令：文件分析（analyze）

### 步骤
1. 读取文件内容，判断文件类型：招标文件 / 投标响应 / 合同及补充协议 / 项目管理计划 / 团队与人员清单 / 干系人清单 / 会议邮件记录 / 财务资料 / 问题风险变更 / 其他。
2. 提取结构化关键信息：事实（facts）、干系人（stakeholders）、财务（finance）、行动项（actions）、冲突（conflicts）。
3. 为每条信息标注状态并保留原文关键句；没有对应内容时对应数组留空 []。

### 校验点
1. 只有文件明确写明的才标 confirmed；合理推测标 provisional；无法确定标 needs_confirmation。
2. 不得编造文件中不存在的人员、金额、日期、联系方式、审批或签章。
3. 财务金额保留原始口径（含税/不含税、当期/累计）。
4. 人名保留原文，疑似错字不要擅自合并。
5. 只输出 JSON，不要输出任何其他文字。

### 输出模板（严格按此 JSON 结构）
{
  "file_type": "招标文件|投标响应|合同及补充协议|项目管理计划|团队与人员清单|干系人清单|会议邮件记录|财务资料|问题风险变更|其他",
  "project_type_hint": "该文件体现的项目类型（如：非标智能装备交付项目）",
  "facts": [
    {"category": "项目|人员|财务|干系人|其他", "field": "字段名", "value": "值", "status": "confirmed|provisional|needs_confirmation", "original_excerpt": "原文关键句"}
  ],
  "stakeholders": [
    {"name": "", "organization": "", "role": "", "influence": "", "concern": "", "channel": "", "frequency": "", "owner": ""}
  ],
  "finance": [
    {"category": "预算|合同|应付|开票|支付|成本", "item": "", "amount": "", "tax_inclusive": "含税|不含税|未说明", "period": "当期|累计|未说明", "note": ""}
  ],
  "actions": [
    {"action": "", "owner": "", "due_date": "", "status": "open", "source": ""}
  ],
  "conflicts": [
    {"category": "", "description": "", "source_a": "", "source_b": ""}
  ]
}
"""

_L2_ANSWER = """## 工作流指令：问答（answer）

### 步骤
1. 读取 user message 中「本次任务指令（L3）」下的「项目事实（关键词召回）」，确认可用材料；同时读取「最近对话历史」以延续上下文。
2. 结合系统指令中的企业知识库与约束库形成结论；材料不足时按「授权-停下」如实说明。
3. 每个关键结论标注来源 [来源: 文件名/章节]。

### 校验点
1. 严格区分「事实 / 推断 / 待确认」，以召回条目自带的状态为准，不把「待确认」当作事实使用。
2. 项目事实段为「未检索到与问题直接相关的事实」时，不得虚构项目事实，只能依据知识库与通用规则回答，并说明未检索到相关事实。
3. 财务金额保留原始口径（含税/不含税、当期/累计）；人名保留原文。
4. 涉及财务/合同/人事的结论标记「需人工复核」。

### 输出模板
1. 直接结论（一句话）
2. 依据（分条列出，逐条带 [来源: 文件名/章节] 与事实状态）
3. 待确认 / 风险（无则写「无」）
4. 建议下一步（可执行动作，含负责人与时间要求）
"""

_L2_DOCGEN = """## 工作流指令：文档生成（docgen）

### 步骤
1. 明确文档类型、读者、用途与时间要求。
2. 从项目事实与长期记忆中取材，逐条对应到来源。
3. 按约束库格式要求生成文档草稿。

### 校验点
1. 不使用无来源的事实；缺失内容显式标注「待补充」。
2. 不生成不存在的人员、联系方式、金额、日期、审批或签章。
3. 财务口径与原文一致（含税/不含税、当期/累计）。

### 输出模板
# 文档标题
## 1. 背景与目的
## 2. 正文（分条，关键结论标注 [来源: 文件名/章节]）
## 3. 待确认事项
## 4. 附件与参考
"""

_WORKFLOW_INSTRUCTIONS = {
    "analyze": _L2_ANALYZE,
    "answer": _L2_ANSWER,
    "docgen": _L2_DOCGEN,
}


def build_workflow_instruction(task_type: str) -> str:
    """L2 工作流指令：按任务类型返回对应的步骤 / 校验点 / 输出模板。

    task_type ∈ {"analyze", "answer", "docgen"}。返回内容拼接在 system role 中 L1 之后。
    """
    if task_type not in _WORKFLOW_INSTRUCTIONS:
        raise ValueError(f"未知工作流类型: {task_type}，应为 analyze/answer/docgen 之一")
    return _WORKFLOW_INSTRUCTIONS[task_type]


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
# 输出模板与校验点已上移 L2（analyze），此处只负责承载文件内容（L3 材料）。
# ============================================================
_ANALYZE_CONTENT = """文件内容：
---
{content}
---"""


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

    # L3 任务指令：本次任务目标 / 材料 / 对象 / 时间要求（拼入 user message 头部）
    l3 = f"""## 本次任务指令（L3）
- 目标：分析该单个项目文件，识别文件类型并提取结构化关键信息
- 材料：文件「{file_name}」（{'已按上限截断' if truncated else '全文'}）
- 对象：该文件本身，不外推到项目其他材料
- 时间要求：只依据文件现有内容作答，不推测文件未记载的时间点"""

    user_msg = f"{l3}\n\n{_ANALYZE_CONTENT.format(content=content)}"
    try:
        raw = llm_client.chat(
            [{"role": "system", "content": build_system_instruction() + "\n\n" + build_workflow_instruction("analyze")},
             {"role": "user", "content": user_msg}],
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
            # L3：简短任务指令（system = L1 + L2(answer)）
            l3 = f"""## 本次任务指令（L3）
- 目标：综合各文件的项目类型提示，判断本项目统一类型
- 材料：{joined}
- 对象：本项目（{total} 个已分析文件）
- 时间要求：立即输出一句话，10 字以内

根据上述材料，综合判断本项目的统一类型（一句话，10 字以内）。"""
            raw = llm_client.chat(
                [{"role": "system", "content": build_system_instruction() + "\n\n" + build_workflow_instruction("answer")},
                 {"role": "user", "content": l3}],
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


# ============================================================
# 检索召回：关键词重叠打分 + Top-K 截断（零新增依赖）
# ============================================================
_KEYWORD_PATTERN = re.compile(r"[\u4e00-\u9fff]{2,}|[A-Za-z]+")

# 各类条目 Top-K 上限
_TOP_K = {"facts": 20, "actions": 10, "finance": 10, "stakeholders": 8, "conflicts": 12}

# 各类条目的打分字段口径
_SCORE_FIELDS = {
    "facts": ("field", "value", "category"),
    "actions": ("action", "owner"),
    "finance": ("item", "category"),
    "stakeholders": ("name", "organization", "role"),
    "conflicts": ("description",),
}


def _keywords(text: str) -> list[str]:
    """提取关键词：长度 ≥2 的连续汉字片段 + 英文单词，去重（保持出现顺序）。"""
    words: list[str] = []
    for m in _KEYWORD_PATTERN.finditer(text or ""):
        w = m.group(0)
        if w not in words:
            words.append(w)
    return words


def _overlap_score(keywords: list[str], text: str) -> int:
    """关键词与条目文本的重叠命中数（score）。

    中文无空格、问句常连写，故命中判定为双向：
    - 正向：关键词作为子串出现在条目文本中（问句「预算」命中字段「项目预算」）；
    - 反向：条目文本中的片段（≥2 汉字片段 / 英文词）整体出现在关键词内
      （问句连写「项目预算是多少」命中字段「预算」）。
    """
    haystack = str(text or "")
    if not haystack:
        return 0
    frags = _keywords(haystack)
    score = 0
    for kw in keywords:
        if kw in haystack or any(frag in kw for frag in frags):
            score += 1
    return score


def _topk(rows: list[dict], keywords: list[str], fields: tuple[str, ...], limit: int) -> list[dict]:
    """返回 score>0 且按 score 降序的前 limit 条（同分保持原顺序）。"""
    scored: list[tuple[int, dict]] = []
    for r in rows:
        text = " ".join(str(r.get(f, "")) for f in fields)
        s = _overlap_score(keywords, text)
        if s > 0:
            scored.append((s, r))
    scored.sort(key=lambda x: -x[0])
    return [r for _, r in scored[:limit]]


def _retrieve(question: str, facts: list[dict], stakeholders: list[dict],
              finance: list[dict], actions: list[dict], conflicts: list[dict]) -> dict:
    """关键词召回与问题相关的条目（facts≤20、actions≤10、finance≤10、stakeholders≤8、conflicts≤12）。

    返回召回后的各表子集；无命中时对应列表为空。
    """
    kws = _keywords(question)
    if not kws:
        return {"facts": [], "stakeholders": [], "finance": [], "actions": [], "conflicts": []}
    return {
        "facts": _topk(facts, kws, _SCORE_FIELDS["facts"], _TOP_K["facts"]),
        "stakeholders": _topk(stakeholders, kws, _SCORE_FIELDS["stakeholders"], _TOP_K["stakeholders"]),
        "finance": _topk(finance, kws, _SCORE_FIELDS["finance"], _TOP_K["finance"]),
        "actions": _topk(actions, kws, _SCORE_FIELDS["actions"], _TOP_K["actions"]),
        "conflicts": _topk(conflicts, kws, _SCORE_FIELDS["conflicts"], _TOP_K["conflicts"]),
    }


_ROLE_CN = {"user": "用户", "assistant": "助手"}


def answer(project_id: int, question: str, session_id: str = "default") -> dict:
    """聊天回答。返回 {answer, sources, stopped}。

    上下文边界：L1（+L2）承载通用规则上下文；user message（L3）承载项目事实上下文
    （召回条目）与当前任务上下文（本次问题 + 工作记忆历史）。
    """
    proj = db.query("SELECT * FROM projects WHERE id=?", (project_id,))
    if not proj:
        return {"answer": "项目不存在。", "sources": [], "stopped": False}

    # 1. 找：先回读工作记忆历史（在写入本条用户消息之前），再做关键词召回
    history = mem.get_working(project_id, session_id, limit=8)
    facts_all = db.query("SELECT * FROM facts WHERE project_id=? ORDER BY id", (project_id,))
    stakeholders_all = db.query("SELECT * FROM stakeholders WHERE project_id=?", (project_id,))
    finance_all = db.query("SELECT * FROM finance WHERE project_id=?", (project_id,))
    actions_all = db.query("SELECT * FROM actions WHERE project_id=?", (project_id,))
    conflicts_all = db.query("SELECT * FROM conflicts WHERE project_id=?", (project_id,))
    longterm = mem.get_longterm_text(project_id)

    recalled = _retrieve(question, facts_all, stakeholders_all, finance_all, actions_all, conflicts_all)
    facts, stakeholders = recalled["facts"], recalled["stakeholders"]
    finance, actions, conflicts = recalled["finance"], recalled["actions"], recalled["conflicts"]

    # 项目事实上下文（召回为空时兜底：不注入项目事实，仅凭知识库与通用规则回答）
    if not (facts or stakeholders or finance or actions or conflicts):
        fact_block = "未检索到与问题直接相关的事实"
    else:
        stake_text = "\n".join(f"- {s['name']}({s['organization']}/{s['role']})" for s in stakeholders) or "（无）"
        fin_text = "\n".join(
            f"- [{f['category']}] {f['item']}: {f['amount']} ({f['tax_inclusive']}/{f['period']}) [来源:{f['source']}]"
            for f in finance) or "（无）"
        act_text = "\n".join(
            f"- {a['action']} 负责人:{a['owner']} 期限:{a['due_date']} 状态:{a['status']}" for a in actions) or "（无）"
        conf_text = "\n".join(f"- [{c['category']}] {c['description']}" for c in conflicts) or "（无）"
        fact_block = f"""### 已确认事实（证据台账，召回 {len(facts)}/{len(facts_all)} 条）
{_facts_to_text(facts)}

### 干系人（召回 {len(stakeholders)}/{len(stakeholders_all)} 条）
{stake_text}

### 财务（召回 {len(finance)}/{len(finance_all)} 条）
{fin_text}

### 行动项（召回 {len(actions)}/{len(actions_all)} 条）
{act_text}

### 冲突/待确认（召回 {len(conflicts)}/{len(conflicts_all)} 条）
{conf_text}

### 长期记忆
{longterm or '（无）'}"""

    history_text = "\n".join(
        f"- {_ROLE_CN.get(h['role'], h['role'])}：{h['content']}" for h in history) or "（无）"

    # L3 任务指令：本次任务目标 / 材料 / 对象 / 时间要求 + 项目事实上下文 + 最近对话历史
    user_msg = f"""## 本次任务指令（L3）
- 目标：回答用户关于本项目的问题，并延续最近对话历史
- 材料：项目事实关键词召回结果 + 长期记忆 + 最近 {len(history)} 条工作记忆
- 对象：项目「{proj[0]['name']}」（类型：{proj[0]['project_type'] or '未识别'}）
- 时间要求：仅基于下述材料作答；材料不足时按「授权-停下」如实说明，不编造

## 项目事实（关键词召回）
{fact_block}

## 最近对话历史
{history_text}

## 用户问题
{question}"""

    # 保存工作记忆（用户消息）——必须在回读历史之后，避免当前问题重复进入上下文
    mem.save_working(project_id, session_id, "user", question)

    # 2-4. 核+写+追：生成回答（system = L1 + L2(answer)）
    try:
        raw = llm_client.chat(
            [{"role": "system", "content": build_system_instruction() + "\n\n" + build_workflow_instruction("answer")},
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
