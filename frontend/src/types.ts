export type Agent = {
  id: string
  name: string
  role: string
  system_prompt: string
  capabilities: string[]
  tools: string[]
  model: string
  status: 'active' | 'disabled'
  version: number
}

export type WorkflowNode = {
  id: string
  label: string
  agent_id: string
  kind: 'agent' | 'validator'
  dependencies: string[]
  position: { x: number; y: number }
}

export type Workflow = {
  id: string
  name: string
  description: string
  nodes: WorkflowNode[]
  quality_threshold: number
  max_loop_count: number
  version: number
}

export type NodeRun = {
  id: string
  node_id: string
  label: string
  status: string
  input: string
  output: string | null
  score: number | null
  duration_ms: number | null
  retry_count: number
  loop: number
  error: string | null
}

export type TaskRun = {
  id: string
  task: string
  workflow_id: string
  status: string
  progress: number
  score: number | null
  loop_count: number
  token_usage: number
  started_at: string
  finished_at: string | null
  node_runs: NodeRun[]
  final_output: string | null
  validation: { score: number; issues: string[]; suggestions: string[]; dimensions?: Record<string, number> } | null
  error: string | null
}

