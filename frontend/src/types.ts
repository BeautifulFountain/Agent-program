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
  evidence_snapshot?: KnowledgeSearchResult[]
  tool_calls?: Array<{tool:string;query?:string;search_query?:string;expression?:string;result?:number|string;token_usage?:number;result_count?:number;found?:number;duplicates?:number;discarded_irrelevant?:number;providers?:string[];errors?:string[];results?:Array<KnowledgeSearchResult|{id:string;provider:string;title:string;url:string;doi?:string}>}>
}

export type KnowledgeDocument = {
  id: string; title: string; organization: string; published_at: string; url: string
  filename: string; path?: string; size?: number; characters?: number; chunks?: number
    editable: boolean; updated_at?: string; content?: string
    authors?: string; doi?: string; cited_by_count?: string; original_file?: string; file_type?: string
}

export type KnowledgeSearchResult = {
  source: string; title: string; organization: string; published_at: string
  url: string; chunk: string; score: string; snippet: string
  coverage?: string; match_terms?: string[]
  evidence_id?: string; doi?: string; relevance_score?: number; relevance_reason?: string
  cited_by_count?: string
  supported_claims?: string[]; limitations?: string[]
}

export type DispatchRecommendation = {
  agent_ids: string[]
  reasons: Record<string,string>
  matched_keywords: Record<string,string[]>
  strategy: string
  llm_called: boolean
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
  delivery_metrics?: {
    citation_coverage: { cited:number; retrieved:number; percent:number }
    constraint_compliance: { satisfied:number; total:number; percent:number; checks:Array<{name:string;passed:boolean}> }
  }
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
  human_rework_count?: number
  final_acceptance?: {status:'revision_requested'|'revised';feedback?:string;agent_ids?:string[];requested_at?:string;ready_at?:string} | null
  error: string | null
}

