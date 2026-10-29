import { http, HttpResponse } from 'msw'
import type { RequirementResult, Status } from '../api/types'
import { completedRun, sample, template } from './fixtures'

export const handlers = [
  http.get('/health', () => HttpResponse.json({ status: 'ok', version: '0.1.0', mode: 'offline', model: 'offline-demo' })),
  http.get('/api/templates', () => HttpResponse.json([template])),
  http.get('/api/samples', () => HttpResponse.json([sample])),
  http.post('/api/checks', () => HttpResponse.json({ ...completedRun, state: 'running', results: [] }, { status: 202 })),
  http.get('/api/checks/:id', () => HttpResponse.json(completedRun)),
  http.patch('/api/checks/:id/findings/:reqId', async ({ request, params }) => {
    const body = (await request.json()) as { status: Status; comment: string }
    const original = completedRun.results.find((r) => r.requirement.id === params.reqId)!
    const updated: RequirementResult = {
      ...original,
      status: body.status,
      override: { status: body.status, comment: body.comment, created_at: '2026-10-29T10:01:00Z' },
      needs_review: false,
    }
    return HttpResponse.json(updated)
  }),
  http.delete('/api/checks/:id/findings/:reqId/override', ({ params }) =>
    HttpResponse.json(completedRun.results.find((r) => r.requirement.id === params.reqId)),
  ),
  http.post('/api/requirements/export', async ({ request }) => {
    const body = (await request.json()) as { format: string }
    return new HttpResponse(body.format === 'yaml' ? 'requirements: []\n' : 'id,title,type\n', {
      headers: { 'Content-Type': 'text/plain' },
    })
  }),
  http.post('/api/datasheets', () =>
    HttpResponse.json({ id: 'ds_upload', filename: 'my-mcu.pdf', page_count: 42, is_sample: false }, { status: 201 }),
  ),
]
