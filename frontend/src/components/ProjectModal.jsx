import { useState } from 'react'
import { api } from '../api'

const SUPPORTED = ['md', 'pdf', 'docx', 'xlsx', 'txt']

export default function ProjectModal({ initial, onClose, onSave }) {
  const [name, setName] = useState(initial?.name || '')
  const [description, setDescription] = useState(initial?.description || '')
  const [folderPath, setFolderPath] = useState(initial?.folder_path || '')
  const [browsing, setBrowsing] = useState(false)
  const [dirData, setDirData] = useState(null)
  const [loadingDir, setLoadingDir] = useState(false)
  const [saving, setSaving] = useState(false)

  const loadDir = async (path) => {
    setLoadingDir(true)
    try {
      const data = await api.browseDir(path)
      setDirData(data)
      setFolderPath(data.path)
    } catch (e) {
      alert(e.message)
    } finally {
      setLoadingDir(false)
    }
  }

  const openBrowser = async () => {
    setBrowsing(true)
    await loadDir(folderPath || '')
  }

  const handleSubmit = async () => {
    if (!name.trim()) { alert('请输入项目名称'); return }
    if (!folderPath.trim()) { alert('请选择项目文件夹'); return }
    setSaving(true)
    try {
      await onSave({ name: name.trim(), description, folder_path: folderPath.trim() })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>{initial ? '编辑项目' : '新建项目'}</h2>
          <button className="icon-btn" onClick={onClose}>✕</button>
        </div>
        <div className="modal-body">
          <div className="form-group">
            <label>项目名称 *</label>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="例如：澄岳DCM项目" autoFocus />
          </div>

          <div className="form-group">
            <label>项目文件夹 *</label>
            <div style={{ display: 'flex', gap: 8 }}>
              <input
                value={folderPath}
                onChange={(e) => setFolderPath(e.target.value)}
                placeholder="选择或输入文件夹路径"
              />
              <button className="btn" onClick={openBrowser}>浏览…</button>
            </div>
            <div className="hint">该文件夹可包含标书、合同、财务、人事、干系人沟通等项目文档</div>
          </div>

          {browsing && (
            <div className="dir-picker" style={{ marginTop: 8, marginBottom: 16 }}>
              <div className="current">
                {loadingDir ? '加载中…' : dirData?.path}
              </div>
              <div className="list">
                {dirData?.parent && dirData.parent !== dirData.path && (
                  <div className="dir-item" onClick={() => loadDir(dirData.parent)}>
                    <span className="icon">📁</span> ..（返回上级）
                  </div>
                )}
                {dirData?.dirs.map((d) => (
                  <div key={d.path} className="dir-item" onClick={() => loadDir(d.path)}>
                    <span className="icon">📁</span> {d.name}
                  </div>
                ))}
                {dirData?.files
                  .filter((f) => SUPPORTED.includes(f.ext))
                  .map((f) => (
                    <div key={f.path} className="dir-item file">
                      <span className="icon">📄</span> {f.name}
                    </div>
                  ))}
              </div>
              <div style={{ padding: 10, borderTop: '1px solid var(--border)', display: 'flex', gap: 8 }}>
                <button
                  className="btn primary"
                  onClick={() => { setFolderPath(dirData?.path || folderPath); setBrowsing(false) }}
                >
                  选择此文件夹
                </button>
                <button className="btn" onClick={() => setBrowsing(false)}>收起</button>
              </div>
            </div>
          )}

          <div className="form-group">
            <label>描述（可选）</label>
            <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3} placeholder="项目简介" />
          </div>
        </div>
        <div className="modal-footer">
          <button className="btn" onClick={onClose}>取消</button>
          <button className="btn primary" onClick={handleSubmit} disabled={saving}>
            {saving ? '保存中…' : '保存'}
          </button>
        </div>
      </div>
    </div>
  )
}
