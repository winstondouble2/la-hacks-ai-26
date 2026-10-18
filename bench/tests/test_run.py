import asyncio
import json

from bench.run import build_cases, run_cases


def test_mock_matrix_rejects_false_passes_and_writes_honest_results(tmp_path):
    cases = build_cases(["M00", "M04", "M09"], seed=7)
    assert cases == build_cases(["M00", "M04", "M09"], seed=7)
    assert len({case["case_id"] for case in cases}) == 6
    output = tmp_path / "smoke.jsonl"
    rows = asyncio.run(run_cases(cases, output))
    saved = [json.loads(line) for line in output.read_text().splitlines()]
    assert saved == rows
    assert len(rows) == 6
    for row in rows:
        expected = row["scenario"] == "success"
        assert row["reported_success"] is True
        assert row["verified"] is expected
        assert row["success"] is expected
        assert row["false_pass"] is (not expected)
        assert row["failure_reason"] == (None if expected else "fixture_verification_failed")
        assert row["synthetic"] is True
        assert row["mutation_applied"] is False
        assert row["verifier_source"] == "mock_fixture"
        assert row["llm_calls"] == 0
        assert row["elapsed_seconds"] >= 0
        assert row["heal_tier"] is None
