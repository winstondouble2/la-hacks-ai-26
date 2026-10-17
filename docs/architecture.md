# Architecture

How Browseen works. The pitch is in [overview.md](overview.md); observability details are in [sentry.md](sentry.md). Anything marked *proposal* is a suggestion for that interface's owner (see [team_plan.md](team_plan.md)) to accept or change.

## The JIT analogy

| JIT compiler | Browseen |
|---|---|
| Interpreter (slow, general) | The Browser Use agent doing the task step by step |
| Profiling the interpreter | Recording the agent's run |
| Compiling the hot path | Compiling the recording into a program |
| Type guards in compiled code | Checks on the page before and after each step |
| Deoptimization: bail out to the interpreter when a guard fails | Hand **only the failing step** to the LLM or the agent |
| Polymorphic inline cache | Keep the old and new paths as branches, so both site variants replay for free |
| Recompilation | The verified patch becomes program v(N+1), and later runs are compiled again |

## Pipeline

```
 FIRST RUN (pays the LLM once)
 task + params ──► Browser Use agent ──► Recorder ──► trace
                                                        │
                                                        ▼
                                                    Compiler
                                                        │
                                                        ▼
 LATER RUNS (0 LLM calls)                        program vN (YAML)
 params ──────────────────────────────────────►  Runtime (Playwright)
                                                        │
                        each step: pre-checks → act → post-checks
                                                        │
               all pass ────────────────────────────────┼──► … ──► success check ──► done
                                                        │
                                          a check fails at step k
                                                        ▼
                                                     Healer
                         tier 1  other locators / fuzzy match        0 LLM calls
                         tier 2  one LLM call patches step k         1 LLM call
                         tier 3  Browser Use agent takes over at k   a few LLM calls
                                                        │ patch passes step k's post-checks
                                                        ▼
                                  program v(N+1) saved ──► resume compiled at step k+1
```

**There is no human in the loop.** A failure is always handed to the next healing tier, and the run either finishes or fails loudly.

## Components

### Recorder (B)

This component wraps a Browser Use `Agent` and uses its step hooks (`on_step_start` / `on_step_end`) to capture, for each step:

- **The action** and its parameters: click, input text, navigate, select, scroll, extract.
- **The target element.** Browser Use records each element it touched with its tag, attributes, XPath, element hash, stable hash, accessible name and bounds. It does **not** store CSS or role selectors, so the compiler derives those.
- **The page around the step:** the URL before and after, a DOM / accessibility snapshot, and a screenshot.
- **The agent's stated goal for the step**, which becomes the step's intent.
- **Tokens and latency** for the step, which feed the cost counters.

**Built.** The code is in `browseen/recorder/`, and you run it like this:

```bash
python -m browseen record 'Buy $qty of $product and check out as $name, $address' --url http://localhost:8765/ --input product="Blue Mug" --input qty=2 --input name="Ada Lovelace" --input address="1 Main St" --name buy-item
```

- **The task is a template plus inputs.** The agent gets the filled-in text, and the trace keeps both, so the compiler knows exactly which literals are parameters.
- **Viewing a run:** `python -m browseen show runs/<run_id>` prints it without any API calls.
- **On the mini shop,** a recording takes about 30 s and costs about $0.18 (6 LLM calls). The first call writes the prompt cache; later ones read it.

Each run writes `runs/<run_id>/` (gitignored):

| File | What it is |
|---|---|
| `trace.json` | The **trace format**, defined in `browseen/recorder/trace.py`, which B owns. It holds, for each step: the URL before and after; the agent's `goal` (which becomes the intent), memory and evaluation; the actions with Browser Use's raw names and params; the element for each action (`tag`, `attributes`, absolute `xpath`, `ax_name`, `bounds`); the step's duration and token usage; and the page and screenshot paths. It also holds the run's totals and the agent's own success claim. Step 0 is the initial navigation. |
| `history.json` | Browser Use's own history file, which the benchmark's Replay baseline needs |
| `events.jsonl` | The run as dashboard events (`mode: "llm"`, `version: 0`, steps `a1`, `a2`, …), with per-step `llm_calls` / `tokens` / `usd` |
| `html/step_NN_before.html`, `html/step_NN_after.html` | The page before and after step NN. **"Before" is what the compiler tests locators on**; every recorded XPath matched exactly one element in it. |
| `screenshots/step_NN.png` | Taken by Browser Use at the start of step NN |

The Browser Use setup is shared in `browseen/agent.py` (`make_agent()`), which A's tier-3 healer should use too. Each setting fixes a real failure with Claude Opus 5.5:

