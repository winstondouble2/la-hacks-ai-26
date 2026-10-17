"""Entry point: python -m browseen <command>. Commands are in browseen/cli.py.

  python -m browseen record | show | compile | run | diff | rollback ...
  python -m browseen --demo llm|compiled|healed|healed3    # Sentry trace demo, no agent
"""

from browseen.observability import init_sentry

init_sentry()  # also loads .env, which browser_use reads at import time

import argparse  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402

from browseen import cli  # noqa: E402
from browseen.tracing import (  # noqa: E402
    agent_span,
    llm_span,
    mark_healed,
    record_agent_result,
    run_span,
    step_span,
)


def demo(mode: str, break_step: int | None, tier: int = 2) -> None:
    """Stand-in for the real agent: shows the trace shape we want to see."""
    steps = [("goto", "/login"), ("type", "#user"), ("click", "#submit")]
    with run_span("demo login", mode, program_version=None if mode == "llm" else 1):
        for i, (action, target) in enumerate(steps):
            with step_span(i, action, mode, target) as span:
                if mode == "llm":
                    with llm_span("decide next action"):
                        time.sleep(0.6)
                if i == break_step:
                    mark_healed(span, f"selector {target} missing", tier=tier)
                    if tier == 3:
                        with agent_span("tier-3 healer", f"Accomplish step {i}: {action} {target}") as agent:
                            for _ in range(2):
                                with llm_span("agent step"):
                                    time.sleep(0.4)
                            record_agent_result(agent, "clicked 'Sign in'", input_tokens=6200, output_tokens=410)
                    else:
                        with llm_span("repair step"):
                            time.sleep(0.6)
                time.sleep(0.05)


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1].startswith("--demo"):
        parser = argparse.ArgumentParser(prog="python -m browseen")
        parser.add_argument("--demo", required=True, choices=["llm", "compiled", "healed", "healed3"])
        args = parser.parse_args()
        healing = args.demo.startswith("healed")
        demo("compiled" if healing else args.demo,
             break_step=2 if healing else None,
             tier=3 if args.demo == "healed3" else 2)
        return
    sys.exit(cli.main())


if __name__ == "__main__":
    main()
