"""Compiler tests on a real recorded run (tests/fixtures/run_mini_shop). Needs Playwright's Chromium."""

import shutil
from pathlib import Path

import pytest

from browseen import program as P
from browseen.compiler.compile import CompileReport, compile_run, compile_trace, normalize
from browseen.recorder.trace import load_trace

RUN = Path(__file__).parent / "fixtures" / "run_mini_shop"


@pytest.fixture(scope="module")
def compiled():
    return compile_trace(load_trace(RUN), RUN, "mini-shop")


def test_program_validates_and_has_the_six_steps(compiled):
    program, _ = compiled
    P.Program.model_validate(program.model_dump())  # round-trips through validation
    assert [(s.id, s.action.type) for s in program.steps] == [
        ("s1", "click"), ("s2", "fill"), ("s3", "click"), ("s4", "fill"), ("s5", "fill"), ("s6", "click")]


def test_params_come_from_the_recorded_inputs(compiled):
    program, _ = compiled
    assert program.task == "Buy $qty of $product and check out as $name, $address"
    assert {k: p.type for k, p in program.params.items()} == {
        "product": "string", "qty": "integer", "name": "string", "address": "string"}
    assert [program.step(s).action.value for s in ("s2", "s4", "s5")] == ["$qty", "$name", "$address"]


def test_locators_are_templated_and_ordered(compiled):
    program, _ = compiled
    link = program.step("s1").target.locators
    assert link[0] == P.Locator(role="link", name="$product", exact=True)
    assert link[-1].xpath == "/html/body/main/ul/li[1]/a"
    assert program.step("s2").target.locators[0] == P.Locator(label="Quantity", exact=True)
    assert program.step("s1").target.fingerprint.name == "Blue Mug"  # the fingerprint keeps the literal


def test_checks_guard_page_and_effect(compiled):
    program, _ = compiled
    s1 = program.step("s1")
    assert [c.kind for c in s1.pre] == ["url_matches", "target_unique", "target_enabled"]
    assert P.Check(text_visible="$product") in s1.post  # catches a wrong-item click
    assert P.Check(text_visible="$qty × $product") in program.step("s3").post
    assert program.step("s2").post == [P.Check(target_value="$qty")]
    assert program.success == [P.Check(text_visible="Order confirmed: $qty × $product")]


def test_report_explains_every_dropped_action(compiled):
    _, report = compiled
    dropped = {(line.trace_step, line.action) for line in report.lines if line.outcome == "dropped"}
    assert dropped == {(0, "navigate"), (6, "done")}
    assert not [line for line in report.lines if line.outcome == "unsupported"]


def test_resolved_program_for_other_inputs(compiled):
    program, _ = compiled
    r = program.resolved({"product": "Red Kettle", "qty": 1, "name": "Alan Turing", "address": "9 Elm Ave"})
    assert r.step("s1").target.locators[0].name == "Red Kettle"
    assert r.success[0].text_visible == "Order confirmed: 1 × Red Kettle"


def test_compile_run_saves_and_refuses_an_existing_program(tmp_path):
    _, _, path = compile_run(RUN, "mini-shop", tmp_path)
    assert path == tmp_path / "mini-shop" / "v1.yaml" and P.load(path).program == "mini-shop"
    with pytest.raises(FileExistsError):
        compile_run(RUN, "mini-shop", tmp_path)


def test_normalize_drops_failures_merges_inputs_and_skips_no_op_clicks(tmp_path):
    run = tmp_path / "run"
    shutil.copytree(RUN, run)
    trace = load_trace(run)
    steps = trace.steps
    # make step 2's input a retype of the same field, step 1 fail, and step 5 a click that changed nothing
    steps[2].actions.append(steps[2].actions[0].model_copy(update={"params": {"text": "3", "clear": True}}))
    steps[1].actions[0].error = "Element not found"
    (run / steps[5].html_after).write_text((run / steps[5].html_before).read_text())
    steps[5].url_after = steps[5].url

    report = CompileReport(trace.run_id)
    kept = normalize(trace, run, report)
    reasons = {(line.trace_step, line.detail.split(":")[0]) for line in report.lines if line.outcome == "dropped"}
    assert (1, "failed") in reasons
    assert (2, "superseded by a later input into the same field") in reasons
    assert (5, "the click changed nothing (a mis-click)") in reasons
    assert [k.action.params.get("text") for k in kept if k.type == "fill"][0] == "3"
