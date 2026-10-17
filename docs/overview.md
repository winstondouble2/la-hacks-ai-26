# Project Overview: Browseen

> The first time a browser agent does a task, Browseen records what it did and compiles it into a program. Next time, the program replays instantly with no LLM calls. When the website has changed, only the step that broke goes back to the LLM (or the agent), which repairs it, and the replay carries on.

LA Hacks AI Hackathon 2026 (UCLA, Oct 17–18, 2026). This is idea #2 from our idea shortlist, the *Self-Healing Agent Compiler*.

See [architecture.md](architecture.md) for how it works, [benchmark.md](benchmark.md) for what we measure, [team_plan.md](team_plan.md) for who builds what, and [sentry.md](sentry.md) for observability.

> **About [build_plan.md](build_plan.md).** It describes a different, safety-focused variant called *Kintsugi*: read/write risk tags, stopping for human approval through Slack, receipt checks against an audit log, and a clinic insurance story. **We are not building that variant.** There is no human approval step: when something doesn't match, the LLM or the agent steps in by itself. Its research is still useful: the prior-art notes, prize stack, Sentry requirements, submission checklist and judge questions. Where it conflicts with these docs, **these docs win.**

## The problem

LLM browser agents such as Browser Use can do almost any web task, but they **re-think every step on every run**. Doing a task for the hundredth time costs the same tokens and the same tens of seconds as the first time. Most of the work people want to automate is repetitive: weekly reports, form submissions, order checks, data entry.

The usual fix is record-and-replay: save the actions once and replay them without the LLM. That's fast and cheap, but **brittle**. A renamed button, a new popup or a moved field breaks the replay. It either crashes or, worse, clicks the wrong thing, and then you're back to running the expensive agent from scratch.

## The idea

1. **Record.** A user asks the agent to do something on a website. The Browser Use agent does it normally, and Browseen records every step: what it clicked or typed, which element, which page, and why.
2. **Compile.** The recording becomes a **program**. It has steps with fallback locators, **parameters** (the search term, the quantity), **guard checks** before and after each step ("is the page in the state this step expects?"), and **branches** for things that only sometimes happen, like a cookie banner.
3. **Replay.** When the user asks for the same task on the same site again, even with different inputs, Browseen runs the program directly with Playwright. There are **no LLM calls**: it takes about a second instead of tens of seconds, and costs no tokens.
4. **Heal.** If a guard check fails because the page doesn't match the recording, **only that step** is repaired, automatically and cheapest first:
   - **Tier 1 (no LLM):** try the other locators and fuzzy-match the element.
   - **Tier 2 (one LLM call):** the LLM patches just that step.
   - **Tier 3 (agent):** the Browser Use agent takes over from that step until the compiled replay can resume, or finishes the task itself.

   A patch counts only if the step's after-checks pass. Then it's saved as a new program version, so the next run is free again.

**No human approval.** The LLM or the agent steps in whenever it's needed, and the run finishes on its own.

Under the hood this works like a **JIT compiler**: fast compiled code protected by cheap checks, falling back to the slow, general path (the LLM agent) only where an assumption broke.

## Prior art and our gap

Record-and-replay with an LLM fallback already exists in several forms, so the pitch has to be specific about what's different. These were checked on Oct 17, 2026; re-check before the pitch.

| Tool | What it does | What it lacks |
|---|---|---|
| **Browser Use `rerun_history()`** | Replays a saved agent history in a straight line, re-matching elements by hash, then XPath, then accessible name. | It isn't LLM-free (extract steps and a final summary call the model), and it has no guards, no branches and no repair. |
| **Workflow Use** (Browser Use team) | Deterministic workflow files with variables. The README advertises a fallback to the agent. | No branches; the agent fallback is commented out in the source; self-healing is an unchecked roadmap item. |
| **taprun** | Compiles a Browser Use history into a linear plan with zero-token replay. | Linear; healing is a whole-plan check after the fact (paid tier), not a per-step fix mid-run. |
| **Skyvern** code caching | Generates code from an agent run. If the cached code fails, it falls back to the agent and regenerates the code. | Regenerates rather than repairing one verified step; no public benchmark on changed pages. |
| **Stagehand** caching | Caches individual act/observe/extract calls; a miss triggers full LLM inference. | Per-call and linear; no multi-step program to patch. |
| **LOOP Skill Engine** (paper, May 2026) | Records tool calls into parameterized linear skills. 7.82 s → 0.90 s on one 3-step task; token savings are modeled, not measured. | Linear, no output validation, no repair, not about websites. |
| **PreAct** (paper, Jun 2026) | The closest prior art. It compiles a run into a state machine with screen checks and branches and replays with 0 LLM calls. | When a check fails, the full agent finishes the task and the **whole** program is recompiled. |

