import { useState, useEffect, useCallback } from 'react'
import { api } from '../api'
import ProjectModal from './ProjectModal'

export default function ProjectList({ onOpenProject }) {
  const [projects, setProjects] = useState([])
  const [modal, setModal] = useState(null) // null | 'create' | project对象
  const [loading, setLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.listProjects()
      setProjects(data)
    } catch (e) {
      alert(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const totalFacts = projects.reduce((s, p) => s + (p.facts_count || 0), 0)
  const totalStakeholders = projects.reduce((s, p) => s + (p.stakeholders_count || 0), 0)
  const totalFinance = projects.reduce((s, p) => s + (p.finance_count || 0), 0)
  const totalActions = projects.reduce((s, p) => s + (p.actions_count || 0), 0)

  const handleSave = async (data) => {
    try {
      if (modal && modal !== 'create') {
        await api.updateProject(modal.id, data)
      } else {
        await api.createProject(data)
      }
      setModal(null)
      load()
    } catch (e) {
      alert(e.message)
    }
  }

  const handleDelete = async (p) => {
    if (!confirm(`确定删除项目「${p.name}」？该项目下所有识别数据与记忆将一并删除。`)) return
    try {
      await api.deleteProject(p.id)
      load()
    } catch (e) {
      alert(e.message)
    }
  }

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1>项目全局管理</h1>
          <div className="subtitle">集中管理项目 · 智能识别项目文件 · 沉淀本地记忆</div>
        </div>
        <button className="btn primary" onClick={() => setModal('create')}>＋ 新建项目</button>
      </div>

      <div className="stats-row">
        <div className="stat-card"><div className="label">项目总数</div><div className="value accent">{projects.length}</div></div>
        <div className="stat-card"><div className="label">已提取事实</div><div className="value">{totalFacts}</div></div>
        <div className="stat-card"><div className="label">干系人</div><div className="value">{totalStakeholders}</div></div>
        <div className="stat-card"><div className="label">行动项</div><div className="value">{totalActions}</div></div>
      </div>

      {loading ? (
        <div className="empty"><span className="spinner" /> 加载中…</div>
      ) : projects.length === 0 ? (
        <div className="empty">
          还没有项目。<br />
          点击右上角「新建项目」，选择一个项目文件夹开始。
        </div>
      ) : (
        <div className="project-grid">
          {projects.map((p) => (
            <div key={p.id} className="project-card" onClick={() => onOpenProject(p)}>
              <div className="actions" onClick={(e) => e.stopPropagation()}>
                <button className="icon-btn" title="编辑" onClick={() => setModal(p)}>✎</button>
                <button className="icon-btn danger" title="删除" onClick={() => handleDelete(p)}>🗑</button>
              </div>
              <div className="name">{p.name}</div>
              <span className="type">{p.project_type || '未识别类型'}</span>
              {p.description && <div className="desc">{p.description}</div>}
              <div className="counts">
                <span className="count-pill">事实 {p.facts_count}</span>
                <span className="count-pill">干系人 {p.stakeholders_count}</span>
                <span className="count-pill">财务 {p.finance_count}</span>
                <span className="count-pill">行动 {p.actions_count}</span>
                <span className="count-pill">冲突 {p.conflicts_count}</span>
              </div>
              <div className="meta">文件 {p.sources_count} · 更新 {p.updated_at || p.created_at}</div>
            </div>
          ))}
        </div>
      )}

      {modal && (
        <ProjectModal
          initial={modal !== 'create' ? modal : null}
          onClose={() => setModal(null)}
          onSave={handleSave}
        />
      )}
    </div>
  )
}
