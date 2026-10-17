"""Writes the dashboard's SAMPLE runs (hand-made, not real):

  runs/sample/events.jsonl          compiled replay of buy-item that heals s4 at tier 2
  runs/sample-agent/events.jsonl    the slow first run: the Browser Use agent doing the same task
  runs/sample-heal1/events.jsonl    s4 heals at tier 1 (fallback locator, no LLM)
  runs/sample-heal3/events.jsonl    tier 1 and 2 fail on s4, a Browser Use agent takes over (tier 3)
  runs/sample-blocked/events.jsonl  s7 (Place order, a write) fails its pre-check and is not healed

Costs use the claude-opus-5-5 prices from browseen/costs.py (USD per million tokens),
so the dashboard's dollar counters agree with the rest of the system.

  python runs/sample/make_samples.py
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

PRICE_IN, PRICE_OUT = 4.00, 20.00  # claude-opus-5-5, browseen/costs.py
ROOT = Path(__file__).parent.parent  # runs/


def usd(input_tokens: int, output_tokens: int) -> float:
    return round((input_tokens * PRICE_IN + output_tokens * PRICE_OUT) / 1_000_000, 4)


def write(run_dir: str, run_id: str, trace_id: str, start: datetime, rows: list[tuple]) -> None:
    """rows: (seconds from start, type, step, tier, detail, version, mode, (in, out) tokens or None)."""
    events, calls, tokens, cost = [], 0, 0, 0.0
    for t, typ, step, tier, detail, version, mode, llm in rows:
        e = {
            "ts": (start + timedelta(seconds=t)).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "run_id": run_id, "program": "buy-item", "version": version, "mode": mode,
            "type": typ, "step": step, "tier": tier, "detail": detail, "diff": None,
            "llm_calls": 0, "tokens": 0, "usd": 0, "trace_id": trace_id,
        }
        if llm:  # one LLM call made during this event
            e.update(llm_calls=1, tokens=sum(llm), usd=usd(*llm))
            calls, tokens, cost = calls + 1, tokens + sum(llm), cost + usd(*llm)
        if typ == "healed":
            e["diff"] = '- role=button[name="Add to cart"]\n+ role=button[name="Add to bag"]'
        if typ == "run_finished":  # totals for the whole run
            e.update(llm_calls=calls, tokens=tokens, usd=round(cost, 4), seconds=t,
                     success=not any(r[1] == "heal_failed" for r in rows))
        events.append(json.dumps(e, ensure_ascii=False))
    path = ROOT / run_dir / "events.jsonl"
    path.parent.mkdir(exist_ok=True)
    path.write_text("\n".join(events) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {path}: {len(events)} events, {calls} LLM calls, {tokens} tokens, ${cost:.4f}, {t:.1f} s")


START = datetime(2026, 10, 17, 21, 4, 9, 800_000, tzinfo=timezone.utc)

# Compiled replay: no LLM except the one tier-2 heal of s4.
C = "compiled"
write("sample", "r_042", "7da7a54de6bb4c149e0e9804dad3d661", START, [
    (0.00, "run_started", None, None, "Compiled run: Blue Mug x 2 for Ada Lovelace", 1, C, None),
    (0.10, "step_started", "s1", None, "Dismiss the cookie banner if one is shown", 1, C, None),
    (0.20, "check_passed", "s1", None, "No cookie banner, optional step skipped", 1, C, None),
    (0.30, "step_started", "s2", None, "Open the product page for Blue Mug", 1, C, None),
    (0.50, "check_passed", "s2", None, 'On /product.html, "Blue Mug" visible', 1, C, None),
    (0.60, "step_started", "s3", None, "Set the quantity to 2", 1, C, None),
    (0.75, "check_passed", "s3", None, "Quantity field holds 2", 1, C, None),
    (0.80, "step_started", "s4", None, "Add the product to the cart", 1, C, None),
    (1.10, "check_failed", "s4", None, 'role=button[name="Add to cart"] not found', 1, C, None),
    (1.20, "heal_started", "s4", 1, "Tier 1 missed, escalating to tier 2", 1, C, None),
    (1.40, "healed", "s4", 2, "'Add to cart' renamed to 'Add to bag'. Post-check passed.", 2, "healed", (9000, 530)),
    (1.50, "step_started", "s5", None, "Enter the customer's full name", 2, C, None),
    (1.60, "check_passed", "s5", None, "Full name holds Ada Lovelace", 2, C, None),
    (1.65, "step_started", "s6", None, "Enter the shipping address", 2, C, None),
    (1.75, "check_passed", "s6", None, "Address holds 1 Main St", 2, C, None),
    (1.80, "step_started", "s7", None, "Place the order", 2, C, None),
    (1.90, "check_passed", "s7", None, "On /done.html", 2, C, None),
    (2.00, "run_finished", None, None, "Order confirmed: 2 x Blue Mug. Program v2 saved.", 2, C, None),
])

# First run: the agent thinks before every action (one LLM call each), and its
# context grows as the page history accumulates.
A = "llm"
agent_rows = [(0.0, "run_started", None, None, "Agent run: Buy 2 Blue Mug and check out as Ada Lovelace", 1, A, None)]
steps = [
    ("s1", "Looks for a cookie banner; none shown", 4.1),
    ("s2", "Clicks the Blue Mug product link", 5.6),
    ("s3", "Types 2 into the Quantity field", 4.8),
    ("s4", "Clicks 'Add to cart'", 5.2),
    ("s5", "Types Ada Lovelace into Full name", 4.4),
    ("s6", "Types 1 Main St into Address", 4.6),
    ("s7", "Clicks 'Place order'", 5.3),
]
t = 0.0
for n, (step, detail, secs) in enumerate(steps):
    t += 0.2
    agent_rows.append((t, "step_started", step, None, "Agent decides the next action", 1, A, (5200 + 900 * n, 310)))
    t += secs
    agent_rows.append((t, "check_passed", step, None, detail, 1, A, None))
t += 1.6
agent_rows.append((t, "check_passed", None, None, "Agent verifies 'Order confirmed' and stops", 1, A, (11800, 140)))
t += 0.2
agent_rows.append((t, "run_finished", None, None, "Order confirmed: 2 x Blue Mug. Trace saved for compiling.", 1, A, None))
write("sample-agent", "r_041", "5b1c0e7a9d2f4c3a8e6b1d0f2a3c4e5f", START, agent_rows)


# The same compiled run up to s4, then each scenario diverges.
def compiled_until_s4(start_version: int = 1) -> list[tuple]:
    v = start_version
    return [
        (0.00, "run_started", None, None, "Compiled run: Blue Mug x 2 for Ada Lovelace", v, C, None),
        (0.10, "step_started", "s1", None, "Dismiss the cookie banner if one is shown", v, C, None),
        (0.20, "check_passed", "s1", None, "No cookie banner, optional step skipped", v, C, None),
        (0.30, "step_started", "s2", None, "Open the product page for Blue Mug", v, C, None),
        (0.50, "check_passed", "s2", None, 'On /product.html, "Blue Mug" visible', v, C, None),
        (0.60, "step_started", "s3", None, "Set the quantity to 2", v, C, None),
        (0.75, "check_passed", "s3", None, "Quantity field holds 2", v, C, None),
        (0.80, "step_started", "s4", None, "Add the product to the cart", v, C, None),
    ]


def finish_after_s4(t0: float, v: int, detail: str) -> list[tuple]:
    return [
        (t0 + 0.10, "step_started", "s5", None, "Enter the customer's full name", v, C, None),
        (t0 + 0.20, "check_passed", "s5", None, "Full name holds Ada Lovelace", v, C, None),
        (t0 + 0.25, "step_started", "s6", None, "Enter the shipping address", v, C, None),
        (t0 + 0.35, "check_passed", "s6", None, "Address holds 1 Main St", v, C, None),
        (t0 + 0.40, "step_started", "s7", None, "Place the order", v, C, None),
        (t0 + 0.50, "check_passed", "s7", None, "On /done.html", v, C, None),
        (t0 + 0.60, "run_finished", None, None, detail, v, C, None),
    ]


# M01 selector churn: the first locator misses, the css fallback still identifies the button.
write("sample-heal1", "r_043", "a1b2c3d4e5f60718293a4b5c6d7e8f90", START, compiled_until_s4() + [
    (0.95, "check_failed", "s4", None, 'role=button[name="Add to cart"] not unique after class churn', 1, C, None),
    (1.00, "heal_started", "s4", 1, "Tier 1: trying fallback locators", 1, C, None),
    (1.10, "healed", "s4", 1, "Fallback css=#add matched the recorded fingerprint. Post-check passed.", 1, "healed", None),
] + finish_after_s4(1.10, 1, "Order confirmed: 2 x Blue Mug. No new version (tier 1 heals are not saved)."))

# M10 new required field: no locator fix exists, the agent fills the phone number and clicks.
write("sample-heal3", "r_044", "b2c3d4e5f60718293a4b5c6d7e8f90a1", START, compiled_until_s4() + [
    (1.10, "check_failed", "s4", None, "Post-check failed: checkout requires a phone number", 1, C, None),
    (1.20, "heal_started", "s4", 1, "Tier 1 missed", 1, C, None),
    (1.40, "heal_started", "s4", 2, "Tier 2 patch rejected by the post-check", 1, C, (8800, 420)),
    (1.50, "heal_started", "s4", 3, "Tier 3: Browser Use agent takes over s4", 1, C, None),
    (5.30, "healed", "s4", 3, "Agent filled Phone and added to cart; sub-trace compiled as s4a. Post-check passed.", 2, "healed", (14600, 690)),
] + finish_after_s4(5.30, 2, "Order confirmed: 2 x Blue Mug. Program v2 saved (inserted s4a)."))

# M16 wrong-target trap on a write step: never heal blind, stop instead.
blocked = compiled_until_s4() + [
    (0.95, "check_passed", "s4", None, "On /checkout.html, 2 x Blue Mug in cart", 1, C, None),
    (1.00, "step_started", "s5", None, "Enter the customer's full name", 1, C, None),
    (1.10, "check_passed", "s5", None, "Full name holds Ada Lovelace", 1, C, None),
    (1.15, "step_started", "s6", None, "Enter the shipping address", 1, C, None),
    (1.25, "check_passed", "s6", None, "Address holds 1 Main St", 1, C, None),
    (1.30, "step_started", "s7", None, "Place the order", 1, C, None),
    (1.45, "check_failed", "s7", None, 'Pre-check: "Place order" now opens "Cancel order" (accessible name changed)', 1, C, None),
    (1.50, "heal_failed", "s7", None, "Write step: not healed automatically; needs approval", 1, C, None),
]
write("sample-blocked", "r_045", "c3d4e5f60718293a4b5c6d7e8f90a1b2", START, blocked + [
    (1.60, "run_finished", None, None, "Stopped before s7. Nothing was submitted.", 1, C, None),
])
