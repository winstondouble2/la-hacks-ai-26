from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from browseen import program as P

EXAMPLE = Path(__file__).resolve().parents[1] / "programs" / "buy-item" / "v1.yaml"
PARAMS = {"product": "Red Kettle", "qty": 1, "name": "Alan Turing", "address": "9 Elm Ave"}


def example_data() -> dict:
    return yaml.safe_load(EXAMPLE.read_text())


def test_example_loads():
    prog = P.load(EXAMPLE)
    assert (prog.program, prog.version) == ("buy-item", 1)
    assert [s.id for s in prog.steps] == ["s1", "s2", "s3", "s4", "s5", "s6", "s7"]
    assert prog.step("s1").when is not None


def test_save_load_round_trip(tmp_path):
    prog = P.load(EXAMPLE)
    path = P.save(prog, root=tmp_path)
    assert path == tmp_path / "buy-item" / "v1.yaml"
    assert P.load(path) == prog


def test_save_refuses_to_overwrite(tmp_path):
    prog = P.load(EXAMPLE)
    P.save(prog, root=tmp_path)
    with pytest.raises(FileExistsError):
        P.save(prog, root=tmp_path)


def test_bump_then_latest(tmp_path):
    prog = P.load(EXAMPLE)
    P.save(prog, root=tmp_path)
    v2 = prog.bump(source="healed", step="s4", tier=2, reason="'Add to cart' renamed to 'Add to bag'")
    v2.step("s4").target.locators.insert(0, P.Locator(role="button", name="Add to bag"))
    P.save(v2, root=tmp_path)

    assert P.versions("buy-item", root=tmp_path) == [1, 2]
    newest = P.latest("buy-item", root=tmp_path)
    assert newest.version == 2
    assert newest.history[-1].step == "s4" and newest.history[-1].tier == 2
    assert newest.step("s4").target.locators[0].name == "Add to bag"
    assert prog.version == 1 and prog.step("s4").target.locators[0].name == "Add to cart"


def test_resolved_substitutes_everywhere():
    r = P.load(EXAMPLE).resolved(PARAMS)
    assert r.step("s2").target.locators[0].name == "Red Kettle"
    assert r.step("s2").post[1].text_visible == "Red Kettle"
    assert r.step("s3").action.value == "1"
    assert r.success[0].text_visible == "Order confirmed: 1 × Red Kettle"
    assert "$product" not in r.to_yaml() and "$qty" not in r.to_yaml()


def test_resolved_rejects_missing_or_unknown_params():
    prog = P.load(EXAMPLE)
    with pytest.raises(KeyError, match="missing"):
        prog.resolved({"product": "Blue Mug"})
    with pytest.raises(KeyError, match="unknown"):
        prog.resolved({**PARAMS, "colour": "blue"})


def test_dollar_dollar_is_a_literal_dollar():
    data = example_data()
    data["steps"][1]["post"][1] = {"text_visible": "$$12"}
    r = P.Program.model_validate(data).resolved(PARAMS)
    assert r.step("s2").post[1].text_visible == "$12"


def test_locator_needs_exactly_one_kind():
    with pytest.raises(ValidationError):
        P.Locator()
    with pytest.raises(ValidationError):
        P.Locator(css="#add", xpath="/html/body/main/button")
    with pytest.raises(ValidationError):
        P.Locator(css="#add", name="Add to cart")


def test_check_needs_exactly_one_kind():
    with pytest.raises(ValidationError):
        P.Check(url_matches="/done", text_visible="Order confirmed")


def test_undeclared_param_is_rejected():
    data = example_data()
    data["steps"][2]["action"]["value"] = "$quantity"
    with pytest.raises(ValidationError, match="quantity"):
        P.Program.model_validate(data)


def test_unknown_key_is_rejected():
    data = example_data()
    data["steps"][0]["actoin"] = {"type": "click"}
    with pytest.raises(ValidationError):
        P.Program.model_validate(data)


def test_target_checks_need_a_target():
    with pytest.raises(ValidationError):
        P.Step(id="s9", intent="Open the shop", action=P.Action(type="navigate", url="http://localhost:8765/"),
               pre=[P.Check(target_unique=True)])
    with pytest.raises(ValidationError):
        P.Step(id="s9", intent="Click something", action=P.Action(type="click"))


def test_action_needs_its_field():
    with pytest.raises(ValidationError):
        P.Action(type="fill")
    with pytest.raises(ValidationError):
        P.Action(type="navigate")
