"""The runtime: replay a compiled program on Playwright with no LLM calls, and heal the steps
that break (heal.py). Entry point for `python -m browseen run`:

    run_program(program, params, *, headless=True) -> RunResult   (RunResult.success sets the exit code)

Every run writes runs/<run_id>/events.jsonl (browseen/events.py). A heal is verified on the live
page before it's kept, then saved as the next program version, so the next run is free again.
"""

from __future__ import annotations

import asyncio
import socket
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

import sentry_sdk.logger  # noqa: F401  (tracing's log helpers need it even when Sentry isn't initialized)

from browseen.events import EventLog
from browseen.program import PROGRAMS_DIR, Locator, Program, Step, diff, save, versions
from browseen.recorder.trace import Usage
from browseen.runtime.checks import POLL_S, describe, evaluate
from browseen.tracing import log_check, log_run_event, mark_healed, run_span, step_span

RUNS_DIR = Path("runs")
WHEN_TIMEOUT_MS = 1000  # an optional step's `when` is checked quickly: absent means skip
MAX_DIFF_LINES = 30


@dataclass
class Failure:
    index: int
    step_id: str
    stage: str  # locate | pre | action | post
    check: str  # what failed, e.g. "url_matches /cart(\?|#|$)" or "target"
    detail: str

    def describe(self) -> str:
        return f"{self.stage} {self.check}: {self.detail}".strip()


@dataclass
class StepResult:
    step_id: str
    status: str  # passed | skipped | healed | failed
    tier: int | None = None
    detail: str = ""


@dataclass
class RunResult:
    run_id: str
    program: str
    version_start: int
    version_end: int
    success: bool
    steps: list[StepResult]
    usage: Usage
    seconds: float
    run_dir: Path
    error: str | None = None

    def summary(self) -> str:
        heals = [s for s in self.steps if s.status == "healed"]
        healed = ", ".join(f"{s.step_id} (tier {s.tier})" for s in heals) or "none"
        version = f"v{self.version_start}" + (f" → v{self.version_end}" if self.version_end != self.version_start else "")
        return (f"{'SUCCESS' if self.success else 'FAILED'}  {self.program} {version}  {self.seconds:.1f}s  "
                f"{self.usage.llm_calls} LLM calls  ${self.usage.usd:.4f}  healed: {healed}"
                + (f"\n  error: {self.error}" if self.error else ""))


def new_run_id() -> str:
    return f"c_{datetime.now():%Y%m%d-%H%M%S}-{uuid4().hex[:4]}"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def with_query(url: str, overrides: dict[str, Any] | None) -> str:
    """Replace query parameters in a URL, e.g. mut=M04 for a testbed mutation."""
    if not overrides:
        return url
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update({k: str(v) for k, v in overrides.items()})
    return urlunsplit(parts._replace(query=urlencode(query)))


def short_diff(old: Program, new: Program) -> str:
    """The changed lines of a version diff, for the dashboard's healed event."""
    lines = [line for line in diff(old, new).splitlines()
             if line[:1] in "+-" and not line.startswith(("+++", "---")) and "version:" not in line]
    return "\n".join(lines[:MAX_DIFF_LINES])


async def resolve(page: Any, locators: list[Locator], timeout_ms: int) -> tuple[Any | None, int | None]:
    """The first locator (in order) that matches exactly one element, polling until the timeout."""
    deadline = time.monotonic() + timeout_ms / 1000
    while True:
        for i, locator in enumerate(locators):
            try:
                found = locator.to_playwright(page)
                if await found.count() == 1:
                    return found, i
            except Exception:
                pass
        if time.monotonic() >= deadline:
            return None, None
        await asyncio.sleep(POLL_S)


async def perform(page: Any, step: Step, target: Any | None) -> str | None:
    """Do the step's action. Returns an error message, or None."""
    a, timeout = step.action, step.timeout_ms
    try:
        if a.type == "click":
            await target.click(timeout=timeout)
        elif a.type == "fill":
            await target.fill(a.value, timeout=timeout)
        elif a.type == "select":
            await target.select_option(a.value, timeout=timeout)
        elif a.type == "check":
            await target.check(timeout=timeout)
        elif a.type == "uncheck":
            await target.uncheck(timeout=timeout)
        elif a.type == "press":
            await (target.press(a.key, timeout=timeout) if target else page.keyboard.press(a.key))
        elif a.type == "navigate":
            await page.goto(a.url, timeout=timeout)
        elif a.type == "extract":
            await target.inner_text(timeout=timeout)
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=timeout)
        except Exception:
            pass
    except Exception as e:
        return str(e).splitlines()[0][:200]
    return None


