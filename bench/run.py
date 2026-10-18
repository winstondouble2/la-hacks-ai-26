"""Run the first synthetic harness smoke check: python -m bench.run --system mock."""
import argparse
import asyncio
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from bench.adapters import mock

# IDs and names from docs/benchmark.md, section 4. Metadata only in this slice.
MUTATIONS = {"M00": "none", "M01": "Selector churn", "M02": "Wrapper insertion", "M03": "Sibling reorder", "M04": "Text rename", "M09": "Popup", "M11": "Flow split", "M14": "A/B layout"}


def build_cases(mutations: list[str], seed: int) -> list[dict]:
    if not mutations or len(mutations) != len(set(mutations)):
        raise ValueError("Provide a nonempty list of distinct mutation IDs")
    unknown = set(mutations) - MUTATIONS.keys()
    if unknown:
        raise ValueError(f"Unsupported mutations for this smoke check: {sorted(unknown)}")
    cases = []
    for mutation in mutations:
        for scenario in ("success", "false-pass"):
            case = {"task_id": "T1", "system": "mock", "mutation_ids": [mutation],
                    "seed": seed, "scenario": scenario, "adapter_version": "mock-v1"}
            identity = json.dumps(case, sort_keys=True, separators=(",", ":"))
            case["case_id"] = hashlib.sha256(identity.encode()).hexdigest()
            cases.append(case)
    return cases


async def run_cases(cases: list[dict], output: Path) -> list[dict]:
    output.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    # Exclusive creation avoids silently overwriting or duplicating a prior run.
    # Resume, timeout/error handling, and budgets are separate review slices.
    with output.open("x", encoding="utf-8") as stream:
        for case in cases:
            started = perf_counter()
            result = await mock.execute(case)
            checks = await mock.verify_fixture(case)
            verified = bool(checks) and all(value is True for value in checks.values())
            success = result["reported_success"] and verified
            row = {**case, **result, "run_id": str(uuid4()),
                   "timestamp": datetime.now(timezone.utc).isoformat(),
                   "synthetic": True, "measurement_kind": "harness_smoke_only",
                   "verifier_source": "mock_fixture", "mutation_applied": False,
                   "verify_checks": checks, "verified": verified, "success": success,
                   "false_pass": result["reported_success"] and not verified,
                   "elapsed_seconds": perf_counter() - started,
                   "heal_tier": None, "trace_id": None,
                   "failure_reason": None if success else "fixture_verification_failed"}
            stream.write(json.dumps(row, allow_nan=False) + "\n")
            stream.flush()
            rows.append(row)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system", choices=["mock"], required=True)
    parser.add_argument("--mutations", default="M00,M04,M09")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    try:
        cases = build_cases(args.mutations.split(","), args.seed)
        output = args.out or Path("bench/results") / f"mock-{uuid4().hex}.jsonl"
        rows = asyncio.run(run_cases(cases, output))
    except (ValueError, FileExistsError) as error:
        parser.error(str(error))
    print("SYNTHETIC HARNESS CHECK — no website mutations or healing executed")
    print(f"{len(rows)} rows: {sum(row['success'] for row in rows)} fixture successes, "
          f"{sum(row['false_pass'] for row in rows)} false-pass fixtures rejected")
    print(f"Results: {output}")


if __name__ == "__main__":
    main()
