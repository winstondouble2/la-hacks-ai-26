import { API_MODE, SENTRY_ORG_URL, sentryTraceUrl, type StreamState } from './api'
import type { RunEvent } from './events'
import { REAL_DEMO_TRACES } from './fixtures'

// A summary of what the runs did, with links into Sentry for the detail.
// Not a copy of Sentry: traces, logs and replays live there.
export default function ObservabilityView({ runs, stream }: { runs: Record<string, RunEvent[]>; stream: StreamState }) {
  const all = Object.values(runs).flat()
  const byTime = (a: RunEvent, b: RunEvent) => Date.parse(b.ts) - Date.parse(a.ts)
  const failures = all.filter((e) => e.type === 'check_failed').sort(byTime)
  const heals = all.filter((e) => e.type.startsWith('heal')).sort(byTime)
  const takeovers = heals.filter((e) => e.tier === 3)
  const durations = Object.values(runs).flatMap(stepDurations).sort((a, b) => b.ms - a.ms).slice(0, 8)
  const linkable = (e: RunEvent) => (API_MODE === 'real' || REAL_DEMO_TRACES.has(e.trace_id) ? sentryTraceUrl(e.trace_id) : null)

  return (
    <div className="flex flex-col gap-7">
      <div className="flex flex-wrap gap-x-6 gap-y-1 font-mono text-[13px]">
        <span>stream <span className="font-semibold">{stream}</span></span>
        <span>
          sentry{' '}
          {SENTRY_ORG_URL ? (
            <a className="font-semibold underline" href={`${SENTRY_ORG_URL}/explore/traces/`} target="_blank" rel="noreferrer">{SENTRY_ORG_URL.replace('https://', '')}</a>
          ) : (
            <span className="text-muted">not configured (set VITE_SENTRY_ORG_URL)</span>
          )}
        </span>
      </div>

      <Section title="Guard failures" empty="No failed checks.">
        {failures.slice(0, 8).map((e, i) => (
          <Row key={i} e={e} link={linkable(e)} tone="text-fail" />
        ))}
      </Section>

      <Section title="Healing" empty="No healing attempts.">
        {heals.slice(0, 10).map((e, i) => (
          <Row key={i} e={e} link={linkable(e)} tone={e.type === 'healed' ? 'text-heal-ink' : e.type === 'heal_failed' ? 'text-fail' : ''} />
        ))}
      </Section>

      <Section title="Agent takeovers (tier 3)" empty="No tier 3 takeovers.">
        {takeovers.map((e, i) => (
          <Row key={i} e={e} link={linkable(e)} />
        ))}
      </Section>

      <Section title="Slowest steps" empty="No step timings.">
        {durations.map((d, i) => (
          <li key={i} className="flex gap-3 font-mono text-[13px] tabular-nums">
            <span className="w-20 shrink-0 text-muted">{d.run}</span>
            <span className="w-8 shrink-0 font-semibold">{d.step}</span>
            <span className="w-16 shrink-0 text-right">{(d.ms / 1000).toFixed(2)} s</span>
            <span className="truncate font-sans text-sm text-muted">{d.intent}</span>
          </li>
        ))}
      </Section>
      <p className="text-xs text-muted">
        Sentry links appear only for traces that exist. Sample runs other than the demo trace have none.
      </p>
    </div>
  )
}

// From a step's step_started to the next step_started (or the end of the run).
function stepDurations(events: RunEvent[]) {
  const starts = events.map((e, i) => ({ e, i })).filter(({ e }) => e.type === 'step_started')
  return starts.map(({ e, i }, k) => {
    const next = starts[k + 1]?.e ?? events.slice(i).find((x) => x.type === 'run_finished') ?? events[events.length - 1]
    return { run: e.run_id, step: e.step ?? '—', intent: e.detail, ms: Date.parse(next.ts) - Date.parse(e.ts) }
  })
}

function Section({ title, empty, children }: { title: string; empty: string; children: React.ReactNode[] }) {
  return (
    <section className="flex flex-col gap-2">
      <h2 className="border-t-[1.5px] border-ink pt-3 text-xs font-medium uppercase tracking-[0.12em] text-muted">{title}</h2>
      {children.length ? <ol className="flex flex-col gap-1.5">{children}</ol> : <p className="text-sm text-muted">{empty}</p>}
    </section>
  )
}

function Row({ e, link, tone = '' }: { e: RunEvent; link: string | null; tone?: string }) {
  return (
    <li className="flex items-baseline gap-3 font-mono text-[13px]">
      <span className="w-20 shrink-0 text-muted">{e.run_id}</span>
      <span className="w-8 shrink-0 font-semibold">{e.step ?? '—'}</span>
      <span className={`w-36 shrink-0 whitespace-nowrap ${tone}`}>{e.type}{e.tier ? ` T${e.tier}` : ''}</span>
      <span className="min-w-0 flex-1 truncate font-sans text-sm" title={e.detail}>{e.detail}</span>
      {link && <a href={link} target="_blank" rel="noreferrer" className="shrink-0 text-xs underline">trace</a>}
    </li>
  )
}
