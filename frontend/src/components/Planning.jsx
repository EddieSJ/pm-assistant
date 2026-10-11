import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'

// 计划与资源智能调度（课程3，F-63 ~ F-90）
// 七类视图 + 治理面板：WBS / 看板 / 甘特 / 资源负荷 / 关键路径 / 冲突预警 / 版本比较
//                      + 输入与效力 / 建议与确认 / 证据与停止

const TABS = [
  { key: 'inputs', label: '输入与效力' },
  { key: 'wbs', label: 'WBS 视图' },
  { key: 'board', label: '任务看板' },
  { key: 'gantt', label: '甘特视图' },
  { key: 'resource', label: '资源负荷' },
  { key: 'critical', label: '关键路径' },
  { key: 'conflict', label: '冲突预警' },
  { key: 'version', label: '版本比较' },
  { key: 'advice', label: '建议与确认' },
  { key: 'evidence', label: '证据与停止' },
]

const CONFLICT_FLOW = ['未确认', '处理中', '已接受', '已关闭']

const EMPTY = '尚未运行计划流程，请先点击「▶ 运行计划流程」'

// ---------- 日期工具 ----------
const DAY = 86400000
const parseD = (s) => {
  if (!s) return null
  const m = String(s).match(/^(\d{4})-(\d{2})-(\d{2})/)
  if (!m) return null
  return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]))
}
const fmtD = (d) => (d ? `${d.getMonth() + 1}/${d.getDate()}` : '—')
const diffDays = (a, b) => Math.round((b - a) / DAY)

// 状态色
const LEVEL_COLOR = { 阻塞: '#fde2e2', 待确认: '#fff3d6', 通过: '#e3f4e8' }
const STATUS_COLOR = {
  NotStarted: '#94a3b8', InProgress: '#2563eb', Done: '#16a34a', Blocked: '#dc2626',
}

