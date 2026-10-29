import {
  AlertTriangle,
  BrainCircuit,
  CheckCircle2,
  FileSearch,
  FileText,
  Play,
  Scale,
  ScanText,
  Search,
  ShieldAlert,
  ShieldCheck,
  XCircle,
  type LucideIcon,
} from 'lucide-react'
import { useEffect, useRef } from 'react'
import type { AgentEvent, EventType } from '../../api/types'
import { EmptyState, Section } from '../../components/ui'

const ICONS: Record<EventType, { icon: LucideIcon; tone: string; label: string }> = {
  run_started: { icon: Play, tone: 'text-accent-600 bg-accent-50 dark:bg-accent-600/15 dark:text-accent-400', label: 'Start' },
  thinking: { icon: BrainCircuit, tone: 'text-violet-600 bg-violet-50 dark:bg-violet-500/10 dark:text-violet-300', label: 'Model' },
  search: { icon: Search, tone: 'text-sky-600 bg-sky-50 dark:bg-sky-500/10 dark:text-sky-300', label: 'Search' },
  read_page: { icon: FileText, tone: 'text-slate-600 bg-slate-100 dark:bg-slate-800 dark:text-slate-300', label: 'Read page' },
  extract: { icon: ScanText, tone: 'text-indigo-600 bg-indigo-50 dark:bg-indigo-500/10 dark:text-indigo-300', label: 'Extract' },
  submit: { icon: FileSearch, tone: 'text-slate-600 bg-slate-100 dark:bg-slate-800 dark:text-slate-300', label: 'Finding' },
  verify: { icon: ShieldCheck, tone: 'text-emerald-600 bg-emerald-50 dark:bg-emerald-500/10 dark:text-emerald-300', label: 'Verify' },
  decide: { icon: Scale, tone: 'text-slate-600 bg-slate-100 dark:bg-slate-800 dark:text-slate-300', label: 'Rule engine' },
  warning: { icon: AlertTriangle, tone: 'text-amber-600 bg-amber-50 dark:bg-amber-500/10 dark:text-amber-300', label: 'Warning' },
  error: { icon: XCircle, tone: 'text-rose-600 bg-rose-50 dark:bg-rose-500/10 dark:text-rose-300', label: 'Error' },
  run_completed: { icon: CheckCircle2, tone: 'text-emerald-600 bg-emerald-50 dark:bg-emerald-500/10 dark:text-emerald-300', label: 'Done' },
}

function styleFor(event: AgentEvent) {
  if (event.type === 'verify' && event.data.verified === false) {
    return { ...ICONS.verify, icon: ShieldAlert, tone: 'text-amber-600 bg-amber-50 dark:bg-amber-500/10 dark:text-amber-300' }
  }
  return ICONS[event.type]
}

const formatMs = (ms: number) => (ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${ms} ms`)

export function AgentTimeline({ events, running }: { events: AgentEvent[]; running: boolean }) {
  const listRef = useRef<HTMLOListElement>(null)

  useEffect(() => {
    const list = listRef.current
    if (list) list.scrollTop = list.scrollHeight
  }, [events.length])

  const counts = events.reduce<Record<string, number>>((acc, e) => ({ ...acc, [e.type]: (acc[e.type] ?? 0) + 1 }), {})

  return (
    <Section
      title="Agent timeline"
      description="Every tool call the agent makes, streamed live."
      actions={
        events.length > 0 && (
          <p className="text-xs text-slate-500 dark:text-slate-400">
            {counts.search ?? 0} searches · {counts.read_page ?? 0} pages read · {counts.verify ?? 0} quotes checked
          </p>
        )
      }
    >
      {events.length === 0 ? (
        <EmptyState icon={<BrainCircuit className="size-5" />} title={running ? 'Starting agent…' : 'No run yet'}>
          Start a check to watch the agent search the datasheet, read pages, extract values and verify quotes.
        </EmptyState>
      ) : (
        <ol ref={listRef} className="max-h-[440px] space-y-1.5 overflow-y-auto pr-1" aria-label="Agent steps" aria-live="polite">
          {events.map((event) => {
            const { icon: Icon, tone, label } = styleFor(event)
            return (
              <li key={event.seq} className="animate-in flex items-start gap-3 rounded-lg px-2 py-2 hover:bg-slate-50 dark:hover:bg-slate-800/40">
                <span className={`mt-0.5 rounded-md p-1.5 ${tone}`} aria-hidden>
                  <Icon className="size-3.5" />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-slate-800 dark:text-slate-100">
                    <span className="sr-only">{label}: </span>
                    {event.title}
                  </p>
                  {event.detail && <p className="mt-0.5 line-clamp-2 text-xs text-slate-500 dark:text-slate-400">{event.detail}</p>}
                </div>
                {event.duration_ms != null && (
                  <span className="shrink-0 font-mono text-[11px] text-slate-400 tabular-nums">{formatMs(event.duration_ms)}</span>
                )}
              </li>
            )
          })}
          {running && (
            <li className="flex items-center gap-3 px-2 py-2 text-sm text-slate-500" aria-label="Agent is working">
              <span className="flex gap-1" aria-hidden>
                <span className="size-1.5 animate-bounce rounded-full bg-accent-500 [animation-delay:-0.3s]" />
                <span className="size-1.5 animate-bounce rounded-full bg-accent-500 [animation-delay:-0.15s]" />
                <span className="size-1.5 animate-bounce rounded-full bg-accent-500" />
              </span>
              Working…
            </li>
          )}
        </ol>
      )}
    </Section>
  )
}
