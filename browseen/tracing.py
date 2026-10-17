"""Span helpers for the compiler. One transaction per run, one span per step.

Names follow docs/architecture.md (Observability). Span data keys:
  mode             "llm" (recording run) | "compiled" (replay) | "healed" (step was repaired)
  program.version  version of the compiled program being run
  guard.result     "pass" | "fail"
  heal.tier        1 local, 2 one LLM patch, 3 scoped agent (only on healed steps)

Agent runs use agent_span (op gen_ai.invoke_agent) so they appear in Sentry's
AI Agents dashboard; custom ops like agent.llm do not.
"""

import json
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
