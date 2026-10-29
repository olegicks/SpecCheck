import { ImageOff, Quote, ShieldAlert, ShieldCheck, Undo2, X } from 'lucide-react'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { api, pageImageUrl } from '../../api/client'
import type { RequirementResult, Status } from '../../api/types'
import { StatusBadge } from '../../components/StatusBadge'
import { Button, ErrorBanner, Skeleton } from '../../components/ui'
import { describe } from '../requirements/requirementUtils'
import { ConfidenceBar } from './ResultsPanel'

const MIN_COMMENT = 3

export function OverrideForm({
  checkId,
  result,
  onSaved,
}: {
  checkId: string
  result: RequirementResult
  onSaved: (updated: RequirementResult) => void
}) {
  const [status, setStatus] = useState<Status>(result.override?.status ?? (result.agent_status === 'PASS' ? 'FAIL' : 'PASS'))
  const [comment, setComment] = useState('')
  const [touched, setTouched] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const commentError = comment.trim().length < MIN_COMMENT ? 'A justification of at least 3 characters is required.' : null

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setTouched(true)
    if (commentError) return
    setSaving(true)
    setError(null)
    try {
      onSaved(await api.override(checkId, result.requirement.id, status, comment.trim()))
      setComment('')
      setTouched(false)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setSaving(false)
    }
  }

  const revert = async () => {
    setSaving(true)
    setError(null)
    try {
      onSaved(await api.clearOverride(checkId, result.requirement.id))
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={submit} className="space-y-3" aria-label="Override status" noValidate>
      {result.override && (
        <div className="rounded-lg border border-accent-100 bg-accent-50/60 p-3 text-sm dark:border-accent-600/30 dark:bg-accent-600/10">
          <p className="font-medium text-slate-800 dark:text-slate-100">
            Overridden: {result.agent_status} → {result.override.status}
          </p>
          <p className="mt-1 text-slate-600 dark:text-slate-300">“{result.override.comment}”</p>
          <Button size="sm" variant="ghost" className="mt-2 -ml-2" icon={<Undo2 className="size-3.5" />} onClick={() => void revert()} disabled={saving}>
            Revert to agent result
          </Button>
        </div>
      )}
      <fieldset>
        <legend className="label mb-1.5">New status</legend>
        <div className="flex gap-2">
          {(['PASS', 'FAIL', 'UNCLEAR'] as Status[]).map((s) => (
            <label
              key={s}
              className={`flex cursor-pointer items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm transition-colors has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-accent-500 ${
                status === s
                  ? 'border-accent-500 bg-accent-50 font-medium text-accent-700 dark:bg-accent-600/15 dark:text-accent-300'
                  : 'border-slate-300 text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800'
              }`}
            >
              <input type="radio" name="override-status" value={s} checked={status === s} onChange={() => setStatus(s)} className="sr-only" />
              {s}
            </label>
          ))}
        </div>
      </fieldset>
      <div>
        <label htmlFor="override-comment" className="label">
          Justification <span className="text-rose-500">*</span>
        </label>
        <textarea
          id="override-comment"
          className={`input mt-1.5 min-h-20 ${touched && commentError ? 'input-error' : ''}`}
          placeholder="e.g. Confirmed with supplier: we order the -Q variant with 1 MB SRAM."
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          onBlur={() => setTouched(true)}
          aria-invalid={touched && !!commentError}
          aria-describedby={touched && commentError ? 'override-comment-error' : undefined}
          maxLength={1000}
          required
        />
        {touched && commentError && (
          <p id="override-comment-error" className="mt-1 text-xs text-rose-600 dark:text-rose-400">
            {commentError}
          </p>
        )}
      </div>
      {error && <ErrorBanner title="Could not save override" messages={[error]} />}
      <Button type="submit" variant="primary" loading={saving}>
        Save override
      </Button>
      <p className="text-xs text-slate-500 dark:text-slate-400">The original agent result is kept and shown in all exports.</p>
    </form>
  )
}

function PagePreview({ datasheetId, page, quote }: { datasheetId: string; page: number; quote?: string | null }) {
  const [state, setState] = useState<'loading' | 'ok' | 'error'>('loading')
  return (
    <figure className="overflow-hidden rounded-lg border border-slate-200 bg-slate-100 dark:border-slate-800 dark:bg-slate-950">
      {state === 'loading' && <Skeleton className="aspect-[1/1.414] w-full rounded-none" />}
      {state === 'error' ? (
        <div className="flex aspect-[1/1.414] flex-col items-center justify-center gap-2 text-sm text-slate-500">
          <ImageOff className="size-6" aria-hidden />
          Page preview unavailable
        </div>
      ) : (
        <img
          src={pageImageUrl(datasheetId, page, quote)}
          alt={`Datasheet page ${page}${quote ? ' with the quoted passage highlighted' : ''}`}
          className={state === 'ok' ? 'block w-full' : 'hidden'}
          onLoad={() => setState('ok')}
          onError={() => setState('error')}
        />
      )}
      <figcaption className="border-t border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-500 dark:border-slate-800 dark:bg-slate-900">
        Page {page} {quote ? '· quote highlighted' : ''}
      </figcaption>
    </figure>
  )
}

