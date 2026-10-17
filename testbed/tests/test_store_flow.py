import re

import pytest
from fastapi.testclient import TestClient

from testbed.app import create_app
from bench.fixtures.mutation_app import DEMO_SCENARIOS


def run_from(page):
    return re.search(r'data-run-id="([^"]+)"', page.text).group(1)


def begin(client, mutation="M00", seed=7):
    return client.get("/shop", params={"mut": mutation, "seed": seed, "run_id": "flow-" + mutation})


@pytest.mark.parametrize("mutation", ["M00", "M01", "M02", "M03", "M04", "M09", "M11", "M14"])
def test_complete_store_purchase_with_each_real_mutation(tmp_path, mutation):
    with TestClient(create_app(tmp_path / "store.sqlite3")) as client:
        home = begin(client, mutation, seed=3 if mutation == "M14" else 7)
        assert home.text.count('data-testid="product-card"') == 8
        run_id = run_from(home)
        params = {"run_id": run_id}
        results = client.get("/search", params={**params, "q": "Blue Wireless Headphones"})
        assert results.text.count('data-testid="product-card"') == 1
        detail = client.get("/products/blue-headphones", params=params)
        assert run_from(detail) == run_id
        data = {**params, "product_id": "blue-headphones", "quantity": 1}
        if mutation == "M01":
            assert 'id="action-' in detail.text
            assert 'data-testid="add-to-cart"' not in detail.text
        if mutation == "M02":
            assert 'class="action-shell"' in detail.text
        if mutation == "M03":
            assert detail.text.index('action="/saved/toggle"') < detail.text.index('action="/cart/add"')
            client.post("/saved/toggle", data=data)
            assert not client.get("/__verify", params=params).json()["success"]
        if mutation == "M04":
            assert '>Add to bag</button>' in detail.text
        if mutation == "M14":
            assert 'data-testid="checkout-panel"' in detail.text
        if mutation == "M09":
            assert 'role="dialog"' in results.text
            assert client.post("/cart/add", data=data).status_code == 409
            client.post("/newsletter/dismiss", data=params)
        added = client.post("/cart/add", data=data)
        assert added.status_code == 200
        if mutation == "M11":
            assert added.url.path == "/cart/review"
            assert client.get("/checkout", params=params).url.path == "/cart/review"
            assert client.post("/checkout", data={**params, "name": "A", "address": "B", "city": "C", "postal": "D"}).status_code == 409
            added = client.post("/cart/review", data=params)
        assert added.url.path == "/cart"
        assert not client.get("/__verify", params=params).json()["success"]
        checkout = client.get("/checkout", params=params)
        assert 'id="full-name"' in checkout.text
        receipt = client.post("/checkout", data={**params, "name": "Demo Shopper", "address": "123 Sample Street", "city": "Example City", "postal": "90000"})
        assert receipt.status_code == 200
        assert receipt.url.path == "/order"
        assert 'data-testid="order-confirmed"' in receipt.text
        assert 'data-testid="cart-count">0</span>' in receipt.text
        verdict = client.get("/__verify", params={**params, "name": "Demo Shopper", "address": "123 Sample Street"}).json()
        assert verdict["success"] is True
        assert not client.get("/__verify", params={**params, "quantity": 2}).json()["success"]
        assert not client.get("/__verify", params={**params, "address": "Wrong address"}).json()["success"]


