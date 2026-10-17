"""Per-run, provider-reported model-usage telemetry.

This module deliberately does not estimate or invent usage.  A runtime records a
model call only after its provider returns token counts; cached execution is
recorded as a distinct event with zero new model tokens.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from threading import RLock


VALID_STAGES = {"record", "replay", "repair"}


@dataclass(frozen=True)
class TokenEvent:
    event_type: str
    stage: str
    model: str | None
    input_tokens: int
    output_tokens: int
    token_source: str

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def as_dict(self) -> dict:
        event = asdict(self)
        event["total_tokens"] = self.total_tokens
        return event


class TokenTracker:
    """Stores usage events separately for every benchmark run."""

    def __init__(self) -> None:
        self._events: dict[str, list[TokenEvent]] = {}
        self._lock = RLock()

    @staticmethod
    def _validate(stage: str, model: str | None, input_tokens: int, output_tokens: int) -> None:
        if stage not in VALID_STAGES:
            raise ValueError(f"stage must be one of {sorted(VALID_STAGES)}")
        if model is not None and (not model.strip() or len(model) > 200):
            raise ValueError("model must be a non-empty name of at most 200 characters")
        if input_tokens < 0 or output_tokens < 0:
            raise ValueError("token counts must be nonnegative")

    def record_provider_usage(
        self, run_id: str, *, stage: str, model: str, input_tokens: int, output_tokens: int
    ) -> TokenEvent:
        """Record counts returned by the model provider for one actual call."""
        self._validate(stage, model, input_tokens, output_tokens)
        event = TokenEvent(
            event_type="model_call",
            stage=stage,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            token_source="provider_reported",
        )
        with self._lock:
            self._events.setdefault(run_id, []).append(event)
        return event

    def record_cache_hit(self, run_id: str, *, stage: str) -> TokenEvent:
        """Record a replay that reused stored work and made no new model call."""
        self._validate(stage, None, 0, 0)
        event = TokenEvent(
            event_type="cache_hit",
            stage=stage,
            model=None,
            input_tokens=0,
            output_tokens=0,
            token_source="not_applicable",
        )
        with self._lock:
            self._events.setdefault(run_id, []).append(event)
        return event

    def clear(self, run_id: str) -> None:
        with self._lock:
            self._events.pop(run_id, None)

    def summary(self, run_id: str) -> dict:
        with self._lock:
            events = list(self._events.get(run_id, []))
        model_calls = [event for event in events if event.event_type == "model_call"]
        return {
            "run_id": run_id,
            # No event is not proof of zero usage; the runtime has not reported yet.
            "status": "reported" if events else "awaiting_runtime_events",
            "totals": {
                "new_model_calls": len(model_calls),
                "cache_hits": sum(event.event_type == "cache_hit" for event in events),
                "input_tokens": sum(event.input_tokens for event in model_calls),
                "output_tokens": sum(event.output_tokens for event in model_calls),
                "total_tokens": sum(event.total_tokens for event in model_calls),
            },
            "events": [event.as_dict() for event in events],
        }
