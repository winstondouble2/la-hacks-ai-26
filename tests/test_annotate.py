"""The v1 LLM pass, with a fake model: no API calls. Needs Playwright's Chromium."""

import json
from pathlib import Path

import pytest

from browseen.compiler.annotate import (SYSTEM_PROMPT, Annotation, LLMResult, ParamNote, StepNote, annotate,
                                        apply_annotation)
from browseen.compiler.compile import compile_trace
from browseen.compiler.locators import PageAnalyzer
from browseen.program import Check, Locator
from browseen.recorder.trace import Usage, load_trace

RUN = Path(__file__).parent / "fixtures" / "run_mini_shop"
INTENTS = {
    "s1": "Open the product page for $product", "s2": "Set the quantity to $qty", "s3": "Add the product to the cart",
    "s4": "Enter the customer's name, $name", "s5": "Enter the shipping address, $address", "s6": "Place the order",
}


def note_all(optional=(), intents=None, success="Order confirmed: $qty × $product", ids=None):
    intents = intents or INTENTS
    return Annotation(
        steps=[StepNote(id=i, intent=intents.get(i, INTENTS.get(i, "x")), optional=i in optional) for i in (ids or INTENTS)],
        params=[ParamNote(name="product", description="Product to buy"), ParamNote(name="nope", description="ignored")],
        success_text=success,
    )


def compile_with(annotation=None, note="", seen=None):
    def fake_call(system, prompt):
        if seen is not None:
            seen.update(system=system, prompt=prompt)
        return LLMResult(annotation, Usage(llm_calls=1, input_tokens=1000, output_tokens=200, usd=0.008), "claude-opus-5-5", note)

    annotator = lambda *args: annotate(*args, call=fake_call)  # noqa: E731
    return compile_trace(load_trace(RUN), RUN, "mini-shop", annotate_with=annotator)


def test_intents_descriptions_and_success_are_applied():
    program, report = compile_with(note_all())
    assert [s.intent for s in program.steps] == list(INTENTS.values())
    assert program.params["product"].description == "Product to buy"
    assert program.success == [Check(text_visible="Order confirmed: $qty × $product")]
    assert "compiler v1" in program.history[0].reason
    assert report.llm.usage.usd == 0.008 and "LLM pass (used)" in report.render()


def test_optional_click_gets_a_when_check_built_from_its_first_locator():
    program, _ = compile_with(note_all(optional={"s3"}))
    s3 = program.step("s3")
    assert s3.when == Check(exists=Locator(role="button", name="Add to cart", exact=True))
    assert all(program.step(i).when is None for i in INTENTS if i != "s3")


def test_optional_fill_is_ignored():
    program, report = compile_with(note_all(optional={"s2"}))
    assert program.step("s2").when is None
    assert any("s2" in w and "optional" in w for w in report.warnings)


def test_mismatched_step_ids_keep_the_v0_program():
    program, report = compile_with(note_all(ids=["s1", "s2", "s3"]))
    assert program.step("s1").intent == "Open the '$product' link"  # v0 template
    assert any("step ids don't match" in w for w in report.warnings)


def test_intent_with_an_unknown_param_keeps_the_v0_intent():
    program, report = compile_with(note_all(intents={**INTENTS, "s2": "Set the quantity to $quantity"}))
    assert program.step("s2").intent == "Enter $qty into 'Quantity'"
    assert program.step("s1").intent == INTENTS["s1"]
    assert any(w.startswith("s2: kept the compiler's intent") for w in report.warnings)


def test_success_text_not_on_the_page_is_rejected():
    program, report = compile_with(note_all(success="Thanks for shopping with $product"))
    assert program.success == [Check(text_visible="Order confirmed: $qty × $product")]  # v0's own pick
    assert any("success text" in w for w in report.warnings)


def test_failed_call_keeps_v0_and_says_why():
    program, report = compile_with(None, note="refused (cyber)")
    assert program.step("s1").intent == "Open the '$product' link"
    assert "compiler v0" in program.history[0].reason
    assert any("refused (cyber)" in w for w in report.warnings)


def test_prompt_carries_goals_params_and_final_page():
    seen = {}
    compile_with(note_all(), seen=seen)
    assert seen["system"] == SYSTEM_PROMPT
    data = json.loads(seen["prompt"].split("\n\n", 1)[1])
    assert data["parameters"]["product"] == "Blue Mug"
    assert [s["id"] for s in data["steps"]] == list(INTENTS)
    assert data["steps"][0]["agent_goal"] == "Open $product product page."
    assert any("Order confirmed" in line for line in data["final_page_lines"])


def test_apply_annotation_does_not_touch_the_input_program():
    program, _ = compile_trace(load_trace(RUN), RUN, "mini-shop")
    before = program.model_dump()
    apply_annotation(program, note_all(optional={"s1"}), ["Order confirmed: 2 × Blue Mug"],
                     load_trace(RUN).inputs, [])
    assert program.model_dump() == before


@pytest.mark.parametrize("html, expected", [
    ('<div role="dialog" aria-label="Cookie consent"><button>Accept all</button></div>', 'dialog "Cookie consent"'),
    ('<div id="newsletter-popup"><button>No thanks</button></div>', "div#newsletter-popup"),
    ('<main><form><button>Accept all</button></form></main>', None),
])
def test_container_hint(html, expected):
    with PageAnalyzer() as pa:
        pa.load(f"<html><body>{html}</body></html>")
        assert pa.container("//button") == expected
