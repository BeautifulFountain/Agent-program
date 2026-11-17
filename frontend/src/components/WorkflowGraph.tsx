import { Background, Controls, Handle, Position, ReactFlow, type Edge, type Node, type NodeProps } from '@xyflow/react'
import { Bot, ShieldCheck } from 'lucide-react'
import { useMemo } from 'react'
import type { Workflow, WorkflowNode } from '../types'

type FlowData={label:string;kind:string;status?:string}

function AgentNode({data}:NodeProps<Node<FlowData>>){return <div className={`flow-node ${data.kind==='validator'?'validator':''}`}><Handle type="target" position={Position.Left}/><div className="flow-icon">{data.kind==='validator'?<ShieldCheck size={17}/>:<Bot size={17}/>}</div><div><strong>{data.label}</strong><span>{data.status?`运行状态：${data.status}`:data.kind==='validator'?'质量验证节点':'Agent 执行节点'}</span></div><Handle type="source" position={Position.Right}/></div>}

function arrange(nodes:WorkflowNode[]){const byId=new Map(nodes.map(node=>[node.id,node]));const depth=new Map<string,number>();const visiting=new Set<string>();const visit=(id:string):number=>{if(depth.has(id))return depth.get(id)!;if(visiting.has(id))return 0;visiting.add(id);const node=byId.get(id);const parents=node?.dependencies.filter(dep=>byId.has(dep))??[];const value=!parents.length?0:Math.max(...parents.map(visit))+1;visiting.delete(id);depth.set(id,value);return value};nodes.forEach(node=>visit(node.id));const groups=new Map<number,WorkflowNode[]>();nodes.forEach(node=>{const level=depth.get(node.id)??0;groups.set(level,[...(groups.get(level)??[]),node])});const positions=new Map<string,{x:number;y:number}>();groups.forEach((items,level)=>{const spacing=138;const start=245-((items.length-1)*spacing)/2;items.forEach((node,index)=>positions.set(node.id,{x:35+level*230,y:start+index*spacing}))});return positions}

export default function WorkflowGraph({workflow,statusByNode={},compact=false}:{workflow:Workflow;statusByNode?:Record<string,string>;compact?:boolean}){
  const positions=useMemo(()=>arrange(workflow.nodes),[workflow])
  const nodes=useMemo<Node<FlowData>[]>(()=>workflow.nodes.map(node=>({id:node.id,position:positions.get(node.id)??node.position,data:{label:node.label,kind:node.kind,status:statusByNode[node.id]},type:'agentNode'})),[workflow,positions,statusByNode])
  const edges=useMemo<Edge[]>(()=>workflow.nodes.flatMap(node=>node.dependencies.map(dep=>({id:`${dep}-${node.id}`,source:dep,target:node.id,animated:Boolean(statusByNode[node.id]),style:{stroke:'#7892b0'}}))),[workflow,statusByNode])
  return <div className={compact?'draft-flow-canvas':'flow-canvas flow-canvas-wide'}><ReactFlow nodes={nodes} edges={edges} nodeTypes={{agentNode:AgentNode}} fitView fitViewOptions={{padding:compact ? 0.2 : 0.14}} minZoom={compact ? 0.38 : 0.45} maxZoom={compact ? 0.9 : 1.25} nodesDraggable={!compact} nodesConnectable={false} elementsSelectable={!compact} panOnDrag={!compact} zoomOnScroll={!compact}><Background color="#dbe4ef" gap={20}/>{!compact&&<Controls/>}</ReactFlow></div>
}
