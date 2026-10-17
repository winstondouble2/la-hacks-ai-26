# Sentry

How we use Sentry, and how what it showed us changed what we built. Design context is in [architecture.md](architecture.md#observability-sentry).

Products used beyond error monitoring: **Tracing**, **Logs** and **AI agent monitoring** (all three confirmed in Sentry with the demo scenarios below), and **Session Replay** on the testbed sites (planned; needs C's sites, see the guide below).

## Setup

- Org: `la-hacksss`. Python project: `browseen`. A second browser project will hold testbed Replay data.
- Install and configure: `pip install -r requirements.txt`, then copy `.env.example` to `.env` and set `SENTRY_DSN` (Sentry → Project Settings → Client Keys). Never commit the DSN.
- `init_sentry()` in [browseen/observability.py](../browseen/observability.py) must run before any agent code. It turns on errors, tracing, profiling and logs.
- Try it without the agent: `python -m browseen.tracing heal1 heal2 heal3 blocked` sends one synthetic run per scenario (heal at tier 1, 2 or 3, or a blocked write) with spans and logs. `python -m browseen --demo …` (B's CLI) still works too.
- **Sentry off:** without `SENTRY_DSN` every helper is a no-op, and a malformed DSN prints a warning and is ignored, so the runtime never depends on Sentry. `tests/test_tracing.py` checks both.

## Span tags

Helpers are in [browseen/tracing.py](../browseen/tracing.py): one transaction per run (`run_span`), one span per step (`step_span`).

| Tag | On | Values |
|---|---|---|
| `step.id` | step | the program's step id (`s1`, `s4a`, …); also the span name prefix, e.g. `s4:click` |
| `mode` | run and step | `llm` (recording run), `compiled` (replay), `healed` (step was repaired) |
| `program.version` | run | version of the compiled program (absent for `llm` runs) |
| `guard.result` | step | `pass`, or `fail` on a healed step |
| `heal.tier` | step, heal span and run | `1` local, `2` one LLM patch, `3` agent takeover |
| `heal.verified` | heal span | `true` only if the patch passed the step's own post-check |
| `run.id`, `program` | run | optional `run_span(..., run_id=, program=)` |

**Logs, one per guard decision.** Call `log_check(span, step_id, check, passed, detail)` for every pre/post check: a pass is an info log, a fail is a warning and sets `guard.result=fail` on the step span. Logs carry the trace id, so they show up under the run's trace. Search Logs for `check failed` to see every failed guard.

**AI agent monitoring.** Wrap an agent run (the first recording run, the tier-3 healer) in `agent_span(name, task)` and call `record_agent_result` with its output and token counts. It emits a `gen_ai.invoke_agent` span, which Sentry's AI Agents dashboard picks up; LLM calls inside it become children. Anthropic SDK calls are recorded automatically; `llm_span` (op `gen_ai.request`) is only for other clients. Try it: `python -m browseen --demo healed3`.

**Healing spans.** Wrap each healing attempt in `heal_span(step_id, tier)` (op `agent.heal`, a child of the step span) and finish it with `record_heal_result(span, step_id, tier, verified, reason)`. The trace then shows which step failed, which guard (from `log_check`), which tier ran, how long it took and whether the repair was verified. For tier 3 use `agent_takeover_span(step_id, task)` inside the heal span: an `agent_span` tagged with the step and tier 3. If browser_use's own LLM calls are auto-instrumented they appear as its children; don't wrap them again.

**Run milestones.** `log_run_event(event, run_id, **attributes)` writes one log line for `run_started`, `run_finished`, `step_started`, `approval_requested`, `program_patched` or `program_rolled_back` (approval requests are warnings).

**Privacy.** Attributes and logs carry ids, check short forms and reasons only: never raw DOM, form values, credentials or patient data. Note `observability.py` sets `send_default_pii=True`, which lets the Anthropic integration record prompts and responses; that's acceptable only because the portals and patients are synthetic. Turn it off before pointing Browseen at real data.

Useful Sentry searches (span.op `agent.step`): `mode:healed` finds repaired steps; compare duration of `run:llm` vs `run:compiled` transactions for the cost story.

## Session Replay on the testbed (guide for C)

Replay records pages that load the Sentry browser SDK, so it goes on C's testbed pages, not on the dashboard. The dashboard's own session is a different browser from the one the agent drives.

1. In Sentry, create a second project, platform *Browser JavaScript* (e.g. `browseen-testbed`), and copy its DSN.
2. In the testbed's base Jinja template, before other scripts (Sentry's loader script also works; use the version their setup page shows):

   ```html
   <script src="https://browser.sentry-cdn.com/<version>/bundle.tracing.replay.min.js" crossorigin="anonymous"></script>
   <script>
     Sentry.init({
       dsn: "{{ sentry_browser_dsn }}",
       integrations: [Sentry.browserTracingIntegration(), Sentry.replayIntegration({
         maskAllText: false,     // synthetic data only: keep text readable for judges
         maskAllInputs: true,    // keep inputs masked anyway
         blockAllMedia: false,
       })],
       tracesSampleRate: 1.0,
       replaysSessionSampleRate: 1.0, // record every agent session during the demo
       replaysOnErrorSampleRate: 1.0,
     });
     Sentry.setTag("run_id", "{{ run_id }}"); // from the run_id header the testbed already records
   </script>
   ```
3. The runner sends `run_id` (and ideally the trace id) in a header on every request, so the replay can be found by tag `run_id:<id>` next to the run's trace. Sharing one trace across Python and the browser needs the `sentry-trace` and `baggage` headers forwarded; untested so far.
4. View replays under *Replays*, filtered by `run_id`. Only claim it works after a replay of a real agent session shows up there: nothing has been verified yet.

## Findings log

Add one entry each time Sentry showed us something that changed the code. Format: what we saw, where (link), what we changed, result.

| When | What Sentry showed | Link | What we changed | Result |
|---|---|---|---|---|
| | | | | |

No entries yet: so far every trace comes from demo or synthetic runs, and none has changed the code. For a bigger finding, copy this block:

```markdown
### Observability finding: <title>

Date:
Run ID:
Sentry trace:
Related logs:

Observed problem:
Evidence:
Root cause:
Change made:
Before:
After:
Verification:
```
