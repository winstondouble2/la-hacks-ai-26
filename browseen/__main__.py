"""Entry point: python -m browseen"""

from browseen.observability import init_sentry

init_sentry()

import argparse  # noqa: E402
import time  # noqa: E402

from browseen.tracing import llm_span, mark_healed, run_span, step_span  # noqa: E402


def demo(mode: str, break_step: int | None) -> None:
    """Stand-in for the real agent: shows the trace shape we want to see."""
    steps = [("goto", "/login"), ("type", "#user"), ("click", "#submit")]
    with run_span("demo login", mode):
        for i, (action, target) in enumerate(steps):
            with step_span(i, action, target) as span:
                if mode == "llm":
                    with llm_span("decide next action"):
                        time.sleep(0.6)
                if i == break_step:
                    mark_healed(span, f"selector {target} missing")
                    with llm_span("repair step"):
                        time.sleep(0.6)
                time.sleep(0.05)


def main() -> None:
    parser = argparse.ArgumentParser(prog="browseen")
    parser.add_argument("task", nargs="?", help="task for the browser agent")
    parser.add_argument("--demo", choices=["llm", "compiled", "healed"])
    args = parser.parse_args()

    if args.demo:
        demo("compiled" if args.demo == "healed" else args.demo,
             break_step=2 if args.demo == "healed" else None)
        return
    if not args.task:
        parser.error("no task given")
    print(f"TODO: run agent for task: {args.task}")


if __name__ == "__main__":
    main()
