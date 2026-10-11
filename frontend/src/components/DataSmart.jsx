import { useEffect, useState } from 'react'
import {
  LineChart, Line, BarChart, Bar, RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  XAxis, YAxis, Tooltip, ResponsiveContainer, Legend,
} from 'recharts'
import { api } from '../api'

const BOARD_TABS = [
  { kind: 'progress', label: '进度' },
  { kind: 'cost', label: '成本' },
  { kind: 'staff', label: '人员' },
  { kind: 'risk', label: '风险' },
  { kind: 'quality', label: '质量' },
  { kind: 'procurement', label: '采购' },
  { kind: 'trend', label: '趋势' },
  { kind: 'custom', label: '自定义' },
]

const EMPTY = '暂无数据，请先运行数据管道或补充对应数据源'

// 八类看板 → 相关指标（custom 展示全部）
const METRIC_KIND = {
  progress: ['PV', 'EV', 'SPI', 'progress_plan', 'progress_actual', 'progress_dev'],
  cost: ['AC', 'BAC', 'CPI', 'EAC', 'completion_dev'],
  staff: ['plan_hours', 'actual_hours', 'overtime_hours', 'hours_util'],
  quality: ['high_defects'],
  procurement: ['delayed_milestones', 'delayed_deliveries'],
}

