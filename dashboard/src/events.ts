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
  if (!res.ok) throw new Error(`No events for run ${runId} (${res.status})`)
  const text = await res.text()
  return text
    .split('\n')
    .filter((line) => line.trim())
    .map((line) => JSON.parse(line) as RunEvent)
}
