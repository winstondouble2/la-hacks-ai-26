"""Record an agent run, or show a recorded one.

  python -m browseen.recorder record "Buy $qty of $product and check out as $name, $address" \\
      --url http://localhost:8765/ --input product="Blue Mug" --input qty=2 \\
      --input name="Ada Lovelace" --input address="1 Main St" --name buy-item
  python -m browseen.recorder show runs/<run_id>          # no API calls
"""

from browseen.observability import init_sentry

init_sentry()  # also loads .env, which browser_use reads at import time

import argparse  # noqa: E402
import asyncio  # noqa: E402
import os  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

from browseen.recorder.record import RUNS_DIR, parse_inputs, record  # noqa: E402
from browseen.recorder.trace import load_trace  # noqa: E402


def show(run_dir: Path) -> None:
    trace = load_trace(run_dir)
    print(f"{trace.run_id}  {trace.name or ''}  model {trace.model}")
    print(f"task: {trace.task}")
    if trace.inputs:
        print(f"inputs: {trace.inputs}")
    for step in trace.steps:
        took = f"{step.duration_s:.1f}s" if step.duration_s is not None else "  -  "
        cost = f"{step.usage.tokens:>7,} tok ${step.usage.usd:.3f}" if step.usage.llm_calls else ""
        print(f"\nstep {step.number:<2} {took:>6}  {cost:<20} {step.url or ''}")
        if step.goal:
            print(f"  goal: {step.goal}")
        for action in step.actions:
            params = {k: v for k, v in action.params.items() if k != "index"}
            print(f"  {action.name} {params if params else ''}")
            if action.element:
                el = action.element
                print(f"    <{el.tag}> {el.ax_name!r}  {el.xpath}")
            if action.error:
                print(f"    error: {action.error}")
        if step.error:
            print(f"  error: {step.error}")
    u = trace.usage
    print(f"\n{len(trace.steps) - 1} steps in {trace.wall_s:.1f}s, {u.llm_calls} LLM calls, {u.tokens:,} tokens "
          f"(cache read {u.cache_read_tokens:,}), ${u.usd:.3f}. "
          f"Agent says: {'success' if trace.agent_success else 'not done'}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m browseen.recorder")
    sub = parser.add_subparsers(dest="cmd", required=True)
    rec = sub.add_parser("record", help="run the agent once and save the trace")
    rec.add_argument("task", help='task text; $name placeholders are filled from --input')
    rec.add_argument("--url", required=True, help="start page")
    rec.add_argument("--input", action="append", default=[], metavar="KEY=VALUE")
    rec.add_argument("--name", help="program name, e.g. buy-item")
    rec.add_argument("--headless", action="store_true")
    rec.add_argument("--max-steps", type=int, default=30)
    rec.add_argument("--runs-dir", type=Path, default=RUNS_DIR)
    shw = sub.add_parser("show", help="print a recorded run (no API calls)")
    shw.add_argument("run_dir", type=Path)
    args = parser.parse_args()

    if args.cmd == "show":
        show(args.run_dir)
        return
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key.")
    try:
        inputs = parse_inputs(args.input)
    except ValueError as e:
        sys.exit(str(e))
    trace, run_dir = asyncio.run(record(args.task, args.url, inputs, name=args.name, headless=args.headless,
                                        max_steps=args.max_steps, runs_dir=args.runs_dir))
    show(run_dir)
    print(f"\nsaved to {run_dir}/  (dashboard: ?run={trace.run_id})")
    sys.exit(0 if trace.agent_success else 1)


if __name__ == "__main__":
    main()
