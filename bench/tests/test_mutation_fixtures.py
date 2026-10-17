import re
from html.parser import HTMLParser

from fastapi.testclient import TestClient

from bench.fixtures.mutation_app import PRODUCT, create_app


class InteractiveElements(HTMLParser):
    def __init__(self):
        super().__init__()
        self.button_text = []
        self.buttons = []
        self.dialogs = 0
        self._button_depth = 0
        self._button_value = []
        self._button_attrs = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "button":
            self._button_depth += 1
            self._button_value = []
            self._button_attrs = attrs
        if attrs.get("role") == "dialog":
            self.dialogs += 1

    def handle_data(self, data):
        if self._button_depth:
            self._button_value.append(data)

    def handle_endtag(self, tag):
        if tag == "button" and self._button_depth:
            text = "".join(self._button_value).strip()
            self.button_text.append(text)
            self.buttons.append({**self._button_attrs, "text": text})
            self._button_depth -= 1


def controls(html: str) -> InteractiveElements:
    parsed = InteractiveElements()
    parsed.feed(html)
    return parsed


def form(mutation: str, run_id: str, seed: int = 7, **extra):
    return {"mut": mutation, "seed": str(seed), "run_id": run_id, **extra}


def test_m00_baseline_action_is_independently_verified():
    with TestClient(create_app()) as client:
        page = client.get("/fixture", params={"mut": "M00", "seed": 7, "run_id": "m00"})
        assert page.status_code == 200
        assert "Add to cart" in controls(page.text).button_text
        assert controls(page.text).dialogs == 0
        added = client.post("/__add", data=form("M00", "m00"))
        assert added.status_code == 200
        assert "Added to cart" in controls(added.text).button_text
        assert 'data-testid="cart-summary"' in added.text
        verdict = client.get("/__verify", params={"run_id": "m00"}).json()
    assert verdict == {
        "run_id": "m00", "success": True,
        "checks": {"product": True, "quantity": True, "total": True, "not_saved_for_later": True, "order_confirmed": True},
    }


def test_m04_renames_the_accessible_locator_but_keeps_the_action():
    with TestClient(create_app()) as client:
        first = client.get("/fixture", params={"mut": "M04", "seed": 7, "run_id": "m04"})
        second = client.get("/fixture", params={"mut": "M04", "seed": 7, "run_id": "m04"})
        assert first.text == second.text
        buttons = controls(first.text).button_text
        assert "Add to cart" not in buttons
        assert "Add to bag" in buttons
        added = client.post("/__add", data=form("M04", "m04"))
        assert added.status_code == 200
        assert "Added to bag" in controls(added.text).button_text
        assert 'Cart: 1 item · $79.99' in added.text
        assert client.get("/__verify", params={"run_id": "m04"}).json()["success"] is True


def test_m01_rotates_selector_attributes_by_seed_without_changing_the_accessible_name():
    with TestClient(create_app()) as client:
        baseline = client.get("/fixture", params={"mut": "M00", "seed": 7, "run_id": "m00-selector"})
        churned = client.get("/fixture", params={"mut": "M01", "seed": 7, "run_id": "m01-seed-7"})
        same_seed = client.get("/fixture", params={"mut": "M01", "seed": 7, "run_id": "m01-seed-7"})
        other_seed = client.get("/fixture", params={"mut": "M01", "seed": 8, "run_id": "m01-seed-8"})
        baseline_button = next(button for button in controls(baseline.text).buttons if button["text"] == "Add to cart")
        churned_button = next(button for button in controls(churned.text).buttons if button["text"] == "Add to cart")
        other_button = next(button for button in controls(other_seed.text).buttons if button["text"] == "Add to cart")
        assert baseline_button["id"] == "add-to-cart"
        assert baseline_button["class"] == "add-button"
        assert baseline_button["data-testid"] == "add-to-cart"
        assert churned.text == same_seed.text
        assert churned_button["id"].startswith("action-")
        assert churned_button["class"].startswith("action-")
        assert "data-testid" not in churned_button
        assert "data-action" not in churned_button
        assert churned_button["id"] != other_button["id"]
        client.post("/__add", data=form("M01", "m01-seed-7"))
        assert client.get("/__verify", params={"run_id": "m01-seed-7"}).json()["success"] is True


