// Event stream format: docs/architecture.md → "Event stream".
// One JSON object per line in runs/<run_id>/events.jsonl.

export type EventType =
  | 'run_started'
  | 'step_started'
  | 'check_passed'
  | 'check_failed'
  | 'heal_started'
  | 'healed'
  | 'heal_failed'
  | 'run_finished'

export interface RunEvent {
  ts: string
  run_id: string
  program: string
  version: number
  mode: 'llm' | 'compiled' | 'healed'
  type: EventType
  step: string | null
  tier: number | null
  detail: string
  diff: string | null
  llm_calls: number
  tokens: number
  usd: number
  trace_id: string
  // run_finished only
  seconds?: number
  success?: boolean
}

export async function loadEvents(runId: string): Promise<RunEvent[]> {
  const res = await fetch(`/runs/${runId}/events.jsonl`)
  // Vite answers unknown paths with index.html, so check the type too.
  if (!res.ok || res.headers.get('content-type')?.includes('html')) {
    throw new Error(`No events for run ${runId} (${res.status})`)
  }
  return parseEvents(await res.text())
}

// One event from a JSONL line or an SSE message; null if it isn't a usable event.
// Unknown types are kept (A may add some) and simply render as plain rows.
export function parseEvent(line: string): RunEvent | null {
  if (!line.trim()) return null
  try {
    const e = JSON.parse(line)
    if (!e || typeof e !== 'object' || typeof e.ts !== 'string' || typeof e.type !== 'string') return null
    return { llm_calls: 0, tokens: 0, usd: 0, step: null, tier: null, detail: '', diff: null, ...e }
  } catch {
    return null
  }
}

export function parseEvents(text: string): RunEvent[] {
  return dedupeEvents(text.split('\n').map(parseEvent).filter((e): e is RunEvent => e !== null))
}

// SSE reconnects can resend events; the same run, time, type and step is one event.
export function eventKey(e: RunEvent): string {
  return `${e.run_id}|${e.ts}|${e.type}|${e.step ?? ''}`
}

export function dedupeEvents(events: RunEvent[]): RunEvent[] {
  const seen = new Set<string>()
  return events.filter((e) => {
    const key = eventKey(e)
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}
