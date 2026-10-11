const API_BASE = '/api'

async function request(path, options = {}) {
  const res = await fetch(API_BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const data = await res.json()
      detail = data.detail || detail
    } catch { /* ignore */ }
    throw new Error(detail)
  }
  return res.json()
}

export const api = {
  health: () => request('/health'),
  // 项目
  listProjects: () => request('/projects'),
  getProject: (id) => request(`/projects/${id}`),
  createProject: (data) => request('/projects', { method: 'POST', body: JSON.stringify(data) }),
  updateProject: (id, data) => request(`/projects/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteProject: (id) => request(`/projects/${id}`, { method: 'DELETE' }),
  browseDir: (path) => request(`/projects/browse/dirs?path=${encodeURIComponent(path || '')}`),
  // 分析 & 看板
  analyze: (id) => request(`/projects/${id}/analyze`, { method: 'POST' }),
  analyzeStatus: (jobId) => request(`/projects/analyze/status/${jobId}`),
  board: (id) => request(`/projects/${id}/board`),
  // 聊天
  chat: (id, message, sessionId = 'default') =>
    request(`/projects/${id}/chat`, { method: 'POST', body: JSON.stringify({ message, session_id: sessionId }) }),
  chatHistory: (id) => request(`/projects/${id}/chat/history`),
  // 文档
  generateSummary: (id) => request(`/projects/${id}/documents/summary`, { method: 'POST' }),
  generateDoc: (id, title, content) =>
    request(`/projects/${id}/documents/generate`, { method: 'POST', body: JSON.stringify({ title, content }) }),
  deleteDocument: (docId) => request(`/projects/documents/${docId}`, { method: 'DELETE' }),
  // 数据智能与决策
  runDataSmart: (id) => request(`/projects/${id}/datasmart/run`, { method: 'POST' }),
  dataSmartRunStatus: (id, jobId) => request(`/projects/${id}/datasmart/run/status/${jobId}`),
  dataSmartOverview: (id) => request(`/projects/${id}/datasmart/overview`),
  dataSmartBoard: (id, kind) => request(`/projects/${id}/datasmart/board/${kind}`),
  dataSmartSnapshots: (id) => request(`/projects/${id}/datasmart/snapshots`),
  dataSmartAdvise: (id) => request(`/projects/${id}/datasmart/advise`, { method: 'POST' }),
  dataSmartAlerts: (id) => request(`/projects/${id}/datasmart/alerts`),
  dataSmartCleanlogs: (id) => request(`/projects/${id}/datasmart/cleanlogs`),
  dataSmartForecast: (id) => request(`/projects/${id}/datasmart/forecast`),
}
