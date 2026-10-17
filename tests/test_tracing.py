"""browseen.tracing: helpers stay safe with Sentry off, and send the right spans and logs when on."""

import sentry_sdk
from sentry_sdk.transport import Transport

from browseen import tracing


class CaptureTransport(Transport):
    """Keeps every envelope in memory instead of sending it."""

    def __init__(self, options=None):
        super().__init__(options)
        self.envelopes = []

    def capture_envelope(self, envelope):
        self.envelopes.append(envelope)


def _items(transport, kind):
    return [item for env in transport.envelopes for item in env.items if item.type == kind]


def test_helpers_are_noops_without_sentry():
    sentry_sdk.init(dsn=None)  # what init_sentry() does when SENTRY_DSN is unset
    with tracing.run_span("t", "compiled", program_version=1, run_id="r1", program="p"):
        with tracing.step_span(0, "click", "compiled", step_id="s1") as span:
            tracing.log_check(span, "s1", "pre target_unique", passed=False, detail="0 matches")
            with tracing.heal_span("s1", 3) as heal:
                with tracing.agent_takeover_span("s1", "do the step") as agent:
                    tracing.record_agent_result(agent, "done", 10, 2)
                tracing.record_heal_result(heal, "s1", 3, verified=True)
            tracing.mark_healed(span, "renamed", 3)
    tracing.log_run_event("run_finished", "r1", success=True)
    # mark_healed outside any run used to raise AttributeError on the missing transaction
    with tracing.step_span(0, "click", "compiled") as span:
        tracing.mark_healed(span, "renamed", 2)


def test_spans_and_logs_are_sent():
    transport = CaptureTransport()
    sentry_sdk.init(dsn="https://key@o1.ingest.us.sentry.io/1", transport=transport,
                    traces_sample_rate=1.0, enable_logs=True)
    tracing._demo("heal3")
    sentry_sdk.flush()

    spans = []
    for item in _items(transport, "transaction"):
        spans += item.payload.json.get("spans", [])
    for item in _items(transport, "span"):
        payload = item.payload.json
        spans += payload.get("items", [payload])
    by_op = {}
    for s in spans:
        by_op.setdefault(s.get("op") or s.get("attributes", {}).get("sentry.op", {}).get("value"), []).append(s)

    assert {"agent.step", "agent.heal", "gen_ai.invoke_agent"} <= set(by_op), set(by_op)
    heal = by_op["agent.heal"][0].get("data", {})
    assert heal.get("heal.tier") == 3 and heal.get("heal.verified") is True
    step_ids = {s.get("data", {}).get("step.id") for s in by_op["agent.step"]}
    assert step_ids == {"s1", "s2", "s3"}

    bodies = [log["body"] for item in _items(transport, "log") for log in item.payload.json["items"]]
    assert any(b.startswith("check failed s3") for b in bodies), bodies
    assert any(b.startswith("heal succeeded s3") for b in bodies), bodies
    assert any(b.startswith("run_started demo_heal3") for b in bodies), bodies
