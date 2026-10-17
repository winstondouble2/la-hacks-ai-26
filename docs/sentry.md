# Sentry

How we use Sentry, and how what it showed us changed what we built. Design context is in [architecture.md](architecture.md#observability-sentry).

Products used beyond error monitoring: **Tracing**, **Logs**, and (planned) **Session Replay** on the testbed sites.

## Setup

- Org: `la-hacksss`. Python project: `browseen`. A second browser project will hold testbed Replay data.
- Install and configure: `pip install -r requirements.txt`, then copy `.env.example` to `.env` and set `SENTRY_DSN` (Sentry → Project Settings → Client Keys). Never commit the DSN.
- `init_sentry()` in [browseen/observability.py](../browseen/observability.py) must run before any agent code. It turns on errors, tracing, profiling and logs.
- Try it without the agent: `python -m browseen --demo llm|compiled|healed`, then open the trace in Sentry.

## Span tags

Helpers are in [browseen/tracing.py](../browseen/tracing.py): one transaction per run (`run_span`), one span per step (`step_span`).

| Tag | On | Values |
|---|---|---|
| `step.id` | step | the program's step id (`s1`, `s4a`, …); also the span name prefix, e.g. `s4:click` |
| `mode` | run and step | `llm` (recording run), `compiled` (replay), `healed` (step was repaired) |
| `program.version` | run | version of the compiled program (absent for `llm` runs) |
| `guard.result` | step | `pass`, or `fail` on a healed step |
| `heal.tier` | step and run | `1` local, `2` one LLM patch, `3` scoped agent |

**Logs, one per guard decision.** Call `log_check(span, step_id, check, passed, detail)` for every pre/post check: a pass is an info log, a fail is a warning and sets `guard.result=fail` on the step span. Logs carry the trace id, so they show up under the run's trace. Search Logs for `check failed` to see every failed guard.

**AI agent monitoring.** Wrap an agent run (the first recording run, the tier-3 healer) in `agent_span(name, task)` and call `record_agent_result` with its output and token counts. It emits a `gen_ai.invoke_agent` span, which Sentry's AI Agents dashboard picks up; LLM calls inside it become children. Anthropic SDK calls are recorded automatically; `llm_span` (op `gen_ai.request`) is only for other clients. Try it: `python -m browseen --demo healed3`.

Useful Sentry searches (span.op `agent.step`): `mode:healed` finds repaired steps; compare duration of `run:llm` vs `run:compiled` transactions for the cost story.

## Findings log

Add one entry each time Sentry showed us something that changed the code. Format: what we saw, where (link), what we changed, result.

| When | What Sentry showed | Link | What we changed | Result |
|---|---|---|---|---|
| | | | | |
