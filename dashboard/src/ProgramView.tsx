import type { RunEvent } from './events'
import { describeCheck, describeLocator, type Program, type Step } from './programs'

type Status = 'healed' | 'passed' | 'failed' | 'not run'

// What happened to each step in the run, from the event stream.
function stepStatus(step: Step, events: RunEvent[]): Status {
  const mine = events.filter((e) => e.step === step.id)
  if (mine.some((e) => e.type === 'healed')) return 'healed'
  if (mine.some((e) => e.type === 'heal_failed')) return 'failed'
  if (mine.some((e) => e.type === 'check_passed')) return 'passed'
  if (mine.some((e) => e.type === 'check_failed')) return 'failed'
  return 'not run'
}

const STATUS_STYLE: Record<Status, string> = {
  healed: 'bg-heal text-ink',
  passed: 'bg-pass text-chart',
  failed: 'bg-fail text-chart',
  'not run': 'border border-rule text-muted',
}

export default function ProgramView({ program, events }: { program: Program; events: RunEvent[] }) {
  const healedHere = new Map(program.history.filter((h) => h.version === program.version).map((h) => [h.step, h]))
  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap gap-x-6 gap-y-1 font-mono text-[13px] text-muted">
        <span>
          params{' '}
          <span className="text-ink">
            {Object.entries(program.params)
              .map(([k, t]) => `$${k}: ${t}`)
              .join(', ')}
          </span>
        </span>
        <span>
          start <span className="text-ink">{program.start_url}</span>
        </span>
      </div>
      <ol className="flex flex-col border-t-[1.5px] border-ink">
        {program.steps.map((step, i) => {
          const status = stepStatus(step, events)
          const heal = healedHere.get(step.id)
          return (
            <li
              key={step.id}
              className={`flex gap-4 border-b border-rule py-4 pr-4 ${
                heal ? 'border-l-4 border-l-heal bg-heal-wash pl-3' : 'pl-4'
              }`}
            >
              <div className="flex w-10 shrink-0 flex-col items-start gap-1 pt-0.5 font-mono text-sm">
                <span className="font-bold">{step.id}</span>
                <span className="text-xs text-muted">{String(i + 1).padStart(2, '0')}</span>
              </div>
              <div className="flex min-w-0 flex-1 flex-col gap-2">
                <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                  <span className="text-[17px] font-medium leading-6">{step.intent}</span>
                  {step.when && (
                    <span className="rounded-full border border-ink px-2 py-0.5 font-mono text-xs">
                      only if {describeCheck(step.when)}
                    </span>
                  )}
                  {step.risk === 'write' && (
                    <span className="rounded-full bg-ink px-2 py-0.5 font-mono text-[11px] uppercase tracking-wider text-chart">
                      write
                    </span>
                  )}
                </div>
                <div className="font-mono text-[13px]">
                  <span className="font-semibold">{step.action.type}</span>
                  {step.action.value && <span className="text-muted"> {step.action.value}</span>}
                  {step.action.url && <span className="text-muted"> {step.action.url}</span>}
                  {step.target && (
                    <>
                      <span className="text-muted"> → </span>
                      <span className={heal ? 'font-semibold text-heal-ink' : ''}>
                        {describeLocator(step.target.locators[0])}
                      </span>
                      {step.target.locators.length > 1 && (
                        <span className="text-muted"> +{step.target.locators.length - 1} fallbacks</span>
                      )}
                    </>
                  )}
                </div>
                <div className="flex flex-wrap gap-1.5 font-mono text-[12px]">
                  {step.pre?.map((c, j) => (
                    <span key={`pre${j}`} className="rounded bg-[#f1f1f2] px-1.5 py-0.5">
                      <span className="text-muted">pre </span>
                      {describeCheck(c)}
                    </span>
                  ))}
                  {step.post?.map((c, j) => (
                    <span key={`post${j}`} className="rounded bg-[#f1f1f2] px-1.5 py-0.5">
                      <span className="text-muted">post </span>
                      {describeCheck(c)}
                    </span>
                  ))}
                </div>
                {heal && (
                  <span className="text-sm text-heal-ink">
                    Healed in v{heal.version} at tier {heal.tier}: {heal.reason}
                  </span>
                )}
              </div>
              <span
                className={`h-fit w-[72px] shrink-0 rounded-full py-1 text-center font-mono text-[11px] font-semibold uppercase tracking-wider ${STATUS_STYLE[status]}`}
              >
                {status}
              </span>
            </li>
          )
        })}
      </ol>
      <div className="font-mono text-[13px] text-muted">
        success <span className="text-ink">{program.success.map(describeCheck).join(', ')}</span>
      </div>
    </div>
  )
}
