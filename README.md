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

## Record a run and compile it

The agent runs once. The recording becomes a program that replays with other inputs and makes no LLM calls. This needs `ANTHROPIC_API_KEY` in `.env`.

```bash
python -m browseen record 'Buy $qty of $product and check out with name $name, street address $address, city $city and postal code $postal' \
  --url "http://127.0.0.1:8001/shop?mut=M00&seed=7&run_id=rec-1" --input run_id=rec-1 \
  --input product="Blue Wireless Headphones" --input qty=2 --input name="Ada Lovelace" \
  --input address="12 Main St" --input city=Pasadena --input postal=91101 --name storefront-buy
python -m browseen compile runs/<run_id>          # writes programs/storefront-buy/v1.yaml
python -m browseen run storefront-buy --param product="Red Kettle" --param qty=1 ...   # A's runtime
python -m browseen diff buy-item                  # what a heal changed between versions
```

| Stage | Measured on C's storefront |
|---|---|
| Recording | 6 agent steps, about 28 s, about $0.20 |
| Compiling | One LLM pass: about 3K tokens, about $0.02 |
| Replay | 9 steps, 0 LLM calls, verified by `/__verify` for Red Kettle ×1 and Headphones ×3 |

- **The task is a template.** `$name` placeholders are filled from `--input`. The `run_id` in the start URL becomes a parameter too, so every replay gets a fresh shop session.
- **Viewing a recording:** `python -m browseen show runs/<run_id>` prints it without any API calls.
- **The format:** [browseen/program.py](browseen/program.py), with examples in `programs/`.
- **The details:** see [docs/architecture.md](docs/architecture.md) (Recorder, Compiler, CLI).

## What works today and what is simulated

| Part | Owner | State |
|---|---|---|
| Program format (`browseen/program.py`, `programs/`) | B | Real; validate with `python -m browseen.program validate <file>` |
| Recorder, compiler, CLI (`browseen/recorder/`, `browseen/compiler/`, `browseen/cli.py`) | B | Real. Recorded and compiled on C's storefront; the compiled program replays other products and quantities with 0 LLM calls, and `/__verify` confirms the orders. `run` waits for A's runtime |
| Runtime, guards, healer, run API | A | Not in the repo yet |
| Testbed sites, mutations, benchmark | C | Not in the repo yet; the catalog is in docs/benchmark.md |
| Dashboard (`dashboard/`) | D | Works in mock mode on sample runs and fixtures, marked SAMPLE DATA; real mode waits for A's API ([contract](dashboard/API_CONTRACT.md)) |
| Sentry (`browseen/observability.py`, `browseen/tracing.py`) | D | Tracing, logs and AI agent spans confirmed with synthetic demo runs; Session Replay waits for C's sites ([docs/sentry.md](docs/sentry.md)) |

## Sentry

Set `SENTRY_DSN` in `.env`; without it Browseen runs with Sentry off. `python -m browseen.tracing heal1 heal2 heal3 blocked` sends synthetic example traces. Helpers, tags, the Session Replay guide and the findings log are in [docs/sentry.md](docs/sentry.md).

## Reused vs. built this weekend

Reused: Browser Use, Playwright, Pydantic, PyYAML, Sentry SDKs, React, Vite, Tailwind, the `yaml` npm package. Everything in `browseen/`, `dashboard/src/`, `programs/` and `docs/` was written during the event.
