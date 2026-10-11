// 后端接口前缀。
// - 本地开发（vite dev / 后端同源托管）：默认走 `/api`，由 vite proxy 或 FastAPI 静态托管处理；
// - 分离部署（前端静态托管 + 后端云托管）：构建时用 VITE_API_BASE=https://<云托管域名>/api 注入。
const API_BASE = import.meta.env.VITE_API_BASE || '/api'

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
  // 成果输出（F-39 干系人分层简报 / F-40 多成果模板）
  deliverableTemplates: (id) => request(`/projects/${id}/deliverables/templates`),
  generateDeliverable: (id, template, audience = 'owner') =>
    request(`/projects/${id}/deliverables/generate`, {
      method: 'POST', body: JSON.stringify({ template, audience }),
    }),
  // 记忆治理（可更新 / 可纠错 / 可失效）
  memoryLongterm: (id, includeInactive = true) =>
    request(`/projects/${id}/memory/longterm?include_inactive=${includeInactive}`),
  memoryCreate: (id, data) =>
    request(`/projects/${id}/memory/longterm`, { method: 'POST', body: JSON.stringify(data) }),
  memoryUpdate: (id, mid, data) =>
    request(`/projects/${id}/memory/longterm/${mid}`, { method: 'PUT', body: JSON.stringify(data) }),
  memoryCorrect: (id, mid, data) =>
    request(`/projects/${id}/memory/longterm/${mid}/correct`, { method: 'POST', body: JSON.stringify(data) }),
  memoryInvalidate: (id, mid, reason) =>
    request(`/projects/${id}/memory/longterm/${mid}/invalidate`, { method: 'POST', body: JSON.stringify({ reason }) }),
  memoryAudit: (id) => request(`/projects/${id}/memory/audit`),
  memoryTask: (id) => request(`/projects/${id}/memory/task`),
  // 计划与资源智能调度（课程3，F-63~F-90）
  planRun: (id) => request(`/projects/${id}/planning/run`, { method: 'POST' }),
  planRunStatus: (id, jobId) => request(`/projects/${id}/planning/run/status/${jobId}`),
  planOverview: (id) => request(`/projects/${id}/planning/overview`),
  planBoard: (id) => request(`/projects/${id}/planning/board`),
  planMaterials: (id) => request(`/projects/${id}/planning/materials`),
  planChecks: (id) => request(`/projects/${id}/planning/checks`),
  planEffectiveness: (id) => request(`/projects/${id}/planning/effectiveness`),
  planWbs: (id) => request(`/projects/${id}/planning/wbs`),
  planConstraints: (id) => request(`/projects/${id}/planning/constraints`),
  planCalendar: (id) => request(`/projects/${id}/planning/calendar`),
  planSchedule: (id, version = 'V1') => request(`/projects/${id}/planning/schedule?version=${version}`),
  planCriticalPath: (id, version = 'V1') => request(`/projects/${id}/planning/critical-path?version=${version}`),
  planResourceLoad: (id, version = 'V1') => request(`/projects/${id}/planning/resource-load?version=${version}`),
  planAllocation: (id) => request(`/projects/${id}/planning/allocation`),
  planConflicts: (id) => request(`/projects/${id}/planning/conflicts`),
  planSetConflictStatus: (id, cid, status) =>
    request(`/projects/${id}/planning/conflicts/${cid}/status`, {
      method: 'POST', body: JSON.stringify({ status }),
    }),
  planVersions: (id) => request(`/projects/${id}/planning/versions`),
  planEvents: (id) => request(`/projects/${id}/planning/events`),
  planApplyEvent: (id, eventId) =>
    request(`/projects/${id}/planning/events/${eventId}/apply`, { method: 'POST' }),
  planScenarios: (id) => request(`/projects/${id}/planning/scenarios`),
  planAdvices: (id) => request(`/projects/${id}/planning/advices`),
  planConfirmations: (id) => request(`/projects/${id}/planning/confirmations`),
  planEvidence: (id) => request(`/projects/${id}/planning/evidence`),
  planStops: (id) => request(`/projects/${id}/planning/stops`),
}
