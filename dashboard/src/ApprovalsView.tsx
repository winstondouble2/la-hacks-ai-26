import { useEffect, useState } from 'react'
import { API_MODE, decideApproval, listApprovals, sentryTraceUrl } from './api'
import { REAL_DEMO_TRACES, type Approval } from './fixtures'

export default function ApprovalsView({ onChange }: { onChange: (approvals: Approval[]) => void }) {
  const [approvals, setApprovals] = useState<Approval[]>([])
  const [open, setOpen] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listApprovals().then(
      (a) => {
        setApprovals(a)
        setOpen(a.find((x) => x.status === 'pending')?.id ?? null)
      },
      (e: Error) => setError(e.message),
    )
  }, [])

  async function decide(id: string, decision: 'approve' | 'reject') {
    setBusy(id)
    setError(null)
    try {
      const updated = await decideApproval(id, decision)
      const next = approvals.map((a) => (a.id === id ? updated : a))
      setApprovals(next)
      onChange(next)
    } catch (e) {
      setError((e as Error).message) // state stays as it was: nothing is shown as decided
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-muted">
        Steps the runtime refused to repair automatically, usually writes whose meaning changed.
        {API_MODE === 'mock' && ' The current architecture auto-heals without approvals; this queue is a mock of the build plan\'s human gate.'}
      </p>
      {error && <p className="text-sm text-fail">{error}</p>}
      {!approvals.length && !error && <p className="text-sm text-muted">No requests.</p>}
      <ol className="flex flex-col border-t-[1.5px] border-ink">
        {approvals.map((a) => {
          const trace = API_MODE === 'real' || REAL_DEMO_TRACES.has(a.trace_id ?? '') ? sentryTraceUrl(a.trace_id) : null
          return (
            <li key={a.id} className="flex flex-col gap-3 border-b border-rule py-4">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <span className="font-mono text-sm font-bold">{a.step}</span>
                <span className="text-[17px] font-medium">{a.intent}</span>
                <span className="rounded-full bg-ink px-2 py-0.5 font-mono text-[11px] uppercase text-chart">{a.risk}</span>
                {a.synthetic && <span className="rounded-full bg-fail px-2 py-0.5 font-mono text-[11px] uppercase text-chart">synthetic</span>}
                <span className="ml-auto font-mono text-xs text-muted">run {a.run_id}</span>
              </div>
              <p className="text-sm"><span className="font-mono text-fail">failed {a.failed_check}</span> · {a.reason}</p>
              {open === a.id && (
                <div className="flex flex-col gap-2 rounded-lg bg-[#f6f6f7] p-3 text-sm">
                  <span className="text-xs font-medium uppercase tracking-[0.1em] text-muted">Proposed patch (not applied)</span>
                  <pre className="overflow-x-auto font-mono text-[12.5px] leading-5">{a.patch ?? 'No patch proposed.'}</pre>
                  <span className="text-xs text-muted">
                    {a.screenshot_url ? <a className="underline" href={a.screenshot_url} target="_blank" rel="noreferrer">Screenshot</a> : 'No screenshot.'}
                    {' · '}
                    {trace ? <a className="underline" href={trace} target="_blank" rel="noreferrer">Sentry trace</a> : 'No trace link.'}
                  </span>
                </div>
              )}
              <div className="flex flex-wrap items-center gap-2">
                {a.status === 'pending' ? (
                  <>
                    <button disabled={busy === a.id} onClick={() => decide(a.id, 'approve')} className="rounded-full bg-pass px-4 py-1.5 text-sm font-semibold text-chart disabled:opacity-50">Approve</button>
                    <button disabled={busy === a.id} onClick={() => decide(a.id, 'reject')} className="rounded-full bg-fail px-4 py-1.5 text-sm font-semibold text-chart disabled:opacity-50">Reject</button>
                  </>
                ) : (
                  <span className={`text-sm font-medium ${a.status === 'approved' ? 'text-pass' : 'text-fail'}`}>
                    {a.status === 'approved'
                      ? 'Approved: the run may continue. The write is not confirmed until the backend\'s receipt check passes.'
                      : 'Rejected: the step stays blocked and the program is unchanged.'}
                  </span>
                )}
                <button onClick={() => setOpen(open === a.id ? null : a.id)} className="ml-auto text-sm text-muted underline">
                  {open === a.id ? 'Hide details' : 'View details'}
                </button>
              </div>
            </li>
          )
        })}
      </ol>
    </div>
  )
}
