# Architecture

How Browseen works. The pitch is in [overview.md](overview.md); observability details are in [sentry.md](sentry.md). Anything marked *proposal* is a suggestion for that interface's owner (see [team_plan.md](team_plan.md)) to accept or change.

## The JIT analogy

| JIT compiler | Browseen |
|---|---|
| Interpreter (slow, general) | The Browser Use agent doing the task step by step |
| Profiling the interpreter | Recording the agent's run |
| Compiling the hot path | Compiling the recording into a program |
| Type guards in compiled code | Checks on the page before and after each step |
| Deoptimization: bail out to the interpreter when a guard fails | Hand **only the failing step** to the LLM or the agent |
| Polymorphic inline cache | Keep the old and new paths as branches, so both site variants replay for free |
| Recompilation | The verified patch becomes program v(N+1), and later runs are compiled again |

## Pipeline

```
 FIRST RUN (pays the LLM once)
 task + params ──► Browser Use agent ──► Recorder ──► trace
                                                        │
                                                        ▼
                                                    Compiler
                                                        │
                                                        ▼
 LATER RUNS (0 LLM calls)                        program vN (YAML)
 params ──────────────────────────────────────►  Runtime (Playwright)
                                                        │
                        each step: pre-checks → act → post-checks
                                                        │
               all pass ────────────────────────────────┼──► … ──► success check ──► done
                                                        │
                                          a check fails at step k
                                                        ▼
                                                     Healer
                         tier 1  other locators / fuzzy match        0 LLM calls
                         tier 2  one LLM call patches step k         1 LLM call
                         tier 3  Browser Use agent takes over at k   a few LLM calls
                                                        │ patch passes step k's post-checks
                                                        ▼
                                  program v(N+1) saved ──► resume compiled at step k+1
```

**There is no human in the loop.** A failure is always handed to the next healing tier, and the run either finishes or fails loudly.

## Components

### Recorder (B)

This component wraps a Browser Use `Agent` and uses its step hooks (`on_step_start` / `on_step_end`) to capture, for each step:

- **The action** and its parameters: click, input text, navigate, select, scroll, extract.
- **The target element.** Browser Use records each element it touched with its tag, attributes, XPath, element hash, stable hash, accessible name and bounds. It does **not** store CSS or role selectors, so the compiler derives those.
- **The page around the step:** the URL before and after, a DOM / accessibility snapshot, and a screenshot.
- **The agent's stated goal for the step**, which becomes the step's intent.
- **Tokens and latency** for the step, which feed the cost counters.

Output: `runs/<run_id>/trace.json` (gitignored), plus Browser Use's own history file from `save_to_file()`.

Two setup notes:

- **Hour-one check:** pin the browser-use version in `requirements.txt`. The latest on PyPI is 0.13.11, which needs Python ≥ 3.11. Confirm that the history has element data.
- **Model gotcha:** Browser Use's `ChatAnthropic` forces `tool_choice` unless thinking is set, and Claude Opus 5.5 / Sonnet 5.5 reject forced tool choice with HTTP 400. Use `ChatAnthropic(model="claude-opus-5-5", thinking={"type": "adaptive"})`, and don't set `temperature`, `top_p` or `seed`.

### Compiler (B)

The compiler is a few deterministic passes plus **one LLM pass**:

1. **Normalize.** Drop failed or no-op actions, collapse mis-click-then-correct sequences, and merge consecutive typing into one action.
2. **Parameterize.** Literals that came from the task inputs become `$params`. The LLM pass names them and gives each a type.
3. **Locators.** For each target, build candidates in this order: test id, then role + accessible name, then label or placeholder, then text, then stable CSS, then XPath. Keep only candidates that match exactly one element in the recorded snapshot. Also store a **fingerprint** of the element (role, name, text, neighbors) for fuzzy matching later.
4. **Guards.** Generate checks for each step:
   - **Pre-checks:** the URL pattern, and that the target exists, is unique and is enabled.
   - **Post-checks:** the URL changed as expected, the expected element or text appeared, or extracted data matches its schema.
5. **Branches.**
   - *Optional steps:* the LLM pass marks steps that dismiss popups or cookie banners, and they become `when: exists(...)`.
   - *Learned branches:* when the healer fixes a step on a site that might switch back (an A/B layout), the old path stays as one arm and the new path becomes another.
   - Loops and merging several recordings into one program are stretch goals.
6. **Intent and success.** Every step keeps a one-sentence intent, and the program gets a task-level **success check**, such as "Order confirmed" being visible.

### Program format (owner: B)

There is one YAML file per program version, under `programs/<name>/v<N>.yaml`. Every version is kept, so a rollback just points back to an older file. Here is an example *proposal*:

