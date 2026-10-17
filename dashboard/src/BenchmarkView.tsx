import { useEffect, useState } from 'react'
import { loadBenchmark, parseBenchmarkFile } from './api'
import { systemStats } from './benchmark'
import { SYSTEMS, type BenchRow } from './fixtures'

export default function BenchmarkView() {
  const [rows, setRows] = useState<BenchRow[]>([])
  const [source, setSource] = useState<'synthetic' | 'api' | string>('synthetic')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    loadBenchmark().then(
      (b) => {
        setRows(b.rows)
        setSource(b.synthetic ? 'synthetic' : 'api')
      },
      (e: Error) => setError(e.message),
    )
  }, [])

  async function importFile(file: File) {
    try {
      setRows(parseBenchmarkFile(await file.text()))
      setSource(file.name)
      setError(null)
    } catch (e) {
      setError(`Couldn't read ${file.name}: ${(e as Error).message}`)
    }
  }

  const stats = systemStats(rows, SYSTEMS)
  const muts = [...new Set(rows.map((r) => r.mutation))].sort()
  const heals = [1, 2, 3].map((t) => ({
    tier: t,
    count: rows.filter((r) => r.system === 'browseen').flatMap((r) => r.heals).filter((h) => h.tier === t).length,
  }))

  return (
    <div className="flex flex-col gap-7">
      <div className="flex flex-wrap items-center gap-3">
        {source === 'synthetic' ? (
          <span className="rounded-full bg-fail px-3 py-1 text-sm font-semibold text-chart">Synthetic: shaped by benchmark.md's expectations, not measured</span>
        ) : (
          <span className="rounded-full bg-pass px-3 py-1 text-sm font-semibold text-chart">Results: {source}</span>
        )}
        <label className="cursor-pointer rounded-full border-[1.5px] border-ink px-3 py-1 text-sm font-medium hover:bg-[#f1f1f2]">
          Import results (.jsonl / .json)
          <input type="file" accept=".jsonl,.json" className="hidden" onChange={(e) => e.target.files?.[0] && importFile(e.target.files[0])} />
        </label>
        <span className="font-mono text-xs text-muted">{rows.length} runs</span>
      </div>
      {error && <p className="text-sm text-fail">{error}</p>}

      <div className="grid gap-7 xl:grid-cols-2">
        <BarChart
          title="Verified success"
          subtitle="Runs where /__verify passed and the system reported success"
          data={stats.map((s) => ({ label: s.system, value: s.n ? s.verified / s.n : 0, text: `${s.verified}/${s.n}` }))}
          max={1}
        />
        <BarChart
          title="False passes (silent failures)"
          subtitle="Reported success, but the testbed says otherwise. Lower is better."
          data={stats.map((s) => ({ label: s.system, value: s.falsePass, text: `${s.falsePass}/${s.n}` }))}
        />
        <BarChart
          title="Median wall time"
          subtitle="Seconds per run, start to verdict"
          data={stats.map((s) => ({ label: s.system, value: s.medianWall, text: `${s.medianWall.toFixed(1)} s` }))}
        />
        <BarChart
          title="LLM cost per run"
          subtitle="Mean model spend; browser and infra time not included"
          data={stats.map((s) => ({ label: s.system, value: s.meanUsd, text: `$${s.meanUsd.toFixed(3)}` }))}
        />
      </div>

      <Heatmap rows={rows} mutations={muts} systems={stats.map((s) => s.system)} />

      <BarChart
        title="Browseen heals by tier"
        subtitle="Tier 1 local (no LLM), tier 2 one LLM patch, tier 3 agent takeover"
        data={heals.map((h) => ({ label: `tier ${h.tier}`, value: h.count, text: String(h.count) }))}
        highlight="none"
      />

      <details className="text-sm">
        <summary className="cursor-pointer font-medium">Table view</summary>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[720px] text-left font-mono text-[13px] tabular-nums">
            <thead className="text-xs uppercase text-muted">
              <tr>{['System', 'Runs', 'Verified', 'False pass', 'Correct fail (L4)', 'False alarms (M00)', 'Median s', 'Mean tokens', 'Mean $'].map((h) => <th key={h} className="py-2 pr-3 font-medium">{h}</th>)}</tr>
            </thead>
            <tbody>
              {stats.map((s) => (
                <tr key={s.system} className="border-t border-rule">
                  <td className="py-2 pr-3 font-semibold">{s.system}</td>
                  <td className="pr-3">{s.n}</td>
                  <td className="pr-3">{s.verified}</td>
                  <td className="pr-3">{s.falsePass}</td>
                  <td className="pr-3">{s.l4 ? `${s.correctFail}/${s.l4}` : '—'}</td>
                  <td className="pr-3">{s.falseAlarms}</td>
                  <td className="pr-3">{s.medianWall.toFixed(1)}</td>
                  <td className="pr-3">{Math.round(s.meanTokens).toLocaleString()}</td>
                  <td className="pr-3">{s.meanUsd.toFixed(3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-2 text-xs text-muted">
            Escalations and receipt failures aren't in the result row format yet (docs/benchmark.md §6), so they aren't shown.
          </p>
        </div>
      </details>
    </div>
  )
}

// One measure per chart, systems on the axis, Browseen highlighted. Value at each bar tip.
function BarChart({
  title,
  subtitle,
  data,
  max,
  highlight = 'browseen',
}: {
  title: string
  subtitle: string
  data: { label: string; value: number; text: string }[]
  max?: number
  highlight?: string
}) {
  const top = max ?? Math.max(...data.map((d) => d.value), 0)
  return (
    <figure className="flex flex-col gap-3">
      <figcaption className="flex flex-col">
        <span className="font-medium">{title}</span>
        <span className="text-xs text-muted">{subtitle}</span>
      </figcaption>
      <div className="flex flex-col gap-1.5 border-l border-rule">
        {data.map((d) => (
          <div key={d.label} className="flex items-center gap-2" title={`${d.label}: ${d.text}`}>
            <div className="relative flex h-6 flex-1 items-center">
              <div
                className={`h-[18px] rounded-r-[4px] ${d.label === highlight ? 'bg-heal' : 'bg-ink/75'}`}
                style={{ width: top > 0 ? `${Math.max((d.value / top) * 85, d.value > 0 ? 0.6 : 0)}%` : '0%' }}
              />
              <span className="ml-2 shrink-0 font-mono text-xs tabular-nums">{d.text}</span>
            </div>
            <span className={`w-24 shrink-0 order-first pl-0 text-right font-mono text-xs ${d.label === highlight ? 'font-bold' : 'text-muted'}`}>
              {d.label}
            </span>
          </div>
        ))}
      </div>
    </figure>
  )
}

// False passes per mutation and system: a single-hue ramp (white → ink) by count.
function Heatmap({ rows, mutations, systems }: { rows: BenchRow[]; mutations: string[]; systems: string[] }) {
  const count = (m: string, s: string) => rows.filter((r) => r.mutation === m && r.system === s && r.false_pass).length
  const total = (m: string, s: string) => rows.filter((r) => r.mutation === m && r.system === s).length
  const peak = Math.max(1, ...mutations.flatMap((m) => systems.map((s) => count(m, s))))
  return (
    <figure className="flex flex-col gap-3">
      <figcaption className="flex flex-col">
        <span className="font-medium">Silent failures by page change</span>
        <span className="text-xs text-muted">False passes per mutation; darker is worse. Counts out of trials per cell.</span>
      </figcaption>
      <div className="overflow-x-auto">
        <table className="border-separate border-spacing-[2px] font-mono text-xs tabular-nums">
          <thead>
            <tr>
              <th />
              {mutations.map((m) => <th key={m} className="px-1 pb-1 font-medium text-muted">{m}</th>)}
            </tr>
          </thead>
          <tbody>
            {systems.map((s) => (
              <tr key={s}>
                <th className={`pr-2 text-right font-medium ${s === 'browseen' ? 'font-bold' : 'text-muted'}`}>{s}</th>
                {mutations.map((m) => {
                  const c = count(m, s)
                  const n = total(m, s)
                  const shade = c / peak
                  return (
                    <td
                      key={m}
                      title={`${s} on ${m}: ${c} false pass${c === 1 ? '' : 'es'} of ${n}`}
                      className="h-8 w-11 rounded-[4px] text-center"
                      style={{ background: n ? `color-mix(in oklab, var(--color-ink) ${Math.round(shade * 85)}%, #f4f4f5)` : 'transparent', color: shade > 0.5 ? 'white' : 'var(--color-ink)' }}
                    >
                      {n ? `${c}/${n}` : ''}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </figure>
  )
}
