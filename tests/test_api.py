"""The dashboard's run API (browseen/api.py), with a fake runner: no browser, no API key."""

import json
import shutil
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from browseen import program as P
from browseen.api import create_app

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def setup(tmp_path):
    programs = tmp_path / "programs"
    shutil.copytree(ROOT / "programs" / "buy-item", programs / "buy-item")
    shutil.copytree(ROOT / "programs" / "storefront-buy", programs / "storefront-buy")
    runs = tmp_path / "runs"
    calls, done = [], threading.Event()

    def fake_runner(**kwargs):
        calls.append(kwargs)
        done.set()

    client = TestClient(create_app(runs_dir=runs, programs_dir=programs, runner=fake_runner,
                                   agent_runner=fake_runner))
    return client, runs, programs, calls, done


def write_run(runs: Path, run_id: str, events: list[dict]) -> None:
    (runs / run_id).mkdir(parents=True)
    (runs / run_id / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))


def test_versions_and_rollback(setup):
    client, _, programs, _, _ = setup
    assert [p["version"] for p in client.get("/programs/buy-item/versions").json()] == [1, 2]
    restored = client.post("/programs/buy-item/rollback?to=1").json()
    assert restored["version"] == 3 and restored["history"][-1]["reason"] == "rollback to v1"
    assert P.versions("buy-item", programs) == [1, 2, 3]
    assert client.post("/programs/buy-item/rollback?to=3").status_code == 409
    assert client.get("/programs/nope/versions").status_code == 404
    assert client.get("/programs").json() == ["buy-item", "storefront-buy"]


def test_runs_and_events(setup):
    client, runs, _, _, _ = setup
    write_run(runs, "c_1", [{"ts": "t1", "type": "run_started"}, {"ts": "t2", "type": "run_finished", "success": True}])
    assert client.get("/runs").json() == [{"run_id": "c_1"}]
    assert client.get("/runs/c_1/events.jsonl").text.count("\n") == 2
    assert client.get("/runs/missing/events.jsonl").status_code == 404
    stream = client.get("/runs/c_1/events").text
    assert [json.loads(line[6:])["type"] for line in stream.splitlines() if line.startswith("data: ")] == [
        "run_started", "run_finished"]


def test_start_run_fills_params_and_testbed_query(setup):
    client, _, _, calls, done = setup
    response = client.post("/programs/storefront-buy/run", json={"params": {"product": "Red Kettle", "qty": 1},
                                                                 "mutations": ["M11"], "seed": 3})
    run_id = response.json()["run_id"]
    assert done.wait(5)
    call = calls[0]
    assert call["run_id"] == run_id and call["url_params"] == {"mut": "M11", "seed": 3}
    assert call["params"]["product"] == "Red Kettle" and call["params"]["name"] == "Ada Lovelace"  # recorded example
    assert call["params"]["run_id"] == run_id  # a fresh testbed session per run
    assert call["program"].version == 1 and call["verbose"] is False


def test_start_agent_run_uses_the_resolved_start_url(setup):
    client, _, _, calls, done = setup
    run_id = client.post("/programs/storefront-buy/run-agent", json={"mutations": ["M04"]}).json()["run_id"]
    assert done.wait(5) and run_id.startswith("r_")
    assert calls[0]["start_url"] == f"http://127.0.0.1:8001/shop?mut=M04&seed=7&run_id={run_id}"


def test_unknown_program_is_404(setup):
    client = setup[0]
    assert client.post("/programs/nope/run", json={}).status_code == 404
