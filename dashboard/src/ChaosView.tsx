import { useEffect, useState } from 'react'
import { API_MODE, listMutations, startMutatedRun, testbedUrl } from './api'
import type { Mutation } from './fixtures'

const LEVEL_STYLE: Record<Mutation['level'], string> = {
  L0: 'border border-rule text-muted',
  L1: 'bg-[#f1f1f2] text-ink',
  L2: 'bg-heal-wash text-heal-ink',
  L3: 'bg-ink text-chart',
  L4: 'bg-fail text-chart',
}

export default function ChaosView({ program, onRunStarted }: { program: string; onRunStarted: (runId: string) => void }) {
  const [mutations, setMutations] = useState<Mutation[]>([])
  const [active, setActive] = useState<Set<string>>(new Set())
  const [seed, setSeed] = useState(1)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  useEffect(() => {
    listMutations().then(setMutations, (e: Error) => setError(e.message))
  }, [])

  function toggle(id: string) {
    const next = new Set(active)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    setActive(next)
    setNotice(null)
  }

  function surprise() {
    const pool = mutations.filter((m) => m.level !== 'L0' && !active.has(m.id))
    if (!pool.length) return
    const pick = pool[Math.floor(Math.random() * pool.length)]
    setActive(new Set([pick.id]))
    setNotice(`Surprise: ${pick.id} ${pick.name}`)
  }

  async function run() {
    const ids = [...active].sort()
    setError(null)
    try {
      const started = await startMutatedRun(program, ids, seed)
      if (started) onRunStarted(started.run_id)
      else setNotice(`Mock mode: no run started. With A's runtime and C's testbed this runs ${program} against ${testbedUrl(ids, seed)}`)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-3">
        <button onClick={run} className="rounded-full bg-ink px-4 py-2 text-sm font-semibold text-chart hover:brightness-125">
          Run {program} with {active.size || 'no'} change{active.size === 1 ? '' : 's'}
        </button>
        <button onClick={surprise} className="rounded-full border-[1.5px] border-ink px-4 py-2 text-sm font-medium hover:bg-[#f1f1f2]">
          Surprise me
        </button>
        <button onClick={() => { setActive(new Set()); setNotice(null) }} className="rounded-full px-3 py-2 text-sm text-muted hover:text-ink">
          Reset
        </button>
        <label className="ml-auto flex items-center gap-2 font-mono text-sm">
          seed
          <input
            type="number"
            min={1}
            value={seed}
            onChange={(e) => setSeed(Math.max(1, Number(e.target.value) || 1))}
            className="w-16 rounded-md border border-rule px-2 py-1"
          />
        </label>
      </div>
      {notice && <p className="rounded-lg bg-heal-wash px-3 py-2 text-sm text-heal-ink">{notice}</p>}
      {error && <p className="text-sm text-fail">{error}</p>}
      {API_MODE === 'mock' && (
        <p className="text-xs text-muted">Catalog from docs/benchmark.md (C's proposal). It is replaced by GET /mutations in real mode.</p>
      )}
      <ul className="grid gap-2 sm:grid-cols-2">
        {mutations.map((m) => {
          const on = active.has(m.id)
          return (
            <li key={m.id}>
              <button
                onClick={() => toggle(m.id)}
                aria-pressed={on}
                className={`flex w-full items-start gap-3 rounded-xl border-[1.5px] px-3 py-2.5 text-left transition-colors ${
                  on ? 'border-ink bg-[#f6f6f7]' : 'border-rule hover:border-muted'
                }`}
              >
                <span className={`mt-0.5 size-4 shrink-0 rounded-full border-[1.5px] ${on ? 'border-ink bg-ink' : 'border-muted'}`} />
                <span className="flex min-w-0 flex-col gap-0.5">
                  <span className="flex items-center gap-2">
                    <span className="font-mono text-sm font-bold">{m.id}</span>
                    <span className="text-sm font-medium">{m.name}</span>
                    <span className={`rounded-full px-1.5 py-px font-mono text-[10px] font-bold ${LEVEL_STYLE[m.level]}`}>{m.level}</span>
                  </span>
                  <span className="text-sm text-muted">{m.change}</span>
                  <span className="font-mono text-xs text-muted">expected: {m.expected}</span>
                </span>
              </button>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
