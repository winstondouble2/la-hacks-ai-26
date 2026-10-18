"""Role A runtime: compiled replay of a program on Playwright, with zero LLM calls.

  from browseen.runtime import run_program
  result = run_program(program, params, headless=True)   # RunResult; result.success, result.failure

The CLI (`python -m browseen run`) calls run_program. Events go to runs/<run_id>/events.jsonl.
"""

from browseen.runtime.models import Failure, GuardFailure, RunResult, StepResult
from browseen.runtime.preflight import new_run_id
from browseen.runtime.runner import run_program, run_program_async

__all__ = ["Failure", "GuardFailure", "RunResult", "StepResult", "new_run_id", "run_program", "run_program_async"]
