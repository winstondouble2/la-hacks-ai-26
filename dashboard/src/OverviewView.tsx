import type { Approval } from './fixtures'
import type { RunStatus, RunSummary } from './replay'

const STATUS_STYLE: Record<RunStatus, string> = {
  running: 'border border-ink text-ink',
  succeeded: 'bg-pass text-chart',
  failed: 'bg-fail text-chart',
  stopped: 'bg-ink text-chart',
}

export default function OverviewView({
  runs,
  approvals,
  currentRunId,
  onOpen,
}: {
  runs: RunSummary[]
  approvals: Approval[]
  currentRunId: string
  onOpen: (runId: string) => void
}) {
  const replays = runs.filter((r) => r.mode !== 'llm')
  const heals = runs.reduce((n, r) => n + r.heals[1] + r.heals[2] + r.heals[3], 0)
  const tiles: [string, string, string?][] = [
    ['Runs', String(runs.length), `${runs.filter((r) => r.status === 'running').length} active`],
    ['Reported success', `${runs.filter((r) => r.reportedSuccess).length}/${runs.length}`, 'not verified: needs /__verify'],
    ['Guard failures', String(runs.reduce((n, r) => n + r.guardFailures, 0))],
    ['Heals', String(heals), tierLine(runs)],
    ['Approvals pending', String(approvals.filter((a) => a.status === 'pending').length)],
    ['LLM spend', `$${runs.reduce((n, r) => n + r.usd, 0).toFixed(3)}`, `${replays.length} replays, ${runs.length - replays.length} agent runs`],
  ]
  return (
    <div className="flex flex-col gap-6">
      <dl className="grid grid-cols-2 gap-x-6 gap-y-5 border-t-[1.5px] border-ink pt-4 sm:grid-cols-3">
        {tiles.map(([label, value, note]) => (
          <div key={label} className="flex flex-col gap-0.5">
            <dt className="text-xs font-medium uppercase tracking-[0.12em] text-muted">{label}</dt>
            <dd className="font-mono text-[28px] font-bold leading-9 tabular-nums">{value}</dd>
            {note && <dd className="text-xs text-muted">{note}</dd>}
          </div>
        ))}
      </dl>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] border-t-[1.5px] border-ink text-left text-sm">
          <thead className="text-xs uppercase tracking-[0.1em] text-muted">
            <tr>
              {['Run', 'Mode', 'Program', 'Status', 'Time', 'LLM', 'Cost', 'Guard fails', 'Heals'].map((h) => (
                <th key={h} className="py-2.5 pr-3 font-medium">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="font-mono tabular-nums">
            {runs.map((r) => (
              <tr
                key={r.runId}
                onClick={() => onOpen(r.runId)}
                className={`cursor-pointer border-t border-rule hover:bg-[#f6f6f7] ${r.runId === currentRunId ? 'bg-heal-wash' : ''}`}
              >
                <td className="py-2.5 pr-3 font-semibold">{r.runId}</td>
                <td className="pr-3">{r.mode === 'llm' ? 'agent' : r.mode}</td>
                <td className="pr-3">{r.program} v{r.version}</td>
                <td className="pr-3">
                  <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold uppercase ${STATUS_STYLE[r.status]}`}>
                    {r.status}
                  </span>
                </td>
                <td className="pr-3">{r.seconds.toFixed(1)} s</td>
                <td className="pr-3">{r.llmCalls}</td>
                <td className="pr-3">${r.usd.toFixed(3)}</td>
                <td className={`pr-3 ${r.guardFailures ? 'text-fail' : ''}`}>{r.guardFailures}</td>
                <td className="pr-3">
                  {[1, 2, 3].filter((t) => r.heals[t as 1 | 2 | 3]).map((t) => `T${t}`).join(' ') ||
                    (r.healFailures ? <span className="text-fail">not healed</span> : '—')}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-muted">
        "Status" is what the system reported. Verified success comes from the testbed's server-side check
        (<code>/__verify</code>), which isn't in the event stream yet.
      </p>
    </div>
  )
}

function tierLine(runs: RunSummary[]) {
  const t = [1, 2, 3].map((k) => runs.reduce((n, r) => n + r.heals[k as 1 | 2 | 3], 0))
  return `tier 1: ${t[0]} · tier 2: ${t[1]} · tier 3: ${t[2]}`
}
