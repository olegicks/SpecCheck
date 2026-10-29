import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { StatusBadge } from '../../components/StatusBadge'
import { completedRun, failResult, passResult, unclearResult } from '../../mocks/fixtures'
import { server } from '../../test/setup'
import { DetailDrawer, OverrideForm } from './DetailDrawer'
import { ResultsPanel, ResultsTable } from './ResultsPanel'

describe('StatusBadge', () => {
  it.each(['PASS', 'FAIL', 'UNCLEAR'] as const)('renders %s with an accessible label', (status) => {
    render(<StatusBadge status={status} />)
    expect(screen.getByLabelText(new RegExp(`^Status: ${status.charAt(0)}`, 'i'))).toHaveTextContent(status)
  })

  it('marks overridden results', () => {
    render(<StatusBadge status="PASS" overridden />)
    expect(screen.getByLabelText('Status: Pass (overridden by reviewer)')).toHaveTextContent('✎')
  })
})

describe('ResultsTable', () => {
  it('shows value, page, confidence and status for each requirement', async () => {
    const onSelect = vi.fn()
    render(<ResultsTable results={completedRun.results} onSelect={onSelect} />)
    const rows = within(screen.getByRole('table', { name: 'Check results' })).getAllByRole('row').slice(1)
    expect(rows).toHaveLength(3)
    expect(within(rows[0]!).getByText('-40 °C … 125 °C')).toBeInTheDocument()
    expect(within(rows[0]!).getByLabelText('Confidence 95%')).toBeInTheDocument()
    expect(within(rows[1]!).getByText('Needs review')).toBeInTheDocument()
    expect(within(rows[2]!).getByLabelText('Status: Fail')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /Show details for REQ-006/ }))
    expect(onSelect).toHaveBeenCalledWith(failResult)
  })
})

describe('ResultsPanel', () => {
  it('renders summary cards and export links when completed', () => {
    render(<ResultsPanel run={completedRun} loading={false} onSelect={() => undefined} />)
    const summary = screen.getByRole('group', { name: 'Result summary' })
    expect(within(summary).getByLabelText('1 Pass')).toBeInTheDocument()
    expect(within(summary).getByLabelText('1 Fail')).toBeInTheDocument()
    expect(within(summary).getByLabelText('1 Unclear')).toBeInTheDocument()
    const exports = within(screen.getByRole('group', { name: 'Export report' })).getAllByRole('link')
    expect(exports.map((a) => a.getAttribute('href'))).toEqual([
      '/api/checks/chk_test/export?format=md',
      '/api/checks/chk_test/export?format=csv',
      '/api/checks/chk_test/export?format=json',
      '/api/checks/chk_test/export?format=xlsx',
    ])
  })

  it('shows skeletons while loading and an empty state before any run', () => {
    const { rerender } = render(<ResultsPanel run={null} loading onSelect={() => undefined} />)
    expect(screen.getByLabelText('Loading results')).toBeInTheDocument()
    rerender(<ResultsPanel run={null} loading={false} onSelect={() => undefined} />)
    expect(screen.getByText('No results yet')).toBeInTheDocument()
  })
})

describe('DetailDrawer', () => {
  it('shows the verbatim quote, verification, reasoning and highlighted page', () => {
    render(<DetailDrawer checkId="chk_test" datasheetId="sc-mcu-100" result={unclearResult} onClose={() => undefined} onUpdated={() => undefined} />)
    const dialog = screen.getByRole('dialog', { name: 'On-chip SRAM' })
    expect(within(dialog).getByText('Up to 1 MB SRAM with ECC, depending on device variant')).toBeInTheDocument()
    expect(within(dialog).getByText(/Quote verified on page 1/)).toBeInTheDocument()
    expect(within(dialog).getByText('Variant dependent: SC-MCU-100A has only 512 KB.')).toBeInTheDocument()
    const img = within(dialog).getByRole('img', { name: /page 1 with the quoted passage highlighted/i })
    expect(img.getAttribute('src')).toBe(
      '/api/datasheets/sc-mcu-100/pages/1.png?highlight=Up%20to%201%20MB%20SRAM%20with%20ECC%2C%20depending%20on%20device%20variant',
    )
  })

  it('warns when the quote could not be verified', () => {
    render(<DetailDrawer checkId="c" datasheetId="d" result={failResult} onClose={() => undefined} onUpdated={() => undefined} />)
    expect(screen.getByText('Quote NOT verified: quote not found on cited page')).toBeInTheDocument()
  })

  it('closes on Escape and via the close button', async () => {
    const onClose = vi.fn()
    render(<DetailDrawer checkId="c" datasheetId="d" result={passResult} onClose={onClose} onUpdated={() => undefined} />)
    expect(screen.getByRole('dialog')).toHaveFocus()
    await userEvent.keyboard('{Escape}')
    await userEvent.click(screen.getByRole('button', { name: 'Close details' }))
    expect(onClose).toHaveBeenCalledTimes(2)
  })
})

describe('OverrideForm', () => {
  it('requires a comment before saving', async () => {
    const onSaved = vi.fn()
    render(<OverrideForm checkId="chk_test" result={unclearResult} onSaved={onSaved} />)
    await userEvent.click(screen.getByRole('button', { name: 'Save override' }))
    expect(screen.getByText('A justification of at least 3 characters is required.')).toBeInTheDocument()
    expect(screen.getByLabelText(/Justification/)).toHaveAttribute('aria-invalid', 'true')
    expect(onSaved).not.toHaveBeenCalled()
  })

  it('sends status and comment, and keeps the agent result', async () => {
    let sent: unknown
    server.use(
      http.patch('/api/checks/:id/findings/:reqId', async ({ request }) => {
        sent = await request.json()
        return HttpResponse.json({
          ...unclearResult,
          status: 'FAIL',
          override: { status: 'FAIL', comment: 'Only 512 KB variant available', created_at: 'now' },
        })
      }),
    )
    const onSaved = vi.fn()
    const user = userEvent.setup()
    render(<OverrideForm checkId="chk_test" result={unclearResult} onSaved={onSaved} />)
    await user.click(screen.getByRole('radio', { name: 'FAIL' }))
    await user.type(screen.getByLabelText(/Justification/), '  Only 512 KB variant available  ')
    await user.click(screen.getByRole('button', { name: 'Save override' }))
    await waitFor(() => expect(onSaved).toHaveBeenCalled())
    expect(sent).toEqual({ status: 'FAIL', comment: 'Only 512 KB variant available' })
    expect(onSaved.mock.lastCall?.[0]).toMatchObject({ agent_status: 'UNCLEAR', status: 'FAIL' })
  })

  it('shows server errors', async () => {
    server.use(http.patch('/api/checks/:id/findings/:reqId', () => HttpResponse.json({ detail: 'The check is still running.' }, { status: 409 })))
    const user = userEvent.setup()
    render(<OverrideForm checkId="c" result={unclearResult} onSaved={() => undefined} />)
    await user.type(screen.getByLabelText(/Justification/), 'looks fine')
    await user.click(screen.getByRole('button', { name: 'Save override' }))
    expect(await screen.findByText('The check is still running.')).toBeInTheDocument()
  })

  it('can revert an existing override', async () => {
    const onSaved = vi.fn()
    const overridden = { ...unclearResult, status: 'PASS' as const, override: { status: 'PASS' as const, comment: 'ok by supplier', created_at: 'x' } }
    render(<OverrideForm checkId="chk_test" result={overridden} onSaved={onSaved} />)
    expect(screen.getByText('Overridden: UNCLEAR → PASS')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Revert to agent result' }))
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(expect.objectContaining({ override: null })))
  })
})
