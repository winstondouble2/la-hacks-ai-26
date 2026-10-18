"""Target resolution and guard checks, each with a bounded wait.

Locators are B's (Locator.to_playwright). The runtime only counts *visible* matches, so a hidden
copy of a button can't make a target ambiguous and a hidden popup counts as absent.
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass
from typing import Any

from playwright.async_api import Error as PlaywrightError

from browseen.program import Check, Locator, Target
from browseen.runtime import text
from browseen.runtime.diagnostics import short_error
from browseen.runtime.models import Failure, GuardFailure, Stage

POLL_S = 0.1
PROBE_S = 2.0  # one round of probes; a hung call counts as "not ready yet"
PROBE_MS = 250  # Playwright calls that would otherwise auto-wait for 30 s
FALLBACK_GRACE_MS = 1000  # how long the primary locator gets before a fallback may be used


def now() -> float:
    return time.monotonic()


def visible(page: Any, locator: Locator) -> Any:
    return locator.to_playwright(page).filter(visible=True)


@dataclass(frozen=True)
class Resolved:
    locator: Any  # the Playwright locator, visible matches only
    index: int  # position in the step's locator list; 0 is the primary
    description: str
    counts: tuple[int, ...]  # visible matches per locator when it resolved


def describe(check: Check) -> str:
    """Short form for events, logs and failures, e.g. 'text_visible 2 × Blue Mug'."""
    kind = check.kind
    value = getattr(check, kind)
    if kind in ("target_unique", "target_enabled"):
        return kind
    if isinstance(value, Locator):
        return f"{kind} {value.describe()}"
    return f"{kind} {value}"


def expected(check: Check) -> str:
    """What a check wants, in words, for failure reports."""
    value = getattr(check, check.kind)
    if check.kind == "target_unique":
        return "exactly one visible match"
    if check.kind == "target_enabled":
        return "enabled"
    if check.kind == "exists":
        return f"a visible {value.describe()}"
    if check.kind == "absent":
        return f"no visible {value.describe()}"
    return repr(value)


def _counts_text(locators: list[Locator], counts: tuple[int, ...]) -> str:
    return ", ".join(f"{loc.describe()}: {n}" for loc, n in zip(locators, counts))


async def _count_all(page: Any, locators: list[Locator]) -> tuple[int, ...]:
    return tuple([await visible(page, loc).count() for loc in locators])


async def resolve(page: Any, step_id: str, target: Target, deadline: float, stage: Stage = "resolve") -> Resolved:
    """The first locator, in order, with exactly one visible match. The primary gets a grace period
    before any fallback is accepted; a locator with several matches is never used."""
    locators = target.locators
    started = now()
    grace_until = min(deadline, started + FALLBACK_GRACE_MS / 1000)
    counts: tuple[int, ...] = tuple(0 for _ in locators)
    last_error = ""
    while True:
        try:
            counts = await asyncio.wait_for(_count_all(page, locators), PROBE_S)
            last_error = ""
        except (PlaywrightError, asyncio.TimeoutError) as e:
            last_error = short_error(e)
        else:
            candidates = [0] if now() < grace_until else range(len(locators))
            for i in candidates:
                if counts[i] == 1:
                    return Resolved(visible(page, locators[i]), i, locators[i].describe(), counts)
        if now() >= deadline:
            ambiguous = any(n > 1 for n in counts)
            actual = ("ambiguous, no locator has exactly one match" if ambiguous else "no locator matched")
            actual += f" ({_counts_text(locators, counts)})" + (f"; {last_error}" if last_error else "")
            raise GuardFailure(Failure(step_id, stage, "target", "exactly one visible match for one locator",
                                       actual, page.url, counts))
        await asyncio.sleep(POLL_S)


async def evaluate(page: Any, check: Check, target: Any | None) -> tuple[bool, str]:
    """(passed, what the page actually shows). Raises only on page errors."""
    kind = check.kind
    if kind == "url_matches":
        return re.search(check.url_matches, page.url) is not None, page.url
    if kind == "text_visible":
        units = await page.evaluate(text.UNITS_JS)
        if text.text_found(units, check.text_visible):
            return True, "visible"
        near = text.near_matches(units, check.text_visible)
        if near:
            return False, "only near matches: " + "; ".join(repr(u) for u in near)
        return False, f"not on the page; visible text: {text.preview(units)!r}"
    if kind in ("exists", "absent"):
        n = await visible(page, getattr(check, kind)).count()
        return (n > 0 if kind == "exists" else n == 0), f"{n} visible matches"
    if target is None:  # the schema forbids this; guard anyway
        return False, "step has no target"
    if kind == "target_unique":
        n = await target.count()
        return n == 1, f"{n} visible matches"
    if await target.count() != 1:
        return False, "target is no longer unique"
    if kind == "target_enabled":
        enabled = await target.is_enabled(timeout=PROBE_MS)
        return enabled, "enabled" if enabled else "disabled"
    value = await target.input_value(timeout=PROBE_MS)
    return value == check.target_value, f"value {value!r}"


async def _evaluate_all(page: Any, checks: list[Check], target: Any | None) -> list[tuple[Check, bool, str]]:
    return [(c, *await evaluate(page, c, target)) for c in checks]


async def wait_for_checks(page: Any, step_id: str | None, stage: Stage, checks: list[Check], target: Any | None,
                          deadline: float) -> list[str]:
    """Poll until every check passes or the deadline passes; returns their short forms.
    On timeout, raises GuardFailure for the first check still failing."""
    if not checks:
        return []
    results: list[tuple[Check, bool, str]] = []
    while True:
        try:
            results = await asyncio.wait_for(_evaluate_all(page, checks, target), PROBE_S)
        except (PlaywrightError, asyncio.TimeoutError) as e:  # e.g. mid-navigation
            results = [(c, False, f"page not ready ({short_error(e)})") for c in checks]
        if all(ok for _, ok, _ in results):
            return [describe(c) for c in checks]
        if now() >= deadline:
            check, _, actual = next(r for r in results if not r[1])
            raise GuardFailure(Failure(step_id, stage, describe(check), expected(check), actual, page.url))
        await asyncio.sleep(POLL_S)


async def holds(page: Any, check: Check, target: Target | None, deadline: float) -> tuple[bool, str]:
    """A step's `when`: does the condition hold within its short timeout?"""
    resolved = None
    if check.uses_target and target is not None:
        try:
            resolved = (await resolve(page, "when", target, deadline, stage="when")).locator
        except GuardFailure as g:
            return False, g.failure.actual
    while True:
        try:
            ok, actual = await asyncio.wait_for(evaluate(page, check, resolved), PROBE_S)
        except (PlaywrightError, asyncio.TimeoutError) as e:
            ok, actual = False, short_error(e)
        if ok or now() >= deadline:
            return ok, actual
        await asyncio.sleep(POLL_S)

