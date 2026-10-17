"""Token prices and cost math, shared by the recorder, runtime, healer and benchmark.

USD per million tokens, Anthropic first-party prices (checked 2026-10-17).
Cache writes are 5-minute writes (1.25x input).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Price:
    input: float
    output: float
    cache_read: float
    cache_write: float


PRICES: dict[str, Price] = {
    "claude-opus-5-5": Price(input=4.00, output=20.00, cache_read=0.20, cache_write=5.00),
    "claude-opus-4-8": Price(input=5.00, output=25.00, cache_read=0.50, cache_write=6.25),  # server-side fallback
}


def usd(model: str, *, input_tokens: int = 0, output_tokens: int = 0,
        cache_read_tokens: int = 0, cache_write_tokens: int = 0) -> float:
    """Cost of one or more calls. `input_tokens` excludes cache reads and writes."""
    p = PRICES[model]
    return (input_tokens * p.input + output_tokens * p.output
            + cache_read_tokens * p.cache_read + cache_write_tokens * p.cache_write) / 1_000_000
