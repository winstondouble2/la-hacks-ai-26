// Mock-mode data. Everything here is SYNTHETIC unless noted, and the UI labels it so.
// In real mode these are replaced by the API (dashboard/API_CONTRACT.md), not edited.

// Sample runs in runs/sample*/ (written by runs/sample/make_samples.py).
export const SAMPLE_RUNS = ['sample', 'sample-heal1', 'sample-heal3', 'sample-blocked', 'sample-agent']

// Trace ids in the sample runs that exist in Sentry (sent by `python -m browseen --demo`).
// Links to any other sample trace would 404, so they're not shown.
export const REAL_DEMO_TRACES = new Set(['7da7a54de6bb4c149e0e9804dad3d661'])

export interface Mutation {
  id: string
  level: 'L0' | 'L1' | 'L2' | 'L3' | 'L4'
  name: string
  change: string
  expected: string
}

// NOT synthetic: copied from C's catalog in docs/benchmark.md §4 (still a proposal).
export const MUTATIONS: Mutation[] = [
  { id: 'M00', level: 'L0', name: 'none', change: 'Unchanged page (control)', expected: 'pass, 0 LLM calls' },
  { id: 'M01', level: 'L1', name: 'Selector churn', change: 'ids and classes randomized, data-testid removed', expected: 'tier 1' },
  { id: 'M02', level: 'L1', name: 'Wrapper insertion', change: 'extra divs around the target', expected: 'tier 1' },
  { id: 'M03', level: 'L1', name: 'Sibling reorder', change: 'buttons or fields swap DOM order', expected: 'tier 1, post-check catches mistakes' },
  { id: 'M04', level: 'L2', name: 'Text rename', change: '"Add to cart" → "Add to bag"', expected: 'tier 1 fuzzy match or tier 2' },
  { id: 'M05', level: 'L2', name: 'Label rename', change: '"Full name" → "Your name"', expected: 'tier 1 or 2' },
  { id: 'M06', level: 'L2', name: 'Moved into a menu', change: 'the button is now inside a "⋯" dropdown', expected: 'tier 2 (inserts "open menu")' },
  { id: 'M07', level: 'L2', name: 'Field order shuffled', change: 'the form fields are reordered', expected: 'tier 1' },
  { id: 'M08', level: 'L3', name: 'Cookie banner', change: 'a banner covers the page on first load', expected: 'optional-step branch, or tier 2 adds one' },
  { id: 'M09', level: 'L3', name: 'Popup', change: 'a newsletter modal appears after step 2', expected: 'tier 2 (inserts "close popup")' },
  { id: 'M10', level: 'L3', name: 'New required field', change: 'checkout now needs a phone number', expected: 'tier 3, or fail loudly' },
  { id: 'M11', level: 'L3', name: 'Flow split', change: 'one form page becomes two', expected: 'tier 3' },
  { id: 'M12', level: 'L3', name: 'Pagination shift', change: 'the target item moves to page 2', expected: 'tier 2 or 3' },
  { id: 'M13', level: 'L3', name: 'Slow load', change: 'content renders after 2–4 s', expected: 'the guard waits; 0 LLM calls' },
  { id: 'M14', level: 'L3', name: 'A/B variant', change: 'a different layout with the same function', expected: 'tier 2, both variants kept as branches' },
  { id: 'M15', level: 'L4', name: 'Impossible', change: 'the product is out of stock', expected: 'must fail loudly (correct fail)' },
  { id: 'M16', level: 'L4', name: 'Wrong-target trap', change: 'a decoy button with the old label does something else', expected: 'the post-check catches it' },
]

export interface Approval {
  id: string
  run_id: string
  step: string
  intent: string
  risk: string
  failed_check: string
  reason: string
  screenshot_url?: string
  patch?: string
  trace_id?: string
  status: 'pending' | 'approved' | 'rejected'
  synthetic: boolean
}

