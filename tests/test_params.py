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


def test_braces_when_a_letter_follows_the_placeholder():
    # The storefront renders "<name><small>Qty 2</small>" as "Blue Wireless HeadphonesQty 2".
    inputs = {"product": "Blue Wireless Headphones", "qty": 2}
    assert templatize("Blue Wireless HeadphonesQty 2", inputs) == "${product}Qty $qty"
    assert templatize("Blue Wireless Headphones · 2", inputs) == "$product · $qty"


def test_mentions_input_ignores_short_values():
    assert mentions_input("2 × Blue Mug", INPUTS)
    assert not mentions_input("Page 2", INPUTS)


def test_param_types():
    assert [param_type(v) for v in (2, 1.5, True, "x")] == ["integer", "number", "boolean", "string"]


def test_url_pattern_generalizes_item_slugs_and_ids():
    inputs = {"product": "Blue Wireless Headphones", "qty": 2}
    slug = url_pattern("http://127.0.0.1:8001/products/blue-headphones?run_id=rec-1", inputs)
    assert slug == r"/products/[^/?#]+(\?|#|$)"
    assert re.search(slug, "http://127.0.0.1:8001/products/red-kettle?run_id=x")
    assert not re.search(slug, "http://127.0.0.1:8001/cart?run_id=x")
    assert url_pattern("http://x/orders/12345", inputs) == r"/orders/[^/?#]+(\?|#|$)"
    assert url_pattern("http://x/checkout", inputs) == r"/checkout(\?|#|$)"
    assert url_pattern("http://localhost:8765/product.html?id=blue-mug", INPUTS) == r"/product\.html(\?|#|$)"


def test_url_pattern_matches_the_same_path_only():
    root = url_pattern("http://localhost:8765/")
    assert re.search(root, "http://localhost:8765/") and re.search(root, "http://localhost:8765/?q=blue")
    assert not re.search(root, "http://localhost:8765/product.html")
    product = url_pattern("http://localhost:8765/product.html?id=blue-mug")
    assert re.search(product, "http://localhost:8765/product.html?id=red-kettle")
    assert not re.search(product, "http://localhost:8765/checkout.html")
