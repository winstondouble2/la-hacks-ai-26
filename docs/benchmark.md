# Benchmark

What we measure, what we need to build to measure it, and which numbers we show at the demo. The working name is **DriftBench**: browser tasks on websites that change underneath the agent.

> **Why this matters for judging.** The criteria are Technical Depth, Product Thinking & Impact, Execution & Polish, and Originality & Insight. Replaying agent runs isn't new: Browser Use's `rerun_history()`, Workflow Use, taprun and LOOP all do it. The closest prior art, **PreAct**, even compiles runs into guarded programs, but when a check fails it hands the *rest of the task* back to the agent and recompiles everything. Our claim is that we **stay correct when the site changes** and **pay the LLM only for the step that broke**, then resume compiled replay. Only a benchmark on deliberately changed pages can show that.

## 1. The claims and the numbers behind them

| # | Claim | Headline number | Compared against |
|---|---|---|---|
| C1 | Compiled runs are much faster and cheaper | **×N faster, ×M cheaper per run** (median seconds, $ per run), plus the break-even run count | The Browser Use agent run from scratch every time |
| C2 | We survive page changes | **Verified success rate on changed pages** | Linear replay (`rerun_history()`) |
| C3 | Healing is cheap | **LLM calls and $ per heal** | One full agent run, and a PreAct-style takeover (the agent finishes the rest of the task) |
| C4 | A heal sticks | **LLM calls on the next run after a heal** (target: 0) | — |
| C5 | We don't fake success | **False-pass rate** (target: 0) and **correct-fail rate** on impossible changes | All systems |

For the demo slide, pick the strongest number from C1, C2 and C3. C5 answers "how do you know it actually worked?" in Q&A.

For context, prior numbers are thin:

- **LOOP Skill Engine:** its 93%–99.98% token savings are *modeled*, not measured, and 7.82 s → 0.90 s is from a single 3-step task.
- **PreAct:** reports 8.5–13× faster replay on AndroidWorld, OSWorld and WebArena.

We **measure end to end**. C1 should land in that range; C2–C5 are what nobody measures on changing websites.

## 2. Testbed sites

We benchmark **only on sites we control**: changes are deterministic, runs are repeatable, and nothing depends on venue Wi-Fi or a third party. Each site is small (3–6 pages) but has realistic markup: forms, tables, modals, pagination. They are built with FastAPI + Jinja templates + SQLite.

| Site | Pages | Exercises |
|---|---|---|
| **Shop** | home → search → product → cart → checkout → confirmation | search, select, quantity, form fill, multi-page flow |
| **Portal** | login → 3-page application form → review → submitted | login, long forms, dropdowns, dates, validation errors |
| **CRM** | login → customer table (paginated, filterable) → customer detail → edit | tables, pagination, extraction, editing a record |

Every site provides four test hooks. These are what make the numbers trustworthy:

- **`?mut=<ids>&seed=<n>`** (or a header) renders the changed version of the page. The same seed always gives the same page, and the dashboard's chaos panel uses the same IDs.
- **`POST /__reset`** restores the seed data before every run.
- **`GET /__verify?task=<id>&params=…`** is **server-side ground truth**: was the order really created with the right item and quantity, was the record really updated? Success is never judged from the agent's own claim or a screenshot.
- **The Sentry browser SDK with Session Replay**, tagged with the `run_id`, lets us replay any benchmark run, including the moment of a heal.

## 3. Tasks

Each task has a natural-language goal, typed parameters and a verifier. Each one has **2–3 parameter sets**: we record with set A and benchmark with set B, which also checks that parameters work.

| ID | Site | Goal (with parameters) | Steps | Verifier | Priority |
|---|---|---|---|---|---|
| T1 | Shop | Buy `{qty}` of `{product}`, checking out with `{name}` and `{address}` | ~10 | An order exists with the exact item, quantity and address | **core** (the demo task) |
| T2 | Portal | Log in and submit the application for `{applicant}` | ~15 | The submission record matches every field | **core** |
| T3 | CRM | Find customer `{name}` and set their status to `{status}` | ~7 | That row is updated and no other rows changed | **core** |
| T4 | CRM | Extract all invoices over `{amount}` (spans pages) | ~6 + loop | The extracted list equals the ground truth | **core** (tests loops) |
| T5 | Shop | Apply coupon `{code}` and report the final total | ~6 | The reported total equals the server's total | nice |
| T6 | Portal | Update the mailing address to `{address}` | ~6 | The profile row is updated | nice |
| T7 | Shop | Add the cheapest item in `{category}` to the wishlist | ~6 | The wishlist holds the right item | stretch |
| T8 | CRM | Export the report for `{month}` | ~5 | The export was requested for the right month | stretch |

