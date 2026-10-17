// Dashboard logic tests. Run: npm test (Node's built-in runner; Node >= 22.6 runs TypeScript).
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import { systemStats } from '../src/benchmark.ts'
import { dedupeEvents, parseEvent, parseEvents, type RunEvent } from '../src/events.ts'
import { APPROVALS, MUTATIONS, SYSTEMS, syntheticBenchmark } from '../src/fixtures.ts'
import { decide, rollbackProgram } from '../src/mockState.ts'
import type { Program } from '../src/programs.ts'
import { compareRuns, summarize, totalsAt } from '../src/replay.ts'

const run = (name: string): RunEvent[] => parseEvents(readFileSync(new URL(`../../runs/${name}/events.jsonl`, import.meta.url), 'utf8'))

test('totals count up with the replay clock and finish with the run', () => {
  const ev = run('sample')
  const early = totalsAt(ev, 500)
  assert.equal(early.llmCalls, 0)
  assert.equal(early.finished, false)
  const end = totalsAt(ev, Number.POSITIVE_INFINITY)
  assert.equal(end.finished, true)
  assert.equal(end.llmCalls, 1) // run_finished repeats the totals and must not double count
  assert.equal(end.seconds, 2)
})

test('comparison: savings, and null instead of dividing by zero', () => {
  const agent = totalsAt(run('sample-agent'), Infinity)
  const replay = totalsAt(run('sample'), Infinity)
  const c = compareRuns(agent, replay)
  assert.ok(c.speedup! > 18 && c.speedup! < 19)
  assert.equal(c.llmCallsAvoided, 7)
  assert.ok(c.tokenReduction! > 0.8)

  const zero = { seconds: 0, tokens: 0, usd: 0, llmCalls: 0, finished: true }
  const z = compareRuns(zero, zero)
  assert.equal(z.speedup, null)
  assert.equal(z.tokenReduction, null)
  assert.equal(z.llmUsdSaved, 0) // zero LLM spend, not "free"
  assert.equal(compareRuns(null, replay).secondsSaved, null) // missing side
})

test('summaries: heal tiers, guard failures and a stopped write', () => {
  const t1 = summarize(run('sample-heal1'))!
  assert.deepEqual(t1.heals, { 1: 1, 2: 0, 3: 0 })
  assert.equal(t1.llmCalls, 0)
  const t3 = summarize(run('sample-heal3'))!
  assert.equal(t3.heals[3], 1)
  assert.equal(t3.version, 2)
  const blocked = summarize(run('sample-blocked'))!
  assert.equal(blocked.status, 'stopped')
  assert.equal(blocked.reportedSuccess, false)
  assert.equal(blocked.guardFailures, 1)
})

test('events: malformed lines dropped, unknown types kept, duplicates removed', () => {
  assert.equal(parseEvent('not json'), null)
  assert.equal(parseEvent('{"type": "healed"}'), null) // no timestamp
  const unknown = parseEvent('{"ts": "2026-10-17T21:00:00Z", "type": "metrics_updated", "run_id": "r"}')
  assert.equal(unknown?.type, 'metrics_updated')
  assert.equal(unknown?.llm_calls, 0) // missing numbers default to 0
  const e = parseEvent('{"ts": "2026-10-17T21:00:00Z", "type": "check_passed", "run_id": "r", "step": "s1"}')!
  assert.equal(dedupeEvents([e, { ...e }, { ...e, step: 's2' }]).length, 2)
})

test('rollback appends a copy of the old version and keeps history', () => {
  const v1 = { program: 'p', version: 1, task: 't', start_url: '/', steps: [{ id: 's1', intent: 'a', action: { type: 'click' } }], history: [] } as Program
  const v2 = { ...v1, version: 2, steps: [{ id: 's1', intent: 'b', action: { type: 'click' } }], history: [{ version: 2, source: 'healed', step: 's1', tier: 2 }] } as Program
  const v3 = rollbackProgram([v1, v2], 1, '2026-10-17T22:00:00Z')
  assert.equal(v3.version, 3)
  assert.equal(v3.steps[0].intent, 'a')
  assert.equal(v3.history!.length, 2)
  assert.equal(v3.history![1].reason?.startsWith('rollback to v1'), true)
  assert.throws(() => rollbackProgram([v1, v2], 2, 'x'), /already the latest/)
  assert.equal(v1.version, 1) // the source version is not mutated
})

test('approvals: a decision changes only that pending request', () => {
  const next = decide(APPROVALS, 'ap_001', 'approve')
  assert.equal(next[0].status, 'approved')
  assert.equal(APPROVALS[0].status, 'pending') // fixture untouched
  assert.equal(decide(next, 'ap_001', 'reject')[0].status, 'approved') // already decided
  assert.throws(() => decide(APPROVALS, 'nope', 'approve'))
})

test('mutation catalog matches docs/benchmark.md ids', () => {
  assert.deepEqual(MUTATIONS.map((m) => m.id), Array.from({ length: 17 }, (_, i) => `M${String(i).padStart(2, '0')}`))
})

test('benchmark stats from rows', () => {
  const stats = systemStats(syntheticBenchmark(), SYSTEMS)
  assert.deepEqual(stats.map((s) => s.system), SYSTEMS)
  const browseen = stats.find((s) => s.system === 'browseen')!
  const replay = stats.find((s) => s.system === 'replay')!
  assert.equal(browseen.falsePass, 0)
  assert.ok(replay.falsePass > 0)
  assert.equal(browseen.falseAlarms, 0)
  assert.equal(systemStats([], SYSTEMS).length, 0)
})
