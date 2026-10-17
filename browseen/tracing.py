"""Span helpers for the compiler. One transaction per run, one span per step.

Names follow docs/architecture.md (Observability). Span data keys:
  mode             "llm" (recording run) | "compiled" (replay) | "healed" (step was repaired)
  program.version  version of the compiled program being run
  guard.result     "pass" | "fail"
  heal.tier        1 local, 2 one LLM patch, 3 scoped agent (only on healed steps)
"""

from contextlib import contextmanager

import sentry_sdk


@contextmanager
def run_span(task: str, mode: str, program_version: int | None = None):
    with sentry_sdk.start_transaction(op="agent.run", name=f"run:{mode}") as txn:
        txn.set_tag("mode", mode)
        txn.set_data("task", task)
        if program_version is not None:
            txn.set_tag("program.version", program_version)
        yield txn


@contextmanager
def step_span(index: int, action: str, mode: str, target: str = ""):
    with sentry_sdk.start_span(op="agent.step", name=f"{index}:{action}") as span:
        span.set_data("step.index", index)
        span.set_data("step.action", action)
        span.set_data("step.target", target)
        span.set_data("mode", mode)
        span.set_data("guard.result", "pass")
        yield span


def mark_healed(span, reason: str, tier: int) -> None:
    span.set_data("mode", "healed")
    span.set_data("guard.result", "fail")
    span.set_data("heal.tier", tier)
    span.set_data("heal.reason", reason)
    sentry_sdk.get_current_scope().transaction.set_tag("heal.tier", tier)
    sentry_sdk.logger.warning("step healed (tier {tier}): {reason}", tier=tier, reason=reason)


@contextmanager
def llm_span(purpose: str):
    """Wrap an LLM call that is not auto-instrumented (e.g. a repair prompt)."""
    with sentry_sdk.start_span(op="agent.llm", name=purpose) as span:
        yield span
