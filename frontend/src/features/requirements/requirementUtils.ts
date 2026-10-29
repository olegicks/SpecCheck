import type { Requirement, RequirementParameters, RequirementType } from '../../api/types'

export const TYPE_LABELS: Record<RequirementType, string> = {
  range: 'Range',
  min: 'Minimum',
  max: 'Maximum',
  equals: 'Equals',
  min_count: 'Min. count',
  presence: 'Presence',
}

export const UNIT_OPTIONS = ['°C', 'V', 'mV', 'Hz', 'kHz', 'MHz', 'GHz', 'B', 'KB', 'MB', 'GB']

const KNOWN_UNITS = new Set(
  [...UNIT_OPTIONS, 'K', '°F', 'C', 'degC', 'µV', 'μV', 'kV', 'KiB', 'MiB', 'GiB', 'kB', 'Kbit', 'Mbit'].map(
    (u) => u.toLowerCase(),
  ),
)

const REQUIRED: Record<RequirementType, (keyof RequirementParameters)[]> = {
  range: ['min', 'max', 'unit'],
  min: ['min', 'unit'],
  max: ['max', 'unit'],
  equals: ['value', 'unit'],
  min_count: ['count', 'feature'],
  presence: ['feature'],
}

export const PARAM_FIELDS: Record<RequirementType, (keyof RequirementParameters)[]> = {
  range: ['min', 'max', 'unit'],
  min: ['min', 'unit'],
  max: ['max', 'unit'],
  equals: ['value', 'tolerance', 'unit'],
  min_count: ['count', 'feature'],
  presence: ['feature'],
}

const fmt = (n: number | null | undefined) => (n == null ? '?' : String(n))

/** Same wording as the backend's Requirement.describe(). */
export function describe(r: Requirement): string {
  const p = r.parameters
  switch (r.type) {
    case 'range':
      return `${fmt(p.min)} … ${fmt(p.max)} ${p.unit ?? ''}`.trim()
    case 'min':
      return `≥ ${fmt(p.min)} ${p.unit ?? ''}`.trim()
    case 'max':
      return `≤ ${fmt(p.max)} ${p.unit ?? ''}`.trim()
    case 'equals':
      return `= ${fmt(p.value)}${p.tolerance ? ` ± ${p.tolerance}` : ''} ${p.unit ?? ''}`.trim()
    case 'min_count':
      return `≥ ${fmt(p.count)} × ${p.feature ?? '?'}`
    case 'presence':
      return `${p.feature ?? '?'} present`
  }
}

export type RowErrors = Partial<Record<'id' | 'title' | keyof RequirementParameters, string>>

/** Client-side mirror of the backend validation for instant inline feedback. */
export function validateRequirements(rows: Requirement[]): RowErrors[] {
  const counts = new Map<string, number>()
  rows.forEach((r) => counts.set(r.id.trim(), (counts.get(r.id.trim()) ?? 0) + 1))

  return rows.map((r) => {
    const errors: RowErrors = {}
    const id = r.id.trim()
    if (!/^[A-Za-z][A-Za-z0-9_]*-\d{1,6}$/.test(id)) errors.id = 'Use a format like REQ-001'
    else if ((counts.get(id) ?? 0) > 1) errors.id = 'Duplicate ID'
    if (!r.title.trim()) errors.title = 'Title is required'

    const p = r.parameters
    for (const key of REQUIRED[r.type]) {
      const value = p[key]
      if (value === null || value === undefined || value === '') errors[key] = 'Required'
    }
    if (p.unit && !KNOWN_UNITS.has(p.unit.trim().toLowerCase()) && r.type !== 'min_count')
      errors.unit = 'Unknown unit'
    if (r.type === 'range' && p.min != null && p.max != null && p.min > p.max)
      errors.max = 'Max must be ≥ min'
    if (r.type === 'min_count' && p.count != null && (!Number.isInteger(p.count) || p.count < 1))
      errors.count = 'Whole number ≥ 1'
    return errors
  })
}

export const hasErrors = (errors: RowErrors[]) => errors.some((e) => Object.keys(e).length > 0)

/** Keep only the parameters relevant for the type (so the backend does not reject extras). */
export function cleanRequirement(r: Requirement): Requirement {
  const parameters: RequirementParameters = {}
  for (const key of PARAM_FIELDS[r.type]) {
    const value = r.parameters[key]
    if (value !== null && value !== undefined && value !== '') {
      ;(parameters as Record<string, unknown>)[key] = typeof value === 'string' ? value.trim() : value
    }
  }
  return { ...r, id: r.id.trim(), title: r.title.trim(), parameters }
}

export function nextId(rows: Requirement[]): string {
  const numbers = rows.map((r) => Number(/-(\d+)$/.exec(r.id)?.[1] ?? 0))
  const next = Math.max(0, ...numbers) + 1
  return `REQ-${String(next).padStart(3, '0')}`
}

export function blankRequirement(rows: Requirement[]): Requirement {
  return { id: nextId(rows), title: '', type: 'min', parameters: { unit: 'MHz' }, priority: 'must' }
}
