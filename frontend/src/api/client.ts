import type {
  AgentEvent,
  CheckRun,
  DatasheetSummary,
  ExportFormat,
  Health,
  Requirement,
  RequirementResult,
  Status,
  Template,
} from './types'

export const API_BASE: string = (import.meta.env.VITE_API_URL as string | undefined) ?? ''

const TOKEN_KEY = 'speccheck-access-code'

function readStoredToken(): string {
  try {
    return localStorage.getItem(TOKEN_KEY) ?? ''
  } catch {
    return ''
  }
}

let accessToken = readStoredToken()

/** Shared access code for deployments that protect runs/uploads (sent as X-Access-Token). */
export function getAccessToken(): string {
  return accessToken
}

export function setAccessToken(token: string) {
  accessToken = token.trim()
  try {
    if (accessToken) localStorage.setItem(TOKEN_KEY, accessToken)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    /* storage unavailable */
  }
}

export class ApiError extends Error {
  readonly status: number
  readonly details: string[]

  constructor(status: number, message: string, details: string[] = []) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.details = details
  }
}

/** Turn FastAPI error payloads (string, list of validation errors, {errors}) into text. */
function parseError(status: number, body: unknown): ApiError {
  const detail = (body as { detail?: unknown } | null)?.detail
  if (typeof detail === 'string') return new ApiError(status, detail)
  if (Array.isArray(detail)) {
    const messages = detail.map((d: { loc?: unknown[]; msg?: string }) => {
      const loc = (d.loc ?? []).filter((p) => p !== 'body').join('.')
      return loc ? `${loc}: ${d.msg}` : String(d.msg)
    })
    return new ApiError(status, messages[0] ?? 'Invalid request', messages)
  }
  if (detail && typeof detail === 'object' && 'errors' in detail) {
    const errors = (detail as { errors: string[] }).errors
    return new ApiError(status, errors[0] ?? 'Invalid input', errors)
  }
  if (status === 429) return new ApiError(status, 'Too many requests — please wait a moment.')
  if (status === 401) return new ApiError(status, 'A valid access code is required.')
  return new ApiError(status, `Request failed (${status})`)
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    const headers = new Headers(init?.headers)
    if (accessToken) headers.set('X-Access-Token', accessToken)
    response = await fetch(`${API_BASE}${path}`, { ...init, headers })
  } catch {
    throw new ApiError(0, 'Cannot reach the SpecCheck backend. Is it running?')
  }
  if (!response.ok) {
    let body: unknown = null
    try {
      body = await response.json()
    } catch {
      /* non-JSON error body */
    }
    throw parseError(response.status, body)
  }
  const type = response.headers.get('content-type') ?? ''
  return (type.includes('application/json') ? response.json() : response.text()) as Promise<T>
}

const json = (body: unknown): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export const api = {
  health: () => request<Health>('/health'),
  templates: () => request<Template[]>('/api/templates'),
  samples: () => request<DatasheetSummary[]>('/api/samples'),

  importRequirements: (format: 'yaml' | 'csv', content: string) =>
    request<Requirement[]>('/api/requirements/import', json({ format, content })),
  exportRequirements: (format: 'yaml' | 'csv', requirements: Requirement[]) =>
    request<string>('/api/requirements/export', json({ format, requirements })),

  uploadDatasheet: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<DatasheetSummary>('/api/datasheets', { method: 'POST', body: form })
  },

  startCheck: (datasheetId: string, requirements: Requirement[]) =>
    request<CheckRun>('/api/checks', json({ datasheet_id: datasheetId, requirements })),
  getCheck: (id: string) => request<CheckRun>(`/api/checks/${id}`),
  override: (checkId: string, requirementId: string, status: Status, comment: string) =>
    request<RequirementResult>(`/api/checks/${checkId}/findings/${encodeURIComponent(requirementId)}`, {
      ...json({ status, comment }),
      method: 'PATCH',
    }),
  clearOverride: (checkId: string, requirementId: string) =>
    request<RequirementResult>(
      `/api/checks/${checkId}/findings/${encodeURIComponent(requirementId)}/override`,
      { method: 'DELETE' },
    ),
}

export const pageImageUrl = (datasheetId: string, page: number, highlight?: string | null) => {
  const query = highlight ? `?highlight=${encodeURIComponent(highlight.slice(0, 600))}` : ''
  return `${API_BASE}/api/datasheets/${datasheetId}/pages/${page}.png${query}`
}

export const exportUrl = (checkId: string, format: ExportFormat) =>
  `${API_BASE}/api/checks/${checkId}/export?format=${format}`

/** Subscribe to the agent's Server-Sent Events. Returns an unsubscribe function. */
export function subscribeToEvents(
  checkId: string,
  onEvent: (event: AgentEvent) => void,
  onDone: () => void,
  onError: () => void,
): () => void {
  const source = new EventSource(`${API_BASE}/api/checks/${checkId}/events`)
  source.addEventListener('agent', (e) => onEvent(JSON.parse((e as MessageEvent).data) as AgentEvent))
  source.addEventListener('done', () => {
    source.close()
    onDone()
  })
  source.onerror = () => {
    // EventSource reconnects automatically (with Last-Event-ID); give up only if closed.
    if (source.readyState === EventSource.CLOSED) onError()
  }
  return () => source.close()
}
