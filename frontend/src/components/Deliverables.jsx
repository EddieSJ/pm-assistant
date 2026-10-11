import { useEffect, useState } from 'react'
import { api } from '../api'

/**
 * 沟通与成果输出（课程1 F-39 / F-40）
 * - F-40：周报 / 风险清单 / 成本说明 / RACI 职责表 / 会议纪要 / 干系人简报
 * - F-39：干系人分层简报（6 类干系人切换信息切面）
 * 所有成果均以统一事实底稿为唯一来源；Agent 只起草，正式外发须人工确认。
 */
export default function Deliverables({ projectId, onGenerated }) {
  const [templates, setTemplates] = useState([])
  const [audiences, setAudiences] = useState([])
  const [audience, setAudience] = useState('owner')
  const [busy, setBusy] = useState('')
  const [msg, setMsg] = useState('')
  const [last, setLast] = useState(null)

  useEffect(() => {
    api.deliverableTemplates(projectId)
      .then((d) => {
        setTemplates(d.templates || [])
        setAudiences(d.audiences || [])
        if (d.audiences?.length) setAudience(d.audiences[0].code)
      })
      .catch((e) => setMsg(String(e)))
  }, [projectId])

  const gen = async (template) => {
    setBusy(template)
    setMsg('')
    try {
      const res = await api.generateDeliverable(projectId, template, audience)
      setLast(res)
      setMsg(`已生成：${res.title}（${res.version}），可在「文档」标签页下载。`)
      onGenerated && onGenerated()
    } catch (e) {
      setMsg('生成失败：' + String(e))
    } finally {
      setBusy('')
    }
  }

  return (
    <div className="deliverables">
      <div className="board-panel full">
        <div className="panel-head">
          <span>成果模板输出（F-40）</span>
          <span className="badge">统一事实底稿 · 一键生成 Word</span>
        </div>
        <div className="panel-body" style={{ maxHeight: 'none' }}>
          <div className="dl-grid">
            {templates.filter((t) => t.code !== 'stakeholder').map((t) => (
              <button key={t.code} className="dl-card" disabled={!!busy} onClick={() => gen(t.code)}>
                <div className="dl-name">{t.name}</div>
                <div className="dl-desc">{busy === t.code ? '生成中…' : '点击生成 Word'}</div>
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="board-panel full" style={{ marginTop: 16 }}>
        <div className="panel-head">
          <span>干系人分层简报（F-39）</span>
          <span className="badge">同一事实 · 6 类切面</span>
        </div>
        <div className="panel-body" style={{ maxHeight: 'none' }}>
          <div className="dl-audience-row">
            <label>面向对象：</label>
            <select value={audience} onChange={(e) => setAudience(e.target.value)}>
              {audiences.map((a) => (
                <option key={a.code} value={a.code}>{a.name}</option>
              ))}
            </select>
            <button className="btn primary" disabled={!!busy} onClick={() => gen('stakeholder')}>
              {busy === 'stakeholder' ? '生成中…' : '生成干系人简报'}
            </button>
          </div>
          {audiences.find((a) => a.code === audience) && (
            <div className="dl-sections">
              关注切面：{audiences.find((a) => a.code === audience).sections.join(' / ')}
            </div>
          )}
        </div>
      </div>

      <div className="dl-notice">
        ⚠️ 人工确认关卡：Agent 只负责起草，正式外发 / 对外通知 / 合同财务 / 结论不确定等场景必须经人工确认。
        确认清单：检查事实 → 修改措辞 → 确认附件与对象 → 批准发送。
      </div>
      {msg && <div className={last ? 'dl-ok' : 'dl-err'}>{msg}</div>}
    </div>
  )
}
