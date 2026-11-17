import { ArrowLeft, GitFork } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import PageHeader from '../components/PageHeader'
import WorkflowGraph from '../components/WorkflowGraph'
import { workflowForSelection } from '../workflow-utils'
import type { Agent, TaskRun, Workflow as WorkflowType } from '../types'

const draftKey='agentflow:new-run-draft'
type RunDraft={task:string;agentIds:string[];format:'markdown'|'document'}
function readDraft():RunDraft|null{try{return JSON.parse(sessionStorage.getItem(draftKey)??'null') as RunDraft|null}catch{return null}}

export default function Workflow(){
 const[base,setBase]=useState<WorkflowType|null>(null);const[runs,setRuns]=useState<TaskRun[]>([]);const[agents,setAgents]=useState<Agent[]>([]);const[selected,setSelected]=useState('template');const[params]=useSearchParams();const location=useLocation();const navigate=useNavigate();const draftMode=params.get('source')==='draft';const draft=useMemo(()=>draftMode?readDraft():null,[draftMode])
 useEffect(()=>{Promise.all([api<WorkflowType>('/api/workflows/research-demo'),api<TaskRun[]>('/api/runs'),api<Agent[]>('/api/agents')]).then(([w,r,a])=>{setBase(w);setRuns(r);setAgents(a.filter(agent=>agent.status==='active'))})},[])
 const run=!draftMode&&selected!=='template'?runs.find(item=>item.id===selected)??null:null
 const workflow=useMemo(()=>{if(!base)return null;if(draftMode&&draft)return workflowForSelection(base,new Set(draft.agentIds),agents);return run?.workflow_snapshot??base},[base,draftMode,draft,agents,run])
 const statusByNode=useMemo(()=>Object.fromEntries((run?.node_runs??[]).map(item=>[item.node_id,item.status])),[run])
 const goBack=()=>navigate((location.state as {from?:string}|null)?.from??'/runs/new')
 const actions=draftMode?<button type="button" className="button tertiary" onClick={goBack}><ArrowLeft size={16}/>返回发起任务</button>:<label className="workflow-select"><span>查看流程</span><select value={selected} onChange={event=>setSelected(event.target.value)}><option value="template">默认工作流模板</option>{runs.map(item=><option key={item.id} value={item.id}>{item.task.slice(0,36)}</option>)}</select></label>
 return <><PageHeader eyebrow="WORKFLOW VIEWER" title={draftMode?'本次任务工作流预览':'任务工作流编排'} description={draftMode?'当前流程根据发起任务页所选 Agent 实时生成；返回后可继续调整，不会丢失草稿。':'选择默认模板或任一历史任务，查看该任务实际使用的 Agent 流程快照。'} actions={actions}/>
 <section className="workflow-stack"><div className="policy-bar"><div className="policy-heading"><span className="eyebrow">RUN POLICY</span><strong>{draftMode?'待启动任务执行策略':run?'当前任务执行策略':'模板执行策略'}</strong></div>{((draftMode&&draft)||run)&&<div className="policy-task"><strong>{draftMode?draft?.task:run?.task}</strong><span>{draftMode?'尚未启动':run?.status} · {workflow?.nodes.length??0} 个节点</span></div>}<div className="policy-stat"><span>质量阈值</span><strong>{workflow?.quality_threshold??80} 分</strong></div><div className="policy-stat"><span>最大循环</span><strong>{workflow?.max_loop_count??3} 轮</strong></div><div className="policy-stat"><span>调度方式</span><strong>依赖就绪 + 并行</strong></div><div className="policy-stat policy-outcome"><span>成果策略</span><strong>保留最高分版本</strong></div></div>
 <div className="canvas-panel"><div className="canvas-toolbar"><span><GitFork size={16}/>{draftMode?'当前任务草稿':run?`任务 ${run.id.toUpperCase()}`:`模板 v${workflow?.version??1}`}</span><span className="legend"><i className="agent-dot"/>Agent <i className="validator-dot"/>验证器</span></div>{workflow&&<WorkflowGraph workflow={workflow} statusByNode={statusByNode}/>}</div>{draftMode&&<div className="workflow-return-bar"><div><strong>流程确认完成后返回发起任务</strong><span>任务内容、Agent 选择和输出格式均已保留。</span></div><button type="button" className="button primary" onClick={goBack}><ArrowLeft size={16}/>返回并继续配置</button></div>}</section></>
}
