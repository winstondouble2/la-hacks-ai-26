"""Turning recorded literals back into $params, and URL patterns for checks."""

import re
from typing import Any
from urllib.parse import urlparse

SHORT = 3  # values shorter than this ("2") are only replaced as whole words


def _text(value: Any) -> str:
    return str(value).lower() if isinstance(value, bool) else str(value)


def _value_pattern(value: str) -> str:
    escaped = re.escape(value.replace("$", "$$"))
    return escaped if len(value) >= SHORT else rf"(?<![\w$]){escaped}(?!\w)"


def templatize(text: str, inputs: dict[str, Any]) -> str:
    """Replace recorded input values in `text` with $name, escaping literal $ as $$.

    One pass, longest values first, so "$product" inserted for one value is never rescanned
    for another, and a short value like "2" can't hit "$12" or "h2".
    """
    out = text.replace("$", "$$")
    values = sorted(((k, _text(v)) for k, v in inputs.items() if _text(v)), key=lambda kv: -len(kv[1]))
    if not values:
        return out
    names = {f"p{i}": name for i, (name, _) in enumerate(values)}
    pattern = re.compile("|".join(f"(?P<p{i}>{_value_pattern(v)})" for i, (_, v) in enumerate(values)))
    return pattern.sub(lambda m: "$" + names[m.lastgroup], out)


def mentions_input(text: str, inputs: dict[str, Any]) -> bool:
    """Whether `text` contains a recorded input value long enough to be distinctive."""
    return any(len(v) >= SHORT and v in text for v in map(_text, inputs.values()))


def param_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    return "string"


def url_path(url: str | None) -> str | None:
    return (urlparse(url).path or "/") if url else None


def url_pattern(url: str) -> str:
    """Regex matching any URL with the same path, ignoring query and fragment."""
    return re.escape(url_path(url)) + r"(\?|#|$)"
