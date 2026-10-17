# Benchmark

What we measure, what we need to build to measure it, and which numbers we show at the demo. Working name: **DriftBench**, a benchmark of browser tasks on websites that change underneath the agent.

> **Why this matters for judging.** The criteria are Technical Depth, Product Thinking & Impact, Execution & Polish, and Originality & Insight. Prior art already replays agent runs: LOOP, taprun, `workflow-use`, and Browser Use's own `rerun_history()`. The closest prior art, **PreAct** ([arXiv 2606.17929](https://arxiv.org/abs/2606.17929)), even compiles runs into guarded state machines. When a guard fails, though, PreAct hands the *rest of the task* back to the agent and recompiles the whole program. Our claim is that we **stay correct when the site changes** and **pay the LLM only for the step that broke**, then resume compiled replay. Only a benchmark on deliberately modified pages can show that.

## 1. The claims and the numbers behind them

| # | Claim | Headline number | Compared against |
|---|---|---|---|
| C1 | Compiled runs are much faster and cheaper | **×N faster, ×M cheaper per run** (median seconds, $ per run) | The Browser Use agent running from scratch every time |
| C2 | We survive page changes | **Verified success rate on modified pages** (e.g. "92% vs. 31%") | Linear replay (`rerun_history()`, LOOP-style) |
| C3 | Healing is cheap | **LLM calls and $ per heal** vs. one full agent run | The agent re-running the whole task, and a PreAct-style takeover (the agent finishes the rest of the task) |
| C4 | A heal persists | **LLM calls on the next run after a heal** (target: 0) | — |
| C5 | We don't fake success | **False-pass rate** (target: 0%) and **correct-fail rate** on impossible changes | All systems |

For the demo slide, pick the strongest one from each of C1, C2 and C3. C5 is the answer to "how do you know it actually worked?" in Q&A.

For context, prior numbers are thin:

- **LOOP Skill Engine:** its 93%–99.98% token savings are *modeled*, not measured, and its 7.82 s → 0.90 s figure comes from a single 3-step task.
- **PreAct:** reports 8.5–13× faster replay, measured on AndroidWorld, OSWorld and WebArena.

We **measure end to end**: C1 should land in that range, and C2–C5 are what neither paper measures on changing websites.

## 2. Testbed sites (what we build)

We benchmark **only on sites we control**, so that mutations are deterministic, runs are repeatable, and nothing depends on venue Wi-Fi or a third party. Each site is small (3–6 pages) with realistic markup: forms, tables, modals, pagination.

| Site | Pages | Exercises |
|---|---|---|
| **Shop** | home → search → product → cart → checkout → confirmation | search, select, quantity, form fill, multi-page flow |
| **Portal** | login → 3-page application form → review → submitted | login, long forms, dropdowns, date fields, validation errors |
| **CRM** | login → customer table (paginated, filterable) → customer detail → edit | tables, pagination, extraction, editing a record |

Every site must provide four test hooks. These are what make the numbers trustworthy:

- **`?mut=<ids>&seed=<n>`** (or a server-side setting) renders the mutated variant. The same seed always produces the same page.
- **`POST /__reset`** restores the seed data before every run, so runs are independent.
- **`GET /__verify?task=<id>&params=...`** gives **server-side ground truth**: was the order created with the right item and quantity, was the record actually updated? Success is never judged from the agent's own claim or a screenshot.
- **The Sentry browser SDK with Session Replay**, tagged with the `run_id`, lets us replay any benchmark run, including the moment of a heal. This also counts toward the Sentry track.

## 3. Tasks

Each task has a natural-language goal, typed parameters, and a verifier. Every task has **2–3 parameter sets**. We record with set A and benchmark with set B, which also checks that parameterization works.

| ID | Site | Goal (with parameters) | Steps | Verifier | Priority |
|---|---|---|---|---|---|
| T1 | Shop | Buy `{qty}` of `{product}` and check out with `{name}`, `{address}` | ~10 | An order exists with the exact item, quantity and address | **core** |
| T2 | Portal | Log in and submit the permit application for `{applicant}` | ~15 | The submission record matches every field | **core** |
| T3 | CRM | Find customer `{name}` and set their status to `{status}` | ~7 | The DB row is updated; no other rows changed | **core** |
| T4 | CRM | Extract all invoices over `{amount}` (spans pages) | ~6 + loop | The extracted list equals the ground truth | **core** (tests loops) |
| T5 | Shop | Apply coupon `{code}` and report the final total | ~6 | The reported total equals the server total | nice |
| T6 | Portal | Update the mailing address to `{address}` | ~6 | The profile row is updated | nice |
| T7 | Shop | Add the cheapest item in `{category}` to the wishlist | ~6 | The wishlist holds the right item | stretch (data-dependent choice) |
| T8 | CRM | Export the report for `{month}` | ~5 | The export request was made with the right month | stretch |

