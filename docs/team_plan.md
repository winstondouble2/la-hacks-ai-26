# Team Plan: Splitting the Work Four Ways

Who builds what, and what each person hands to the others. The design is in [architecture.md](architecture.md), and what we measure is in [benchmark.md](benchmark.md).

## Roles at a glance

| Role | Owns | Code | Interfaces owned | Who |
|---|---|---|---|---|
| **A: Runtime + healer** | Compiled replay on Playwright, guard checks, the three healing tiers, versioning and rollback | `browseen/runtime/`, `browseen/healer/`, `browseen/api.py` (with D) | Event stream; run API (with D) | _fill in_ |
| **B: Recorder + compiler** | Recording the Browser Use run, compiling it into a program, the CLI | `browseen/recorder/`, `browseen/compiler/`, `browseen/__main__.py`, `programs/` | Trace format; **program YAML** | _fill in_ |
| **C: Testbed + benchmark** | The test sites with page-change switches, the benchmark harness and runs | `testbed/`, `bench/` | Testbed contract; mutation list; task definitions | _fill in_ |
| **D: Dashboard + Sentry + story** | The demo dashboard, Sentry, README, Devpost, the pitch and the video | `dashboard/`, `browseen/observability.py`, `browseen/tracing.py`, `docs/sentry.md`, `README.md` | Run API (with A) | _fill in_ |

Charlie has already built the Sentry setup and span helpers (`observability.py`, `tracing.py`, `docs/sentry.md`), which is D's area.

**Matching people to roles:**

- **A** is the hardest Python piece, so give it the strongest backend person.
- **B** needs someone happy reading browser-use internals.
- **C** suits someone fast with web templates who doesn't mind running long jobs.
- **D** needs the best presenter, who will also give the pitch.

## What each person builds

### A: Runtime + healer

- **Runtime.** Run a program YAML on Playwright. For each step: check `when`, resolve the target through the locator list, run the pre-checks, act, wait, run the post-checks. Run the success check at the end.
- **Checks:** `url_matches`, `unique` / exists / enabled, `text_visible`, element fingerprint.
- **Tier 1 heal:** try the other locators, then fuzzy-match the fingerprint against the accessibility tree. No LLM.
- **Tier 2 heal:** one LLM call returns a structured patch (a new target, inserted steps, or a new branch arm). It's dry-run and must pass the step's post-checks.
- **Tier 3 heal:** hand the same browser to a Browser Use agent over CDP, and resume compiled replay as soon as a later step's pre-checks pass.
- **Versioning:** every accepted patch becomes `v(N+1)` with a diff and a reason; `rollback` restores any earlier version.
- **Event stream** (`runs/<id>/events.jsonl` + SSE), and the run API, built with D.
- **System adapters for C's harness:** `browseen`, `browseen-t1`, `browseen-t2`, and `takeover` (on any failure, the agent finishes the task).
- **Sentry spans** in the runtime and healer, using D's helpers in `tracing.py` (`step_span`, `mark_healed` with `heal.tier`).

### B: Recorder + compiler

- **Browser Use setup.** Pin the version in `requirements.txt` and smoke-test it with `ChatAnthropic(model="claude-opus-5-5", thinking={"type": "adaptive"})`; without `thinking` it fails with HTTP 400. Confirm the step history has element data.
- **Recorder.** Hook the agent's steps to capture the action, the target element (XPath, accessible name, attributes), the URL, a page snapshot, a screenshot, the agent's stated goal, and tokens and time. Write `runs/<id>/trace.json`.
- **Program YAML schema,** plus a hand-written example `programs/buy-item/v1.yaml` for A and D to build against.
- **Compiler.** Normalize the trace, turn task inputs into `$params`, build the locator list and fingerprint, generate the pre- and post-checks and the success check, and mark optional steps such as the cookie banner. It uses one LLM pass for parameter names, intents and optional steps.
- **CLI:** `python -m browseen record | compile | run | diff | rollback`. `run`, `diff` and `rollback` wrap A's functions.
- **Harness adapters** for the `agent` and `replay` (Browser Use `load_and_rerun`) systems, paired with C.
- **README section with D:** how to run it, plus the reused-vs-new table. Browser Use and Playwright are reused; everything else was written at the event.

