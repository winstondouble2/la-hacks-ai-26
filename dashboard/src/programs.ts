// Program format, mirrored from browseen/program.py (owner: B; JSON Schema in
// programs/program.schema.json). One YAML file per version: programs/<name>/v<N>.yaml.
import { parse } from 'yaml'

export interface Param {
  type: 'string' | 'integer' | 'number' | 'boolean'
  example?: string | number | boolean
  description?: string
}

// Exactly one of testid, role, label, placeholder, text, css, xpath is set.
export interface Locator {
  testid?: string
  role?: string
  name?: string
  exact?: boolean
  label?: string
  placeholder?: string
  text?: string
  css?: string
  xpath?: string
}

// Exactly one kind is set.
export interface Check {
  url_matches?: string
  text_visible?: string
  exists?: Locator
  absent?: Locator
  target_unique?: true
  target_enabled?: true
  target_value?: string
}

export interface Step {
  id: string
  intent: string
  action: { type: string; value?: string; url?: string; key?: string; into?: string }
  target?: { locators: Locator[]; fingerprint?: Record<string, unknown> }
  when?: Check
  pre?: Check[]
  post?: Check[]
  timeout_ms?: number
}

export interface Change {
  version: number
  source: 'recorded' | 'compiled' | 'healed' | 'manual'
  step?: string
  tier?: 1 | 2 | 3
  reason?: string
  at?: string
}

export interface Program {
  program: string
  version: number
  task: string
  start_url: string
  params?: Record<string, Param>
  steps: Step[]
  success?: Check[]
  history?: Change[]
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

const LOCATOR_KINDS = ['testid', 'role', 'label', 'placeholder', 'text', 'css', 'xpath'] as const

// Same short form as Locator.describe() in program.py, e.g. role=button[name="Add to cart"].
export function describeLocator(loc: Locator): string {
  const kind = LOCATOR_KINDS.find((k) => loc[k] !== undefined) ?? 'css'
  if (kind === 'role') return loc.name !== undefined ? `role=${loc.role}[name="${loc.name}"]` : `role=${loc.role}`
  return `${kind}=${loc[kind]}`
}

// {url_matches: "^/shop"} → `url_matches ^/shop`; {target_unique: true} → `target_unique`;
// {exists: {role: button, name: "Accept all"}} → `exists role=button[name="Accept all"]`.
export function describeCheck(check: Check): string {
  return Object.entries(check)
    .map(([k, v]) => {
      if (v === true) return k
      if (v && typeof v === 'object') return `${k} ${describeLocator(v as Locator)}`
      return `${k} ${v}`
    })
    .join(', ')
}
