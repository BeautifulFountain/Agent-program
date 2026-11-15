import { Bot, Plus, Search, ShieldCheck, Wrench } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from '../api'
import PageHeader from '../components/PageHeader'
import StatusBadge from '../components/StatusBadge'
import type { Agent } from '../types'

export default function Agents() {
  const [agents, setAgents] = useState<Agent[]>([])
  const [query, setQuery] = useState('')
  useEffect(() => { api<Agent[]>('/api/agents').then(setAgents) }, [])
  const visible = agents.filter(agent => `${agent.name}${agent.role}${agent.capabilities.join('')}`.toLowerCase().includes(query.toLowerCase()))
  return <>
    <PageHeader eyebrow="AGENT REGISTRY" title="Agent 团队管理" description="管理角色、能力、工具和提示词版本，构建可调度的智能体团队。" actions={<button className="button primary" disabled title="首版通过API添加"><Plus size={17}/>新建 Agent</button>}/>
    <div className="toolbar"><label className="search-box"><Search size={17}/><span className="sr-only">搜索Agent</span><input value={query} onChange={e => setQuery(e.target.value)} placeholder="搜索名称、角色或能力"/></label><span className="result-count">{visible.length} 个 Agent</span></div>
    <section className="agent-grid">{visible.map(agent => <article className="agent-card" key={agent.id}>
      <div className="agent-card-head"><div className="avatar"><Bot size={21}/></div><div><h2>{agent.name}</h2><p>{agent.role}</p></div><StatusBadge status={agent.status}/></div>
      <p className="prompt-preview">{agent.system_prompt}</p>
      <div className="chip-row">{agent.capabilities.map(cap => <span className="chip" key={cap}>{cap}</span>)}</div>
      <div className="agent-meta"><span><Wrench size={14}/>{agent.tools.length} 个工具</span><span><ShieldCheck size={14}/>v{agent.version}</span><span>{agent.model}</span></div>
    </article>)}</section>
  </>
}

