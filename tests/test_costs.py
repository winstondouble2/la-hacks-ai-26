import pytest

from browseen.costs import usd


def test_opus_5_5_prices():
    assert usd("claude-opus-5-5", input_tokens=1_000_000) == pytest.approx(4.00)
    assert usd("claude-opus-5-5", output_tokens=1_000_000) == pytest.approx(20.00)
    # The Oct 17 smoke run: 29,228×4 + 68,470×0.20 + 13,694×5 + 1,767×20 = 234,416 → $0.234416
    assert usd("claude-opus-5-5", input_tokens=29_228, cache_read_tokens=68_470,
               cache_write_tokens=13_694, output_tokens=1_767) == pytest.approx(0.234416)


def test_unknown_model_raises():
    with pytest.raises(KeyError):
        usd("gpt-unknown", input_tokens=1)
