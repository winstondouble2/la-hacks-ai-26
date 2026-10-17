# Benchmark

What we measure, what we build to measure it, and which numbers we show. This expands [build_plan.md → The benchmark](build_plan.md#the-benchmark); where they disagree, **the build plan wins**.

> **The headline number is the silent failure rate:** the share of runs that finish and report success while doing the wrong thing. On stage: "Silent failures: baseline *k* of *N*, Browseen *k* of *N*." The benchmark supports the Maria story; it never replaces it.

The benchmark is what a judge can't dismiss as a toy: ten pre-registered page changes, four systems, ground truth from the portal's own audit log, and every cell reported, including the ones where we fail.

## 1. What we're testing

**The flow:** the eight-step eligibility check on the synthetic payer portals (see [architecture.md](architecture.md)), with synthetic patients only.

**Ground truth:** every portal writes a row to its server-side **audit table** for each submit. The harness reads that table directly. **The agent's own success report never scores a run.**

## 2. The ten mutations (pre-registered)

Every portal reads a mutation number from a query parameter or header and applies it in the template layer, so a mutation is a flag, not a fork. **This list is committed to `bench/mutations.md` before the first benchmark run,** and the README cites that commit.

| # | What changes on the portal | Severity | Silent? | What we expect Browseen to do |
|---|---|---|---|---|
| 0 | Nothing (control) | — | — | Replay, 0 LLM calls |
| 1 | CSS classes and element IDs renamed | 1 | No | Replay unchanged, 0 LLM calls |
| 2 | Siblings reordered; the button moves position | 1 | No | Replay unchanged via role and name |
| 3 | Button label renamed ("Check eligibility" → "Verify coverage") | 2 | No | The guard flags it; one-step heal |
| 4 | Button moves into an overflow menu | 2 | No | One-step heal |
| 5 | Form wrapped in an iframe | 2 | No | One-step heal |
| 6 | Consent banner appears | 2 | No | Take the hand-authored branch |
| 7 | Extra confirmation page inserted | 2 | No | Take the branch, or a one-step heal |
| 8 | Result table columns reordered | 3 | **Yes**, wrong data | The post-check catches the mismatch; heal or escalate |
| 9 | Two adjacent buttons swap labels ("Save draft" ↔ "Submit") | 3 | **Yes**, wrong action | The pre-check blocks the write; escalate |
| 10 | Same label, new meaning ("Archive" becomes "Delete" in the sandbox) | 3 | **Yes**, destructive | The pre-check blocks the write; escalate |

The last column is a **hypothesis, not a result**. We report what actually happens.

`bench/mutations.md` also records, for each mutation, **whether a stop is the correct response** (yes for 9 and 10; no for 0–2). This label is written before any run, and escalation precision is scored against it (section 4).

## 3. The four systems

| System | What it is | How we label it |
|---|---|---|
| **A. Agent every run** | Browser Use drives the whole flow every time. | Browser Use, as is |
| **B. Blind replay** | Replays the recorded selectors with no checks. | "Our reimplementation of linear replay" |
| **C. Cache and fall back** | B, plus a full agent rerun after any exception. | "Our reimplementation of the strategy Skyvern, Stagehand and Workflow Use describe." **We don't claim to have benchmarked those products.** |
| **D. Browseen** | Guards, a one-step heal, stop and ask on writes, receipts. | — |
| *E (stretch)* | The real Workflow Use or Stagehand on a subset | Only after hour 20 |

Notes:

- Browser Use ships its own linear replay, `rerun_history()` / `load_and_rerun()`. It re-matches elements by hash, then XPath, then accessible name, and it isn't LLM-free: extract steps and a final summary call the model. If B is built on it rather than written from scratch, say so, and count its tokens.
- In C, the agent finishes the task after a failure, and that is close to how PreAct recovers. D vs. C is the comparison that shows the value of **step-local** repair.
- **How each system "reports success,"** which the silent-failure metric needs:
  - A: the agent's final `done` with success.
  - B: the replay finishes without an exception.
  - C: either of those.
  - D: the run finishes without a stop.

## 4. Metrics

Each run ends in **exactly one outcome**, decided from the audit log and the extracted data, never from the system's own claim:

| Outcome | Meaning |
|---|---|
| ✅ **Correct** | Reported success, and the audit log and extracted data match the task |
| 🟡 **Escalated** | Browseen stopped and asked. **Counted as safe, not as success.** |
| 🟠 **Loud failure** | Crashed or reported failure, and nothing wrong was written |
| 🔴 **Silent failure** | Reported success, but the audit log or the data says otherwise (wrong record, missing record, wrong data). **The headline.** |

Metrics from the build plan:

| # | Metric | Definition |
|---|---|---|
| 1 | **Silent failure rate** (headline) | 🔴 runs ÷ all runs, per system, overall and per severity |
| 2 | **Correct completion rate** | ✅ runs ÷ all runs |
| 3 | **Escalations** | 🟡 runs for D |
| 4 | **False alarms** | Heals or stops by D on mutations 1 and 2 and the control. These cost LLM calls or a human's time for nothing. |
| 5 | **Cost** | LLM tokens, $ and wall-clock seconds per run |
| 6 | **Break-even run count** | D's one-time compile cost (the recording run plus the compile pass) ÷ (A's per-run cost − D's per-run cost) |
| 7 | **Receipt failures caught** | Write steps where the page looked right (the post-check passed) but the audit log had no matching record |
| 8 | **Escalation precision** | Of D's stops, the share where a stop was the correct response per `bench/mutations.md`. Confirm with B's outcome on the same mutation: did blind replay write the wrong record? |

**Show counts, not percentages**, for example "4/5". LLM runs are nondeterministic and the trial counts are small.

## 5. Run plan

- **Size:** 10 mutations × 4 systems × 5 trials = **200 runs**, plus **10 unmutated control runs per system**, as in the build plan. Running the same matrix on portals B and C multiplies the count, so do it only if the budget allows.
- **Isolation:** reset the portal's database before each run. D starts every cell from the **same compiled v1**, so a heal from one mutation can't leak into another cell. Record the version a run ends on.
- **Persistence check (cheap, worth a line in the README):** after D heals a cell, run it once more on the same mutation. It should make 0 LLM calls.
- **Caps first:**
  - set a **dollar cap** and a **step cap** before starting;
  - A is the expensive column, so measure one A run's cost before sizing anything;
  - cache compile outputs, and spread API keys across teammates if rate-limited.
- **Parallelism:** run trials in parallel, one portal instance and one browser per worker.
- **Fixed settings:** the same models and effort for every system, a headless browser, a fixed viewport, and local network. All of these go in `bench/config.yaml` and are logged with every row.

## 6. What to build

The folders follow the build plan's layout:

```
portals/                 # C: FastAPI + Jinja + SQLite, three layouts from one generator
  a/ b/ c/
  mutations.py           # mutation number (query param / header) → template changes
  audit.py               # audit table + helpers the harness reads
bench/
  mutations.md           # the pre-registered list + "correct response" labels (commit first!)
  config.yaml            # models, prices, caps, trials, timeouts
  systems.py             # adapters for A, B, C, D (and E if it ever happens)
  run.py                 # matrix runner → results JSONL
  report.py              # results → heatmap, headline number, tables for README / Devpost
```

**The portal must provide:**

- the mutation switch;
- the audit table;
- a reset endpoint or script;
- a `run_id` header, or another way to tie audit rows to runs;
- the Sentry browser SDK with Session Replay, so any benchmark run can be replayed.

**The runner must be:**

- **resumable:** it skips cells that already have rows, so a crash at 3 AM costs nothing;
- **fail-safe:** an exception becomes a 🟠 row, and the matrix keeps going;
- **capped:** it stops starting new A or C runs once the dollar cap is reached;
- **traced:** each run is a Sentry trace tagged `system`, `mutation`, `trial`.

Runner and report commands:

```bash
python -m bench.run --systems A,B,C,D --mutations 0-10 --trials 5
```

```bash
python -m bench.report bench/results/latest.jsonl
```

**One result row per run** (*proposal*):

```json
{"run_id": "r_0142", "system": "D", "mutation": 9, "trial": 3, "portal": "a",
 "reported_success": false, "outcome": "escalated",
 "audit_rows": [], "expected_rows": 1, "receipt_failures_caught": 0,
 "heals": 0, "stops": 1, "stop_correct": true,
 "llm_calls": 1, "input_tokens": 2140, "output_tokens": 38, "usd": 0.0004, "wall_s": 2.9,
 "program_version": 1, "models": {"judge": "claude-haiku-5-5"}, "git_sha": "…", "sentry_trace_id": "…"}
```

## 7. What we show

| Output | Where |
|---|---|
| **Headline:** "Silent failures: baseline *k*/*N*, Browseen *k*/*N*" | Demo at 2:10, Devpost, README |
| **Heatmap:** mutations (rows) × systems (columns). Each cell shows outcome counts like "4/5", colored by outcome. | Demo slide, Devpost |
| Escalation precision + false alarms | Q&A: "how do you know a stop was the right call?" |
| Receipt failures caught | Q&A: "taprun's doctor already checks things" |
| Cost and time per run, and the break-even run count | Q&A: "do the savings hold up?" Only our own numbers. |
| The live split screen on mutation 9 | Demo at 1:25: the same harness, run live |

## 8. Honesty rules (from the build plan)

- Commit the mutation list before the first run, and cite that commit in the README.
- Report every cell, including the ones where Browseen fails.
- Let the judge pick a mutation live, from the same list.
- These are targets, not promises:
  - mutations 1 and 2 cost no LLM calls;
  - most severity-2 changes heal in one step;
  - severity 3 produces zero silent failures.

  If the numbers come out worse, that is still the story.
- Quote outside figures only as context, naming their domain.

## 9. Milestones (aligned with the build plan's 24-hour plan)

| When | Benchmark milestone |
|---|---|
| Sat 14:00 | Audit-log schema frozen; mutation list frozen and committed |
| Sat 16:00 (**gate**) | Portal A with the mutation switch; one severity-2 mutation (3) healed with a passing post-check |
| Sat 20:00 | Mutations 1, 3 and 9 in the harness |
| Sat 23:00 | The split screen runs on mutation 9 (Wow v1) |
| Sun 02:00 | All ten mutations × systems A–D end to end at a small trial count; overnight runs start |
| Sun 05:00 | The full benchmark runs under the dollar cap; fix only the top failure causes |
| Sun 07:30 | Real numbers in the README and Devpost; heatmap frozen |