class Run:
    """One run of one program. Keeps the templated program (what heals patch and save) and the
    resolved one (what executes) in step."""

    def __init__(self, program: Program, params: dict[str, Any], *, headless: bool = True, healing: bool = True,
                 tiers: tuple[int, ...] = (1, 2, 3), runs_dir: Path = RUNS_DIR, programs_dir: Path = PROGRAMS_DIR,
                 run_id: str | None = None, url_params: dict[str, Any] | None = None, verbose: bool = False,
                 llm_call: Any = None, takeover: Any = None):
        self.template = program
        self.params = params
        self.resolved = program.resolved(params)  # raises KeyError for missing or unknown params
        self.headless, self.healing, self.tiers = headless, healing, tiers
        self.runs_dir, self.programs_dir = Path(runs_dir), Path(programs_dir)
        self.run_id = run_id or new_run_id()
        self.run_dir = self.runs_dir / self.run_id
        self.start_url = with_query(self.resolved.start_url, url_params)
        self.verbose = verbose
        self.llm_call, self.takeover = llm_call, takeover  # test hooks; default to the real ones
        self.usage = Usage()
        self.cdp_url = ""
        self.page: Any = None
        self.events: EventLog | None = None

    def log(self, message: str) -> None:
        if self.verbose:
            print(message, flush=True)

    def set_program(self, program: Program) -> None:
        self.template = program
        self.resolved = program.resolved(self.params)

    async def run_step(self, page: Any, step: Step, span: Any = None,
                       locators: list[Locator] | None = None) -> tuple[str, Failure | None, int | None]:
        """Run one step. Returns ("passed" | "skipped" | "failed", failure, index of the locator used)."""
        index = next((i for i, s in enumerate(self.resolved.steps) if s.id == step.id), -1)  # -1: a step being inserted

        def record(stage: str, check: str, passed: bool, detail: str = "") -> None:
            self.events.emit("check_passed" if passed else "check_failed", step=step.id, stage=stage,
                             check=check, detail=f"{stage} {check}" + (f": {detail}" if detail else ""),
                             version=self.template.version)
            if span is not None:
                log_check(span, step.id, f"{stage} {check}", passed, detail)

        if step.when is not None:
            present, _ = await evaluate(page, step.when, None, WHEN_TIMEOUT_MS)
            record("when", describe(step.when), True, "" if present else "not present, so the optional step is skipped")
            if not present:
                return "skipped", None, None

        target, used = None, None
        if step.target is not None:
            candidates = locators or step.target.locators
            target, used = await resolve(page, candidates, step.timeout_ms)
            if target is None:
                tried = ", ".join(loc.describe() for loc in candidates)
                record("locate", "target", False, f"no locator matched exactly one element ({tried})")
                return "failed", Failure(index, step.id, "locate", "target", f"no unique match for {tried}"), None

        for check in step.pre:
            passed, seen = await evaluate(page, check, target, step.timeout_ms)
            record("pre", describe(check), passed, seen)
            if not passed:
                return "failed", Failure(index, step.id, "pre", describe(check), seen), used

        if error := await perform(page, step, target):
            record("action", step.action.type, False, error)
            return "failed", Failure(index, step.id, "action", step.action.type, error), used

        for check in step.post:
            passed, seen = await evaluate(page, check, None if step.action.type == "click" else target, step.timeout_ms)
            record("post", describe(check), passed, seen)
            if not passed:
                return "failed", Failure(index, step.id, "post", describe(check), seen), used
        return "passed", None, used

    def commit(self, new: Program, *, tier: int, step_id: str, reason: str, usage: Usage | None = None) -> Program:
        """Save a verified patch as the next version and announce it."""
        taken = versions(new.program, self.programs_dir)
        if taken and new.version <= max(taken):  # another run healed first: take the next free number
            bumped = max(taken) + 1
            new.history[-1].version = bumped
            new.version = bumped
        old = self.template
        save(new, self.programs_dir)
        self.events.emit("healed", step=step_id, tier=tier, detail=reason, diff=short_diff(old, new),
                         version=new.version, mode="healed", usage=usage)
        log_run_event("program_patched", self.run_id, program=new.program, version=new.version, tier=tier)
        self.log(f"  healed {step_id} (tier {tier}): {reason} → saved v{new.version}")
        self.set_program(new)
        return new

    def promote(self, step_id: str, locator_index: int) -> None:
        """A later locator worked: put it first, so the next run uses it straight away (tier 1)."""
        new = self.template.bump(source="healed", step=step_id, tier=1,
                                 reason=f"locator {locator_index + 1} worked; promoted to first")
        step = new.step(step_id)
        step.target.locators.insert(0, step.target.locators.pop(locator_index))
        self.commit(new, tier=1, step_id=step_id, reason=f"first locator failed; {step.target.locators[0].describe()} worked")

    async def execute(self) -> RunResult:
        from playwright.async_api import async_playwright

        from browseen.runtime.heal import heal

        started = time.monotonic()
        version_start = self.template.version
        results: list[StepResult] = []
        error: str | None = None
        success = False

        with run_span(self.resolved.task, "compiled", program_version=version_start, run_id=self.run_id,
                      program=self.template.program) as txn:
            self.events = EventLog(self.run_dir / "events.jsonl", run_id=self.run_id, program=self.template.program,
                                   trace_id=getattr(txn, "trace_id", None) or "", version=version_start, mode="compiled")
            self.events.emit("run_started", detail=f"Compiled run of {self.template.program} v{version_start}",
                             params={k: str(v) for k, v in self.params.items()}, start_url=self.start_url)
            log_run_event("run_started", self.run_id, program=self.template.program, version=version_start)
            self.log(f"run {self.run_id}: {self.template.program} v{version_start}  {self.start_url}")

            async with async_playwright() as pw:
                port = free_port()
                self.cdp_url = f"http://127.0.0.1:{port}"
                browser = await pw.chromium.launch(headless=self.headless, args=[f"--remote-debugging-port={port}"])
                page = await browser.new_page()
                self.page = page  # tier 3 and test hooks act on the same tab
                try:
                    await page.goto(self.start_url)
                    i = 0
                    while i < len(self.resolved.steps):
                        step = self.resolved.steps[i]
                        self.events.emit("step_started", step=step.id, detail=step.intent, version=self.template.version)
                        target_desc = step.target.locators[0].describe() if step.target else ""
                        with step_span(i, step.action.type, "compiled", target_desc, step.id) as span:
                            status, failure, used = await self.run_step(page, step, span)
                            if status == "skipped":
                                results.append(StepResult(step.id, "skipped"))
                                self.log(f"  {step.id} skipped (optional, not present)")
                                i += 1
                                continue
                            if status == "passed":
                                if used:  # a fallback locator did the work
                                    mark_healed(span, "fallback locator", 1)
                                    self.promote(step.id, used)
                                    results.append(StepResult(step.id, "healed", 1, "fallback locator promoted"))
                                else:
                                    results.append(StepResult(step.id, "passed"))
                                    self.log(f"  {step.id} ok   {step.intent}")
                                i += 1
                                continue
                            self.log(f"  {step.id} FAIL {failure.describe()}")
                            outcome = await heal(self, page, i, failure, span) if self.healing else None
                            if outcome is None:
                                results.append(StepResult(step.id, "failed", detail=failure.describe()))
                                error = f"{step.id}: {failure.describe()}"
                                break
                            mark_healed(span, outcome.reason, outcome.tier)
                            results.append(StepResult(step.id, "healed", outcome.tier, outcome.reason))
                            i = outcome.resume_at
                    else:
                        success = True
                        for check in self.resolved.success:
                            passed, seen = await evaluate(page, check, None, 5000)
                            self.events.emit("check_passed" if passed else "check_failed", stage="success",
                                             check=describe(check), detail=f"success {describe(check)}"
                                             + (f": {seen}" if seen else ""))
                            if not passed:
                                success, error = False, f"success check failed: {describe(check)} ({seen})"
                except Exception as e:  # never leave a run without a run_finished event
                    error = f"{type(e).__name__}: {str(e).splitlines()[0][:200]}"
                finally:
                    await browser.close()

            seconds = time.monotonic() - started
            self.events.emit("run_finished", usage=self.usage, version=self.template.version, seconds=round(seconds, 1),
                             success=success, detail=("Success" if success else f"Failed: {error}")
                             + (f". Program now v{self.template.version}" if self.template.version != version_start else ""))
            log_run_event("run_finished", self.run_id, program=self.template.program, success=success,
                          version=self.template.version)

        result = RunResult(self.run_id, self.template.program, version_start, self.template.version, success,
                           results, self.usage, round(seconds, 1), self.run_dir, error)
        self.log(result.summary())
        return result


async def run_program_async(program: Program, params: dict[str, Any], *, headless: bool = True,
                            **options: Any) -> RunResult:
    return await Run(program, params, headless=headless, **options).execute()


def run_program(program: Program, params: dict[str, Any], *, headless: bool = True, **options: Any) -> RunResult:
    """Replay `program` with `params`, healing broken steps. Options: healing, tiers, runs_dir,
    programs_dir, run_id, url_params (e.g. {"mut": "M04"}), verbose."""
    options.setdefault("verbose", True)
    return asyncio.run(run_program_async(program, params, headless=headless, **options))
