import { Activity, Bot, Boxes, FlaskConical, GitBranch, LayoutDashboard, Menu, PlayCircle, X } from 'lucide-react'
import { NavLink, Route, Routes } from 'react-router-dom'
import { useState } from 'react'
import Dashboard from './pages/Dashboard'
import Agents from './pages/Agents'
import Workflow from './pages/Workflow'
import NewRun from './pages/NewRun'
import RunDetail from './pages/RunDetail'
import GlobalAssistant from './components/GlobalAssistant'

const navigation = [
  { to: '/', label: '控制台', icon: LayoutDashboard },
  { to: '/runs/new', label: '发起任务', icon: PlayCircle },
  { to: '/agents', label: 'Agent 管理', icon: Bot },
  { to: '/workflow', label: '工作流编排', icon: GitBranch },
]

export default function App() {
  const [open, setOpen] = useState(false)
  return <div className="app-shell">
    <aside className={`sidebar ${open ? 'is-open' : ''}`}>
      <div className="brand"><div className="brand-mark"><Boxes size={20}/></div><div><strong>AgentFlow</strong><span>智能体编排平台</span></div></div>
      <button className="mobile-close icon-button" aria-label="关闭导航" onClick={() => setOpen(false)}><X size={20}/></button>
      <nav aria-label="主导航">
        <p className="nav-label">工作空间</p>
        {navigation.map(item => <NavLink key={item.to} to={item.to} end={item.to === '/'} onClick={() => setOpen(false)}>
          <item.icon size={18}/><span>{item.label}</span>
        </NavLink>)}
      </nav>
      <div className="sidebar-status"><span className="status-dot"/><div><strong>调度服务在线</strong><span>DeepSeek 兼容模式</span></div></div>
    </aside>
    <main>
      <header className="topbar">
        <button className="menu-button icon-button" aria-label="打开导航" onClick={() => setOpen(true)}><Menu size={21}/></button>
        <div className="context"><FlaskConical size={16}/><span>科研任务协作空间</span></div>
        <div className="system-chip"><Activity size={15}/><span>系统正常</span></div>
      </header>
      <div className="content">
        <Routes>
          <Route path="/" element={<Dashboard/>}/>
          <Route path="/agents" element={<Agents/>}/>
          <Route path="/workflow" element={<Workflow/>}/>
          <Route path="/runs/new" element={<NewRun/>}/>
          <Route path="/runs/:id" element={<RunDetail/>}/>
        </Routes>
      </div>
    </main>
    {open && <button className="overlay" aria-label="关闭导航遮罩" onClick={() => setOpen(false)}/>} 
    <GlobalAssistant/>
  </div>
}

