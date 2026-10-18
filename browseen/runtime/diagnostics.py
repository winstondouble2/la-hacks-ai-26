"""Bounded evidence for a failed run: a screenshot and a trimmed accessibility snapshot.

Capture never raises: anything that goes wrong is reported in `error`, so it can't hide the
failure being diagnosed. Files go in the run's own folder (runs/<run_id>/).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SNAPSHOT_MAX_CHARS = 8000
CAPTURE_TIMEOUT_MS = 3000
_TRUNCATED = "\n… (truncated)"


@dataclass(frozen=True)
class Diagnostics:
    screenshot: Path | None
    snapshot: Path | None
    error: str | None


async def _screenshot(page: Any, path: Path) -> None:
    await page.screenshot(path=str(path), timeout=CAPTURE_TIMEOUT_MS)


async def _snapshot(page: Any) -> str:
    return await page.locator("body").aria_snapshot(timeout=CAPTURE_TIMEOUT_MS)


def short_error(e: BaseException) -> str:
    """'TimeoutError: Timeout 1500ms exceeded.' without Playwright's multi-line call log."""
    first = (str(e).strip().splitlines() or [""])[0]
    return f"{type(e).__name__}: {first[:300]}"


def _trim(text: str) -> str:
    if len(text) <= SNAPSHOT_MAX_CHARS:
        return text
    return text[: SNAPSHOT_MAX_CHARS - len(_TRUNCATED)] + _TRUNCATED


async def capture(page: Any, run_dir: Path, label: str) -> Diagnostics:
    label = re.sub(r"[^A-Za-z0-9_-]", "_", label)
    errors: list[str] = []
    screenshot: Path | None = run_dir / f"{label}.png"
    try:
        await _screenshot(page, screenshot)
    except Exception as e:  # noqa: BLE001 - reported, never raised
        errors.append(f"screenshot: {short_error(e)}")
        screenshot = None
    snapshot: Path | None = run_dir / f"{label}.aria.yaml"
    try:
        snapshot.write_text(_trim(await _snapshot(page)), encoding="utf-8")
    except Exception as e:  # noqa: BLE001 - reported, never raised
        errors.append(f"snapshot: {short_error(e)}")
        snapshot = None
    return Diagnostics(screenshot, snapshot, "; ".join(errors) or None)
