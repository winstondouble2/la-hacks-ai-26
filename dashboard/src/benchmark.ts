// Benchmark metrics from result rows (docs/benchmark.md §6). Pure, so it's testable.
import type { BenchRow } from './fixtures'

export interface SystemStats {
  system: string
  n: number
  verified: number
  falsePass: number
  correctFail: number // on L4 mutations (M15, M16): reported failure instead of success
  l4: number
  medianWall: number
  meanUsd: number
  meanTokens: number
  falseAlarms: number // heals on the unchanged control (M00)
}

const L4 = new Set(['M15', 'M16'])

function median(xs: number[]) {
  if (!xs.length) return 0
  const s = [...xs].sort((a, b) => a - b)
  return s.length % 2 ? s[(s.length - 1) / 2] : (s[s.length / 2 - 1] + s[s.length / 2]) / 2
}

// order: preferred system order (fixtures SYSTEMS); systems not in it follow.
export function systemStats(rows: BenchRow[], order: string[]): SystemStats[] {
  const systems = [...new Set([...order.filter((s) => rows.some((r) => r.system === s)), ...rows.map((r) => r.system)])]
  return systems.map((system) => {
    const mine = rows.filter((r) => r.system === system)
    const l4 = mine.filter((r) => L4.has(r.mutation))
    return {
      system,
      n: mine.length,
      verified: mine.filter((r) => r.verified).length,
      falsePass: mine.filter((r) => r.false_pass).length,
      correctFail: l4.filter((r) => !r.reported_success).length,
      l4: l4.length,
      medianWall: median(mine.map((r) => r.wall_s)),
      meanUsd: mine.length ? mine.reduce((n, r) => n + r.usd, 0) / mine.length : 0,
      meanTokens: mine.length ? mine.reduce((n, r) => n + r.input_tokens + r.output_tokens, 0) / mine.length : 0,
      falseAlarms: mine.filter((r) => r.mutation === 'M00' && r.heals.length).length,
    }
  })
}
