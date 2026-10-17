"""Trace format: the raw record of one agent run. The recorder writes it; the compiler reads it.

A run lives in runs/<run_id>/:
  trace.json                  this format
  history.json                Browser Use's own history file (the benchmark's Replay baseline needs it)
  events.jsonl                the run as dashboard events (mode "llm")
  html/step_NN_before.html    the page before step NN acted (what the compiler tests locators on)
  html/step_NN_after.html
  screenshots/step_NN.png     taken by Browser Use at the start of step NN

Paths inside the trace are relative to the run directory. Step 0 is the initial navigation.
Action names and params are Browser Use's own (click, input, navigate, done, …); the
compiler maps them to program actions. B owns this format.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TraceElement(_Model):
    tag: str  # lowercase, e.g. "button"
    attributes: dict[str, str] = Field(default_factory=dict)
    xpath: str  # absolute: /html/body/...
    ax_name: str | None = None  # accessible name, e.g. "Add to cart"
    bounds: dict[str, float] | None = None
    stable_hash: int | None = None
    backend_node_id: int | None = None


class TraceAction(_Model):
    name: str
    params: dict[str, Any] = Field(default_factory=dict)  # `index` is a per-page-load element index: never reuse it
    element: TraceElement | None = None
    result: str | None = None  # Browser Use's extracted_content
    error: str | None = None


class Usage(_Model):
    llm_calls: int = 0
    input_tokens: int = 0  # excludes cache reads and writes
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    output_tokens: int = 0
    usd: float = 0.0

    @property
    def tokens(self) -> int:
        return self.input_tokens + self.cache_read_tokens + self.cache_write_tokens + self.output_tokens

    def __add__(self, other: Usage) -> Usage:
        fields = ("llm_calls", "input_tokens", "cache_read_tokens", "cache_write_tokens", "output_tokens", "usd")
        return Usage(**{f: getattr(self, f) + getattr(other, f) for f in fields})


class StepCapture(_Model):
    """What the recorder's hooks saw for one step (everything Browser Use's history lacks)."""

    url_after: str | None = None
    html_before: str | None = None
    html_after: str | None = None
    screenshot: str | None = None
    usage: Usage = Field(default_factory=Usage)


class TraceStep(_Model):
    number: int
    url: str | None = None  # page URL when the step started
    url_after: str | None = None
    goal: str | None = None  # the agent's next_goal: the program step's intent
    memory: str | None = None
    evaluation: str | None = None  # the agent's verdict on the previous step
    actions: list[TraceAction] = Field(default_factory=list)
    error: str | None = None  # a step-level failure with no action (e.g. an LLM error)
    duration_s: float | None = None
    usage: Usage = Field(default_factory=Usage)
    html_before: str | None = None
    html_after: str | None = None
    screenshot: str | None = None


class Trace(_Model):
    format: Literal[1] = 1
    run_id: str
    name: str | None = None
    task_template: str  # with $params, e.g. "Buy $qty of $product"
    inputs: dict[str, str | int | float | bool] = Field(default_factory=dict)
    task: str  # what the agent was actually told
    start_url: str
    model: str
    browser_use_version: str | None = None
    started_at: datetime
    wall_s: float
    agent_done: bool
    agent_success: bool | None = None  # the agent's own claim; the benchmark verifies separately
    final_result: str | None = None
    usage: Usage
    steps: list[TraceStep]


def _element(raw: dict[str, Any] | None) -> TraceElement | None:
    if not raw or not raw.get("x_path"):
        return None
    xpath = raw["x_path"]
    return TraceElement(
        tag=(raw.get("node_name") or "").lower(),
        attributes={k: str(v) for k, v in (raw.get("attributes") or {}).items()},
        xpath=xpath if xpath.startswith("/") else "/" + xpath,
        ax_name=raw.get("ax_name") or None,
        bounds=raw.get("bounds"),
        stable_hash=raw.get("stable_hash"),
        backend_node_id=raw.get("backend_node_id"),
    )


def build_trace(history: dict[str, Any], *, captures: dict[int, StepCapture], run_id: str,
                task_template: str, inputs: dict[str, Any], task: str, start_url: str, model: str,
                started_at: datetime, wall_s: float, name: str | None = None,
                browser_use_version: str | None = None) -> Trace:
    """Turn Browser Use's history (the dict in history.json) plus the hooks' captures into a Trace."""
    items = history.get("history") or []
    steps = []
    for i, item in enumerate(items):
        output = item.get("model_output") or {}
        state = item.get("state") or {}
        meta = item.get("metadata") or {}
        number = meta.get("step_number", i)
        elements = state.get("interacted_element") or []
        results = item.get("result") or []

        actions = []
        for j, action in enumerate(output.get("action") or []):
            ((action_name, params),) = action.items()  # one action per dict
            result = results[j] if j < len(results) else {}
            actions.append(TraceAction(
                name=action_name,
                params=params or {},
                element=_element(elements[j] if j < len(elements) else None),
                result=result.get("extracted_content"),
                error=result.get("error"),
            ))
        step_error = next((r["error"] for r in results if r.get("error")), None) if not actions else None

        duration = None
        if meta.get("step_start_time") and meta.get("step_end_time"):
            duration = round(meta["step_end_time"] - meta["step_start_time"], 2)
        capture = captures.get(number) or StepCapture()
        steps.append(TraceStep(
            number=number,
            url=state.get("url"),
            url_after=capture.url_after,
            goal=output.get("next_goal"),
            memory=output.get("memory"),
            evaluation=output.get("evaluation_previous_goal"),
            actions=actions,
            error=step_error,
            duration_s=duration,
            usage=capture.usage,
            html_before=capture.html_before,
            html_after=capture.html_after,
            screenshot=capture.screenshot,
        ))

    last = (items[-1].get("result") or [{}])[-1] if items else {}
    done = bool(last.get("is_done"))
    return Trace(
        run_id=run_id,
        name=name,
        task_template=task_template,
        inputs=inputs,
        task=task,
        start_url=start_url,
        model=model,
        browser_use_version=browser_use_version,
        started_at=started_at,
        wall_s=round(wall_s, 2),
        agent_done=done,
        agent_success=last.get("success") if done else None,
        final_result=last.get("extracted_content") if done else None,
        usage=sum((s.usage for s in steps), Usage()),
        steps=steps,
    )


def load_trace(run_dir: str | Path) -> Trace:
    return Trace.model_validate_json((Path(run_dir) / "trace.json").read_text())