Task definitions live in `bench/tasks/<id>.yaml`:

```yaml
id: T1
site: shop
goal: "Buy {qty} of '{product}' and check out with name {name} and address {address}"
start_url: http://localhost:8001/
params:
  record: { product: "Blue Mug", qty: 2, name: "Ada Lovelace", address: "1 Main St" }
  bench:  { product: "Red Kettle", qty: 1, name: "Alan Turing", address: "9 Elm Ave" }
verify: shop.order_exists
max_agent_steps: 30
timeout_s: 180
```

## 4. Mutations (page changes)

Each mutation is a deterministic change the testbed applies to a page. Severity runs from **L0**, no change, to **L4**, where the task has become impossible.

| ID | Level | Mutation | Example | Replay (our guess) | Browseen (expected tier) |
|---|---|---|---|---|---|
| M00 | L0 | none | — | pass | pass, 0 LLM calls |
| M01 | L1 | Selector churn | `id`s and classes randomized, `data-testid` removed | may survive (XPath / accessible-name re-match) | tier 1 |
| M02 | L1 | Wrapper insertion | extra `div`s around the target | XPath breaks; may survive by name | tier 1 |
| M03 | L1 | Sibling reorder | buttons or fields swap DOM order | XPath may hit the **wrong** element | tier 1, with the post-check catching mistakes |
| M04 | L2 | Text rename | "Add to cart" → "Add to bag" | may survive by XPath if the structure is unchanged | tier 1 fuzzy match or tier 2 |
| M05 | L2 | Label rename | "Full name" → "Your name" | may survive by XPath | tier 1 or 2 |
| M06 | L2 | Moved into a menu | the button is now inside a "⋯" dropdown | fail | tier 2 (inserts "open menu") |
| M07 | L2 | Field order shuffled | the form fields are reordered | wrong-field risk | tier 1 |
| M08 | L3 | Cookie banner | a banner covers the page on first load | fail (click blocked) | the optional-step branch, or tier 2 adds one |
| M09 | L3 | Popup | a newsletter modal appears after step 2 | fail | tier 2 (inserts "close popup") |
| M10 | L3 | New required field | checkout now needs a phone number | fail | tier 3 if the agent can fill it; otherwise the run must **fail loudly** |
| M11 | L3 | Flow split | one form page becomes two | fail | tier 3 |
| M12 | L3 | Pagination shift | the target item moves to page 2 | fail | tier 2 or 3 |
| M13 | L3 | Slow load | content renders after 2–4 s | flaky | the guard waits; 0 LLM calls |
| M14 | L3 | A/B variant | a different layout with the same function, chosen by seed | fail | tier 2, then **both variants kept as branches** |
| M15 | L4 | Impossible | the product is out of stock or the feature was removed | may **false-pass** | **must fail loudly** (correct-fail) |
| M16 | L4 | Wrong-target trap | a decoy button with the old label does something else | **false-pass risk** | the post-check catches it |

The "Replay" column is a guess; the benchmark decides. Browser Use's `rerun_history()` re-matches elements by hash, then XPath, then accessible name, so it will survive some L1 and L2 changes. Where it survives by XPath on a changed page, watch for **wrong-element clicks**: M03, M07 and M16 are designed to expose them.

The design rules for the mutation catalog:

- **Commit the list before the first benchmark run,** and cite that commit in the README.
- **Dev set vs. held-out set.** Split the mutations into a **dev set**, used while building the healer, and a **held-out set**, written by a teammate who didn't work on the healer and run only at the end. Report both.
- **Compound cases.** Also run 2–3 mutations at once (for example `M01+M04+M09`), because real redesigns change several things together.
- **Live judge mutation.** The chaos panel exposes the same IDs, so what a judge triggers live is a case from the benchmark.

## 5. Systems compared

