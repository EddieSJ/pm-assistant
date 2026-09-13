import { useState } from 'react'
import Sidebar from './components/Sidebar'
import ProjectList from './components/ProjectList'
import ProjectBoard from './components/ProjectBoard'

export default function App() {
  const [view, setView] = useState('projects')
  const [currentProject, setCurrentProject] = useState(null)

  const openProject = (project) => {
    setCurrentProject(project)
    setView('board')
  }

  const goHome = () => {
    setCurrentProject(null)
    setView('projects')
  }

  return (
    <div className="app">
      <Sidebar view={view} onHome={goHome} />
      <main className="main">
        {view === 'projects' && <ProjectList onOpenProject={openProject} />}
        {view === 'board' && currentProject && (
          <ProjectBoard project={currentProject} onBack={goHome} />
        )}
      </main>
    </div>
  )
}
