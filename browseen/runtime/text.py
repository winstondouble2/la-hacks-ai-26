"""Visible-text matching for `text_visible` checks.

A plain substring test lets near matches pass: "Blue Mug" is inside "Blue Mug Deluxe", and
"2 × Blue Mug" is inside "12 × Blue Mug". Here the expected text must appear in one visible
text unit (a rendered line, or one element's own visible text) with clean edges on both sides:

- the unit starts or ends there, or
- the neighbouring character is punctuation (":", ",", "—", "$", "(" ...), or
- the neighbour is a space and the character beyond it is not a letter or digit.

So "Blue Mug — $12", "Order confirmed: 2 × Blue Mug" and "Thanks, Ada Lovelace." match, while
"Blue Mug Deluxe", "Mini Blue Mug", "12 × Blue Mug" and "Blue Mugs" do not. Matching ignores
case and collapses whitespace. An element's own text counts as a unit, so
"Deliver to <b>Ada Lovelace</b>" still matches "Ada Lovelace". Hidden text never counts.
"""

from __future__ import annotations

import re
from typing import Iterable

_SPACE = re.compile(r"\s+")

# Visible text units. Only text nodes that are actually rendered count: the parent passes
# checkVisibility (display, visibility, content-visibility, and opacity on it or any ancestor) and
# the text keeps a box of at least 2x2 px after clipping by overflow-hidden ancestors (so zero-size
# clips, screen-reader-only 1px boxes and font-size 0 are out). innerText alone
# would keep opacity:0 and zero-size text. Each element's unit is its visible text, with a line
# break wherever the text moves to another block, so a block's lines and an inline element's own
# text (e.g. <b>Ada Lovelace</b> inside a sentence) are both units.
UNITS_JS = r"""() => {
  const body = document.body;
  if (!body) return [];
  const SKIP = new Set(["SCRIPT", "STYLE", "NOSCRIPT", "TEMPLATE"]);
  const isBlock = (el) => { const d = getComputedStyle(el).display; return !d.startsWith("inline") && d !== "contents"; };
  const blockOf = (el) => { for (let e = el; e && e !== body; e = e.parentElement) if (isBlock(e)) return e; return body; };
  const shown = (el) => el.checkVisibility({ visibilityProperty: true, opacityProperty: true, contentVisibilityAuto: true });
  // The text's boxes, cut down by every ancestor that clips its overflow; at least 2x2 px must remain.
  const clips = (el) => { const s = getComputedStyle(el); return s.overflowX !== "visible" || s.overflowY !== "visible"; };
  const hasBox = (node) => {
    const range = document.createRange();
    range.selectNodeContents(node);
    let boxes = Array.from(range.getClientRects()).map((r) => [r.left, r.top, r.right, r.bottom]);
    for (let el = node.parentElement; el && boxes.length; el = el.parentElement) {
      if (!clips(el)) continue;
      const c = el.getBoundingClientRect();
      boxes = boxes.map(([l, t, r, b]) => [Math.max(l, c.left), Math.max(t, c.top), Math.min(r, c.right), Math.min(b, c.bottom)]);
    }
    return boxes.some(([l, t, r, b]) => r - l >= 2 && b - t >= 2);
  };
  const texts = new Map();  // element -> { parts, block }
  const walker = document.createTreeWalker(body, NodeFilter.SHOW_TEXT);
  let used = 0;
  for (let node = walker.nextNode(); node && used < 5000; node = walker.nextNode()) {
    const value = node.nodeValue.replace(/\s+/g, " ");
    const parent = node.parentElement;
    if (!parent || SKIP.has(parent.tagName) || !shown(parent)) continue;
    const spacer = !value.trim();  // whitespace between elements keeps "Quantity Add to cart" apart
    if (!spacer && !hasBox(node)) continue;
    if (!spacer) used++;
    const block = blockOf(parent);
    for (let el = parent; el; el = el === body ? null : el.parentElement) {
      const entry = texts.get(el) || { parts: [], block: null };
      if (spacer) { if (entry.parts.length) entry.parts.push(" "); continue; }
      if (entry.block && entry.block !== block) entry.parts.push("\n");
      entry.parts.push(value);
      entry.block = block;
      texts.set(el, entry);
    }
  }
  const units = new Set();
  for (const { parts } of texts.values()) {
    for (const line of parts.join("").split("\n")) if (line.trim()) units.add(line);
  }
  return Array.from(units);
}"""


def normalize(text: str) -> str:
    return _SPACE.sub(" ", text).strip()


def _clean_edge(unit: str, inside: int, outside: int) -> bool:
    """Is the edge between unit[inside] (last/first matched char) and the text beyond clean?"""
    if not 0 <= outside < len(unit):
        return True
    neighbour = unit[outside]
    if neighbour.isalnum():
        return False
    if neighbour != " ":
        return True
    beyond = outside + (outside - inside)
    return not (0 <= beyond < len(unit) and unit[beyond].isalnum())


def _bounded_in(unit: str, expected: str) -> bool:
    start = unit.find(expected)
    while start != -1:
        end = start + len(expected)
        if _clean_edge(unit, start, start - 1) and _clean_edge(unit, end - 1, end):
            return True
        start = unit.find(expected, start + 1)
    return False


def text_found(units: Iterable[str], expected: str) -> bool:
    wanted = normalize(expected).casefold()
    if not wanted:
        return False
    return any(_bounded_in(normalize(u).casefold(), wanted) for u in units)


def near_matches(units: Iterable[str], expected: str, limit: int = 3) -> list[str]:
    """Units that contain the expected text without a clean match, for failure reports."""
    wanted = normalize(expected).casefold()
    found: list[str] = []
    for unit in dict.fromkeys(normalize(u) for u in units):
        if wanted and wanted in unit.casefold() and unit not in found:
            found.append(unit[:120])
        if len(found) == limit:
            break
    return found


def preview(units: Iterable[str], max_chars: int = 160) -> str:
    """The start of the page's visible text, for failure reports."""
    lines = [u for u in dict.fromkeys(normalize(u) for u in units) if u]
    text = " | ".join(lines)
    return text if len(text) <= max_chars else text[: max_chars - 1] + "…"
