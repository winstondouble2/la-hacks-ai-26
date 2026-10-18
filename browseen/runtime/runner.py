"""Compiled replay: run a program with Playwright and no model calls.

For each step: evaluate `when` (skip if false), resolve a unique target, wait for the pre-checks,
act once, wait for the post-checks. Then the program's success checks. Any failure stops the run;
an action is never repeated after its post-checks fail. Healing comes in a later milestone.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Awaitable, Callable

import sentry_sdk
import sentry_sdk.logger  # noqa: F401 - tracing's log helpers need it even when init_sentry() never ran
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import async_playwright

from browseen.program import Program, Step
from browseen.runtime import checks, diagnostics
from browseen.runtime.diagnostics import short_error
from browseen.runtime.events import EventLog
from browseen.runtime.models import Failure, GuardFailure, RunResult, StepResult
from browseen.runtime.preflight import check_run_id, new_run_id, prepare
from browseen.tracing import log_check, run_span, step_span

RUNS_DIR = Path("runs")
WHEN_TIMEOUT_MS = 500  # optional steps: how long to look for their condition
NAVIGATE_TIMEOUT_MS = 15000
SUCCESS_TIMEOUT_MS = 5000
CLOSE_TIMEOUT_S = 10

ContextHook = Callable[[Any], Awaitable[None]]


@dataclass(frozen=True)
class _Run:
    page: Any
    events: EventLog
    run_dir: Path


def _make_run_dir(runs_dir: Path, run_id: str | None) -> tuple[str, Path]:
    runs_dir.mkdir(parents=True, exist_ok=True)
    for _ in range(5):
        rid = check_run_id(run_id) if run_id else new_run_id()
        try:
            (runs_dir / rid).mkdir()
            return rid, runs_dir / rid
        except FileExistsError:
            if run_id:
                raise ValueError(f"run {run_id!r} already exists in {runs_dir}") from None
    raise RuntimeError("could not pick an unused run id")


async def _with_diagnostics(failure: Failure, page: Any, run_dir: Path) -> Failure:
    label = f"fail_{failure.step_id or failure.stage}"
    try:
        found = await diagnostics.capture(page, run_dir, label)
    except Exception as e:  # noqa: BLE001 - the original failure must survive a broken capture
        return replace(failure, diagnostics_error=f"capture failed: {short_error(e)}")
    return replace(failure, screenshot=found.screenshot, snapshot=found.snapshot, diagnostics_error=found.error,
                   url=failure.url or page.url)


async def _act(page: Any, step: Step, target: Any | None, timeout_ms: int) -> None:
    a = step.action
    try:
        if a.type == "navigate":
            await page.goto(a.url, wait_until="load", timeout=NAVIGATE_TIMEOUT_MS)
        elif a.type == "click":
            await target.click(timeout=timeout_ms)
        elif a.type == "fill":
            await target.fill(a.value, timeout=timeout_ms)
        elif a.type == "select":
            await target.select_option(a.value, timeout=timeout_ms)
        elif a.type == "check":
            await target.check(timeout=timeout_ms)
        elif a.type == "uncheck":
            await target.uncheck(timeout=timeout_ms)
        elif a.type == "press":
            await (target.press(a.key, timeout=timeout_ms) if target is not None else page.keyboard.press(a.key))
        else:  # prepare() rejects these before the run
            raise ValueError(f"unsupported action {a.type}")
    except PlaywrightError as e:
        raise GuardFailure(Failure(step.id, "action", a.type, "the action completes", short_error(e), page.url)) from e


def _remaining_ms(deadline: float) -> int:
    return max(1000, int((deadline - checks.now()) * 1000))


async def _run_step(run: _Run, index: int, template: Step, step: Step, results: list[StepResult]) -> None:
    """One step; appends its StepResult. Raises GuardFailure after recording a failed result."""
    started = time.monotonic()
    events, page = run.events, run.page
    events.emit("step_started", step=step.id, detail=step.intent)
    first = template.target.locators[0].describe() if template.target else ""
    resolved: checks.Resolved | None = None
    with step_span(index, step.action.type, "compiled", target=first, step_id=step.id) as span:
        try:
            if step.when is not None:
                ok, actual = await checks.holds(page, step.when, step.target, checks.now() + WHEN_TIMEOUT_MS / 1000)
                when = f"when {checks.describe(template.when)}"
                if ok:
                    log_check(span, step.id, when, True)
                else:  # a normal skip, not a failed guard: guard.result stays "pass"
                    span.set_data("step.skipped", True)
                    sentry_sdk.logger.info("step skipped {step_id}: {check} not met", step_id=step.id, check=when)
                    events.emit("check_passed", step=step.id, stage="when",
                                detail=f"Optional step skipped: {checks.describe(step.when)} not met ({actual})")
                    results.append(StepResult(step.id, "skipped", seconds=time.monotonic() - started))
                    return
                events.emit("check_passed", step=step.id, stage="when",
                            detail=f"Condition met: {checks.describe(step.when)}")
            deadline = checks.now() + step.timeout_ms / 1000
            if step.target is not None:
                resolved = await checks.resolve(page, step.id, step.target, deadline)
                events.emit("check_passed", step=step.id, stage="resolve", detail=_resolved_detail(step, resolved))
            target = resolved.locator if resolved else None
            passed = await checks.wait_for_checks(page, step.id, "pre", step.pre, target, deadline)
            if passed:
                log_check(span, step.id, "pre " + ", ".join(checks.describe(c) for c in template.pre), True)
                events.emit("check_passed", step=step.id, stage="pre", detail="; ".join(passed))
            await _act(page, step, target, _remaining_ms(deadline))
            passed = await checks.wait_for_checks(page, step.id, "post", step.post, target,
                                                  checks.now() + step.timeout_ms / 1000)
            if passed:
                log_check(span, step.id, "post " + ", ".join(checks.describe(c) for c in template.post), True)
                events.emit("check_passed", step=step.id, stage="post", detail="; ".join(passed))
        except GuardFailure as g:
            kind = g.failure.check.split(" ", 1)[0]  # no resolved values (names, addresses) in Sentry
            log_check(span, step.id, f"{g.failure.stage} {kind}", False)
            events.emit("check_failed", step=step.id, stage=g.failure.stage, detail=g.failure.summary)
            results.append(_step_result(step.id, "failed", resolved, started))
            raise
        except BaseException:
            results.append(_step_result(step.id, "failed", resolved, started))
            raise
    results.append(_step_result(step.id, "passed", resolved, started))


def _step_result(step_id: str, status: str, resolved: checks.Resolved | None, started: float) -> StepResult:
    return StepResult(step_id, status, resolved.description if resolved else None,
                      resolved.index if resolved else None, time.monotonic() - started)


def _resolved_detail(step: Step, r: checks.Resolved) -> str:
    total = len(step.target.locators)
    if r.index == 0:
        return f"Target: {r.description} (primary locator, 1 of {total})"
    earlier = ", ".join(f"{loc.describe()}: {n} visible" for loc, n in zip(step.target.locators[: r.index], r.counts))
    return f"Target: {r.description} via fallback (locator {r.index + 1} of {total}; {earlier})"


async def _open(run: _Run, url: str) -> None:
    try:
        await run.page.goto(url, wait_until="load", timeout=NAVIGATE_TIMEOUT_MS)
    except PlaywrightError as e:
        failure = Failure(None, "navigate", "open start_url", url, short_error(e), run.page.url)
        run.events.emit("check_failed", stage="navigate", detail=failure.summary)
        raise GuardFailure(failure) from e


async def _success(run: _Run, program: Program) -> None:
    deadline = checks.now() + SUCCESS_TIMEOUT_MS / 1000
    try:
        passed = await checks.wait_for_checks(run.page, None, "success", program.success, None, deadline)
    except GuardFailure as g:
        run.events.emit("check_failed", stage="success", detail=g.failure.summary)
        raise
    run.events.emit("check_passed", stage="success", detail="; ".join(passed))


async def _execute(run_dir: Path, events: EventLog, template: Program, program: Program, headless: bool,
                   on_context: ContextHook | None) -> tuple[list[StepResult], Failure | None]:
    results: list[StepResult] = []
    async with async_playwright() as pw:
        try:
            browser = await pw.chromium.launch(headless=headless)
        except PlaywrightError as e:
            failure = Failure(None, "browser", "launch chromium", "a running browser", short_error(e))
            events.emit("check_failed", stage="browser", detail=failure.summary)
            return results, failure
        try:
            context = await browser.new_context()
            if on_context is not None:
                await on_context(context)
            run = _Run(await context.new_page(), events, run_dir)
            try:
                await _open(run, program.start_url)
                for index, (tmpl, step) in enumerate(zip(template.steps, program.steps)):
                    await _run_step(run, index, tmpl, step, results)
                await _success(run, program)
            except GuardFailure as g:
                return results, await _with_diagnostics(g.failure, run.page, run_dir)
            return results, None
        finally:
            try:
                await asyncio.wait_for(browser.close(), CLOSE_TIMEOUT_S)
            except Exception as e:  # noqa: BLE001 - never mask the run's own outcome
                sentry_sdk.logger.warning("browser close failed: {error}", error=short_error(e))


def _sentry_sending() -> bool:
    """init_sentry() without SENTRY_DSN leaves an active client with no DSN; nothing is sent, so
    there is no trace to link."""
    client = sentry_sdk.get_client()
    return client.is_active() and bool(client.dsn)


async def run_program_async(program: Program, params: dict[str, Any], *, headless: bool = True,
                            runs_dir: Path | str = RUNS_DIR, run_id: str | None = None,
                            on_context: ContextHook | None = None) -> RunResult:
    """Replay `program` with `params`. Expected failures come back as RunResult(success=False)
    with a Failure; bad inputs raise ValueError before anything starts. `on_context` lets a
    test or demo set up the browser context (e.g. routes) before the first page opens."""
    resolved = prepare(program, params)
    rid, run_dir = _make_run_dir(Path(runs_dir), run_id)
    events = EventLog(run_dir / "events.jsonl", rid, program.program, program.version)
    started = time.monotonic()
    with run_span(program.task, "compiled", program_version=program.version, run_id=rid,
                  program=program.program) as txn:
        events.trace_id = txn.trace_id if _sentry_sending() else ""
        events.emit("run_started", detail=f"Compiled run of {program.program} v{program.version}")
        try:
            results, failure = await _execute(run_dir, events, program, resolved, headless, on_context)
        except BaseException as e:
            events.finish(success=False, seconds=time.monotonic() - started,
                          detail=f"Run stopped by an internal error: {short_error(e)}")
            raise
        seconds = time.monotonic() - started
        detail = f"Failed: {failure.summary}" if failure else f"Done: {len(results)} steps, success checks passed"
        events.finish(success=failure is None, seconds=seconds, detail=detail)
    return RunResult(run_id=rid, program=program.program, version=program.version, success=failure is None,
                     seconds=seconds, run_dir=run_dir, steps=tuple(results), failure=failure,
                     trace_id=events.trace_id)


def run_program(program: Program, params: dict[str, Any], *, headless: bool = True, **kwargs: Any) -> RunResult:
    """The CLI's entry point (browseen/cli.py): run_program(program, params, *, headless)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(run_program_async(program, params, headless=headless, **kwargs))
    raise RuntimeError("run_program() can't run inside an event loop; await run_program_async() instead")
