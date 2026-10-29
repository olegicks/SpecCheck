import { Moon, Sun } from 'lucide-react'
import type { Health } from '../api/types'

export const GITHUB_URL = 'https://github.com/olegicks/SpecCheck'

function GithubMark() {
  return (
    <svg viewBox="0 0 16 16" className="size-4" fill="currentColor" aria-hidden>
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
    </svg>
  )
}

export function ModeBadge({ health, error }: { health: Health | null; error: boolean }) {
  if (error) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-rose-50 px-2.5 py-1 text-xs font-medium text-rose-700 ring-1 ring-rose-600/20 ring-inset dark:bg-rose-500/10 dark:text-rose-300">
        <span className="size-1.5 rounded-full bg-rose-500" aria-hidden />
        Backend offline
      </span>
    )
  }
  if (!health) {
    return <span className="h-6 w-24 animate-pulse rounded-full bg-slate-200 dark:bg-slate-800" aria-label="Loading mode" />
  }
  const live = health.mode === 'live'
  return (
    <span
      title={live ? `Live OpenAI agent (${health.model})` : 'No API key configured: scripted offline demo'}
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ring-1 ring-inset ${
        live
          ? 'bg-emerald-50 text-emerald-700 ring-emerald-600/20 dark:bg-emerald-500/10 dark:text-emerald-300'
          : 'bg-amber-50 text-amber-800 ring-amber-600/25 dark:bg-amber-500/10 dark:text-amber-300'
      }`}
    >
      <span className="relative flex size-1.5" aria-hidden>
        {live && <span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-400 opacity-75" />}
        <span className={`relative inline-flex size-1.5 rounded-full ${live ? 'bg-emerald-500' : 'bg-amber-500'}`} />
      </span>
      {live ? `Live LLM · ${health.model}` : 'Offline demo'}
    </span>
  )
}

export function Header({
  health,
  healthError,
  dark,
  onToggleTheme,
}: {
  health: Health | null
  healthError: boolean
  dark: boolean
  onToggleTheme: () => void
}) {
  return (
    <header className="sticky top-0 z-30 border-b border-slate-200/80 bg-white/80 backdrop-blur-md dark:border-slate-800 dark:bg-slate-950/80">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-4 px-4 sm:px-6">
        <div className="flex min-w-0 items-center gap-3">
          <img src="/favicon.svg" alt="" className="size-8" />
          <div className="min-w-0">
            <h1 className="text-lg leading-tight font-semibold tracking-tight text-slate-900 dark:text-white">SpecCheck</h1>
            <p className="hidden truncate text-xs text-slate-500 sm:block dark:text-slate-400">
              Traceable AI verification of hardware requirements against datasheets
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <ModeBadge health={health} error={healthError} />
          <button
            type="button"
            onClick={onToggleTheme}
            className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-700 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200"
            aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'}
          >
            {dark ? <Sun className="size-4" /> : <Moon className="size-4" />}
          </button>
          <a
            href={GITHUB_URL}
            target="_blank"
            rel="noreferrer"
            className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-700 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200"
            aria-label="SpecCheck on GitHub"
          >
            <GithubMark />
          </a>
        </div>
      </div>
    </header>
  )
}
