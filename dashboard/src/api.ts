// The dashboard's only data layer. VITE_API_MODE=mock (default) reads the repo's
// runs/ and programs/ plus fixtures.ts; VITE_API_MODE=real calls A's API at
// VITE_API_BASE_URL. Real mode never falls back to mock data: a failed request is an
// error the UI shows. Endpoints are proposals: see dashboard/API_CONTRACT.md.
import { loadEvents, parseEvent, parseEvents, type RunEvent } from './events'
import {
  APPROVALS,
  MUTATIONS,
  SAMPLE_RUNS,
  syntheticBenchmark,
  type Approval,
  type BenchRow,
  type Mutation,
} from './fixtures'
import { decide, rollbackProgram } from './mockState'
import { loadVersions as loadVersionFiles, type Program } from './programs'

const env = import.meta.env
export const API_MODE: 'mock' | 'real' = env.VITE_API_MODE === 'real' ? 'real' : 'mock'
export const API_BASE = (env.VITE_API_BASE_URL ?? 'http://localhost:8000').replace(/\/$/, '')
// Empty string turns Sentry links off.
export const SENTRY_ORG_URL = (env.VITE_SENTRY_ORG_URL ?? 'https://la-hacksss.sentry.io').replace(/\/$/, '')
export const TESTBED_URL = (env.VITE_TESTBED_URL ?? 'http://localhost:8001').replace(/\/$/, '')

async function http<T>(method: string, path: string, body?: unknown): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    })
  } catch (e) {
    throw new Error(`API unreachable at ${API_BASE} (${(e as Error).message})`)
  }
  if (!res.ok) throw new Error(`${method} ${path} failed: ${res.status} ${await res.text().catch(() => '')}`.trim())
  return res.json() as Promise<T>
}

// ---- runs ----

export async function listRuns(): Promise<string[]> {
  if (API_MODE === 'mock') return SAMPLE_RUNS
  return (await http<{ run_id: string }[]>('GET', '/runs')).map((r) => r.run_id)
}

export async function loadRun(runId: string): Promise<RunEvent[]> {
  if (API_MODE === 'mock') return loadEvents(runId)
  const res = await fetch(`${API_BASE}/runs/${runId}/events.jsonl`)
  if (!res.ok) throw new Error(`GET /runs/${runId}/events.jsonl failed: ${res.status}`)
  return parseEvents(await res.text())
}

export type StreamState = 'mock' | 'connecting' | 'live' | 'reconnecting' | 'closed'

// Real mode: server-sent events, one RunEvent per message. EventSource reconnects by
// itself; parseEvent drops malformed messages and the caller dedupes by eventKey.
export function subscribeRun(
  runId: string,
  onEvent: (e: RunEvent) => void,
  onState: (s: StreamState) => void,
): () => void {
  if (API_MODE === 'mock') {
    onState('mock')
    return () => {}
  }
  onState('connecting')
  const source = new EventSource(`${API_BASE}/runs/${runId}/events`)
  source.onopen = () => onState('live')
  source.onerror = () => onState(source.readyState === EventSource.CLOSED ? 'closed' : 'reconnecting')
  source.onmessage = (m) => {
    const e = parseEvent(m.data)
    if (e) onEvent(e)
  }
  return () => {
    source.close()
    onState('closed')
  }
}

// ---- programs ----

const mockRollbacks = new Map<string, Program[]>()

export async function loadVersions(name: string): Promise<Program[]> {
  if (API_MODE === 'mock') return [...(await loadVersionFiles(name)), ...(mockRollbacks.get(name) ?? [])]
  return http<Program[]>('GET', `/programs/${name}/versions`)
}

// Real mode: A's endpoint. Mock: browseen/program.py's append-only semantics (mockState.ts).
export async function rollback(name: string, to: number, versions: Program[]): Promise<Program> {
  if (API_MODE === 'real') return http<Program>('POST', `/programs/${name}/rollback?to=${to}`)
  const next = rollbackProgram(versions, to, new Date().toISOString())
  mockRollbacks.set(name, [...(mockRollbacks.get(name) ?? []), next])
  return next
}

// ---- mutations (C's testbed) ----

export async function listMutations(): Promise<Mutation[]> {
  if (API_MODE === 'mock') return MUTATIONS
  return http<Mutation[]>('GET', '/mutations')
}

export async function startMutatedRun(program: string, mutations: string[], seed: number): Promise<{ run_id: string } | null> {
  if (API_MODE === 'mock') return null // nothing to run without A's runtime and C's testbed
  return http<{ run_id: string }>('POST', `/programs/${program}/run`, { mutations, seed })
}

export function testbedUrl(mutations: string[], seed: number): string {
  return `${TESTBED_URL}/?mut=${mutations.join(',') || 'M00'}&seed=${seed}`
}

// ---- approvals ----

let mockApprovals = structuredClone(APPROVALS)

export async function listApprovals(): Promise<Approval[]> {
  if (API_MODE === 'mock') return mockApprovals
  return http<Approval[]>('GET', '/approvals')
}

// Approving authorizes the run to continue. It is not proof the write happened:
// that needs the backend's receipt check.
export async function decideApproval(id: string, decision: 'approve' | 'reject'): Promise<Approval> {
  if (API_MODE === 'real') return http<Approval>('POST', `/approvals/${id}/${decision}`)
  mockApprovals = decide(mockApprovals, id, decision)
  return mockApprovals.find((a) => a.id === id)!
}

// ---- benchmark (C) ----

export async function loadBenchmark(): Promise<{ rows: BenchRow[]; synthetic: boolean }> {
  if (API_MODE === 'mock') return { rows: syntheticBenchmark(), synthetic: true }
  return { rows: await http<BenchRow[]>('GET', '/benchmarks'), synthetic: false }
}

export function parseBenchmarkFile(text: string): BenchRow[] {
  const trimmed = text.trim()
  if (trimmed.startsWith('[')) return JSON.parse(trimmed) as BenchRow[]
  return trimmed.split('\n').filter((l) => l.trim()).map((l) => JSON.parse(l) as BenchRow)
}

export function sentryTraceUrl(traceId: string | undefined): string | null {
  if (!SENTRY_ORG_URL || !traceId) return null
  return `${SENTRY_ORG_URL}/explore/traces/trace/${traceId}`
}
