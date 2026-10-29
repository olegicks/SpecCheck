import { ArrowDown, ArrowUp, Download, FileUp, ListPlus, Plus, Trash2 } from 'lucide-react'
import { useId, useMemo, useRef, useState } from 'react'
import { ApiError, api } from '../../api/client'
import type { Priority, Requirement, RequirementParameters, RequirementType, Template } from '../../api/types'
import { Button, EmptyState, ErrorBanner, Section } from '../../components/ui'
import {
  PARAM_FIELDS,
  TYPE_LABELS,
  UNIT_OPTIONS,
  blankRequirement,
  cleanRequirement,
  describe,
  validateRequirements,
  type RowErrors,
} from './requirementUtils'

const PARAM_LABELS: Record<keyof RequirementParameters, string> = {
  min: 'Min',
  max: 'Max',
  value: 'Value',
  tolerance: '±',
  unit: 'Unit',
  count: 'Count',
  feature: 'Feature',
}

function download(filename: string, content: string, type: string) {
  const url = URL.createObjectURL(new Blob([content], { type }))
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

interface Props {
  requirements: Requirement[]
  onChange: (rows: Requirement[]) => void
  templates: Template[]
  disabled?: boolean
}

export function RequirementsEditor({ requirements, onChange, templates, disabled = false }: Props) {
  const errors = useMemo(() => validateRequirements(requirements), [requirements])
  const [importErrors, setImportErrors] = useState<string[]>([])
  const fileInput = useRef<HTMLInputElement>(null)
  const datalistId = useId()

  const update = (index: number, patch: Partial<Requirement>) =>
    onChange(requirements.map((r, i) => (i === index ? { ...r, ...patch } : r)))

  const updateParam = (index: number, key: keyof RequirementParameters, raw: string) => {
    const numeric = key !== 'unit' && key !== 'feature'
    const value = raw === '' ? null : numeric ? Number(raw) : raw
    const row = requirements[index]
    if (row) update(index, { parameters: { ...row.parameters, [key]: value } })
  }

  const move = (index: number, delta: number) => {
    const target = index + delta
    if (target < 0 || target >= requirements.length) return
    const next = [...requirements]
    ;[next[index], next[target]] = [next[target]!, next[index]!]
    onChange(next)
  }

  const handleImport = async (file: File) => {
    setImportErrors([])
    const format = /\.csv$/i.test(file.name) ? 'csv' : 'yaml'
    try {
      onChange(await api.importRequirements(format, await file.text()))
    } catch (e) {
      setImportErrors(e instanceof ApiError && e.details.length ? e.details : [(e as Error).message])
    }
  }

  const handleExport = async (format: 'yaml' | 'csv') => {
    try {
      const text = await api.exportRequirements(format, requirements.map(cleanRequirement))
      download(`requirements.${format === 'yaml' ? 'yaml' : 'csv'}`, text, format === 'yaml' ? 'application/x-yaml' : 'text/csv')
    } catch (e) {
      setImportErrors([(e as Error).message])
    }
  }

  const invalidCount = errors.filter((e) => Object.keys(e).length > 0).length

  return (
    <Section
      step={1}
      title="Requirements"
      description="What the component must satisfy. Python checks these deterministically against the extracted values."
      actions={
        <>
          <label className="sr-only" htmlFor="template-select">
            Load template
          </label>
          <select
            id="template-select"
            className="input h-8 w-auto py-0 text-xs"
            value=""
            disabled={disabled}
            onChange={(e) => {
              const t = templates.find((x) => x.id === e.target.value)
              if (t) onChange(t.requirements)
            }}
          >
            <option value="">Load template…</option>
            {templates.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
          <Button size="sm" icon={<FileUp className="size-3.5" />} onClick={() => fileInput.current?.click()} disabled={disabled}>
            Import
          </Button>
          <input
            ref={fileInput}
            type="file"
            accept=".yaml,.yml,.csv"
            className="hidden"
            aria-label="Import requirements file"
            data-testid="import-input"
            onChange={(e) => {
              const file = e.target.files?.[0]
              if (file) void handleImport(file)
              e.target.value = ''
            }}
          />
          <Button size="sm" icon={<Download className="size-3.5" />} onClick={() => void handleExport('yaml')} disabled={!requirements.length}>
            YAML
          </Button>
          <Button size="sm" icon={<Download className="size-3.5" />} onClick={() => void handleExport('csv')} disabled={!requirements.length}>
            CSV
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <ErrorBanner title="Import failed" messages={importErrors} onDismiss={() => setImportErrors([])} />
        <datalist id={datalistId}>
          {UNIT_OPTIONS.map((u) => (
            <option key={u} value={u} />
          ))}
        </datalist>

        {requirements.length === 0 ? (
          <EmptyState icon={<ListPlus className="size-5" />} title="No requirements yet">
            Load the <strong>Vehicle Computer MCU</strong> template, import a YAML/CSV file, or add a requirement manually.
          </EmptyState>
        ) : (
          <div className="-mx-5 overflow-x-auto">
            <table className="w-full min-w-[860px] text-sm" aria-label="Requirements">
              <thead>
                <tr className="border-b border-slate-100 text-left dark:border-slate-800">
                  <th className="label w-28 px-5 pb-2 font-medium">ID</th>
                  <th className="label px-2 pb-2 font-medium">Title</th>
                  <th className="label w-32 px-2 pb-2 font-medium">Type</th>
                  <th className="label px-2 pb-2 font-medium">Criterion</th>
                  <th className="label w-24 px-2 pb-2 font-medium">Priority</th>
                  <th className="w-24 px-5 pb-2">
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {requirements.map((r, index) => (
                  <RequirementRow
                    key={index}
                    row={r}
                    index={index}
                    total={requirements.length}
                    errors={errors[index] ?? {}}
                    unitListId={datalistId}
                    disabled={disabled}
                    onUpdate={(patch) => update(index, patch)}
                    onParam={(key, raw) => updateParam(index, key, raw)}
                    onMove={(delta) => move(index, delta)}
                    onDelete={() => onChange(requirements.filter((_, i) => i !== index))}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="flex flex-wrap items-center justify-between gap-2">
          <Button
            size="sm"
            variant="ghost"
            icon={<Plus className="size-4" />}
            onClick={() => onChange([...requirements, blankRequirement(requirements)])}
            disabled={disabled}
          >
            Add requirement
          </Button>
          <p className="text-xs text-slate-500 dark:text-slate-400" aria-live="polite">
            {requirements.length} requirement{requirements.length === 1 ? '' : 's'}
            {invalidCount > 0 && <span className="ml-1 text-rose-600 dark:text-rose-400">· {invalidCount} with errors</span>}
          </p>
        </div>
      </div>
    </Section>
  )
}

interface RowProps {
  row: Requirement
  index: number
  total: number
  errors: RowErrors
  unitListId: string
  disabled: boolean
  onUpdate: (patch: Partial<Requirement>) => void
  onParam: (key: keyof RequirementParameters, raw: string) => void
  onMove: (delta: number) => void
  onDelete: () => void
}

function FieldError({ id, message }: { id: string; message?: string }) {
  if (!message) return null
  return (
    <p id={id} className="mt-0.5 text-[11px] text-rose-600 dark:text-rose-400">
      {message}
    </p>
  )
}

function RequirementRow({ row, index, total, errors, unitListId, disabled, onUpdate, onParam, onMove, onDelete }: RowProps) {
  const base = `req-${index}`
  const label = row.id || `row ${index + 1}`
  return (
    <tr className="group border-b border-slate-100 align-top last:border-0 hover:bg-slate-50/60 dark:border-slate-800/70 dark:hover:bg-slate-800/30">
      <td className="px-5 py-2">
        <input
          className={`input font-mono text-xs ${errors.id ? 'input-error' : ''}`}
          value={row.id}
          disabled={disabled}
          aria-label={`ID of ${label}`}
          aria-invalid={!!errors.id}
          aria-describedby={errors.id ? `${base}-id-err` : undefined}
          onChange={(e) => onUpdate({ id: e.target.value })}
        />
        <FieldError id={`${base}-id-err`} message={errors.id} />
      </td>
      <td className="px-2 py-2">
        <input
          className={`input ${errors.title ? 'input-error' : ''}`}
          value={row.title}
          placeholder="e.g. Operating temperature"
          disabled={disabled}
          aria-label={`Title of ${label}`}
          aria-invalid={!!errors.title}
          aria-describedby={errors.title ? `${base}-title-err` : undefined}
          onChange={(e) => onUpdate({ title: e.target.value })}
        />
        <FieldError id={`${base}-title-err`} message={errors.title} />
      </td>
      <td className="px-2 py-2">
        <select
          className="input"
          value={row.type}
          disabled={disabled}
          aria-label={`Type of ${label}`}
          onChange={(e) => onUpdate({ type: e.target.value as RequirementType })}
        >
          {Object.entries(TYPE_LABELS).map(([value, text]) => (
            <option key={value} value={value}>
              {text}
            </option>
          ))}
        </select>
      </td>
      <td className="px-2 py-2">
        <div className="flex flex-wrap gap-1.5">
          {PARAM_FIELDS[row.type].map((key) => {
            const text = key === 'unit' || key === 'feature'
            const value = row.parameters[key]
            const width = key === 'feature' ? 'w-40' : key === 'unit' ? 'w-20' : 'w-20'
            return (
              <div key={key} className={width}>
                <input
                  className={`input ${errors[key] ? 'input-error' : ''}`}
                  type={text ? 'text' : 'number'}
                  step="any"
                  list={key === 'unit' ? unitListId : undefined}
                  placeholder={PARAM_LABELS[key]}
                  value={value ?? ''}
                  disabled={disabled}
                  aria-label={`${PARAM_LABELS[key] === '±' ? 'Tolerance' : PARAM_LABELS[key]} of ${label}`}
                  aria-invalid={!!errors[key]}
                  onChange={(e) => onParam(key, e.target.value)}
                />
                <FieldError id={`${base}-${key}-err`} message={errors[key]} />
              </div>
            )
          })}
        </div>
        <p className="mt-1 font-mono text-[11px] text-slate-400 dark:text-slate-500">{describe(row)}</p>
      </td>
      <td className="px-2 py-2">
        <select
          className="input"
          value={row.priority}
          disabled={disabled}
          aria-label={`Priority of ${label}`}
          onChange={(e) => onUpdate({ priority: e.target.value as Priority })}
        >
          <option value="must">Must</option>
          <option value="should">Should</option>
        </select>
      </td>
      <td className="px-5 py-2">
        <div className="flex justify-end gap-0.5 opacity-60 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
          <button
            type="button"
            className="rounded p-1.5 text-slate-500 hover:bg-slate-100 disabled:opacity-30 dark:hover:bg-slate-800"
            onClick={() => onMove(-1)}
            disabled={disabled || index === 0}
            aria-label={`Move ${label} up`}
          >
            <ArrowUp className="size-3.5" />
          </button>
          <button
            type="button"
            className="rounded p-1.5 text-slate-500 hover:bg-slate-100 disabled:opacity-30 dark:hover:bg-slate-800"
            onClick={() => onMove(1)}
            disabled={disabled || index === total - 1}
            aria-label={`Move ${label} down`}
          >
            <ArrowDown className="size-3.5" />
          </button>
          <button
            type="button"
            className="rounded p-1.5 text-slate-500 hover:bg-rose-50 hover:text-rose-600 disabled:opacity-30 dark:hover:bg-rose-950/40"
            onClick={onDelete}
            disabled={disabled}
            aria-label={`Delete ${label}`}
          >
            <Trash2 className="size-3.5" />
          </button>
        </div>
      </td>
    </tr>
  )
}
