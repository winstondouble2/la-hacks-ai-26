"""Entry point: python -m browseen"""

from browseen.observability import init_sentry

init_sentry()

import argparse  # noqa: E402

import sentry_sdk  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(prog="browseen")
    parser.add_argument("task", nargs="?", help="task for the browser agent")
    args = parser.parse_args()

    with sentry_sdk.start_transaction(op="agent.run", name="browseen run"):
        if not args.task:
            parser.error("no task given")
        print(f"TODO: run agent for task: {args.task}")


if __name__ == "__main__":
    main()