```yaml
program: buy-item
version: 2
params: {product: string, qty: integer}
start_url: http://localhost:8001/shop
steps:
  - id: s1
    intent: "Dismiss the cookie banner if it is shown"
    when: {exists: {role: button, name: "Accept all"}}      # optional-step branch
    action: {type: click, target: {role: button, name: "Accept all"}}

  - id: s2
    intent: "Search for the product"
    action: {type: fill, value: "$product"}
    target:
      locators:                                               # tried in order
        - {testid: search-input}
        - {role: searchbox, name: Search}
        - {css: "input[name=q]"}
        - {xpath: "/html/body/header/form/input"}
      fingerprint: {role: searchbox, name: Search, near: header}
    pre:  [{url_matches: "^/shop"}, {unique: target}]
    post: [{url_matches: "^/search"}]
  # … s3 to s9
success: [{text_visible: "Order confirmed"}]
history:
  - {version: 2, step: s5, tier: 2, reason: "'Add to cart' renamed to 'Add to bag'"}
```

### Runtime (A)

The runtime interprets the program with Playwright. For each step it:

1. skips the step if its `when` is false;
2. resolves the target through the locator list;
3. runs the pre-checks;
4. performs the action and waits for the page to settle;
5. runs the post-checks.

When the last step is done, it runs the **success check**. The happy path makes **zero LLM calls**.

When a check fails, the runtime raises `GuardFailure`, carrying which check failed, the expected vs. the actual state, a snapshot and a screenshot, and hands the step to the healer.

**One browser per run.** Launch Chromium with a CDP port so that tier 3 can hand the *same* page (with its cookies and cart) to Browser Use, which connects over CDP. Playwright pauses while the agent drives. Verify this in hour one. If it doesn't work, the agent can open its own browser at the current URL with Playwright's saved storage state.

### Healer (A)

The healer repairs only the failing step, escalating through three tiers, cheapest first. These are the same tier numbers as `heal.tier` in [sentry.md](sentry.md).

| Tier | What happens | LLM calls |
|---|---|---|
| **1. Local** | Try the step's other locators, then fuzzy-match the stored fingerprint against the current accessibility tree. Accept only a single candidate that passes both pre- and post-checks. | 0 |
| **2. Patch** | One LLM call. It gets the step's intent, the original fingerprint, the failed check and a trimmed accessibility snapshot (plus a screenshot), and returns a **structured patch**: a new target, steps to insert before this one (such as "close the popup"), or a new branch arm. | 1 |
| **3. Agent** | A Browser Use agent starts from the current page with the task "accomplish *step k's intent* (overall goal: *task*)". After each agent step, the runtime checks whether a later compiled step's pre-checks pass; as soon as one does, the agent stops, its actions are compiled into a replacement block, and compiled replay resumes. If no step ever matches, the agent finishes the task and its trace is compiled into the rest of the program. | a few |

These rules apply at every tier:

- **Verify before saving.** A patch is kept only if the step's post-checks pass, and a run counts as successful only if the success check passes. That prevents lucky passes.
- **Version every patch.** Program v(N+1) records the step, the tier and the reason, and the dashboard shows the diff. `rollback` restores any earlier version.
- **Resume compiled.** After a heal, execution continues at the next step in compiled mode, and the next run is free again.
- **Fail loudly.** If all three tiers fail, the run is marked failed with a report. It is never reported as a success.
- **No human approval.** The LLM or the agent always handles the repair.

## Interfaces

| Interface | Owner | Consumers |
|---|---|---|
| Trace format | B | B's compiler |
| Program YAML | B | A (runtime, healer), D (program view, diff) |
| Event stream | A | D (dashboard), C (benchmark) |
| Run API | A + D | D (dashboard), C (harness) |
| Testbed contract | C | Everyone |

### Event stream (*proposal* for A)

The event stream is one JSON object per line, written to `runs/<run_id>/events.jsonl` and served to the dashboard over server-sent events:

```json
{"ts": "2026-10-17T21:04:11.2Z", "run_id": "r_042", "program": "buy-item", "version": 1,
 "mode": "compiled", "type": "healed", "step": "s5", "tier": 2,
 "detail": "'Add to cart' renamed to 'Add to bag'", "diff": "…",
 "llm_calls": 1, "tokens": 9530, "usd": 0.045, "trace_id": "…"}
```

`type` is one of `run_started`, `step_started`, `check_passed`, `check_failed`, `heal_started`, `healed`, `heal_failed`, or `run_finished`. `run_finished` carries the totals: LLM calls, tokens, $, seconds and success.

