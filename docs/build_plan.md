# Kintsugi: safe replay for browser agents

Oct 17, 2026 · @Safkatul Islam

Build Kintsugi: a browser-agent compiler that replays for free, checks every step before and after it acts, and stops for a human when a page no longer means what it did. It enters Applied Intelligence with Browser Use, Sentry and Cognition stacked. This is version 2: the original core plus what the 2023 to 2025 LA Hacks winners had in common, which is a person in the first sentence, a visible output and a demo that runs live.

## The story

**Identity sentence:** Browser agents are right the first time and quietly wrong the hundredth. Kintsugi turns one agent run into a guarded program that replays for free, blocks when a page no longer means what it did, repairs only the cracked step, and asks a human before anything that writes.

**Opening, first 30 seconds (a story, not a feature list):** "Meet Maria. Every morning she checks insurance eligibility for thirty patients across three payer portals. One day a portal swaps its Save draft and Submit buttons. Her browser agent does not crash. It clicks Submit on a half-filled form, reports success, and nobody finds out until a claim bounces. Kintsugi is what stops that click." Maria is an illustrative character and the portals and patients are synthetic. No dashboard appears until after this story.

**Why the problem is real.** Context from others, each in its own domain; none of these are our results:

- taprun logged 15,455 executions of web-data automations. Errors from changed page structure outnumbered plain "element not found" 176 to 5, and one site returned empty results with no error on half its runs ([taprun](https://taprun.dev/blog/what-actually-breaks-15000-automations.html)).
- A Browserbase talk by Derek Meegan: 99% accuracy per step over 100 steps is about 36% end to end, and success should be confirmed against the system of record, not the agent's own report. His case study was a health-insurance portal download ([summary](https://www.sean-weldon.com/blog/2026-10-03-why-99-accurate-browser-agents-still-fail-derek-meegan-browserbase)).
- One developer reports about 40% of production Puppeteer agent sessions degrading silently ([AI Weekly](https://aiweekly.co/alerts/puppeteer-agent-silently-fails-40-of-production-runs)). That is a single Reddit anecdote: use it as color, never as a statistic.

**Named user:** front-desk staff at a small clinic who re-verify patient insurance eligibility on three payer web portals every morning. Same eight clicks each time, portals that often expose only a web form, and layouts that change without notice. Demo with synthetic patients on portals we build ourselves; no real patient data and no real payer sites. This ties us to the track's healthcare and automation language and answers "who would use this?"

**Visual signature:** the name comes from repairing a break with gold. The healed step gets a gold seam in the program view and in the diff, so a judge sees the repair at a glance. It is also our best answer to Paper's design criteria.

**Numbers rule:** quote only figures we measure ourselves. Outside figures are context and must name their domain. For example, the Compiled AI paper's break-even of about 17 runs is for function-calling workflows, not browsers.

## What last year's winners tell us

Eight overall winners from LA Hacks 2023 to 2025 share five habits, and version 2 is built around them. The sample is small and judges and tracks change every year, so treat this as a pattern, not a rule.

| Winner habit | Evidence | What Kintsugi does |
| --- | --- | --- |
| A person in the first sentence | Lumos (2025, 2nd) for Alzheimer's patients; DataGuardian (2023, 1st) for your data rights; HearShot (2023, 2nd) for local safety | Open with Maria; the dashboard comes after |
| A working flow with real integrations | Alto (2025, 1st) posts its findings to Slack and reads GitHub | Real Playwright runs, a real Slack alert, a real Sentry trace |
| An agent that acts on the web | DataGuardian; OpenSesame.Work (2025, 3rd) drives a browser to apply for jobs | Our first run is a Browser Use agent; we make agents like that safe to rerun |
| Sponsor tools on the critical path | Alto and Lumos won the Fetch.ai agents prize in 2025; Soundscape won Intel's challenge in 2024 | Browser Use, Sentry and Cognition are used for real, not just listed |
| Simple and finished | OpenSesame.Work placed third as a Browser Use app with retries | One flow polished; the Wow tier is cut before the core |

The gap: none of them reported measured results, and Alto labeled its replication step experimental. Our benchmark is the difference, but it supports the story and never replaces it. Sources: the [2025](https://la-hacks-2025.devpost.com/project-gallery), [2024](https://la-hacks-2024.devpost.com/project-gallery) and [2023](https://la-hacks-2023.devpost.com/project-gallery) project galleries and their winning project pages.

## Why this is not a duplicate

The existing tools fix loud failures, where a replay crashes and an LLM takes over. Kintsugi targets silent failures, where the replay succeeds and does the wrong thing, and it measures them.

| Tool | What it does today | What it lacks that we add |
| --- | --- | --- |
| [Skyvern](https://skyvern.com/docs/developers/features/code-caching) | Turns a successful agent run into generated code and replays it. AI fallback is on by default: if the cached code fails, it falls back to the agent and regenerates the code. An earlier docs snapshot also described progressive caching for conditional branches; the page I opened did not mention it, so verify before claiming either way. | No documented check that a step still means what it did before it runs; recovery regenerates code rather than repairing one verified step. |
| [Stagehand](https://docs.stagehand.dev/v4/best-practices/caching) | Caches act, observe and extract results. A miss or an unresolved selector triggers full LLM inference. The managed cache needs a Browserbase browser. | Cached replay runs with self-healing off, and a cache hit is not checked for correct meaning. |
| [Workflow Use](https://github.com/sauravpanda/workflow-use) (fork copy of the README) | Records a browser session into a deterministic workflow file and falls back to Browser Use if a step fails. README says very early development; self-healing and a better LLM fallback are unchecked roadmap items. | Guards, verified repair, any benchmark. Re-check the upstream repo before the pitch. |
| [taprun](https://taprun.dev/integrations/browser-use.html) | Compiles a Browser Use history into a linear replay plan. A `doctor` command compares against an authoritative data source and returns ok, stale or broken. Healing with cached patches is in the paid tier. Write actions are skipped by `doctor` because checking them has side effects. Its own 15,455-run study found changed page structure and silent empty results, not missing selectors, were the main failures. | Drift checks lean on sites with structured data feeds. Nothing for DOM-only pages, and nothing guarding write actions, which is where wrong clicks hurt. |
| [LOOP Skill Engine](https://arxiv.org/pdf/2605.14237) | Records tool calls into linear templated skills. Reports 93% to 99.98% token savings and about 8.7x lower latency on periodic tasks. The authors list linear-only skills and no output validation; drift detection is future work; websites are not mentioned. The 99% success figure is an argument, not a measurement. | Everything that happens on a website. |
| Verifier pattern (Notte glossary) | Describes a separate check that decides whether the agent finished, by deterministic checks or an LLM judge. The page does not say Notte ships one and mentions no replay or repair. | A verifier that is part of a compiled program: checks before and after each step, a receipt check against the portal's log, and a one-step repair loop. |
| Browser agent on every run (last year's OpenSesame.Work pattern) | Pays the model on every run and trusts the agent's own success report. Retries when it fails. | Compile once, replay free, and verify each step instead of trusting the report. |

**Our three differences:**

1. **Intent guards that fail closed.** Every step carries a plain-language intent plus checks on the page before and after (URL pattern, element role and accessible name, expected text or state change). Write and irreversible steps need the pre-check to pass, or the run stops and asks a human.
2. **Verified, step-local repair.** A failing step sends only its intent, the guard failure and the current accessibility snapshot to the model. The proposed patch must pass the same post-check, then lands as a versioned diff with rollback.
3. **A drift benchmark with a silent-failure metric.** Pre-registered mutations, four systems, counts reported as they are. See the benchmark section.

**Added in version 2: the receipt and the human gate.** A write step only counts as done when the portal's own audit log shows the matching record, which is the "verify against the system of record" advice from the Browserbase talk. When a step stops, a person gets the step's intent, a screenshot, the proposed diff and the trace link in Slack. taprun's doctor skips writes, and the verifier pattern in Notte's glossary covers outcome checks only, so neither combines a receipt check, a repair loop and a human gate.

**How to say it:** "Everyone fixes the crash. We catch the silent wrong click." Never say nobody does self-healing; four of the five rows above do some version of it.

**Re-check in hour one:** open taprun's and Skyvern's docs again. If either ships semantic guards, shift the emphasis to the benchmark.

## Scope: core, wow, stretch, cut

One flow working end to end beats four half-built ones, and the winners were simple but finished. Everything serves one eight-step eligibility check on three portals. Version 2 splits the work into Core, Wow and Stretch. Wow starts only after the 4pm gate and is cut before anything in Core.

**Core (running by hour 12):**

1. Recorder: run one Browser Use agent on a portal, save its step history with element locators, and tag each step read, write or irreversible.
2. Compiler: one LLM pass turns that history into a YAML program with, per step, an action, locator fallbacks, parameters, an intent sentence, pre-checks, post-checks, a receipt rule and a risk level.
3. Guarded executor on Playwright: deterministic checks first, an LLM judge only on write steps or when a locator still matches but its accessible name changed, and a receipt check on every write.
4. Step-local healer with a versioned diff and rollback.
5. Three portals with a mutation switch and a server-side audit log of every submitted action. The log is both the receipt and the benchmark's ground truth.
6. Benchmark harness: 10 mutations, 4 systems.
7. CLI: record, compile, run, doctor, heal, rollback.
8. Dashboard: program view with the gold seam on healed steps, live cost and time counters, and an approvals queue.
9. Sentry: Tracing, AI agent monitoring, Session Replay and Logs.
10. Two hand-authored branches: a consent banner that may or may not appear, and an extra confirmation page. Say they are authored by us, not learned.

**Wow (running by hour 18, started only after the gate):**

1. Live split screen: the same mutated portal, blind replay on the left and Kintsugi on the right, with an outcome auditor reading the portal's audit log. Blind replay shows a green Success over a red "wrong action recorded".
2. Human gate: on every stop, post to Slack through an incoming webhook with the step's intent, a screenshot, the proposed diff and the Sentry trace link. Approve and reject live in the dashboard; Slack buttons are stretch. A phone on the table buzzes during the demo.
3. Break-it panel: the judge picks any of the ten mutations, or Surprise me.

**Stretch (only after hour 20):**

- Learn branches by merging two or more recordings.
- A GitHub Action that runs kintsugi doctor nightly and opens an issue with the drift report, to show a team could adopt it.
- One or two real public read-only sites for credibility.
- The real Workflow Use or Stagehand as extra baselines.
- Voice escalation, only after reading the ElevenLabs challenge text and only if it honestly fits.

**Cut, do not touch:**

- Logins, CAPTCHAs and anti-bot defenses.
- Multiple tabs and file uploads.
- Any real payer site or patient data.
- Fine-tuning, model routing and multi-user features.

**Reuse rule:** the rules allow open-source work you disclose, but judges only score what was added during the event. The README needs a table of reused pieces (Browser Use, Playwright) against what we wrote this weekend.

## How it works

&#91;embedded content: Kintsugi flow · compile once, check every step, repair or stop\]

Compile once from a Browser Use run. Every replay checks each step before and after it acts. A failed check on a read step gets a one-step repair, highlighted in the diagram, that must pass the same check and is saved as a diff with rollback. A failed check on a write or irreversible step stops for a human.

## Technical design

One pipeline, one file format and four interfaces. Freeze the interfaces early so four people can work in parallel. Everything here is our own design, so check each library detail against the installed version.

| Layer | Choice | Note |
| --- | --- | --- |
| Runtime | Python 3.12 with uv, Playwright | Pin the installed browser-use version. In hour one confirm it exposes step history with element data and a rerun method |
| Models | One thin client; a frontier model to compile and heal, a cheap fast model as the judge | Log tokens and dollars per call; they feed the cost counters |
| Portals | FastAPI with Jinja templates and SQLite | Three layouts from one generator; every action writes to an audit table |
| Dashboard | React, Vite and Tailwind; server-sent events for live updates | The approvals queue lives here |
| Observability | Sentry Python SDK on the runner, browser SDK on the portals | One span per program step |
| Notifications | Slack incoming webhook | Posts step intent, screenshot, diff and trace link |
| Hosting | Local for the demo; Vultr for portals and runner if time allows | The demo must not depend on it |

**Program format.** One YAML file per flow. The version number goes up on every accepted repair and each version is stored, so a rollback is a file swap.

```yaml
program: eligibility-check
version: 3
steps:
  - id: s5
    intent: "Submit the eligibility request for the selected patient"
    risk: write                 # read | write | irreversible
    action: {type: click, target: {role: button, name: "Check eligibility"}}
    locators: [role_name, text, css, xpath]     # tried in order
    pre:
      - url_matches: "/portal-a/eligibility"
      - element: {role: button, name: "Check eligibility", enabled: true}
      - fingerprint: "form#elig > fieldset(3) > button[type=submit]"
    post:
      - text_visible: "Request received"
      - receipt: {source: audit_log, match: {action: eligibility_submit, patient: $patient_id}}
    on_fail: {read: heal, write: stop_and_ask, irreversible: stop_and_ask}
```

**Guard order for every step**

1. Resolve the target with the locator list. No match fails the step.
2. Run the deterministic pre-checks: URL, role and accessible name, structural fingerprint.
3. A locator that matches but whose name or fingerprint changed goes to the judge with the step's intent. On a read step, a "still means the same" verdict continues. On a write or irreversible step the default is stop and ask.
4. Act.
5. Run the post-checks, then the receipt check for write steps.
6. On any failure, read steps go to the healer; write and irreversible steps stop and ask.

**Healer contract.** Input: the step's intent, the failing check, the previous locators and a trimmed accessibility snapshot of the current page. Output: one patched step. The patch runs on a dry run and must pass the same post-check. If it does, the program version goes up and the diff is stored. If not, the step stops and asks. Rollback restores the previous version file.

**Ground truth and receipts.** Each portal appends a row to its audit table for every submit (action, patient id, request id, time) and shows the request id on screen. The harness reads that table directly. The agent's own success report is never used to score a run.

**Mutation switch.** Every portal reads a mutation number from a query parameter or header and applies it in the template layer, so a mutation is a flag, not a fork. The list of ten is committed before the first benchmark run.

**Repo layout**

```
kintsugi/
  recorder/  compiler/  executor/  guards/  healer/
  portals/   a/ b/ c/ mutations.py audit.py
  bench/     mutations.md run.py report.py
  dashboard/ cli.py README.md
```

**Interfaces to freeze early**

- Audit-log schema: owned by C, frozen by 14:00.
- Program YAML schema: owned by B, frozen by 14:30.
- Event stream, JSON lines for step started, check passed, check failed, healed and stopped: emitted by A, consumed by D.
- Approval API (list stops, approve, reject): owned by A and D together.

## The benchmark

The benchmark is the part a judge cannot dismiss as a toy: ten pre-registered page changes, four systems, and one headline number, the share of runs that finish and report success while doing the wrong thing. Benchmark advice for self-healing tools says to test changes of increasing severity and report the heal rate at each level; we add the silent-failure count.

| # | What changes on the portal | Severity | Silent? | What we expect Kintsugi to do |
| --- | --- | --- | --- | --- |
| 1 | CSS classes and element IDs renamed | 1 | No | Replay unchanged, zero LLM calls |
| 2 | Siblings reordered, button moves position | 1 | No | Replay unchanged via role and name |
| 3 | Button label renamed ("Check eligibility" to "Verify coverage") | 2 | No | Guard flags, one-step heal |
| 4 | Button moves into an overflow menu | 2 | No | One-step heal |
| 5 | Form wrapped in an iframe | 2 | No | One-step heal |
| 6 | Consent banner appears | 2 | No | Take the hand-authored branch |
| 7 | Extra confirmation page inserted | 2 | No | Branch or one-step heal |
| 8 | Result table columns reordered | 3 | Yes, wrong data | Post-check catches the mismatch, heal or escalate |
| 9 | Two adjacent buttons swap labels ("Save draft" and "Submit") | 3 | Yes, wrong action | Pre-check blocks the write, escalate |
| 10 | Same label, new meaning ("Archive" becomes "Delete" in the sandbox) | 3 | Yes, destructive | Pre-check blocks the write, escalate |

The last column is our hypothesis, not a result. Report what actually happens.

**Four systems compared:**

- **A. Agent every run:** Browser Use drives the whole flow each time.
- **B. Blind replay:** recorded selectors, no checks. Our own reimplementation of the linear-replay strategy; label it that way.
- **C. Cache and fall back:** B plus a full agent rerun after any exception. Our reimplementation of the strategy Skyvern, Stagehand and Workflow Use describe; label it that way and do not claim to have benchmarked those products.
- **D. Kintsugi.**
- **E (stretch):** the real Workflow Use or Stagehand on a subset.

**Metrics:**

1. **Silent failure rate (headline):** the run reports success but the portal's own server-side log or the extracted data says otherwise. Ground truth comes from the portal, never from the agent's claim.
2. **Correct completion rate.**
3. **Escalations:** runs where Kintsugi stopped and asked a human. Counted as safe, not as success.
4. **False alarms:** heals or blocks triggered on harmless mutations 1 and 2 and on the unchanged control.
5. **LLM tokens, dollars and wall-clock seconds per run.**
6. **Break-even run count:** compile cost divided by the per-run saving.

**Added in version 2:** two more numbers, both read straight from the audit log. Receipt failures caught: steps where the page looked right but the log had no matching record. Escalation precision: of all stops, how many were genuine wrong clicks and how many were unnecessary.

**Run plan:** 10 mutations x 4 systems x 5 trials is 200 runs, plus 10 unmutated control runs per system. LLM runs are nondeterministic, so show counts like 4/5, not percentages. Agent runs are the expensive column: set a dollar cap and a step cap before starting, and run trials in parallel.

**Honesty rules:**

- Commit the mutation list before the first run and mention the commit in the README.
- Report every cell, including the ones where Kintsugi fails.
- Let the judge pick a mutation live from the same list.
- Targets, not promises: mutations 1 and 2 cost no LLM calls, most severity 2 changes heal in one step, and severity 3 produces zero silent failures. If the numbers come out worse, that is still the story.

## Demo script, 2:30

One script serves the live pitch and the 2 to 3 minute Devpost video. Version 2 opens with Maria, not the product, and the middle of the demo is a live split screen plus a phone that buzzes.

| Time | What the room sees | What you say | If it breaks |
| --- | --- | --- | --- |
| 0:00 | One text card with Maria's morning; a phone face-up on the table | The Maria story from the first section, about 25 seconds | Static card |
| 0:25 | Run 1: a Browser Use agent works on Portal A while a timer and token counter climb; Kintsugi records | "The agent pays once." | Clip of run 1 |
| 0:40 | The compiled program: steps with intents, checks and read or write tags | "It wrote a program, not a recording." | Screenshot |
| 0:50 | Run 2 finishes in about a second; the counter shows $0 | "Now it replays free." | Cached run, labeled |
| 1:00 | A judge picks a mutation from the panel. Rename a button: one step turns gold, a diff appears, the run finishes | "It repaired only that step and proved the repair." | Cached heal, labeled |
| 1:25 | Live split screen on mutation 9, the swapped buttons: blind replay shows a green Success over a red "wrong action recorded"; Kintsugi stops; the phone buzzes with the Slack alert | "Replay did not crash. It clicked Submit. Kintsugi stopped and asked Maria." | Pre-recorded split screen and a screenshot of the Slack message |
| 1:55 | Maria's view: the approvals queue shows the intent, screenshot and diff; click Approve; the rerun passes the receipt check | "A person decides, and the program keeps the fix." | Cached approval, labeled |
| 2:10 | Benchmark heatmap with one headline number | "Silent failures: baseline k of N, Kintsugi k of N." Fill in the real numbers | Slide |
| 2:25 | Sentry trace with the healed step highlighted | The identity sentence again | Screenshot |

**Rules for the room:**

- The judge chooses from the mutation panel, not free-form edits. If a judge insists on a free-form edit, say the system falls back to the full agent or escalates, and treat that as part of the demo.
- Record the 60-second backup capture first. Wi-Fi fails at events; the venue lists UCLA\_WEB, UCLA\_WIFI and eduroam inside, so bring a phone hotspot.
- Any cached result shown on stage carries a visible "cached" label. Never present cached output as live.
- Rehearse the first 30 seconds out loud until it is automatic.
- Reserve at least 20 minutes before the deadline for the demo plan and video; submit early.
- Say the weakness before a judge asks: logins, CAPTCHAs and anti-bot defenses are out of scope, and a wrong write is stopped, not guessed.

**Added in version 2:** keep Slack open on the phone with the sound on, and keep a screenshot of the message in case signal fails; the webhook also posts to the dashboard feed, so the stop is visible either way. The room sees no dashboard until the story is done.

## Judge questions

Expect these. A judge who wrote up a year of scoring says the questions that decide scores are usually who it is for, what was built this weekend, and what breaks first, and that naming a real weakness raised scores.

| Question | Answer |
| --- | --- |
| How is this different from Skyvern, Stagehand or Workflow Use? | They recover when a replay crashes. We catch replays that succeed and do the wrong thing, repair one verified step, and measured it on ten pre-registered changes. |
| Who is it for? | Front-desk staff re-verifying insurance eligibility on several payer web portals every morning. |
| What did you build this weekend? | The compiler, the guards, the healer, the portals, the benchmark and the dashboard. We reused Browser Use for the first run and Playwright for execution. |
| How do you know a heal is right? | The patched step must pass the same post-check that was recorded for it, and the change lands as a diff with rollback. Write steps are never healed blind; they stop and ask. |
| Isn't the benchmark rigged since you built the sites? | The mutation list is committed before any run, you pick the mutation live, and we report every cell including failures. Stretch: a subset on real public sites. |
| What breaks first? | Logins, CAPTCHAs and anti-bot defenses are out of scope. Guards can also be too strict, which costs LLM calls; we report the false-alarm rate. |
| Do the savings hold up? | We report our own break-even run count and per-run cost, not outside figures. |
| Why not use an API? | Many portals offer only a web form, and this works where no API exists. Do not claim that no payer has an API. |
| What happens to credentials and patient data? | Neither is in scope. The demo uses synthetic patients on portals we built. |
| Why Browser Use? | It produces the first-run trajectory we compile, and Kintsugi falls back to it when a step cannot be repaired. |
| Isn't this just Playwright tests with assertions? | Nobody writes the checks. They are compiled from one agent run with an intent per step, and a failed read step is repaired and re-verified. Hand-written tests only tell you it broke. |
| taprun already has a doctor command. Why yours? | Its doctor checks reads against a data source and skips writes because checking them has side effects. We guard writes by failing closed and confirm them against the portal's audit log. |
| How do you know a stop was the right call? | We report escalation precision from the audit log: stops that prevented a wrong action versus unnecessary stops. |
| Isn't 99% accuracy good enough? | At 99% per step, 100 steps succeed about 36% of the time, according to a Browserbase talk on a different domain. We measure our own eight-step flow. |

**Answer pattern:** one sentence, one specific number or fact, then stop.

## Prize stack

Enter the main track plus three company challenges that the core build already satisfies: Browser Use, Sentry and Cognition. Add Commit Fellowship, which costs only a form. The rest are optional or skipped. Build the project to win outright; the sponsor entries should cost little extra work.

| Challenge | Why it fits | What to show | Effort | Call |
| --- | --- | --- | --- | --- |
| Applied Intelligence (main track) | Track text names automation and healthcare and asks for practical tools. | The clinic eligibility flow, the benchmark, the demo. | Framing only | Enter |
| Browser Use, Best Use | Asks for an agent that turns a goal into action on the web, a working demo, and the intended audience. We use its agent for the first run and as the fallback. | Run 1 on Browser Use, compile, replay, repair. | None beyond core | Enter |
| Sentry, Best Use | Needs at least two products beyond error monitoring. First place gets guaranteed interviews for every team member. | See the Sentry setup below. | About 2 hours | Enter |
| Cognition, Best Use of Devin | Judged on creativity, novelty and polish. First place wins $5,000 in Devin credits and every team gets free credits. | Use Devin for parallel chores: portal generator, benchmark scaffold, README. Keep the sessions as proof. | Low to medium | Enter, only if you really use it |
| MLH Commit Fellowship | Needs a working prototype with a team and a real problem. | Opt in on Devpost, then fill the supplemental form. | 10 minutes | Enter |
| Paper, Best Designed Hack | Judged on design fundamentals, ease of use and personal craft. | The program view, gold seam, diff and split screen. | Medium | Only if one teammate owns design |
| MLH Best Use of Vultr | Hosting the portals and benchmark runner there is a real use. | Portals and runner deployed on Vultr. | Low | Optional |
| StepFun, Get It Done | The app must call step-5-preview when it runs. Judged on reliability and on whether users can understand and control the workflow. | Step 5 Preview as the guard judge or healer. | Unknown model quality | Skip unless a 15-minute test works |

**Sentry setup (the one with specific requirements):**

- Use at least two of Tracing, AI agent monitoring, Session Replay, Logs, and aim for all four.
- Python SDK: enable tracing with a sample rate above zero; the SDK instruments supported AI libraries automatically, and agent runs can be wrapped with manual `gen_ai.invoke_agent` spans.
- One custom span per program step with attributes for step id, guard result and healed or not. The healer's LLM call becomes a child agent span, so a judge can open the trace and see exactly which step cracked and what repaired it.
- Session Replay: add the browser SDK to the portals we build so the agent's clicks replay. Replay masks text and inputs by default; check the docs for loosening that on our own pages.
- Logs: one line per guard decision.
- Sentry asks to see how observability shaped the build. Keep a running build log and write down real moments, such as a trace that showed where time went. Do not invent them afterward.

**Skipped, no honest fit:** Fetch.ai, Base44, QNX, Workday, Even Realities, Photon, Visa, Intuit, Espressif, Creao, veri.studio, ElevenLabs, Solana, Tiger Data, Snowflake, GoDaddy, Gemini.

**Check at the info desk:**

- Paper's amount differs between pages: the tracks page says up to $1,500, Devpost lists $3,000.
- Devpost shows Cognition with 5,000 winners, which looks like a typo for credits.
- Devpost lists no amounts for Browser Use or Sentry; ask.
- Main-track prizes read "To Be Determined."
- Ask whether there is a cap on company challenges per team.

**Submission checklist:**

- [ ] Public GitHub repo with run steps and a reused-versus-new table in the README
- [ ] Demo video, 2 to 3 minutes
- [ ] Devpost page: summary, technologies, track, and one paragraph per company challenge on how we apply to it
- [ ] Commit Fellowship opt-in plus the supplemental form
- [ ] Confirm the deadline: the Devpost header says Oct 18, 12:00pm PDT, but the rules page still shows April 26, 8am
- [ ] Be present in person for judging

## Devpost write-up

Mirror the structure the 2025 first-place project used, because judges have read many of them. Each part has one job.

1. Inspiration: Maria, plus the two outside data points with their domains named.
2. What it does: record once, replay free, block on a changed meaning, repair one step, ask a human before writes.
3. How we built it: the pipeline in one paragraph and the reused-versus-new table.
4. Challenges: guard tuning (too strict costs LLM calls, too loose lets silent failures through) and what we changed.
5. Accomplishments: the headline number, the false-alarm rate and the cells where we failed.
6. What we learned: one real build-log moment, including one from Sentry.
7. Competitors we studied: Skyvern, Stagehand, Workflow Use, taprun, LOOP and the verifier pattern, one sentence each on what they do and what we add.
8. What's next: the nightly drift-check GitHub Action and a pilot with a clinic team.
9. One paragraph per company challenge: Browser Use, Sentry, Cognition, Commit Fellowship, plus Vultr and Paper if entered.

Built With: Python, Playwright, Browser Use, FastAPI, React, Sentry, Slack, Devin.

## 24-hour plan

The plan has one hard gate at 4pm Saturday: if one flow cannot be recorded, compiled, replayed and healed by then, cut scope or switch ideas. Times assume hacking starts around noon Saturday and the Devpost deadline is Sunday noon; adjust after the opening ceremony and confirm that the venue stays open overnight, since the schedule page said "coming soon."

**Roles for four people (three: person C also takes D's Sentry work):**

- A, runtime: executor, guard engine, healer, diff and rollback, receipt check; emits the event stream and the approval API.
- B, capture: Browser Use recorder, compiler, YAML schema, CLI and the two hand-authored branches.
- C, sites and benchmark: three portals with audit log and mutation switch, the harness, the overnight runs and the Vultr deploy.
- D, product and story: dashboard, approvals queue, Slack, Sentry, README, Devpost, demo and video.
- With three people: C also takes Sentry, and the break-it panel and Slack move to Stretch.
- Start Devin sessions in the first hour for the portal generator and the harness scaffold, and keep them as proof for the Cognition challenge.

| When | Milestone | Done when |
| --- | --- | --- |
| Sat 12:30 to 14:00 | Setup and freeze | Repo, keys, Sentry project and Browser Use version check done. Identity sentence, mutation list and audit-log schema frozen. Devin sessions started. Talk to Browser Use and Sentry staff. |
| Sat 14:30 | Schema freeze | Program YAML schema frozen and the first recording of the eligibility flow saved. |
| Sat 16:00 | Go or no-go gate | One flow recorded, compiled and replayed deterministically on portal A, and one severity 2 mutation healed with a passing post-check. If missed: drop the Wow tier, the branches and the LLM judge, and keep deterministic guards. Still missed by 18:00: switch to Agent Bisect, idea 3. |
| Sat 20:00 | Guards and receipts | Deterministic guards and the receipt check work. Mutations 1, 3 and 9 are in the harness. Sentry traces are visible. The dashboard shows the program view. |
| Sat 23:00 | Wow v1 | The live split screen runs against mutation 9, the Slack alert posts, and the Approve button resumes the run. |
| Sun 02:00 | Full harness | All ten mutations across systems A to D run end to end at a small trial count. Break-it panel works. Sleep rota starts. |
| Sun 05:00 | Core freeze | No new features. The full benchmark runs under the dollar cap. Fix only the top failure causes. B and D draft the README and Devpost page. |
| Sun 07:30 | Everything frozen | Record the 60-second backup. Fill the README and Devpost with the real numbers. |
| Sun 09:00 | Rehearse | Three full run-throughs, then record the video. |
| Sun 10:30 | Submit | Ninety minutes before the deadline. |
| Sun 12:00 | Deadline | Confirm the time on Devpost. |

**Working rules:**

- Keep the main branch runnable at all times; risky work goes on feature branches.
- Mock only what is not core, such as the portals. Never mock the compile, guard or heal steps; judges can tell.
- Use coding agents and Devin for the portals, harness scaffolding and README, and keep every teammate able to explain the core code. If you cannot explain a piece in the demo, judges notice.
- At each milestone, ask whether we still have the identity sentence; if a feature does not serve it, cut it.

## Stress test of this version

The most likely way to lose is scope, not competitors. Each attack below has a verdict and a fix that is already in the plan.

| Attack | Verdict | Fix |
| --- | --- | --- |
| "It is infrastructure; the winners had a person." | A real risk if the slides lead with the dashboard | Maria opens the demo; no dashboard in the first 30 seconds |
| "Skyvern, Stagehand and taprun already cache and heal." | True for loud failures. Our gap is silent failures, writes and measurement | Re-check their docs in hour one. If any ships semantic guards, lead with the benchmark and the receipt check |
| "Your benchmark is rigged because you built the portals." | Fair | Commit the mutation list first, the judge picks live, report every cell, real public sites as stretch, claim only what we tested |
| "Four people, 24 hours, ten Core items and three Wow items." | The most likely way to lose | The 4pm gate; Wow is cut before Core; every item has an owner and a cut line |
| "LLM runs are noisy, so your numbers mean nothing." | Fair for percentages | Show counts like 4/5 over five trials, fix the prompts, report variance honestly |
| "A wrong heal is worse than a crash." | True | The patch must pass the recorded post-check on a dry run; writes are never healed blind; rollback |
| "The demo depends on Wi-Fi and a phone." | True | Phone hotspot, cached results labeled, backup video, a screenshot of the Slack message |
| "Another team builds a Browser Use agent for the same challenge." | Likely | We are the layer under their agent; our proof is the benchmark and the receipt check |

## Risks and fallbacks

The biggest risks are guard tuning and the live demo, so both get explicit fallbacks.

| Risk | Why it matters | Fallback |
| --- | --- | --- |
| Guards too strict | Constant LLM calls erase the savings | Deterministic checks first; tune on mutations 1 and 2; report the false-alarm rate |
| Guards too loose | Silent failures get through, which is the whole pitch | Pre-check on every write step; fail closed and escalate |
| Heal produces a wrong patch | A bad repair is worse than a crash | Patch must pass the recorded post-check; diff with rollback; writes never healed blind |
| Branches cannot be learned from one run | Overclaiming gets caught | Hand-author two branches and say so; learning from several runs is stretch |
| Wi-Fi or API outage on stage | A dead demo removes judges' trust | Phone hotspot, cached results with a visible label, 60-second backup capture, Devpost video |
| Judge edits the page in a way we did not plan | A failed heal on stage hurts | Mutation menu first; for free-form edits, show fallback to the full agent or escalation as designed behavior |
| Sites we built look like a toy | Perceived rigging | Mutation list committed before runs, judge picks live, one or two real public read-only sites as a stretch |
| Browser Use API differs from what we expect | Hour-one surprise | Check the installed version at setup; pin versions |
| Benchmark cost or rate limits | LLM runs are the expensive column | Dollar and step caps set first; spread keys across teammates; cache compile outputs |
| Scope creep | The usual killer | Hour-16 core freeze; identity sentence checked at each milestone |
| Burnout | Bugs spike after midnight | Sleep rota; the person writing the Devpost page is not the one running the benchmark |
| Another team builds the same idea | Likely at a Browser Use challenge | Our difference is guards and the benchmark, so finish those before polish |
| Wow tier eats the core | Slack, the split screen and the break-it panel compete for the same hours | Wow starts only after the 4pm gate. Cut order: Slack buttons, break-it panel, split-screen polish; then stop adding |
| Receipts exist only on portals we built | Looks rigged to a skeptical judge | Say plainly that a receipt check needs a system of record; add one or two real public read-only sites as a stretch |

## Sources

Opened in full on Oct 17, 2026:

- [LA Hacks tracks and company challenges](https://live.lahacks.com/tracks)
- [LA Hacks Devpost page: criteria, requirements, prizes](https://la-ai-hackathon-2026.devpost.com/)
- [Skyvern code caching](https://skyvern.com/docs/developers/features/code-caching)
- [Stagehand caching](https://docs.stagehand.dev/v4/best-practices/caching)
- [taprun with Browser Use](https://taprun.dev/integrations/browser-use.html)
- [Workflow Use README (fork copy)](https://github.com/sauravpanda/workflow-use)
- [LOOP Skill Engine paper](https://arxiv.org/pdf/2605.14237)
- [How to Win Hackathons, Browser Use](https://browser-use.com/posts/how-to-win-hackathons)
- [What Judges Actually Score, DEV Community](https://dev.to/kurbaitaev/what-judges-actually-score-notes-from-a-year-of-hackathon-judging-3p4l)

Read only as search results, not opened in full; check before quoting:

- [Sentry AI agent instrumentation, Python](https://docs.sentry.io/platforms/python/tracing/instrumentation/custom-instrumentation/ai-agents-module/)
- [Sentry Session Replay setup](https://docs.sentry.io/platforms/javascript/session-replay)
- [Compiled AI paper](https://arxiv.org/abs/2604.05150)
- [Agentic QA benchmark: self-heal rate under UI change](https://dev.to/manavshiplightai/agentic-qa-benchmark-how-to-measure-what-matters-2026-21bg)

The Sentry and Cognition challenge descriptions were read from the Google Docs linked on the tracks page.

Opened in full for version 2 on Oct 17, 2026:

- [taprun: what actually breaks in 15,000 automations](https://taprun.dev/blog/what-actually-breaks-15000-automations.html)
- [Why 99% accurate browser agents still fail, summary of Derek Meegan's Browserbase talk](https://www.sean-weldon.com/blog/2026-10-03-why-99-accurate-browser-agents-still-fail-derek-meegan-browserbase)
- [AI Weekly: Puppeteer agent silently fails 40% of production runs](https://aiweekly.co/alerts/puppeteer-agent-silently-fails-40-of-production-runs)
- [Notte glossary: what is a verifier in browser agents](https://www.notte.cc/glossary/ai-browser-agents/what-is-a-verifier-in-browser-agents)
- LA Hacks winners: [Alto](https://devpost.com/software/alto), [Lumos](https://devpost.com/software/lumos-f8h0mn), [OpenSesame.Work](https://devpost.com/software/opensesame-work), [MarkedDown](https://devpost.com/software/markeddown), [FormFixer](https://devpost.com/software/formfixer-a7txz8), [Soundscape](https://devpost.com/software/soundscape-u19mo7), [DataGuardian](https://devpost.com/software/dataguardian), [HearShot](https://devpost.com/software/hearshot)
