# Architecture

How the Self-Healing Agent Compiler works. For the pitch and motivation see [overview.md](overview.md); for libraries and versions see [tech-stack.md](tech-stack.md).

## The JIT analogy

The design borrows its vocabulary from JIT compilers, and the analogy holds closely enough to guide implementation decisions:

| JIT compiler | Our system |
|---|---|
| Interpreter (slow, general) | LLM browser agent (Browser Use) doing the task step by step |
| Profiling the interpreter | Recording the agent's trajectory |
| Compiling the hot path to machine code | Compiling the trajectory into a program (IR) |
| Type guards in compiled code | Guards on the page state before and after each step |
| Deoptimization: bail out to the interpreter when a guard fails | Hand only the failing step back to the LLM |
| Polymorphic inline cache | Keep the old and new paths as branches, so site variants (A/B tests) both run compiled |
| Recompilation | The verified patch becomes program v(n+1); later runs are compiled again |

## Big picture

```
                 FIRST RUN (slow, costs tokens)
  task + params ──► Recorder ──► Browser Use agent ──► trajectory
                                                          │
                                                          ▼
                                                      Compiler
                                                          │
                                                          ▼
                 LATER RUNS (fast, 0 LLM calls)     Program vN (IR, JSON)
  params ───────────────────────────────────────►  Runtime (Playwright)
                                                          │
                                       all guards pass ───┼──► result
                                                          │
                                   guard fails at step k  ▼
                                                       Healer
                                    tier 1: alternate locators / fuzzy match (no LLM)
                                    tier 2: one Claude call to patch step k
                                    tier 3: scoped Browser Use agent for step k
                                                          │ patch verified by post-guards
                                                          ▼
                                     Program v(N+1) ──► resume compiled at step k+1
```

## Components

### 1. Recorder

This component wraps a Browser Use `Agent` and hooks every step to capture:

