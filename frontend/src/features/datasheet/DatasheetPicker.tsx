import { CheckCircle2, FileText, Loader2, UploadCloud } from 'lucide-react'
import { useRef, useState, type DragEvent } from 'react'
import { api } from '../../api/client'
import type { DatasheetSummary } from '../../api/types'
import { ErrorBanner, Section, Skeleton } from '../../components/ui'

const MAX_MB = 10

interface Props {
  samples: DatasheetSummary[] | null
  selected: DatasheetSummary | null
  onSelect: (sheet: DatasheetSummary) => void
  disabled?: boolean
}

function SelectableCard({
  active,
  disabled,
  onClick,
  children,
  label,
}: {
  active: boolean
  disabled: boolean
  onClick: () => void
  children: React.ReactNode
  label: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-pressed={active}
      aria-label={label}
      className={`relative flex w-full items-start gap-3 rounded-lg border p-4 text-left transition-all disabled:cursor-not-allowed disabled:opacity-60 ${
        active
          ? 'border-accent-500 bg-accent-50/60 ring-2 ring-accent-500/20 dark:bg-accent-600/10'
          : 'border-slate-200 hover:border-slate-300 hover:bg-slate-50 dark:border-slate-700 dark:hover:border-slate-600 dark:hover:bg-slate-800/40'
      }`}
    >
      {children}
      {active && <CheckCircle2 className="absolute top-3 right-3 size-4 text-accent-600 dark:text-accent-400" aria-hidden />}
    </button>
  )
}

export function DatasheetPicker({ samples, selected, onSelect, disabled = false }: Props) {
  const [uploading, setUploading] = useState(false)
  const [uploaded, setUploaded] = useState<DatasheetSummary | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const input = useRef<HTMLInputElement>(null)

  const upload = async (file: File) => {
    setError(null)
    if (!/\.pdf$/i.test(file.name) && file.type !== 'application/pdf') {
      setError('Please choose a PDF file.')
      return
    }
    if (file.size > MAX_MB * 1024 * 1024) {
      setError(`The file is larger than ${MAX_MB} MB.`)
      return
    }
    setUploading(true)
    try {
      const sheet = await api.uploadDatasheet(file)
      setUploaded(sheet)
      onSelect(sheet)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setUploading(false)
    }
  }

  const onDrop = (e: DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files[0]
    if (file && !disabled) void upload(file)
  }

  return (
    <Section step={2} title="Datasheet" description="Use the built-in fictional sample or upload a PDF (max 10 MB, 80 pages). Uploads stay in memory only.">
      <div className="space-y-3">
        <div className="grid gap-3 md:grid-cols-2">
          {samples === null ? (
            <Skeleton className="h-24" />
          ) : (
            samples.map((s) => (
              <SelectableCard
                key={s.id}
                active={selected?.id === s.id}
                disabled={disabled}
                onClick={() => onSelect(s)}
                label={`Use sample datasheet ${s.filename}`}
              >
                <div className="rounded-md bg-accent-50 p-2 text-accent-600 dark:bg-accent-600/15 dark:text-accent-400">
                  <FileText className="size-5" aria-hidden />
                </div>
                <div className="min-w-0 pr-5">
                  <p className="flex items-center gap-2 font-medium text-slate-900 dark:text-white">
                    SC-MCU-100
                    <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold tracking-wide text-slate-500 uppercase dark:bg-slate-800 dark:text-slate-400">
                      Sample · fictional
                    </span>
                  </p>
                  <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
                    {s.filename} · {s.page_count} pages
                  </p>
                  {s.description && <p className="mt-1.5 text-xs text-slate-500 dark:text-slate-400">{s.description}</p>}
                </div>
              </SelectableCard>
            ))
          )}

          {uploaded ? (
            <div className="relative">
              <SelectableCard
                active={selected?.id === uploaded.id}
                disabled={disabled}
                onClick={() => onSelect(uploaded)}
                label={`Use uploaded datasheet ${uploaded.filename}`}
              >
                <div className="rounded-md bg-slate-100 p-2 text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                  <FileText className="size-5" aria-hidden />
                </div>
                <div className="min-w-0 pr-5 pb-5">
                  <p className="truncate font-medium text-slate-900 dark:text-white">{uploaded.filename}</p>
                  <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">Uploaded · {uploaded.page_count} pages</p>
                </div>
              </SelectableCard>
              <button
                type="button"
                disabled={disabled || uploading}
                onClick={() => input.current?.click()}
                className="absolute bottom-3 left-[3.75rem] text-xs text-accent-600 hover:underline disabled:opacity-50 dark:text-accent-400"
              >
                {uploading ? 'Uploading…' : 'Replace file'}
              </button>
            </div>
          ) : (
            <div
              role="button"
              tabIndex={disabled ? -1 : 0}
              aria-label="Upload a PDF datasheet: drop a file here or press Enter to browse"
              aria-disabled={disabled}
              onClick={() => !disabled && input.current?.click()}
              onKeyDown={(e) => {
                if ((e.key === 'Enter' || e.key === ' ') && !disabled) {
                  e.preventDefault()
                  input.current?.click()
                }
              }}
              onDragOver={(e) => {
                e.preventDefault()
                setDragOver(true)
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={onDrop}
              className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed p-4 text-center transition-colors ${
                dragOver
                  ? 'border-accent-500 bg-accent-50/60 dark:bg-accent-600/10'
                  : 'border-slate-300 hover:border-slate-400 hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800/40'
              } ${disabled ? 'pointer-events-none opacity-60' : ''}`}
            >
              {uploading ? (
                <>
                  <Loader2 className="size-6 animate-spin text-accent-600" aria-hidden />
                  <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">Uploading and indexing…</p>
                </>
              ) : (
                <>
                  <UploadCloud className="size-6 text-slate-400" aria-hidden />
                  <p className="mt-2 text-sm text-slate-700 dark:text-slate-200">
                    <span className="font-medium text-accent-600 dark:text-accent-400">Upload a PDF</span> or drag and drop
                  </p>
                  <p className="text-xs text-slate-500 dark:text-slate-400">Text-based PDFs only · max {MAX_MB} MB</p>
                </>
              )}
            </div>
          )}
        </div>
        <input
          ref={input}
          type="file"
          accept="application/pdf,.pdf"
          className="hidden"
          aria-label="Choose PDF datasheet"
          data-testid="pdf-input"
          onChange={(e) => {
            const file = e.target.files?.[0]
            if (file) void upload(file)
            e.target.value = ''
          }}
        />
        {error && <ErrorBanner title="Upload failed" messages={[error]} onDismiss={() => setError(null)} />}
      </div>
    </Section>
  )
}
