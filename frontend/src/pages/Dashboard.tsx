import { ArrowRight, CheckCircle2, Clock3, Cpu, Plus, RotateCcw, Workflow as WorkflowIcon } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import PageHeader from '../components/PageHeader'
import StatusBadge from '../components/StatusBadge'
import type { Agent, TaskRun } from '../types'

export default function Dashboard() {
  const [runs, setRuns] = useState<TaskRun[]>([])
  const [agents, setAgents] = useState<Agent[]>([])
  useEffect(() => { Promise.all([api<TaskRun[]>('/api/runs'), api<Agent[]>('/api/agents')]).then(([r, a]) => {setRuns(r); setAgents(a)}).catch(() => {}) }, [])
  const completed = runs.filter(r => r.status === 'completed')
  const stats = useMemo(() => [
    { label: '累计任务', value: runs.length, note: '完整运行记录', icon: WorkflowIcon },
    { label: '活跃 Agent', value: agents.filter(a => a.status === 'active').length, note: '覆盖研究全流程', icon: Cpu },
    { label: '任务成功率', value: runs.length ? `${Math.round(completed.length / runs.length * 100)}%` : '—', note: '达到质量阈值', icon: CheckCircle2 },
    { label: '自动返工', value: runs.reduce((sum, r) => sum + r.loop_count, 0), note: 'Self-Loop 优化次数', icon: RotateCcw },
  ], [runs, agents, completed.length])
  return <>
    <PageHeader eyebrow="OVERVIEW" title="多智能体运行控制台" description="统一观察科研任务的编排、调度、验证和反馈优化过程。" actions={<Link className="button primary" to="/runs/new"><Plus size={17}/>发起任务</Link>}/>
    <section className="stats-grid" aria-label="运行指标">{stats.map(item => <article className="stat-card" key={item.label}><div className="stat-top"><span>{item.label}</span><item.icon size={18}/></div><strong>{item.value}</strong><small>{item.note}</small></article>)}</section>
    <div className="dashboard-grid">
      <section className="panel span-2"><div className="panel-header"><div><h2>最近任务</h2><p>查看执行状态、质量评分与循环次数</p></div><Link to="/runs/new" className="text-link">新建任务 <ArrowRight size={15}/></Link></div>
        {runs.length ? <div className="table-wrap"><table><thead><tr><th>任务</th><th>状态</th><th>质量分</th><th>循环</th><th>Token</th><th></th></tr></thead><tbody>{runs.slice(0,6).map(run => <tr key={run.id}><td><strong>{run.task.slice(0,34)}</strong><small>{new Date(run.started_at).toLocaleString()}</small></td><td><StatusBadge status={run.status}/></td><td>{run.score ?? '—'}</td><td>{run.loop_count}</td><td>{run.token_usage}</td><td><Link className="row-link" to={`/runs/${run.id}`}>详情</Link></td></tr>)}</tbody></table></div> : <div className="empty-state"><Clock3/><h3>还没有运行记录</h3><p>从科研问题开始，观察多个Agent如何协同完成任务。</p><Link className="button secondary" to="/runs/new">创建首个任务</Link></div>}
      </section>
      <section className="panel"><div className="panel-header"><div><h2>默认工作流</h2><p>科研协作质量闭环</p></div></div><ol className="mini-flow">{['需求澄清','研究规划','并行研究','报告整合','事实核验','质量评审'].map((label, index) => <li key={label}><span>{index+1}</span><div><strong>{label}</strong><small>{index === 2 ? '文献与数据双分支' : index === 5 ? '低于80分自动返工' : '自动调度执行'}</small></div></li>)}</ol><Link className="button tertiary full" to="/workflow">查看工作流</Link></section>
    </div>
  </>
}

