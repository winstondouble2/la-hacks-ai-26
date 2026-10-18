"""What a compiled run returns, and the failure it raises internally."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

# Where a run stopped: opening the start page, a step's `when` / target / pre-checks / action /
# post-checks, the program's success checks, or the browser itself.
Stage = Literal["browser", "navigate", "when", "resolve", "pre", "action", "post", "success"]


@dataclass(frozen=True)
class Failure:
    """Why a run failed. `check` is the check's short form, e.g. 'text_visible 2 × Blue Mug'."""

    step_id: str | None
    stage: Stage
    check: str
    expected: str
    actual: str
    url: str = ""
    locator_counts: tuple[int, ...] = ()  # visible matches per locator, for a target that didn't resolve
    screenshot: Path | None = None
    snapshot: Path | None = None  # trimmed accessibility snapshot of the page
    diagnostics_error: str | None = None  # why a screenshot or snapshot is missing

    @property
    def summary(self) -> str:
        where = f"{self.step_id} " if self.step_id else ""
        return f"{where}{self.stage}: {self.check}: expected {self.expected}; got {self.actual}"


class GuardFailure(Exception):
    """An expected execution failure (a check, the target, the action or the page). The public
    run boundary turns it into RunResult(success=False, failure=...)."""

    def __init__(self, failure: Failure):
        super().__init__(failure.summary)
        self.failure = failure


@dataclass(frozen=True)
class StepResult:
    step_id: str
    status: Literal["passed", "skipped", "failed"]
    locator: str | None = None  # the locator that resolved the target, e.g. css=#add
    locator_index: int | None = None  # its position in the step's locator list (0 = primary)
    seconds: float = 0.0

    @property
    def fallback_used(self) -> bool:
        return bool(self.locator_index)


@dataclass(frozen=True)
class RunResult:
    run_id: str
    program: str
    version: int
    success: bool
    seconds: float
    run_dir: Path
    steps: tuple[StepResult, ...] = ()
    failure: Failure | None = None
    # Usage is measured, not assumed: compiled replay has no model client, so these stay 0.
    llm_calls: int = 0
    tokens: int = 0
    usd: float = 0.0
    trace_id: str = ""

    @property
    def events_path(self) -> Path:
        return self.run_dir / "events.jsonl"

    def step(self, step_id: str) -> StepResult:
        return next(s for s in self.steps if s.step_id == step_id)
