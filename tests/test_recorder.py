"""Recorder tests that need no browser and no API: they build traces from a real recorded history."""

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from browseen.recorder.record import parse_inputs, record, usage_from_entries
from browseen.recorder.trace import StepCapture, Trace, Usage, build_trace

FIXTURE = Path(__file__).parent / "fixtures" / "smoke_history.json"  # the Oct 17 mini-shop run
META = dict(
    run_id="r_test", name="buy-item", task_template="Buy $qty of $product", inputs={"qty": 2, "product": "Blue Mug"},
    task="Buy 2 of Blue Mug", start_url="http://localhost:8765/", model="claude-opus-5-5",
    browser_use_version="0.13.11", started_at=datetime(2026, 10, 17, tzinfo=timezone.utc), wall_s=30.0,
)


def make_trace(captures=None) -> Trace:
    return build_trace(json.loads(FIXTURE.read_text()), captures=captures or {}, **META)


def test_steps_start_with_the_initial_navigation():
    trace = make_trace()
    assert [s.number for s in trace.steps] == list(range(7))
    first = trace.steps[0].actions[0]
    assert first.name == "navigate" and first.params["url"] == "http://localhost:8765/"
    assert first.element is None


def test_click_records_the_element():
    action = make_trace().steps[1].actions[0]
    assert action.name == "click"
    el = action.element
    assert el.tag == "a"
    assert el.xpath == "/html/body/main/ul/li[1]/a"  # leading slash added
    assert el.ax_name == "Blue Mug"
    assert el.attributes["href"] == "product.html?id=blue-mug"


def test_a_step_with_two_actions_keeps_each_element():
    step = make_trace().steps[4]
    assert [a.name for a in step.actions] == ["input", "input"]
    assert [a.params["text"] for a in step.actions] == ["Ada Lovelace", "1 Main St"]
    assert [a.element.ax_name for a in step.actions] == ["Full name", "Address"]


def test_done_and_agent_claims():
    trace = make_trace()
    done = trace.steps[-1].actions[0]
    assert done.name == "done" and done.element is None
    assert trace.agent_done and trace.agent_success
    assert "Order confirmed" in trace.final_result


def test_goal_url_and_duration():
    step = make_trace().steps[3]
    assert step.goal == "Click Add to cart."
    assert step.url == "http://localhost:8765/product.html?id=blue-mug"
    assert step.duration_s > 0


def test_captures_fill_in_pages_and_usage():
    usage = Usage(llm_calls=1, input_tokens=100, cache_read_tokens=50, output_tokens=10, usd=0.0006)
    trace = make_trace({1: StepCapture(html_before="html/step_01_before.html", url_after="http://x/p", usage=usage)})
    assert trace.steps[1].html_before == "html/step_01_before.html"
    assert trace.steps[1].url_after == "http://x/p"
    assert trace.usage.llm_calls == 1 and trace.usage.tokens == 160


def test_json_round_trip():
    trace = make_trace()
    assert Trace.model_validate_json(trace.model_dump_json()) == trace


def test_usage_from_entries_splits_cache_tokens():
    entry = SimpleNamespace(model="claude-opus-5-5", usage=SimpleNamespace(
        prompt_tokens=1000, prompt_cached_tokens=600, prompt_cache_creation_tokens=200, completion_tokens=50))
    u = usage_from_entries([entry, entry])
    assert (u.llm_calls, u.input_tokens, u.cache_read_tokens, u.cache_write_tokens, u.output_tokens) == (2, 800, 1200, 400, 100)
    assert u.usd == pytest.approx(2 * (400 * 4 + 50 * 20 + 600 * 0.20 + 200 * 5) / 1e6)


def test_parse_inputs_types_numbers():
    assert parse_inputs(["qty=2", "product=Blue Mug", "price=1.5", "note=a=b"]) == {
        "qty": 2, "product": "Blue Mug", "price": 1.5, "note": "a=b"}
    with pytest.raises(ValueError):
        parse_inputs(["no-equals-sign"])


def test_record_rejects_a_task_with_missing_inputs(tmp_path):
    # Fails before any browser or API call.
    with pytest.raises(ValueError, match="qty"):
        asyncio.run(record("Buy $qty of $product", "http://localhost:8765/", {"product": "Blue Mug"}, runs_dir=tmp_path))
    assert not any(tmp_path.iterdir())
