import { CheckCircle2, HelpCircle, XCircle } from 'lucide-react'
import type { Status } from '../api/types'

const STYLES: Record<Status, { className: string; icon: typeof CheckCircle2; label: string }> = {
  PASS: {
    className:
      'bg-emerald-50 text-emerald-700 ring-emerald-600/20 dark:bg-emerald-500/10 dark:text-emerald-400 dark:ring-emerald-400/30',
    icon: CheckCircle2,
    label: 'Pass',
  },
  FAIL: {
    className: 'bg-rose-50 text-rose-700 ring-rose-600/20 dark:bg-rose-500/10 dark:text-rose-400 dark:ring-rose-400/30',
    icon: XCircle,
    label: 'Fail',
  },
  UNCLEAR: {
    className:
      'bg-amber-50 text-amber-800 ring-amber-600/25 dark:bg-amber-500/10 dark:text-amber-300 dark:ring-amber-400/30',
    icon: HelpCircle,
    label: 'Unclear',
  },
}

export function StatusBadge({ status, overridden = false }: { status: Status; overridden?: boolean }) {
  const { className, icon: Icon, label } = STYLES[status]
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ring-1 ring-inset ${className}`}
      aria-label={`Status: ${label}${overridden ? ' (overridden by reviewer)' : ''}`}
    >
      <Icon className="size-3.5" aria-hidden />
      {status}
      {overridden && (
        <span className="font-normal opacity-75" aria-hidden>
          ✎
        </span>
      )}
    </span>
  )
}
