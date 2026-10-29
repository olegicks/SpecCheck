export type RequirementType = 'range' | 'min' | 'max' | 'equals' | 'min_count' | 'presence'
export type Priority = 'must' | 'should'
export type Status = 'PASS' | 'FAIL' | 'UNCLEAR'

export interface RequirementParameters {
  min?: number | null
  max?: number | null
  value?: number | null
  tolerance?: number | null
  unit?: string | null
  count?: number | null
  feature?: string | null
}

export interface Requirement {
  id: string
  title: string
  type: RequirementType
  parameters: RequirementParameters
  priority: Priority
}

export interface Template {
  id: string
  name: string
  description: string
  requirements: Requirement[]
}

export interface Health {
  status: string
  version: string
  mode: 'live' | 'offline'
  model: string
  auth_required?: boolean
}

export interface DatasheetSummary {
  id: string
  filename: string
  page_count: number
  is_sample: boolean
  title?: string | null
  description?: string
}

export type EventType =
  | 'run_started'
  | 'thinking'
  | 'search'
  | 'read_page'
  | 'extract'
  | 'submit'
  | 'verify'
  | 'decide'
  | 'warning'
  | 'error'
  | 'run_completed'

export interface AgentEvent {
  seq: number
  type: EventType
  title: string
  detail?: string | null
  step?: number | null
  duration_ms?: number | null
  timestamp: number
  data: Record<string, unknown>
}

export interface Finding {
  requirement_id: string
  value: number | string | boolean | null
  unit?: string | null
  page?: number | null
  quote?: string | null
  confidence: number
  notes?: string | null
}

export interface Verification {
  verified: boolean
  method: string
  score: number
  reason?: string | null
}

export interface Override {
  status: Status
  comment: string
  created_at: string
}

export interface RequirementResult {
  requirement: Requirement
  finding: Finding | null
  verification: Verification | null
  agent_status: Status
  reason: string
  found_display: string | null
  override: Override | null
  status: Status
  needs_review: boolean
}

export interface Summary {
  total: number
  passed: number
  failed: number
  unclear: number
  overridden: number
}

export interface CheckRun {
  id: string
  state: 'running' | 'completed' | 'failed'
  mode: string
  model: string
  datasheet: DatasheetSummary
  requirements: Requirement[]
  results: RequirementResult[]
  stop_reason: string | null
  error: string | null
  steps: number
  tokens: number
  created_at: string
  completed_at: string | null
  summary: Summary
}

export type ExportFormat = 'md' | 'csv' | 'json' | 'xlsx'
