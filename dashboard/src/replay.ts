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
