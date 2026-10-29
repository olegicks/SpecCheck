import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { useState } from 'react'
import type { Requirement } from '../../api/types'
import { requirements, template } from '../../mocks/fixtures'
import { server } from '../../test/setup'
import { RequirementsEditor } from './RequirementsEditor'
import { cleanRequirement, describe as describeReq, nextId, validateRequirements } from './requirementUtils'

function Harness({ initial, onChange }: { initial: Requirement[]; onChange?: (rows: Requirement[]) => void }) {
  const [rows, setRows] = useState(initial)
  return (
    <RequirementsEditor
      requirements={rows}
      templates={[template]}
      onChange={(next) => {
        setRows(next)
        onChange?.(next)
      }}
    />
  )
}

const rowIds = () =>
  screen.getAllByRole('textbox', { name: /^ID of/ }).map((input) => (input as HTMLInputElement).value)

describe('RequirementsEditor', () => {
  it('shows an empty state and loads a template', async () => {
    const user = userEvent.setup()
    render(<Harness initial={[]} />)
    expect(screen.getByText('No requirements yet')).toBeInTheDocument()
    await user.selectOptions(screen.getByLabelText('Load template'), 'vehicle-computer-mcu')
    expect(rowIds()).toEqual(['REQ-001', 'REQ-005', 'REQ-006'])
    expect(screen.getByText('3 requirements')).toBeInTheDocument()
  })

  it('adds, edits and deletes a requirement', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<Harness initial={requirements} onChange={onChange} />)

    await user.click(screen.getByRole('button', { name: 'Add requirement' }))
    expect(rowIds()).toEqual(['REQ-001', 'REQ-005', 'REQ-006', 'REQ-007'])

    const title = screen.getByRole('textbox', { name: 'Title of REQ-007' })
    expect(screen.getByText('Title is required')).toBeInTheDocument()
    await user.type(title, 'CPU clock')
    await user.type(screen.getByRole('spinbutton', { name: 'Min of REQ-007' }), '300')
    expect(screen.queryByText('Title is required')).not.toBeInTheDocument()
    expect(onChange.mock.lastCall?.[0].at(-1)).toMatchObject({ title: 'CPU clock', parameters: { min: 300, unit: 'MHz' } })

    await user.click(screen.getByRole('button', { name: 'Delete REQ-005' }))
    expect(rowIds()).toEqual(['REQ-001', 'REQ-006', 'REQ-007'])
  })

  it('reorders rows', async () => {
    const user = userEvent.setup()
    render(<Harness initial={requirements} />)
    expect(screen.getByRole('button', { name: 'Move REQ-001 up' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Move REQ-001 down' }))
    expect(rowIds()).toEqual(['REQ-005', 'REQ-001', 'REQ-006'])
    await user.click(screen.getByRole('button', { name: 'Move REQ-006 up' }))
    expect(rowIds()).toEqual(['REQ-005', 'REQ-006', 'REQ-001'])
  })

  it('validates inline and switches parameter fields by type', async () => {
    const user = userEvent.setup()
    render(<Harness initial={requirements} />)

    const id = screen.getByRole('textbox', { name: 'ID of REQ-005' })
    await user.clear(id)
    await user.type(id, 'REQ-001')
    expect(screen.getAllByText('Duplicate ID')).toHaveLength(2) // both rows are flagged
    expect(screen.getByText('2 with errors', { exact: false })).toBeInTheDocument()

    await user.clear(id)
    await user.type(id, 'bad id')
    expect(screen.getByText('Use a format like REQ-001')).toBeInTheDocument()
    expect(id).toHaveAttribute('aria-invalid', 'true')

    await user.selectOptions(screen.getByLabelText('Type of REQ-001'), 'presence')
    expect(screen.getByRole('textbox', { name: 'Feature of REQ-001' })).toBeInTheDocument()
    expect(screen.queryByRole('spinbutton', { name: 'Min of REQ-001' })).not.toBeInTheDocument()
  })

  it('imports a YAML file through the API', async () => {
    server.use(http.post('/api/requirements/import', () => HttpResponse.json([requirements[2]])))
    const user = userEvent.setup()
    render(<Harness initial={requirements} />)
    const file = new File(['- id: REQ-006'], 'reqs.yaml', { type: 'application/x-yaml' })
    await user.upload(screen.getByTestId('import-input'), file)
    await waitFor(() => expect(rowIds()).toEqual(['REQ-006']))
  })

  it('shows every import error returned by the backend', async () => {
    server.use(
      http.post('/api/requirements/import', () =>
        HttpResponse.json({ detail: { errors: ['row 1 (REQ-1): min: required', 'row 2: duplicate id'] } }, { status: 422 }),
      ),
    )
    const user = userEvent.setup()
    render(<Harness initial={requirements} />)
    await user.upload(screen.getByTestId('import-input'), new File(['x'], 'reqs.csv', { type: 'text/csv' }))
    const alert = await screen.findByRole('alert')
    expect(within(alert).getByText('Import failed')).toBeInTheDocument()
    expect(within(alert).getByText('row 2: duplicate id')).toBeInTheDocument()
    await user.click(within(alert).getByRole('button', { name: 'Dismiss error' }))
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('exports YAML via the backend', async () => {
    let body: unknown
    server.use(
      http.post('/api/requirements/export', async ({ request }) => {
        body = await request.json()
        return new HttpResponse('requirements: []', { headers: { 'Content-Type': 'application/x-yaml' } })
      }),
    )
    const user = userEvent.setup()
    render(<Harness initial={requirements} />)
    await user.click(screen.getByRole('button', { name: 'YAML' }))
    await waitFor(() => expect(body).toMatchObject({ format: 'yaml', requirements: { length: 3 } }))
  })
})

describe('requirementUtils', () => {
  it('describes every type like the backend', () => {
    const base = { id: 'REQ-1', title: 't', priority: 'must' as const }
    expect(describeReq({ ...base, type: 'range', parameters: { min: -40, max: 125, unit: '°C' } })).toBe('-40 … 125 °C')
    expect(describeReq({ ...base, type: 'max', parameters: { max: 3.6, unit: 'V' } })).toBe('≤ 3.6 V')
    expect(describeReq({ ...base, type: 'equals', parameters: { value: 3.3, tolerance: 0.1, unit: 'V' } })).toBe('= 3.3 ± 0.1 V')
    expect(describeReq({ ...base, type: 'min_count', parameters: { count: 2, feature: 'CAN FD' } })).toBe('≥ 2 × CAN FD')
    expect(describeReq({ ...base, type: 'presence', parameters: { feature: 'ECC' } })).toBe('ECC present')
  })

  it('flags range and unit problems', () => {
    const [errors] = validateRequirements([
      { id: 'REQ-1', title: 'x', type: 'range', parameters: { min: 5, max: 1, unit: 'parsec' }, priority: 'must' },
    ])
    expect(errors).toEqual({ max: 'Max must be ≥ min', unit: 'Unknown unit' })
    const [count] = validateRequirements([
      { id: 'REQ-1', title: 'x', type: 'min_count', parameters: { count: 1.5, feature: 'CAN' }, priority: 'must' },
    ])
    expect(count).toEqual({ count: 'Whole number ≥ 1' })
  })

  it('strips parameters that do not belong to the type', () => {
    const cleaned = cleanRequirement({
      id: ' REQ-1 ',
      title: ' Clock ',
      type: 'min',
      parameters: { min: 300, unit: 'MHz', feature: 'leftover', max: null },
      priority: 'must',
    })
    expect(cleaned).toEqual({ id: 'REQ-1', title: 'Clock', type: 'min', parameters: { min: 300, unit: 'MHz' }, priority: 'must' })
    expect(nextId([])).toBe('REQ-001')
  })
})
