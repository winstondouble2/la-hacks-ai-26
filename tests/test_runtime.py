"""The runtime and its heals on the local mini shop (Playwright; no API key: the LLM and the agent are fakes)."""

import functools
import http.server
import json
import threading
from pathlib import Path

import pytest

from browseen import program as P
from browseen.llm import StructuredResult
from browseen.recorder.trace import Usage
from browseen.runtime.heal import LocatorSpec, Patch, PatchStep, agent_steps
from browseen.runtime.runner import run_program

ROOT = Path(__file__).resolve().parents[1]
SHOP = ROOT / "browseen" / "recorder" / "fixtures" / "mini_shop"
PARAMS = {"product": "Red Kettle", "qty": 1, "name": "Alan Turing", "address": "9 Elm Ave"}


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def shop_url():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(SHOP)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/"
    server.shutdown()


def program_at(path: str, url: str, timeout_ms: int | None = None) -> P.Program:
    program = P.load(ROOT / path).model_copy(update={"start_url": url})
    if timeout_ms:
        for step in program.steps:
            step.timeout_ms = timeout_ms
    return program


def run(program, tmp_path, **options):
    return run_program(program, PARAMS, headless=True, runs_dir=tmp_path / "runs", programs_dir=tmp_path / "programs",
                       verbose=False, **options)


def events(result):
    return [json.loads(line) for line in (result.run_dir / "events.jsonl").read_text().splitlines()]


def test_replay_with_new_inputs_makes_no_llm_calls(shop_url, tmp_path):
    result = run(program_at("programs/buy-item/v1.yaml", shop_url), tmp_path)
    assert result.success and result.usage.llm_calls == 0 and result.version_end == 1
    assert [s.status for s in result.steps] == ["skipped"] + ["passed"] * 6  # s1: no cookie banner
    log = events(result)
    assert log[0]["type"] == "run_started" and log[-1]["type"] == "run_finished" and log[-1]["success"] is True
    assert any(e["type"] == "check_passed" and e.get("stage") == "success" for e in log)


def test_tier1_promotes_a_fallback_locator_and_the_next_run_is_clean(shop_url, tmp_path):
    program = program_at("programs/buy-item/v1.yaml", shop_url)
    program.step("s4").target.locators.insert(0, P.Locator(testid="gone"))
    first = run(program, tmp_path)
    assert first.success and [(s.step_id, s.tier) for s in first.steps if s.status == "healed"] == [("s4", 1)]
    v2 = P.latest("buy-item", tmp_path / "programs")
    assert v2.version == 2 and v2.step("s4").target.locators[0] == P.Locator(role="button", name="Add to cart")
    second = run(v2, tmp_path)
    assert second.success and not [s for s in second.steps if s.status == "healed"]


def test_tier1_fingerprint_match_when_every_locator_is_stale(shop_url, tmp_path):
    program = program_at("programs/buy-item/v1.yaml", shop_url, timeout_ms=1500)
    target = program.step("s4").target
    target.locators = [P.Locator(role="button", name="Add to basket", exact=True), P.Locator(css="#basket")]
    target.fingerprint = P.Fingerprint(tag="button", role="button", name="Add to the cart", attributes={"type": "button"})
    result = run(program, tmp_path, tiers=(1,))
    assert result.success and [(s.step_id, s.tier) for s in result.steps if s.status == "healed"] == [("s4", 1)]
    assert P.latest("buy-item", tmp_path / "programs").step("s4").target.locators[0].name == "Add to cart"


def test_tier2_inserts_an_optional_step_that_later_runs_reuse(shop_url, tmp_path):
    calls = []

    def fake_llm(system, prompt):
        calls.append(prompt)
        patch = Patch(kind="insert_before", locator=None, reason="a cookie wall covers the page", steps=[
            PatchStep(intent="Accept the cookie banner", action="click",
                      locator=LocatorSpec(role="button", name="Accept all"), value=None, key=None)])
        return StructuredResult(patch, Usage(llm_calls=1, input_tokens=900, output_tokens=60, usd=0.005), "fake")

    program = program_at("programs/mini-shop/v1.yaml", shop_url, timeout_ms=1500)
    healed = run(program, tmp_path, url_params={"banner": "1"}, tiers=(2,), llm_call=fake_llm)
    assert healed.success and healed.usage.llm_calls == 1 and len(calls) == 1
    assert "Cookie consent" in calls[0]  # the page snapshot went to the model
    v2 = P.latest("mini-shop", tmp_path / "programs")
    inserted = v2.steps[0]
    assert inserted.id == "s1a" and inserted.when == P.Check(exists=P.Locator(role="button", name="Accept all", exact=True))

    with_banner = run(v2, tmp_path, url_params={"banner": "1"}, tiers=(2,), llm_call=fake_llm)
    assert with_banner.success and with_banner.usage.llm_calls == 0 and len(calls) == 1
    without_banner = run(v2, tmp_path, tiers=(2,), llm_call=fake_llm)
    assert without_banner.success and without_banner.steps[0].status == "skipped"


def test_no_healing_fails_loudly(shop_url, tmp_path):
    program = program_at("programs/buy-item/v1.yaml", shop_url, timeout_ms=1000)
    program.step("s4").target.locators = [P.Locator(css="#gone")]
    result = run(program, tmp_path, healing=False)
    assert not result.success and result.error.startswith("s4: locate target")
    assert events(result)[-1]["success"] is False


def test_heal_takes_the_next_free_version_number(shop_url, tmp_path):
    taken = program_at("programs/buy-item/v1.yaml", shop_url).model_copy(update={"version": 5})
    P.save(taken, tmp_path / "programs")
    program = program_at("programs/buy-item/v1.yaml", shop_url)
    program.step("s4").target.locators.insert(0, P.Locator(testid="gone"))
    result = run(program, tmp_path)
    assert result.success and result.version_end == 6


def test_agent_actions_become_optional_steps():
    history = json.loads((ROOT / "tests" / "fixtures" / "smoke_history.json").read_text())
    run_stub = type("RunStub", (), {"run_id": "r_test", "params": {"product": "Blue Mug", "qty": 2,
                                                                   "name": "Ada Lovelace", "address": "1 Main St"}})()
    steps = agent_steps(history, run_stub, ["s2a", "s2b", "s2c"])
    assert [s.id for s in steps] == ["s2a", "s2b", "s2c"]
    assert steps[0].target.locators[0] == P.Locator(role="link", name="$product", exact=True)
    assert steps[0].when == P.Check(exists=steps[0].target.locators[0])
    assert steps[1].action == P.Action(type="fill", value="$qty")
