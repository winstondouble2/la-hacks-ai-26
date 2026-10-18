from fastapi.testclient import TestClient

from testbed.app import create_app


def test_search_returns_matching_product_only(tmp_path):
    with TestClient(create_app(tmp_path / "catalog.sqlite3")) as client:
        response = client.get("/search", params={"q": "Blue Wireless Headphones"})
    assert response.status_code == 200
    assert '>Blue Wireless Headphones</a>' in response.text
    assert response.text.count('data-testid="product-card"') == 1
    assert "Blue Mug" not in response.text
    assert "Red Kettle" not in response.text
    assert "$79.99" in response.text