### C: Testbed + benchmark

- **Devin sessions** for the test-site generator and the harness scaffold, kept as proof for the Cognition track.
- **Test sites**, built with FastAPI + Jinja + SQLite: the **shop** (the demo task), then the **portal** and **CRM**.
- **Testbed hooks:** `?mut=<ids>&seed=<n>`, `POST /__reset`, `GET /__verify`, and a `run_id` header recorded server-side.
- **Mutations M00–M16** in `testbed/mutations.py`, and the catalog with the dev / held-out split in `bench/mutations.yaml`. **Commit the list before the first benchmark run.** Ask a teammate who isn't working on the healer to write the held-out set.
- **Task definitions:** `bench/tasks/T1.yaml` and the others.
- **Harness:** `bench/run.py` (resumable, with a budget cap, one JSONL row per run, every run traced in Sentry) and `bench/config.yaml`.
- **Benchmark runs,** including the drift scenario, then `bench/report.py` for the charts and headline numbers, which go to D.
- **Sentry browser SDK + Session Replay** on the test sites, with D.
- *Optional:* deploy the test sites to Vultr. The demo must not depend on it.

### D: Dashboard + Sentry + story

- **Dashboard** (React + Vite + Tailwind), reading the event stream:
  - **side-by-side runs** with live counters for time, tokens, $ and LLM calls (first agent run vs. compiled run);
  - the **program view**, showing steps, intents, guards and branches, with healed steps highlighted;
  - a **diff view** for v1 → v2, showing the tier and the reason;
  - the **chaos panel**, which turns test-site mutations on and off live for the judge;
  - a **benchmark page** with C's charts.
- **Sentry:**
  - extend `tracing.py` as A needs;
  - add a `gen_ai.invoke_agent` span around tier 3, so it shows up in AI agent monitoring;
  - set up Session Replay on the test sites with C;
  - keep the findings log in `docs/sentry.md` up to date with real moments.
- **Story:** the README, the Devpost write-up (one paragraph per company challenge), the demo script, a 60-second backup recording, the 2–3 minute video, and the submission, including the Commit Fellowship opt-in.

## Handoffs

Nobody should be blocked on another person. Work against a mock until the real piece lands.

| Dependency | From → to | Mock until then |
|---|---|---|
| Shop site with the demo task | C → A, B | A: a saved HTML copy of a simple page. B: record a Browser Use run on any simple site to learn the history format. |
| Program YAML schema + example file | B → A, D | The example in [architecture.md](architecture.md#program-format-owner-b), hand-written as `programs/buy-item/v1.yaml` |
| A compiled program from a real recording | B → A | The hand-written v1 |
| Event stream | A → D | A fake `runs/sample/events.jsonl`, written from the proposal in [architecture.md](architecture.md#event-stream-proposal-for-a) |
| Run API | A + D | D's dashboard reads the fake stream; A calls functions directly |
| System adapters (`browseen`, `takeover`, …) | A → C | C builds the `agent` and `replay` systems first (with B) |
| Mutation IDs | C → D (chaos panel) | Hard-code M04, M06 and M09 in the panel |
| Benchmark numbers | C → D | Placeholders in the README and Devpost drafts |

## Ownership rules

- **Each folder has one owner** (see the table at the top). Edit someone else's folder only after asking them.
- **Only the owner changes an interface:** B for the trace format and the program YAML, A for the event stream, A + D together for the run API, C for the testbed contract and the mutation list. Post any change in the team chat first.
- **Every teammate must be able to explain the core loop:** record, compile, replay, check, heal. Judges ask.

## If we're only three

C also takes D's Sentry work, the chaos panel becomes a fixed list of three mutations, and the benchmark shrinks to its minimum version (see [benchmark.md → If we're short on time](benchmark.md#12-if-were-short-on-time)).
