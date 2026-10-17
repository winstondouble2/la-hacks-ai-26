"""Span helpers for the compiler. One transaction per run, one span per step.

Span data keys are what the Sentry traces view is filtered and grouped by:
  run.mode      "llm" (first run) | "compiled" (replay)
  step.index    position in the program
  step.action   click / type / extract / ...
  step.healed   True when a guard failed and the LLM patched the step
"""

from contextlib import contextmanager

import sentry_sdk


@contextmanager
def run_span(task: str, mode: str):
    with sentry_sdk.start_transaction(op="agent.run", name=f"run:{mode}") as txn:
        txn.set_tag("run.mode", mode)
        txn.set_data("task", task)
        yield txn


@contextmanager
def step_span(index: int, action: str, target: str = ""):
    with sentry_sdk.start_span(op="agent.step", name=f"{index}:{action}") as span:
        span.set_data("step.index", index)
        span.set_data("step.action", action)
        span.set_data("step.target", target)
        span.set_data("step.healed", False)
        yield span


def mark_healed(span, reason: str) -> None:
    span.set_data("step.healed", True)
    span.set_data("step.heal_reason", reason)
    sentry_sdk.get_current_scope().transaction.set_tag("run.healed", "true")
    sentry_sdk.logger.warning("step healed: {reason}", reason=reason)


@contextmanager
def llm_span(purpose: str):
    """Wrap an LLM call that is not auto-instrumented (e.g. a repair prompt)."""
    with sentry_sdk.start_span(op="agent.llm", name=purpose) as span:
        yield span