### Run API (*proposal* for A + D, FastAPI in `browseen/api.py`)

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/record` | Run the Browser Use agent on a task, record it, and compile program v1 |
| `POST` | `/programs/{name}/run` | Compiled run with params, healing automatically |
| `POST` | `/programs/{name}/run-agent` | Baseline: run the plain agent, for the side-by-side counters |
| `GET` | `/programs` · `/programs/{name}/versions` | List programs and their versions |
| `GET` | `/programs/{name}/diff?from=1&to=2` | Diff between two versions |
| `POST` | `/programs/{name}/rollback?to=1` | Restore a version |
| `GET` | `/runs/{id}/events` | Event stream (SSE) |

### Testbed contract (*proposal* for C)

These are the test sites we control (see [benchmark.md](benchmark.md#2-testbed-sites)):

- **`?mut=<ids>`** or a header turns on page changes. The chaos panel uses the same IDs.
- **`POST /__reset`** restores the seed data.
- **`GET /__verify?task=…`** gives server-side ground truth for the benchmark.
- **A `run_id` header** is recorded server-side, so verification maps to runs.
- **The Sentry browser SDK with Session Replay** runs on every page.

## CLI (B)

Run commands as `python -m browseen <command>`. The entry point is `browseen/__main__.py`, which already has `--demo` for trying Sentry.

| Command | Does |
|---|---|
| `record "<task>" --url <start>` | Run the agent once and save the trace |
| `compile <trace>` | Trace → `programs/<name>/v1.yaml` |
| `run <name> --param k=v` | Compiled run with automatic healing |
| `diff <name> <a> <b>` | Show what changed between two versions |
| `rollback <name> --to <v>` | Restore a version |

## Tech stack

| Layer | Choice | Notes |
|---|---|---|
| Language and packaging | Python 3.12, `requirements.txt` + a venv | `python -m venv .venv && pip install -r requirements.txt`. Pin versions once they're confirmed. |
| First run and tier 3 | browser-use (pinned) | Drives Chrome over CDP. Gives us step history with element data. |
| Compiled runtime | Playwright for Python (1.64) | `get_by_role` / `get_by_text` / `get_by_test_id` for locators; `aria_snapshot()` for snapshots and guard checks. |
| LLM | Anthropic SDK; `claude-opus-5-5` by default for compile, tier 2 and the agent | One thin client that logs tokens and $ for every call. The model is configurable, and the benchmark logs it. |
| API | FastAPI + SSE | `browseen/api.py` |
| Test sites | FastAPI + Jinja templates + SQLite | Shop, form portal and CRM with page-change switches |
| Dashboard | React + Vite + Tailwind | Live counters, side-by-side runs, program view, diffs with the healed step highlighted, chaos panel, benchmark charts |
| Observability | `sentry-sdk` (Python) and the Sentry browser SDK on the test sites | See below and [sentry.md](sentry.md) |
| Hosting | Local for the demo; Vultr optional | The demo must not depend on it |

### Repo layout

```
browseen/                 # Python package
  __main__.py             # CLI entry (exists)
  observability.py        # Sentry init (exists)
  tracing.py              # run / step / LLM span helpers (exists)
  recorder/  compiler/    # B
  runtime/   healer/      # A (runtime/ includes the guard checks)
  api.py                  # A + D
testbed/                  # C: shop/ portal/ crm/ mutations.py
bench/                    # C: tasks/ mutations.yaml config.yaml run.py report.py results/
dashboard/                # D
programs/                 # compiled programs, every version kept
requirements.txt
```

## Observability (Sentry)

[sentry.md](sentry.md) is the reference for setup, tags and the findings log. In short:

- **Tracing.** There is one transaction per run (`run_span`) and one span per step (`step_span`), both in `browseen/tracing.py`. The tags are:
  - `mode`: `llm`, `compiled` or `healed`
  - `program.version`
  - `guard.result`: `pass` or `fail`
  - `heal.tier`: 1, 2 or 3

  A heal shows up as one slow span among fast ones.
- **Logs.** `mark_healed` writes one log line per heal. Add one for each failed check too.
- **Profiling** is already on in `observability.py`.
- **AI agent monitoring.** The Python SDK auto-instruments the Anthropic SDK, so compile and tier-2 calls appear as `gen_ai` spans with tokens and cost. Spans with custom ops such as `agent.llm` don't appear in Sentry's Agents view, so wrap the tier-3 agent in a `gen_ai.invoke_agent` span (*proposal*).
- **Session Replay** goes on the test sites, so we can watch the browser at the moment of a heal. Replay masks text and inputs by default; turn that off on our synthetic sites. Replay can't record third-party sites.
