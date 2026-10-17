import { useEffect, useState } from 'react'
import { loadEvents, type EventType, type RunEvent } from './events'

const SENTRY_ORG_URL = 'https://la-hacksss.sentry.io'

// Run id comes from ?run=<id>; the fake stream lives in runs/sample/.
const runId = new URLSearchParams(location.search).get('run') ?? 'sample'

export default function App() {
  const [events, setEvents] = useState<RunEvent[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    loadEvents(runId).then(setEvents, (e: Error) => setError(e.message))
  }, [])

  const first = events[0]
  const finished = events.find((e) => e.type === 'run_finished')
  const healed = events.some((e) => e.type === 'healed')

  return (
    <div className="flex min-h-screen flex-col">
      <Chrome runId={first?.run_id ?? runId} finished={!!finished} healed={healed} />
      <main className="flex flex-1 flex-col lg:flex-row">
        <aside className="flex flex-col justify-between gap-12 border-ink px-6 py-10 lg:w-[560px] lg:shrink-0 lg:border-r-[1.5px] lg:px-10 lg:pt-12">
          <Wordmark />
          {finished && <Summary finished={finished} />}
        </aside>
        <section className="flex min-w-0 flex-1 flex-col gap-6 px-6 py-10 lg:px-12 lg:pt-12">
          <header className="flex flex-wrap items-end justify-between gap-4">
            <div className="flex flex-col gap-1.5">
              <span className="text-[13px] font-medium uppercase tracking-[0.14em] text-muted">
                {first ? `${first.program} · ${modeLabel(events)}` : 'Loading run'}
              </span>
              <h1 className="font-display text-[44px] font-extrabold leading-[44px] tracking-[-0.03em]">
                Every step, seen.
              </h1>
            </div>
            <Legend />
          </header>
          {error ? <p className="text-fail">{error}</p> : <EventList events={events} />}
          <div className="flex-1" />
          {first && <SentryFooter event={events.find((e) => e.type === 'healed') ?? first} />}
        </section>
      </main>
    </div>
  )
}

function modeLabel(events: RunEvent[]) {
  const versions = [...new Set(events.map((e) => e.version))]
  const span = versions.length > 1 ? `v${versions[0]} → v${versions.at(-1)}` : `v${versions[0]}`
  return `${span} · ${events[0].mode}`
}

function Chrome({ runId, finished, healed }: { runId: string; finished: boolean; healed: boolean }) {
  const status = finished ? (healed ? 'Healed · finished' : 'Finished') : 'Running'
  return (
    <div className="flex items-center gap-5 border-b-[1.5px] border-ink px-6 py-3.5 lg:px-10">
      <div className="flex shrink-0 gap-2">
        <span className="size-3 rounded-full bg-fail" />
        <span className="size-3 rounded-full bg-pass" />
      </div>
      <div className="flex min-w-0 flex-1 items-center gap-2.5 rounded-full border-[1.5px] border-ink px-3.5 py-2 font-mono text-sm">
        <EyeIcon className="size-4 shrink-0" />
        <span className="text-muted">browseen://</span>
        <span className="truncate font-semibold">runs/{runId}</span>
      </div>
      <div className="flex shrink-0 items-center gap-2 rounded-full bg-ink px-3.5 py-2 text-[13px] font-medium uppercase tracking-[0.06em] text-chart">
        <span className={`size-2 rounded-full ${healed ? 'bg-heal' : 'bg-pass'}`} />
        <span className="hidden sm:inline">{status}</span>
      </div>
    </div>
  )
}

function Wordmark() {
  return (
    <div className="flex flex-col gap-3.5">
      <span className="text-[13px] font-medium uppercase tracking-[0.14em] text-muted">
        Self-healing agent compiler
      </span>
      <div
        aria-label="Browseen"
        className="font-display condensed flex items-center text-[clamp(56px,9vw,120px)] font-extrabold leading-[0.85] tracking-[-0.04em]"
      >
        <span>BROWS</span>
        <span className="flex shrink-0 gap-[0.05em] px-[0.05em]">
          <Eye className="h-[0.73em] w-auto" pupil="var(--color-ink)" />
          <Eye className="eye-heal h-[0.73em] w-auto" pupil="var(--color-heal)" />
        </span>
        <span>N</span>
      </div>
    </div>
  )
}

function Eye({ className, pupil }: { className?: string; pupil: string }) {
  return (
    <svg className={className} viewBox="0 0 76 88" fill="none" aria-hidden>
      <path
        d="M4 44C14 22 26 12 38 12s24 10 34 32c-10 22-22 32-34 32S14 66 4 44z"
        stroke="currentColor"
        strokeWidth="10"
        strokeLinejoin="round"
      />
      <circle cx="48" cy="44" r="12" fill={pupil} />
    </svg>
  )
}

function EyeIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z" stroke="currentColor" strokeWidth="2" />
      <circle cx="12" cy="12" r="3" fill="currentColor" />
    </svg>
  )
}

