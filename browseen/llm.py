"""One structured-output Claude call, shared by the compiler's LLM pass and the tier-2 healer.

Never raises for API problems: a refusal, truncation or API error comes back as parsed=None
with a note, so callers can fall back. Opus 5.5 always thinks, so no thinking/temperature.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

from browseen.agent import FALLBACK_MODEL, MODEL
from browseen.costs import PRICES, usd
from browseen.recorder.trace import Usage

T = TypeVar("T", bound=BaseModel)


@dataclass
class StructuredResult(Generic[T]):
    parsed: T | None
    usage: Usage
    model: str
    note: str = ""  # why parsed is None, or that the fallback model served


def structured_call(system: str, prompt: str, output_format: type[T], *, effort: str = "medium",
                    max_tokens: int = 16000, model: str = MODEL) -> StructuredResult[T]:
    import anthropic

    try:
        response = anthropic.Anthropic().beta.messages.parse(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_format=output_format,
            output_config={"effort": effort},
            # Server-side fallback: if the model refuses, Anthropic reruns the request on this one.
            betas=["server-side-fallback-2026-06-01"],
            fallbacks=[{"model": FALLBACK_MODEL}],
        )
    except anthropic.APIConnectionError as e:
        return StructuredResult(None, Usage(), model, f"connection error: {e}")
    except anthropic.RateLimitError as e:
        return StructuredResult(None, Usage(), model, f"rate limited: {e.message}")
    except anthropic.APIStatusError as e:
        return StructuredResult(None, Usage(), model, f"API error {e.status_code}: {e.message}")

    u = response.usage
    tokens: dict[str, Any] = dict(
        input_tokens=u.input_tokens or 0, output_tokens=u.output_tokens or 0,
        cache_read_tokens=u.cache_read_input_tokens or 0, cache_write_tokens=u.cache_creation_input_tokens or 0)
    served = response.model if response.model in PRICES else model
    usage = Usage(llm_calls=1, usd=usd(served, **tokens), **tokens)
    fallback_ran = any(getattr(e, "type", None) == "fallback_message" for e in (getattr(u, "iterations", None) or []))
    note = f"served by fallback {response.model}" if fallback_ran else ""

    if response.stop_reason == "refusal":
        category = response.stop_details.category if response.stop_details else "unknown"
        return StructuredResult(None, usage, response.model, f"refused ({category})")
    if response.stop_reason == "max_tokens":
        return StructuredResult(None, usage, response.model, "output truncated at max_tokens")
    if response.parsed_output is None:
        return StructuredResult(None, usage, response.model, "no parsable output")
    return StructuredResult(response.parsed_output, usage, response.model, note)
