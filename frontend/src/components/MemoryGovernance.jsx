import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'

/**
 * 记忆治理（N-11 / 7.9）：记忆可更新、可纠错、可失效。
 * 失效 / 被取代的记忆不再参与召回，避免错误被反复引用放大。
 */
const STATUS_LABEL = { active: '生效', superseded: '已被取代', inactive: '已失效' }

export default function MemoryGovernance({ projectId, onChanged }) {
  const [rows, setRows] = useState([])
  const [audit, setAudit] = useState([])
  const [form, setForm] = useState({ key: '', value: '', category: '' })
  const [editing, setEditing] = useState(null) // {id, mode: 'update'|'correct', value, reason}
  const [msg, setMsg] = useState('')

  const reload = useCallback(async () => {
    try {
      const [lt, au] = await Promise.all([api.memoryLongterm(projectId), api.memoryAudit(projectId)])
      setRows(lt)
      setAudit(au)
    } catch (e) {
      setMsg(String(e))
    }
  }, [projectId])

  useEffect(() => { reload() }, [reload])

  const after = () => { reload(); onChanged && onChanged() }

  const create = async () => {
    if (!form.key.trim()) return setMsg('请填写 key')
    try {
      await api.memoryCreate(projectId, form)
      setForm({ key: '', value: '', category: '' })
      setMsg('已新增长期记忆')
      after()
    } catch (e) { setMsg('新增失败：' + String(e)) }
  }

  const submitEdit = async () => {
    if (!editing) return
    try {
      if (editing.mode === 'update') {
        await api.memoryUpdate(projectId, editing.id, {
          value: editing.value, note: editing.reason, reason: editing.reason || '手动更新',
        })
        setMsg('记忆已更新（可更新）')
      } else {
        await api.memoryCorrect(projectId, editing.id, { value: editing.value, reason: editing.reason })
        setMsg('记忆已纠错，旧版本置为「已被取代」（可纠错）')
      }
      setEditing(null)
      after()
    } catch (e) { setMsg('操作失败：' + String(e)) }
  }

  const invalidate = async (row) => {
    const reason = window.prompt('失效原因（可选）：', '过时/被推翻') ?? null
    if (reason === null) return
    try {
      await api.memoryInvalidate(projectId, row.id, reason)
      setMsg('记忆已置为失效，不再参与召回（可失效）')
      after()
    } catch (e) { setMsg('操作失败：' + String(e)) }
  }

  return (
    <div className="memory-gov">
      {msg && <div className="dl-ok">{msg}</div>}

      <div className="board-panel full">
        <div className="panel-head">
          <span>长期记忆台账</span>
          <span className="badge">{rows.length} 条</span>
        </div>
        <div className="panel-body" style={{ maxHeight: 'none' }}>
          <table className="data-table">
            <thead>
              <tr><th>状态</th><th>分类</th><th>Key</th><th>Value</th><th>更新时间</th><th>操作</th></tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} style={{ opacity: r.status === 'active' ? 1 : 0.55 }}>
                  <td><span className={`mem-status ${r.status}`}>{STATUS_LABEL[r.status] || r.status}</span></td>
                  <td>{r.category || '-'}</td>
                  <td>{r.key}</td>
                  <td>{r.value}</td>
                  <td style={{ color: 'var(--text-muted)', fontSize: 12 }}>{r.updated_at || r.created_at}</td>
                  <td>
                    {r.status === 'active' && (
                      <div className="mem-actions">
                        <button className="icon-btn" title="更新"
                          onClick={() => setEditing({ id: r.id, mode: 'update', value: r.value, reason: '' })}>✏️</button>
                        <button className="icon-btn" title="纠错"
                          onClick={() => setEditing({ id: r.id, mode: 'correct', value: r.value, reason: '' })}>🛠</button>
                        <button className="icon-btn danger" title="置为失效"
                          onClick={() => invalidate(r)}>🚫</button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
              {rows.length === 0 && <tr><td colSpan={6} className="empty">暂无长期记忆</td></tr>}
            </tbody>
          </table>

          {editing && (
            <div className="mem-edit">
              <div className="mem-edit-title">
                {editing.mode === 'update' ? '更新记忆内容（可更新）' : '纠错：写入新值并把旧值置为「已被取代」（可纠错）'}
              </div>
              <textarea rows={2} value={editing.value}
                onChange={(e) => setEditing({ ...editing, value: e.target.value })} />
              <input placeholder="原因 / 备注（可选）" value={editing.reason}
                onChange={(e) => setEditing({ ...editing, reason: e.target.value })} />
              <div className="mem-edit-actions">
                <button className="btn primary" onClick={submitEdit}>提交</button>
                <button className="btn" onClick={() => setEditing(null)}>取消</button>
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="board-panel full" style={{ marginTop: 16 }}>
        <div className="panel-head"><span>新增长期记忆</span></div>
        <div className="panel-body" style={{ maxHeight: 'none' }}>
          <div className="mem-create">
            <input placeholder="Key（如：项目类型）" value={form.key}
              onChange={(e) => setForm({ ...form, key: e.target.value })} />
            <input placeholder="Value" value={form.value}
              onChange={(e) => setForm({ ...form, value: e.target.value })} />
            <input placeholder="分类（可空）" value={form.category}
              onChange={(e) => setForm({ ...form, category: e.target.value })} />
            <button className="btn primary" onClick={create}>➕ 新增</button>
          </div>
        </div>
      </div>

      <div className="board-panel full" style={{ marginTop: 16 }}>
        <div className="panel-head"><span>记忆治理审计</span><span className="badge">{audit.length} 条</span></div>
        <div className="panel-body" style={{ maxHeight: 260 }}>
          <table className="data-table">
            <thead><tr><th>时间</th><th>动作</th><th>变更前</th><th>变更后</th><th>原因</th></tr></thead>
            <tbody>
              {audit.map((a) => (
                <tr key={a.id}>
                  <td style={{ color: 'var(--text-muted)', fontSize: 12 }}>{a.created_at}</td>
                  <td>{({ create: '新增', update: '更新', correct: '纠错', invalidate: '失效' })[a.action] || a.action}</td>
                  <td>{a.before}</td>
                  <td>{a.after}</td>
                  <td>{a.reason}</td>
                </tr>
              ))}
              {audit.length === 0 && <tr><td colSpan={5} className="empty">暂无治理记录</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
