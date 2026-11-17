import type { Agent, Workflow } from './types'

export function workflowForSelection(workflow:Workflow, selected:Set<string>, agents:Agent[]):Workflow{
  const copy:Workflow={...workflow,nodes:workflow.nodes.filter(node=>selected.has(node.agent_id)).map(node=>({...node,dependencies:[...node.dependencies]}))}
  const existingAgentIds=new Set(copy.nodes.map(node=>node.agent_id))
  agents.filter(agent=>selected.has(agent.id)&&!existingAgentIds.has(agent.id)).forEach((agent,index)=>copy.nodes.push({id:`custom-${agent.id}`,label:agent.name,agent_id:agent.id,kind:'agent',dependencies:['requirements'],position:{x:500,y:420+index*120}}))
  const kept=new Set(copy.nodes.map(node=>node.id))
  copy.nodes.forEach(node=>{node.dependencies=node.dependencies.filter(dep=>kept.has(dep));if(['literature','analyst'].includes(node.id)&&!node.dependencies.length)node.dependencies=['requirements']})
  const writer=copy.nodes.find(node=>node.id==='writer')
  if(writer){const contributors=copy.nodes.filter(node=>!['requirements','writer','fact-checker','reviewer'].includes(node.id)).map(node=>node.id);writer.dependencies=contributors.length?contributors:['requirements']}
  const reviewer=copy.nodes.find(node=>node.id==='reviewer')
  if(reviewer)reviewer.dependencies=kept.has('fact-checker')?['fact-checker']:['writer']
  return copy
}
