"""Smoke test: run one Browser Use agent with Claude on the mini shop fixture, then
report which fields its history records per step (what the recorder can rely on).

  python -m http.server 8765 -d browseen/recorder/fixtures/mini_shop   # in another terminal
  python -m browseen.recorder.smoke                                     # runs the agent (costs tokens)
  python -m browseen.recorder.smoke --inspect runs/smoke                # re-print the report, no API calls
"""

from browseen.observability import init_sentry

init_sentry()  # also loads .env, which browser_use reads at import time

import argparse  # noqa: E402
import asyncio  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402

from browseen.tracing import run_span  # noqa: E402

DEFAULT_URL = "http://localhost:8765/"
DEFAULT_TASK = "Go to {url} and buy 2 Blue Mugs. Check out as Ada Lovelace, 1 Main St."
MODEL = "claude-opus-5-5"
ELEMENT_FIELDS = ("node_name", "x_path", "ax_name", "attributes")
# Chromium on macOS can hang at startup on a keychain prompt (browser-use #5415).
CHROME_ARGS = ["--use-mock-keychain", "--password-store=basic"]


async def run_agent(task: str, out: Path, headless: bool, max_steps: int) -> bool:
    from browser_use import Agent, BrowserProfile, ChatAnthropic

    out.mkdir(parents=True, exist_ok=True)

    async def save_html(agent, name: str) -> None:
        # Dry run of the recorder's page capture. History item 0 is the initial navigation,
        # so len(history) is the number of the step about to run (before) or just run + 1 (after).
        try:
            page = await agent.browser_session.get_current_page()
            if page is None:
                return
            html = await page.evaluate("() => document.documentElement.outerHTML")
            (out / name).write_text(html)
        except Exception as e:  # never let capture break the agent run
            print(f"[capture] {name}: {e}", file=sys.stderr)

    async def before_step(agent) -> None:
        # The page the step's target element lives on: what the compiler tests locators against.
        await save_html(agent, f"step_{len(agent.history.history):02d}_before.html")

    async def after_step(agent) -> None:
        await save_html(agent, f"step_{len(agent.history.history) - 1:02d}_after.html")

    llm = ChatAnthropic(
        model=MODEL,
        # Opus 5.5 rejects forced tool_choice; setting thinking makes the wrapper use "auto".
        thinking={"type": "adaptive"},
        max_tokens=16000,
        # Server-side fallback: if Opus 5.5 refuses a step, Anthropic retries it on this model.
        fallbacks=[{"model": "claude-opus-4-8"}],
    )
    # No default extensions: they include a cookie-banner auto-dismisser, and we want the
    # agent to see the page exactly as served (also avoids their download on startup).
    profile = BrowserProfile(headless=headless, args=CHROME_ARGS, enable_default_extensions=False)
    # use_thinking=False: Browser Use's default output has a "thinking" field, which Opus 5.5
    # refuses as reasoning extraction (stop_reason "refusal").
    agent = Agent(task=task, llm=llm, browser_profile=profile, use_judge=False, use_thinking=False)

    started = time.monotonic()
    with run_span(task, "llm"):
        history = await agent.run(max_steps=max_steps, on_step_start=before_step, on_step_end=after_step)
    wall_s = time.monotonic() - started

    # save_to_file() leaves out token usage (browser-use #5767), so it gets its own file.
    history.save_to_file(str(out / "history.json"))
    usage = history.usage.model_dump(mode="json") if history.usage else None
    (out / "usage.json").write_text(json.dumps(usage, indent=2))
    summary = {
        "task": task,
        "model": MODEL,
        "wall_s": round(wall_s, 1),
        "steps": history.number_of_steps(),
        "is_done": history.is_done(),
        "is_successful": history.is_successful(),
        "final_result": history.final_result(),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    return bool(summary["is_done"] and summary["is_successful"])


def report(out: Path) -> None:
    """Print what each recorded step contains. Reads only the saved files."""
    history = json.loads((out / "history.json").read_text())["history"]
    usage = json.loads((out / "usage.json").read_text()) if (out / "usage.json").exists() else None
    summary = json.loads((out / "summary.json").read_text()) if (out / "summary.json").exists() else {}

    seen = {f: 0 for f in ELEMENT_FIELDS}
    n_elements = 0
    for item in history:
        meta = item.get("metadata") or {}
        output = item.get("model_output") or {}
        state = item.get("state") or {}
        actions = [name for a in output.get("action") or [] for name in a]
        duration = ""
        if meta.get("step_start_time") and meta.get("step_end_time"):
            duration = f"{meta['step_end_time'] - meta['step_start_time']:.1f}s"
        print(f"\nstep {meta.get('step_number', '?')}  {duration}  {state.get('url', '')}")
        print(f"  actions:   {', '.join(actions) or '-'}")
        print(f"  next_goal: {(output.get('next_goal') or '-')[:100]}")
        for result in item.get("result") or []:
            if result.get("error"):
                print(f"  error:     {result['error'][:100]}")
        for el in state.get("interacted_element") or []:
            if not el:
                continue
            n_elements += 1
            present = [f for f in ELEMENT_FIELDS if el.get(f)]
            for f in present:
                seen[f] += 1
            missing = [f for f in ELEMENT_FIELDS if f not in present]
            print(f"  element:   <{el.get('node_name', '?')}> ax_name={el.get('ax_name')!r} "
                  f"attrs={sorted((el.get('attributes') or {}).keys())}")
            print(f"             x_path={el.get('x_path')}" + (f"  MISSING {missing}" if missing else ""))

    print("\n=== summary")
    print(f"steps: {len(history)}  wall: {summary.get('wall_s', '?')}s  "
          f"done: {summary.get('is_done')}  success: {summary.get('is_successful')}")
    print(f"elements: {n_elements}  " + "  ".join(f"{f}: {seen[f]}/{n_elements}" for f in ELEMENT_FIELDS))
    if usage:
        print(f"tokens: prompt {usage.get('total_prompt_tokens')}  completion "
              f"{usage.get('total_completion_tokens')}  total {usage.get('total_tokens')}")
    if summary.get("final_result"):
        print(f"final result: {summary['final_result'][:200]}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m browseen.recorder.smoke")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--task", help="defaults to buying 2 Blue Mugs on --url")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--max-steps", type=int, default=25)
    parser.add_argument("--out", type=Path, default=Path("runs/smoke"))
    parser.add_argument("--inspect", type=Path, metavar="DIR", help="only print the report for a saved run")
    args = parser.parse_args()

    if args.inspect:
        report(args.inspect)
        return
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key.")

    task = args.task or DEFAULT_TASK.format(url=args.url)
    ok = asyncio.run(run_agent(task, args.out, args.headless, args.max_steps))
    report(args.out)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
