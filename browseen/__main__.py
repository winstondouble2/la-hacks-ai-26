"""Entry point: python -m browseen"""

from browseen.observability import init_sentry

init_sentry()

import argparse  # noqa: E402
import time  # noqa: E402

from browseen.tracing import (  # noqa: E402
    agent_span,
    llm_span,
    log_check,
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
            step_id = f"s{i + 1}"
            with step_span(i, action, mode, target, step_id=step_id) as span:
                if mode == "llm":
                    with llm_span("decide next action"):
                        time.sleep(0.6)
                if i == break_step:
                    log_check(span, step_id, f"pre target_unique {target}", passed=False, detail="0 matches")
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
                log_check(span, step_id, f"post after {action} {target}", passed=True)
                time.sleep(0.05)


def main() -> None:
    parser = argparse.ArgumentParser(prog="browseen")
    parser.add_argument("task", nargs="?", help="task for the browser agent")
    parser.add_argument("--demo", choices=["llm", "compiled", "healed", "healed3"])
    args = parser.parse_args()

    if args.demo:
        healing = args.demo.startswith("healed")
        demo("compiled" if healing else args.demo,
             break_step=2 if healing else None,
             tier=3 if args.demo == "healed3" else 2)
        return
    if not args.task:
        parser.error("no task given")
    print(f"TODO: run agent for task: {args.task}")


if __name__ == "__main__":
    main()
