"""Role A: replay compiled programs and heal broken steps. `python -m browseen run` calls run_program."""

from browseen.runtime.runner import RunResult, run_program, run_program_async

__all__ = ["RunResult", "run_program", "run_program_async"]