def test_m02_inserts_wrappers_without_changing_the_product_action():
    with TestClient(create_app()) as client:
        baseline = client.get("/fixture", params={"mut": "M00", "seed": 7, "run_id": "m00-wrapper"})
        wrapped = client.get("/fixture", params={"mut": "M02", "seed": 7, "run_id": "m02-wrapper"})
        assert 'class="action-shell"' not in baseline.text
        assert 'class="action-shell"' in wrapped.text
        assert 'class="action-inner"' in wrapped.text
        assert "Add to cart" in controls(wrapped.text).button_text
        client.post("/__add", data=form("M02", "m02-wrapper"))
        assert client.get("/__verify", params={"run_id": "m02-wrapper"}).json()["success"] is True


def test_m03_reorders_siblings_and_wrong_target_is_rejected():
    with TestClient(create_app()) as client:
        baseline = controls(client.get("/fixture", params={"mut": "M00", "seed": 7, "run_id": "m00-order"}).text)
        reordered = controls(client.get("/fixture", params={"mut": "M03", "seed": 7, "run_id": "m03-order"}).text)
        assert baseline.button_text[-2:] == ["Add to cart", "Save for later"]
        assert reordered.button_text[-2:] == ["Save for later", "Add to cart"]
        saved = client.post("/__save", data=form("M03", "m03-order"))
        assert 'data-testid="save-summary"' in saved.text
        wrong_target = client.get("/__verify", params={"run_id": "m03-order"}).json()
        assert wrong_target["success"] is False
        assert wrong_target["checks"]["not_saved_for_later"] is False
        client.post("/__reset", data=form("M03", "m03-order"))
        client.post("/__add", data=form("M03", "m03-order"))
        assert client.get("/__verify", params={"run_id": "m03-order"}).json()["success"] is True


def test_m11_requires_a_new_confirmation_step_after_add_to_cart():
    with TestClient(create_app()) as client:
        client.get("/fixture", params={"mut": "M11", "seed": 7, "run_id": "m11-flow"})
        added = client.post("/__add", data=form("M11", "m11-flow"))
        assert 'data-testid="cart-summary"' in added.text
        assert 'data-testid="order-confirmation-step"' in added.text
        incomplete = client.get("/__verify", params={"run_id": "m11-flow"}).json()
        assert incomplete["success"] is False
        assert incomplete["checks"]["order_confirmed"] is False
        confirmed = client.post("/__confirm", data=form("M11", "m11-flow"))
        assert 'data-testid="order-confirmed"' in confirmed.text
        assert client.get("/__verify", params={"run_id": "m11-flow"}).json()["success"] is True


def test_guided_demo_advances_through_a_fixed_scenario_order_on_each_reload():
    with TestClient(create_app()) as client:
        first = client.get("/demo")
        second = client.get("/demo")
        third = client.get("/demo")
    assert 'data-mutation="M00"' in first.text
    assert 'View 1 of 10' in first.text
    assert 'data-mutation="M00"' in second.text
    assert 'View 2 of 10' in second.text
    assert 'Baseline repeat' in second.text
    assert 'data-mutation="M01"' in third.text
    assert 'View 3 of 10' in third.text
    assert 'Reload to change the site' in first.text
    assert 'data-testid="demo-telemetry"' in first.text
    assert 'Waiting for the runtime to report usage.' in first.text


def test_demo_renders_the_active_case_directly_and_keeps_actions_in_the_same_page():
    with TestClient(create_app()) as client:
        first = client.get("/demo")
        run_id = re.search(r'data-run-id="([^"]+)"', first.text).group(1)
        continued = client.post("/__add", data={
            "mut": "M00", "seed": "7", "run_id": run_id,
            "return_to": f"/demo?current=0&run_id={run_id}",
        })

    assert "<iframe" not in first.text
    assert 'data-testid="demo-current"' in first.text
    assert continued.url.path == "/demo"
    assert 'data-testid="cart-summary"' in continued.text
    assert 'data-testid="demo-telemetry"' in continued.text


def test_guided_demo_can_start_at_any_real_mutation_case():
    with TestClient(create_app()) as client:
        selected = client.get("/demo/case/M09")
    assert 'data-mutation="M09"' in selected.text
    assert 'View 7 of 10' in selected.text