Task definitions live in `bench/tasks/<id>.yaml`:

```yaml
id: T1
site: shop
goal: "Buy {qty} of '{product}' and check out with name {name} and address {address}"
start_url: http://localhost:3001/
params:
  record: { product: "Blue Mug", qty: 2, name: "Ada Lovelace", address: "1 Main St" }
  bench:  { product: "Red Kettle", qty: 1, name: "Alan Turing", address: "9 Elm Ave" }
verify: shop.order_exists
max_agent_steps: 30
timeout_s: 180
```

## 4. Mutations

A mutation is a deterministic change the testbed applies to a page. Mutations are grouped by **severity level**: L0 means no change, L4 means the task has become impossible.

| ID | Level | Mutation | Example | Replay (our guess) | Ours (expected tier) |
|---|---|---|---|---|---|
| M00 | L0 | none | — | pass | pass, 0 LLM calls |
| M01 | L1 | Selector churn | all `id`s/classes randomized, `data-testid` removed | may survive (XPath / accessible-name re-match) | tier 1 (role/text locator) |
| M02 | L1 | Wrapper insertion | extra `div`s / a shadow root around the target | XPath breaks; may survive by name | tier 1 |
| M03 | L1 | Sibling reorder | buttons or fields swap DOM order | XPath may hit the **wrong** element | tier 1 + postcondition |
| M04 | L2 | Text rename | "Add to cart" → "Add to bag" | may survive by XPath if the structure is unchanged | tier 1 fuzzy match or tier 2 |
| M05 | L2 | Label rename | "Full name" → "Your name" | may survive by XPath | tier 1 or tier 2 |
| M06 | L2 | Moved into a menu | the button is now inside a "⋯" dropdown | fail | tier 2 (insert "open menu") |
| M07 | L2 | Field order shuffled | the form fields are reordered | wrong-field risk | tier 1 |
| M08 | L3 | Cookie banner | a banner covers the page on first load | fail (click blocked) | an `if` branch, or tier 2 adds one |
| M09 | L3 | Interstitial modal | a newsletter popup appears after step 2 | fail | tier 2 (insert "close modal") |
| M10 | L3 | New required field | checkout now needs a phone number | fail | tier 2/3; the phone number must be a parameter or the run fails loudly |
| M11 | L3 | Flow split | one form page becomes two | fail | tier 3 |
| M12 | L3 | Pagination shift | the target item moves to page 2 | fail | a loop branch, or tier 2 |
| M13 | L3 | Slow / lazy load | content renders after 2–4 s | flaky | the guard waits; 0 LLM calls |
| M14 | L3 | A/B variant | a different layout with the same function, chosen by seed | fail | tier 2, then **both variants kept as branches** |
| M15 | L4 | Impossible | the product is out of stock or the feature was removed | may **false-pass** | **must fail loudly** (correct-fail) |
| M16 | L4 | Wrong-target trap | a decoy button with the old label does something else | **false-pass risk** | the postcondition catches it |

The "Replay" column is a guess, not a result; the benchmark decides. Browser Use's `rerun_history()` re-matches elements by exact hash, then stable hash, then XPath, then accessible name, then a unique attribute, so it will survive some L1/L2 changes. Where it survives by XPath on a changed page, watch for **wrong-element clicks**. That is exactly what M03, M07 and M16 are designed to expose.

The design rules for the mutation catalog:

- **Compound cases.** Also run 2–3 mutations at once (e.g. `M01+M04+M09`). Real redesigns change many things together.
- **Dev set vs. held-out set.** This is the most important credibility rule. Split the mutations into a **dev set**, used while building the healer, and a **held-out set**, written by a teammate who did not work on the healer and run only at the end. Report both. If the held-out numbers are close to the dev numbers, we can claim the healer generalizes.
- **Live judge mutation.** The chaos panel in the demo exposes the same mutation IDs, so what the judge triggers live is a case from the benchmark.

## 5. Systems compared

