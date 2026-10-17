"""Compile a recorded run into a program (no LLM).

  python -m browseen.compiler runs/<run_id> --name mini-shop          # writes programs/mini-shop/v1.yaml
  python -m browseen.compiler runs/<run_id> --name mini-shop --dry-run
"""

import argparse
import sys
from pathlib import Path

from browseen.compiler.compile import compile_run
from browseen.program import PROGRAMS_DIR
from browseen.recorder.trace import load_trace


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m browseen.compiler")
    parser.add_argument("run_dir", type=Path, help="a recorded run, e.g. runs/r_20261017-142906")
    parser.add_argument("--name", help="program name (defaults to the name given when recording)")
    parser.add_argument("--programs-dir", type=Path, default=PROGRAMS_DIR)
    parser.add_argument("--dry-run", action="store_true", help="print the program instead of saving it")
    args = parser.parse_args()

    name = args.name or load_trace(args.run_dir).name
    if not name:
        sys.exit("this run has no name; pass --name")
    try:
        program, report, path = compile_run(args.run_dir, name, args.programs_dir, dry_run=args.dry_run)
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
        print(f"  {step.id:<4} {step.action.type:<8} {first:<42} {step.intent}")


if __name__ == "__main__":
    main()