def test_mounted_demo_uses_a_different_cookie_from_the_standalone_fixture():
    standalone = create_app()
    mounted = create_app(path_prefix="/lab")
    with TestClient(standalone) as standalone_client, TestClient(mounted) as mounted_client:
        standalone_client.get("/demo")
        mounted_first = mounted_client.get("/demo")
        mounted_second = mounted_client.get("/demo")

    assert 'View 1 of 10' in mounted_first.text
    assert 'View 2 of 10' in mounted_second.text


def test_telemetry_tracks_provider_usage_and_explicit_cache_hits_without_faking_empty_runs():
    with TestClient(create_app()) as client:
        empty = client.get("/__telemetry", params={"run_id": "telemetry-empty"}).json()
        assert empty["status"] == "awaiting_runtime_events"
        assert empty["totals"]["total_tokens"] == 0

        reported = client.post("/__telemetry/usage", data={
            "run_id": "telemetry-run", "stage": "record", "model": "example-model",
            "input_tokens": "120", "output_tokens": "35",
        })
        assert reported.status_code == 200
        cache_hit = client.post("/__telemetry/cache-hit", data={
            "run_id": "telemetry-run", "stage": "replay",
        })
        assert cache_hit.status_code == 200
        summary = client.get("/__telemetry", params={"run_id": "telemetry-run"}).json()

    assert summary["status"] == "reported"
    assert summary["totals"] == {
        "new_model_calls": 1, "cache_hits": 1,
        "input_tokens": 120, "output_tokens": 35, "total_tokens": 155,
    }
    assert summary["events"][0]["token_source"] == "provider_reported"
    assert summary["events"][1] == {
        "event_type": "cache_hit", "stage": "replay", "model": None,
        "input_tokens": 0, "output_tokens": 0, "token_source": "not_applicable",
        "total_tokens": 0,
    }


def test_m09_blocks_the_action_until_the_inserted_step_is_completed():
    with TestClient(create_app()) as client:
        before = client.get("/fixture", params={"mut": "M09", "seed": 7, "run_id": "m09"})
        assert controls(before.text).dialogs == 0
        searched = client.post(
            "/__search", data=form("M09", "m09", query=PRODUCT), follow_redirects=True,
        )
        assert controls(searched.text).dialogs == 1
        blocked = client.post("/__add", data=form("M09", "m09"), follow_redirects=False)
        assert blocked.status_code == 409
        assert client.get("/__verify", params={"run_id": "m09"}).json()["success"] is False
        dismissed = client.post("/__dismiss", data=form("M09", "m09"), follow_redirects=True)
        assert controls(dismissed.text).dialogs == 0
        added = client.post("/__add", data=form("M09", "m09"))
        assert added.status_code == 200
        assert "Added to cart" in controls(added.text).button_text
        assert client.get("/__verify", params={"run_id": "m09"}).json()["success"] is True


def test_m14_uses_seeded_layout_branches_without_changing_the_task():
    with TestClient(create_app()) as client:
        inline = client.get("/fixture", params={"mut": "M14", "seed": 2, "run_id": "m14-inline"})
        inline_repeat = client.get("/fixture", params={"mut": "M14", "seed": 2, "run_id": "m14-inline"})
        side_panel = client.get("/fixture", params={"mut": "M14", "seed": 3, "run_id": "m14-side"})
        assert inline.text == inline_repeat.text
        assert 'data-layout-variant="inline"' in inline.text
        assert 'data-testid="checkout-panel"' not in inline.text
        assert 'data-layout-variant="side-panel"' in side_panel.text
        assert 'data-testid="checkout-panel"' in side_panel.text
        assert "Add to cart" in controls(inline.text).button_text
        assert "Add to cart" in controls(side_panel.text).button_text
        client.post("/__add", data=form("M14", "m14-inline", seed=2))
        client.post("/__add", data=form("M14", "m14-side", seed=3))
        assert client.get("/__verify", params={"run_id": "m14-inline"}).json()["success"] is True
        assert client.get("/__verify", params={"run_id": "m14-side"}).json()["success"] is True


def test_runs_are_isolated_and_wrong_run_does_not_false_pass():
    with TestClient(create_app()) as client:
        client.post("/__add", data=form("M00", "run-a"))
        assert client.get("/__verify", params={"run_id": "run-a"}).json()["success"] is True
        run_b = client.get("/__verify", params={"run_id": "run-b"}).json()
    assert run_b["success"] is False
    assert run_b["checks"] == {"product": False, "quantity": False, "total": False, "not_saved_for_later": True, "order_confirmed": False}
