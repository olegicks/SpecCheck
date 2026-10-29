import type { AgentEvent, CheckRun, Requirement, RequirementResult, Template } from '../api/types'

export const requirements: Requirement[] = [
  { id: 'REQ-001', title: 'Ambient operating temperature', type: 'range', parameters: { min: -40, max: 125, unit: '°C' }, priority: 'must' },
  { id: 'REQ-005', title: 'On-chip SRAM', type: 'min', parameters: { min: 1, unit: 'MB' }, priority: 'must' },
  { id: 'REQ-006', title: 'CAN FD interfaces', type: 'min_count', parameters: { count: 4, feature: 'CAN FD controller' }, priority: 'must' },
]

export const template: Template = {
  id: 'vehicle-computer-mcu',
  name: 'Vehicle Computer MCU',
  description: 'Typical requirements',
  requirements,
}

export const sample = {
  id: 'sc-mcu-100',
  filename: 'SC-MCU-100_datasheet.pdf',
  page_count: 8,
  is_sample: true,
  title: 'SC-MCU-100 Datasheet (fictional sample)',
  description: 'Fictional automotive MCU datasheet.',
}

export const passResult: RequirementResult = {
  requirement: requirements[0]!,
  finding: {
    requirement_id: 'REQ-001',
    value: '-40 to 125',
    unit: '°C',
    page: 5,
    quote: 'TA Ambient operating temperature -40 - 125 °C',
    confidence: 0.95,
    notes: 'From Table 5-1.',
  },
  verification: { verified: true, method: 'exact', score: 100, reason: null },
  agent_status: 'PASS',
  reason: 'Datasheet range -40 °C … 125 °C covers required -40 … 125 °C',
  found_display: '-40 °C … 125 °C',
  override: null,
  status: 'PASS',
  needs_review: false,
}

export const unclearResult: RequirementResult = {
  requirement: requirements[1]!,
  finding: {
    requirement_id: 'REQ-005',
    value: '1',
    unit: 'MB',
    page: 1,
    quote: 'Up to 1 MB SRAM with ECC, depending on device variant',
    confidence: 0.45,
    notes: 'Variant dependent: SC-MCU-100A has only 512 KB.',
  },
  verification: { verified: true, method: 'exact', score: 100, reason: null },
  agent_status: 'UNCLEAR',
  reason: 'Low confidence 0.45 < 0.60 — needs review',
  found_display: '1 MB',
  override: null,
  status: 'UNCLEAR',
  needs_review: true,
}

export const failResult: RequirementResult = {
  requirement: requirements[2]!,
  finding: {
    requirement_id: 'REQ-006',
    value: 3,
    unit: null,
    page: 3,
    quote: 'The device contains 3 CAN FD controllers (MCAN0 to MCAN2).',
    confidence: 0.95,
    notes: null,
  },
  verification: { verified: false, method: 'none', score: 40, reason: 'quote not found on cited page' },
  agent_status: 'FAIL',
  reason: '3 × CAN FD controller < required 4',
  found_display: '3',
  override: null,
  status: 'FAIL',
  needs_review: false,
}

export const completedRun: CheckRun = {
  id: 'chk_test',
  state: 'completed',
  mode: 'offline',
  model: 'offline-demo',
  datasheet: sample,
  requirements,
  results: [passResult, unclearResult, failResult],
  stop_reason: 'completed',
  error: null,
  steps: 12,
  tokens: 0,
  created_at: '2026-10-29T10:00:00Z',
  completed_at: '2026-10-29T10:00:05Z',
  summary: { total: 3, passed: 1, failed: 1, unclear: 1, overridden: 0 },
}

export const events: AgentEvent[] = [
  { seq: 1, type: 'run_started', title: 'Agent started (offline-demo)', detail: '3 requirements, 8 pages', timestamp: 0, data: {} },
  { seq: 2, type: 'search', title: 'Searched "ambient operating temperature TA"', detail: '3 hit(s)', duration_ms: 1250, timestamp: 0, data: {} },
  { seq: 3, type: 'read_page', title: 'Read page 5', duration_ms: 12, timestamp: 0, data: {} },
  { seq: 4, type: 'verify', title: 'Quote NOT verified for REQ-006', detail: 'quote not found', timestamp: 0, data: { verified: false } },
  { seq: 5, type: 'run_completed', title: 'Check completed', detail: '1 pass · 1 fail · 1 unclear', timestamp: 0, data: {} },
]
