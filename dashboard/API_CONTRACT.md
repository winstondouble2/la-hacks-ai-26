# Dashboard API contract (proposal)

What the dashboard calls in real mode (`VITE_API_MODE=real`), all relative to `VITE_API_BASE_URL` (default `http://localhost:8000`). **None of these endpoints exist yet**: `browseen/api.py` hasn't been written. Rows marked *architecture* are A + D's proposal in [docs/architecture.md](../docs/architecture.md#run-api-proposal-for-a--d-fastapi-in-browseenapipy); the rest are new requests from D. Every call goes through [src/api.ts](src/api.ts), so changing a path is a one-line edit there.

In real mode a failed request is shown as an error. The dashboard never falls back to mock data.

## Runs (owner: A)

| Method | Path | Returns | Status |
|---|---|---|---|
| `GET` | `/runs` | `[{"run_id": "r_042"}, …]`, newest first | new |
| `GET` | `/runs/{id}/events.jsonl` | the run's `events.jsonl` so far | new (the file A already writes) |
| `GET` | `/runs/{id}/events` | SSE: one event per `data:` message, same JSON as a JSONL line | architecture |
| `POST` | `/programs/{name}/run` | body `{"mutations": ["M04"], "seed": 1}` → `{"run_id": "…"}` | architecture (body is new) |
| `POST` | `/programs/{name}/run-agent` | the agent baseline for the side-by-side; `{"run_id": "…"}` | architecture |

Events follow architecture.md's format (`run_started`, `step_started`, `check_passed`, `check_failed`, `heal_started`, `healed`, `heal_failed`, `run_finished`). Per-event `llm_calls`, `tokens` and `usd` are what that event cost; `run_finished` carries the run totals and `success`. The dashboard keeps unknown types (shown as plain rows), drops malformed lines, and dedupes resent events by `(run_id, ts, type, step)`.

Requested additions to the event format, in priority order:
1. `pre` / `post` on `check_*` events (which check), so the program view stops inferring the stages.
2. `input_tokens` / `output_tokens` next to `tokens`.
3. `verified` on `run_finished`, from the testbed's `/__verify`, so the overview can show verified success, not only reported.
4. An event for a stop that needs a person (e.g. `approval_requested`), if the human gate comes back.

## Programs (owner: B's format, A serves it)

| Method | Path | Returns | Status |
|---|---|---|---|
| `GET` | `/programs/{name}/versions` | every version as a JSON array of Program objects (browseen/program.py) | architecture (body shape is new) |
| `POST` | `/programs/{name}/rollback?to=1` | the new latest Program (B's `rollback()`: append-only copy) | architecture |

## Mutations (owner: C)

| Method | Path | Returns | Status |
|---|---|---|---|
| `GET` | `/mutations` | `[{"id": "M04", "level": "L2", "name": "Text rename", "change": "…", "expected": "…"}]` | new |

The chaos panel builds the testbed URL as `VITE_TESTBED_URL/?mut=<ids>&seed=<n>` (testbed contract in architecture.md).

## Approvals (owner: A, only if the human gate returns)

The current architecture auto-heals and has no approvals. If they come back:

| Method | Path | Returns |
|---|---|---|
| `GET` | `/approvals` | `[{id, run_id, step, intent, risk, failed_check, reason, screenshot_url?, patch?, trace_id?, status}]` |
| `POST` | `/approvals/{id}/approve` · `/approvals/{id}/reject` | the updated approval |

Approving authorizes the run to continue; it is not proof a write succeeded (that's the receipt check).

## Benchmark (owner: C)

| Method | Path | Returns | Status |
|---|---|---|---|
| `GET` | `/benchmarks` | rows in the format of docs/benchmark.md §6 | new |

Without an API, the Benchmark tab also imports a `bench/results/*.jsonl` file directly.
