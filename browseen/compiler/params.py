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

    def placeholder(m: re.Match) -> str:
        name = names[m.lastgroup]
        # "$productQty" would read as one param; use braces when a letter or digit follows.
        return f"${{{name}}}" if re.match(r"[A-Za-z0-9_]", out[m.end():m.end() + 1]) else f"${name}"

    return pattern.sub(placeholder, out)


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


def _dynamic_segment(segment: str, inputs: dict[str, Any]) -> bool:
    """A path part that names the chosen item (a slug like blue-headphones, or a numeric id)."""
    if re.fullmatch(r"\d{2,}", segment):
        return True
    tokens = [t for t in re.split(r"[-_.]+", segment.lower()) if t]
    words = set(re.findall(r"[a-z0-9]+", " ".join(_text(v) for v in inputs.values()).lower()))
    return bool(tokens) and any(len(t) >= SHORT for t in tokens) and all(t in words for t in tokens)


def url_pattern(url: str, inputs: dict[str, Any] | None = None) -> str:
    """Regex matching any URL with the same path, ignoring query and fragment. Path parts that
    name an input-chosen item (/products/blue-headphones) match any value."""
    parts = url_path(url).split("/")
    return "/".join("[^/?#]+" if part and inputs and _dynamic_segment(part, inputs) else re.escape(part)
                    for part in parts) + r"(\?|#|$)"
