"""Span helpers for the compiler. One transaction per run, one span per step.

Names follow docs/architecture.md (Observability). Span data keys:
  step.id          the program's step id (s1, s4a, …)
  mode             "llm" (recording run) | "compiled" (replay) | "healed" (step was repaired)
  program.version  version of the compiled program being run
  guard.result     "pass" | "fail"
  heal.tier        1 local, 2 one LLM patch, 3 scoped agent (only on healed steps)

  heal.verified    the patch passed the step's own post-check (heal spans)
  run.id, program  run and program the trace belongs to (run tags, optional)

Agent runs use agent_span (op gen_ai.invoke_agent) so they appear in Sentry's
AI Agents dashboard; custom ops like agent.llm do not.

Every helper is a no-op when Sentry is not initialized (no SENTRY_DSN), so the
runtime never depends on it. Never pass raw DOM, form input values, credentials
or patient data as attributes: ids, check short forms and reasons only.

Try it without the agent: python -m browseen.tracing [heal1|heal2|heal3|blocked]
"""

import json
from contextlib import contextmanager

import sentry_sdk


@contextmanager
def run_span(task: str, mode: str, program_version: int | None = None,
             run_id: str | None = None, program: str | None = None):
    with sentry_sdk.start_transaction(op="agent.run", name=f"run:{mode}") as txn:
        txn.set_tag("mode", mode)
        txn.set_data("task", task)
        if program_version is not None:
            txn.set_tag("program.version", program_version)
        if run_id is not None:
            txn.set_tag("run.id", run_id)
        if program is not None:
            txn.set_tag("program", program)
        yield txn


@contextmanager
def step_span(index: int, action: str, mode: str, target: str = "", step_id: str | None = None):
    """step_id is the program's id (s1, s4a, …); defaults to s<index+1>."""
    step_id = step_id or f"s{index + 1}"
    with sentry_sdk.start_span(op="agent.step", name=f"{step_id}:{action}") as span:
        span.set_data("step.id", step_id)
        span.set_data("step.index", index)
        span.set_data("step.action", action)
        span.set_data("step.target", target)
        span.set_data("mode", mode)
        span.set_data("guard.result", "pass")
        yield span


def log_check(span, step_id: str, check: str, passed: bool, detail: str = "") -> None:
    """Record one guard decision: a Sentry log line (info on pass, warning on
    fail) linked to the current trace, and guard.result=fail on the step span.

    check is the check's short form, e.g. 'pre url_matches /product\\.html'.
    """
    if not passed:
        span.set_data("guard.result", "fail")
    log = sentry_sdk.logger.info if passed else sentry_sdk.logger.warning
    log(
        "check {result} {step_id}: {check} {detail}",
        result="passed" if passed else "failed",
        step_id=step_id,
        check=check,
        detail=detail,
    )


def mark_healed(span, reason: str, tier: int) -> None:
    span.set_data("mode", "healed")
    span.set_data("guard.result", "fail")
    span.set_data("heal.tier", tier)
    span.set_data("heal.reason", reason)
    txn = sentry_sdk.get_current_scope().transaction
    if txn is not None:  # None outside run_span, or when Sentry is off
        txn.set_tag("heal.tier", tier)
    sentry_sdk.logger.warning("step healed (tier {tier}): {reason}", tier=tier, reason=reason)


@contextmanager
def heal_span(step_id: str, tier: int):
    """Time one healing attempt (tier 1 local, 2 LLM patch, 3 agent takeover)
    as a child of the step span. Call record_heal_result when it is decided;
    an attempt that never records a result counts as not verified."""
    with sentry_sdk.start_span(op="agent.heal", name=f"heal {step_id} tier {tier}") as span:
        span.set_data("step.id", step_id)
        span.set_data("heal.tier", tier)
        span.set_data("heal.verified", False)
        sentry_sdk.logger.info("heal attempted {step_id}: tier {tier}", step_id=step_id, tier=tier)
        yield span


def record_heal_result(span, step_id: str, tier: int, verified: bool, reason: str = "") -> None:
    """verified means the patch passed the step's own post-check, not just that it ran."""
    span.set_data("heal.verified", verified)
    if reason:
        span.set_data("heal.reason", reason)
    log = sentry_sdk.logger.info if verified else sentry_sdk.logger.warning
    log("heal {outcome} {step_id}: tier {tier} {reason}",
        outcome="succeeded" if verified else "failed", step_id=step_id, tier=tier, reason=reason)


