export default function Sidebar({ view, onHome }) {
  return (
    <aside className="sidebar">
      <div className="logo">
        <span className="dot">项</span>
        项目管理智能助手
      </div>
      <div
        className={`nav-item ${view === 'projects' ? 'active' : ''}`}
        onClick={onHome}
      >
        <span>📁</span> 项目全局管理
      </div>
      <div className="footer">
        私人智能体 · 本地部署<br />
        有据可依 · 有理有据<br />
        有记忆 · 有标准
      </div>
    </aside>
  )
}
