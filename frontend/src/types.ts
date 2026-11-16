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
  requires_approval?: boolean
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
  tool_calls?: Array<{tool:string;query?:string;expression?:string;result?:number;result_count?:number}>
}

export type TaskRun = {
  id: string
  task: string
  workflow_id: string
  workflow_snapshot?: Workflow
  output_format?: 'markdown' | 'document'
  status: string
  progress: number
  score: number | null
  selected_loop?: number | null
  latest_score?: number | null
  loop_count: number
  token_usage: number
  started_at: string
  finished_at: string | null
  node_runs: NodeRun[]
  final_output: string | null
  validation: {
    score: number
    issues?: Array<string | { id?: string; severity?: string; description?: string; suggestion?: string }>
    suggestions?: string[]
    dimensions?: Record<string, number | { score?: number; value?: number; comment?: string }>
    dimension_scores?: Record<string, number | { score?: number; value?: number; comment?: string }>
    dimension_comments?: Record<string, string>
    improvement_suggestions?: string[]
  } | null
  approval?: {
    node_id: string
    status: 'pending' | 'approved'
    feedback?: string | null
    requested_at?: string
    approved_at?: string
    options?: Array<{id:string;question:string;type:'single'|'multiple';options:string[]}>
  } | null
  human_feedback?: string | null
  error: string | null
}

