// Program format: docs/architecture.md → "Program format" (owner: B).
// One YAML file per version at programs/<name>/v<N>.yaml.
import { parse } from 'yaml'

type Check = Record<string, unknown>

export interface Step {
  id: string
  intent: string
  when?: Check
  action: { type: string; value?: string; url?: string }
  target?: {
    locators: Record<string, string>[]
    fingerprint?: Record<string, string>
  }
  pre?: Check[]
  post?: Check[]
  risk?: 'read' | 'write' | 'irreversible'
}

export interface HistoryEntry {
  version: number
  step: string
  tier: number
  reason: string
}

export interface Program {
  program: string
  version: number
  params: Record<string, string>
  start_url: string
  steps: Step[]
  success: Check[]
  history: HistoryEntry[]
}

// No directory listing yet, so fetch v1, v2, … until one is missing.
export async function loadVersions(name: string): Promise<Program[]> {
  const versions: Program[] = []
  for (let v = 1; ; v++) {
    const res = await fetch(`/programs/${name}/v${v}.yaml`)
    if (!res.ok || !res.headers.get('content-type')?.includes('yaml')) break
    versions.push(parse(await res.text()) as Program)
  }
  if (!versions.length) throw new Error(`No versions found for program ${name}`)
  return versions
}

// A check like {url_matches: "^/shop"} reads as `url_matches ^/shop`, and
// {exists: {role: button, name: "Accept all"}} as `exists button "Accept all"`.
export function describeCheck(check: Check): string {
  return Object.entries(check)
    .map(([k, v]) =>
      v && typeof v === 'object' ? `${k} ${describeLocator(v as Record<string, string>)}` : `${k} ${v}`,
    )
    .join(', ')
}

export function describeLocator(loc: Record<string, string>): string {
  const [[kind, value]] = Object.entries(loc)
  const name = loc.name ? ` "${loc.name}"` : ''
  return kind === 'role' ? `${value}${name}` : `${kind}=${value}`
}