// SYNTHETIC: matches runs/sample-blocked. Note the current architecture auto-heals and has
// no approval step (docs/architecture.md); this exists for the build plan's human gate.
export const APPROVALS: Approval[] = [
  {
    id: 'ap_001',
    run_id: 'r_045',
    step: 's7',
    intent: 'Place the order',
    risk: 'write',
    failed_check: 'pre role=button[name="Place order"]',
    reason: 'Accessible name changed: the button now reads "Cancel order". Write steps are never healed blind.',
    patch: '- role=button[name="Place order"]\n+ role=button[name="Cancel order"]   # proposed by tier 2, NOT applied',
    trace_id: 'c3d4e5f60718293a4b5c6d7e8f90a1b2',
    status: 'pending',
    synthetic: true,
  },
]

// One benchmark result row, as proposed in docs/benchmark.md §6.
export interface BenchRow {
  run_id: string
  task: string
  mutation: string
  seed: number
  system: string
  repeat: number
  reported_success: boolean
  verified: boolean
  false_pass: boolean
  wall_s: number
  llm_calls: number
  input_tokens: number
  output_tokens: number
  usd: number
  heals: { step: string; tier: number; latency_s?: number; usd?: number }[]
}

export const SYSTEMS = ['agent', 'replay', 'takeover', 'browseen-t1', 'browseen-t2', 'browseen']

// SYNTHETIC rows shaped by the "what we expect" columns of docs/benchmark.md, so every
// chart has something to draw. Deterministic (no randomness) and never a measurement.
export function syntheticBenchmark(): BenchRow[] {
  const muts = ['M00', 'M01', 'M04', 'M06', 'M09', 'M10', 'M15', 'M16']
  const rows: BenchRow[] = []
  let n = 0
  for (const system of SYSTEMS) {
    for (const mutation of muts) {
      for (let repeat = 1; repeat <= 3; repeat++) {
        const r = outcome(system, mutation, repeat)
        rows.push({
          run_id: `syn_${String(++n).padStart(3, '0')}`, task: 'T1', mutation, seed: repeat, system, repeat,
          ...r, input_tokens: Math.round(r.tokens * 0.95), output_tokens: Math.round(r.tokens * 0.05),
        })
      }
    }
  }
  return rows
}

function outcome(system: string, m: string, repeat: number) {
  const impossible = m === 'M15'
  const trap = m === 'M16'
  const hard = m === 'M10'
  const odd = repeat === 3
  const agent = { wall_s: 38 + repeat * 2, llm_calls: 8, tokens: 69000, heals: [] }
  const base = { wall_s: 2 + repeat * 0.1, llm_calls: 0, tokens: 0, heals: [] as BenchRow['heals'] }
  let ok = true
  let reported = true
  let r = base
  if (system === 'agent') {
    r = agent
    reported = !impossible || odd // the agent sometimes "succeeds" on an impossible task
    ok = !impossible && !(trap && odd)
  } else if (system === 'replay') {
    r = { ...base, llm_calls: 1, tokens: 1200 }
    reported = m === 'M00' || m === 'M01' || trap || impossible
    ok = m === 'M00' || m === 'M01'
  } else if (system === 'takeover') {
    const broke = !['M00', 'M01'].includes(m)
    r = broke ? { wall_s: 21, llm_calls: 5, tokens: 40000, heals: [] } : base
    reported = !impossible
    ok = !impossible && !trap
  } else {
    const maxTier = system === 'browseen-t1' ? 1 : system === 'browseen-t2' ? 2 : 3
    const need = m === 'M00' ? 0 : m === 'M01' ? 1 : hard ? 3 : impossible || trap ? 9 : 2
    if (need === 0) r = base
    else if (need <= maxTier) {
      const tok = need === 1 ? 0 : need === 2 ? 9500 : 24500
      r = { wall_s: base.wall_s + need * 1.4, llm_calls: need === 1 ? 0 : need - 1, tokens: tok,
            heals: [{ step: 's4', tier: need, latency_s: need * 1.3 }] }
    } else {
      reported = false // fails loudly instead of guessing
      r = { ...base, wall_s: base.wall_s + 1.5 }
    }
    ok = need <= maxTier
  }
  const verified = ok && reported
  return { ...r, reported_success: reported, verified, false_pass: reported && !ok,
           usd: Math.round((r.tokens * 0.95 * 4 + r.tokens * 0.05 * 20) / 10_000) / 100 }
}
