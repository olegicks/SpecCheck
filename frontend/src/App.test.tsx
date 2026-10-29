import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import App from './App'
import { ModeBadge } from './components/Header'
import { DatasheetPicker } from './features/datasheet/DatasheetPicker'
import { AgentTimeline } from './features/timeline/AgentTimeline'
import { events, sample } from './mocks/fixtures'
import { FakeEventSource, server } from './test/setup'

describe('App flow', () => {
  it('runs a check, streams the timeline and shows results', async () => {
    const user = userEvent.setup()
    render(<App />)

    expect(await screen.findByText('Offline demo')).toBeInTheDocument()
    expect(screen.getByText(/Offline demo mode\./)).toBeInTheDocument()
    const run = await screen.findByRole('button', { name: 'Run check' })
    await waitFor(() => expect(run).toBeEnabled())

    await user.click(run)
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1))
    expect(screen.getByRole('button', { name: /Agent running/ })).toBeDisabled()
    const source = FakeEventSource.instances[0]!
    expect(source.url).toBe('/api/checks/chk_test/events')

    act(() => events.forEach((e) => source.emit('agent', e)))
    const steps = screen.getByRole('list', { name: 'Agent steps' })
    expect(within(steps).getByText('Read page 5')).toBeInTheDocument()
    expect(within(steps).getByText('1.3 s')).toBeInTheDocument()

    act(() => source.emit('done', { state: 'completed' }))
    expect(await screen.findByRole('group', { name: 'Result summary' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Run check' })).toBeEnabled()

    await user.click(screen.getByRole('button', { name: /Show details for REQ-005/ }))
    expect(screen.getByRole('dialog', { name: 'On-chip SRAM' })).toBeInTheDocument()
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('disables the run button while requirements are invalid', async () => {
    const user = userEvent.setup()
    render(<App />)
    const title = await screen.findByRole('textbox', { name: 'Title of REQ-001' })
    await user.clear(title)
    expect(screen.getByRole('button', { name: 'Run check' })).toBeDisabled()
    expect(screen.getByText('Fix the highlighted requirement errors')).toBeInTheDocument()
  })

  it('reports a failed start', async () => {
    server.use(http.post('/api/checks', () => HttpResponse.json({ detail: 'Too many requests' }, { status: 429 })))
    const user = userEvent.setup()
    render(<App />)
    const run = await screen.findByRole('button', { name: 'Run check' })
    await waitFor(() => expect(run).toBeEnabled())
    await user.click(run)
    expect(await screen.findByText('Too many requests')).toBeInTheDocument()
  })

  it('shows a friendly error when the backend is unreachable', async () => {
    server.use(
      http.get('/health', () => HttpResponse.error()),
      http.get('/api/templates', () => HttpResponse.error()),
      http.get('/api/samples', () => HttpResponse.error()),
    )
    render(<App />)
    expect(await screen.findByText('Backend offline')).toBeInTheDocument()
    expect(await screen.findAllByText('Cannot reach the SpecCheck backend. Is it running?')).not.toHaveLength(0)
  })

  it('asks for an access code when the deployment requires one and sends it', async () => {
    let sentToken: string | null = null
    server.use(
      http.get('/health', () =>
        HttpResponse.json({ status: 'ok', version: '1', mode: 'live', model: 'gpt-4o-mini', auth_required: true }),
      ),
      http.post('/api/checks', ({ request }) => {
        sentToken = request.headers.get('X-Access-Token')
        return HttpResponse.json({ detail: 'A valid access code is required to run checks.' }, { status: 401 })
      }),
    )
    const user = userEvent.setup()
    render(<App />)
    const code = await screen.findByLabelText('Access code')
    expect(screen.getByRole('button', { name: 'Run check' })).toBeDisabled()
    expect(screen.getByText('Enter the access code for this deployment')).toBeInTheDocument()

    await user.type(code, 'wrong-code')
    await user.click(screen.getByRole('button', { name: 'Run check' }))
    expect(sentToken).toBe('wrong-code')
    expect(await screen.findByText('A valid access code is required to run checks.')).toBeInTheDocument()
    await user.clear(code)
  })

  it('toggles dark mode', async () => {
    const user = userEvent.setup()
    render(<App />)
    const toggle = screen.getByRole('button', { name: /Switch to (dark|light) mode/ })
    const wasDark = document.documentElement.classList.contains('dark')
    await user.click(toggle)
    expect(document.documentElement.classList.contains('dark')).toBe(!wasDark)
  })
})

describe('ModeBadge', () => {
  it('shows the live model', () => {
    render(<ModeBadge health={{ status: 'ok', version: '1', mode: 'live', model: 'gpt-4o-mini' }} error={false} />)
    expect(screen.getByText('Live LLM · gpt-4o-mini')).toBeInTheDocument()
  })
})

describe('AgentTimeline', () => {
  it('shows an empty state and step counters', () => {
    const { rerender } = render(<AgentTimeline events={[]} running={false} />)
    expect(screen.getByText('No run yet')).toBeInTheDocument()
    rerender(<AgentTimeline events={events} running />)
    expect(screen.getByText('1 searches · 1 pages read · 1 quotes checked')).toBeInTheDocument()
    expect(screen.getByLabelText('Agent is working')).toBeInTheDocument()
  })
})

describe('DatasheetPicker', () => {
  it('uploads a dropped PDF and selects it', async () => {
    const onSelect = vi.fn()
    const user = userEvent.setup()
    render(<DatasheetPicker samples={[sample]} selected={sample} onSelect={onSelect} />)
    expect(screen.getByRole('button', { name: /Use sample datasheet/ })).toHaveAttribute('aria-pressed', 'true')
    await user.upload(screen.getByTestId('pdf-input'), new File(['%PDF-1.7'], 'my-mcu.pdf', { type: 'application/pdf' }))
    await waitFor(() => expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ id: 'ds_upload', page_count: 42 })))
    expect(screen.getByText('Uploaded · 42 pages')).toBeInTheDocument()
  })

  it('rejects non-PDF files client-side and shows server errors', async () => {
    server.use(http.post('/api/datasheets', () => HttpResponse.json({ detail: 'File is not a PDF (missing %PDF- header).' }, { status: 422 })))
    const user = userEvent.setup({ applyAccept: false })
    render(<DatasheetPicker samples={[sample]} selected={sample} onSelect={() => undefined} />)
    await user.upload(screen.getByTestId('pdf-input'), new File(['x'], 'notes.txt', { type: 'text/plain' }))
    expect(await screen.findByText('Please choose a PDF file.')).toBeInTheDocument()
    await user.upload(screen.getByTestId('pdf-input'), new File(['MZ'], 'fake.pdf', { type: 'application/pdf' }))
    expect(await screen.findByText('File is not a PDF (missing %PDF- header).')).toBeInTheDocument()
  })
})
