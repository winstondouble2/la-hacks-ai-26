"""Compile a recorded run into a program.

  python -m browseen.compiler runs/<run_id> --name mini-shop          # writes programs/mini-shop/v1.yaml
  python -m browseen.compiler runs/<run_id> --name mini-shop --dry-run
  python -m browseen.compiler runs/<run_id> --name mini-shop --no-llm # compiler v0 only
"""

from browseen.observability import init_sentry

init_sentry()  # loads .env (ANTHROPIC_API_KEY); the Anthropic call shows up in Sentry

import argparse  # noqa: E402
import os  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

from browseen.compiler.annotate import annotate  # noqa: E402
from browseen.compiler.compile import compile_run  # noqa: E402
from browseen.program import PROGRAMS_DIR  # noqa: E402
from browseen.recorder.trace import load_trace  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m browseen.compiler")
    parser.add_argument("run_dir", type=Path, help="a recorded run, e.g. runs/r_20261017-142906")
    parser.add_argument("--name", help="program name (defaults to the name given when recording)")
    parser.add_argument("--programs-dir", type=Path, default=PROGRAMS_DIR)
    parser.add_argument("--dry-run", action="store_true", help="print the program instead of saving it")
    parser.add_argument("--no-llm", action="store_true", help="skip the LLM pass (compiler v0 output)")
    args = parser.parse_args()

    name = args.name or load_trace(args.run_dir).name
    if not name:
        sys.exit("this run has no name; pass --name")
    use_llm = not args.no_llm
    if use_llm and not os.environ.get("ANTHROPIC_API_KEY"):
        print("warning: ANTHROPIC_API_KEY is not set, so compiling without the LLM pass (v0)", file=sys.stderr)
        use_llm = False
    try:
        program, report, path = compile_run(args.run_dir, name, args.programs_dir, dry_run=args.dry_run,
                                            annotate_with=annotate if use_llm else None)
    except (FileExistsError, ValueError) as e:
        sys.exit(str(e))

    print(report.render())
    print()
    if args.dry_run:
        print(program.to_yaml())
        return
    print(f"wrote {path}: {program.program} v{program.version}, {len(program.steps)} steps, params {list(program.params)}")
    for step in program.steps:
        first = step.target.locators[0].describe() if step.target else ""
        optional = "  (optional)" if step.when else ""
        print(f"  {step.id:<4} {step.action.type:<8} {first:<42} {step.intent}{optional}")


if __name__ == "__main__":
    main()
