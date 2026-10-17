# Project Overview: Browseen

> Browser agents are right the first time and quietly wrong the hundredth. Browseen turns one agent run into a guarded program that replays for free, blocks when a page no longer means what it did, repairs only the cracked step, and asks a human before anything that writes.

LA Hacks AI Hackathon 2026 (UCLA, Oct 17–18, 2026). **[build_plan.md](build_plan.md) is the source of truth** for scope, story and plan. It still uses an earlier working name, *Kintsugi*; the project is **Browseen**. This page summarizes it. See [architecture.md](architecture.md) for how it works, [benchmark.md](benchmark.md) for what we measure, and [team_plan.md](team_plan.md) for who builds what.

## The story

**Meet Maria.** Every morning she checks insurance eligibility for thirty patients across three payer portals. One day a portal swaps its *Save draft* and *Submit* buttons. Her browser agent doesn't crash. It clicks Submit on a half-filled form and reports success, and nobody finds out until a claim bounces. **Browseen is what stops that click.**

Maria is an illustrative character, and the portals and patients are synthetic. No dashboard appears in the demo until this story is told.

- **Named user:** front-desk staff at a small clinic who re-verify patient insurance eligibility on three payer web portals every morning. It's the same eight clicks each time, the portals often expose only a web form, and their layouts change without notice.
- **Visual signature:** a healed step gets a **gold seam** in the program view and in the diff, so a judge sees the repair at a glance.

## The problem: silent failures

Existing tools fix **loud** failures, where a replay crashes and an LLM takes over. The dangerous case is the **silent** failure: the replay finishes, reports success, and did the wrong thing. That means the wrong button, the wrong row, or a write that never landed.

Here is context from others in their own domains. None of it is our result, and we quote only figures we measure ourselves.

- **taprun's study of 15,455 automation runs:** errors from changed page structure outnumbered plain "element not found" errors 176 to 5, and one site returned empty results with no error on half its runs.
- **A Browserbase talk (Derek Meegan):**
  - 99% per-step accuracy over 100 steps is about 36% end to end.
  - Success should be confirmed against the system of record, not the agent's own report.

## What Browseen does

1. **Record.** A Browser Use agent runs the flow once. We save its step history with element locators and tag each step **read**, **write** or **irreversible**.
2. **Compile.** One LLM pass turns that history into a **YAML program**. Each step gets an action, fallback locators, parameters, an intent sentence, pre-checks, post-checks, a receipt rule and a risk level.
3. **Replay with guards.** Playwright runs the program with no LLM calls. Every step is checked **before and after** it acts. A cheap LLM judge is used only on write steps, or when a locator still matches but its accessible name changed.
4. **Repair or stop.**
   - When a **read** step fails a check, it gets a **one-step repair**. The patch must pass the same post-check, then lands as a versioned diff with rollback.
   - When a **write** or **irreversible** step fails a check, the run **fails closed**: it stops and asks a human.
5. **Receipt.** A write step only counts as done when the portal's own **audit log** shows the matching record.
6. **Human gate.** When a run stops, a person gets the step's intent, a screenshot, the proposed diff and the Sentry trace link in **Slack**, and approves or rejects in the dashboard's approvals queue.

## Our three differences

1. **Intent guards that fail closed.** Every step carries a plain-language intent plus pre- and post-checks: URL pattern, element role and accessible name, expected text or state change. A write or irreversible step runs only if its pre-check passes; otherwise the run stops and asks.
2. **Verified, step-local repair.** Only the failing step's intent, the guard failure and the current accessibility snapshot go to the model. The patch must pass the same post-check and lands as a versioned diff with rollback.
3. **A drift benchmark with a silent-failure metric.** Ten pre-registered page changes, four systems, and every count reported as it comes out. See [benchmark.md](benchmark.md).

**How to say it:** "Everyone fixes the crash. We catch the silent wrong click." Never say nobody does self-healing; most of the tools below do some version of it.

## Prior art

The build plan's comparison table is the reference ([build_plan.md → Why this is not a duplicate](build_plan.md#why-this-is-not-a-duplicate)). In short:

| Tool | What it does | What we add |
|---|---|---|
| Skyvern | Turns an agent run into generated code. If the cached code fails, it falls back to the agent and regenerates. | A check that a step still *means* the same before it runs; repair of one verified step instead of regeneration. |
| Stagehand | Caches act, observe and extract results. A cache miss triggers full LLM inference. | Meaning checks on cache hits; guarded writes. |
| Workflow Use | Deterministic workflow files with a fallback to Browser Use. In very early development. | Guards, verified repair, a benchmark. |
| taprun | Compiles a Browser Use history into a linear plan. `doctor` checks reads against a data source and skips writes. | Guards on DOM-only pages, and guarded writes with receipts. |
| LOOP Skill Engine | Linear templated skills from tool calls. Websites are not covered. | Everything that happens on a website. |
| Verifier pattern (Notte glossary) | A separate check that decides whether the agent finished. | Checks compiled into the program, before and after every step, plus receipts and repair. |
| Agent on every run | Pays the model on every run and trusts the agent's own success report. | Compile once, replay free, verify every step. |

