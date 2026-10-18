"""The run's event stream: runs/<run_id>/events.jsonl, one JSON object per line.

Fields follow dashboard/src/events.ts. Per-event llm_calls / tokens / usd are what that event
cost; run_finished carries the run's totals plus `seconds` and `success`. `stage` is an
additive field on check events (when, resolve, pre, action, post, success, navigate).

Timestamps are UTC with millisecond precision and strictly increasing within a run, so the
dashboard's deduper, which keys on (run_id, ts, type, step), never merges two real events.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class EventLog:
    """Appends events for one run. Exactly one run_finished may be written."""

    def __init__(self, path: Path, run_id: str, program: str, version: int, mode: str = "compiled"):
        self.path = path
        self.base = {"run_id": run_id, "program": program, "version": version, "mode": mode}
        self.trace_id = ""
        self.finished = False
        self._last_ms = 0

    def _stamp(self) -> str:
        self._last_ms = max(int(time.time() * 1000), self._last_ms + 1)
        return _iso(self._last_ms)

    def emit(self, type_: str, *, step: str | None = None, detail: str = "", **extra: Any) -> dict[str, Any]:
        if self.finished:
            raise RuntimeError(f"run {self.base['run_id']} already finished; refusing to write {type_}")
        event = {"ts": self._stamp(), **self.base, "type": type_, "step": step, "tier": None, "detail": detail,
                 "diff": None, "llm_calls": 0, "tokens": 0, "usd": 0, "trace_id": self.trace_id, **extra}
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
        return event

    def finish(self, *, success: bool, seconds: float, detail: str, llm_calls: int = 0, tokens: int = 0,
               usd: float = 0.0) -> dict[str, Any]:
        event = self.emit("run_finished", detail=detail, llm_calls=llm_calls, tokens=tokens, usd=usd,
                          seconds=round(seconds, 3), success=success)
        self.finished = True
        return event
