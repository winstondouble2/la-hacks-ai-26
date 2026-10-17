import { useState } from 'react'
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

type Rung = 'passed' | 'failed' | 'no data'

// The stages of one step, kept apart: finding the element, the pre-check, acting, the
// post-check and the receipt are different claims. The event stream only says
// check_passed / check_failed, so later stages are inferred (a post-check can only pass
// after the action ran) and anything it can't tell is "no data".
function ladder(step: Step, events: RunEvent[]): [string, Rung, string][] {
  const mine = events.filter((e) => e.step === step.id)
  const failed = mine.filter((e) => e.type === 'check_failed')
  const passed = mine.some((e) => e.type === 'check_passed' || e.type === 'healed')
  const preFail = failed.some((e) => /^pre/i.test(e.detail))
  const postFail = failed.some((e) => /^post/i.test(e.detail))
  const locatorFail = failed.some((e) => /not found|not unique/i.test(e.detail))
  const inferred = passed ? 'inferred from a passing post-check' : ''
  return [
    ['Locator resolved', passed ? 'passed' : locatorFail ? 'failed' : 'no data', locatorFail && !passed ? 'first locator missed' : inferred],
    ['Guard (pre-check) passed', preFail ? 'failed' : passed ? 'passed' : 'no data', preFail ? 'see failed check' : inferred],
    ['Action executed', passed ? 'passed' : 'no data', inferred],
    ['Post-check passed', passed ? 'passed' : postFail ? 'failed' : 'no data', ''],
    ['Receipt verified', 'no data', step.action.type === 'click' ? 'backend receipt check, not in the event stream' : 'n/a for reads'],
  ]
}

const RUNG_STYLE: Record<Rung, string> = { passed: 'text-pass', failed: 'text-fail', 'no data': 'text-muted' }

const STATUS_STYLE: Record<Status, string> = {
  healed: 'bg-heal text-ink',
  passed: 'bg-pass text-chart',
  failed: 'bg-fail text-chart',
  'not run': 'border border-rule text-muted',
}

export default function ProgramView({ program, events }: { program: Program; events: RunEvent[] }) {
  const [open, setOpen] = useState<string | null>(null)
  const healEvents = new Map(events.filter((e) => e.type === 'healed' && e.step).map((e) => [e.step!, e]))
  const healedHere = new Map(
    (program.history ?? [])
      .filter((h) => h.source === 'healed' && h.version === program.version && h.step)
      .map((h) => [h.step!, h]),
  )
  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-1.5 font-mono text-[13px] text-muted">
        <span>
          task <span className="text-ink">{program.task}</span>
        </span>
        <span className="flex flex-wrap gap-x-6 gap-y-1">
          <span>
            params{' '}
            <span className="text-ink">
              {Object.entries(program.params ?? {})
                .map(([k, p]) => `$${k}: ${p.type}${p.example !== undefined ? ` (${p.example})` : ''}`)
                .join(', ')}
            </span>
          </span>
          <span>
            start <span className="text-ink">{program.start_url}</span>
          </span>
        </span>
      </div>
      <ol className="flex flex-col border-t-[1.5px] border-ink">
        {program.steps.map((step, i) => {
          const status = stepStatus(step, events)
          const heal = healedHere.get(step.id)
          const healedInRun = healEvents.get(step.id)
          const gold = !!heal || !!healedInRun
          return (
            <li
              key={step.id}
              className={`flex gap-4 border-b border-rule py-4 pr-4 ${
                gold ? 'border-l-4 border-l-heal bg-heal-wash pl-3' : 'pl-4'
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
                {!heal && healedInRun && (
                  <span className="text-sm text-heal-ink">
                    Healed in this run at tier {healedInRun.tier}: {healedInRun.detail}
                    {healedInRun.tier === 1 ? ' (tier 1 heals are not saved as a new version)' : ''}
                  </span>
                )}
                {open === step.id && <StepDetails step={step} events={events} />}
                <button onClick={() => setOpen(open === step.id ? null : step.id)} className="self-start text-xs text-muted underline">
                  {open === step.id ? 'Hide guard details' : 'Guard details'}
                </button>
              </div>
              <span
                className={`h-fit w-[72px] shrink-0 rounded-full py-1 text-center font-mono text-[11px] font-semibold uppercase tracking-wider ${STATUS_STYLE[status]}`}
              >
                {status}
                {status === 'healed' && healedInRun?.tier ? ` T${healedInRun.tier}` : ''}
              </span>
            </li>
          )
        })}
      </ol>
      <div className="font-mono text-[13px] text-muted">
        success <span className="text-ink">{(program.success ?? []).map(describeCheck).join(', ')}</span>
      </div>
    </div>
  )
}

function StepDetails({ step, events }: { step: Step; events: RunEvent[] }) {
  return (
    <div className="mt-1 grid gap-4 rounded-lg bg-chart/70 p-3 text-[13px] ring-1 ring-rule sm:grid-cols-2">
      <div className="flex flex-col gap-1.5">
        <span className="text-xs font-medium uppercase tracking-[0.1em] text-muted">This run</span>
        {ladder(step, events).map(([label, rung, note]) => (
          <div key={label} className="flex items-baseline gap-2">
            <span className={`w-14 shrink-0 font-mono text-[11px] font-semibold uppercase ${RUNG_STYLE[rung]}`}>{rung}</span>
            <span className="flex flex-col">
              <span className="whitespace-nowrap">{label}</span>
              {note && <span className="text-xs text-muted">{note}</span>}
            </span>
          </div>
        ))}
      </div>
      <div className="flex flex-col gap-1.5 font-mono">
        <span className="font-sans text-xs font-medium uppercase tracking-[0.1em] text-muted">Locators, tried in order</span>
        {(step.target?.locators ?? []).map((l, i) => (
          <span key={i}>{i + 1}. {describeLocator(l)}</span>
        ))}
        {!step.target && <span className="text-muted">no target ({step.action.type})</span>}
        {step.target?.fingerprint && (
          <span className="text-xs text-muted">
            fingerprint: {Object.entries(step.target.fingerprint).filter(([k]) => k !== 'attributes').map(([k, v]) => `${k}=${v}`).join(' ')}
          </span>
        )}
        <span className="text-xs text-muted">branch: {step.when ? `only if ${describeCheck(step.when)}` : 'none'}</span>
        <span className="text-xs text-muted">risk: not in the program format yet (B)</span>
        <span className="text-xs text-muted">timeout: {step.timeout_ms ?? 5000} ms</span>
      </div>
    </div>
  )
}