export default function Planning() {
  const [projects, setProjects] = useState([])
  const [pid, setPid] = useState(null)
  const [board, setBoard] = useState(null)
  const [tab, setTab] = useState('inputs')
  const [running, setRunning] = useState(false)
  const [msg, setMsg] = useState('')
  const [sel, setSel] = useState(null)          // 选中活动（甘特/看板详情，F-77）
  const [selRes, setSelRes] = useState('P004')  // 资源负荷选中资源

  useEffect(() => {
    api.listProjects().then((ps) => {
      setProjects(ps)
      if (ps.length) setPid(ps[0].id)
    }).catch((e) => setMsg(String(e)))
  }, [])

  const refresh = async (id) => {
    if (!id) return
    try {
      const d = await api.planBoard(id)
      setBoard(d)
      if (!d.empty && d.activities?.length) {
        setSel((s) => s || d.activities.find((a) => a.is_critical === 1) || d.activities[0])
      }
    } catch (e) { setMsg(String(e)) }
  }

  useEffect(() => { if (pid) refresh(pid) /* eslint-disable-next-line */ }, [pid])

  const runPipeline = async () => {
    if (!pid) return
    setRunning(true); setMsg('')
    try {
      const { job_id } = await api.planRun(pid)
      // 轮询直到任务结束；最多等约 72 秒（90 × 800ms）。
      // 关键：不要静默退出循环，否则会把一个「仍在重算」的中间态当成结果展示。
      let done = false
      for (let i = 0; i < 90; i++) {
        await new Promise((r) => setTimeout(r, 800))
        const job = await api.planRunStatus(pid, job_id)
        if (job.status === 'completed') { done = true; break }
        if (job.status === 'failed') throw new Error(job.error || '运行失败')
      }
      if (!done) throw new Error('等待超时（超过 72 秒仍未完成），请稍后重试')
      await refresh(pid)
      setMsg('计划流程运行完成：接入材料 → 效力判定 → 输入检查 → WBS 映射 → 五类约束 → 确定性排程 → 资源冲突 → V1 冻结')
    } catch (e) { setMsg('运行失败: ' + String(e)) } finally { setRunning(false) }
  }

  const setConflict = async (cid, status) => {
    try {
      await api.planSetConflictStatus(pid, cid, status)
      await refresh(pid)
    } catch (e) { setMsg(String(e)) }
  }
  const applyEvent = async (ev) => {
    try {
      const r = await api.planApplyEvent(pid, ev)
      await refresh(pid)
      setMsg(`${ev}（${r.event_authority}）→ ${r.actions.join('；')}`)
      setTab('version')
    } catch (e) { setMsg(String(e)) }
  }

  // ---------- 派生数据 ----------
  const blockedIds = useMemo(() => {
    if (!board || board.empty) return new Set()
    const s = new Set()
    for (const d of (board.dependencies || [])) if (!d.is_structured) { s.add(d.successor_id) }
    for (const c of (board.confirm_status || [])) {
      const m = String(c.object).match(/A\d{3}/g)
      if (m) m.forEach((x) => s.add(x))
    }
    return s
  }, [board])

  const ganttRange = useMemo(() => {
    if (!board || board.empty) return null
    const ds = []
    for (const a of board.activities) {
      [a.baseline_start, a.baseline_finish, a.scheduled_start, a.scheduled_finish,
        a.forecast_start, a.forecast_finish].forEach((x) => { const d = parseD(x); if (d) ds.push(d) })
    }
    if (!ds.length) return null
    const min = new Date(Math.min(...ds)), max = new Date(Math.max(...ds))
    return { min, max, total: diffDays(min, max) + 1 }
  }, [board])

  const workdaySet = useMemo(() => {
    if (!board || board.empty) return new Set()
    return new Set((board.loads || []).map((l) => l.work_date))
  }, [board])

  if (!projects.length) return <div className="plan"><div className="plan-empty">暂无项目，请先在「项目全局管理」创建项目。</div></div>

  return (
    <div className="plan">
      <div className="plan-header">
        <h2>🗓 计划与资源智能调度</h2>
        <div className="plan-controls">
          <select value={pid || ''} onChange={(e) => setPid(Number(e.target.value))}>
            {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
          <button onClick={runPipeline} disabled={running || !pid}>
            {running ? '运行中…' : '▶ 运行计划流程'}
          </button>
        </div>
      </div>
      {msg && <div className="plan-msg">{msg}</div>}

      {(!board || board.empty) && <div className="plan-empty">{board?.message || EMPTY}</div>}

      {board && !board.empty && (
        <>
          <div className="plan-cards">
            <Card num={board.overview.materials_authorized} label={`授权材料 / 共 ${board.overview.materials_count}（${board.overview.materials_pending} 项不授权）`} />
            <Card num={board.overview.activities_count} label={`计划活动（里程碑 ${board.overview.milestones_count}）`} />
            <Card num={board.overview.critical_count} label="关键路径活动" />
            <Card num={board.overview.conflicts_open} label={`未关闭冲突（超载 ${board.overview.resource_over_days} 资源日）`} tone={board.overview.conflicts_open ? 'warn' : ''} />
            <Card num={board.overview.boundary || '—'} label="交付边界（最终验收 A427）" small />
            <Card num={board.overview.plan_start || '—'} label="计划起点" small />
          </div>

          <div className="plan-tabs">
            {TABS.map((t) => (
              <div key={t.key} className={`plan-tab ${tab === t.key ? 'active' : ''}`} onClick={() => setTab(t.key)}>{t.label}</div>
            ))}
          </div>

          {tab === 'inputs' && <InputsTab board={board} />}
          {tab === 'wbs' && <WbsTab board={board} onSelect={setSel} />}
          {tab === 'board' && <BoardTab board={board} blocked={blockedIds} onSelect={setSel} />}
          {tab === 'gantt' && <GanttTab board={board} range={ganttRange} workdays={workdaySet} onSelect={setSel} />}
          {tab === 'resource' && <ResourceTab board={board} rid={selRes} setRid={setSelRes} />}
          {tab === 'critical' && <CriticalTab board={board} onSelect={setSel} />}
          {tab === 'conflict' && <ConflictTab board={board} onSet={setConflict} />}
          {tab === 'version' && <VersionTab board={board} onApplyEvent={applyEvent} />}
          {tab === 'advice' && <AdviceTab board={board} />}
          {tab === 'evidence' && <EvidenceTab board={board} />}

          {sel && (tab === 'gantt' || tab === 'wbs' || tab === 'board' || tab === 'critical') && (
            <ActivityDetail board={board} a={sel} />
          )}
        </>
      )}
    </div>
  )
}

function Card({ num, label, tone = '', small = false }) {
  return (
    <div className={`plan-card ${tone}`}>
      <div className={`num ${small ? 'small' : ''}`}>{num}</div>
      <div className="label">{label}</div>
    </div>
  )
}

// ---------------- 输入与效力（F-63 ~ F-66） ----------------
function InputsTab({ board }) {
  return (
    <div className="plan-panes">
      <div className="plan-pane">
        <h3>输入检查七问（F-66）</h3>
        <table className="plan-table">
          <thead><tr><th>#</th><th>检查</th><th>对象</th><th>发现</th><th>拟处理规则</th><th>待确认</th><th>结论</th></tr></thead>
          <tbody>
            {board.checks.map((c) => (
              <tr key={c.no} style={{ background: LEVEL_COLOR[c.level] || '' }}>
                <td>{c.no}</td><td>{c.check}</td><td>{c.object}</td>
                <td>{c.problem}</td><td>{c.rule}</td><td>{c.pending}</td>
                <td><b>{c.level}</b></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="plan-pane">
        <h3>文件效力分级（F-64）</h3>
        <table className="plan-table">
          <thead><tr><th>效力</th><th>日期类型</th><th>含义</th><th>能否进入 V1</th></tr></thead>
          <tbody>
            {board.effectiveness.levels.map((l) => (
              <tr key={l.date_type}>
                <td><b>{l.strength}</b></td><td>{l.date_type}</td><td>{l.meaning}</td><td>{l.enter_v1}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="plan-pane">
        <h3>效力判定四问（F-65）</h3>
        <table className="plan-table">
          <thead><tr><th>材料</th><th>效力</th><th>谁发布</th><th>何时生效</th><th>是否批准</th><th>能否追溯</th><th>结论</th></tr></thead>
          <tbody>
            {board.effectiveness.four_questions.map((q) => (
              <tr key={q.material_code}>
                <td><b>{q.material_code}</b></td><td>{q.effectiveness}</td><td>{q.q1_issuer}</td>
                <td>{q.q2_effective}</td><td>{q.q3_approved}</td><td>{q.q4_traceable}</td>
                <td>{q.can_enter_v1}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="plan-pane">
        <h3>计划材料接入（F-63）</h3>
        <table className="plan-table">
          <thead><tr><th>组</th><th>编号</th><th>材料</th><th>效力定位</th><th>接入方式</th><th>记录数</th></tr></thead>
          <tbody>
            {board.materials.map((m) => (
              <tr key={m.material_code} style={{ opacity: m.access_mode === '只读接入' ? 1 : 0.55 }}>
                <td>{m.group_code}</td><td><b>{m.material_code}</b></td><td>{m.material_name}</td>
                <td>{m.effectiveness}</td><td>{m.access_mode}</td><td>{m.record_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="plan-pane">
        <h3>五类约束与确认状态（F-71 / F-72）</h3>
        <div className="plan-grid2">
          <table className="plan-table">
            <thead><tr><th>约束</th><th>作用</th><th>内容</th><th>状态</th></tr></thead>
            <tbody>
              {board.constraints.map((c) => (
                <tr key={c.kind}><td><b>{c.kind}</b></td><td>{c.role}</td><td>{c.detail}</td><td>{c.status}</td></tr>
              ))}
            </tbody>
          </table>
          <table className="plan-table">
            <thead><tr><th>对象</th><th>类别</th><th>状态</th><th>说明</th></tr></thead>
            <tbody>
              {board.confirm_status.map((c, i) => (
                <tr key={i} style={{ background: c.status === '待批准' ? LEVEL_COLOR['待确认'] : '' }}>
                  <td>{c.object}</td><td>{c.kind}</td><td><b>{c.status}</b></td><td>{c.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

// ---------------- WBS 视图（F-67 ~ F-69） ----------------
function WbsTab({ board, onSelect }) {
  const depMap = useMemo(() => {
    const m = {}
    for (const d of board.dependencies) (m[d.successor_id] = m[d.successor_id] || []).push(d)
    return m
  }, [board])
  return (
    <div className="plan-pane">
      <h3>统一 WBS：父任务 → 活动 → 交付物（映射而非覆盖）</h3>
      <p className="plan-hint">
        稳定 ID 为锚点：父任务 <code>task_id</code> / 活动 <code>activity_id</code> / 资源 <code>resource_id</code> /
        里程碑 <code>milestone_id</code>；保留专业本地编号，禁止用姓名、描述或行号作跨表主键。
      </p>
      {board.wbs_tree.map((g) => (
        <div key={g.task_id} className="plan-wbs-group">
          <div className="plan-wbs-task">📁 父任务 {g.task_id}（{g.activities.length} 项活动）</div>
          <table className="plan-table">
            <thead>
              <tr>
                <th>活动 ID</th><th>WBS 路径</th><th>名称</th><th>本地编号</th><th>负责人</th>
                <th>基线</th><th>预测</th><th>排程</th><th>工期</th><th>时差</th><th>前置</th><th>质量门</th><th>映射</th>
              </tr>
            </thead>
            <tbody>
              {g.activities.map((a) => (
                <tr key={a.activity_id} onClick={() => onSelect(a)}
                  className={a.is_critical === 1 ? 'plan-crit-row' : ''} style={{ cursor: 'pointer' }}>
                  <td><b>{a.activity_id}</b></td>
                  <td className="plan-mono">{a.wbs_path}</td>
                  <td>{a.activity_name}{a.is_milestone === '是' ? ' ◆' : ''}</td>
                  <td>{a.local_ids || '—'}</td>
                  <td>{a.owner_resource_id} {a.owner_name}</td>
                  <td>{a.baseline_start} ~ {a.baseline_finish}</td>
                  <td>{a.forecast_start} ~ {a.forecast_finish}</td>
                  <td><b>{a.scheduled_start} ~ {a.scheduled_finish}</b></td>
                  <td>{a.duration_days}d</td>
                  <td>{a.float_days}</td>
                  <td>{(depMap[a.activity_id] || []).map((d) => d.predecessor_id).join(',') || '—'}</td>
                  <td>{a.quality_gate !== '无' ? <b>{a.quality_gate}</b> : '—'}</td>
                  <td>{a.mapping_confirmed ? '已确认' : <span className="plan-badge warn">待确认</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  )
}

// ---------------- 任务看板（F-76） ----------------
function BoardTab({ board, blocked, onSelect }) {
  const cols = useMemo(() => {
    const c = { 阻塞待确认: [], 未开始: [], 进行中: [], 已完成: [] }
    for (const a of board.activities) {
      const p = parseFloat(String(a.actual_progress || '0').replace('%', '')) || 0
      if (blocked.has(a.activity_id)) c['阻塞待确认'].push(a)
      else if (p >= 100) c['已完成'].push(a)
      else if (p > 0) c['进行中'].push(a)
      else c['未开始'].push(a)
    }
    return c
  }, [board, blocked])
  return (
    <div className="plan-kanban">
      {Object.entries(cols).map(([k, list]) => (
        <div key={k} className="plan-kanban-col">
          <div className="plan-kanban-head">{k} <span>{list.length}</span></div>
          {list.map((a) => (
            <div key={a.activity_id} className={`plan-kanban-card ${a.is_critical === 1 ? 'crit' : ''}`}
              onClick={() => onSelect(a)}>
              <div className="t"><b>{a.activity_id}</b> {a.activity_name}</div>
              <div className="m">{a.owner_name || '—'} · {a.scheduled_start}~{a.scheduled_finish} · {a.duration_days}d</div>
              <div className="m">完成率 {a.actual_progress || '0%'} · 时差 {a.float_days}d{a.is_critical === 1 ? ' · 关键' : ''}</div>
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}

// ---------------- 甘特视图（F-76 / F-77） ----------------
function GanttTab({ board, range, workdays, onSelect }) {
  const [scale, setScale] = useState('day')
  if (!range) return <div className="plan-empty">暂无日期数据</div>
  const cols = range.total
  const pos = (d) => (d ? diffDays(range.min, d) : 0)
  // 时间刻度表头：按月分段
  const months = []
  for (let i = 0; i < cols; i++) {
    const d = new Date(range.min.getTime() + i * DAY)
    const key = `${d.getFullYear()}-${d.getMonth() + 1}`
    if (!months.length || months[months.length - 1].key !== key) {
      months.push({ key, label: `${d.getMonth() + 1}月`, span: 1 })
    } else months[months.length - 1].span += 1
  }
  return (
    <div className="plan-pane">
      <h3>甘特视图（计划输入 / 排程结果 / 里程碑 / 时差）</h3>
      <div className="plan-gantt-toolbar">
        <span>时间刻度：</span>
        <label><input type="radio" checked={scale === 'day'} onChange={() => setScale('day')} /> 日</label>
        <span className="plan-hint">浅色列为非工作日（节假日）；细条为基线，粗条为排程结果；◆ 为里程碑。</span>
      </div>
      <div className="plan-gantt">
        <div className="plan-gantt-left">
          <div className="plan-gantt-head">活动</div>
          {board.activities.map((a) => (
            <div key={a.activity_id} className="plan-gantt-label" onClick={() => onSelect(a)}>
              <b>{a.activity_id}</b> {a.activity_name}{a.is_milestone === '是' ? ' ◆' : ''}
            </div>
          ))}
        </div>
        <div className="plan-gantt-right" style={{ '--cols': cols }}>
          <div className="plan-gantt-months">
            {months.map((m) => <div key={m.key} style={{ flex: m.span }}>{m.label}</div>)}
          </div>
          <div className="plan-gantt-bg">
            {Array.from({ length: cols }).map((_, i) => {
              const d = new Date(range.min.getTime() + i * DAY)
              const iso = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
              const work = workdays.has(iso)
              return <div key={i} className={`plan-gantt-col ${work ? '' : 'off'} ${d.getMonth() % 2 ? 'alt' : ''}`} />
            })}
          </div>
          {board.activities.map((a) => {
            const bs = parseD(a.baseline_start), bf = parseD(a.baseline_finish)
            const ss = parseD(a.scheduled_start), sf = parseD(a.scheduled_finish)
            return (
              <div key={a.activity_id} className="plan-gantt-row" onClick={() => onSelect(a)}>
                {bs && bf && (
                  <div className="plan-bar base" style={{
                    left: `${(pos(bs) / cols) * 100}%`, width: `${((diffDays(bs, bf) + 1) / cols) * 100}%`,
                  }} title={`基线 ${a.baseline_start}~${a.baseline_finish}`} />
                )}
                {ss && sf && (
                  <div className={`plan-bar ${a.is_critical === 1 ? 'crit' : ''}`} style={{
                    left: `${(pos(ss) / cols) * 100}%`, width: `${((diffDays(ss, sf) + 1) / cols) * 100}%`,
                  }} title={`排程 ${a.scheduled_start}~${a.scheduled_finish}（时差 ${a.float_days}d）`}>
                    {a.is_milestone === '是' ? '◆' : `${a.duration_days}d`}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

// ---------------- 资源负荷（F-79 ~ F-81） ----------------
function ResourceTab({ board, rid, setRid }) {
  const dates = useMemo(() => [...new Set(board.loads.map((l) => l.work_date))].sort(), [board])
  const byKey = useMemo(() => {
    const m = {}
    for (const l of board.loads) m[`${l.resource_id}|${l.work_date}`] = l
    return m
  }, [board])
  const color = (u) => (u > 100 ? '#dc2626' : u > 85 ? '#f59e0b' : u > 0 ? '#16a34a' : '#e5e7eb')
  const selLoads = dates.map((d) => byKey[`${rid}|${d}`]).filter(Boolean)
  const over = board.loads.filter((l) => l.over)
  return (
    <div className="plan-panes">
      <div className="plan-pane">
        <h3>资源可用性（F-79）：可用性 = 日期区间容量 − 其他已承诺工作</h3>
        <p className="plan-hint">
          「名单里有这个人」不等于「那一天有容量」。单元格为该资源当日利用率；红色为超载（并发需求 &gt; 有效容量）。
        </p>
        <div className="plan-heat">
          <div className="plan-heat-head">
            <div className="plan-heat-name">资源</div>
            {dates.map((d) => <div key={d} className="plan-heat-date" title={d}>{d.slice(8)}</div>)}
          </div>
          {board.resources.map((r) => (
            <div key={r.resource_id} className={`plan-heat-row ${r.resource_id === rid ? 'sel' : ''}`}
              onClick={() => setRid(r.resource_id)}>
              <div className="plan-heat-name" title={`${r.resource_id} ${r.resource_name} ${r.role}`}>
                <b>{r.resource_id}</b> {r.resource_name}
                {r.approval_status === '审批中' && <span className="plan-badge warn">审批中</span>}
              </div>
              {dates.map((d) => {
                const l = byKey[`${r.resource_id}|${d}`]
                const u = l ? l.utilization : 0
                return (
                  <div key={d} className="plan-heat-cell" style={{ background: color(u) }}
                    title={`${r.resource_id} ${d}\n容量 ${l?.effective_capacity_hours ?? 0}h / 需求 ${l?.demand_hours ?? 0}h\n利用率 ${u}%${l?.over ? '（超载）' : ''}`} />
                )
              })}
            </div>
          ))}
        </div>
      </div>

      <div className="plan-pane">
        <h3>{rid} 逐日负荷明细</h3>
        <table className="plan-table">
          <thead><tr><th>日期</th><th>容量</th><th>既有承诺</th><th>可用</th><th>有效容量</th><th>并发需求</th><th>利用率</th><th>活动</th></tr></thead>
          <tbody>
            {selLoads.map((l) => (
              <tr key={l.work_date} style={{ background: l.over ? LEVEL_COLOR['阻塞'] : '' }}>
                <td>{l.work_date}</td><td>{l.capacity_hours}</td><td>{l.committed_hours}</td>
                <td>{l.available_hours}</td><td>{l.effective_capacity_hours}</td>
                <td><b>{l.demand_hours}</b></td><td><b>{l.utilization}%</b></td>
                <td>{l.activities.join(', ') || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="plan-pane">
        <h3>资源分配方案（F-81）</h3>
        <p className="plan-hint">待批准资源只能进入「批准情景」，不得进入 V1 正式容量。</p>
        <table className="plan-table">
          <thead><tr><th>方案</th><th>说明</th><th>前置条件</th><th>是否影响 V1</th></tr></thead>
          <tbody>
            {board.allocation.map((o) => (
              <tr key={o.option}><td><b>{o.option}</b></td><td>{o.detail}</td><td>{o.precondition}</td><td>{o.affects_v1}</td></tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="plan-pane">
        <h3>超载明细（共 {over.length} 个资源日）</h3>
        <table className="plan-table">
          <thead><tr><th>资源</th><th>日期</th><th>需求</th><th>有效容量</th><th>利用率</th><th>活动</th></tr></thead>
          <tbody>
            {over.map((l) => (
              <tr key={l.resource_id + l.work_date} style={{ background: LEVEL_COLOR['阻塞'] }}>
                <td><b>{l.resource_id}</b></td><td>{l.work_date}</td><td>{l.demand_hours}h</td>
                <td>{l.effective_capacity_hours}h</td><td><b>{l.utilization}%</b></td><td>{l.activities.join(', ')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ---------------- 关键路径（F-82） ----------------
function CriticalTab({ board, onSelect }) {
  const c = board.critical
  const byId = useMemo(() => Object.fromEntries(board.activities.map((a) => [a.activity_id, a])), [board])
  return (
    <div className="plan-panes">
      <div className="plan-pane">
        <h3>关键路径（{c.chain.length} 项活动，交付边界 {c.boundary}）</h3>
        <div className="plan-chain">
          {c.chain.map((n, i) => (
            <span key={n.activity_id}>
              <span className="plan-chain-node" onClick={() => onSelect(byId[n.activity_id])}>
                <b>{n.activity_id}</b>
                <em>{n.activity_name}</em>
                <small>{n.scheduled_start}~{n.scheduled_finish} · {n.duration_days}d{n.quality_gate !== '无' ? ` · ${n.quality_gate}` : ''}</small>
              </span>
              {i < c.chain.length - 1 && <span className="plan-chain-arrow">→</span>}
            </span>
          ))}
        </div>
      </div>
      <div className="plan-pane">
        <h3>它为什么关键</h3>
        <ul className="plan-list">
          {c.reasons.map((r, i) => <li key={i}>{r}</li>)}
        </ul>
      </div>
      <div className="plan-pane">
        <h3>关键活动明细</h3>
        <table className="plan-table">
          <thead><tr><th>活动</th><th>名称</th><th>前置</th><th>工期</th><th>排程</th><th>时差</th><th>质量门</th><th>里程碑</th></tr></thead>
          <tbody>
            {c.chain.map((n) => (
              <tr key={n.activity_id} className="plan-crit-row">
                <td><b>{n.activity_id}</b></td><td>{n.activity_name}</td>
                <td>{n.predecessors.join(',') || '—'}</td><td>{n.duration_days}d</td>
                <td>{n.scheduled_start} ~ {n.scheduled_finish}</td><td><b>{n.float_days}</b></td>
                <td>{n.quality_gate !== '无' ? <b>{n.quality_gate}</b> : '—'}</td>
                <td>{n.milestone_id || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ---------------- 冲突预警（F-83 / F-84） ----------------
function ConflictTab({ board, onSet }) {
  return (
    <div className="plan-panes">
      {board.conflicts.length === 0 && <div className="plan-empty">暂无冲突预警</div>}
      {board.conflicts.map((c) => (
        <div key={c.conflict_id} className="plan-pane plan-conflict">
          <h3><span className="plan-badge danger">{c.conflict_id}</span> {c.conflict_type} · {c.status}</h3>
          <table className="plan-table">
            <tbody>
              <tr><th>① 对象</th><td>{c.object_id}　（{c.object_name}）</td></tr>
              <tr><th>② 时间</th><td>{c.conflict_date}</td></tr>
              <tr><th>③ 原因</th><td>{c.reason}</td></tr>
              <tr><th>④ 证据</th><td>{c.evidence}</td></tr>
              <tr><th>⑤ 影响</th><td>{c.impact}</td></tr>
              <tr><th>⑥ 备选处理</th><td>{c.options}</td></tr>
              <tr><th>责任人</th><td>{c.owner}</td></tr>
              <tr><th>待确认</th><td>{c.pending}</td></tr>
            </tbody>
          </table>
          <div className="plan-flow">
            <span>状态流转：</span>
            {CONFLICT_FLOW.map((s) => (
              <button key={s} className={c.status === s ? 'on' : ''} disabled={c.status === s}
                onClick={() => onSet(c.conflict_id, s)}>{s}</button>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

// ---------------- 版本比较（F-85 ~ F-88） ----------------
function VersionTab({ board, onApplyEvent }) {
  const sc = board.scenarios
  return (
    <div className="plan-panes">
      <div className="plan-pane">
        <h3>计划版本与恢复点（F-85 / F-86）</h3>
        <table className="plan-table">
          <thead><tr><th>版本</th><th>类型</th><th>名称</th><th>状态</th><th>派生来源</th><th>正式计划</th></tr></thead>
          <tbody>
            {board.versions.map((v) => (
              <tr key={v.version} className={v.version === 'V1' ? 'plan-crit-row' : ''}>
                <td><b>{v.version}</b></td><td>{v.kind}</td><td>{v.label}</td><td>{v.status}</td>
                <td>{v.basis_event || '—'}</td>
                <td>{v.is_formal ? '是' : <span className="plan-badge warn">情景（不得视为已批准）</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="plan-pane">
        <h3>动态事件效力判定与追加式调整（F-86）</h3>
        <p className="plan-hint">追加读取不覆盖原文件：先判效力，再决定重算 / 模拟 / 记录 / 等待确认。V1 冻结后仍保持完整可查。</p>
        <table className="plan-table">
          <thead><tr><th>事件</th><th>类型</th><th>效力</th><th>批准状态</th><th>处理动作</th><th>操作</th></tr></thead>
          <tbody>
            {board.events.map((e) => (
              <tr key={e.event_id}>
                <td><b>{e.event_id}</b></td><td>{e.event_type}</td>
                <td><span className="plan-badge">{e.event_authority}</span></td>
                <td>{e.approval_status}</td><td>{e.required_action}</td>
                <td><button onClick={() => onApplyEvent(e.event_id)}>应用</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="plan-pane">
        <h3>方案比较（F-87）：条件 / 结果 / 代价</h3>
        <p className="plan-hint">{sc.note}（质量门保持不变：{String(sc.quality_gate_unchanged)}）</p>
        <table className="plan-table">
          <thead><tr><th>方案</th><th>条件</th><th>结果</th><th>代价</th><th>工期变化</th><th>增量成本</th><th>由谁确认</th></tr></thead>
          <tbody>
            {sc.versions.map((v) => (
              <tr key={v.version} className={v.version === 'V1' ? 'plan-crit-row' : ''}>
                <td><b>{v.version}</b><br /><small>{v.label}</small></td>
                <td>{v.condition}</td><td>{v.result}</td><td>{v.cost}</td>
                <td>{v.schedule_impact_days ? `+${v.schedule_impact_days} 工作日` : '0'}</td>
                <td>{v.cost_impact_value ? `${Number(v.cost_impact_value).toLocaleString()} 元` : '0'}</td>
                <td>{v.confirm_by}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ---------------- 建议与确认（F-88） ----------------
function AdviceTab({ board }) {
  return (
    <div className="plan-panes">
      <div className="plan-pane">
        <h3>决策支持建议六要素（F-88）</h3>
        <p className="plan-hint">Agent 只生成建议草案，不执行责任动作。数字由规则计算，建议由 Agent 解释，责任由人承担。</p>
        {board.advices.map((a) => (
          <div key={a.id} className="plan-advice">
            <div className="plan-advice-head"><span className="plan-badge">{a.action_type}</span> {a.object}</div>
            <table className="plan-table">
              <tbody>
                <tr><th>① 具体对象</th><td>{a.object}</td></tr>
                <tr><th>② 证据</th><td>{a.evidence}</td></tr>
                <tr><th>③ 责任人</th><td>{a.owner}</td></tr>
                <tr><th>④ 期限</th><td>{a.due_date}</td></tr>
                <tr><th>⑤ 替代方案</th><td>{a.alternative}</td></tr>
                <tr><th>⑥ 待确认事项</th><td>{a.pending}</td></tr>
                <tr><th>状态</th><td><b>{a.status}</b>（草案）</td></tr>
              </tbody>
            </table>
          </div>
        ))}
      </div>
      <div className="plan-pane">
        <h3>人工确认关卡（N-19）：五类责任动作必须由人确认</h3>
        <table className="plan-table">
          <thead><tr><th>动作类型</th><th>事项</th><th>对象</th><th>责任人</th><th>期限</th><th>证据</th><th>状态</th></tr></thead>
          <tbody>
            {board.confirmations.map((c) => (
              <tr key={c.id} style={{ background: c.status === '待确认' ? LEVEL_COLOR['待确认'] : '' }}>
                <td><b>{c.action_type}</b></td><td>{c.title}</td><td>{c.object_id}</td>
                <td>{c.owner}</td><td>{c.due_date}</td><td>{c.evidence}</td><td><b>{c.status}</b></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ---------------- 证据与停止（F-89 / F-90） ----------------
function EvidenceTab({ board }) {
  return (
    <div className="plan-panes">
      <div className="plan-pane">
        <h3>自动停止（F-90）</h3>
        <table className="plan-table">
          <thead><tr><th>类型</th><th>原因</th><th>影响范围</th><th>对象</th></tr></thead>
          <tbody>
            {board.stops.map((s, i) => (
              <tr key={i} style={{ background: LEVEL_COLOR['阻塞'] }}>
                <td><b>{s.stop_type}</b></td><td>{s.reason}</td><td>{s.impact}</td><td>{s.ref_key}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="plan-pane">
        <h3>证据与审计轨迹（F-89）</h3>
        <p className="plan-hint">保留原值、标准值、处理规则、来源、计划版本与确认状态，形成可提交的证据索引与恢复点。</p>
        <table className="plan-table">
          <thead><tr><th>闭环步骤</th><th>类别</th><th>对象</th><th>原值</th><th>标准值 / 结论</th><th>规则</th><th>来源</th><th>确认状态</th></tr></thead>
          <tbody>
            {board.evidence.slice(0, 120).map((e) => (
              <tr key={e.id}>
                <td>{e.step}</td><td>{e.category}</td><td><b>{e.ref_key}</b></td>
                <td>{e.original_value}</td><td>{e.standard_value}</td><td>{e.rule}</td>
                <td>{e.source}</td><td>{e.confirm_status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ---------------- 活动详情（F-77） ----------------
function ActivityDetail({ board, a }) {
  const deps = board.dependencies.filter((d) => d.successor_id === a.activity_id)
  const succs = board.dependencies.filter((d) => d.predecessor_id === a.activity_id)
  const demands = board.demands.filter((d) => d.activity_id === a.activity_id)
  const cf = board.conflicts.filter((c) => String(c.object_id).includes(a.activity_id))
  return (
    <div className="plan-detail">
      <h3>活动详情：{a.activity_id} {a.activity_name}</h3>
      <div className="plan-detail-grid">
        <div><b>WBS 路径</b>{a.wbs_path}</div>
        <div><b>负责人</b>{a.owner_resource_id} {a.owner_name}</div>
        <div><b>计划起止（排程）</b>{a.scheduled_start} ~ {a.scheduled_finish}</div>
        <div><b>工期</b>{a.duration_days} 工作日</div>
        <div><b>基线 / 预测</b>{a.baseline_start}~{a.baseline_finish} / {a.forecast_start}~{a.forecast_finish}</div>
        <div><b>总时差</b>{a.float_days} 天 {a.is_critical === 1 ? '（关键活动）' : ''}</div>
        <div><b>状态 / 完成率</b>{a.status} / {a.actual_progress || '0%'}</div>
        <div><b>里程碑</b>{a.milestone_id || '—'} {a.is_milestone === '是' ? '（是）' : ''}</div>
        <div><b>质量门</b>{a.quality_gate}</div>
        <div><b>计划版本</b>{a.version} · 批准状态 {a.approval_status}</div>
        <div><b>最后更新</b>{a.updated_at}</div>
        <div><b>映射来源</b>{a.local_ids || '—'}（{a.mapping_confirmed ? '已确认' : '待确认'}）</div>
        <div><b>来源材料</b>{a.source_material}</div>
        <div><b>前置依赖</b>{deps.map((d) => `${d.predecessor_id}${d.is_structured ? '' : '（待确认）'}`).join(', ') || '—'}</div>
        <div><b>后继活动</b>{succs.map((d) => d.successor_id).join(', ') || '—'}</div>
        <div><b>资源需求</b>{demands.map((d) => `${d.resource_id}(${d.demand_role} ${d.demand_hours_per_day}h/日, ${d.confirmation_status})`).join('；') || '—'}</div>
      </div>
      {cf.length > 0 && (
        <div className="plan-detail-warn">
          关联冲突预警：{cf.map((c) => `${c.conflict_id}（${c.status}）`).join('、')}
        </div>
      )}
      <div className="plan-hint">
        规则复核：完成日 = 开始日 +（工期 − 1）工作日，按工作日历（周一至周五，扣除节假日）计算；
        总时差 = 最晚开始 − 最早开始；日期可回到依赖、工期、日历与资源复核。
      </div>
    </div>
  )
}
