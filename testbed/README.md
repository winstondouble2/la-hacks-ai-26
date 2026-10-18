# Browseen storefront

A complete local demo shop: collection, search, categories, price sorting,
product details, saved favorites, editable cart, delivery form, and order receipt.
The eight existing mutation cases happen inside that same shopping flow.

From the repository root:

```sh
.venv/bin/python -m pip install -r testbed/tests/requirements.txt
.venv/bin/python -m uvicorn testbed.app:app --port 8001
```

Open http://127.0.0.1:8001/demo/reset to start at M00. The old `/lab/demo`
entry point now opens the full storefront, too.

## Manual demo

1. Browse or search for Blue Wireless Headphones.
2. Open the product, choose a quantity, and add it to the cart.
3. Continue to checkout and enter sample delivery details.
4. Place the demo order and inspect the receipt. No payment is collected.
5. Reload to switch to the next mutation and start a fresh shopping run.

Navigation and form submissions keep the current run. Browser reload, detected
by the Navigation Timing API, posts to `/demo/advance` and opens a fresh homepage.
This shortcut requires JavaScript. The sequence is M00, M00 repeat, M01, M02,
M03, M04, M09, M11, M11 repeat, M14, then back to M00.

M01 rotates product action IDs/classes and omits its test ID. M02 adds wrappers.
M03 places Save for later before Add to cart. M04 renames Add to cart to Add to
bag. M09 shows a blocking newsletter dialog after search. M11 adds a product
review/confirmation step between adding an item and reaching the cart; checkout
cannot bypass it. M14 moves purchase controls into a separate panel for odd
seeds. The unmodified cart and delivery checkout are shared by all cases.

The footer always shows the step number, including on narrow screens. Its
Tokens & run info panel explains the current change, shows the next case and all
ten steps, and includes a Next case button as a fallback for browser refresh.
It also keeps the active run ID, usage, verifier link, case selection, and reset
control. Fixed benchmark runs show Pinned instead of a sequence number. Unknown token counts remain unknown.
Repeating a case alone does not prove a cache hit; the real runtime must report
its model and cache events.

## Fixed benchmark runs

For example, `/shop?mut=M11&seed=7&run_id=my-benchmark-run` creates a pinned run.
Its links carry the run ID and browser reload does **not** advance a pinned run.
Use a new run ID for each independent attempt. All products and quantities
are read and totaled on the server, and sessions/orders persist in the local
SQLite database. Set `TESTBED_DATABASE` for an isolated database.

The storefront verifier is `GET /__verify?run_id=...&product_id=blue-headphones&quantity=1`.
Optional `name` and `address` parameters check exact expected delivery values.
It reads the stored order receipt, so adding an item or saving it for later is
not success. These endpoints are separate from the minimal fixture's
`/lab/__verify`; automation for the full website must use the root endpoints.

Post real runtime usage to `/__telemetry/usage` with form fields `run_id`,
`stage` (record/replay/repair), `model`, `input_tokens`, and `output_tokens`.
Report cache events to `/__telemetry/cache-hit` with `run_id` and `stage`.
`GET /__telemetry?run_id=...` supplies the live footer panel. Usage is kept in
memory for this local demo, so it clears when the server restarts. Persistent
shopping state does not imply persistent runtime telemetry.

## Checks

```sh
.venv/bin/python -m pytest bench/tests testbed/tests -q
```

Tests cover the existing minimal fixtures, all eight storefront purchase flows,
blocked and incomplete workflows, exact receipt verification, cart updates,
saved items, input validation, run isolation, reload progression, and telemetry.

This is a local testbed, not a deployed payment service. The actual Browseen
agent/compiler/healer integration and measured cache results remain separate.
