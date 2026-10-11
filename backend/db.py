"""数据库层：SQLite 建表与连接管理。

贴合 05_当前任务记忆体/memory_schema.json 的结构，
并承载 项目/来源/事实/冲突/行动/干系人/财务/三层记忆/文档/聊天 数据。
"""
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from config import Config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL,
    folder_path  TEXT NOT NULL,
    project_type TEXT DEFAULT '',
    project_code TEXT DEFAULT '',
    description  TEXT DEFAULT '',
    created_at   TEXT DEFAULT '',
    updated_at   TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS sources (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      INTEGER NOT NULL,
    file            TEXT NOT NULL,
    file_type       TEXT DEFAULT '',
    version_or_date TEXT DEFAULT '',
    loaded_at       TEXT DEFAULT '',
    content         TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS facts (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id       INTEGER NOT NULL,
    category         TEXT DEFAULT '',
    field            TEXT NOT NULL,
    value            TEXT DEFAULT '',
    source           TEXT DEFAULT '',
    status           TEXT DEFAULT 'provisional',
    original_excerpt TEXT DEFAULT '',
    created_at       TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS conflicts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER NOT NULL,
    category    TEXT DEFAULT '',
    description TEXT DEFAULT '',
    source_a    TEXT DEFAULT '',
    source_b    TEXT DEFAULT '',
    status      TEXT DEFAULT 'open',
    created_at  TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS actions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    action     TEXT DEFAULT '',
    owner      TEXT DEFAULT '',
    due_date   TEXT DEFAULT '',
    status     TEXT DEFAULT 'open',
    source     TEXT DEFAULT '',
    created_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS stakeholders (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id   INTEGER NOT NULL,
    name         TEXT DEFAULT '',
    organization TEXT DEFAULT '',
    role         TEXT DEFAULT '',
    influence    TEXT DEFAULT '',
    concern      TEXT DEFAULT '',
    channel      TEXT DEFAULT '',
    frequency    TEXT DEFAULT '',
    owner        TEXT DEFAULT '',
    created_at   TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS finance (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id    INTEGER NOT NULL,
    category      TEXT DEFAULT '',
    item          TEXT DEFAULT '',
    amount        TEXT DEFAULT '',
    tax_inclusive TEXT DEFAULT '',
    period        TEXT DEFAULT '',
    source        TEXT DEFAULT '',
    note          TEXT DEFAULT '',
    created_at    TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS memories_working (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    session_id TEXT DEFAULT '',
    role       TEXT DEFAULT '',
    content    TEXT DEFAULT '',
    created_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS memories_task (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    task_id    TEXT DEFAULT '',
    objective  TEXT DEFAULT '',
    as_of_date TEXT DEFAULT '',
    json_data  TEXT DEFAULT '',
    updated_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS memories_longterm (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    key        TEXT DEFAULT '',
    value      TEXT DEFAULT '',
    category   TEXT DEFAULT '',
    status     TEXT DEFAULT 'active',
    note       TEXT DEFAULT '',
    supersedes INTEGER DEFAULT 0,
    created_at TEXT DEFAULT '',
    updated_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS memory_audit (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    memory_id  INTEGER DEFAULT 0,
    action     TEXT DEFAULT '',
    before     TEXT DEFAULT '',
    after      TEXT DEFAULT '',
    reason     TEXT DEFAULT '',
    created_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS documents (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    title      TEXT DEFAULT '',
    version    TEXT DEFAULT 'v1.0',
    file_path  TEXT DEFAULT '',
    created_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    role       TEXT DEFAULT '',
    content    TEXT DEFAULT '',
    sources    TEXT DEFAULT '',
    created_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS data_sources (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER NOT NULL,
    category    TEXT DEFAULT '',
    folder_path TEXT DEFAULT '',
    file_name   TEXT DEFAULT '',
    data_date   TEXT DEFAULT '',
    status      TEXT DEFAULT 'loaded',
    revision    INTEGER DEFAULT 1,
    loaded_at   TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS clean_logs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id     INTEGER NOT NULL,
    snapshot_id    INTEGER DEFAULT 0,
    table_name     TEXT DEFAULT '',
    row_key        TEXT DEFAULT '',
    field          TEXT DEFAULT '',
    original_value TEXT DEFAULT '',
    standard_value TEXT DEFAULT '',
    rule           TEXT DEFAULT '',
    source_file    TEXT DEFAULT '',
    status         TEXT DEFAULT 'auto',
    created_at     TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS snapshots (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    node_label TEXT DEFAULT '',
    data_date  TEXT DEFAULT '',
    revision   INTEGER DEFAULT 1,
    created_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS metrics (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER NOT NULL,
    snapshot_id INTEGER DEFAULT 0,
    code        TEXT DEFAULT '',
    value       REAL DEFAULT 0,
    formula     TEXT DEFAULT '',
    source_ref  TEXT DEFAULT '',
    computed_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS alerts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER NOT NULL,
    snapshot_id INTEGER DEFAULT 0,
    object_id   TEXT DEFAULT '',
    alert_type  TEXT DEFAULT '',
    object_name TEXT DEFAULT '',
    owner       TEXT DEFAULT '',
    due_date    TEXT DEFAULT '',
    level       TEXT DEFAULT 'normal',
    source_file TEXT DEFAULT '',
    status      TEXT DEFAULT 'open',
    created_at  TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS advices (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id    INTEGER NOT NULL,
    snapshot_id   INTEGER DEFAULT 0,
    anomaly       TEXT DEFAULT '',
    evidence      TEXT DEFAULT '',
    action        TEXT DEFAULT '',
    owner         TEXT DEFAULT '',
    due_date      TEXT DEFAULT '',
    confirm_point TEXT DEFAULT '',
    status        TEXT DEFAULT 'pending_confirm',
    created_at    TEXT DEFAULT ''
);

-- ==================================================================
-- 课程3「计划与资源智能调度」实体（F-63 ~ F-90）
-- 设计原则（对齐 PRD 6.2 / N-16 / N-18）：
--   * 稳定 ID 为锚点：activity_id / task_id / resource_id / milestone_id /
--     source_record_id / plan_version / event_id，禁止用姓名、描述或行号做跨表主键；
--   * 原始材料只读，接入结果落库并保留来源；
--   * 版本派生而非覆盖：V1 冻结后追加事件派生 V2 / S1 / S2 / S3，历史版本始终保留。
-- ==================================================================

-- 计划材料接入记录（F-63/F-64）
CREATE TABLE IF NOT EXISTS plan_materials (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id    INTEGER NOT NULL,
    group_code    TEXT DEFAULT '',      -- A 计划基线 / B 资源与日历 / C 外部条件与协同 / D 动态事件
    material_code TEXT DEFAULT '',      -- A01 / B01b / C03 / D02 …
    material_name TEXT DEFAULT '',
    file_path     TEXT DEFAULT '',
    effectiveness TEXT DEFAULT '',      -- 效力定位（基线/预测/专业估算/容量基线/申请/供应商承诺/窗口通知/会议讨论/事件）
    access_mode   TEXT DEFAULT '',      -- 只读接入 / 本期不授权
    issuer        TEXT DEFAULT '',      -- 发布主体（效力四问之一：谁发布）
    effective_at  TEXT DEFAULT '',      -- 何时生效
    approved      INTEGER DEFAULT 0,    -- 是否已获正式批准
    traceable     INTEGER DEFAULT 1,    -- 能否被历史记录追溯
    record_count  INTEGER DEFAULT 0,
    loaded_at     TEXT DEFAULT ''
);

-- 计划活动 / 统一 WBS（F-67/F-68/F-69/F-74）
CREATE TABLE IF NOT EXISTS plan_activities (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id         INTEGER NOT NULL,
    version            TEXT DEFAULT 'V1',
    activity_id        TEXT DEFAULT '',   -- 稳定 ID：A401—A427
    task_id            TEXT DEFAULT '',   -- 父任务 T05—T15
    wbs_path           TEXT DEFAULT '',
    activity_name      TEXT DEFAULT '',
    discipline         TEXT DEFAULT '',
    owner_resource_id  TEXT DEFAULT '',
    owner_name         TEXT DEFAULT '',
    baseline_start     TEXT DEFAULT '',
    baseline_finish    TEXT DEFAULT '',
    forecast_start     TEXT DEFAULT '',
    forecast_finish    TEXT DEFAULT '',
    duration_days      REAL DEFAULT 0,
    is_milestone       TEXT DEFAULT '否',
    milestone_id       TEXT DEFAULT '',
    quality_gate       TEXT DEFAULT '无',
    status             TEXT DEFAULT '',
    actual_progress    TEXT DEFAULT '',
    approval_status    TEXT DEFAULT '',
    source_material    TEXT DEFAULT '',
    local_ids          TEXT DEFAULT '',   -- 映射来源本地编号（如 DG-01），映射而非覆盖（F-69）
    mapping_confirmed  INTEGER DEFAULT 0, -- 映射是否经人工确认
    scheduled_start    TEXT DEFAULT '',   -- 确定性排程结果（F-74）
    scheduled_finish   TEXT DEFAULT '',
    earliest_start     TEXT DEFAULT '',
    latest_start       TEXT DEFAULT '',
    float_days         REAL DEFAULT 0,    -- 总时差（F-82）
    is_critical        INTEGER DEFAULT 0,
    priority           TEXT DEFAULT '',
    updated_at         TEXT DEFAULT ''
);

-- 依赖关系（F-70）
CREATE TABLE IF NOT EXISTS plan_dependencies (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id     INTEGER NOT NULL,
    version        TEXT DEFAULT 'V1',
    predecessor_id TEXT DEFAULT '',
    successor_id   TEXT DEFAULT '',
    dep_type       TEXT DEFAULT 'FS',     -- 默认 Finish-to-Start
    statement      TEXT DEFAULT '',       -- 原始依赖描述（保留自然语言）
    is_structured  INTEGER DEFAULT 1,     -- 0 = 仅为自然语言候选，须人工转结构化
    confirm_status TEXT DEFAULT '待确认',  -- 已确认 / 待确认
    source         TEXT DEFAULT ''
);

-- 资源池（F-71/F-79/F-81）
CREATE TABLE IF NOT EXISTS plan_resources (
    id                              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id                      INTEGER NOT NULL,
    resource_id                     TEXT DEFAULT '',
    resource_name                   TEXT DEFAULT '',
    department                      TEXT DEFAULT '',
    role                            TEXT DEFAULT '',
    discipline                      TEXT DEFAULT '',
    skills                          TEXT DEFAULT '',
    capacity_hours_per_day          REAL DEFAULT 0,
    availability_start              TEXT DEFAULT '',
    availability_end                TEXT DEFAULT '',
    employment_type                 TEXT DEFAULT '',
    resource_status                 TEXT DEFAULT '',
    source_material                 TEXT DEFAULT '',
    approval_status                 TEXT DEFAULT '正式可用', -- 正式可用 / 审批中
    approved_capacity_hours_per_day REAL DEFAULT 0,          -- 申请不等于批准（F-72）
    note                            TEXT DEFAULT ''
);

-- 资源每日容量与承诺（F-79）
CREATE TABLE IF NOT EXISTS plan_resource_capacity (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id               INTEGER NOT NULL,
    resource_id              TEXT DEFAULT '',
    work_date                TEXT DEFAULT '',
    capacity_hours           REAL DEFAULT 0,
    committed_hours          REAL DEFAULT 0,
    available_hours          REAL DEFAULT 0,
    effective_capacity_hours REAL DEFAULT 0,   -- 计入已批准借调/事件后的有效容量
    commitment_source        TEXT DEFAULT '',
    note                     TEXT DEFAULT ''
);

-- 活动资源需求（F-79/F-80/F-81）
CREATE TABLE IF NOT EXISTS plan_activity_demand (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id           INTEGER NOT NULL,
    version              TEXT DEFAULT 'V1',
    activity_id          TEXT DEFAULT '',
    resource_id          TEXT DEFAULT '',
    demand_role          TEXT DEFAULT '',   -- 责任 / 支持
    demand_hours_per_day REAL DEFAULT 0,
    demand_start         TEXT DEFAULT '',
    demand_end           TEXT DEFAULT '',
    source_material      TEXT DEFAULT '',
    confirmation_status  TEXT DEFAULT '已确认',
    note                 TEXT DEFAULT ''
);

-- 计划版本与情景（F-85/F-86/F-87）
CREATE TABLE IF NOT EXISTS plan_versions (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id         INTEGER NOT NULL,
    version            TEXT DEFAULT '',   -- V1 / V2 / S1 / S2 / S3
    kind               TEXT DEFAULT '',   -- 冻结基准 / 派生版本 / 备选情景
    label              TEXT DEFAULT '',
    status             TEXT DEFAULT '',   -- 已冻结 / 情景（未批准）/ 已批准 / 待确认
    basis_event        TEXT DEFAULT '',   -- 派生来源 event_id
    condition          TEXT DEFAULT '',   -- 方案条件
    result_summary     TEXT DEFAULT '',   -- 方案结果
    cost_summary       TEXT DEFAULT '',   -- 方案代价
    schedule_impact_days REAL DEFAULT 0,
    cost_impact_value  REAL DEFAULT 0,
    is_formal          INTEGER DEFAULT 1, -- 0 = 情景（不得视为已批准计划）
    frozen_at          TEXT DEFAULT '',
    created_at         TEXT DEFAULT ''
);

-- 版本快照 / 恢复点（F-85/F-89）
CREATE TABLE IF NOT EXISTS plan_snapshots (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    version    TEXT DEFAULT '',
    payload    TEXT DEFAULT '',   -- 输入快照 + 计算参数 + 日期结果 + 资源分配
    checksum   TEXT DEFAULT '',
    label      TEXT DEFAULT '',
    created_at TEXT DEFAULT ''
);

-- 动态事件（F-86）
CREATE TABLE IF NOT EXISTS plan_events (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id       INTEGER NOT NULL,
    event_id         TEXT DEFAULT '',   -- D01—D04
    event_type       TEXT DEFAULT '',
    issuer           TEXT DEFAULT '',
    issued_at        TEXT DEFAULT '',
    event_authority  TEXT DEFAULT '',   -- 立即生效 / 条件生效 / 仅情景模拟 / 仅形成比对任务
    approval_status  TEXT DEFAULT '',
    required_action  TEXT DEFAULT '',
    payload          TEXT DEFAULT '',
    applied          INTEGER DEFAULT 0,
    derived_version  TEXT DEFAULT '',
    applied_at       TEXT DEFAULT ''
);

-- 冲突预警（F-83/F-84）
CREATE TABLE IF NOT EXISTS plan_conflicts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id    INTEGER NOT NULL,
    version       TEXT DEFAULT 'V1',
    conflict_id   TEXT DEFAULT '',      -- CF-01 …
    conflict_type TEXT DEFAULT '',
    object_id     TEXT DEFAULT '',      -- 对象
    object_name   TEXT DEFAULT '',
    conflict_date TEXT DEFAULT '',      -- 时间
    reason        TEXT DEFAULT '',      -- 原因
    evidence      TEXT DEFAULT '',      -- 证据
    impact        TEXT DEFAULT '',      -- 影响
    options       TEXT DEFAULT '',      -- 备选处理
    owner         TEXT DEFAULT '',      -- 责任人
    pending       TEXT DEFAULT '',      -- 待确认事项
    level         TEXT DEFAULT '预警',
    status        TEXT DEFAULT '未确认', -- 未确认 → 处理中 → 已接受 / 已关闭
    created_at    TEXT DEFAULT '',
    updated_at    TEXT DEFAULT ''
);

-- 人工确认关卡（F-88 / N-19）
CREATE TABLE IF NOT EXISTS plan_confirmations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER NOT NULL,
    version     TEXT DEFAULT 'V1',
    action_type TEXT DEFAULT '',   -- 资源批准 / 正式变更 / 生产切换 / UAT 签署 / 最终验收
    title       TEXT DEFAULT '',
    object_id   TEXT DEFAULT '',
    owner       TEXT DEFAULT '',
    due_date    TEXT DEFAULT '',
    evidence    TEXT DEFAULT '',
    status      TEXT DEFAULT '待确认',
    decided_by  TEXT DEFAULT '',
    decided_at  TEXT DEFAULT '',
    note        TEXT DEFAULT '',
    created_at  TEXT DEFAULT ''
);

-- 证据与审计轨迹（F-89）
CREATE TABLE IF NOT EXISTS plan_evidence (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id     INTEGER NOT NULL,
    version        TEXT DEFAULT 'V1',
    step           TEXT DEFAULT '',   -- 计划闭环九步
    category       TEXT DEFAULT '',
    ref_key        TEXT DEFAULT '',
    original_value TEXT DEFAULT '',
    standard_value TEXT DEFAULT '',
    rule           TEXT DEFAULT '',
    source         TEXT DEFAULT '',
    confirm_status TEXT DEFAULT '',
    created_at     TEXT DEFAULT ''
);

-- 自动停止记录（F-90）
CREATE TABLE IF NOT EXISTS plan_stops (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    version    TEXT DEFAULT 'V1',
    stop_type  TEXT DEFAULT '',   -- 来源不足 / 解析失败 / 关键假设未确认 / 责任动作即将发生
    reason     TEXT DEFAULT '',
    impact     TEXT DEFAULT '',
    ref_key    TEXT DEFAULT '',
    status     TEXT DEFAULT 'open',
    created_at TEXT DEFAULT ''
);

-- 决策支持建议六要素（F-88）
CREATE TABLE IF NOT EXISTS plan_advices (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER NOT NULL,
    version     TEXT DEFAULT 'V1',
    action_type TEXT DEFAULT '',
    object      TEXT DEFAULT '',   -- ① 具体对象
    evidence    TEXT DEFAULT '',   -- ② 证据
    owner       TEXT DEFAULT '',   -- ③ 责任人
    due_date    TEXT DEFAULT '',   -- ④ 期限
    alternative TEXT DEFAULT '',   -- ⑤ 替代方案
    pending     TEXT DEFAULT '',   -- ⑥ 待确认事项
    status      TEXT DEFAULT '草案',
    created_at  TEXT DEFAULT ''
);
"""

_lock = threading.Lock()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(Config.db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with _lock:
        conn = _connect()
        try:
            conn.executescript(_SCHEMA)
            _migrate(conn)
            conn.commit()
        finally:
            conn.close()


def _migrate(conn) -> None:
    """向后兼容的轻量迁移：为已存在的表补充新字段。"""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(documents)").fetchall()]
    if "version" not in cols:
        conn.execute("ALTER TABLE documents ADD COLUMN version TEXT DEFAULT 'v1.0'")
    # 记忆治理（N-11）：长期记忆新增 状态 / 备注 / 取代关系 / 更新时间
    lt_cols = [r[1] for r in conn.execute("PRAGMA table_info(memories_longterm)").fetchall()]
    for name, ddl in (
        ("status", "ALTER TABLE memories_longterm ADD COLUMN status TEXT DEFAULT 'active'"),
        ("note", "ALTER TABLE memories_longterm ADD COLUMN note TEXT DEFAULT ''"),
        ("supersedes", "ALTER TABLE memories_longterm ADD COLUMN supersedes INTEGER DEFAULT 0"),
        ("updated_at", "ALTER TABLE memories_longterm ADD COLUMN updated_at TEXT DEFAULT ''"),
    ):
        if name not in lt_cols:
            conn.execute(ddl)


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def query(sql: str, params: tuple = ()) -> list[dict]:
    """读查询，返回 dict 列表。"""
    conn = _connect()
    try:
        cur = conn.execute(sql, params)
        rows = cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def execute(sql: str, params: tuple = ()) -> int:
    """写操作，返回 lastrowid。"""
    with _lock:
        conn = _connect()
        try:
            cur = conn.execute(sql, params)
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()


init_db()
