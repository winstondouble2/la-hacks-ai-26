# Browseen dashboard

React 19 + Vite 8 + Tailwind 4. Shows runs, the compiled program, repairs between versions, page-change controls, benchmark results and what Sentry saw. Owner: D.

```bash
cd dashboard
npm install
npm run dev        # http://localhost:5173
npm test           # logic tests (Node's built-in runner)
npm run build      # type-check + production build
npm run lint
```

## Mock and real mode

| | Mock (default) | Real |
|---|---|---|
| Set | nothing | `VITE_API_MODE=real` (see `.env.example`) |
| Runs | `runs/sample*/events.jsonl`, replayed at their recorded speed | A's API; live updates over SSE |
| Programs | `programs/<name>/v*.yaml` | `GET /programs/{name}/versions` |
| Chaos, approvals, benchmark | fixtures in `src/fixtures.ts` | the endpoints in [API_CONTRACT.md](API_CONTRACT.md) |

Mock mode needs neither the Python runtime nor the testbed, and shows a red **SAMPLE DATA** banner on every page. Real mode shows errors instead of falling back to mock data. The connection state (mock data / connecting / live / reconnecting / disconnected) is in the address bar.

`?run=<id>` picks the run, `?baseline=<id>` the agent run to compare with, `?view=<tab>` the tab.

## Tabs

| Tab | Shows | Data today |
|---|---|---|
| Overview | runs, reported success (verified needs `/__verify`), guard failures, heals by tier, approvals, LLM spend | sample runs |
| Events | every event of the current run | sample run |
| Side by side | the agent's first run against the compiled replay on one clock; time, tokens, LLM calls and LLM cost saved | sample runs |
| Program | each step's intent, action, locators, checks and status; *Guard details* splits locator / pre-check / action / post-check / receipt; healed steps get the gold seam | B's `programs/buy-item` (v2 is an example) |
| Diff | changed steps between versions, tier, reason, before/after, verification; rollback (append-only, like `program.py`) | same; mock rollback lives in the browser only |
| Chaos | C's mutations (M00–M16) with toggles, reset, surprise me, run | catalog from docs/benchmark.md; mock mode starts no run |
| Approvals | blocked writes with approve / reject | one synthetic request (the architecture currently has no approvals) |
| Benchmark | verified success, false passes, latency, cost, false passes by mutation, heals by tier; import `.jsonl` | synthetic rows until C's results exist |
| Observability | guard failures, heals, tier-3 takeovers, slowest steps, Sentry links | sample runs; links only for traces that exist |

## Sample data

`python runs/sample/make_samples.py` rewrites the sample runs (`runs/sample*`): a compiled run that heals at tier 2, the agent baseline, tier 1 and tier 3 heals, and a write blocked before it runs. Costs use the `claude-opus-5-5` prices from `browseen/costs.py`.

## Files

- `src/api.ts`: the only data layer (mock vs real).
- `src/events.ts`, `src/programs.ts`: event and program formats (A's and B's).
- `src/replay.ts`: replay clock, totals, comparisons, run summaries. `src/benchmark.ts`, `src/mockState.ts`: pure logic.
- `src/fixtures.ts`: everything synthetic, in one place.
- `tests/logic.test.ts`: the tests.
