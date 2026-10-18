# Benchmark: first runnable slices

The complete storefront now lives at `http://127.0.0.1:8001/shop`.
Start with `/demo/reset` and follow the normal collection → product → cart →
checkout → receipt flow. Reload switches the underlying mutation.
See `testbed/README.md` for the storefront verifier and telemetry endpoints.
The standalone minimal fixtures below remain available for focused checks.

## Real mutation fixture

The fixture exposes actual deterministic page changes for the first eight cases:

- `M00`: baseline button named **Add to cart**.
- `M01`: the product button's IDs and classes rotate by seed, and its test ID
  disappears. Its visible name remains **Add to cart**.
- `M02`: wrapper elements appear around the product action.
- `M03`: **Save for later** moves before **Add to cart**. Choosing it must not
  pass verification.
- `M04`: the same action is renamed **Add to bag**.
- `M09`: after search, a modal blocks the product action until dismissed.
- `M11`: after adding the product, an inserted order-review step must be completed
  before the verifier accepts the run.
- `M14`: a deterministic A/B layout. Even seeds keep the action with the product;
  odd seeds move it into a separate checkout panel.

Install and run it from the repository root:

```sh
python -m venv .venv
.venv/bin/python -m pip install -r bench/tests/requirements.txt
.venv/bin/python -m uvicorn bench.fixtures.mutation_app:app --port 8011
```

Teammates can point a recorder or runtime at URLs such as:

```text
http://127.0.0.1:8011/fixture?mut=M00&seed=7&run_id=trial-1
http://127.0.0.1:8011/fixture?mut=M01&seed=7&run_id=trial-1a
http://127.0.0.1:8011/fixture?mut=M02&seed=7&run_id=trial-1b
http://127.0.0.1:8011/fixture?mut=M03&seed=7&run_id=trial-1c
http://127.0.0.1:8011/fixture?mut=M04&seed=7&run_id=trial-2
http://127.0.0.1:8011/fixture?mut=M09&seed=7&run_id=trial-3
http://127.0.0.1:8011/fixture?mut=M11&seed=7&run_id=trial-3a
http://127.0.0.1:8011/fixture?mut=M14&seed=2&run_id=trial-4
http://127.0.0.1:8011/fixture?mut=M14&seed=3&run_id=trial-5
```

After an attempted run, use `GET /__verify?run_id=trial-1`. Success requires
the exact product, quantity 1, and total $79.99. State is isolated by `run_id`.
The fixture is in-memory and local-only; restarting it clears all state.

Run the contract tests with:

```sh
.venv/bin/python -m pytest bench/tests/test_mutation_fixtures.py -q
```

These tests prove that the mutations and verifier behave correctly. They do not
prove that Browseen heals them. That claim begins only when a real runtime adapter
drives the fixture and its result is accepted by `/__verify`.

## Guided demo

Open `http://127.0.0.1:8011/demo` for one human-facing sequence. Reloading the
outer guided-demo page advances through M00, an M00 repeat, M01, M02, M03, M04,
M09, M11, an M11 repeat, and M14. Each page creates a fresh run ID and renders
the active fixture. The repeat pages are deliberately the same real cases; they
become cache/replay evidence only after a connected runtime reports it. Use
`/demo/reset` to return to the first scenario.

The demo page includes a live token checker for its generated run ID. It polls
the same `__telemetry` endpoint that the runtime reports to, so it stays
"Waiting for the runtime" until real provider usage arrives. `/demo/case/M09`
(replace `M09` with any supported mutation) opens that real case inside the
polished reload demo.

This is intentionally separate from benchmark mode: individual fixture URLs pin
their mutation and seed for repeatable measurements.

When the companion shop is running, the same fixture is also mounted at
`http://127.0.0.1:8001/lab`. Its human-facing hub is
`http://127.0.0.1:8001/test-cases`; its case links now launch the complete
storefront with the selected mutation. The full store uses root `/__verify`
and `/__telemetry` endpoints; `/lab/__verify` and `/lab/__telemetry` remain
specific to the minimal fixtures.

## Runtime token telemetry

The fixture now has a per-run telemetry receiver, ready for the recorder/runtime
integration. It never manufactures token counts: before the runtime sends an
event, `GET /__telemetry?run_id=trial-1` returns
`"status": "awaiting_runtime_events"`, which is deliberately different from a
claim of zero tokens.

After each real model-provider response, the runtime should post the exact
provider-reported values:

```sh
curl -X POST http://127.0.0.1:8011/__telemetry/usage \
  -d run_id=trial-1 -d stage=record -d model=YOUR_MODEL \
  -d input_tokens=123 -d output_tokens=45
```

On a reused compiled program or cached repair, it should post a cache event:

```sh
curl -X POST http://127.0.0.1:8011/__telemetry/cache-hit \
  -d run_id=trial-1 -d stage=replay
```

`GET /__telemetry?run_id=trial-1` returns the event list and totals. Cache hits
always contribute zero new model tokens. Token events are runtime-reported
telemetry, separate from the fixture's independent order verifier.

## Synthetic harness smoke check

This is a **synthetic harness smoke check**, runnable without a website, browser,
API keys, or the A/B implementations. It checks case generation, independent
fixture verification, false-pass classification, and JSONL output.

## Try it

From the repository root, using Python 3.11+:

```sh
python -m bench.run --system mock --mutations M00,M04,M09 --seed 7
```

No packages are needed for that command. It prints the generated JSONL path.
Expected: **6 rows, 3 fixture successes, 3 false-pass fixtures rejected**.
The rejected cases deliberately model an adapter claiming success when the
verifier says the expected order is absent. These are expected fixture outcomes,
not three failing automated tests. Open the printed JSONL file to inspect them.

To run the harness smoke test:

```sh
.venv/bin/python -m pytest bench/tests -q
```

Existing project environments can be reused.

## What these results mean

- M00 = none, M01 = selector churn, M02 = wrapper insertion, M03 = sibling reorder,
  M04 = text rename, M09 = popup, M11 = flow split, M14 = A/B layout, from `docs/benchmark.md`.
- Mutation IDs are case metadata here. No DOM mutation is applied yet.
- Seed participates in stable case identity; mock behavior does not vary by seed.
- Both adapter and verifier are fixtures. This does not verify a real order.
- Timing measures mock harness execution only. It is not browser performance.
- Zero LLM usage is confirmed because this adapter makes no model calls.
- Every row is marked `synthetic: true`, `mutation_applied: false`, and
  `measurement_kind: harness_smoke_only`. Do not use these rows in benchmark charts.
- Output files are ignored by Git. An explicit `--out` must name a new file;
  existing files are never overwritten.

## Next review slices

Error/timeout handling; resumable case IDs; budget stops; actual mutation fixtures;
then A/B adapters and a verifier that reads website state. The mock adapter is
internal harness scaffolding, not a new shared interface imposed on A/B.

This slice changes only `bench/`. The unfinished shop under `testbed/` is separate
and is not required to run it.
