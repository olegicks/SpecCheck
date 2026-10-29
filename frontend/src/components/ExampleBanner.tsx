import { FlaskConical, Play, Upload } from 'lucide-react'
import { Button } from './ui'

const TRAPS = ['values only in tables', 'mV instead of V', 'a footnote', 'a variant-dependent value', 'one real failure']

/** Prominent notice that the page starts with a ready-to-run example. */
export function ExampleBanner({
  requirementCount,
  canRun,
  onRun,
  onUseOwn,
}: {
  requirementCount: number
  canRun: boolean
  onRun: () => void
  onUseOwn: () => void
}) {
  return (
    <section
      aria-labelledby="example-title"
      className="animate-in relative overflow-hidden rounded-xl border border-accent-200 bg-gradient-to-br from-accent-50 via-white to-white p-5 shadow-card dark:border-accent-600/40 dark:from-accent-600/20 dark:via-slate-900 dark:to-slate-900"
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 flex-1 gap-4">
          <div className="hidden rounded-xl bg-accent-600 p-2.5 text-white shadow-sm sm:block">
            <FlaskConical className="size-6" aria-hidden />
          </div>
          <div className="min-w-0">
            <p className="text-xs font-semibold tracking-wider text-accent-700 uppercase dark:text-accent-300">Example loaded</p>
            <h2 id="example-title" className="mt-0.5 text-lg font-semibold text-slate-900 dark:text-white">
              Ready to run: {requirementCount} vehicle-computer requirements vs. the fictional SC-MCU-100 datasheet
            </h2>
            <p className="mt-1 max-w-3xl text-sm text-slate-600 dark:text-slate-300">
              This is a demo example, not a real product. The sample datasheet hides deliberate traps:{' '}
              {TRAPS.join(', ')}. Press <strong>Run the example</strong> to watch the AI agent work, or edit the requirements
              and upload your own datasheet.
            </p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="primary" icon={<Play className="size-4" />} onClick={onRun} disabled={!canRun}>
            Run the example
          </Button>
          <Button icon={<Upload className="size-4" />} onClick={onUseOwn}>
            Use your own PDF
          </Button>
        </div>
      </div>
    </section>
  )
}
