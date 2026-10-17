import re

from browseen.compiler.params import mentions_input, param_type, templatize, url_pattern

INPUTS = {"qty": 2, "product": "Blue Mug", "name": "Ada Lovelace", "address": "1 Main St"}


def test_values_become_params():
    assert templatize("Order confirmed: 2 × Blue Mug", INPUTS) == "Order confirmed: $qty × $product"
    assert templatize("Shipping to Ada Lovelace, 1 Main St", INPUTS) == "Shipping to $name, $address"


def test_literal_dollars_are_escaped_and_short_values_need_word_boundaries():
    assert templatize("Blue Mug — $12", INPUTS) == "$product — $$12"
    assert templatize("h2 price 22", INPUTS) == "h2 price 22"


def test_longest_value_wins_and_placeholders_are_not_rescanned():
    inputs = {"product": "Blue Mug", "big": "Blue Mug XL", "x": "rod"}
    assert templatize("Blue Mug XL", inputs) == "$big"
    assert templatize("Blue Mug", inputs) == "$product"  # "rod" doesn't hit the inserted "$product"


def test_mentions_input_ignores_short_values():
    assert mentions_input("2 × Blue Mug", INPUTS)
    assert not mentions_input("Page 2", INPUTS)


def test_param_types():
    assert [param_type(v) for v in (2, 1.5, True, "x")] == ["integer", "number", "boolean", "string"]


def test_url_pattern_matches_the_same_path_only():
    root = url_pattern("http://localhost:8765/")
    assert re.search(root, "http://localhost:8765/") and re.search(root, "http://localhost:8765/?q=blue")
    assert not re.search(root, "http://localhost:8765/product.html")
    product = url_pattern("http://localhost:8765/product.html?id=blue-mug")
    assert re.search(product, "http://localhost:8765/product.html?id=red-kettle")
    assert not re.search(product, "http://localhost:8765/checkout.html")