- the action and its parameters (`click`, `input_text`, `go_to_url`, `select_dropdown_option`, `scroll`, `extract`, etc.)
- the **target element**: tag, attributes, XPath, accessible role + name, visible text, bounding box, and its neighbors (the label, the parent section heading)
- the URL before and after the step, an ARIA snapshot of the page (or the target's region) before and after, and a screenshot
- the agent's stated goal for the step (its `next_goal`/reasoning), which becomes the step's **intent**
- token usage and latency for the step, which feed the cost comparison

Output: a `Trace` JSON file saved under `runs/<run_id>/` (this directory is gitignored).

### 2. Compiler

This component turns a `Trace` into a `Program`. It runs as a series of passes:

1. **Normalize.** Drop failed or no-op actions, collapse the agent's mis-click-then-correct sequences, and merge consecutive typing into one action.
2. **Parameterize.** Find literals that came from the task inputs (the search term, the quantity, the email) and replace them with `{{variables}}`. One LLM call at compile time names the variables and their types.
3. **Locator synthesis.** For each target, generate ranked locator candidates in this order: `data-testid`, then role + accessible name, then label/placeholder, then text, then stable CSS, then XPath. Check each candidate against the recorded snapshot and keep only those that match exactly one element. Also store a **fingerprint** of the element (role, name, text, attributes, neighbors) so the healer can match it fuzzily later.
4. **Guard synthesis.**
   - *Preconditions*: the URL matches a pattern; the target exists, is unique, visible and enabled; the ARIA fingerprint of the region is similar enough to what was recorded.
   - *Postconditions*: the URL changed as expected; the expected element appeared or disappeared; extracted data matches its schema.
5. **Branch synthesis.** The compiler emits branches, which is what separates us from linear replay:
   - *Optional steps*: steps that dismiss popups or cookie banners become `if exists(...)`.
   - *Loops*: pagination or per-item work becomes `while` / `for_each`.
   - *Trace merging*: several recorded runs of the same task merge into one control-flow graph that branches on the page state that distinguishes them.
   - *Learned branches*: when the healer fixes a step, the old path stays as one arm and the new path becomes another (the polymorphic inline cache).
6. **Intent annotation.** Every step keeps its natural-language intent, for example "Click 'Add to cart' for the selected product". The healer needs this to know what the step was *for*.

### 3. Program IR

Programs are versioned JSON files, which makes the v1 → v2 diff easy to show on stage. The schema is defined with Pydantic in `engine/`. Here is a trimmed example:

```json
{
  "program": "buy-item",
  "version": 2,
  "params": { "product": "string", "qty": "integer" },
  "start_url": "http://localhost:3001/shop",
  "steps": [
    {
      "id": "s1",
      "intent": "Dismiss the cookie banner if it is shown",
      "kind": "if",
      "cond": { "exists": { "role": "button", "name": "Accept all" } },
      "then": [{ "id": "s1a", "action": "click", "target": { "role": "button", "name": "Accept all" } }]
    },
    {
      "id": "s2",
      "intent": "Search for the product",
      "action": "fill",
      "target": {
        "candidates": [
          { "testid": "search-input" },
          { "role": "searchbox", "name": "Search" },
          { "css": "input[name=q]" }
        ],
        "fingerprint": { "role": "searchbox", "name": "Search", "near": "header" }
      },
      "value": "{{product}}",
      "pre": [{ "url_matches": "^/shop" }, { "target_unique": true }],
      "post": [{ "url_matches": "^/search" }]
    }
  ],
  "success": { "text_visible": "Order confirmed" },
  "history": [{ "version": 2, "patched_step": "s5", "reason": "button renamed 'Add to cart' → 'Add to bag'", "tier": 2 }]
}
```

### 4. Runtime

The runtime interprets the IR with Playwright and makes **zero LLM calls on the happy path**. For each step it:

1. evaluates the preconditions,
2. performs the action,
3. waits for the page to settle (load state, network idle, or the expected element),
4. evaluates the postconditions.

When a guard fails it raises `GuardFailure` with diagnostics (which guard, the expected vs. the actual state, a snapshot, a screenshot), and execution passes to the healer. The runtime streams events (`step_started`, `step_passed`, `guard_failed`, `step_healed`, `run_finished`) to the dashboard over WebSocket and emits a Sentry span for each step.

### 5. Healer (deoptimization)

The healer repairs only the step that broke, and escalates through three tiers, cheapest first:

| Tier | What it does | LLM calls |
|---|---|---|
| 1. Local | Try the other locator candidates, then fuzzy-match the stored fingerprint against the current ARIA tree (similar role, name, text, neighbors). Accept only a single candidate that passes both pre- and postconditions. | 0 |
| 2. Patch | One Claude call with the step intent, the original fingerprint, the current ARIA snapshot + screenshot and the guard failure. It returns a **structured patch**: a new target, inserted steps (such as a new modal to close), or a new branch arm. | 1 |
| 3. Agent | A Browser Use agent scoped to "accomplish step k's intent from the current page", with a small `max_steps`. Its sub-trace is compiled into a replacement block. | a few |

These rules keep a heal honest:

- **Verify before committing.** A patch is kept only if the step's postconditions pass, and the run counts as successful only if the program's `success` check passes, so a lucky pass doesn't count.
- **Version every patch.** Program v(N+1) records the patched step, the reason, and the tier, and the dashboard renders the diff.
- **Fail loudly.** If all three tiers fail, the run aborts with a report instead of guessing.
- **Resume compiled.** After a heal, execution continues at step k+1 in compiled mode.

## Data flow and storage

| What | Where | Committed? |
|---|---|---|
| Programs (IR, every version) | `programs/<name>/v<N>.json` | yes, so they can be shown and diffed |
| Traces, screenshots, snapshots | `runs/<run_id>/` | no (gitignored) |
| Run metrics (tokens, $, latency, outcome) | SQLite `engine/data.db` | no |
| Benchmark results | `bench/results/*.json` (final ones are copied into the README) | the final ones only |

## API (engine, FastAPI)

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/tasks` | Create a task (natural-language goal, param schema, start URL) |
| `POST` | `/tasks/{id}/record` | Run the Browser Use agent, record the trace, compile program v1 |
| `POST` | `/programs/{name}/run` | Run the compiled program with params, healing if needed |
| `POST` | `/programs/{name}/run-llm` | Baseline: run the plain agent with no compilation |
| `GET` | `/programs/{name}` / `/programs/{name}/versions/{a}..{b}` | Show a program and the diff between versions |
| `POST` | `/bench` | Run the benchmark matrix |
| `WS` | `/runs/{id}/events` | Live step events for the dashboard |

## Observability (Sentry)

- **Tracing.** Each run is a transaction and each step is a span tagged `mode=compiled|healed|llm`, `program.version`, `guard.result`, `heal.tier`. A heal is visible as one slow span among fast ones.
- **AI agent monitoring.** LLM calls (the recording run, tier-2 and tier-3 heals) show up as AI spans with model, tokens and cost.
- **Session Replay.** The testbed sites run the Sentry browser SDK with Replay at 100% sampling and are tagged with the `run_id`, so judges can watch the agent's browser session and the moment the heal happened.
- The dashboard links each run to its Sentry trace and replay.

See [tech-stack.md](tech-stack.md#observability--sentry) for which Sentry products count toward the sponsor track.

## Benchmark design

The **modified-page benchmark** is the claim that separates us from linear replay (LOOP, taprun). It has four parts:

- **Tasks.** 5–8 tasks across 2–3 testbed sites: shop checkout, a multi-page form, search-and-extract on a table, a login-gated flow.
- **Mutations.** A catalog of deterministic page changes, toggled through `?mut=` or the chaos panel:

  | Mutation | Example |
  |---|---|
  | Text rename | "Add to cart" → "Add to bag" |
  | Selector churn | ids and classes changed, `data-testid` removed |
  | Move / reorder | button moved into a dropdown; field order shuffled |
  | Wrapper insertion | extra `div`s / shadow root around the target |
  | Interstitial | a newsletter modal or cookie banner appears |
  | New required field | the checkout now needs a phone number |
  | Variant | an A/B layout with the same function and different structure |
  | Timing | slow load, lazy-rendered list |
  | Pagination | the item moves to page 2 |

- **Baselines.**
  1. *LLM every time*: plain Browser Use agent.
  2. *Linear replay*: recorded selectors with no guards, branches or repair (LOOP-style; also Browser Use's own history rerun, if available).
  3. *Ours.*
- **Metrics**, always reported together: verified success rate, $ and tokens per run, wall-clock time, LLM calls per run, heal success rate by tier, and false-pass rate.