**Our gap, in one line:** compiled programs with **guards and branches**, plus **step-local, tiered repair** (no LLM first, then one LLM call, then the agent) that patches one step and **resumes compiled replay**, measured end to end on **deliberately changed websites**.

**How to say it:** "Pay the LLM once, then only for what changed."

## What we'll show

1. **Cost and speed.** The first (agent) run vs. a compiled run: tokens, dollars and seconds. Then the break-even point: after how many runs Browseen beats running the agent every time.
2. **Robustness.** Success rate on deliberately changed pages: Browseen vs. plain linear replay vs. the agent every time.
3. **Cheap healing.** LLM calls and dollars per heal vs. re-running the whole agent, and proof that the next run after a heal costs nothing again.

The details are in [benchmark.md](benchmark.md).

## Demo (about 2:30)

1. **The first run.** "Buy 2 Blue Mugs" on our demo shop. The Browser Use agent works while the dashboard's time, token and $ counters climb. Browseen records.
2. **The program.** The compiled steps appear, with guards, parameters and the cookie-banner branch.
3. **The second run.** "Buy 1 Red Kettle" finishes in about a second, at **$0.00 and 0 LLM calls**, with both runs side by side.
4. **A judge changes the site** in the chaos panel: renames "Add to cart", moves it into a menu, or adds a popup.
5. **The heal.** On the next run, one step fails its check and is highlighted. It heals (the dashboard shows which tier, with one LLM call), and the run finishes. The v1 → v2 diff appears.
6. **Free again.** One more run: 0 LLM calls, because the repair was saved.
7. **The numbers.** The benchmark chart, plus the Sentry trace showing exactly which step healed.

## Tracks

| Challenge | Fit |
|---|---|
| **Applied Intelligence** (main track) | Practical automation: repeated browser tasks become fast, cheap and reliable. |
| Browser Use, Best Use | Browser Use does the first run and is the tier-3 healer. |
| Sentry, Best Use | Tracing, Logs, Profiling, AI agent monitoring and Session Replay on our test sites. The challenge needs at least two products beyond error monitoring; see [sentry.md](sentry.md). |
| Cognition, Best Use of Devin | Enter only if we really use Devin (for example for the test sites or the harness), and keep the session links as proof. |
| MLH Commit Fellowship | A 10-minute opt-in form. |

The prize details and submission checklist are in [build_plan.md → Prize stack](build_plan.md#prize-stack). They're still valid.

## Risks

| Risk | Mitigation |
|---|---|
| "How is this different from Workflow Use / taprun / Skyvern / PreAct?" | Lead with step-local tiered repair that resumes compiled replay, and back it with the changed-page benchmark. |
| A wrong heal, where the patch clicks the wrong thing | The patch must pass the step's after-checks and the task's success check; every patch is a new version with rollback. We report the false-pass rate. |
| A judge makes a change we never planned for | The chaos panel offers tested changes, and tier 3 (the agent) is the catch-all. |
| Guards too strict, so they fire on harmless changes and waste LLM calls | Use cheap deterministic checks first; we measure false alarms on harmless changes. |
| Third-party sites are flaky or have CAPTCHAs | Demo and benchmark on **test sites we control**; a real site is a bonus at most. |
| API spend on the benchmark | A dollar cap, cached baseline runs, a small matrix. |
| Wi-Fi on stage | Everything runs on localhost except the LLM calls. Keep a backup video and label any cached result "cached". |
