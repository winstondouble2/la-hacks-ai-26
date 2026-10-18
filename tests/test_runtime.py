"""Role A runtime: compiled replay with Playwright, zero LLM calls, truthful failures.

Runs B's programs/buy-item/v1.yaml against the mini shop, served by the Role A fixture in
tests/fixtures/role_a_runtime (no server, no network). Sentry stays off; no model is called.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import sentry_sdk
import yaml

from browseen import program as P
from browseen.runtime import RunResult, new_run_id, run_program
from browseen.runtime import diagnostics
from browseen.runtime.text import text_found

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "role_a_runtime"
sys.path.insert(0, str(FIXTURE))
from role_a_site import FixtureSite  # noqa: E402  (Role A fixture helper)

BUY_ITEM = ROOT / "programs" / "buy-item" / "v1.yaml"
BLUE = {"product": "Blue Mug", "qty": 2, "name": "Ada Lovelace", "address": "1 Main St"}
RED = {"product": "Red Kettle", "qty": 1, "name": "Alan Turing", "address": "9 Elm Ave"}
EVENT_FIELDS = {"ts", "run_id", "program", "version", "mode", "type", "step", "tier", "detail", "diff",
                "llm_calls", "tokens", "usd", "trace_id"}  # dashboard/src/events.ts
FAST = 1500  # step timeout for failure cases, so they fail quickly


@pytest.fixture(autouse=True)
def no_telemetry(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    assert not sentry_sdk.get_client().is_active(), "Sentry must stay off in runtime tests"


def buy_item(*, timeout_ms: int | None = None, start_url: str | None = None, **step_updates) -> P.Program:
    # Explicit UTF-8: the YAML holds "×", and Windows defaults to cp1252 (see B's P.load).
    data = yaml.safe_load(BUY_ITEM.read_text(encoding="utf-8"))
    if start_url:
        data["start_url"] = start_url
    for step in data["steps"]:
        if timeout_ms:
            step["timeout_ms"] = timeout_ms
        step.update(step_updates.get(step["id"], {}))
    return P.Program.model_validate(data)


def run(tmp_path, program=None, params=BLUE, site=None, **kwargs) -> tuple[RunResult, FixtureSite]:
    site = site or FixtureSite()
    result = run_program(program or buy_item(), params, headless=True, runs_dir=tmp_path,
                         on_context=site.install, **kwargs)
    return result, site


def events(result: RunResult) -> list[dict]:
    lines = result.events_path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def assert_one_terminal(result: RunResult) -> list[dict]:
    evs = events(result)
    assert evs[0]["type"] == "run_started"
    assert [e["type"] for e in evs].count("run_finished") == 1
    assert evs[-1]["type"] == "run_finished" and evs[-1]["success"] is result.success
    return evs


def status(result: RunResult) -> dict[str, str]:
    return {s.step_id: s.status for s in result.steps}


# --- happy path -------------------------------------------------------------------------------

@pytest.mark.parametrize("params, line", [(BLUE, "2 × Blue Mug"), (RED, "1 × Red Kettle")])
def test_parameterized_replay_succeeds_with_zero_llm_calls(tmp_path, params, line):
    result, site = run(tmp_path, params=params)
    assert result.success, result.failure
    assert result.failure is None and result.llm_calls == 0 and result.tokens == 0 and result.usd == 0
    assert status(result) == {"s1": "skipped", "s2": "passed", "s3": "passed", "s4": "passed",
                              "s5": "passed", "s6": "passed", "s7": "passed"}
    assert not any(s.fallback_used for s in result.steps)
    assert site.count("done.html") == 1
    evs = assert_one_terminal(result)
    assert any(e["type"] == "check_passed" and e["stage"] == "success" and line in e["detail"] for e in evs)


def test_optional_step_runs_when_its_condition_holds(tmp_path):
    result, _ = run(tmp_path, buy_item(start_url="http://localhost:8765/?banner=1"))
    assert result.success, result.failure
    assert status(result)["s1"] == "passed"


def test_slow_content_is_waited_for_within_the_step_timeout(tmp_path):
    result, _ = run(tmp_path, site=FixtureSite({"product.html": "product_slow.html"}))
    assert result.success, result.failure
    assert result.step("s4").locator_index == 0


def test_fallback_is_not_taken_while_the_primary_may_still_appear(tmp_path):
    site = FixtureSite({"product.html": "product_late_primary.html"})
    result, _ = run(tmp_path, site=site)
    assert result.success, result.failure
    assert result.step("s4").locator_index == 0
    assert site.count("notify-clicked") == 0  # the early #add placeholder was never clicked


# --- locator fallbacks ------------------------------------------------------------------------

@pytest.mark.parametrize("page", ["product_renamed.html", "product_duplicate.html"])
def test_broken_primary_succeeds_through_a_unique_fallback(tmp_path, page):
    result, _ = run(tmp_path, site=FixtureSite({"product.html": page}))
    assert result.success, result.failure
    s4 = result.step("s4")
    assert (s4.locator_index, s4.locator, s4.fallback_used) == (1, "css=#add", True)
    s4_events = [e for e in events(result) if e["step"] == "s4"]
    assert all(e["tier"] is None for e in s4_events)  # fallback use is reported, not classified as a heal
    assert any("fallback" in e["detail"] and "css=#add" in e["detail"] for e in s4_events)


def test_unresolved_ambiguity_fails_without_acting(tmp_path):
    site = FixtureSite({"product.html": "product_ambiguous.html"})
    result, _ = run(tmp_path, buy_item(timeout_ms=FAST), site=site)
    assert not result.success
    f = result.failure
    assert (f.step_id, f.stage, f.locator_counts) == ("s4", "resolve", (2, 0, 2))
    assert "ambiguous" in f.actual
    assert site.count("checkout.html") == 0  # nothing was clicked
    assert "s5" not in status(result)
    evs = assert_one_terminal(result)
    failed = [e for e in evs if e["type"] == "check_failed"]
    assert [(e["step"], e["stage"]) for e in failed] == [("s4", "resolve")]


def test_all_locators_missing_fails(tmp_path):
    result, site = run(tmp_path, buy_item(timeout_ms=FAST), site=FixtureSite({"product.html": "product_missing.html"}))
    f = result.failure
    assert not result.success and (f.step_id, f.stage, f.locator_counts) == ("s4", "resolve", (0, 0, 0))
    assert site.count("checkout.html") == 0
    assert_one_terminal(result)


def test_fallback_that_selects_the_wrong_item_fails_its_post_check_once(tmp_path):
    site = FixtureSite({"shop.js": "shop_renamed_kettle.js"})
    result, _ = run(tmp_path, buy_item(timeout_ms=FAST), params=RED, site=site)
    assert not result.success
    f = result.failure
    assert (f.step_id, f.stage, f.check) == ("s2", "post", "text_visible Red Kettle")
    assert result.step("s2").locator.startswith("xpath=")  # the recorded Blue Mug link
    assert site.count("product.html") == 1  # clicked once, never retried
    assert site.count("checkout.html") == 0
    assert_one_terminal(result)


# --- visible text: near matches are not passes ------------------------------------------------

def test_near_match_product_name_is_not_a_pass(tmp_path):
    site = FixtureSite({"shop.js": "shop_near_match.js"})
    result, _ = run(tmp_path, buy_item(timeout_ms=FAST), site=site)
    f = result.failure
    assert not result.success and (f.step_id, f.stage, f.check) == ("s2", "post", "text_visible Blue Mug")
    assert "Blue Mug Deluxe" in f.actual
    assert site.count("checkout.html") == 0


def test_near_match_quantity_is_not_a_pass(tmp_path):
    site = FixtureSite({"product.html": "product_merge.html"})
    result, _ = run(tmp_path, buy_item(timeout_ms=FAST), site=site)
    f = result.failure
    assert not result.success and (f.step_id, f.stage, f.check) == ("s4", "post", "text_visible 2 × Blue Mug")
    assert "12 × Blue Mug" in f.actual
    assert site.count("checkout.html") == 1


@pytest.mark.parametrize("lines, expected, found", [
    (["2 × Blue Mug"], "2 × Blue Mug", True),
    (["Order confirmed: 2 × Blue Mug"], "Order confirmed: 2 × Blue Mug", True),
    (["Order confirmed: 2 × Blue Mug"], "2 × Blue Mug", True),
    (["Blue Mug — $12"], "Blue Mug", True),
    (["Thanks, Ada Lovelace. Your demo order is confirmed."], "Ada Lovelace", True),
    (["BLUE   MUG "], "Blue Mug", True),
    (["Red Kettle", "Blue Mug"], "Blue Mug", True),
    (["12 × Blue Mug"], "2 × Blue Mug", False),
    (["2 × Blue Mug Deluxe"], "2 × Blue Mug", False),
    (["Blue Mug Deluxe"], "Blue Mug", False),
    (["Mini Blue Mug"], "Blue Mug", False),
    (["Blue Mugs"], "Blue Mug", False),
    (["Red Kettle"], "Blue Mug", False),
    ([], "Blue Mug", False),
    (["anything"], "", False),
])
def test_text_found_requires_a_bounded_match(lines, expected, found):
    assert text_found(lines, expected) is found


# --- no repeated side effects, success check --------------------------------------------------

def test_failed_post_check_does_not_repeat_the_submit(tmp_path):
    site = FixtureSite({"checkout.html": "checkout_no_redirect.html"})
    result, _ = run(tmp_path, buy_item(timeout_ms=FAST), site=site)
    f = result.failure
    assert not result.success and (f.step_id, f.stage) == ("s7", "post")
    assert f.check.startswith("url_matches")
    assert site.count("order-submitted") == 1
    assert_one_terminal(result)


def test_success_check_is_mandatory(tmp_path):
    result, _ = run(tmp_path, site=FixtureSite({"done.html": "done_pending.html"}))
    assert all(s.status in ("passed", "skipped") for s in result.steps)
    f = result.failure
    assert not result.success and (f.step_id, f.stage) == (None, "success")
    assert "Order pending review" in f.actual
    evs = assert_one_terminal(result)
    assert any(e["type"] == "check_failed" and e["stage"] == "success" for e in evs)


@pytest.mark.parametrize("page", ["done_hidden_opacity.html", "done_hidden_opacity_parent.html",
                                  "done_hidden_opacity_inline.html", "done_hidden_visibility.html",
                                  "done_hidden_zero_size.html"])
def test_hidden_confirmation_text_is_not_a_pass(tmp_path, page):
    result, _ = run(tmp_path, site=FixtureSite({"done.html": page}))
    f = result.failure
    assert not result.success and (f.step_id, f.stage) == (None, "success")
    assert f.check == "text_visible Order confirmed: 2 × Blue Mug"
    assert "Order pending review" in f.actual


def test_visible_inline_confirmation_still_passes(tmp_path):
    result, _ = run(tmp_path, site=FixtureSite({"done.html": "done_visible_inline.html"}))
    assert result.success, result.failure


# --- failures outside checks still end the run once --------------------------------------------

def test_navigation_failure_is_reported(tmp_path):
    result, _ = run(tmp_path, site=FixtureSite(abort=("index.html",)))
    assert not result.success and result.failure.stage == "navigate"
    assert result.steps == ()
    assert_one_terminal(result)


def test_action_error_is_reported_without_post_checks(tmp_path):
    program = buy_item(timeout_ms=FAST, s4={"action": {"type": "fill", "value": "x"}, "post": []})
    result, site = run(tmp_path, program)
    f = result.failure
    assert not result.success and (f.step_id, f.stage) == ("s4", "action")
    assert site.count("checkout.html") == 0
    evs = assert_one_terminal(result)
    assert [(e["step"], e["stage"]) for e in evs if e["type"] == "check_failed"] == [("s4", "action")]


def test_unexpected_error_still_emits_one_terminal_event(tmp_path):
    async def broken(context):
        raise RuntimeError("setup exploded")

    with pytest.raises(RuntimeError, match="setup exploded"):
        run_program(buy_item(), BLUE, headless=True, runs_dir=tmp_path, on_context=broken)
    (run_dir,) = tmp_path.iterdir()
    evs = [json.loads(line) for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [e["type"] for e in evs] == ["run_started", "run_finished"]
    assert evs[-1]["success"] is False and "RuntimeError" in evs[-1]["detail"]


# --- diagnostics ------------------------------------------------------------------------------

def test_guard_failure_keeps_bounded_diagnostics(tmp_path):
    result, _ = run(tmp_path, buy_item(timeout_ms=FAST), site=FixtureSite({"product.html": "product_missing.html"}))
    f = result.failure
    assert f.url.endswith("product.html?id=blue-mug")
    assert f.screenshot and f.screenshot.is_file() and f.screenshot.parent == result.run_dir
    assert f.snapshot and f.snapshot.is_file()
    assert len(f.snapshot.read_text(encoding="utf-8")) <= diagnostics.SNAPSHOT_MAX_CHARS
    assert f.diagnostics_error is None


def test_diagnostics_errors_do_not_hide_the_original_failure(tmp_path, monkeypatch):
    async def broken_screenshot(page, path):
        raise OSError("disk full")

    monkeypatch.setattr(diagnostics, "_screenshot", broken_screenshot)
    result, _ = run(tmp_path, buy_item(timeout_ms=FAST), site=FixtureSite({"product.html": "product_missing.html"}))
    f = result.failure
    assert (f.step_id, f.stage) == ("s4", "resolve")
    assert f.screenshot is None and "disk full" in f.diagnostics_error
    assert f.snapshot and f.snapshot.is_file()


def test_a_crashing_capture_does_not_hide_the_original_failure(tmp_path, monkeypatch):
    async def crash(*args, **kwargs):
        raise RuntimeError("capture bug")

    monkeypatch.setattr(diagnostics, "capture", crash)
    result, _ = run(tmp_path, buy_item(timeout_ms=FAST), site=FixtureSite({"product.html": "product_missing.html"}))
    f = result.failure
    assert (f.step_id, f.stage) == ("s4", "resolve") and "capture bug" in f.diagnostics_error
    assert_one_terminal(result)


# --- Sentry spans (helpers stay D's; Sentry itself stays off) ---------------------------------

class RecordingSpan:
    def __init__(self):
        self.data = {"guard.result": "pass"}  # what D's step_span starts with

    def set_data(self, key, value):
        self.data[key] = value


def record_spans(monkeypatch) -> dict[str, RecordingSpan]:
    from contextlib import contextmanager

    from browseen.runtime import runner

    spans: dict[str, RecordingSpan] = {}

    @contextmanager
    def fake_step_span(index, action, mode, target="", step_id=None):
        spans[step_id] = RecordingSpan()
        yield spans[step_id]

    monkeypatch.setattr(runner, "step_span", fake_step_span)
    return spans


def test_a_skipped_optional_step_is_not_a_failed_guard(tmp_path, monkeypatch):
    spans = record_spans(monkeypatch)
    result, _ = run(tmp_path)
    assert result.success and status(result)["s1"] == "skipped"
    assert spans["s1"].data["guard.result"] == "pass" and spans["s1"].data["step.skipped"] is True
    assert all(span.data["guard.result"] == "pass" for span in spans.values())


def test_a_failed_guard_still_marks_its_span(tmp_path, monkeypatch):
    spans = record_spans(monkeypatch)
    result, _ = run(tmp_path, buy_item(timeout_ms=FAST), site=FixtureSite({"product.html": "product_missing.html"}))
    assert not result.success
    assert spans["s4"].data["guard.result"] == "fail"
    assert spans["s1"].data["guard.result"] == "pass"


# --- events -----------------------------------------------------------------------------------

def test_events_follow_the_dashboard_format(tmp_path):
    result, _ = run(tmp_path)
    evs = assert_one_terminal(result)
    for e in evs:
        assert EVENT_FIELDS <= e.keys()
        assert (e["run_id"], e["program"], e["version"], e["mode"]) == (result.run_id, "buy-item", 1, "compiled")
        assert (e["llm_calls"], e["tokens"], e["usd"], e["tier"], e["diff"], e["trace_id"]) == (0, 0, 0, None, None, "")
        if e["type"].startswith("check_"):
            assert e["stage"] in ("when", "resolve", "pre", "action", "post", "success", "navigate")
    stamps = [e["ts"] for e in evs]
    assert stamps == sorted(stamps) and len(set(stamps)) == len(stamps)
    keys = [f'{e["run_id"]}|{e["ts"]}|{e["type"]}|{e["step"] or ""}' for e in evs]  # D's eventKey
    assert len(set(keys)) == len(keys)
    final = evs[-1]
    assert final["success"] is True and final["seconds"] > 0 and final["llm_calls"] == 0
    assert result.events_path == result.run_dir / "events.jsonl"


def test_no_trace_is_linked_when_sentry_has_no_dsn(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from browseen.runtime import runner

    def client(dsn):
        return lambda: SimpleNamespace(is_active=lambda: True, dsn=dsn)

    with monkeypatch.context() as m:  # what init_sentry() leaves without SENTRY_DSN: active, sends nothing
        m.setattr(runner.sentry_sdk, "get_client", client(""))
        assert runner._sentry_sending() is False
        m.setattr(runner.sentry_sdk, "get_client", client("https://key@o0.ingest.example/1"))
        assert runner._sentry_sending() is True
    result, _ = run(tmp_path)  # Sentry off: no trace to link
    assert result.trace_id == "" and {e["trace_id"] for e in events(result)} == {""}


def test_failure_reports_keep_word_spacing(tmp_path):
    result, _ = run(tmp_path, buy_item(timeout_ms=FAST), params={**BLUE, "product": "Purple Vase"})
    f = result.failure
    assert (f.step_id, f.stage, f.check) == ("s2", "post", "text_visible Purple Vase")
    assert "Quantity Add to cart" in f.actual and "QuantityAdd" not in f.actual


def test_run_ids_do_not_collide(tmp_path):
    assert len({new_run_id() for _ in range(2000)}) == 2000
    first, _ = run(tmp_path)
    second, _ = run(tmp_path)
    assert first.run_id != second.run_id and first.run_dir != second.run_dir


# --- inputs are validated before anything starts ----------------------------------------------

@pytest.mark.parametrize("params, message", [
    ({**BLUE, "qty": "two"}, "qty"),
    ({**BLUE, "qty": True}, "qty"),
    ({k: v for k, v in BLUE.items() if k != "address"}, "missing params"),
    ({**BLUE, "colour": "blue"}, "unknown params"),
])
def test_bad_params_are_rejected_before_the_run_starts(tmp_path, params, message):
    with pytest.raises(ValueError, match=message):
        run_program(buy_item(), params, headless=True, runs_dir=tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_unsupported_actions_are_rejected_before_the_run_starts(tmp_path):
    program = buy_item(s7={"action": {"type": "extract", "into": "receipt"}, "post": []})
    with pytest.raises(ValueError, match="extract"):
        run_program(program, BLUE, headless=True, runs_dir=tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_programs_without_success_checks_are_rejected_before_the_run_starts(tmp_path):
    data = buy_item().model_dump(mode="json")
    program = P.Program.model_validate({**data, "success": []})  # valid under B's schema
    with pytest.raises(ValueError, match="no success checks"):
        run_program(program, BLUE, headless=True, runs_dir=tmp_path, on_context=FixtureSite().install)
    assert list(tmp_path.iterdir()) == []


# --- zero LLM: the runtime needs no model client ----------------------------------------------

def test_runtime_runs_without_importing_model_clients(tmp_path):
    script = f"""
import json, sys
sys.path.insert(0, {str(FIXTURE)!r})
from role_a_site import FixtureSite
import yaml
from browseen import program as P
from browseen.runtime import run_program
data = yaml.safe_load(open({str(BUY_ITEM)!r}, encoding="utf-8"))
site = FixtureSite()
result = run_program(P.Program.model_validate(data), {BLUE!r}, headless=True,
                     runs_dir={str(tmp_path)!r}, on_context=site.install)
clients = ["anthropic", "browser_use", "openai", "google.genai", "groq", "ollama", "browseen.agent"]
print(json.dumps({{"success": result.success, "llm_calls": result.llm_calls,
                  "loaded": [m for m in clients if m in sys.modules]}}))
"""
    env = {k: v for k, v in os.environ.items() if k != "SENTRY_DSN"}
    env["PYTHONPATH"] = str(ROOT)
    out = subprocess.run([sys.executable, "-c", script], cwd=ROOT, env=env, capture_output=True, text=True,
                         encoding="utf-8", timeout=120)
    assert out.returncode == 0, out.stderr
    report = json.loads(out.stdout.strip().splitlines()[-1])
    assert report == {"success": True, "llm_calls": 0, "loaded": []}
