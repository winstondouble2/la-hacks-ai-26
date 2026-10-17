"""The Browseen command line: python -m browseen <command>.

  record    run the agent once on a task and save the trace             (B)
  show      print a recorded run, no API calls                          (B)
  compile   recorded run -> program, with one LLM pass (--no-llm: v0)   (B)
  run       replay a program with new inputs, healing as needed         (A)
  diff      what changed between two versions of a program              (B)
  rollback  save the next version as a copy of an older one             (B)
  serve     the run API for the dashboard                               (A)

The entry modules (browseen/__main__.py and friends) call init_sentry() before using this,
so .env is loaded before browser_use is imported.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import importlib.util
import os
import sys
from pathlib import Path

from browseen import program as P
from browseen.recorder.trace import load_trace

RUNTIME_MODULE = "browseen.runtime"  # run_program(program, params, *, headless, **options)
RUNS_DIR = Path("runs")


def print_run(run_dir: Path) -> None:
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


def print_steps(program: P.Program) -> None:
    for step in program.steps:
        first = step.target.locators[0].describe() if step.target else ""
        optional = "  (optional)" if step.when else ""
        print(f"  {step.id:<4} {step.action.type:<8} {first:<42} {step.intent}{optional}")


def load_program(ref: str, version: int | None = None, root: Path = P.PROGRAMS_DIR) -> P.Program:
    """A program by file path, or by name (latest version unless `version` is given)."""
    path = Path(ref)
    if path.suffix in (".yaml", ".yml") and path.exists():
        return P.load(path)
    if version is not None:
        file = P.program_path(ref, version, root)
        if not file.exists():
            raise FileNotFoundError(f"{ref} has no v{version}; versions: {P.versions(ref, root)}")
        return P.load(file)
    return P.latest(ref, root)


def cmd_record(args: argparse.Namespace) -> int:
    from browseen.recorder.record import parse_inputs, record

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key.")
    inputs = parse_inputs(args.input)
    trace, run_dir = asyncio.run(record(args.task, args.url, inputs, name=args.name, headless=args.headless,
                                        max_steps=args.max_steps, runs_dir=args.runs_dir))
    print_run(run_dir)
    print(f"\nsaved to {run_dir}/  (dashboard: ?run={trace.run_id})")
    print(f"next: python -m browseen compile {run_dir}" + ("" if args.name else " --name <name>"))
    return 0 if trace.agent_success else 1


def cmd_show(args: argparse.Namespace) -> int:
    print_run(args.run_dir)
    return 0


def cmd_compile(args: argparse.Namespace) -> int:
    from browseen.compiler.annotate import annotate
    from browseen.compiler.compile import compile_run

    name = args.name or load_trace(args.run_dir).name
    if not name:
        sys.exit("this run has no name; pass --name")
    use_llm = not args.no_llm
    if use_llm and not os.environ.get("ANTHROPIC_API_KEY"):
        print("warning: ANTHROPIC_API_KEY is not set, so compiling without the LLM pass (v0)", file=sys.stderr)
        use_llm = False
    program, report, path = compile_run(args.run_dir, name, args.programs_dir, dry_run=args.dry_run,
                                        annotate_with=annotate if use_llm else None)
    print(report.render())
    print()
    if args.dry_run:
        print(program.to_yaml())
        return 0
    print(f"wrote {path}: {program.program} v{program.version}, {len(program.steps)} steps, params {list(program.params)}")
    print_steps(program)
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    from browseen.recorder.record import parse_inputs

    program = load_program(args.program, args.version, args.programs_dir)
    params = parse_inputs(args.param)
    try:
        program.resolved(params)  # all params given, none unknown
    except KeyError as e:
        needed = " ".join(f'--param {k}="{p.example}"' for k, p in program.params.items())
        sys.exit(f"{e.args[0]}. {program.program} takes: {needed}")
    if importlib.util.find_spec(RUNTIME_MODULE) is None:
        sys.exit(f"The runtime isn't on this branch yet: `run` calls {RUNTIME_MODULE}.run_program(program, params, "
                 "*, headless), which role A is building. Pull A's work, then try again.")
    run_program = importlib.import_module(RUNTIME_MODULE).run_program
    options = {"programs_dir": args.programs_dir}  # heals are saved next to the program
    if args.query:
        options["url_params"] = parse_inputs(args.query)
    if args.no_heal:
        options["healing"] = False
    if args.tiers:
        options["tiers"] = tuple(int(t) for t in args.tiers.split(","))
    result = run_program(program, params, headless=args.headless, **options)
    return 0 if getattr(result, "success", result) else 1


def cmd_diff(args: argparse.Namespace) -> int:
    found = P.versions(args.program, args.programs_dir)
    if not found:
        raise FileNotFoundError(f"no versions of {args.program!r} under {args.programs_dir}")
    # diff NAME: previous vs latest. diff NAME 1: v1 vs latest. diff NAME 1 3: v1 vs v3.
    if len(args.versions) > 2:
        sys.exit("give at most two versions")
    if len(args.versions) == 2:
        older, newer = args.versions
    else:
        newer = found[-1]
        older = args.versions[0] if args.versions else newer
        if older == newer:
            earlier = [v for v in found if v < newer]
            if not earlier:
                sys.exit(f"nothing to compare: {args.program} has only v{newer}")
            older = earlier[-1]
    a, b = load_program(args.program, older, args.programs_dir), load_program(args.program, newer, args.programs_dir)
    changes = P.changed_steps(a, b)
    summary = ", ".join(f"{kind}: {' '.join(ids)}" for kind, ids in changes.items() if ids) or "no step changes"
    print(f"{args.program} v{a.version} → v{b.version}  ({summary})")
    print(P.diff(a, b) or "no differences")
    return 0


def cmd_rollback(args: argparse.Namespace) -> int:
    new = P.rollback(args.program, args.to, args.programs_dir)
    print(f"saved {new.program} v{new.version}, a copy of v{args.to}. Earlier versions are kept.")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from browseen.api import create_app

    uvicorn.run(create_app(runs_dir=args.runs_dir, programs_dir=args.programs_dir), host=args.host, port=args.port)
    return 0


def build_parser(prog: str = "python -m browseen") -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=prog, description="Record a browser agent once, replay it for free.",
                                     epilog="Sentry trace demo without an agent: python -m browseen --demo "
                                            "llm|compiled|healed|healed3")
    sub = parser.add_subparsers(dest="cmd", required=True, metavar="command")

    rec = sub.add_parser("record", help="run the agent once on a task and save the trace")
    rec.add_argument("task", help="task text; $name placeholders are filled from --input")
    rec.add_argument("--url", required=True, help="start page")
    rec.add_argument("--input", action="append", default=[], metavar="KEY=VALUE")
    rec.add_argument("--name", help="program name, e.g. buy-item")
    rec.add_argument("--headless", action="store_true")
    rec.add_argument("--max-steps", type=int, default=30)
    rec.add_argument("--runs-dir", type=Path, default=RUNS_DIR)
    rec.set_defaults(func=cmd_record)

    shw = sub.add_parser("show", help="print a recorded run (no API calls)")
    shw.add_argument("run_dir", type=Path)
    shw.set_defaults(func=cmd_show)

    cmp = sub.add_parser("compile", help="compile a recorded run into a program")
    cmp.add_argument("run_dir", type=Path, help="a recorded run, e.g. runs/r_20261017-142906")
    cmp.add_argument("--name", help="program name (defaults to the name given when recording)")
    cmp.add_argument("--programs-dir", type=Path, default=P.PROGRAMS_DIR)
    cmp.add_argument("--dry-run", action="store_true", help="print the program instead of saving it")
    cmp.add_argument("--no-llm", action="store_true", help="skip the LLM pass (compiler v0 output)")
    cmp.set_defaults(func=cmd_compile)

    run = sub.add_parser("run", help="replay a program with new inputs (A's runtime)")
    run.add_argument("program", help="program name or path to a .yaml file")
    run.add_argument("--param", action="append", default=[], metavar="KEY=VALUE")
    run.add_argument("--version", type=int, help="a specific version (default: latest)")
    run.add_argument("--headless", action="store_true")
    run.add_argument("--query", action="append", default=[], metavar="KEY=VALUE",
                     help="override a start-URL query parameter, e.g. mut=M04 for a testbed mutation")
    run.add_argument("--no-heal", action="store_true", help="fail on the first broken step instead of healing")
    run.add_argument("--tiers", help="healing tiers to try, in order (default 1,2,3), e.g. 1 or 3")
    run.add_argument("--programs-dir", type=Path, default=P.PROGRAMS_DIR)
    run.set_defaults(func=cmd_run)

    dif = sub.add_parser("diff", help="what changed between two versions (default: previous vs latest)")
    dif.add_argument("program", help="program name")
    dif.add_argument("versions", nargs="*", type=int, help="zero, one or two version numbers")
    dif.add_argument("--programs-dir", type=Path, default=P.PROGRAMS_DIR)
    dif.set_defaults(func=cmd_diff)

    rb = sub.add_parser("rollback", help="save the next version as a copy of an older one")
    rb.add_argument("program", help="program name")
    rb.add_argument("--to", type=int, required=True, help="the version to restore")
    rb.add_argument("--programs-dir", type=Path, default=P.PROGRAMS_DIR)
    rb.set_defaults(func=cmd_rollback)

    srv = sub.add_parser("serve", help="start the run API the dashboard calls (dashboard/API_CONTRACT.md)")
    srv.add_argument("--host", default="127.0.0.1")
    srv.add_argument("--port", type=int, default=8000)
    srv.add_argument("--runs-dir", type=Path, default=RUNS_DIR)
    srv.add_argument("--programs-dir", type=Path, default=P.PROGRAMS_DIR)
    srv.set_defaults(func=cmd_serve)
    return parser


def main(argv: list[str] | None = None, *, prog: str = "python -m browseen") -> int:
    args = build_parser(prog).parse_args(argv)
    try:
        return args.func(args)
    except (FileNotFoundError, FileExistsError, ValueError) as e:
        sys.exit(f"error: {e}")
