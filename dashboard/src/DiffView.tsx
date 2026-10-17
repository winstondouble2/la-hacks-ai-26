import { useState } from 'react'
import { stringify } from 'yaml'
import type { Program, Step } from './programs'

// Hand-written and compiler-written files order keys differently and may omit
// defaults, so steps are put in one canonical shape before comparing:
// Step fields in program.py order, nested keys sorted, defaults filled in.
const STEP_ORDER = ['id', 'intent', 'action', 'target', 'when', 'pre', 'post', 'timeout_ms']

function sortDeep(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sortDeep)
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value)
        .filter(([, v]) => !(Array.isArray(v) && v.length === 0))
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([k, v]) => [k, sortDeep(v)]),
    )
  }
  return value
}

function canonical(step: Step): Record<string, unknown> {
  const filled: Record<string, unknown> = { timeout_ms: 5000, ...step }
  const out: Record<string, unknown> = {}
  for (const key of STEP_ORDER) {
    const v = sortDeep(filled[key])
    if (v !== undefined && !(Array.isArray(v) && v.length === 0)) out[key] = v
  }
  return out
}

// Steps are matched by id. A step is "changed" if its canonical YAML differs.
function stepYaml(step: Step | undefined): string[] {
  return step ? stringify(canonical(step), { lineWidth: 0 }).trimEnd().split('\n') : []
}

export default function DiffView({ versions }: { versions: Program[] }) {
  const [from, setFrom] = useState(Math.max(0, versions.length - 2))
  const [to, setTo] = useState(versions.length - 1)
  const a = versions[from]
  const b = versions[to]

  const ids = [...new Set([...a.steps.map((s) => s.id), ...b.steps.map((s) => s.id)])]
  const reasons = (b.history ?? []).filter((h) => h.version > a.version && h.version <= b.version)

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-3 font-mono text-sm">
        <VersionPicker versions={versions} value={from} onChange={setFrom} />
        <span className="text-muted">→</span>
        <VersionPicker versions={versions} value={to} onChange={setTo} />
        {reasons.map((h) => (
          <span key={h.version} className="rounded-full bg-heal-wash px-3 py-1 font-sans text-sm text-heal-ink">
            v{h.version}: {h.source === 'healed' ? `${h.step} healed at tier ${h.tier}` : h.source}
            {h.reason ? `, ${h.reason}` : ''}
          </span>
        ))}
      </div>
      <ol className="flex flex-col border-t-[1.5px] border-ink">
        {ids.map((id) => {
          const left = stepYaml(a.steps.find((s) => s.id === id))
          const right = stepYaml(b.steps.find((s) => s.id === id))
          const changed = left.join('\n') !== right.join('\n')
          const intent = (b.steps.find((s) => s.id === id) ?? a.steps.find((s) => s.id === id))?.intent
          if (!changed) {
            return (
              <li key={id} className="flex gap-4 border-b border-rule px-4 py-2.5 text-muted">
                <span className="w-10 shrink-0 font-mono text-sm">{id}</span>
                <span className="truncate text-sm">{intent}</span>
                <span className="ml-auto shrink-0 font-mono text-xs">unchanged</span>
              </li>
            )
          }
          return (
            <li key={id} className="flex flex-col gap-3 border-b border-l-4 border-rule border-l-heal bg-heal-wash py-4 pr-4 pl-3">
              <div className="flex gap-4">
                <span className="w-10 shrink-0 font-mono text-sm font-bold">{id}</span>
                <span className="font-medium">{intent}</span>
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                <YamlPane label={`v${a.version}`} lines={left} other={right} tone="old" />
                <YamlPane label={`v${b.version}`} lines={right} other={left} tone="new" />
              </div>
            </li>
          )
        })}
      </ol>
    </div>
  )
}

function VersionPicker({
  versions,
  value,
  onChange,
}: {
  versions: Program[]
  value: number
  onChange: (i: number) => void
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(Number(e.target.value))}
      className="rounded-full border-[1.5px] border-ink bg-chart px-3 py-1 font-semibold"
    >
      {versions.map((p, i) => (
        <option key={p.version} value={i}>
          v{p.version}
        </option>
      ))}
    </select>
  )
}

// Lines missing from the other side are highlighted: red in the old version, green in the new.
function YamlPane({ label, lines, other, tone }: { label: string; lines: string[]; other: string[]; tone: 'old' | 'new' }) {
  const otherSet = new Set(other)
  const mark = tone === 'old' ? 'bg-fail/12 text-fail' : 'bg-pass/12 text-pass'
  return (
    <div className="min-w-0 overflow-hidden rounded-lg border border-rule bg-chart">
      <div className="border-b border-rule px-3 py-1.5 font-mono text-xs font-semibold text-muted">{label}</div>
      <pre className="overflow-x-auto py-2 font-mono text-[12.5px] leading-5">
        {lines.map((line, i) => {
          const diff = !otherSet.has(line)
          return (
            <div key={i} className={`px-3 ${diff ? `${mark} font-semibold` : ''}`}>
              <span className="mr-2 inline-block w-3 select-none text-muted">{diff ? (tone === 'old' ? '−' : '+') : ''}</span>
              {line}
            </div>
          )
        })}
      </pre>
    </div>
  )
}
