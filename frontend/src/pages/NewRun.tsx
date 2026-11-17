import { ArrowRight, Bot, Check, ExternalLink, FileText, GitBranch, LockKeyhole, Play, ShieldCheck, Sparkles } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import PageHeader from '../components/PageHeader'
import WorkflowGraph from '../components/WorkflowGraph'
import { workflowForSelection } from '../workflow-utils'
import type { Agent, DispatchRecommendation, TaskRun, Workflow } from '../types'

const required = new Set(['requirements','writer','reviewer'])
const examples = ['分析人工智能辅助高校科研管理的应用价值与风险，并形成研究报告', '研究校园碳排放核算方法，提出可执行的数据采集与评估框架', '评估多智能体协作对复杂科研任务效率和质量的影响']
const draftKey='agentflow:new-run-draft'
type RunDraft={task:string;agentIds:string[];format:'markdown'|'document'}
function readDraft():RunDraft|null{try{return JSON.parse(sessionStorage.getItem(draftKey)??'null') as RunDraft|null}catch{return null}}

export default function NewRun() {
  const restored=useMemo(()=>readDraft(),[]);const [task, setTask] = useState(restored?.task??examples[0]); const [agents,setAgents]=useState<Agent[]>([]); const [workflow,setWorkflow]=useState<Workflow|null>(null)
  const [selected,setSelected]=useState<Set<string>>(new Set(restored?.agentIds??[])); const [format,setFormat]=useState<'markdown'|'document'>(restored?.format??'markdown'); const [loading,setLoading]=useState(false); const [routing,setRouting]=useState(false); const [recommendation,setRecommendation]=useState<DispatchRecommendation|null>(null); const [error,setError]=useState(''); const navigate=useNavigate()
  useEffect(()=>{Promise.all([api<Agent[]>('/api/agents'),api<Workflow>('/api/workflows/research-demo')]).then(([a,w])=>{const active=a.filter(x=>x.status==='active');setAgents(active);setWorkflow(w);setSelected(current=>current.size?new Set([...current].filter(id=>active.some(agent=>agent.id===id)).concat(active.filter(agent=>required.has(agent.id)).map(agent=>agent.id))):new Set(active.filter(x=>required.has(x.id)).map(x=>x.id)))})},[])
  useEffect(()=>{if(agents.length)sessionStorage.setItem(draftKey,JSON.stringify({task,agentIds:[...selected],format} satisfies RunDraft))},[task,selected,format,agents.length])
  const selectedWorkflow=useMemo(()=>workflow?workflowForSelection(workflow,selected,agents):null,[workflow,selected,agents])
  const toggle=(id:string)=>{if(required.has(id))return;setSelected(old=>{const next=new Set(old);if(next.has(id))next.delete(id);else next.add(id);return next})}
  const recommend=async()=>{if(task.trim().length<10)return;setRouting(true);setError('');try{const result=await api<DispatchRecommendation>('/api/dispatch/recommend',{method:'POST',body:JSON.stringify({task})});setRecommendation(result);setSelected(new Set(result.agent_ids))}catch(e){setError(e instanceof Error?e.message:'调度推荐失败')}finally{setRouting(false)}}
  const submit=async()=>{setLoading(true);setError('');try{const run=await api<TaskRun>('/api/runs',{method:'POST',body:JSON.stringify({task,workflow_id:'research-demo',agent_ids:[...selected],output_format:format})});navigate(`/runs/${run.id}`)}catch(e){setError(e instanceof Error?e.message:'创建失败');setLoading(false)}}
  const inspectWorkflow=()=>navigate('/workflow?source=draft',{state:{from:'/runs/new'}})
  return <><PageHeader eyebrow="NEW RESEARCH RUN" title="发起科研协作任务" description="输入研究任务或文档要求，选择协作Agent，确认流程后开始执行。"/>
    <div className="run-create-grid"><section className="panel run-form"><label htmlFor="task"><span>研究任务或文档要求</span><small>请写明研究对象、交付形式、范围与约束；需求分析后仍会暂停等待人工确认。</small></label><textarea id="task" value={task} onChange={e=>{setTask(e.target.value);setRecommendation(null)}} rows={7}/><div className="task-routing-row"><div className="examples"><span>示例任务</span>{examples.map(item=><button key={item} onClick={()=>{setTask(item);setRecommendation(null)}}>{item}</button>)}</div><button className="button secondary" disabled={routing||task.trim().length<10} onClick={()=>void recommend()}><Sparkles size={16}/>{routing?'正在生成…':'生成协作方案'}</button></div>
      <div className="section-heading agent-section-heading"><div><h2>协作 Agent 配置</h2><p>系统依据任务特征、角色能力与流程依赖生成建议，你可以继续调整。</p></div><span>{selected.size} / {agents.length} 已选</span></div>
      {recommendation&&<div className="dispatch-notice"><span className="dispatch-icon"><Sparkles size={16}/></span><div><strong>智能调度方案已生成</strong><p>{recommendation.strategy} · 已匹配 {recommendation.agent_ids.length} 个协作角色 · 流程预览已同步更新</p></div><span className="dispatch-status"><Check size={13}/>已就绪</span></div>}
      <div className="agent-picker">{agents.map(agent=><label key={agent.id} className={selected.has(agent.id)?'selected':''}><input type="checkbox" checked={selected.has(agent.id)} disabled={required.has(agent.id)} onChange={()=>toggle(agent.id)}/><span className="picker-icon"><Bot size={17}/></span><span><strong>{agent.name}</strong><small>{recommendation?.reasons[agent.id]??agent.role}</small>{recommendation?.matched_keywords[agent.id]?.length?<em>任务匹配：{recommendation.matched_keywords[agent.id].join('、')}</em>:null}</span>{required.has(agent.id)&&<LockKeyhole size={14} aria-label="必要Agent"/>}</label>)}</div>
      <fieldset className="format-picker"><legend>最终输出格式</legend><label><input type="radio" checked={format==='markdown'} onChange={()=>setFormat('markdown')}/><FileText size={16}/>Markdown（.md）</label><label><input type="radio" checked={format==='document'} onChange={()=>setFormat('document')}/><FileText size={16}/>文档格式（可打印）</label></fieldset>
      {error&&<p className="form-error" role="alert">{error}</p>}<button className="button primary launch" disabled={loading||task.trim().length<10||!workflow} onClick={submit}>{loading?'正在创建…':<><Play size={18}/>启动多智能体协作<ArrowRight size={17}/></>}</button></section>
      <aside className="panel run-summary"><div className="workflow-preview-heading"><div><span className="eyebrow">WORKFLOW PREVIEW</span><h2>本次 Agent 流程图</h2></div><button type="button" className="button tertiary workflow-open" onClick={inspectWorkflow}><ExternalLink size={15}/>进入工作流编排</button></div>{selectedWorkflow&&<WorkflowGraph workflow={selectedWorkflow} compact/>}<div className="policy-box"><p><span>质量阈值</span><strong>{workflow?.quality_threshold??80} 分</strong></p><p><span>最多返工</span><strong>{workflow?.max_loop_count??3} 轮</strong></p><p><span>执行节点</span><strong>{selected.size} 个</strong></p><p><span>人工确认</span><strong><Check size={13}/>已启用</strong></p></div><p className="flow-note"><GitBranch size={15}/>流程图会随 Agent 选择实时更新；同层节点表示可并行执行。</p><p className="flow-note"><ShieldCheck size={15}/>进入编排页后可以查看大图，并返回继续编辑当前任务。</p></aside>
    </div></>
}
