// Pure state changes behind mock mode (no I/O), so they can be tested on their own.
import type { Approval } from './fixtures'
import type { Program } from './programs'

// Same semantics as browseen/program.py rollback(): versions are append-only, so the
// new latest version is a copy of v`to` with a history entry. Nothing is deleted.
export function rollbackProgram(versions: Program[], to: number, at: string): Program {
  const current = versions[versions.length - 1]
  const target = versions.find((p) => p.version === to)
  if (!current || !target) throw new Error(`no v${to}`)
  if (to === current.version) throw new Error(`v${to} is already the latest version`)
  return {
    ...structuredClone(target),
    version: current.version + 1,
    history: [
      ...(current.history ?? []),
      { version: current.version + 1, source: 'manual', reason: `rollback to v${to} (mock, not saved)`, at },
    ],
  }
}

export function decide(approvals: Approval[], id: string, decision: 'approve' | 'reject'): Approval[] {
  if (!approvals.some((a) => a.id === id)) throw new Error(`no approval ${id}`)
  const status = decision === 'approve' ? 'approved' : 'rejected'
  return approvals.map((a) => (a.id === id && a.status === 'pending' ? { ...a, status } : a))
}
