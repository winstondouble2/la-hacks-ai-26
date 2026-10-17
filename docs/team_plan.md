# Team Plan: Splitting the Work Four Ways

Who builds what, when each piece is due, and what each person hands to the others. The roles and milestones come from [build_plan.md → 24-hour plan](build_plan.md#24-hour-plan); this page turns them into per-person checklists. Hacking runs **Sat Oct 17, 12:00 → Sun Oct 18, 12:00 PDT**, and we submit at **10:30 Sunday**.

## Roles at a glance

| Role | Owns | Code | Interfaces owned | Who |
|---|---|---|---|---|
| **A: Runtime** | Executor, guard engine, judge, healer, diff + rollback, receipt check | `browseen/executor/`, `guards/`, `healer/`, `api.py` | Event stream; approval API (with D) | _fill in_ |
| **B: Capture** | Browser Use recorder, compiler, YAML schema, CLI, the two hand-authored branches | `browseen/recorder/`, `compiler/`, `__main__.py`, `programs/` | **Program YAML schema** (frozen 14:30) | _fill in_ |
| **C: Sites + benchmark** | Three portals with audit log and mutation switch, the benchmark harness, overnight runs, (Vultr deploy) | `portals/`, `bench/` | **Audit-log schema** (frozen 14:00); mutation list | _fill in_ |
| **D: Product + story** | Dashboard, approvals queue, Slack, Sentry, README, Devpost, demo and video | `dashboard/`, `browseen/observability.py`, `browseen/tracing.py`, `README.md` | Approval API (with A) | _fill in_ |

Charlie has already started the Sentry setup (`browseen/observability.py`, `browseen/tracing.py`), which is D's area.

**Matching people to roles:**

- **A** is the hardest Python piece, so give it the strongest backend person.
- **B** needs someone happy reading browser-use internals.
- **C** suits someone fast with web templates who doesn't mind running long jobs at night.
- **D** needs the best presenter, who will also give the pitch.

## Handoffs: what to mock until the real thing lands

Nobody should be blocked on another person. Until a dependency is ready, work against a mock, and swap in the real thing at the time shown.

| Dependency | From → to | Ready by | Mock until then |
|---|---|---|---|
| Portal A with the eligibility flow | C → A, B | ~14:00 | A: a saved HTML copy of a simple form. B: record a Browser Use run on any simple page to learn the history format. |
| Audit-log schema | C → A, C's harness | **14:00 freeze** | The proposal in [architecture.md](architecture.md#audit-log-proposal-for-c) |
| Program YAML schema + example file | B → A, D | **14:30 freeze** | A hand-written `programs/eligibility-check/v1.yaml` that A and B draft together in the first hour |
| First compiled program from a real recording | B → A | 16:00 (gate) | The hand-written v1 |
| Event stream (`events.jsonl` + SSE) | A → D | sample by ~15:00 | A fake `runs/sample/events.jsonl` that D writes from the proposal in [architecture.md](architecture.md#event-stream-proposal-for-a) |
| System D adapter (run one program on one mutation, return the outcome) | A → C | 20:00 | C builds systems A (agent) and B (blind replay) first |
| CLI commands | B → everyone | 20:00 | Call the Python functions directly |
| Approval API | A + D | 23:00 (Wow v1) | The dashboard queue reads `stopped` events from the fake stream |
| Benchmark numbers | C → D | 07:30 | Placeholder "*k* of *N*" in the README and Devpost drafts |

## Checklists by person

### A: Runtime

- [ ] **12:30–14:00:**
  - Set up Playwright.
  - Build an executor skeleton that runs the hand-written v1 YAML and writes `events.jsonl`.
  - Write the first deterministic checks: `url_matches`, `element` (role + name + enabled), `text_visible`.
- [ ] **By 16:00 (gate):**
  - Replay the eligibility flow deterministically on portal A from the compiled program.
  - Healer v0 fixes mutation 3. The patch is dry-run against the same post-check, the version goes up, and the diff is stored.
- [ ] **By 20:00:**
  - Structural fingerprint check.
  - `on_fail` by risk: heal reads; stop and ask on write and irreversible steps.
  - Receipt check against the audit table.
  - Rollback.
  - The judge (cheap model), called only on write steps and on renamed-but-matching elements.
  - Hand C the system D adapter.
- [ ] **By 23:00:** with D, the approval API and SSE endpoint. Approving resumes the run, and a `stopped` event carries everything Slack needs.
- [ ] **By 02:00:** all ten mutations run through system D. Tune away false alarms on mutations 1, 2 and the control.
- [ ] **05:00–07:30:** fix only the top failure causes from the benchmark. No new features.

### B: Capture

- [ ] **12:30–14:00:**
  - Pin the browser-use version and smoke-test it with `ChatAnthropic(model="claude-opus-5-5", thinking={"type": "adaptive"})`. Without `thinking`, it fails with HTTP 400.
  - Confirm the history has element data and that a rerun method exists.
  - Draft v1 YAML with A.
- [ ] **By 14:30:**
  - **Freeze the program YAML schema** and commit the example file.
  - Save the first recording of the eligibility flow on portal A.
- [ ] **By 16:00 (gate):** the compiler (one LLM pass) turns the recording into a v1 that A's executor replays. It covers risk tags, intents, pre- and post-checks, receipt rules, and `$parameters`.
- [ ] **By 20:00:**
  - CLI: `record`, `compile`, `run`, `doctor`, `heal`, `rollback`, wrapping A's functions.
  - The two hand-authored branches: the consent banner (mutation 6) and the extra confirmation page (mutation 7).
- [ ] **By 02:00:** pair with C on the harness adapters for systems A (agent every run) and B (blind replay from the recorded selectors), since B knows the recordings best.
- [ ] **05:00–07:30:** with D, draft the README, including the run steps and the **reused-vs-new table**. Browser Use and Playwright are reused; everything else was written this weekend.

### C: Sites + benchmark

- [ ] **12:30–14:00:**
  - **Start a Devin session for the portal generator**, and another for the harness scaffold (proof for the Cognition track).
  - Build portal A (FastAPI + Jinja + SQLite) with the eight-step eligibility flow and synthetic patients.
  - **Freeze the audit-log schema at 14:00.**
  - Write `bench/mutations.md`: the ten mutations plus a "correct response" label for each. **Commit it before any run.**
- [ ] **By 16:00 (gate):**
  - The mutation switch (query param or header) with mutations 1, 3 and 9.
  - A reset script.
  - A `run_id` header recorded in audit rows.
- [ ] **By 20:00:**
  - `bench/run.py` with systems A and B producing JSONL rows.
  - Mutations 1, 3 and 9 in the harness.
  - Plug in A's system D adapter.
  - With D, add the Sentry browser SDK + Session Replay to the portals.
- [ ] **By 23:00:** with D, the split-screen setup: two portal instances on mutation 9, blind replay on the left, Browseen on the right.
- [ ] **By 02:00:**
  - All ten mutations, plus portals B and C from the generator.
  - Systems A–D end to end at a small trial count.
  - Set the dollar and step caps, then **start the overnight runs**.
- [ ] **05:00–07:30:**
  - Run the full benchmark under the cap.
  - `bench/report.py` produces the heatmap and the headline numbers.
  - Hand the numbers to D by 07:30.
- [ ] *Optional:* deploy the portals and runner to Vultr. The demo must not depend on it.

### D: Product + story

- [ ] **12:30–14:00:**
  - Create the Sentry project and share the DSN in `.env`.
  - Create the Slack incoming webhook.
  - Build the dashboard skeleton (React + Vite + Tailwind) reading the fake `events.jsonl`.
  - Write Maria's story card.
  - Talk to the Browser Use and Sentry staff.
- [ ] **By 16:00 (gate):**
  - The program view renders the YAML example: steps, intents, read/write tags, checks.
  - The executor's Sentry traces are visible.
- [ ] **By 20:00:**
  - Live counters (tokens, $, seconds) from the event stream.
  - A diff view with the **gold seam** on healed steps.
  - Sentry step attributes (`step.id`, `step.risk`, `guard.result`) and a Logs line per guard decision, added with A.
  - Session Replay on the portals, with C.
- [ ] **By 23:00:**
  - The approvals queue (intent, screenshot, diff, trace link, Approve / Reject).
  - The Slack alert, with a phone buzzing on the table.
  - The split-screen view.
- [ ] **By 02:00:** the break-it panel: pick a mutation, or "Surprise me".
- [ ] **05:00–07:30:**
  - With B, draft the README and Devpost.
  - Keep the **build log** of real Sentry moments for the Sentry write-up.
  - Record the 60-second backup capture.
- [ ] **09:00–10:30:** run three rehearsals, record the 2–3 minute video, and submit on Devpost (including the Commit Fellowship opt-in).

## The 4 pm gate

At **Sat 16:00**, all four of you meet for 5 minutes. The gate passes only if **one flow is recorded (B), compiled (B), replayed deterministically on portal A (A, C), and one severity-2 mutation is healed with a passing post-check (A)**.

- **Missed:** drop the Wow tier, the branches and the LLM judge, and keep the deterministic guards.
- **Still missed by 18:00:** switch to Agent Bisect (idea 3), per the build plan.

## Daily rhythm

- **Stand-up at every milestone** (14:00, 14:30, 16:00, 20:00, 23:00, 02:00, 05:00, 07:30), 5 minutes:
  - show the integrated state running on `main`;
  - check that we still have the identity sentence;
  - name what's being cut.
- **Wow-tier cut order**, from the build plan: Slack buttons, then the break-it panel, then split-screen polish. Wow is always cut before Core.
- **Never mock** the compile, guard or heal steps; only non-core pieces like the portals' data. Every teammate must be able to explain the core code.

## Sleep rota (proposal)

The build plan starts the rota at 02:00. Everyone must be awake for the 05:00 freeze, so the sleep happens in staggered shifts before it:

| Who | Sleeps | Why then |
|---|---|---|
| B | 22:00 → 01:30 | B's core work is done by 20:00. B is up to watch the overnight runs. |
| A, D | 02:00 → 05:00 | After Wow v1 and the 02:00 milestone. |
| C | 02:30 → 05:30 | After starting the overnight runs. B monitors them. |

Per the build plan, the person writing the Devpost page (D) is never the one running the benchmark (C).

## Git workflow

- **`main` stays runnable** at all times. Each person works on their own branch, named after the person or the area (for example `Peter`, `runtime`, `portals`), and merges into `main` at each milestone after a quick end-to-end run.
- **Folder ownership** (see the table at the top) keeps merge conflicts rare. Only the owner of an interface changes it, and posts the change in the team chat first.
- **Pull `main` before merging,** and never force-push `main`.

## If we're only three

From the build plan: C also takes D's Sentry work, and the break-it panel and Slack move to Stretch.