| System | What it is | Why it's included |
|---|---|---|
| **Agent** | A plain Browser Use agent run from scratch on every run, with the same model | The "LLM every time" cost and speed baseline |
| **Replay** | Browser Use's built-in `save_history()` + `load_and_rerun(path, variables=...)` on the recorded run | An honest linear-replay baseline using the official tool, the same idea as LOOP. It is **not zero-LLM**: it re-runs `extract` steps with an LLM and always writes a final summary, so we count those tokens. |
| **Takeover** | Our compiled program, but on a guard failure the full agent finishes the **rest of the task** from the live page, and the new trace is recompiled | The **PreAct-style** recovery strategy. Comparing it with **Ours** isolates the value of per-step repair, which is our main claim against the closest prior art. |
| **Ours-T1** | Compiled program with guards + locator fallback + fuzzy match, **no LLM** | Ablation: how much do guards alone buy? |
| **Ours-T2** | + tier-2 single-step LLM patch | Ablation |
| **Ours** | Full system: tiers 1–3 + branches | The headline system |
| *(optional)* taprun | `taprun.forge(trajectory=history)` compiles the same Browser Use history into a replay plan | Cheap to try because it takes our recording directly. Time-box it to **1 hour**; otherwise cite it. (`workflow-use` is cite-only: its agent fallback is commented out in the source.) |

The ablation rows and the Takeover row are what earn Technical Depth and Originality points: they show *where* the robustness comes from and *why* per-step repair beats handing the rest of the task back.

## 6. Metrics

Every run writes one JSON row. All metrics are computed from those rows.

| Metric | Definition |
|---|---|
| **Verified success** | `/__verify` returns true **and** the system reported success |
| **False pass** | The system reported success but `/__verify` returns false (the wrong item ordered, or nothing submitted). The worst outcome. |
| **Correct fail** | On L4 mutations, the system aborted with an error instead of claiming success |
| **Wall time** | From starting the run to the final verdict (median and p90) |
| **LLM calls** | Number of model requests during the run |
| **Tokens / $** | Input, output and cache-read tokens × the pinned price table → $ per run |
| **Heals** | For each heal: step id, tier, latency, tokens, $ |
| **Persisted heal** | On the *next* run against the same mutation, LLM calls = 0 |
| **One-time compile cost** | Cost of the recording run plus compiler LLM calls. Reported separately and included in the amortized charts. |

The result row schema, written to `bench/results/<timestamp>.jsonl`:

```json
{
  "run_id": "r_0142", "task": "T1", "mutation": "M04", "seed": 3, "system": "ours", "repeat": 2,
  "reported_success": true, "verified": true, "false_pass": false,
  "wall_s": 3.8, "llm_calls": 1, "input_tokens": 9120, "output_tokens": 410, "cache_read_tokens": 0,
  "cost_usd": 0.045,
  "heals": [{ "step": "s5", "tier": 2, "latency_s": 2.6, "cost_usd": 0.045 }],
  "program_version_before": 1, "program_version_after": 2,
  "model": "claude-opus-5-5", "git_sha": "abc1234", "sentry_trace_id": "…"
}
```

## 7. Protocol

1. **Record.** For each task, record once on M00 with param set A. That produces program v1, and its one-time compile cost is logged.
2. **Isolated runs.** For each (task × mutation × system), start from a **fresh copy of v1**, so heals from one mutation can't leak into another cell. Run with param set B, reset the site, then verify.
3. **Repeats.** Run each cell 3 times, because the agent and tier-2/3 heals are non-deterministic. Report the mean, and the min–max where it is noisy.
4. **Persistence check.** After a cell where ours healed, run once more on the same mutation and confirm the run makes 0 LLM calls (C4).
5. **Drift scenario.** For the amortized-cost chart, run one task 30 times while the site picks up a new mutation every ~5 runs (M00 → M01 → M04 → M09 → M14 → M06). Agent re-runs everything each time; ours records once and then heals occasionally. Plot cumulative $ and time.
6. **Fixed settings.** Use the same model and effort for the agent baseline, the takeover and the healer, plus a headless browser, a fixed viewport, local network, and fixed timeouts. All of these go in `bench/config.yaml` and are logged in each row.
   - **Model gotcha.** Browser Use's `ChatAnthropic` forces `tool_choice` unless thinking is set, and Claude Opus 5.5 / Sonnet 5.5 reject forced tool choice with HTTP 400. Construct it as `ChatAnthropic(model="claude-opus-5-5", thinking={"type": "adaptive"})` and don't set `temperature`/`top_p`/`seed`. Smoke-test one agent run before starting the matrix.
7. **Pinned prices.** The $ figures come from a price table in `bench/config.yaml` (for example, Claude Opus 5.5 at $4 / $20 per MTok input/output and $0.20 per MTok for cache reads). We compute $ from token counts so that every system is priced the same way.

## 8. Budget

LLM spend comes almost entirely from the **Agent** system and the recording runs. Replay and ours are nearly free when no heal happens.

```
agent_cost ≈ tasks × mutations_run_for_agent × repeats × cost_per_agent_run
```

- **Measure `cost_per_agent_run` first** on T1, before sizing anything. Don't guess.
- The agent baseline barely depends on mutations, so run it on **M00 plus 4 representative mutations** (M04, M09, M14, M15) instead of the whole catalog.
- **Cache agent results** by (task, mutation, seed, model, git sha), so re-running the report never re-pays for them.
- Set a **hard budget cap** in config (e.g. `budget_usd: 75`). The runner stops starting new agent runs once it's reached.

