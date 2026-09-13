import { useState, useEffect, useCallback } from 'react'
import { api } from '../api'
import ChatPanel from './ChatPanel'
import Dashboard from './Dashboard'

const STATUS_LABELS = {
  confirmed: '已确认',
  provisional: '待核实',
  needs_confirmation: '待确认',
  open: '进行中',
  closed: '已关闭',
}

function StatusPill({ status }) {
  return <span className={`status-pill ${status}`}>{STATUS_LABELS[status] || status}</span>
}

function FactsTable({ facts }) {
  if (!facts.length) return <div className="empty">暂无事实，点击「重新识别文件」提取项目关键信息。</div>
  return (
    <div className="board-panel full">
      <div className="panel-head"><span>事实台账</span><span className="badge">{facts.length} 条</span></div>
      <div className="panel-body" style={{ maxHeight: 'none' }}>
        <table className="data-table">
          <thead>
            <tr><th>分类</th><th>字段</th><th>值</th><th>状态</th><th>来源</th></tr>
          </thead>
          <tbody>
            {facts.map((f) => (
              <tr key={f.id}>
                <td>{f.category}</td>
                <td>{f.field}</td>
                <td>{f.value}</td>
                <td><StatusPill status={f.status} /></td>
                <td style={{ color: 'var(--text-muted)', fontSize: 12 }}>{f.source}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function StakeholdersTable({ data }) {
  if (!data.length) return <div className="empty">暂无干系人信息。</div>
  return (
    <div className="board-panel full">
      <div className="panel-head"><span>干系人</span><span className="badge">{data.length} 人</span></div>
      <div className="panel-body" style={{ maxHeight: 'none' }}>
        <table className="data-table">
          <thead>
            <tr><th>姓名</th><th>单位</th><th>角色</th><th>影响力</th><th>关注点</th><th>沟通渠道</th></tr>
          </thead>
          <tbody>
            {data.map((s) => (
              <tr key={s.id}>
                <td>{s.name}</td>
                <td>{s.organization}</td>
                <td>{s.role}</td>
                <td>{s.influence}</td>
                <td>{s.concern}</td>
                <td>{s.channel}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function FinanceTable({ data }) {
  if (!data.length) return <div className="empty">暂无财务信息。</div>
  return (
    <div className="board-panel full">
      <div className="panel-head"><span>财务信息</span><span className="badge">{data.length} 条</span></div>
      <div className="panel-body" style={{ maxHeight: 'none' }}>
        <table className="data-table">
          <thead>
            <tr><th>类别</th><th>项目</th><th>金额</th><th>口径</th><th>来源</th><th>备注</th></tr>
          </thead>
          <tbody>
            {data.map((f) => (
              <tr key={f.id}>
                <td>{f.category}</td>
                <td>{f.item}</td>
                <td>{f.amount}</td>
                <td>{f.tax_inclusive} / {f.period}</td>
                <td style={{ color: 'var(--text-muted)', fontSize: 12 }}>{f.source}</td>
                <td>{f.note}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 8 }}>⚠️ 财务结论为教学整理结果，需财务复核。</div>
      </div>
    </div>
  )
}

function ActionsTable({ data }) {
  if (!data.length) return <div className="empty">暂无行动项。</div>
  return (
    <div className="board-panel full">
      <div className="panel-head"><span>行动项</span><span className="badge">{data.length} 条</span></div>
      <div className="panel-body" style={{ maxHeight: 'none' }}>
        <table className="data-table">
          <thead>
            <tr><th>行动</th><th>负责人</th><th>期限</th><th>状态</th><th>来源</th></tr>
          </thead>
          <tbody>
            {data.map((a) => (
              <tr key={a.id}>
                <td>{a.action}</td>
                <td>{a.owner}</td>
                <td>{a.due_date}</td>
                <td><StatusPill status={a.status} /></td>
                <td style={{ color: 'var(--text-muted)', fontSize: 12 }}>{a.source}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function ConflictsTable({ data }) {
  if (!data.length) return <div className="empty">暂无冲突或待确认事项。</div>
  return (
    <div className="board-panel full">
      <div className="panel-head"><span>冲突 / 待确认事项</span><span className="badge">{data.length} 条</span></div>
      <div className="panel-body" style={{ maxHeight: 'none' }}>
        <table className="data-table">
          <thead>
            <tr><th>类别</th><th>描述</th><th>来源A</th><th>来源B</th></tr>
          </thead>
          <tbody>
            {data.map((c) => (
              <tr key={c.id}>
                <td>{c.category}</td>
                <td>{c.description}</td>
                <td style={{ color: 'var(--text-muted)', fontSize: 12 }}>{c.source_a}</td>
                <td style={{ color: 'var(--text-muted)', fontSize: 12 }}>{c.source_b}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function SourcesTable({ data }) {
  if (!data.length) return <div className="empty">暂无来源文件。</div>
  return (
    <div className="board-panel full">
      <div className="panel-head"><span>来源文件</span><span className="badge">{data.length} 个</span></div>
      <div className="panel-body" style={{ maxHeight: 'none' }}>
        <table className="data-table">
          <thead>
            <tr><th>文件</th><th>识别类型</th><th>加载时间</th></tr>
          </thead>
          <tbody>
            {data.map((s) => (
              <tr key={s.id}>
                <td>{s.file}</td>
                <td>{s.file_type}</td>
                <td style={{ color: 'var(--text-muted)', fontSize: 12 }}>{s.loaded_at}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function DocumentsPanel({ data, onDelete }) {
  if (!data.length) return <div className="empty">暂无生成文档，点击右上角「生成综合报告」。</div>
  return (
    <div className="board-panel full">
      <div className="panel-head"><span>已生成文档</span><span className="badge">{data.length} 个</span></div>
      <div className="panel-body" style={{ maxHeight: 'none' }}>
        {data.map((d) => {
          const filename = d.file_path.split('/').pop()
          return (
            <div key={d.id} className="doc-row">
              <div className="doc-info">
                <span className="doc-title">📄 {d.title}</span>
                {d.version && <span className="doc-version">{d.version}</span>}
                <span className="doc-time">{d.created_at}</span>
              </div>
              <div className="doc-actions">
                <a className="doc-link" href={`/api/projects/documents/download/${encodeURIComponent(filename)}`} download>⬇ 下载</a>
                <button className="icon-btn danger" title="删除" onClick={() => onDelete(d.id)}>🗑</button>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default function ProjectBoard({ project, onBack }) {
  const [board, setBoard] = useState(null)
  const [tab, setTab] = useState('dashboard')
  const [job, setJob] = useState(null)
  const [loading, setLoading] = useState(false)

  const load = useCallback(async () => {
    try {
      const data = await api.board(project.id)
      setBoard(data)
    } catch (e) {
      alert(e.message)
    }
  }, [project.id])

  useEffect(() => { load() }, [load])

  const startAnalyze = async () => {
    try {
      const { job_id } = await api.analyze(project.id)
      pollJob(job_id)
    } catch (e) {
      alert(e.message)
    }
  }

  const pollJob = (jobId) => {
    setLoading(true)
    setJob(null)
    const timer = setInterval(async () => {
      try {
        const j = await api.analyzeStatus(jobId)
        setJob(j)
        if (j.status === 'completed' || j.status === 'failed') {
          clearInterval(timer)
          setLoading(false)
          if (j.status === 'completed') {
            load()
          }
          if (j.status === 'failed') {
            alert(j.error || '分析失败')
          }
        }
      } catch {
        clearInterval(timer)
        setLoading(false)
      }
    }, 2000)
  }

  const generateSummary = async () => {
    try {
      await api.generateSummary(project.id)
      await load()
      setTab('documents')
      alert('综合整理报告已生成，可在「文档」标签页下载。')
    } catch (e) {
      alert(e.message)
    }
  }

  const handleDeleteDoc = async (docId) => {
    if (!confirm('确定删除该文档？此操作不可恢复。')) return
    try {
      await api.deleteDocument(docId)
      await load()
    } catch (e) {
      alert(e.message)
    }
  }

  const hasData = board && board.facts.length > 0

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <button className="icon-btn" onClick={onBack} title="返回">←</button>
            <h1>{project.name}</h1>
            {board?.project?.project_type && <span className="type">{board.project.project_type}</span>}
          </div>
          <div className="subtitle">📁 {project.folder_path.split('/').pop()}</div>
        </div>
        <div style={{ display: 'flex', gap: 10, flexShrink: 0 }}>
          <button className="btn" onClick={startAnalyze} disabled={loading}>
            {loading ? '识别中…' : '🔄 重新识别文件'}
          </button>
          <button className="btn primary" onClick={generateSummary} disabled={!hasData}>
            📄 生成综合报告
          </button>
        </div>
      </div>

      {job && job.status === 'running' && (
        <div className="analyzing">
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <strong>正在识别项目文件…</strong>
            <span>{job.done} / {job.total}</span>
          </div>
          <div className="bar-track">
            <div className="bar-fill" style={{ width: `${job.total ? (job.done / job.total) * 100 : 0}%` }} />
          </div>
          <div className="status-text">当前：{job.current}</div>
        </div>
      )}

      {board && (
        <div className="board-toolbar">
          <div className="tabs">
            <div className={`tab ${tab === 'dashboard' ? 'active' : ''}`} onClick={() => setTab('dashboard')}>📊 概览看板</div>
            <div className={`tab ${tab === 'facts' ? 'active' : ''}`} onClick={() => setTab('facts')}>事实台账 ({board.facts.length})</div>
            <div className={`tab ${tab === 'stakeholders' ? 'active' : ''}`} onClick={() => setTab('stakeholders')}>干系人 ({board.stakeholders.length})</div>
            <div className={`tab ${tab === 'finance' ? 'active' : ''}`} onClick={() => setTab('finance')}>财务 ({board.finance.length})</div>
            <div className={`tab ${tab === 'actions' ? 'active' : ''}`} onClick={() => setTab('actions')}>行动项 ({board.actions.length})</div>
            <div className={`tab ${tab === 'conflicts' ? 'active' : ''}`} onClick={() => setTab('conflicts')}>冲突/待确认 ({board.conflicts.length})</div>
            <div className={`tab ${tab === 'sources' ? 'active' : ''}`} onClick={() => setTab('sources')}>来源文件 ({board.sources.length})</div>
            <div className={`tab ${tab === 'documents' ? 'active' : ''}`} onClick={() => setTab('documents')}>文档 ({board.documents.length})</div>
            <div className={`tab ${tab === 'chat' ? 'active' : ''}`} onClick={() => setTab('chat')}>💬 项目智能助手</div>
          </div>
        </div>
      )}

      {board && tab === 'dashboard' && <Dashboard board={board} />}
      {board && tab === 'facts' && <FactsTable facts={board.facts} />}
      {board && tab === 'stakeholders' && <StakeholdersTable data={board.stakeholders} />}
      {board && tab === 'finance' && <FinanceTable data={board.finance} />}
      {board && tab === 'actions' && <ActionsTable data={board.actions} />}
      {board && tab === 'conflicts' && <ConflictsTable data={board.conflicts} />}
      {board && tab === 'sources' && <SourcesTable data={board.sources} />}
      {board && tab === 'documents' && <DocumentsPanel data={board.documents} onDelete={handleDeleteDoc} />}
      {tab === 'chat' && <ChatPanel projectId={project.id} />}
    </div>
  )
}
