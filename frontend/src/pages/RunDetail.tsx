import { AlertTriangle, CheckCircle2, ChevronDown, Circle, Clock3, RotateCcw, Square, Zap } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../api'
import PageHeader from '../components/PageHeader'
import StatusBadge from '../components/StatusBadge'
import type { NodeRun, TaskRun } from '../types'

function NodeRecord({ node }: { node: NodeRun }) { const [open,setOpen]=useState(false); return <article className="node-record"><button onClick={()=>setOpen(!open)} aria-expanded={open}><span className={`node-state ${node.status}`}>{node.status === 'completed' ? <CheckCircle2/> : node.status === 'failed' ? <AlertTriangle/> : <Circle/>}</span><div><strong>{node.label}</strong><span>第 {node.loop+1} 轮 · {node.duration_ms ?? '—'} ms · 重试 {node.retry_count}</span></div>{node.score != null && <b>{node.score} 分</b>}<ChevronDown className={open?'rotate':''}/></button>{open && <div className="node-output"><h4>节点输出</h4><pre>{node.output ?? node.error ?? '执行中…'}</pre></div>}</article> }

export default function RunDetail() {
  const {id}=useParams(); const [run,setRun]=useState<TaskRun|null>(null); const [error,setError]=useState('')
  useEffect(()=>{ let timer:number; const load=()=>api<TaskRun>(`/api/runs/${id}`).then(data=>{setRun(data); if(!['completed','failed','cancelled','needs_review'].includes(data.status)) timer=window.setTimeout(load,700)}).catch(e=>setError(e.message)); load(); return()=>clearTimeout(timer)},[id])
  const cancel=()=>api(`/api/runs/${id}/cancel`,{method:'POST'}).catch(()=>{})
  if(error) return <div className="error-panel"><AlertTriangle/><h2>无法加载任务</h2><p>{error}</p></div>
  if(!run) return <div className="loading-panel"><span className="spinner"/>加载运行数据…</div>
  const latest = Object.values(run.node_runs.reduce<Record<string,NodeRun>>((acc,n)=>{acc[`${n.node_id}-${n.loop}`]=n; return acc},{}))
  const dimensions = run.validation?.dimensions ?? run.validation?.dimension_scores ?? {}
  const issues = (run.validation?.issues ?? []).map(item => {
    if (typeof item === 'string') return item
    const severity = item.severity ? `[${item.severity}] ` : ''
    const description = item.description ?? '未提供问题描述'
    const suggestion = item.suggestion ? `；建议：${item.suggestion}` : ''
    return `${severity}${description}${suggestion}`
  })
  const suggestions = run.validation?.suggestions ?? run.validation?.improvement_suggestions ?? []
  return <>
    <PageHeader eyebrow={`RUN ${run.id}`} title="任务运行详情" description={run.task} actions={<div className="action-row"><StatusBadge status={run.status}/>{run.status==='running'&&<button className="button danger" onClick={cancel}><Square size={15}/>停止任务</button>}</div>}/>
    <section className="run-metrics"><div><span>执行进度</span><strong>{run.progress}%</strong><div className="progress"><i style={{width:`${run.progress}%`}}/></div></div><div><span>质量评分</span><strong>{run.score ?? '—'}</strong><small>/ 100</small></div><div><span>Self-Loop</span><strong>{run.loop_count}</strong><small>轮返工</small></div><div><span>Token 使用</span><strong>{run.token_usage}</strong><small>累计</small></div></section>
    <div className="run-detail-grid"><section className="panel"><div className="panel-header"><div><h2>执行时间线</h2><p>所有中间结果、耗时和重试均被记录</p></div><span className="live-indicator"><i/>实时更新</span></div><div className="timeline">{latest.map(node=><NodeRecord node={node} key={node.id}/>)}{run.status==='queued'&&<div className="pending-line"><Clock3/>等待调度器分配节点</div>}</div></section>
      <aside className="result-column">{run.loop_count>0&&<section className="panel rework-summary"><div className="summary-icon"><RotateCcw/></div><div><span className="eyebrow">FEEDBACK LOOP</span><h2>自动返工已触发</h2><p>系统根据评审问题定向修订报告并重新核验。</p></div></section>}{run.validation&&<section className="panel"><div className="panel-header"><div><h2>质量评审</h2><p>交叉验证结果</p></div><span className="score-ring">{run.validation.score}</span></div>{Object.keys(dimensions).length>0&&<div className="dimension-list">{Object.entries(dimensions).map(([k,v])=><div key={k}><span>{k}</span><div><i style={{width:`${v}%`}}/></div><strong>{v}</strong></div>)}</div>}<ul className="issue-list">{[...issues,...suggestions].map((item,index)=><li key={`${index}-${item}`}><Zap size={15}/>{item}</li>)}</ul></section>}{run.final_output&&<section className="panel final-output"><div className="panel-header"><div><h2>最终研究成果</h2><p>已通过编排与验证闭环</p></div></div><pre>{run.final_output}</pre></section>}</aside></div>
  </>
}