export function DetailDrawer({
  checkId,
  datasheetId,
  result,
  onClose,
  onUpdated,
}: {
  checkId: string
  datasheetId: string
  result: RequirementResult
  onClose: () => void
  onUpdated: (updated: RequirementResult) => void
}) {
  const panel = useRef<HTMLDivElement>(null)
  const f = result.finding
  const v = result.verification

  useEffect(() => {
    panel.current?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <div className="absolute inset-0 bg-slate-900/40 backdrop-blur-[2px]" onClick={onClose} aria-hidden />
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby="drawer-title"
        tabIndex={-1}
        className="animate-slide-in relative flex h-full w-full max-w-2xl flex-col bg-white shadow-2xl outline-none dark:bg-slate-900"
      >
        <header className="flex items-start justify-between gap-4 border-b border-slate-200 px-6 py-4 dark:border-slate-800">
          <div className="min-w-0">
            <p className="font-mono text-xs text-slate-400">{result.requirement.id}</p>
            <h2 id="drawer-title" className="text-lg font-semibold text-slate-900 dark:text-white">
              {result.requirement.title}
            </h2>
            <p className="mt-0.5 font-mono text-xs text-slate-500">{describe(result.requirement)}</p>
          </div>
          <div className="flex items-center gap-2">
            <StatusBadge status={result.status} overridden={!!result.override} />
            <button type="button" onClick={onClose} className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800" aria-label="Close details">
              <X className="size-5" />
            </button>
          </div>
        </header>

        <div className="flex-1 space-y-6 overflow-y-auto px-6 py-5">
          <section aria-label="Decision">
            <h3 className="label">Rule engine decision</h3>
            <p className="mt-1.5 text-sm text-slate-700 dark:text-slate-200">{result.reason}</p>
            <dl className="mt-3 grid grid-cols-3 gap-3 text-sm">
              <div>
                <dt className="text-xs text-slate-500">Found value</dt>
                <dd className="font-mono text-slate-800 dark:text-slate-100">{result.found_display ?? '—'}</dd>
              </div>
              <div>
                <dt className="text-xs text-slate-500">Page</dt>
                <dd className="text-slate-800 dark:text-slate-100">{f?.page ?? '—'}</dd>
              </div>
              <div>
                <dt className="text-xs text-slate-500">Confidence</dt>
                <dd>{f && f.value !== null ? <ConfidenceBar value={f.confidence} /> : '—'}</dd>
              </div>
            </dl>
          </section>

          {f?.quote && (
            <section aria-label="Evidence">
              <h3 className="label">Verbatim quote</h3>
              <blockquote className="mt-1.5 flex gap-2 rounded-lg border-l-4 border-accent-500 bg-slate-50 px-4 py-3 text-sm text-slate-800 dark:bg-slate-800/50 dark:text-slate-100">
                <Quote className="mt-0.5 size-4 shrink-0 text-accent-500" aria-hidden />
                <span className="font-mono text-[13px] leading-relaxed">{f.quote}</span>
              </blockquote>
              {v && (
                <p className={`mt-2 flex items-center gap-1.5 text-xs ${v.verified ? 'text-emerald-700 dark:text-emerald-400' : 'text-amber-700 dark:text-amber-400'}`}>
                  {v.verified ? <ShieldCheck className="size-3.5" aria-hidden /> : <ShieldAlert className="size-3.5" aria-hidden />}
                  {v.verified ? `Quote verified on page ${f.page} (${v.method} match, ${Math.round(v.score)}%)` : `Quote NOT verified: ${v.reason}`}
                </p>
              )}
            </section>
          )}

          {f?.notes && (
            <section aria-label="Agent notes">
              <h3 className="label">Agent reasoning</h3>
              <p className="mt-1.5 text-sm text-slate-600 dark:text-slate-300">{f.notes}</p>
            </section>
          )}

          {f?.page ? <PagePreview key={`${f.page}-${f.quote}`} datasheetId={datasheetId} page={f.page} quote={f.quote} /> : null}

          <section aria-label="Human review" className="rounded-xl border border-slate-200 p-4 dark:border-slate-800">
            <h3 className="mb-3 text-sm font-semibold text-slate-900 dark:text-white">Human review</h3>
            <OverrideForm key={result.override?.created_at ?? 'none'} checkId={checkId} result={result} onSaved={onUpdated} />
          </section>
        </div>
      </div>
    </div>
  )
}
