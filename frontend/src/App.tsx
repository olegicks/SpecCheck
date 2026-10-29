import { Info, Loader2, Play, ShieldCheck } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { WAKE_UP_DELAYS_MS, api, withRetry } from './api/client'
import type { DatasheetSummary, Health, Requirement, RequirementResult, Template } from './api/types'
import { Header } from './components/Header'
import { Button, ErrorBanner } from './components/ui'
import { DatasheetPicker } from './features/datasheet/DatasheetPicker'
import { RequirementsEditor } from './features/requirements/RequirementsEditor'
import { cleanRequirement, hasErrors, validateRequirements } from './features/requirements/requirementUtils'
import { DetailDrawer } from './features/results/DetailDrawer'
import { ResultsPanel } from './features/results/ResultsPanel'
import { AgentTimeline } from './features/timeline/AgentTimeline'
import { useCheckRun } from './hooks/useCheckRun'
import { useTheme } from './hooks/useTheme'

export default function App({ retryDelays = WAKE_UP_DELAYS_MS }: { retryDelays?: number[] }) {
  const { dark, toggle } = useTheme()
  const [health, setHealth] = useState<Health | null>(null)
  const [loading, setLoading] = useState(true)
  const [slowStart, setSlowStart] = useState(false)
  const [templates, setTemplates] = useState<Template[]>([])
  const [samples, setSamples] = useState<DatasheetSummary[] | null>(null)
  const [requirements, setRequirements] = useState<Requirement[]>([])
  const [datasheet, setDatasheet] = useState<DatasheetSummary | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const check = useCheckRun()

  useEffect(() => {
    // The demo backend may be waking up: retry quietly and show a neutral notice if slow.
    let cancelled = false
    const slowTimer = setTimeout(() => setSlowStart(true), 2500)
    withRetry(() => api.health(), retryDelays).then(
      (h) => !cancelled && setHealth(h),
      () => undefined,
    )
    Promise.all([withRetry(() => api.templates(), retryDelays), withRetry(() => api.samples(), retryDelays)])
      .then(([t, s]) => {
        if (cancelled) return
        setTemplates(t)
        if (t[0]) setRequirements(t[0].requirements)
        setSamples(s)
        if (s[0]) setDatasheet(s[0])
      })
      .catch(() => {
        if (cancelled) return
        setSamples([])
        setLoadError('The demo server is still starting. Please reload the page in a moment.')
      })
      .finally(() => {
        clearTimeout(slowTimer)
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
      clearTimeout(slowTimer)
    }
  }, [retryDelays])

  const invalid = useMemo(() => hasErrors(validateRequirements(requirements)), [requirements])
  const canRun = !check.running && !invalid && requirements.length > 0 && datasheet !== null

  const disabledReason = check.running
    ? 'A check is running'
    : requirements.length === 0
      ? 'Add at least one requirement'
      : invalid
        ? 'Fix the highlighted requirement errors'
        : !datasheet
          ? 'Select a datasheet'
          : null

  const run = () => {
    if (!datasheet) return
    setSelectedId(null)
    void check.start(datasheet.id, requirements.map(cleanRequirement))
  }

  const selected = check.run?.results.find((r) => r.requirement.id === selectedId) ?? null
  const closeDrawer = useCallback(() => setSelectedId(null), [])
  const onUpdated = useCallback((updated: RequirementResult) => void check.applyUpdate(updated), [check])

  return (
    <div className="min-h-screen">
      <Header dark={dark} onToggleTheme={toggle} />

      <main className="mx-auto max-w-7xl space-y-6 px-4 py-8 sm:px-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h2 className="text-2xl font-semibold tracking-tight text-slate-900 dark:text-white">Datasheet compliance check</h2>
            <p className="mt-1 max-w-2xl text-sm text-slate-500 dark:text-slate-400">
              An LLM agent finds and quotes values in the datasheet. A deterministic rule engine decides PASS / FAIL /
              UNCLEAR, and every quote is verified against its page.
            </p>
          </div>
          <div className="flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400">
            <ShieldCheck className="size-4 text-emerald-600" aria-hidden />
            LLM extracts · Python decides · Human reviews
          </div>
        </div>

        {health?.mode === 'offline' && (
          <div className="flex gap-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-900/60 dark:bg-amber-500/10 dark:text-amber-200" role="status">
            <Info className="mt-0.5 size-4 shrink-0" aria-hidden />
            <p>
              <strong>Offline demo mode.</strong> No <code className="font-mono">OPENAI_API_KEY</code> is configured, so a
              scripted agent replays a realistic run on the built-in sample. Add a key to <code className="font-mono">.env</code> to
              use the live LLM agent on any PDF.
            </p>
          </div>
        )}
        {loading && slowStart && (
          <div
            className="flex items-center gap-3 rounded-lg border border-accent-100 bg-accent-50/60 p-3 text-sm text-slate-700 dark:border-accent-600/30 dark:bg-accent-600/10 dark:text-slate-200"
            role="status"
          >
            <Loader2 className="size-4 shrink-0 animate-spin text-accent-600 dark:text-accent-400" aria-hidden />
            <p>
              <strong>Starting the demo server…</strong> The free hosting sleeps when idle, so the first load can take up
              to a minute.
            </p>
          </div>
        )}
        {loadError && <ErrorBanner title="Still waking up" messages={[loadError]} onDismiss={() => setLoadError(null)} />}

        <RequirementsEditor requirements={requirements} onChange={setRequirements} templates={templates} disabled={check.running} />
        <DatasheetPicker samples={samples} selected={datasheet} onSelect={setDatasheet} disabled={check.running} />

        <div className="card flex flex-wrap items-center justify-between gap-4 px-5 py-4">
          <div className="text-sm">
            <p className="font-medium text-slate-900 dark:text-white">
              {requirements.length} requirement{requirements.length === 1 ? '' : 's'} against{' '}
              <span className="font-mono text-accent-700 dark:text-accent-400">{datasheet?.filename ?? 'no datasheet'}</span>
            </p>
            <p className="text-xs text-slate-500 dark:text-slate-400" id="run-hint">
              {disabledReason ?? 'Cost is capped per run (max steps, pages and tokens).'}
            </p>
          </div>
          <Button
            variant="primary"
            size="lg"
            icon={<Play className="size-4" />}
            loading={check.running}
            disabled={!canRun}
            onClick={run}
            aria-describedby="run-hint"
          >
            {check.running ? 'Agent running…' : 'Run check'}
          </Button>
        </div>
        {check.error && <ErrorBanner title="Check failed" messages={[check.error]} onDismiss={check.clearError} />}

        <div className="grid gap-6 xl:grid-cols-5">
          <div className="xl:col-span-2">
            <AgentTimeline events={check.events} running={check.running} />
          </div>
          <div className="xl:col-span-3">
            <ResultsPanel run={check.run} loading={check.running} onSelect={(r) => setSelectedId(r.requirement.id)} />
          </div>
        </div>
      </main>

      <footer className="mx-auto max-w-7xl px-4 pb-10 text-center text-xs text-slate-400 sm:px-6">
        SpecCheck · The sample datasheet describes a fictional device · Always review UNCLEAR results
      </footer>

      {selected && check.run && (
        <DetailDrawer
          checkId={check.run.id}
          datasheetId={check.run.datasheet.id}
          result={selected}
          onClose={closeDrawer}
          onUpdated={onUpdated}
        />
      )}
    </div>
  )
}
