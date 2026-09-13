import { useMemo } from 'react'
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid,
  PieChart, Pie, Cell, Legend,
} from 'recharts'

const COLORS = ['#6366f1', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4', '#ec4899', '#14b8a6']
const STATUS_LABEL = { confirmed: '已确认', provisional: '待核实', needs_confirmation: '待确认', open: '进行中', closed: '已关闭' }

function parseAmount(s) {
  if (s == null || s === '') return 0
  const m = String(s).replace(/[^\d.-]/g, '')
  const n = parseFloat(m)
  return isNaN(n) ? 0 : n
}

function fmtWan(n) {
  if (n >= 10000) return (n / 10000).toFixed(1) + '万'
  return String(n)
}

function KpiCard({ label, value, sub, accent, warn }) {
  return (
    <div className="kpi-card">
      <div className="label">{label}</div>
      <div className={`value ${accent ? 'accent' : ''} ${warn ? 'warn' : ''}`}>{value}</div>
      {sub && <div className="sub">{sub}</div>}
    </div>
  )
}

export default function Dashboard({ board }) {
  const d = useMemo(() => {
    const facts = board.facts || []
    const stakeholders = board.stakeholders || []
    const finance = board.finance || []
    const actions = board.actions || []
    const conflicts = board.conflicts || []

    const confirmed = facts.filter((f) => f.status === 'confirmed').length
    const provisional = facts.filter((f) => f.status === 'provisional').length
    const needsConf = facts.filter((f) => f.status === 'needs_confirmation').length
    const openActions = actions.filter((a) => a.status === 'open').length

    // 项目总金额
    let amount = null
    let amountSource = ''
    const fin = finance.find((f) => /总价|总金额/.test(f.item || ''))
    if (fin && parseAmount(fin.amount) > 0) { amount = fin.amount; amountSource = fin.source }
    else {
      const fact = facts.find((f) => /合同总价|合同金额|总价|总金额/.test(f.field || ''))
      if (fact) { amount = fact.value; amountSource = fact.source }
    }

    // 事实分类分布
    const catMap = {}
    facts.forEach((f) => { const c = f.category || '其他'; catMap[c] = (catMap[c] || 0) + 1 })
    const factByCategory = Object.entries(catMap).map(([name, value]) => ({ name, value })).sort((a, b) => b.value - a.value)

    // 事实状态
    const factByStatus = [
      { name: '已确认', value: confirmed },
      { name: '待核实', value: provisional },
      { name: '待确认', value: needsConf },
    ].filter((x) => x.value > 0)

    // 干系人单位分布
    const orgMap = {}
    stakeholders.forEach((s) => { const o = s.organization || '未知'; orgMap[o] = (orgMap[o] || 0) + 1 })
    const stakeholderByOrg = Object.entries(orgMap).map(([name, value]) => ({ name, value })).sort((a, b) => b.value - a.value).slice(0, 8)

    // 财务类别金额
    const finMap = {}
    finance.forEach((f) => { const c = f.category || '其他'; finMap[c] = (finMap[c] || 0) + parseAmount(f.amount) })
    const financeByCategory = Object.entries(finMap).map(([name, value]) => ({ name, value })).sort((a, b) => b.value - a.value)

    // 项目核心信息（项目类别事实）
    const projectFacts = facts.filter((f) => f.category === '项目').slice(0, 10)

    return {
      confirmed, provisional, needsConf, openActions,
      amount, amountSource, factByCategory, factByStatus, stakeholderByOrg, financeByCategory, projectFacts,
      conflicts, actions, facts, stakeholders, finance,
    }
  }, [board])

  return (
    <div className="dashboard">
      {/* 指标卡片 */}
      <div className="kpi-row">
        <KpiCard label="合同总金额" value={d.amount || '—'} sub={d.amountSource ? `来源:${d.amountSource}` : ''} accent />
        <KpiCard label="干系人" value={board.stakeholders.length} sub="相关单位 / 角色" />
        <KpiCard label="行动项" value={board.actions.length} sub={`${d.openActions} 项进行中`} />
        <KpiCard label="冲突 / 待确认" value={board.conflicts.length} sub="需人工复核" warn={board.conflicts.length > 0} />
        <KpiCard label="已确认事实" value={d.confirmed} sub={`/ ${board.facts.length} 条事实`} />
      </div>

      <div className="dashboard-grid">
        {/* 项目核心信息 */}
        <div className="board-panel">
          <div className="panel-head">
            <span>📋 项目核心信息</span>
            <span className="badge">{board.project.project_type || '未识别类型'}</span>
          </div>
          <div className="panel-body">
            {d.projectFacts.length ? (
              d.projectFacts.map((f) => (
                <div key={f.id} className="fact-row">
                  <span className="fact-field">{f.field}</span>
                  <span className="fact-value" title={f.value}>{f.value}</span>
                  <span className={`status-pill ${f.status}`}>{STATUS_LABEL[f.status] || f.status}</span>
                </div>
              ))
            ) : (
              <div className="empty">暂无项目信息，点击右上角「重新识别文件」。</div>
            )}
          </div>
        </div>

        {/* 财务金额分布 */}
        <div className="board-panel">
          <div className="panel-head"><span>💰 财务金额分布</span><span className="badge">按类别</span></div>
          <div className="panel-body chart-body">
            {d.financeByCategory.length ? (
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={d.financeByCategory} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                  <YAxis tickFormatter={fmtWan} tick={{ fontSize: 11 }} width={44} />
                  <Tooltip formatter={(v) => ['¥' + Number(v).toLocaleString(), '金额']} />
                  <Bar dataKey="value" fill="#6366f1" radius={[4, 4, 0, 0]} maxBarSize={48} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="empty">暂无财务数据</div>
            )}
          </div>
        </div>

        {/* 干系人分布 */}
        <div className="board-panel">
          <div className="panel-head"><span>👥 干系人分布</span><span className="badge">按单位</span></div>
          <div className="panel-body chart-body">
            {d.stakeholderByOrg.length ? (
              <ResponsiveContainer width="100%" height={250}>
                <PieChart>
                  <Pie data={d.stakeholderByOrg} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={78} innerRadius={30} paddingAngle={2}>
                    {d.stakeholderByOrg.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                  </Pie>
                  <Legend verticalAlign="bottom" height={24} iconSize={10} wrapperStyle={{ fontSize: 11 }} />
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className="empty">暂无干系人数据</div>
            )}
          </div>
        </div>

        {/* 事实状态 */}
        <div className="board-panel">
          <div className="panel-head"><span>✅ 事实确认度</span><span className="badge">状态分布</span></div>
          <div className="panel-body chart-body">
            {d.factByStatus.length ? (
              <ResponsiveContainer width="100%" height={250}>
                <PieChart>
                  <Pie data={d.factByStatus} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={78} innerRadius={30} paddingAngle={2}>
                    {d.factByStatus.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                  </Pie>
                  <Legend verticalAlign="bottom" height={24} iconSize={10} wrapperStyle={{ fontSize: 11 }} />
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className="empty">暂无事实数据</div>
            )}
          </div>
        </div>
      </div>

      {/* 冲突与风险 */}
      {d.conflicts.length > 0 && (
        <div className="board-panel full" style={{ marginTop: 16 }}>
          <div className="panel-head"><span>⚠️ 冲突与风险提示</span><span className="badge">{d.conflicts.length} 条</span></div>
          <div className="panel-body">
            {d.conflicts.slice(0, 12).map((c) => (
              <div key={c.id} className="conflict-row">
                <span className="conflict-cat">{c.category || '其他'}</span>
                <span className="conflict-desc">{c.description}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
