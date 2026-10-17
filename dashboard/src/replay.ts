import { useCallback, useEffect, useRef, useState } from 'react'
import type { RunEvent } from './events'

// Replays recorded runs at their real speed: `elapsed` counts up from 0 to
// `durationMs`, and a run shows only the events whose offset has passed.
export function useReplay(durationMs: number) {
  const [elapsed, setElapsed] = useState(0)
  const startRef = useRef<number | null>(null)
  const frameRef = useRef(0)

  const play = useCallback(() => {
    cancelAnimationFrame(frameRef.current)
    startRef.current = performance.now()
    const tick = (now: number) => {
      const t = Math.min(now - startRef.current!, durationMs)
      setElapsed(t)
      if (t < durationMs) frameRef.current = requestAnimationFrame(tick)
    }
    frameRef.current = requestAnimationFrame(tick)
  }, [durationMs])

  // Start once the runs are loaded, and again if a longer run arrives.
  useEffect(() => {
    if (durationMs > 0) play()
    return () => cancelAnimationFrame(frameRef.current)
  }, [durationMs, play])

  return { elapsed, playing: elapsed < durationMs, play }
}

export function offsetMs(e: RunEvent, start: RunEvent): number {
  return Date.parse(e.ts) - Date.parse(start.ts)
}

export function durationMs(events: RunEvent[]): number {
  return events.length ? offsetMs(events[events.length - 1], events[0]) : 0
}

export function visibleAt(events: RunEvent[], elapsed: number): RunEvent[] {
  return events.length ? events.filter((e) => offsetMs(e, events[0]) <= elapsed) : []
}

export interface Totals {
  seconds: number
  tokens: number
  usd: number
  llmCalls: number
  finished: boolean
}

// Running totals from the events seen so far. Per-event llm_calls/tokens/usd
// are what that event cost; run_finished repeats the run's totals, so skip it.
export function totalsAt(events: RunEvent[], elapsed: number): Totals {
  const seen = visibleAt(events, elapsed)
  const work = seen.filter((e) => e.type !== 'run_finished')
  return {
    seconds: Math.min(elapsed, durationMs(events)) / 1000,
    tokens: work.reduce((n, e) => n + e.tokens, 0),
    usd: work.reduce((n, e) => n + e.usd, 0),
    llmCalls: work.reduce((n, e) => n + e.llm_calls, 0),
    finished: seen.some((e) => e.type === 'run_finished'),
  }
}

export interface Comparison {
  secondsSaved: number | null
  speedup: number | null // baseline seconds ÷ compiled seconds
  tokenReduction: number | null // 0–1
  llmCallsAvoided: number | null
  llmUsdSaved: number | null // model spend only; browser time and infra still cost money
}

// null wherever a side is missing or a ratio would divide by zero.
export function compareRuns(baseline: Totals | null, compiled: Totals | null): Comparison {
  if (!baseline || !compiled) {
    return { secondsSaved: null, speedup: null, tokenReduction: null, llmCallsAvoided: null, llmUsdSaved: null }
  }
  return {
    secondsSaved: baseline.seconds - compiled.seconds,
    speedup: compiled.seconds > 0 ? baseline.seconds / compiled.seconds : null,
    tokenReduction: baseline.tokens > 0 ? 1 - compiled.tokens / baseline.tokens : null,
    llmCallsAvoided: baseline.llmCalls - compiled.llmCalls,
    llmUsdSaved: baseline.usd - compiled.usd,
  }
}

export type RunStatus = 'running' | 'succeeded' | 'failed' | 'stopped'

export interface RunSummary {
  runId: string
  program: string
  version: number
  mode: string
  status: RunStatus
  // What the system reported. Verified success needs the testbed's /__verify (C), which
  // the event stream doesn't carry yet, so the dashboard never shows "verified" from it.
  reportedSuccess: boolean | null
  seconds: number
  llmCalls: number
  tokens: number
  usd: number
  guardFailures: number
  heals: Record<1 | 2 | 3, number>
  healFailures: number
  currentStep: string | null
  traceId: string
}

export function summarize(events: RunEvent[]): RunSummary | null {
  if (!events.length) return null
  const first = events[0]
  const last = events[events.length - 1]
  const finished = events.find((e) => e.type === 'run_finished')
  const totals = totalsAt(events, Number.POSITIVE_INFINITY)
  const heals = { 1: 0, 2: 0, 3: 0 } as Record<1 | 2 | 3, number>
  for (const e of events) if (e.type === 'healed' && e.tier && e.tier in heals) heals[e.tier as 1 | 2 | 3]++
  const healFailures = events.filter((e) => e.type === 'heal_failed').length
  const status: RunStatus = !finished
    ? 'running'
    : finished.success
      ? 'succeeded'
      : healFailures
        ? 'stopped'
        : 'failed'
  const started = events.filter((e) => e.type === 'step_started')
  return {
    runId: first.run_id,
    program: first.program,
    version: last.version,
    mode: first.mode,
    status,
    reportedSuccess: finished ? !!finished.success : null,
    seconds: totals.seconds,
    llmCalls: totals.llmCalls,
    tokens: totals.tokens,
    usd: totals.usd,
    guardFailures: events.filter((e) => e.type === 'check_failed').length,
    heals,
    healFailures,
    currentStep: finished ? null : (started.at(-1)?.step ?? null),
    traceId: first.trace_id,
  }
}
