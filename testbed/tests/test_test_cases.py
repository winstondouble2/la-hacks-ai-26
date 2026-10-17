from fastapi.testclient import TestClient

from testbed.app import create_app


def test_test_case_hub_launches_all_real_fixture_routes_from_the_shop(tmp_path):
    with TestClient(create_app(tmp_path / "catalog.sqlite3")) as client:
        hub = client.get("/test-cases")
        demo_case = client.get("/lab/demo/case/M11")
        fixture = client.get("/lab/fixture", params={"mut": "M11", "seed": 7, "run_id": "shop-m11"})
        added = client.post("/lab/__add", data={"mut": "M11", "seed": "7", "run_id": "shop-m11"})
        incomplete = client.get("/lab/__verify", params={"run_id": "shop-m11"}).json()
        confirmed = client.post("/lab/__confirm", data={"mut": "M11", "seed": "7", "run_id": "shop-m11"})
        complete = client.get("/lab/__verify", params={"run_id": "shop-m11"}).json()

    assert hub.status_code == 200
    assert hub.text.count('data-testid="test-case-') == 8
    assert 'href="/lab/demo/case/M09"' in hub.text
    assert 'data-mutation="M11"' in demo_case.text
    assert 'data-testid="demo-telemetry"' in demo_case.text
    assert fixture.status_code == 200
    assert 'action="/lab/__add"' in fixture.text
    assert 'href="/test-cases">← Back to Browseen test cases</a>' in fixture.text
    assert added.status_code == 200
    assert incomplete["success"] is False
    assert confirmed.status_code == 200
    assert complete["success"] is True
