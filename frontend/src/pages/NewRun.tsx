import { ArrowRight, Check, FlaskConical, GitBranch, Play, ShieldCheck } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import PageHeader from '../components/PageHeader'
import type { TaskRun } from '../types'

const examples = ['分析人工智能辅助高校科研管理的应用价值与风险，并形成研究报告', '研究校园碳排放核算方法，提出可执行的数据采集与评估框架', '评估多智能体协作对复杂科研任务效率和质量的影响']

export default function NewRun() {
  const [task, setTask] = useState(examples[0])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const navigate = useNavigate()
  const submit = async () => { setLoading(true); setError(''); try { const run = await api<TaskRun>('/api/runs', {method:'POST', body:JSON.stringify({task,workflow_id:'research-demo'})}); navigate(`/runs/${run.id}`) } catch(e) { setError(e instanceof Error ? e.message : '创建失败'); setLoading(false) } }
  return <>
    <PageHeader eyebrow="NEW RESEARCH RUN" title="发起科研协作任务" description="描述研究目标，调度器会组织多个Agent规划、并行研究、撰写与验证。"/>
    <div className="run-create-grid"><section className="panel run-form"><label htmlFor="task"><span>研究任务</span><small>建议包含研究对象、期望成果和约束条件</small></label><textarea id="task" value={task} onChange={e => setTask(e.target.value)} rows={9}/><div className="examples"><span>示例任务</span>{examples.map(item => <button key={item} onClick={() => setTask(item)}>{item}</button>)}</div>{error && <p className="form-error" role="alert">{error}</p>}<button className="button primary launch" disabled={loading || task.trim().length < 10} onClick={submit}>{loading ? '正在创建…' : <><Play size={18}/>启动多智能体协作<ArrowRight size={17}/></>}</button></section>
      <aside className="panel run-summary"><span className="eyebrow">EXECUTION PLAN</span><h2>本次运行将执行</h2><ul>{[['需求与规划',FlaskConical],['双分支并行研究',GitBranch],['事实交叉核验',ShieldCheck],['质量评分与自动返工',Check]].map(([label,Icon],i) => <li key={label as string}><span>{i+1}</span><Icon size={18}/><strong>{label as string}</strong></li>)}</ul><div className="policy-box"><p><span>质量阈值</span><strong>80 分</strong></p><p><span>最多返工</span><strong>3 轮</strong></p><p><span>执行节点</span><strong>7 个</strong></p></div></aside>
    </div>
  </>
}

