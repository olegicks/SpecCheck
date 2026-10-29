import { CheckCircle2, ChevronRight, Download, HelpCircle, ListChecks, XCircle } from 'lucide-react'
import { exportUrl } from '../../api/client'
import type { CheckRun, ExportFormat, RequirementResult } from '../../api/types'
import { StatusBadge } from '../../components/StatusBadge'
import { EmptyState, Section, Skeleton } from '../../components/ui'
import { describe } from '../requirements/requirementUtils'

export function SummaryCards({ run }: { run: CheckRun }) {
  const s = run.summary
  const cards = [
    { label: 'Pass', value: s.passed, icon: CheckCircle2, tone: 'text-emerald-600 dark:text-emerald-400', bar: 'bg-emerald-500' },
    { label: 'Fail', value: s.failed, icon: XCircle, tone: 'text-rose-600 dark:text-rose-400', bar: 'bg-rose-500' },
    { label: 'Unclear', value: s.unclear, icon: HelpCircle, tone: 'text-amber-600 dark:text-amber-400', bar: 'bg-amber-500' },
  ]
  return (
    <div className="grid grid-cols-3 gap-3" role="group" aria-label="Result summary">
      {cards.map(({ label, value, icon: Icon, tone, bar }) => (
        <div key={label} className="relative overflow-hidden rounded-lg border border-slate-200 p-4 dark:border-slate-800">
          <div className="flex items-center justify-between">
            <span className="label">{label}</span>
            <Icon className={`size-4 ${tone}`} aria-hidden />
          </div>
          <p className="mt-1 text-3xl font-semibold text-slate-900 tabular-nums dark:text-white" aria-label={`${value} ${label}`}>
            {value}
            <span className="ml-1 text-sm font-normal text-slate-400">/ {s.total}</span>
          </p>
          <div className="absolute inset-x-0 bottom-0 h-1 bg-slate-100 dark:bg-slate-800">
            <div className={`h-full ${bar}`} style={{ width: `${s.total ? (value / s.total) * 100 : 0}%` }} />
          </div>
        </div>
      ))}
    </div>
  )
}

export function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100)
  const color = value >= 0.8 ? 'bg-emerald-500' : value >= 0.6 ? 'bg-sky-500' : 'bg-amber-500'
  return (
    <div className="flex items-center gap-2" aria-label={`Confidence ${pct}%`}>
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="font-mono text-xs text-slate-500 tabular-nums">{pct}%</span>
    </div>
  )
}

const ROW_TINT: Record<string, string> = {
  PASS: 'border-l-emerald-500',
  FAIL: 'border-l-rose-500',
  UNCLEAR: 'border-l-amber-400',
}

export function ResultsTable({ results, onSelect }: { results: RequirementResult[]; onSelect: (r: RequirementResult) => void }) {
  return (
    <div className="-mx-5 overflow-x-auto">
      <table className="w-full min-w-[640px] text-sm" aria-label="Check results">
        <thead>
          <tr className="border-b border-slate-100 text-left dark:border-slate-800">
            <th className="label px-5 pb-2 font-medium">Requirement</th>
            <th className="label px-2 pb-2 font-medium">Found value</th>
            <th className="label w-16 px-2 pb-2 font-medium">Page</th>
            <th className="label w-28 px-2 pb-2 font-medium">Confidence</th>
            <th className="label w-28 px-5 pb-2 font-medium">Status</th>
          </tr>
        </thead>
        <tbody>
          {results.map((r) => (
            <tr
              key={r.requirement.id}
              onClick={() => onSelect(r)}
              className={`cursor-pointer border-b border-l-4 border-b-slate-100 transition-colors last:border-b-0 hover:bg-slate-50 dark:border-b-slate-800/70 dark:hover:bg-slate-800/40 ${ROW_TINT[r.status]}`}
            >
              <td className="px-5 py-3">
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation()
                    onSelect(r)
                  }}
                  className="group/title text-left font-medium text-slate-900 hover:text-accent-700 dark:text-white dark:hover:text-accent-400"
                  aria-label={`Show details for ${r.requirement.id} ${r.requirement.title}`}
                >
                  <span className="mr-2 font-mono text-xs text-slate-400">{r.requirement.id}</span>
                  {r.requirement.title}
                  <ChevronRight className="ml-0.5 inline size-3.5 opacity-0 transition-opacity group-hover/title:opacity-100" aria-hidden />
                </button>
                <p className="mt-0.5 font-mono text-xs text-slate-500 dark:text-slate-400">
                  {describe(r.requirement)}
                  {r.requirement.priority === 'should' && <span className="ml-2 font-sans text-slate-400">(should)</span>}
                </p>
              </td>
              <td className="px-2 py-3 font-mono text-xs text-slate-700 dark:text-slate-300">
                {r.found_display ?? <span className="text-slate-400">—</span>}
              </td>
              <td className="px-2 py-3 text-slate-600 tabular-nums dark:text-slate-400">{r.finding?.page ?? '—'}</td>
              <td className="px-2 py-3">{r.finding && r.finding.value !== null ? <ConfidenceBar value={r.finding.confidence} /> : <span className="text-slate-400">—</span>}</td>
              <td className="px-5 py-3">
                <div className="flex flex-col items-start gap-1">
                  <StatusBadge status={r.status} overridden={!!r.override} />
                  {r.needs_review && <span className="text-[11px] font-medium text-amber-700 dark:text-amber-400">Needs review</span>}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

const EXPORTS: { format: ExportFormat; label: string }[] = [
  { format: 'md', label: 'Markdown' },
  { format: 'csv', label: 'CSV' },
  { format: 'json', label: 'JSON' },
  { format: 'xlsx', label: 'Excel' },
]

export function ExportButtons({ checkId }: { checkId: string }) {
  return (
    <div className="flex flex-wrap gap-1.5" role="group" aria-label="Export report">
      {EXPORTS.map(({ format, label }) => (
        <a
          key={format}
          href={exportUrl(checkId, format)}
          download
          className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-2.5 text-xs font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"
        >
          <Download className="size-3.5" aria-hidden />
          {label}
        </a>
      ))}
    </div>
  )
}

export function ResultsPanel({
  run,
  loading,
  onSelect,
}: {
  run: CheckRun | null
  loading: boolean
  onSelect: (r: RequirementResult) => void
}) {
  const done = run && run.state !== 'running'
  return (
    <Section
      title="Results"
      description="Status decided by the deterministic rule engine. Click a row for evidence and to override."
      actions={done ? <ExportButtons checkId={run.id} /> : undefined}
    >
      {loading ? (
        <div className="space-y-3" aria-label="Loading results">
          <div className="grid grid-cols-3 gap-3">
            <Skeleton className="h-24" />
            <Skeleton className="h-24" />
            <Skeleton className="h-24" />
          </div>
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-12" />
          ))}
        </div>
      ) : done ? (
        <div className="space-y-5">
          <SummaryCards run={run} />
          {run.error && (
            <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:bg-amber-500/10 dark:text-amber-300" role="status">
              {run.error}
            </p>
          )}
          <ResultsTable results={run.results} onSelect={onSelect} />
          <p className="text-xs text-slate-400">
            {run.model} · {run.steps} agent steps{run.tokens ? ` · ${run.tokens.toLocaleString()} tokens` : ''} · stop reason:{' '}
            {run.stop_reason?.replace(/_/g, ' ') ?? '—'}
          </p>
        </div>
      ) : (
        <EmptyState icon={<ListChecks className="size-5" />} title="No results yet">
          Results appear here when the run finishes. Every PASS/FAIL links to a page and a verified quote.
        </EmptyState>
      )}
    </Section>
  )
}
