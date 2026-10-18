"""Synthetic wiring fixtures. No browser, website, model, or healing is run."""


async def execute(case: dict) -> dict:
    # Deliberately claims success even for the false-pass fixture.
    return {"reported_success": True, "llm_calls": 0,
            "input_tokens": 0, "output_tokens": 0,
            "estimated_cost_usd": 0.0, "usage_status": "reported"}


async def verify_fixture(case: dict) -> dict:
    # Separate fixture oracle: never trusts execute()'s claimed success.
    # This does NOT inspect persisted website state.
    if case["scenario"] == "success":
        return {"fixture_expected_order": True}
    if case["scenario"] == "false-pass":
        return {"fixture_expected_order": False}
    raise ValueError(f"Unknown fixture scenario: {case['scenario']}")
