import { Bot, Edit3, Plus, Search, ShieldCheck, Trash2, Wrench, X } from 'lucide-react'
import { FormEvent, useEffect, useState } from 'react'
import { api } from '../api'
import PageHeader from '../components/PageHeader'
import StatusBadge from '../components/StatusBadge'
import type { Agent } from '../types'

type AgentForm = {name:string;role:string;system_prompt:string;capabilities:string;tools:string;model:string;status:'active'|'disabled'}
const emptyAgent: AgentForm = { name:'', role:'', system_prompt:'', capabilities:'', tools:'local_knowledge', model:'deepseek-chat', status:'active' }

export default function Agents() {
  const [agents, setAgents] = useState<Agent[]>([])
  const [query, setQuery] = useState('')
  const [editing, setEditing] = useState<Agent | null>(null)
  const [form, setForm] = useState<AgentForm>(emptyAgent)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [message, setMessage] = useState('')
  const load = () => api<Agent[]>('/api/agents').then(setAgents)
  useEffect(() => { load() }, [])
  const visible = agents.filter(agent => `${agent.name}${agent.role}${agent.capabilities.join('')}`.toLowerCase().includes(query.toLowerCase()))
  const openCreate = () => { setEditing(null); setForm(emptyAgent); setMessage(''); setDialogOpen(true) }
  const openEdit = (agent: Agent) => { setEditing(agent); setForm({name:agent.name, role:agent.role, system_prompt:agent.system_prompt, capabilities:agent.capabilities.join('，'), tools:agent.tools.join('，'), model:agent.model, status:agent.status}); setMessage(''); setDialogOpen(true) }
  const save = async (event: FormEvent) => { event.preventDefault(); setMessage(''); const payload={...form, capabilities:form.capabilities.split(/[，,]/).map(v=>v.trim()).filter(Boolean), tools:form.tools.split(/[，,]/).map(v=>v.trim()).filter(Boolean)}; try { await api(editing ? `/api/agents/${editing.id}` : '/api/agents',{method:editing?'PUT':'POST',body:JSON.stringify(payload)}); setDialogOpen(false); await load() } catch(e) { setMessage(e instanceof Error ? e.message : '保存失败') } }
  const remove = async (agent: Agent) => { if (!confirm(`确定删除“${agent.name}”吗？被工作流使用的Agent会受到保护。`)) return; try { await api(`/api/agents/${agent.id}`,{method:'DELETE'}); await load() } catch(e) { alert(e instanceof Error ? e.message : '删除失败') } }
  return <>
    <PageHeader eyebrow="AGENT REGISTRY" title="Agent 团队管理" description="创建、编辑和管理智能体。运行任务时可按需选择，必要角色会自动锁定。" actions={<button className="button primary" onClick={openCreate}><Plus size={17}/>新建 Agent</button>}/>
    <div className="toolbar"><label className="search-box"><Search size={17}/><span className="sr-only">搜索Agent</span><input value={query} onChange={e => setQuery(e.target.value)} placeholder="搜索名称、角色或能力"/></label><span className="result-count">{visible.length} 个 Agent</span></div>
    <section className="agent-grid">{visible.map(agent => <article className="agent-card" key={agent.id}>
      <div className="agent-card-head"><div className="avatar"><Bot size={21}/></div><div><h2>{agent.name}</h2><p>{agent.role}</p></div><StatusBadge status={agent.status}/></div>
      <p className="prompt-preview">{agent.system_prompt}</p><div className="chip-row">{agent.capabilities.map(cap => <span className="chip" key={cap}>{cap}</span>)}</div>
      <div className="agent-meta"><span><Wrench size={14}/>{agent.tools.length} 个工具</span><span><ShieldCheck size={14}/>v{agent.version}</span><span>{agent.model}</span></div>
      <div className="card-actions"><button className="button tertiary" onClick={()=>openEdit(agent)}><Edit3 size={15}/>编辑</button><button className="button danger" onClick={()=>remove(agent)}><Trash2 size={15}/>删除</button></div>
    </article>)}</section>
    {dialogOpen && <div className="modal-backdrop"><section className="modal" role="dialog" aria-modal="true" aria-labelledby="agent-dialog-title"><div className="modal-head"><div><span className="eyebrow">AGENT CONFIG</span><h2 id="agent-dialog-title">{editing?'编辑 Agent':'新建 Agent'}</h2></div><button className="icon-button" aria-label="关闭" onClick={()=>setDialogOpen(false)}><X/></button></div><form onSubmit={save} className="form-grid">
      <label><span>名称</span><input required minLength={2} value={form.name} onChange={e=>setForm({...form,name:e.target.value})}/></label><label><span>角色</span><input required minLength={2} value={form.role} onChange={e=>setForm({...form,role:e.target.value})}/></label>
      <label className="full"><span>系统提示词</span><textarea required minLength={10} rows={5} value={form.system_prompt} onChange={e=>setForm({...form,system_prompt:e.target.value})}/></label><label><span>能力标签（逗号分隔）</span><input value={form.capabilities} onChange={e=>setForm({...form,capabilities:e.target.value})}/></label><label><span>工具（逗号分隔）</span><input value={form.tools} onChange={e=>setForm({...form,tools:e.target.value})}/></label><label><span>模型</span><input value={form.model} onChange={e=>setForm({...form,model:e.target.value})}/></label><label><span>状态</span><select value={form.status} onChange={e=>setForm({...form,status:e.target.value as 'active'|'disabled'})}><option value="active">启用</option><option value="disabled">停用</option></select></label>
      {message&&<p className="form-error full" role="alert">{message}</p>}<div className="modal-actions full"><button type="button" className="button tertiary" onClick={()=>setDialogOpen(false)}>取消</button><button className="button primary">保存 Agent</button></div>
    </form></section></div>}
  </>
}
