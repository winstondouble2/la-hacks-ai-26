"""The run event stream: one JSON object per line in runs/<run_id>/events.jsonl.

Format: docs/architecture.md → "Event stream" and dashboard/src/events.ts. The recorder writes
mode "llm" runs (version 0); the runtime writes "compiled" runs and marks healed steps "healed".
Per-event llm_calls / tokens / usd are what that event cost; run_finished carries the totals.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from browseen.recorder.trace import Usage


class EventLog:
    def __init__(self, path: Path, *, run_id: str, program: str, trace_id: str = "",
                 version: int = 0, mode: str = "llm"):
        self.path, self.run_id, self.program, self.trace_id = Path(path), run_id, program, trace_id
        self.version, self.mode = version, mode
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, type: str, *, step: str | None = None, tier: int | None = None, detail: str = "",
             diff: str | None = None, usage: Usage | None = None, mode: str | None = None,
             version: int | None = None, **extra: Any) -> dict[str, Any]:
        usage = usage or Usage()
        event = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "run_id": self.run_id, "program": self.program,
            "version": self.version if version is None else version,
            "mode": mode or self.mode, "type": type, "step": step, "tier": tier, "detail": detail, "diff": diff,
            "llm_calls": usage.llm_calls, "tokens": usage.tokens,
            "input_tokens": usage.input_tokens + usage.cache_read_tokens + usage.cache_write_tokens,
            "output_tokens": usage.output_tokens, "usd": round(usage.usd, 4),
            "trace_id": self.trace_id, **extra,
        }
        with self.path.open("a") as f:
            f.write(json.dumps(event) + "\n")
        return event