def log_run_event(event: str, run_id: str, **attributes) -> None:
    """One log line for a run milestone: run_started, run_finished, step_started,
    approval_requested, program_patched, program_rolled_back. attributes become
    searchable log attributes (ids, versions, counts; no page content)."""
    level = sentry_sdk.logger.warning if event in ("approval_requested", "run_failed") else sentry_sdk.logger.info
    detail = " ".join(f"{k}={{{k}}}" for k in attributes)
    level(f"{{event}} {{run_id}} {detail}".rstrip(), event=event, run_id=run_id, **attributes)


@contextmanager
def llm_span(purpose: str, model: str = "claude-opus-5-5"):
    """Wrap an LLM call that is not auto-instrumented.

    Anthropic SDK calls are recorded by the SDK already; use this only for
    other clients. The gen_ai.* op is what puts it in Sentry's AI views.
    """
    with sentry_sdk.start_span(op="gen_ai.request", name=f"chat {model}") as span:
        span.set_data("gen_ai.operation.name", "chat")
        span.set_data("gen_ai.request.model", model)
        span.set_data("llm.purpose", purpose)
        yield span


@contextmanager
def agent_span(agent_name: str, task: str, model: str = "claude-opus-5-5"):
    """Wrap a whole agent run (the first recording run, or the tier-3 healer)
    so it shows up in Sentry's AI Agents dashboard. LLM calls made inside it
    become its children."""
    with sentry_sdk.start_span(op="gen_ai.invoke_agent", name=f"invoke_agent {agent_name}") as span:
        span.set_data("gen_ai.operation.name", "invoke_agent")
        span.set_data("gen_ai.agent.name", agent_name)
        span.set_data("gen_ai.request.model", model)
        span.set_data("gen_ai.request.messages", json.dumps([{"role": "user", "content": task}]))
        yield span


def record_agent_result(span, output: str, input_tokens: int, output_tokens: int) -> None:
    span.set_data("gen_ai.response.text", json.dumps([output]))
    span.set_data("gen_ai.usage.input_tokens", input_tokens)
    span.set_data("gen_ai.usage.output_tokens", output_tokens)
    span.set_data("gen_ai.usage.total_tokens", input_tokens + output_tokens)


@contextmanager
def agent_takeover_span(step_id: str, task: str, agent_name: str = "browser-use-takeover",
                        model: str = "claude-opus-5-5", run_id: str | None = None):
    """Tier 3: a Browser Use agent takes over one step. An agent_span (so it shows in
    AI Agents) tagged with the step and tier. If browser_use's own LLM calls are
    auto-instrumented, they appear as its children; don't wrap them again."""
    with agent_span(agent_name, task, model) as span:
        span.set_data("step.id", step_id)
        span.set_data("heal.tier", 3)
        if run_id is not None:
            span.set_data("run.id", run_id)
        yield span


def _demo(scenario: str) -> None:
    """Sends one synthetic run's trace and logs (no agent, no browser)."""
    import time

    tier = {"heal1": 1, "heal2": 2, "heal3": 3}.get(scenario)
    steps = [("s1", "click"), ("s2", "fill"), ("s3", "click")]
    with run_span("demo buy-item", "compiled", program_version=1, run_id=f"demo_{scenario}", program="buy-item"):
        log_run_event("run_started", f"demo_{scenario}", program="buy-item", version=1)
        for i, (sid, action) in enumerate(steps):
            with step_span(i, action, "compiled", step_id=sid) as span:
                time.sleep(0.05)
                if sid != "s3":
                    log_check(span, sid, "pre target_unique", passed=True)
                    continue
                log_check(span, sid, "pre target_unique", passed=False, detail="0 matches")
                if scenario == "blocked":
                    log_run_event("approval_requested", f"demo_{scenario}", step_id=sid, reason="write step, guard failed")
                    break
                with heal_span(sid, tier) as heal:
                    if tier == 3:
                        with agent_takeover_span(sid, "Click 'Add to cart' for the product", run_id=f"demo_{scenario}") as agent:
                            with llm_span("agent step"):
                                time.sleep(0.3)
                            record_agent_result(agent, "clicked 'Add to bag'", input_tokens=6200, output_tokens=410)
                    elif tier == 2:
                        with llm_span("repair step"):
                            time.sleep(0.3)
                    record_heal_result(heal, sid, tier, verified=True, reason="'Add to cart' renamed to 'Add to bag'")
                mark_healed(span, "'Add to cart' renamed to 'Add to bag'", tier)
                log_check(span, sid, "post url_matches /checkout", passed=True)
        log_run_event("run_finished", f"demo_{scenario}", success=scenario != "blocked")


if __name__ == "__main__":
    import sys

    from browseen.observability import init_sentry

    init_sentry()
    for name in sys.argv[1:] or ["heal2"]:
        _demo(name)
    print("sent; flushing...")
    sentry_sdk.flush()
