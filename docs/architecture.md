# Architecture

How Browseen works, in more depth than [build_plan.md → Technical design](build_plan.md#technical-design). Where this page and the build plan disagree, **the build plan wins**. Anything marked *proposal* is a suggestion for the interface owner to accept or change at the freeze.

## Pipeline

```
 FIRST RUN (pays the model once)
 Browser Use agent ──► Recorder ──► step history (+ read / write / irreversible tags)
                                          │
                                          ▼
                                     Compiler (one LLM pass)
                                          │
                                          ▼
 EVERY LATER RUN                   program.yaml  vN
 params ─────────────────────────► Guarded executor (Playwright, no LLM on the happy path)
                                          │
              for each step: resolve → pre-checks → [judge] → act → post-checks → [receipt]
                                          │
          ┌───────────────────────────────┼─────────────────────────────────┐
     all checks pass                read step fails                write / irreversible fails
          │                               │                                 │
          ▼                               ▼                                 ▼
     next step                      Healer: one-step patch           STOP and ask a human
                                    dry run, same post-check         Slack + approvals queue
                                      │ pass         │ fail            │ approve        │ reject
                                      ▼              ▼                 ▼                ▼
                                 program v(N+1)   STOP and ask     apply / resume    run ends, safe
                                 + diff, rollback
```

## Risk levels

Every step carries one risk level. The risk level decides what happens when a check fails, and that is the core of "fail closed".

| Risk | Examples | On a failed check |
|---|---|---|
| `read` | Navigate, open a menu, search, read a table | Heal (one-step repair), then continue |
| `write` | Submit a form, save a record | **Stop and ask.** Never healed blind. |
| `irreversible` | Delete, final submit, pay | **Stop and ask.** The judge's default is also to stop. |

The recorder proposes a tag for each step from the action and its target (a submit button counts as `write`, a "Delete" label as `irreversible`), and the compiler pass confirms it. When in doubt, tag upward.

## Components

### Recorder (B)

- Runs one Browser Use agent on a portal and saves its step history with element data. Browser Use records the XPath, accessible name, attributes and a stable hash for each element it touched; it does not store CSS or role selectors, so the compiler derives those.
- Proposes a risk tag for each step.
- **Hour-one check:** pin the installed browser-use version and confirm it exposes step history with element data and a rerun method. Run one smoke test.
- **Model gotcha.** Browser Use's `ChatAnthropic` forces `tool_choice` unless thinking is set, and Claude Opus 5.5 / Sonnet 5.5 reject forced tool choice with HTTP 400. Construct it as `ChatAnthropic(model="claude-opus-5-5", thinking={"type": "adaptive"})` and don't set `temperature`/`top_p`/`seed`.

### Compiler (B)

One LLM pass turns the history into the YAML program. For each step, it produces:

- an action, and **fallback locators** in order: role + name, text, CSS, XPath;
- **parameters**: literals from the task become `$variables`, such as `$patient_id`;
- an **intent** sentence;
- **pre-checks** and **post-checks**;
- a **receipt rule** for write steps, and the **risk** level.

It also inserts the **two hand-authored branches**: a consent banner that may or may not appear, and an extra confirmation page. We present these as authored by us, not learned.

### Guarded executor (A)

This runs the program on Playwright, following the guard order below for every step, and emits the event stream. It makes no LLM calls on the happy path.

### Judge (A)

A cheap, fast model that answers one question: *does this element still mean the same as the step's intent?* It is called only:

- on write and irreversible steps, and
- when a locator still matches but the element's accessible name or structural fingerprint changed.

It returns a structured verdict: `same | different | unsure`. On write and irreversible steps, anything but `same` stops the run.

### Healer (A)

**Contract**, from the build plan:

- **Input:** the step's intent, the failing check, the previous locators, and a trimmed accessibility snapshot of the current page.
- **Output:** one patched step.

**Procedure:**

1. Run the patch as a dry run. It must pass **the same post-check** that was recorded for the step.
2. If it passes, the program version goes up, the diff is stored, and the step gets its gold seam in the UI. If it fails, the run stops and asks.
3. Rollback restores the previous version file.

Write and irreversible steps never reach the healer. When a page change can't be repaired at all, such as a judge's free-form edit, the system falls back to the full Browser Use agent or escalates. In the demo, we present this as designed behavior.

## Guard order for every step

1. **Resolve** the target with the locator list, in order. No match fails the step.
2. **Deterministic pre-checks:** the URL pattern, the role + accessible name, the structural fingerprint.
3. **Judge.** If the locator matched but the name or fingerprint changed, ask the judge with the step's intent.
   - On a read step, a `same` verdict continues.
   - On a write or irreversible step, the default is to stop and ask.
4. **Act.**
5. **Post-checks**, then the **receipt check** for write steps.
6. **On failure:** read steps go to the healer; write and irreversible steps stop and ask.

## Program format (owner: B, frozen by 14:30)

There is one YAML file per flow. Every accepted repair bumps the version, and every version is kept, so a rollback is a file swap. This example is from the build plan:

```yaml
program: eligibility-check
version: 3
steps:
  - id: s5
    intent: "Submit the eligibility request for the selected patient"
    risk: write                 # read | write | irreversible
    action: {type: click, target: {role: button, name: "Check eligibility"}}
    locators: [role_name, text, css, xpath]     # tried in order
    pre:
      - url_matches: "/portal-a/eligibility"
      - element: {role: button, name: "Check eligibility", enabled: true}
      - fingerprint: "form#elig > fieldset(3) > button[type=submit]"
    post:
      - text_visible: "Request received"
      - receipt: {source: audit_log, match: {action: eligibility_submit, patient: $patient_id}}
    on_fail: {read: heal, write: stop_and_ask, irreversible: stop_and_ask}
```

The schema still needs these decisions, which are B's call:

- the top-level `params:` block with types;
- how a branch is written (*proposal*: `kind: optional` with a `when:` check for the consent banner);
- where versions live (*proposal*: `programs/eligibility-check/v3.yaml`).

## Interfaces to freeze early

| Interface | Owner | Freeze |
|---|---|---|
| Audit-log schema | C | 14:00 |
| Program YAML schema | B | 14:30 |
| Event stream (JSON lines) | A emits, D consumes | with the executor |
| Approval API | A + D | before Wow v1 (23:00) |

### Audit log (*proposal* for C)

Each portal appends a row for every submit and shows the `request_id` on screen. The harness and the receipt check read this table directly; the agent's own success report never scores a run.

```sql
CREATE TABLE audit (
  id          INTEGER PRIMARY KEY,
  portal      TEXT NOT NULL,         -- a | b | c
  action      TEXT NOT NULL,         -- eligibility_submit | save_draft | delete | ...
  patient_id  TEXT,
  request_id  TEXT NOT NULL,
  payload     TEXT,                  -- JSON of submitted fields
  mutation    INTEGER,               -- active mutation number, 0 = none
  run_id      TEXT,                  -- from a header the runner sends, so rows map to runs
  created_at  TEXT NOT NULL
);
```

### Event stream (*proposal* for A)

The event stream is one JSON object per line. The executor writes it to `runs/<run_id>/events.jsonl` and serves it to the dashboard over server-sent events.

```json
{"ts": "2026-10-17T21:04:11.2Z", "run_id": "r_042", "program": "eligibility-check", "version": 3,
 "type": "check_failed", "step": "s5", "risk": "write", "check": "pre.element",
 "detail": "name changed: 'Check eligibility' -> 'Verify coverage'",
 "tokens": 0, "usd": 0.0, "trace_id": "…"}
```

`type` is one of:

- `run_started`, `step_started`, `check_passed`, `check_failed`, `healed`, `stopped`, `approved`, `rejected`, `run_finished`.
- `healed` carries the diff.
- `stopped` carries the intent, a screenshot path and the proposed diff, which is everything Slack and the approvals queue need.

### Approval API (*proposal* for A + D)

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/stops` | Open stops, with intent, screenshot, proposed diff and trace link |
| `POST` | `/stops/{id}/approve` | Apply the proposed patch (a new program version) and resume the run |
| `POST` | `/stops/{id}/reject` | End the run safely; keep the program version |
| `GET` | `/runs/{id}/events` | The SSE event stream |

## CLI (B)

Run as `python -m browseen <command>` (the entry point is `browseen/__main__.py`).

| Command | Does |
|---|---|
| `record <flow>` | Run the Browser Use agent once and save the step history |
| `compile <history>` | History → `program.yaml` v1 |
| `run <program> --param k=v` | Guarded replay: heal reads, stop on writes |
| `doctor <program>` | Dry run: resolve every step and run the pre-checks without acting on writes, then report drift |
| `heal <program> --step s5` | Run the healer on one step by hand |
| `rollback <program> [--to vN]` | Restore an earlier version file |

## Tech stack

| Layer | Choice | Notes |
|---|---|---|
| Runtime | Python 3.12, Playwright, browser-use | browser-use 0.13.11 is the latest on PyPI (needs Python ≥ 3.11) and drives Chrome over CDP, not Playwright. Playwright 1.64 runs the compiled programs: `get_by_role`, `aria_snapshot()`, `to_match_aria_snapshot()` for guards. |
| Packaging | `requirements.txt` + a venv | `python -m venv .venv && pip install -r requirements.txt`. Pin versions in `requirements.txt` once they're confirmed in hour one. (The build plan mentions uv; we're staying with `requirements.txt`.) |
| Models | One thin client around the Anthropic SDK | *Proposal*: `claude-opus-5-5` to compile and heal, `claude-haiku-5-5` as the judge. Log tokens and $ for every call; these feed the cost counters. |
| Portals | FastAPI + Jinja templates + SQLite | Three layouts from one generator, mutations applied in the template layer, audit table. |
| Dashboard | React + Vite + Tailwind, SSE | Program view with gold seams, diff view, live counters, approvals queue. |
| Notifications | Slack incoming webhook | Posts the step intent, screenshot, diff and trace link. |
| Observability | Sentry Python SDK on the runner, browser SDK on the portals | See below. |
| Hosting | Local for the demo; Vultr only if time allows | The demo must not depend on it. |

**Repo layout.** This is the build plan's layout with the core code inside the existing `browseen/` package:

```
browseen/                 # Python package: python -m browseen <command>
  __main__.py             # CLI entry point (exists)
  observability.py        # Sentry init (exists)
  tracing.py              # run / step / LLM span helpers (exists)
  recorder/  compiler/    # B
  executor/  guards/  healer/  api.py   # A (api.py: SSE + approval API, shared with D)
portals/                  # C: a/ b/ c/ mutations.py audit.py
bench/                    # C: mutations.md config.yaml systems.py run.py report.py
dashboard/                # D: React + Vite + Tailwind
programs/                 # compiled YAML programs, one folder per flow, every version kept
requirements.txt
README.md
```

## Observability (Sentry)

The Sentry challenge requires two or more products beyond error monitoring. We aim for four:

- **Tracing.** One transaction per run and one span per program step. `browseen/tracing.py` already has `run_span`, `step_span`, `mark_healed` and `llm_span`, with span data `run.mode`, `step.index`, `step.action`, `step.target`, `step.healed`. Per the build plan, add `step.id`, `step.risk`, `guard.result`, `step.stopped` and `program.version`, so a judge can open the trace and see which step cracked and what repaired it.
- **AI agent monitoring.** The Python SDK auto-instruments the Anthropic SDK, so the compiler, judge and healer calls show up as `gen_ai` spans with tokens and cost. Custom ops such as `agent.llm` don't appear in Sentry's Agents view; for anything not auto-instrumented, use `gen_ai.*` ops. Wrap the healer as a `gen_ai.invoke_agent` span so the repair shows as a child agent span.
- **Session Replay.** Add the Sentry browser SDK to the portals we build, so the agent's clicks are replayable. Replay masks text and inputs by default; on our synthetic portals, turn that off (`maskAllText: false`, `maskAllInputs: false`). Replay can't record third-party sites, which is one more reason the demo stays on our portals.
- **Logs.** One `sentry_sdk.logger` line per guard decision. On SDK 2.x, `enable_logs=True` is required; `browseen/observability.py` already sets it.
- **Build log.** Sentry asks how observability shaped the build. Write down real moments as they happen, such as a trace that showed where time went.