Example size for the core set: 4 tasks × 5 mutations × 3 repeats = **60 agent runs**. Everything else (replay and ours on all ~17 mutations plus compound cases) costs only the heals.

## 9. What to build

Folder layout, matching the gitignored output paths in `.gitignore`:

```
testbed/                     # demo + benchmark sites (shop, portal, crm)
  ...                        # each site implements ?mut=, /__reset, /__verify, Sentry Replay
bench/
  config.yaml                # model, effort, prices, timeouts, budget cap, repeats
  tasks/T1.yaml ...          # task definitions (section 3)
  mutations.yaml             # mutation catalog + dev / held-out split (section 4)
  systems.py                 # adapters: agent, replay, takeover, ours-t1, ours-t2, ours
  run.py                     # matrix runner → results/*.jsonl (resumable, cached, budget-capped)
  report.py                  # results → markdown tables, charts, dashboard JSON
  results/                   # final result files we commit for the writeup
```

Runner CLI:

```bash
python -m bench.run --tasks T1,T2,T3,T4 --mutations dev --systems agent,replay,takeover,ours-t1,ours-t2,ours --repeats 3
```

```bash
python -m bench.report bench/results/latest.jsonl --out bench/results/report
```

The runner must:

- **Be resumable.** It skips cells that already have rows, so a crash at 4 AM costs nothing.
- **Fail fast.** An exception in one run is logged as a failed row, and the matrix keeps going.
- **Trace everything.** Each run is a Sentry trace tagged `task`, `mutation`, `system`, so a slow or broken cell can be opened in Sentry.

## 10. Outputs: what we show

| Output | Chart | Used in |
|---|---|---|
| Headline numbers | 3 big numbers (C1, C2, C3) | Demo slide, Devpost, README |
| Success under change | Grouped bars: success rate by severity level (L0–L4) × system | Demo, Devpost |
| Cost and speed per run | Bars on a log scale: agent run vs. compiled run vs. compiled run with a heal | Demo |
| **Drift over time** | Line chart: cumulative $ over 30 runs while the site changes. The agent's line climbs steadily; ours is a step at recording plus small bumps at heals. Mark the break-even run. | **Demo centerpiece** |
| Where robustness comes from | Table of the ablations (Ours-T1 / T2 / full) × success | Q&A, Devpost (technical depth) |
| Per-step repair vs. takeover | Bars: LLM calls, $ and seconds per recovery for Ours vs. Takeover (PreAct-style) | Q&A answer to "how is this different from PreAct?" |
| Honesty | False-pass and correct-fail rates for every system | Q&A |
| Held-out vs. dev | Success on held-out vs. dev mutations | Q&A, Devpost |

The dashboard's live counters (tokens, $, seconds, LLM calls) use the same metric definitions, so the live demo and the charts agree.

## 11. Threats to validity (say these before judges do)

- **We built the testbed.** The held-out mutations from a teammate who didn't write the healer, plus live judge mutations, address this.
- **Small N.** A few tasks and 3 repeats. We present the results as evidence, not as a paper.
- **LLM non-determinism.** We use repeats and report min–max.
- **Synthetic sites.** These are realistic markup patterns, not the real web. Optionally, add a no-mutation sanity run on 1–2 public sites to show cost and latency there. Respect their terms, and no CAPTCHAs.
- **Prices change.** We publish token counts as well as $.

## 12. Milestones (hacking ends Sun Oct 18, 12:00 PM PDT)

| By | Benchmark milestone |
|---|---|
| Sat ~6 PM | Shop site with `?mut=`, `/__reset`, `/__verify`; T1 defined; mutations M01, M04, M09 working |
| Sat ~10 PM | `bench.run` runs Replay and Ours-T1 on T1 × dev mutations; first JSONL rows |
| Sun ~2 AM | All 4 core tasks; Agent baseline measured; tier-2 heals in the matrix |
| Sun ~5 AM | Held-out mutations written (by a non-healer teammate); full core run; drift scenario |
| Sun ~8 AM | `bench.report` charts frozen; numbers copied into README and Devpost |
| Sun 12 PM | **Hard stop.** No code after 12 PM, and the Devpost video uses these numbers. |

**If we fall behind, cut to the minimum viable benchmark:** T1 + T3, mutations M00/M01/M04/M09/M14/M15, systems Agent / Replay / Takeover / Ours, 3 repeats. That is still enough for C1, C2, C3 and C5. Takeover is cheap to keep because it reuses our runtime plus the agent.
