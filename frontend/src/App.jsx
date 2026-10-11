import { useState } from 'react'
import Sidebar from './components/Sidebar'
import ProjectList from './components/ProjectList'
import ProjectBoard from './components/ProjectBoard'
import DataSmart from './components/DataSmart'
import Planning from './components/Planning'

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

  const goDatasmart = () => setView('datasmart')
  const goPlanning = () => setView('planning')

  return (
    <div className="app">
      <Sidebar view={view} onHome={goHome} onDatasmart={goDatasmart} onPlanning={goPlanning} />
      <main className="main">
        {view === 'projects' && <ProjectList onOpenProject={openProject} />}
        {view === 'board' && currentProject && (
          <ProjectBoard project={currentProject} onBack={goHome} />
        )}
        {view === 'datasmart' && <DataSmart />}
        {view === 'planning' && <Planning />}
      </main>
    </div>
  )
}
