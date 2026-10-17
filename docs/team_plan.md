# Team Plan: Splitting the Work Four Ways

Who builds what, and what each person hands to the others. The four roles come from [build_plan.md → 24-hour plan](build_plan.md#24-hour-plan).

## Roles at a glance

| Role | Owns | Code | Interfaces owned | Who |
|---|---|---|---|---|
| **A: Runtime** | Executor, guard engine, judge, healer, diff + rollback, receipt check | `browseen/executor/`, `guards/`, `healer/`, `api.py` | Event stream; approval API (with D) | _fill in_ |
| **B: Capture** | Browser Use recorder, compiler, YAML schema, CLI, the two hand-authored branches | `browseen/recorder/`, `compiler/`, `__main__.py`, `programs/` | Program YAML schema | _fill in_ |
| **C: Sites + benchmark** | Three portals with audit log and mutation switch, the benchmark harness, the benchmark runs, (Vultr deploy) | `portals/`, `bench/` | Audit-log schema; mutation list | _fill in_ |
| **D: Product + story** | Dashboard, approvals queue, Slack, Sentry, README, Devpost, demo and video | `dashboard/`, `browseen/observability.py`, `browseen/tracing.py`, `README.md` | Approval API (with A) | _fill in_ |

Charlie has already started the Sentry setup (`browseen/observability.py`, `browseen/tracing.py`), which is D's area.

**Matching people to roles:**

- **A** is the hardest Python piece, so give it the strongest backend person.
- **B** needs someone happy reading browser-use internals.
- **C** suits someone fast with web templates who doesn't mind running long jobs.
- **D** needs the best presenter, who will also give the pitch.

## What each person builds

### A: Runtime

- **Executor:** runs a YAML program on Playwright and writes the event stream (`events.jsonl` + SSE).
- **Deterministic checks:** `url_matches`, `element` (role + name + enabled), `text_visible`, structural fingerprint.
- **Failure rules by risk:** heal on read steps; stop and ask on write and irreversible steps.
- **Judge:** a cheap model, called only on write steps and on elements that still match but were renamed.
- **Healer:** a one-step patch that is dry-run against the same post-check. On a pass, the version goes up and the diff is stored.
- **Rollback** to any earlier program version.
- **Receipt check** against the portal's audit table.
- **Approval API + SSE endpoint**, built with D. Approving resumes the run, and a `stopped` event carries everything Slack needs.
- **System D adapter** for C's harness: run one program on one mutation and return the outcome.
- **Tuning:** remove false alarms on mutations 1, 2 and the control.

### B: Capture

- **Browser Use setup.** Pin the version and smoke-test it with `ChatAnthropic(model="claude-opus-5-5", thinking={"type": "adaptive"})`; without `thinking` it fails with HTTP 400. Confirm the step history has element data.
- **Recorder:** records the eligibility flow on portal A and tags each step read, write or irreversible.
- **Program YAML schema** plus an example file, `programs/eligibility-check/v1.yaml`.
- **Compiler:** one LLM pass from the recording to v1, with intents, pre- and post-checks, receipt rules, risk tags and `$parameters`.
- **CLI:** `record`, `compile`, `run`, `doctor`, `heal`, `rollback`, wrapping A's functions.
- **The two hand-authored branches:** the consent banner (mutation 6) and the extra confirmation page (mutation 7).
- **Harness adapters** for systems A (agent every run) and B (blind replay from the recorded selectors), paired with C.
- **README draft** with D, including the run steps and the **reused-vs-new table**. Browser Use and Playwright are reused; everything else was written this weekend.

### C: Sites + benchmark

- **Devin sessions** for the portal generator and the harness scaffold, kept as proof for the Cognition track.
- **Portals** A, B and C (FastAPI + Jinja + SQLite, three layouts from one generator) with the eight-step eligibility flow and synthetic patients.
- **Audit-log schema and table**, plus a `run_id` header recorded in audit rows and a reset script.
- **Mutation switch** (query param or header) for all ten mutations.
- **`bench/mutations.md`:** the ten mutations, each with a "correct response" label. **Commit it before any benchmark run.**
- **Harness:** `bench/run.py` with systems A–D, writing JSONL rows, with a dollar cap and a step cap.
- **Sentry browser SDK + Session Replay** on the portals, with D.
- **Split-screen setup** with D: two portal instances on mutation 9, blind replay on the left and Browseen on the right.
- **Benchmark runs** and `bench/report.py`: the heatmap and the headline numbers, handed to D.
- *Optional:* deploy the portals and runner to Vultr. The demo must not depend on it.

### D: Product + story

- **Accounts:** the Sentry project (share the DSN in `.env`) and the Slack incoming webhook.
- **Dashboard** (React + Vite + Tailwind):
  - program view: steps, intents, read/write tags, checks;
  - live counters: tokens, $, seconds;
  - diff view with the **gold seam** on healed steps;
  - approvals queue: intent, screenshot, diff, trace link, Approve / Reject;
  - split-screen view;
  - break-it panel: pick a mutation, or "Surprise me".
- **Slack alert** on every stop.
- **Sentry:**
  - step attributes (`step.id`, `step.risk`, `guard.result`) and a Logs line per guard decision, with A;
  - Session Replay on the portals, with C;
  - a **build log** of real Sentry moments for the Sentry write-up.
- **Story:** Maria's story card, the README and Devpost (with B), the 60-second backup capture, rehearsals, the 2–3 minute video, and the Devpost submission, including the Commit Fellowship opt-in.

## Handoffs

Nobody should be blocked on another person. Work against a mock until the real piece lands.

| Dependency | From → to | Mock until then |
|---|---|---|
| Portal A with the eligibility flow | C → A, B | A: a saved HTML copy of a simple form. B: record a Browser Use run on any simple page to learn the history format. |
| Audit-log schema | C → A, C's harness | The proposal in [architecture.md](architecture.md#audit-log-proposal-for-c) |
| Program YAML schema + example file | B → A, D | A hand-written `programs/eligibility-check/v1.yaml` that A and B draft together |
| Compiled program from a real recording | B → A | The hand-written v1 |
| Event stream (`events.jsonl` + SSE) | A → D | A fake `runs/sample/events.jsonl`, written from the proposal in [architecture.md](architecture.md#event-stream-proposal-for-a) |
| System D adapter | A → C | C builds systems A (agent) and B (blind replay) first |
| CLI commands | B → everyone | Call the Python functions directly |
| Approval API | A + D | The dashboard queue reads `stopped` events from the fake stream |
| Benchmark numbers | C → D | Placeholder "*k* of *N*" in the README and Devpost drafts |

## Ownership rules

- **Each folder has one owner** (see the table at the top). Edit someone else's folder only after asking them.
- **Only the owner changes an interface:** B for the YAML schema, C for the audit log and mutation list, A for the event stream, A + D together for the approval API. Post any change in the team chat first.
- **Every teammate must be able to explain the core code** (compile, guards, heal), even if it isn't their piece.

## If we're only three

From the build plan: C also takes D's Sentry work, and the break-it panel and Slack move to Stretch.