function Summary({ finished }: { finished: RunEvent }) {
  // The first-run (agent) column needs a baseline run in the stream; until A
  // emits one, it shows a dash instead of made-up numbers.
  const rows: [string, string][] = [
    ['Time', `${finished.seconds?.toFixed(1) ?? '—'} s`],
    ['Tokens', finished.tokens.toLocaleString()],
    ['Cost', `$${finished.usd.toFixed(3)}`],
    ['LLM calls', String(finished.llm_calls)],
  ]
  return (
    <div className="flex flex-col border-t-[1.5px] border-ink">
      <div className="flex py-2.5 text-xs font-medium uppercase tracking-[0.12em] text-muted">
        <span className="w-24 shrink-0 sm:w-40" />
        <span className="flex-1 text-right">First run · agent</span>
        <span className="flex-1 text-right text-ink">Compiled · v{finished.version}</span>
      </div>
      {rows.map(([label, value]) => (
        <div key={label} className="flex items-baseline border-t border-rule py-3 font-mono text-[15px]">
          <span className="w-24 shrink-0 font-sans text-muted sm:w-40">{label}</span>
          <span className="flex-1 text-right text-muted">—</span>
          <span className="flex-1 text-right text-[22px] font-bold">{value}</span>
        </div>
      ))}
    </div>
  )
}

function Legend() {
  return (
    <div className="flex gap-4 pb-1.5 text-[13px]">
      {[
        ['bg-pass', 'passed'],
        ['bg-fail', 'failed'],
        ['bg-heal', 'healed'],
      ].map(([bg, label]) => (
        <span key={label} className="flex items-center gap-1.5">
          <span className={`size-2.5 rounded-full ${bg}`} />
          {label}
        </span>
      ))}
    </div>
  )
}

const DOT: Record<EventType, string> = {
  run_started: 'bg-ink',
  step_started: 'bg-rule',
  check_passed: 'bg-pass',
  check_failed: 'bg-fail',
  heal_started: 'border-2 border-heal bg-chart',
  healed: 'bg-heal',
  heal_failed: 'bg-fail',
  run_finished: 'bg-ink',
}

function EventList({ events }: { events: RunEvent[] }) {
  return (
    <ol className="flex flex-col border-t-[1.5px] border-ink">
      {events.map((e, i) => {
        const isHeal = e.type === 'healed'
        const isFail = e.type === 'check_failed' || e.type === 'heal_failed'
        const quiet = e.type === 'step_started'
        return (
          <li
            key={i}
            className={`flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-rule py-3 pr-4 font-mono text-sm sm:flex-nowrap ${
              isHeal ? 'border-l-4 border-l-heal bg-heal-wash pl-3' : 'pl-4'
            } ${quiet ? 'text-muted' : ''}`}
          >
            <span className={`size-2.5 shrink-0 rounded-full ${DOT[e.type]}`} />
            <span className="hidden w-[84px] shrink-0 text-muted sm:inline">{e.ts.slice(11, 21)}</span>
            <span
              className={`w-[104px] shrink-0 font-semibold sm:w-[120px] ${isHeal ? 'font-bold text-heal-ink' : ''} ${
                isFail ? 'text-fail' : ''
              } ${quiet ? 'font-normal' : ''}`}
            >
              {e.type}
            </span>
            <span className="w-7 shrink-0 text-muted">{e.step ?? '—'}</span>
            <span
              className={`order-last min-w-0 basis-full pl-[26px] font-sans text-[15px] sm:order-none sm:flex-1 sm:basis-auto sm:pl-0 ${isHeal ? 'font-medium' : 'truncate'} ${
                e.type === 'run_finished' ? 'font-bold' : ''
              }`}
              title={e.detail}
            >
              {e.detail}
            </span>
            <span className={`ml-auto w-24 shrink-0 sm:w-28 text-right ${e.llm_calls ? 'text-heal-ink' : 'text-muted'}`}>
              {e.llm_calls ? `${e.llm_calls} · $${e.usd.toFixed(3)}` : '0 LLM'}
            </span>
          </li>
        )
      })}
    </ol>
  )
}

function SentryFooter({ event }: { event: RunEvent }) {
  const traceUrl = `${SENTRY_ORG_URL}/explore/traces/trace/${event.trace_id}`
  return (
    <div className="flex flex-wrap items-center justify-between gap-4 rounded-[14px] bg-ink px-5 py-4 text-chart">
      <div className="flex flex-col gap-1">
        <span className="text-xs font-medium uppercase tracking-[0.14em] text-[#a8a8ae]">Seen by Sentry</span>
        <span className="text-[17px] font-medium">
          {event.type === 'healed' ? `Step ${event.step} healed in trace ` : 'Trace '}
          {event.trace_id.slice(0, 8)}
        </span>
      </div>
      <a
        href={traceUrl}
        target="_blank"
        rel="noreferrer"
        className="rounded-full bg-heal px-4 py-2.5 text-sm font-semibold text-ink hover:brightness-110"
      >
        Open trace →
      </a>
    </div>
  )
}
