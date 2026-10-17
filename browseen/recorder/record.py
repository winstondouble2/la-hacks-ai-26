"""Record one Browser Use run into runs/<run_id>/ (format: trace.py).

Load .env before calling record() (init_sentry() does): browser_use reads its env vars at
import time. The CLI is `python -m browseen.recorder`.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from typing import Any

from browseen.agent import MODEL, make_agent
from browseen.costs import PRICES, usd
from browseen.program import param_refs, substitute
from browseen.recorder.trace import StepCapture, Trace, Usage, build_trace
from browseen.tracing import agent_span, record_agent_result, run_span, step_span

RUNS_DIR = Path("runs")


def new_run_id() -> str:
    return "r_" + datetime.now().strftime("%Y%m%d-%H%M%S")


def parse_inputs(pairs: list[str]) -> dict[str, str | int | float]:
    """["qty=2", "product=Blue Mug"] -> {"qty": 2, "product": "Blue Mug"}."""
    inputs: dict[str, str | int | float] = {}
    for pair in pairs:
        key, sep, raw = pair.partition("=")
        if not sep or not key:
            raise ValueError(f"expected key=value, got {pair!r}")
        if re.fullmatch(r"-?\d+", raw):
            inputs[key] = int(raw)
        elif re.fullmatch(r"-?\d+\.\d+", raw):
            inputs[key] = float(raw)
        else:
            inputs[key] = raw
    return inputs


def usage_from_entries(entries: list[Any], default_model: str = MODEL) -> Usage:
    """Sum Browser Use TokenUsageEntry objects. Its prompt_tokens includes cache reads."""
    total = Usage()
    for entry in entries:
        u = entry.usage
        cache_read = u.prompt_cached_tokens or 0
        tokens = dict(
            input_tokens=max(u.prompt_tokens - cache_read, 0),
            cache_read_tokens=cache_read,
            cache_write_tokens=u.prompt_cache_creation_tokens or 0,
            output_tokens=u.completion_tokens or 0,
        )
        model = entry.model if entry.model in PRICES else default_model
        total += Usage(llm_calls=1, usd=usd(model, **tokens), **tokens)
    return total


class EventLog:
    """Writes the run as dashboard events (dashboard/src/events.ts), one JSON line each."""

    def __init__(self, path: Path, *, run_id: str, program: str, trace_id: str):
        self.path, self.run_id, self.program, self.trace_id = path, run_id, program, trace_id

    def emit(self, type: str, *, step: str | None = None, detail: str = "", usage: Usage | None = None,
             **extra: Any) -> None:
        usage = usage or Usage()
        event = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "run_id": self.run_id, "program": self.program, "version": 0, "mode": "llm",
            "type": type, "step": step, "tier": None, "detail": detail, "diff": None,
            "llm_calls": usage.llm_calls, "tokens": usage.tokens, "usd": round(usage.usd, 4),
            "trace_id": self.trace_id, **extra,
        }
        with self.path.open("a") as f:
            f.write(json.dumps(event) + "\n")


def _warn(msg: str) -> None:
    print(f"[recorder] {msg}", file=sys.stderr)


async def record(task_template: str, start_url: str, inputs: dict[str, Any] | None = None, *,
                 name: str | None = None, headless: bool = False, max_steps: int = 30,
                 runs_dir: Path = RUNS_DIR) -> tuple[Trace, Path]:
    """Run the agent once on `task_template` (filled with `inputs`) and save the trace."""
    inputs = inputs or {}
    if missing := sorted(param_refs(task_template) - set(inputs)):
        raise ValueError(f"task uses {missing} but no --input was given for them")
    task = substitute(task_template, inputs)

    run_id = new_run_id()
    run_dir = Path(runs_dir) / run_id
    (run_dir / "html").mkdir(parents=True)
    captures: dict[int, StepCapture] = {}
    hook_state: dict[str, Any] = {"usage_seen": 0, "span": None}

    agent = make_agent(task, headless=headless,
                       initial_actions=[{"navigate": {"url": start_url, "new_tab": False}}])

    async def save_html(rel_path: str) -> str | None:
        page = await agent.browser_session.get_current_page()
        if page is None:
            return None
        (run_dir / rel_path).write_text(await page.evaluate("() => document.documentElement.outerHTML"))
        return rel_path

    async def before_step(agent) -> None:
        # History item 0 is the initial navigation, so len(history) is the step about to run.
        n = len(agent.history.history)
        capture = captures.setdefault(n, StepCapture())
        try:
            capture.html_before = await save_html(f"html/step_{n:02d}_before.html")
        except Exception as e:  # a capture failure must never break the run
            _warn(f"step {n}: no before-HTML ({e})")
        hook_state["usage_seen"] = len(agent.token_cost_service.usage_history)
        span_cm = step_span(n, "agent", "llm")
        hook_state["span"] = (span_cm, span_cm.__enter__())

    async def after_step(agent) -> None:
        n = len(agent.history.history) - 1
        capture = captures.setdefault(n, StepCapture())
        try:
            capture.html_after = await save_html(f"html/step_{n:02d}_after.html")
            capture.url_after = await agent.browser_session.get_current_page_url()
        except Exception as e:
            _warn(f"step {n}: no after-page ({e})")
        capture.usage = usage_from_entries(agent.token_cost_service.usage_history[hook_state["usage_seen"]:])

        item = agent.history.history[-1]
        output = item.model_output
        actions = [action for a in (output.action if output else []) for action in a.model_dump(exclude_none=True)]
        goal = output.next_goal if output else None
        events.emit("step_started", step=f"a{n}", usage=capture.usage,
                    detail=goal or "(no model output: the step failed)")
        if hook_state["span"]:
            span_cm, span = hook_state["span"]
            span.set_data("step.action", ", ".join(actions) or "none")
            span.set_data("gen_ai.usage.total_tokens", capture.usage.tokens)
            span_cm.__exit__(None, None, None)
            hook_state["span"] = None

    started_at = datetime.now(timezone.utc)
    started = time.monotonic()
    with run_span(task, "llm") as txn:
        events = EventLog(run_dir / "events.jsonl", run_id=run_id, program=name or "unnamed",
                          trace_id=getattr(txn, "trace_id", None) or "")
        events.emit("run_started", detail=f"Recording run: {task}")
        with agent_span("recorder", task, model=MODEL) as span:
            history = await agent.run(max_steps=max_steps, on_step_start=before_step, on_step_end=after_step)
            wall_s = time.monotonic() - started

            history.save_to_file(run_dir / "history.json")
            raw = json.loads((run_dir / "history.json").read_text())
            for i, item in enumerate(raw.get("history") or []):
                src = (item.get("state") or {}).get("screenshot_path")
                if src and Path(src).exists():
                    (run_dir / "screenshots").mkdir(exist_ok=True)
                    dest = f"screenshots/step_{i:02d}.png"
                    shutil.copyfile(src, run_dir / dest)
                    captures.setdefault(i, StepCapture()).screenshot = dest

            trace = build_trace(raw, captures=captures, run_id=run_id, name=name, task_template=task_template,
                                inputs=inputs, task=task, start_url=start_url, model=MODEL,
                                browser_use_version=version("browser-use"), started_at=started_at, wall_s=wall_s)
            (run_dir / "trace.json").write_text(trace.model_dump_json(indent=2))
            record_agent_result(span, trace.final_result or "",
                                input_tokens=trace.usage.tokens - trace.usage.output_tokens,
                                output_tokens=trace.usage.output_tokens)

        if history.usage and history.usage.total_prompt_tokens != trace.usage.tokens - trace.usage.output_tokens - trace.usage.cache_write_tokens:
            _warn("per-step token counts don't add up to Browser Use's total; some LLM calls happened outside steps")
        events.emit("run_finished", usage=trace.usage, seconds=round(wall_s, 1), success=bool(trace.agent_success),
                    detail=("Agent reported success" if trace.agent_success else "Agent did not finish the task")
                    + f" in {len(trace.steps) - 1} steps")
    return trace, run_dir
