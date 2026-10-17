"""Evaluate program checks against the live page (Playwright async API)."""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any

from browseen.program import Check

POLL_S = 0.15


def describe(check: Check) -> str:
    """Short form for events and logs, e.g. 'url_matches /cart(\\?|#|$)'."""
    kind = check.kind
    value = getattr(check, kind)
    if kind in ("exists", "absent"):
        return f"{kind} {value.describe()}"
    if kind in ("target_unique", "target_enabled"):
        return kind
    return f"{kind} {value}"


async def _once(page: Any, check: Check, target: Any | None) -> bool:
    kind = check.kind
    if kind == "url_matches":
        return re.search(check.url_matches, page.url) is not None
    if kind == "text_visible":
        found = page.get_by_text(check.text_visible)
        return await found.count() > 0 and await found.first.is_visible()
    if kind == "exists":
        return await check.exists.to_playwright(page).count() > 0
    if kind == "absent":
        return await check.absent.to_playwright(page).count() == 0
    if target is None:
        return False
    if kind == "target_unique":
        return await target.count() == 1
    if kind == "target_enabled":
        return await target.is_enabled()
    return await target.input_value() == check.target_value  # target_value


async def evaluate(page: Any, check: Check, target: Any | None = None, timeout_ms: int = 5000) -> tuple[bool, str]:
    """Poll the check until it passes or the timeout runs out. Returns (passed, what was seen)."""
    deadline = time.monotonic() + timeout_ms / 1000
    while True:
        try:
            if await _once(page, check, target):
                return True, ""
        except Exception as e:  # a detached element or a navigation in progress: try again
            last_error = str(e).splitlines()[0][:120]
        else:
            last_error = ""
        if time.monotonic() >= deadline:
            seen = f"url is {page.url}" if check.kind == "url_matches" else last_error or "not satisfied"
            return False, seen
        await asyncio.sleep(POLL_S)