export default function DataSmart() {
  const [projects, setProjects] = useState([])
  const [pid, setPid] = useState(null)
  const [overview, setOverview] = useState(null)
  const [boardKind, setBoardKind] = useState('progress')
  const [board, setBoard] = useState(null)
  const [alerts, setAlerts] = useState([])
  const [cleanlogs, setCleanlogs] = useState([])
  const [forecast, setForecast] = useState(null)
  const [advices, setAdvices] = useState([])
  const [running, setRunning] = useState(false)
  const [msg, setMsg] = useState('')

  useEffect(() => {
    api.listProjects().then((ps) => {
      setProjects(ps)
      if (ps.length) setPid(ps[0].id)
    }).catch((e) => setMsg(String(e)))
  }, [])

  const refresh = async (id) => {
    if (!id) return
    try {
      const [ov, bd, al, cl, fc] = await Promise.all([
        api.dataSmartOverview(id),
        api.dataSmartBoard(id, boardKind),
        api.dataSmartAlerts(id),
        api.dataSmartCleanlogs(id),
        api.dataSmartForecast(id),
      ])
      setOverview(ov)
      setBoard(bd)
      setAlerts(al)
      setCleanlogs(cl)
      setForecast(fc)
    } catch (e) {
      setMsg(String(e))
    }
  }

  useEffect(() => {
    if (pid) refresh(pid)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pid, boardKind])

  const runPipeline = async () => {
    if (!pid) return
    setRunning(true)
    setMsg('')
    try {
      const { job_id } = await api.runDataSmart(pid)
      // 轮询任务状态
      for (let i = 0; i < 60; i++) {
        await new Promise((r) => setTimeout(r, 1000))
        const job = await api.dataSmartRunStatus(pid, job_id)
        if (job.status === 'completed') break
        if (job.status === 'failed') throw new Error(job.error || '运行失败')
      }
      await refresh(pid)
      setMsg('数据管道运行完成')
    } catch (e) {
      setMsg('运行失败: ' + String(e))
    } finally {
      setRunning(false)
    }
  }

  const genAdvise = async () => {
    if (!pid) return
    try {
      const res = await api.dataSmartAdvise(pid)
      setAdvices(res.advices || [])
    } catch (e) {
      setMsg('生成建议失败: ' + String(e))
    }
  }

  const metricVal = (code) => {
    const m = (board?.metrics || []).find((x) => x.code === code)
    return m ? m.value : null
  }

  const trendData = (board?.trend || []).map((t) => ({
    node: t.node,
    计划: t.progress_plan ?? null,
    实际: t.progress_actual ?? null,
    预测: null,
  }))
  if (forecast && forecast.predicted != null && trendData.length) {
    trendData[trendData.length - 1].预测 = forecast.predicted
  }

  const devData = (board?.trend || []).filter((t) => t.progress_dev != null)
    .map((t) => ({ node: t.node, 偏差: t.progress_dev }))

  // 六维风险雷达：以指标换算 0~100 风险指数（越高风险越大）
  const clamp = (n) => Math.max(0, Math.min(100, Math.round(n)))
  const radarData = [
    { 维度: '进度', 风险: clamp((1 - (metricVal('SPI') ?? 1)) * 100) },
    { 维度: '成本', 风险: clamp((1 - (metricVal('CPI') ?? 1)) * 100) },
    { 维度: '质量', 风险: clamp((metricVal('high_defects') ?? 0) * 20) },
    { 维度: '资源', 风险: clamp(Math.max(0, (metricVal('hours_util') ?? 1) - 1) * 100) },
    { 维度: '采购', 风险: clamp((metricVal('delayed_deliveries') ?? 0) * 20) },
    { 维度: '合规', 风险: clamp(((metricVal('risk_score') ?? 0) / 40) * 100) },
  ]

  const project = projects.find((p) => p.id === pid)

  return (
    <div className="datasmart">
      <div className="datasmart-header">
        <h2>📊 数据智能与决策</h2>
        <div className="datasmart-controls">
          {projects.length > 0 && (
            <select value={pid || ''} onChange={(e) => setPid(Number(e.target.value))}>
              {projects.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          )}
          <button onClick={runPipeline} disabled={running || !pid}>
            {running ? '运行中…' : '▶ 运行数据管道'}
          </button>
          <button onClick={genAdvise} disabled={!pid}>💡 生成决策建议</button>
          {project && <span className="datasmart-path">{project.folder_path}</span>}
        </div>
      </div>
      {msg && <div className="datasmart-msg">{msg}</div>}

      {overview && (
        <div className="datasmart-cards">
          <div className="datasmart-card">
            <div className="num">{overview.sources_count}</div>
            <div className="label">数据源数量</div>
          </div>
          <div className="datasmart-card">
            <div className="num">{overview.clean_done}%</div>
            <div className="label">清洗完成率</div>
          </div>
          <div className="datasmart-card">
            <div className="num">{overview.metrics_count}</div>
            <div className="label">指标数</div>
          </div>
          <div className="datasmart-card">
            <div className="num small">{overview.latest_snapshot
              ? `${overview.latest_snapshot.node_label} (r${overview.latest_snapshot.revision})` : '—'}</div>
            <div className="label">最新快照 / 更新时间: {overview.updated_at || '—'}</div>
          </div>
        </div>
      )}

      <div className="datasmart-tabs">
        {BOARD_TABS.map((t) => (
          <div
            key={t.kind}
            className={`datasmart-tab ${boardKind === t.kind ? 'active' : ''}`}
            onClick={() => setBoardKind(t.kind)}
          >
            {t.label}
          </div>
        ))}
      </div>

      <div className="datasmart-board">
        {board?.empty && <div className="datasmart-empty">{board.message || EMPTY}</div>}
        {board && !board.empty && boardKind === 'trend' && (
          <div className="datasmart-charts">
            {trendData.length >= 2 ? (
              <div className="datasmart-chart">
                <h4>计划 vs 实际 vs 预测（进度 %）</h4>
                <ResponsiveContainer width="100%" height={260}>
                  <LineChart data={trendData}>
                    <XAxis dataKey="node" /><YAxis /><Tooltip /><Legend />
                    <Line type="monotone" dataKey="计划" stroke="#8884d8" dot />
                    <Line type="monotone" dataKey="实际" stroke="#82ca9d" dot />
                    <Line type="monotone" dataKey="预测" stroke="#ff7300" strokeDasharray="5 5" dot />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            ) : <div className="datasmart-empty">快照不足 2 个，暂无法绘制趋势</div>}
            {devData.length >= 1 ? (
              <div className="datasmart-chart">
                <h4>进度偏差</h4>
                <ResponsiveContainer width="100%" height={260}>
                  <BarChart data={devData}>
                    <XAxis dataKey="node" /><YAxis /><Tooltip />
                    <Bar dataKey="偏差" fill="#ffc658" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            ) : null}
            {forecast && (
              <div className="datasmart-forecast">
                <h4>预测结果</h4>
                <table>
                  <tbody>
                    <tr><td>下一节点</td><td>{forecast.next_node || '—'}</td></tr>
                    <tr><td>预测值</td><td>{forecast.predicted != null ? forecast.predicted : '—'}</td></tr>
                    <tr><td>斜率</td><td>{forecast.slope != null ? forecast.slope : '—'}</td></tr>
                    <tr><td>置信度</td><td>{forecast.confidence || '—'}{forecast.r2 != null ? ` (R²=${forecast.r2})` : ''}</td></tr>
                    <tr><td>方法</td><td>{forecast.method || '—'}</td></tr>
                    <tr><td>基线</td><td>{forecast.baseline || '—'}</td></tr>
                    <tr><td>局限</td><td>{forecast.limitation || '—'}</td></tr>
                    {forecast.error && <tr><td>提示</td><td>{forecast.error}</td></tr>}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
        {board && !board.empty && boardKind === 'risk' && radarData.length > 0 && (
          <div className="datasmart-chart">
            <h4>六维风险雷达（进度/成本/质量/资源/采购/合规，风险指数 0~100）</h4>
            <ResponsiveContainer width="100%" height={300}>
              <RadarChart data={radarData} outerRadius="70%">
                <PolarGrid />
                <PolarAngleAxis dataKey="维度" />
                <PolarRadiusAxis domain={[0, 100]} />
                <Radar dataKey="风险" stroke="#ef4444" fill="#ef4444" fillOpacity={0.5} />
                <Tooltip />
              </RadarChart>
            </ResponsiveContainer>
          </div>
        )}
        {board && !board.empty && boardKind !== 'trend' && boardKind !== 'risk' && (
          <div className="datasmart-metrics">
            <h4>{BOARD_TABS.find((t) => t.kind === boardKind)?.label}看板指标</h4>
            {(() => {
              const all = board.metrics || []
              const codes = METRIC_KIND[boardKind]
              const rows = codes ? all.filter((m) => codes.includes(m.code)) : all
              if (rows.length === 0) return <div className="datasmart-empty">{EMPTY}</div>
              return (
                <table className="datasmart-table">
                  <thead>
                    <tr><th>指标</th><th>值</th><th>公式</th><th>来源</th></tr>
                  </thead>
                  <tbody>
                    {rows.map((m) => (
                      <tr key={m.id}>
                        <td>{m.code}</td>
                        <td>{m.value}</td>
                        <td>{m.formula}</td>
                        <td>{m.source_ref}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )
            })()}
          </div>
        )}
      </div>

      <div className="datasmart-section">
        <h3>🚨 预警明细</h3>
        {alerts.length === 0 && <div className="datasmart-empty">暂无预警记录</div>}
        {alerts.length > 0 && (
          <table className="datasmart-table">
            <thead>
              <tr><th>对象ID</th><th>类型</th><th>对象名</th><th>责任人</th><th>期限</th><th>来源</th><th>状态</th></tr>
            </thead>
            <tbody>
              {alerts.map((a) => (
                <tr key={a.id}>
                  <td>{a.object_id}</td>
                  <td>{a.alert_type}</td>
                  <td>{a.object_name}</td>
                  <td>{a.owner}</td>
                  <td>{a.due_date}</td>
                  <td>{a.source_file}</td>
                  <td>{a.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="datasmart-section">
        <h3>🧹 清洗日志</h3>
        {cleanlogs.length === 0 && <div className="datasmart-empty">暂无清洗记录</div>}
        {cleanlogs.length > 0 && (
          <table className="datasmart-table">
            <thead>
              <tr><th>表名</th><th>行键</th><th>字段</th><th>原值</th><th>标准值</th><th>规则</th><th>来源文件</th><th>状态</th></tr>
            </thead>
            <tbody>
              {cleanlogs.map((c) => (
                <tr key={c.id}>
                  <td>{c.table_name}</td>
                  <td>{c.row_key}</td>
                  <td>{c.field}</td>
                  <td>{c.original_value}</td>
                  <td>{c.standard_value}</td>
                  <td>{c.rule}</td>
                  <td>{c.source_file}</td>
                  <td>{c.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="datasmart-section">
        <h3>💡 决策建议</h3>
        {advices.length === 0 && <div className="datasmart-empty">点击「生成决策建议」按钮获取行动草案</div>}
        <div className="datasmart-advice-list">
          {advices.map((a) => (
            <div key={a.id} className="datasmart-advice">
              <div><b>异常：</b>{a.anomaly}</div>
              <div><b>证据：</b>{a.evidence}</div>
              <div><b>动作：</b>{a.action}</div>
              <div><b>责任：</b>{a.owner}　<b>期限：</b>{a.due_date}</div>
              <div><b>确认点：</b>{a.confirm_point}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}