def test_navigation_keeps_run_and_advancement_starts_fresh_without_erasing_old_cart(tmp_path):
    with TestClient(create_app(tmp_path / "store.sqlite3")) as client:
        home = client.get("/demo/reset")
        first_id = run_from(home)
        client.post("/cart/add", data={"run_id": first_id, "product_id": "blue-mug", "quantity": 2})
        for route in ["/shop", "/products/blue-mug", "/saved", "/cart", "/checkout"]:
            assert run_from(client.get(route, params={"run_id": first_id})) == first_id
        repeat = client.post("/demo/advance", data={"run_id": first_id})
        assert 'data-mutation="M00"' in repeat.text
        assert 'Baseline repeat' in repeat.text
        assert run_from(repeat) != first_id
        assert 'data-testid="cart-count">0</span>' in repeat.text
        next_case = client.post("/demo/advance", data={"run_id": run_from(repeat)})
        assert 'data-mutation="M01"' in next_case.text
        old_cart = client.get("/cart", params={"run_id": first_id})
        assert 'data-testid="cart-count">2</span>' in old_cart.text


def test_cart_edits_validation_saved_items_and_usage(tmp_path):
    path = tmp_path / "store.sqlite3"
    with TestClient(create_app(path)) as client:
        run_id = run_from(client.get("/shop"))
        params = {"run_id": run_id}
        data = {**params, "product_id": "blue-mug", "quantity": 2}
        client.post("/cart/add", data=data)
        assert '$36.00' in client.get("/cart", params=params).text
        client.post("/cart/update", data={**data, "quantity": 3})
        assert '$54.00' in client.get("/cart", params=params).text
        invalid = client.post("/checkout", data={**params, "name": " ", "address": "", "city": "", "postal": ""})
        assert 'role="alert"' in invalid.text
        assert not client.get("/__verify", params=params).json()["success"]
        assert client.post("/cart/add", data={**data, "quantity": -1}).status_code == 422
        client.post("/saved/toggle", data=data)
        assert '>Blue Mug</a>' in client.get("/saved", params=params).text
        client.post("/saved/toggle", data=data)
        assert 'Nothing here just yet.' in client.get("/saved", params=params).text
        client.post("/cart/update", data={**data, "quantity": 0})
        assert 'Your cart is empty.' in client.get("/cart", params=params).text
        assert client.get("/__telemetry", params=params).json()["status"] == "awaiting_runtime_events"
        client.post("/__telemetry/usage", data={**params, "stage": "record", "model": "unit-test-model", "input_tokens": 123, "output_tokens": 45})
        client.post("/__telemetry/cache-hit", data={**params, "stage": "replay"})
        assert client.get("/__telemetry", params=params).json()["totals"] == {
            "new_model_calls": 1, "cache_hits": 1, "input_tokens": 123, "output_tokens": 45, "total_tokens": 168}
    # Shopping state survives app recreation; telemetry is intentionally local memory.
    with TestClient(create_app(path)) as client:
        assert client.get("/cart", params=params).status_code == 200


def test_demo_cycles_all_steps_with_explanations_and_keeps_pinned_runs(tmp_path):
    with TestClient(create_app(tmp_path / "store.sqlite3")) as client:
        page = client.get("/demo/reset")
        seen = set()
        for index, (mutation, seed, title, _) in enumerate(DEMO_SCENARIOS):
            run_id = run_from(page)
            assert run_id not in seen
            seen.add(run_id)
            assert f'data-scenario-index="{index}"' in page.text
            assert f'data-mutation="{mutation}"' in page.text
            assert f'data-seed="{seed}"' in page.text
            assert f'class="case-progress">{index + 1}/10' in page.text
            assert 'data-testid="case-explanation"' in page.text
            assert title in page.text
            # Neither shopping navigation nor opening diagnostics advances.
            detail = client.get("/products/blue-headphones", params={"run_id": run_id})
            assert run_from(detail) == run_id
            assert f'data-scenario-index="{index}"' in detail.text
            page = client.post("/demo/advance", data={"run_id": run_id})
        assert 'data-scenario-index="0"' in page.text
        assert run_from(page) not in seen
        pinned = begin(client, "M14", 2)
        assert 'class="case-progress">Pinned' in pinned.text
        assert 'data-demo-mode="false"' in pinned.text
        assert 'action="/demo/advance"' not in pinned.text
        assert run_from(client.get(str(pinned.url))) == run_from(pinned)
