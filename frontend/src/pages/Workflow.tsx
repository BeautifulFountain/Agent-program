import { Background, Controls, Handle, MiniMap, Position, ReactFlow, type Edge, type Node, type NodeProps } from '@xyflow/react'
import { Bot, GitFork, RotateCcw, Save, ShieldCheck } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import PageHeader from '../components/PageHeader'
import type { Workflow as WorkflowType } from '../types'

type FlowData = { label: string; kind: string }
function AgentNode({ data }: NodeProps<Node<FlowData>>) { return <div className={`flow-node ${data.kind === 'validator' ? 'validator' : ''}`}><Handle type="target" position={Position.Left}/><div className="flow-icon">{data.kind === 'validator' ? <ShieldCheck size={17}/> : <Bot size={17}/>}</div><div><strong>{data.label}</strong><span>{data.kind === 'validator' ? '质量验证节点' : 'Agent 执行节点'}</span></div><Handle type="source" position={Position.Right}/></div> }

export default function Workflow() {
  const [workflow, setWorkflow] = useState<WorkflowType | null>(null)
  useEffect(() => { api<WorkflowType>('/api/workflows/research-demo').then(setWorkflow) }, [])
  const nodes = useMemo<Node<FlowData>[]>(() => workflow?.nodes.map(n => ({ id:n.id, position:n.position, data:{label:n.label,kind:n.kind}, type:'agentNode' })) ?? [], [workflow])
  const edges = useMemo<Edge[]>(() => workflow?.nodes.flatMap(n => n.dependencies.map(dep => ({ id:`${dep}-${n.id}`, source:dep, target:n.id, animated:n.id==='reviewer', style:{stroke:'#7892b0'} }))) ?? [], [workflow])
  return <>
    <PageHeader eyebrow="WORKFLOW DESIGNER" title="科研协作工作流" description="DAG驱动的动态调度，支持并行分支、质量验证与自动返工。" actions={<button className="button primary" disabled><Save size={17}/>保存版本</button>}/>
    <section className="workflow-layout">
      <div className="canvas-panel"><div className="canvas-toolbar"><span><GitFork size={16}/>版本 v{workflow?.version ?? 1}</span><span className="legend"><i className="agent-dot"/>Agent <i className="validator-dot"/>验证器</span></div><div className="flow-canvas"><ReactFlow nodes={nodes} edges={edges} nodeTypes={{agentNode:AgentNode}} fitView minZoom={0.4} maxZoom={1.5}><Background color="#dbe4ef" gap={20}/><MiniMap pannable zoomable/><Controls/></ReactFlow></div></div>
      <aside className="config-panel"><span className="eyebrow">RUN POLICY</span><h2>执行策略</h2><div className="config-item"><span>质量阈值</span><strong>{workflow?.quality_threshold ?? 80} 分</strong></div><div className="config-item"><span>最大循环</span><strong>{workflow?.max_loop_count ?? 3} 轮</strong></div><div className="config-item"><span>调度方式</span><strong>依赖就绪 + 并行</strong></div><div className="rework-card"><RotateCcw size={18}/><div><strong>Self-Loop</strong><p>评审分数低于阈值时，携带问题与建议定向返工报告节点。</p></div></div><p className="subtle-note">拖拽编辑与条件边保存将在下一迭代开放；当前工作流已可完整执行。</p></aside>
    </section>
  </>
}