Our research on Oct 17 found three more things, which the build plan doesn't cover yet. Re-check each before the pitch:

- **PreAct** ([arXiv 2606.17929](https://arxiv.org/abs/2606.17929)) is the closest research prior art.
  - It compiles a computer-use run into a state machine with screen-verification predicates (guards) and predicate branches, and replays with 0 LLM calls.
  - When a predicate fails, the full agent finishes the task and the whole program is recompiled.
  - From what we read, it doesn't tag write steps, check receipts or stop for a human. Those three are our answer if a judge brings it up.
- **Browser Use already ships `rerun_history()` / `load_and_rerun()`.**
  - It replays a saved history linearly, re-matching elements by hash, then XPath, then accessible name.
  - It is not LLM-free: extract steps and a final summary call the model.
  - It has no guards and no write checks.
- **Workflow Use's agent fallback is commented out** in the upstream source (`workflow/service.py`), even though the README advertises it.

## Scope

One flow, the eight-step eligibility check on three portals, polished end to end. The full lists are in [build_plan.md → Scope](build_plan.md#scope-core-wow-stretch-cut).

| Tier | When | Contents |
|---|---|---|
| **Core** | Running by hour 12 | Recorder, compiler, guarded executor, step-local healer with diff and rollback, 3 portals with mutation switch and audit log, benchmark harness (10 mutations × 4 systems), CLI, dashboard (program view with gold seam, live counters, approvals queue), Sentry, two hand-authored branches |
| **Wow** | Hour 18, started only after the 4 pm gate | A live split screen (blind replay vs. Browseen on the same mutated portal), a Slack human gate with a phone buzzing on the table, and a break-it panel |
| **Stretch** | Only after hour 20 | Branches learned by merging several recordings, a nightly `browseen doctor` GitHub Action, 1–2 real read-only public sites, the real Workflow Use or Stagehand as baselines |
| **Cut** | Never | Logins, CAPTCHAs, anti-bot defenses, multiple tabs, file uploads, real payer sites or patient data, fine-tuning, multi-user |

## The demo (2:30)

The full script with fallbacks is in [build_plan.md → Demo script](build_plan.md#demo-script-230). Its outline:

1. **0:00** Maria's story on a text card, with a phone face up on the table.
2. **0:25** Run 1: the Browser Use agent works while a timer and token counter climb. "The agent pays once."
3. **0:40** The compiled program, with intents, checks and read/write tags. "It wrote a program, not a recording."
4. **0:50** Run 2 finishes in about a second for $0.
5. **1:00** A judge picks a mutation and renames a button. One step turns **gold**, a diff appears, and the run finishes.
6. **1:25** A live split screen on mutation 9 (swapped Save/Submit):
   - Blind replay shows a green "Success" over a red "wrong action recorded".
   - Browseen stops, and the phone buzzes with the Slack alert.
7. **1:55** Maria approves in the queue, and the rerun passes the receipt check.
8. **2:10** The benchmark heatmap and one headline number: silent failures, baseline *k* of *N* vs. Browseen *k* of *N*.
9. **2:25** The Sentry trace with the healed step, then the identity sentence again.

## Tracks and prizes

| Challenge | Call |
|---|---|
| **Applied Intelligence** (main track) | Enter. The track text names automation and healthcare. |
| Browser Use, Best Use | Enter. It does the first run, and it is the fallback. |
| Sentry, Best Use | Enter. Tracing, AI agent monitoring, Session Replay and Logs. |
| Cognition, Best Use of Devin | Enter **only if** we really use Devin. Keep the sessions as proof. |
| MLH Commit Fellowship | Enter. It takes a 10-minute form. |
| Paper, Best Designed Hack / MLH Vultr | Optional |

The submission checklist, Devpost structure and judge Q&A are in [build_plan.md](build_plan.md#prize-stack).

## Top risks

| Risk | Fallback |
|---|---|
| Scope, which is the most likely way to lose | A hard **4 pm Saturday gate**; Wow is cut before Core |
| Guards too strict (constant LLM calls) or too loose (silent failures get through) | Deterministic checks first, fail closed on writes, report the false-alarm rate |
| A wrong heal | The patch must pass the recorded post-check on a dry run; writes are never healed blind; rollback |
| "The benchmark is rigged" | Commit the mutation list before the first run, let the judge pick live, report every cell |
| Wi-Fi or API outage on stage | A phone hotspot, cached results with a visible "cached" label, a 60-second backup capture |

The full table is in [build_plan.md → Risks and fallbacks](build_plan.md#risks-and-fallbacks).