| System | What it is | Why it's included |
|---|---|---|
| **Agent** | A plain Browser Use agent run from scratch every time, with the same model | The "LLM every time" cost and speed baseline |
| **Replay** | Browser Use's built-in `save_history()` + `load_and_rerun(path, variables=…)` | The honest linear-replay baseline. It is **not zero-LLM** (extract steps and a final summary call the model), so we count those tokens. |
| **Takeover** | Our compiled program, but any failed check hands the **rest of the task** to the full agent, and the new trace is recompiled | The PreAct-style recovery. Comparing it with **Browseen** isolates the value of step-local repair. |
| **Browseen-T1** | Guards plus tier 1 only, with **no LLM** | Ablation: how much do guards and locator fallbacks alone buy? |
| **Browseen-T2** | Tiers 1 and 2 | Ablation |
| **Browseen** | The full system: tiers 1–3 plus branches | The headline system |
| *(optional)* taprun | `taprun.forge(trajectory=history)` on the same recording | Time-box it to **1 hour**; otherwise just cite it. (Workflow Use is cite-only, because its agent fallback is commented out.) |

The ablations and the Takeover row earn the Technical Depth and Originality points: they show *where* the robustness comes from and *why* per-step repair beats handing the whole task back.

## 6. Metrics

Every run writes one JSON row, and every metric is computed from those rows.

| Metric | Definition |
|---|---|
| **Verified success** | `/__verify` is true **and** the system reported success |
| **False pass** | The system reported success but `/__verify` is false. This is the worst outcome. |
| **Correct fail** | On an L4 mutation, the system reported failure instead of success |
| **Wall time** | From starting the run to the final verdict (median and p90) |
| **LLM calls** | Number of model requests in the run |
| **Tokens and $** | Input, output and cache-read tokens × the pinned price table |
| **Heals** | For each heal: the step, tier, latency, tokens and $ |
| **Heal sticks** | On the *next* run against the same mutation, LLM calls = 0 |
| **Compile cost** | The one-time cost of the recording run plus the compiler's LLM pass. Reported separately and included in the break-even. |
| **Break-even run count** | Compile cost ÷ (Agent's $ per run − Browseen's $ per run) |

**One row per run** (*proposal*), written to `bench/results/<timestamp>.jsonl`:

```json
{"run_id": "r_0142", "task": "T1", "mutation": "M04", "seed": 3, "system": "browseen", "repeat": 2,
 "reported_success": true, "verified": true, "false_pass": false,
 "wall_s": 3.8, "llm_calls": 1, "input_tokens": 9120, "output_tokens": 410, "cache_read_tokens": 0,
 "usd": 0.045, "heals": [{"step": "s5", "tier": 2, "latency_s": 2.6, "usd": 0.045}],
 "program_version_before": 1, "program_version_after": 2,
 "model": "claude-opus-5-5", "git_sha": "…", "sentry_trace_id": "…"}
```

## 7. Protocol

1. **Record once.** For each task, record on M00 with param set A. That gives program v1, and its compile cost is logged.
2. **Isolated cells.** For each (task × mutation × system), start from a **fresh copy of v1**, so a heal can't leak into another cell. Run with param set B: reset the site, run, verify.
3. **Repeats.** Run every cell 3 times, because the agent and tier 2/3 are nondeterministic. With small N, **show counts like 3/3, not percentages**.
4. **Heal-sticks check.** After a cell where Browseen healed, run once more on the same mutation and confirm it makes 0 LLM calls.
5. **Drift scenario,** for the cost-over-time chart. Run T1 30 times while the site picks up a new mutation every ~5 runs (M00 → M01 → M04 → M09 → M14 → M06). The Agent pays every time; Browseen pays once to record and then a little at each heal.
6. **Fixed settings.** Use the same model and effort for Agent, Takeover and Browseen, a headless browser, a fixed viewport, local network and fixed timeouts. They all go in `bench/config.yaml` and are logged with every row.
   - **Model gotcha:** use `ChatAnthropic(model="claude-opus-5-5", thinking={"type": "adaptive"})` for Browser Use; without `thinking` it fails with HTTP 400. Smoke-test one Agent run before the matrix.
7. **Pinned prices.** $ comes from token counts × a price table in `bench/config.yaml` (Claude Opus 5.5: $4 input / $20 output per million tokens, $0.20 per million for cache reads), so every system is priced the same way.

