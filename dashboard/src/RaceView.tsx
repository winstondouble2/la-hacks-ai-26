import type { RunEvent } from './events'
import { compareRuns, totalsAt, visibleAt } from './replay'

// Both runs replay on one clock, so the compiled run visibly finishes while
// the agent is still on its first steps.
export default function RaceView({
  baseline,
  compiled,
  elapsed,
}: {
  baseline: RunEvent[]
  compiled: RunEvent[]
  elapsed: number
}) {
  const steps = [...new Set([...baseline, ...compiled].map((e) => e.step).filter((s): s is string => !!s))]
  const b = baseline.length ? totalsAt(baseline, elapsed) : null
  const c = compiled.length ? totalsAt(compiled, elapsed) : null
  // Savings only once both runs are complete; partial runs would mislead.
  const cmp = b?.finished && c?.finished ? compareRuns(b, c) : null
  const fmt = (v: number | null | undefined, f: (n: number) => string) => (v === null || v === undefined ? '—' : f(v))
  return (
    <div className="flex flex-col gap-6">
      <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {(
          [
            ['Time saved', fmt(cmp?.secondsSaved, (n) => `${n.toFixed(1)} s`), fmt(cmp?.speedup, (n) => `${n.toFixed(1)}× faster`)],
            ['Tokens', fmt(cmp?.tokenReduction, (n) => `−${Math.round(n * 100)}%`), 'vs the agent run'],
            ['LLM calls avoided', fmt(cmp?.llmCallsAvoided, String), ''],
            ['LLM cost saved', fmt(cmp?.llmUsdSaved, (n) => `$${n.toFixed(3)}`), 'model spend only'],
          ] as const
        ).map(([label, value, note]) => (
          <div key={label} className="flex flex-col">
            <dt className="text-xs font-medium uppercase tracking-[0.12em] text-muted">{label}</dt>
            <dd className="font-mono text-2xl font-bold tabular-nums">{value}</dd>
            <dd className="text-xs text-muted">{cmp ? note : 'when both runs finish'}</dd>
          </div>
        ))}
      </dl>
      <div className="grid gap-6 md:grid-cols-2">
        <Lane label="First run · agent" events={baseline} steps={steps} elapsed={elapsed} />
        <Lane label="Compiled replay" events={compiled} steps={steps} elapsed={elapsed} accent />
      </div>
      <p className="text-xs text-muted">
        Input and output tokens aren't separate in the event stream yet, so lanes show the total. Outcomes are what each
        system reported; verification needs the testbed's /__verify.
      </p>
    </div>
  )
}

function Lane({
  label,
  events,
  steps,
  elapsed,
  accent,
}: {
  label: string
  events: RunEvent[]
  steps: string[]
  elapsed: number
  accent?: boolean
}) {
  if (!events.length) {
    return (
      <div className="flex flex-col gap-3 border-t-[1.5px] border-ink pt-3">
        <span className="text-xs font-medium uppercase tracking-[0.12em] text-muted">{label}</span>
        <p className="text-sm text-muted">No run to compare yet. Pass ?baseline=&lt;run_id&gt;.</p>
      </div>
    )
  }
  const seen = visibleAt(events, elapsed)
  const now = totalsAt(events, elapsed)
  const done = new Set(seen.filter((e) => e.type === 'check_passed' || e.type === 'healed').map((e) => e.step))
  const healed = new Set(seen.filter((e) => e.type === 'healed').map((e) => e.step))
  const failing = new Set(
    seen.filter((e) => e.type === 'check_failed' && !healed.has(e.step)).map((e) => e.step),
  )
  const latest = seen.slice(-7)
  const finishedEvent = seen.find((e) => e.type === 'run_finished')
  const current = finishedEvent ? null : seen.filter((e) => e.type === 'step_started').at(-1)?.step
  const status = !finishedEvent
    ? current ? `running ${current}` : 'starting'
    : finishedEvent.success ? 'reported success' : 'stopped / failed'

  return (
    <div className="flex min-w-0 flex-col gap-4 border-t-[1.5px] border-ink pt-3">
      <div className="flex items-baseline justify-between gap-3">
        <span className={`text-xs font-medium uppercase tracking-[0.12em] ${accent ? 'text-ink' : 'text-muted'}`}>
          {label}
        </span>
        <span className="font-mono text-xs text-muted tabular-nums">
          {now.llmCalls} LLM · {now.tokens.toLocaleString()} tok · ${now.usd.toFixed(3)}
        </span>
      </div>
      <div className="flex items-end gap-3">
        <span className="font-display condensed text-[72px] leading-[60px] font-extrabold tracking-[-0.03em] tabular-nums">
          {now.seconds.toFixed(1)}
          <span className="text-[32px]">s</span>
        </span>
        <span
          className={`mb-1 rounded-full px-2.5 py-1 text-xs font-semibold ${
            !finishedEvent ? 'border border-ink' : finishedEvent.success ? (accent ? 'bg-pass text-chart' : 'bg-ink text-chart') : 'bg-fail text-chart'
          }`}
        >
          {status}
        </span>
      </div>
      <div className="flex gap-1" aria-label="Steps completed">
        {steps.map((s) => (
          <div key={s} className="flex flex-1 flex-col items-center gap-1">
            <div
              className={`h-2.5 w-full rounded-full transition-colors duration-300 ${
                healed.has(s) ? 'bg-heal' : failing.has(s) ? 'bg-fail' : done.has(s) ? 'bg-pass' : 'bg-rule'
              }`}
            />
            <span className="font-mono text-[11px] text-muted">{s}</span>
          </div>
        ))}
      </div>
      <ol className="flex min-h-[230px] flex-col gap-1.5 font-mono text-[13px]">
        {latest.map((e, i) => (
          <li key={`${e.ts}${i}`} className={`flex gap-2 ${i === latest.length - 1 ? '' : 'opacity-60'}`}>
            <span className="w-7 shrink-0 text-muted">{e.step ?? '—'}</span>
            <span
              className={`truncate font-sans text-sm ${
                e.type === 'healed' ? 'font-medium text-heal-ink' : e.type === 'check_failed' ? 'text-fail' : ''
              }`}
              title={e.detail}
            >
              {e.detail}
            </span>
          </li>
        ))}
      </ol>
    </div>
  )
}