- **`thinking={"type": "adaptive"}`.** Without it, the wrapper forces `tool_choice`, and the API returns HTTP 400.
- **`use_thinking=False`.** Without it, Browser Use's `thinking` output field is refused as reasoning extraction.
- **Server-side `fallbacks` to `claude-opus-4-8`.** If Opus 5.5 refuses a step, Anthropic retries it on the fallback model.
- **`enable_default_extensions=False`.** Otherwise a cookie-banner auto-dismisser hides banners from the recording.
- **`use_judge=False`.** The judge makes extra LLM calls; we verify success ourselves.
- **Chrome flags for the macOS keychain.** They stop Chromium from hanging at startup.

Prices are in `browseen/costs.py`.

### Compiler (B)

**Built** in `browseen/compiler/`: deterministic passes (v0) plus one LLM pass (v1).

```bash
python -m browseen compile runs/<run_id> --name mini-shop
```

That writes `programs/mini-shop/v1.yaml` and prints a compile report: each trace action is kept (and which step it became), dropped (with the reason) or unsupported, plus each locator candidate with ✓/✗, and the LLM pass's tokens and cost. Add `--dry-run` to print the program without saving, or `--no-llm` for v0 only. The compiler refuses to write into an existing program folder.

Compiled from the mini-shop recording, the program replays with Blue Mug ×2 and with Red Kettle ×1, with 0 LLM calls.

**Normalize:**

- *Mapped:* `click` → click, `input` → fill, `select_dropdown` → select, `send_keys` → press, later `navigate` → navigate.
- *Dropped, with a reason:* the step-0 navigation, `done`, `wait`, `scroll`, read-only tools, failed actions, an input superseded by a later input into the same field, and a single click that changed nothing.
- *Not handled in v0:* `extract`, and *unsupported* `go_back`, `upload_file`, tab switching and `evaluate`.

**Locators.** Each saved page is loaded with scripts stripped and JavaScript off, so it's exactly the recorded DOM.

- The element's real role and accessible name come from Playwright's `aria_snapshot()`.
- Candidates are tried in this order: `data-testid`, then for form fields `label` and then role + name, for everything else role + name and then `text`, then `placeholder`, then a stable CSS selector (`#id` or `[name]`), then the XPath.
- When an accessible name ends in a price or count ("Place demo order · $159.98"), the stable start ("Place demo order") is added as a substring-matching role locator, so the step still works for another product or quantity.
- A candidate is kept **only if it matches exactly one element and that element is the recorded one.**

**Parameters.** Recorded input values become `$params`, with the longest values replaced first. Short values such as `2` are replaced only as whole words, and literal `$` becomes `$$`. This applies to values, locator names, check text and the start URL, but never to CSS or XPath.

