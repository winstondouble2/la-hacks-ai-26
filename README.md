# la-hacks-ai-26

Browseen: compile a browser agent's first run into a guarded program, replay it without the LLM, and repair only the step that breaks. Design docs are in [docs/](docs/) ([overview](docs/overview.md), [architecture](docs/architecture.md), [benchmark](docs/benchmark.md), [team plan](docs/team_plan.md)).

## Run it

```bash
python -m venv .venv && .venv/Scripts/activate      # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                                # set SENTRY_DSN (optional) and API keys
python -m pytest tests                              # Python tests

cd dashboard && npm install && npm run dev          # dashboard on http://localhost:5173
```

## What works today and what is simulated

| Part | Owner | State |
|---|---|---|
| Program format (`browseen/program.py`, `programs/`) | B | Real; validate with `python -m browseen.program validate <file>` |
| Recorder, compiler, CLI | B | In progress on B's branch |
| Runtime, guards, healer, run API | A | Not in the repo yet |
| Testbed sites, mutations, benchmark | C | Not in the repo yet; the catalog is in docs/benchmark.md |
| Dashboard (`dashboard/`) | D | Works in mock mode on sample runs and fixtures, marked SAMPLE DATA; real mode waits for A's API ([contract](dashboard/API_CONTRACT.md)) |
| Sentry (`browseen/observability.py`, `browseen/tracing.py`) | D | Tracing, logs and AI agent spans confirmed with synthetic demo runs; Session Replay waits for C's sites ([docs/sentry.md](docs/sentry.md)) |

## Sentry

Set `SENTRY_DSN` in `.env`; without it Browseen runs with Sentry off. `python -m browseen.tracing heal1 heal2 heal3 blocked` sends synthetic example traces. Helpers, tags, the Session Replay guide and the findings log are in [docs/sentry.md](docs/sentry.md).

## Reused vs. built this weekend

Reused: Browser Use, Playwright, Pydantic, PyYAML, Sentry SDKs, React, Vite, Tailwind, the `yaml` npm package. Everything in `browseen/`, `dashboard/src/`, `programs/` and `docs/` was written during the event.
