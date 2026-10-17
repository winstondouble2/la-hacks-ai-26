# Project Overview: Self-Healing Agent Compiler

> The first time a browser agent does a task, compile what it did into a program. Replay it instantly and cheaply afterwards, and when the website changes, repair only the step that broke.

LA Hacks AI Hackathon 2026 (UCLA, Oct 17–18, 2026). This is idea #2 from our idea shortlist.

## The problem

LLM browser agents such as Browser Use can do almost any web task, but they **re-think every step on every run**. A task the agent has already solved costs the same tokens and the same seconds the hundredth time as the first. That makes them a poor fit for the work people actually want to automate, which is repetitive: weekly reports, form submissions, order checks, data entry.

The usual fix is record-and-replay: save the actions once and replay them without the LLM. Replay is fast and cheap, but brittle. A renamed button, a new cookie banner or a moved field breaks it, and it either crashes or, worse, clicks the wrong thing. Then you're back to running the expensive agent from scratch.

## Our idea

Treat the LLM agent as an **interpreter** and add a **JIT compiler** on top:

1. **Record.** The first run is a normal Browser Use agent run, and we record every step it takes.
2. **Compile.** We turn that trajectory into a program with **branches** (optional popups, loops, site variants) and **guard checks** (is the page in the state this step expects?) before and after each step.
3. **Replay.** Later runs execute the program directly with Playwright: no LLM calls, about a second instead of tens of seconds.
4. **Heal.** When a guard fails because the page changed, **only that step** falls back to the LLM (deoptimization). The LLM patches that step, the patch is verified, the program becomes v2, and the run continues compiled.

The analogy is a JIT compiler with deoptimization: fast compiled code guarded by cheap checks, with a fallback to the slow general path only where an assumption broke. [architecture.md](architecture.md) has the full design.

## Prior work and the gap

| Work | What it does | What it lacks (our angle) |
|---|---|---|
| **LOOP Skill Engine** (preprint, May 2026, [arXiv 2605.14237](https://arxiv.org/abs/2605.14237)) | Records an agent's tool calls on the first LLM run, turns them into a parameterized **linear** "skill", and replays it with no LLM calls. Reports 93%–99.98% token savings and 7.82 s → 0.90 s mean latency (~8.7×). | The authors list the limits themselves: linear skills only (no branches), no output validation, no drift detection or automatic re-recording. It was tested on periodic tasks in one agent framework, not on websites, and its "99% success" figure is not measured end to end. |
| **taprun** ([Browser Use integration](https://taprun.dev/integrations/browser-use.html)) | Record-and-replay for agents with a Browser Use integration. | We need to confirm exactly what it covers (branches? healing?). See the prior-art notes in [tech-stack.md](tech-stack.md#prior-art-to-check-and-differentiate-from). |

**Our gap:** compiled programs with **branches and guard checks**, plus **step-level LLM repair** that is verified and versioned, measured end to end on a **benchmark of deliberately modified pages** against both linear replay and an "LLM every time" baseline.

## What we'll show

1. **Cost and latency per run.** The first (LLM) run vs. a compiled run: tokens, dollars, seconds.
2. **Robustness.** Verified success rate on a set of deliberately modified pages: ours vs. LOOP-style linear replay vs. the agent running from scratch every time.
3. **Healing cost.** How many LLM calls and dollars a heal takes compared with re-running the whole agent.

## Demo (about 3 minutes)

1. **The first run is slow.** We give the agent "Buy 2 Blue Mugs on the demo shop", and the dashboard ticks up live token, dollar and time counters.
2. **Compile.** The program appears as a step graph with its guards and branches.
3. **The second run is instant.** It finishes in about a second for $0.00, with both runs side by side.
4. **A judge breaks the site.** In the testbed's chaos panel, a judge renames "Add to cart" to "Add to bag" and moves it into a menu.
5. **It heals.** On the next run one step turns red, then amber as it heals with a single LLM call, then green. The run finishes, and the dashboard shows the v1 → v2 diff plus the Sentry trace and session replay of the heal.
6. **The numbers.** The benchmark chart: success rate and cost across the three approaches.

## Hackathon tracks

| | Track | Why we fit |
|---|---|---|
| **Main track** | Applied Intelligence (automation) | We make browser automation cheap and reliable enough to run repeatedly. |
| Company track | Browser Use | Browser Use is our "interpreter" and the tier-3 healer. |
| Company track | Sentry | Tracing (one span per step, heals visible) + Session Replay of the agent's browser + AI agent monitoring. The track requires using two Sentry products beyond error monitoring. |
| Company track | Cognition | Only if we build parts with Devin. |

Track requirements and judging criteria are collected in [hackathon-plan.md](hackathon-plan.md).

## Needs and risks

| Risk | Mitigation |
|---|---|
| Overlap with taprun / LOOP | Our differentiators are branching and self-healing, backed by the modified-page benchmark. Lead every pitch with them. |
| The judge's live edit is something we never planned for | The chaos panel offers a menu of mutations we tested, and tier 3 (scoped agent) is the catch-all. |
| A lucky pass after a heal | Postconditions on every step plus a task-level `success` check. We report false passes. |
| Third-party sites are flaky, have CAPTCHAs, or change mid-demo | Demo and benchmark only on **testbed sites we control**. A real site is a bonus slide at most. |
| API spend on the benchmark | Set a budget up front, cache the LLM baseline runs, and keep the matrix small. |
| Conference Wi-Fi | Run everything on localhost. Only LLM calls need the network, and we keep a recorded video backup of the demo. |

## Inputs we start from

- Browser Use, an LLM API key, and a few test websites that we control and can modify.
- References: [LOOP Skill Engine](https://arxiv.org/abs/2605.14237) · [taprun × Browser Use](https://taprun.dev/integrations/browser-use.html)