- **Start URL.** An input that appears in the start URL (the storefront's `run_id`) becomes a param, so each replay gets a fresh session.
- **Check text.** Inputs the task text doesn't name are templated but never picked as check text.

**Checks:**

- Pre-checks: the page path, the target is unique, and the target is enabled (for clicks).
- Post-checks: the field's value (for fill and select), the new page path, and the shortest text line on the new page that names an input (for example `$qty × $product`). That last one catches a wrong-item click.
  - Lines that would still contain a number after templating, such as a price, are skipped; if every line has one, the input alone is used (`$product`).
  - URL checks match any value for path parts that name the chosen item: a slug like `/products/blue-headphones`, or a numeric id.
- Success check: a heading or text line on the final page that names an input.
- A click that adds no text but makes its own target disappear (dismissing a banner) gets an `absent` post-check.

**The LLM pass (v1)** is in `annotate.py`. It's one structured-output call to `claude-opus-5-5` (effort `medium`, with a server-side fallback to Opus 4.8) that costs about $0.015 per compile.

- **What the model sees:** each step's action, target, page path, v0 intent, the recording agent's own goal, and a *container hint* (for example `dialog "Cookie consent"`, from the element's nearest dialog, banner or popup ancestor). It also sees the final page's text.
- **What it returns:** an intent per step, which steps are optional, a description per param, and success text.

Every suggestion passes a guard before it's used:

- The step IDs must match exactly.
- Intents may only use declared `$params`.
- Only a `click` with a target can be optional, and we build its `when: {exists: <first locator>}` ourselves.
- The success text must actually appear on the final page.

If the call fails or is refused, or there's no API key, the compiler keeps the v0 output and prints a warning.

On a recording that dismissed the shop's cookie wall (`?banner=1` on the mini shop), v1 marks that click optional, so the program runs it when the wall appears and skips it when consent is already stored. The v0 program fails in the second case.

**Limits:**

- The CSS and XPath fallbacks for parameter-dependent elements still point at the recorded item. The post-checks catch that.
- Branches learned from heals and merging several recordings are not built.

The full design, including the LLM pass:

1. **Normalize.** Drop failed or no-op actions, collapse mis-click-then-correct sequences, and merge consecutive typing into one action.
2. **Parameterize.** Literals that came from the task inputs become `$params`. The LLM pass names them and gives each a type.
3. **Locators.** For each target, build candidates in this order: test id, then role + accessible name, then label or placeholder, then text, then stable CSS, then XPath. Keep only candidates that match exactly one element in the recorded snapshot. Also store a **fingerprint** of the element (role, name, text, neighbors) for fuzzy matching later.
4. **Guards.** Generate checks for each step:
   - **Pre-checks:** the URL pattern, and that the target exists, is unique and is enabled.
   - **Post-checks:** the URL changed as expected, the expected element or text appeared, or extracted data matches its schema.
5. **Branches.**
   - *Optional steps:* the LLM pass marks steps that dismiss popups or cookie banners, and they become `when: exists(...)`.
   - *Learned branches:* when the healer fixes a step on a site that might switch back (an A/B layout), the old path stays as one arm and the new path becomes another.
   - Loops and merging several recordings into one program are stretch goals.
6. **Intent and success.** Every step keeps a one-sentence intent, and the program gets a task-level **success check**, such as "Order confirmed" being visible.

### Program format (owner: B)

**Frozen.** The format is defined in code in [`browseen/program.py`](../browseen/program.py), as Pydantic models that both the compiler and the runtime import. The reference example is [`programs/buy-item/v1.yaml`](../programs/buy-item/v1.yaml), for the mini-shop fixture. A JSON Schema for the dashboard's types is in `programs/program.schema.json` (`python -m browseen.program schema`). Change the format only through B.

- **Files.** There is one YAML file per version, `programs/<name>/v<N>.yaml`. Versions are append-only (`save()` refuses to overwrite), so a rollback just means loading an older file.
- **Validation.** `python -m browseen.program validate <file>` checks a file. Unknown keys are rejected.

| Piece | Fields | Notes |
|---|---|---|
| Program | `program`, `version`, `task`, `start_url`, `params`, `steps`, `success`, `history` | `success` is a list of checks for the whole task |
| Step | `id` (`s1`, `s2`, `s4a`, …), `intent`, `action`, `target`, `when`, `pre`, `post`, `timeout_ms` | `target` sits at **step** level. It's required except for `navigate` and `press`. |
| Action | `type` (navigate, click, fill, select, check, uncheck, press, extract) plus `value`, `url`, `key` or `into` | `fill` and `select` need `value`, `navigate` needs `url` |
| Target | `locators` (tried in order), `fingerprint` | The fingerprint is the recorded element, which tier 1 fuzzy-matches against |
| Locator | exactly one of `testid`, `role` (+ `name`, `exact`), `label`, `placeholder`, `text`, `css`, `xpath` | `Locator.to_playwright(page)` is the one shared mapping to Playwright. `xpath` must start with `/`. |
| Check | exactly one of `url_matches` (a regex), `text_visible`, `exists`, `absent`, `target_unique`, `target_enabled`, `target_value` | `target_*` checks refer to the step's own target |
| Change | `version`, `source` (recorded, compiled, healed, manual), `step`, `tier`, `reason`, `at` | History; `Program.bump(...)` appends one |

- **Optional steps.** If a step's `when` check fails, the step is skipped. Evaluate `when` with a short timeout (the dry run used 500 ms).
- **Parameters.** `$name` can appear in any string: values, URLs, check text, locator names such as `{role: link, name: $product}`. Use `${name}` when a letter or digit directly follows (`${product}Qty`). `$$` is a literal `$`. The runtime calls `program.resolved(params)` once per run.
- **Healing.** `program.bump(source="healed", step=…, tier=…, reason=…)` returns the next version. Edit the copy, then `save()` it.

### Runtime (A)

The runtime interprets the program with Playwright. For each step it:

1. skips the step if its `when` is false;
2. resolves the target through the locator list;
3. runs the pre-checks;
4. performs the action and waits for the page to settle;
5. runs the post-checks.

When the last step is done, it runs the **success check**. The happy path makes **zero LLM calls**.

When a check fails, the runtime raises `GuardFailure`, carrying which check failed, the expected vs. the actual state, a snapshot and a screenshot, and hands the step to the healer.

**One browser per run.** Launch Chromium with a CDP port so that tier 3 can hand the *same* page (with its cookies and cart) to Browser Use, which connects over CDP. Playwright pauses while the agent drives. Verify this in hour one. If it doesn't work, the agent can open its own browser at the current URL with Playwright's saved storage state.

### Healer (A)

The healer repairs only the failing step, escalating through three tiers, cheapest first. These are the same tier numbers as `heal.tier` in [sentry.md](sentry.md).

| Tier | What happens | LLM calls |
|---|---|---|
| **1. Local** | Try the step's other locators, then fuzzy-match the stored fingerprint against the current accessibility tree. Accept only a single candidate that passes both pre- and post-checks. | 0 |
| **2. Patch** | One LLM call. It gets the step's intent, the original fingerprint, the failed check and a trimmed accessibility snapshot (plus a screenshot), and returns a **structured patch**: a new target, steps to insert before this one (such as "close the popup"), or a new branch arm. | 1 |
| **3. Agent** | A Browser Use agent starts from the current page with the task "accomplish *step k's intent* (overall goal: *task*)". After each agent step, the runtime checks whether a later compiled step's pre-checks pass; as soon as one does, the agent stops, its actions are compiled into a replacement block, and compiled replay resumes. If no step ever matches, the agent finishes the task and its trace is compiled into the rest of the program. | a few |

These rules apply at every tier:

- **Verify before saving.** A patch is kept only if the step's post-checks pass, and a run counts as successful only if the success check passes. That prevents lucky passes.
- **Version every patch.** Program v(N+1) records the step, the tier and the reason, and the dashboard shows the diff. `rollback` restores any earlier version.
- **Resume compiled.** After a heal, execution continues at the next step in compiled mode, and the next run is free again.
- **Fail loudly.** If all three tiers fail, the run is marked failed with a report. It is never reported as a success.
- **No human approval.** The LLM or the agent always handles the repair.

## Interfaces

| Interface | Owner | Consumers |
|---|---|---|
| Trace format | B | B's compiler |
| Program YAML | B | A (runtime, healer), D (program view, diff) |
| Event stream | A | D (dashboard), C (benchmark) |
| Run API | A + D | D (dashboard), C (harness) |
| Testbed contract | C | Everyone |

### Event stream (*proposal* for A)

The event stream is one JSON object per line, written to `runs/<run_id>/events.jsonl` and served to the dashboard over server-sent events:

```json
{"ts": "2026-10-17T21:04:11.2Z", "run_id": "r_042", "program": "buy-item", "version": 1,
 "mode": "compiled", "type": "healed", "step": "s5", "tier": 2,
 "detail": "'Add to cart' renamed to 'Add to bag'", "diff": "…",
 "llm_calls": 1, "tokens": 9530, "usd": 0.045, "trace_id": "…"}
```

`type` is one of `run_started`, `step_started`, `check_passed`, `check_failed`, `heal_started`, `healed`, `heal_failed`, or `run_finished`. `run_finished` carries the totals: LLM calls, tokens, $, seconds and success.

### Run API (*proposal* for A + D, FastAPI in `browseen/api.py`)

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/record` | Run the Browser Use agent on a task, record it, and compile program v1 |
| `POST` | `/programs/{name}/run` | Compiled run with params, healing automatically |
| `POST` | `/programs/{name}/run-agent` | Baseline: run the plain agent, for the side-by-side counters |
| `GET` | `/programs` · `/programs/{name}/versions` | List programs and their versions |
| `GET` | `/programs/{name}/diff?from=1&to=2` | Diff between two versions |
| `POST` | `/programs/{name}/rollback?to=1` | Restore a version |
| `GET` | `/runs/{id}/events` | Event stream (SSE) |

### Testbed contract (*proposal* for C)

These are the test sites we control (see [benchmark.md](benchmark.md#2-testbed-sites)):

- **`?mut=<ids>`** or a header turns on page changes. The chaos panel uses the same IDs.
- **`POST /__reset`** restores the seed data.
- **`GET /__verify?task=…`** gives server-side ground truth for the benchmark.
- **A `run_id` header** is recorded server-side, so verification maps to runs.
- **The Sentry browser SDK with Session Replay** runs on every page.

## CLI (B)

**Built.** Run commands as `python -m browseen <command>`. The commands are in `browseen/cli.py`. The old forms `python -m browseen.recorder …` and `python -m browseen.compiler …` still work, and so does `python -m browseen --demo llm|compiled|healed|healed3` (the Sentry trace demo).

| Command | Does |
|---|---|
| `record "<task with $params>" --url <start> --input k=v … [--name NAME] [--headless]` | Run the agent once and save the trace to `runs/<run_id>/` |
| `show runs/<run_id>` | Print a recorded run, with no API calls |
| `compile runs/<run_id> [--name NAME] [--no-llm] [--dry-run]` | Recorded run → `programs/<name>/v1.yaml` |
| `run <name or file.yaml> --param k=v … [--version N] [--headless]` | Compiled run with automatic healing, via A's runtime (below). It first checks that every param is given, and lists the missing ones with examples. |
| `diff <name> [a] [b]` | What changed between two versions: previous vs. latest, `a` vs. latest, or `a` vs. `b`. It compares the normalized YAML, so formatting differences don't show, and names the steps that were added, removed or changed. |
| `rollback <name> --to <v>` | Saves the next version as a copy of `v`. Versions are append-only, so nothing is deleted, and the history records the rollback. |

**The runtime hook (for A).** `run` calls `browseen.runtime.run_program(program, params, *, headless)`:

- `program` is the loaded `Program` (the latest version, or the one asked for with `--version`);
- `params` is the dict of typed inputs.

It should return an object with a `success` attribute (or a plain bool), which sets the command's exit code. Until `browseen/runtime/` exists, `run` says that the runtime isn't on the branch yet. `tests/test_cli.py::test_run_calls_the_runtime_contract` pins down this contract.

## Tech stack

| Layer | Choice | Notes |
|---|---|---|
| Language and packaging | Python 3.12, `requirements.txt` + a venv | `python -m venv .venv && pip install -r requirements.txt`. Pin versions once they're confirmed. |
| First run and tier 3 | browser-use (pinned) | Drives Chrome over CDP. Gives us step history with element data. |
| Compiled runtime | Playwright for Python (1.64) | `get_by_role` / `get_by_text` / `get_by_test_id` for locators; `aria_snapshot()` for snapshots and guard checks. |
| LLM | Anthropic SDK; `claude-opus-5-5` by default for compile, tier 2 and the agent | One thin client that logs tokens and $ for every call. The model is configurable, and the benchmark logs it. |
| API | FastAPI + SSE | `browseen/api.py` |
| Test sites | FastAPI + Jinja templates + SQLite | Shop, form portal and CRM with page-change switches |
| Dashboard | React + Vite + Tailwind | Live counters, side-by-side runs, program view, diffs with the healed step highlighted, chaos panel, benchmark charts |
| Observability | `sentry-sdk` (Python) and the Sentry browser SDK on the test sites | See below and [sentry.md](sentry.md) |
| Hosting | Local for the demo; Vultr optional | The demo must not depend on it |

### Repo layout

```
browseen/                 # Python package
  __main__.py             # CLI entry (exists)
  observability.py        # Sentry init (exists)
  tracing.py              # run / step / LLM span helpers (exists)
  recorder/  compiler/    # B
  runtime/   healer/      # A (runtime/ includes the guard checks)
  api.py                  # A + D
testbed/                  # C: shop/ portal/ crm/ mutations.py
bench/                    # C: tasks/ mutations.yaml config.yaml run.py report.py results/
dashboard/                # D
programs/                 # compiled programs, every version kept
requirements.txt
```

## Observability (Sentry)

[sentry.md](sentry.md) is the reference for setup, tags and the findings log. In short:

- **Tracing.** There is one transaction per run (`run_span`) and one span per step (`step_span`), both in `browseen/tracing.py`. The tags are:
  - `mode`: `llm`, `compiled` or `healed`
  - `program.version`
  - `guard.result`: `pass` or `fail`
  - `heal.tier`: 1, 2 or 3

  A heal shows up as one slow span among fast ones.
- **Logs.** `mark_healed` writes one log line per heal. Add one for each failed check too.
- **Profiling** is already on in `observability.py`.
- **AI agent monitoring.** The Python SDK auto-instruments the Anthropic SDK, so compile and tier-2 calls appear as `gen_ai` spans with tokens and cost. Spans with custom ops such as `agent.llm` don't appear in Sentry's Agents view, so wrap the tier-3 agent in a `gen_ai.invoke_agent` span (*proposal*).
- **Session Replay** goes on the test sites, so we can watch the browser at the moment of a heal. Replay masks text and inputs by default; turn that off on our synthetic sites. Replay can't record third-party sites.