## 8. Budget

Nearly all of the LLM spend comes from the **Agent** and **Takeover** systems and the recording runs. Replay is cheap, and Browseen is free unless it heals.

```
agent_cost ≈ tasks × mutations_run_for_agent × repeats × cost_per_agent_run
```

- **Measure `cost_per_agent_run` on T1 first.** Don't guess it.
- The Agent barely depends on the mutation, so run it on **M00 plus 4 representative mutations** (M04, M09, M14, M15) instead of the whole list.
- **Cache Agent results** by (task, mutation, seed, model, git sha), so re-running the report never pays for them again.
- Set a **hard budget cap** in the config (for example `budget_usd: 75`). Once it's reached, the runner stops starting new Agent or Takeover runs.

For example, the core set is 4 tasks × 5 mutations × 3 repeats = **60 Agent runs**. Replay and Browseen on all ~17 mutations plus the compound cases cost only the heals.

## 9. What to build

```
testbed/                     # C: shop/, portal/, crm/ (FastAPI + Jinja + SQLite)
  mutations.py               # mutation IDs → template changes; also used by the chaos panel
bench/
  config.yaml                # model, prices, timeouts, budget cap, repeats
  tasks/T1.yaml …            # task definitions (section 3)
  mutations.yaml             # catalog + dev / held-out split (section 4)
  systems.py                 # adapters: agent, replay, takeover, browseen-t1, browseen-t2, browseen
  run.py                     # matrix runner → results/*.jsonl
  report.py                  # results → tables, charts, dashboard JSON
  results/                   # final result files we commit for the write-up
```

Runner and report commands:

```bash
python -m bench.run --tasks T1,T2,T3,T4 --mutations dev --systems agent,replay,takeover,browseen-t1,browseen-t2,browseen --repeats 3
```

```bash
python -m bench.report bench/results/latest.jsonl --out bench/results/report
```

The runner must:

- **Be resumable.** It skips cells that already have rows, so a crash at 4 AM costs nothing.
- **Keep going.** An exception in one run becomes a failed row, and the matrix continues.
- **Trace everything.** Each run is a Sentry trace tagged `task`, `mutation` and `system`, so a slow or broken cell opens straight in Sentry.

## 10. What we show

| Output | Chart | Used in |
|---|---|---|
| Headline numbers | Three big numbers, one each from C1, C2 and C3 | Demo slide, Devpost, README |
| Success under change | Grouped bars: verified success by severity level (L0–L4) × system | Demo, Devpost |
| Cost and speed per run | Bars on a log scale: Agent run vs. compiled run vs. compiled run with a heal | Demo |
| **Cost over time** | Line chart: cumulative $ over 30 runs while the site changes. Agent climbs steadily; Browseen is a step at recording plus small bumps at heals. Mark the break-even run. | **Demo centerpiece** |
| Where robustness comes from | Ablation table: Browseen-T1 / T2 / full × success | Q&A, Devpost |
| Per-step repair vs. takeover | Bars: LLM calls, $ and seconds per recovery, Browseen vs. Takeover | Q&A: "how is this different from PreAct?" |
| Honesty | False-pass and correct-fail rates for every system; held-out vs. dev success | Q&A |

The dashboard's live counters (tokens, $, seconds, LLM calls) use the same definitions as these charts, so the live demo and the charts agree.

## 11. Threats to validity (say them before judges do)

- **We built the testbed.** The held-out mutations were written by someone who didn't build the healer, the mutation list is committed before the first run, judges pick mutations live, and we report every cell, including the failures.
- **Small N.** A few tasks with 3 repeats each. We present this as evidence, not a paper.
- **LLM nondeterminism.** We run repeats and show counts.
- **Synthetic sites.** The markup patterns are realistic but it isn't the real web. Optionally, a no-mutation sanity run on 1–2 public read-only sites shows cost and latency there (respecting their terms, and no CAPTCHAs).
- **Prices change.** We publish token counts as well as dollars.

## 12. If we're short on time

Cut to the minimum viable benchmark: **T1 and T3; mutations M00, M01, M04, M09, M14 and M15; systems Agent, Replay, Takeover and Browseen; 3 repeats.** That still supports C1, C2, C3 and C5.
