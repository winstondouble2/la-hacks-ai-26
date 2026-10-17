"""Locator synthesis: build candidate locators for a recorded element and test them on the
page as it was recorded (the step's before-HTML).

Pages are loaded with scripts stripped and JavaScript off, so set_content shows exactly
the recorded DOM. A candidate is kept only if it matches one element and that element is
the recorded one (same node as the recorded XPath).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from playwright.sync_api import sync_playwright

from browseen.program import Locator
from browseen.recorder.trace import TraceElement

SCRIPT_RE = re.compile(r"<script\b[^>]*>.*?</script\s*>", re.S | re.I)
SNAPSHOT_RE = re.compile(r'^- ([a-z]+)(?: "((?:[^"\\]|\\.)*)")?')
FIELD_ROLES = {"textbox", "searchbox", "spinbutton", "combobox", "listbox", "checkbox", "radio", "slider", "switch"}
NON_ROLES = {"text", "generic", "paragraph", "group", "img"}  # snapshot lines that don't name a usable role
TAG_ROLES = {"button": "button", "a": "link", "select": "combobox", "textarea": "textbox"}
INPUT_ROLES = {"checkbox": "checkbox", "radio": "radio", "number": "spinbutton", "search": "searchbox",
               "range": "slider", "submit": "button", "button": "button", "reset": "button", "image": "button"}
FINGERPRINT_ATTRS = ("id", "name", "type", "href", "placeholder", "aria-label", "data-testid", "role")
GENERATED_ID_RE = re.compile(r"\d{4,}|[0-9a-f]{8,}|^(ember|react|radix|mui|headlessui|:r)", re.I)
IS_TARGET_JS = "(el, xpath) => el === document.evaluate(xpath, document, null, 9, null).singleNodeValue"
# Nearest ancestor that looks like a dialog, banner or popup: a hint that the step may be optional.
CONTAINER_JS = r"""(el) => {
  const hint = /cookie|consent|banner|modal|popup|overlay|newsletter/i;
  for (let n = el.parentElement; n && n !== document.body; n = n.parentElement) {
    const role = n.getAttribute("role") || (n.tagName === "DIALOG" ? "dialog" : "");
    const label = n.getAttribute("aria-label");
    const named = label ? ` "${label}"` : "";
    if (role === "dialog" || role === "alertdialog" || n.getAttribute("aria-modal") === "true")
      return (role || "dialog") + named;
    const cls = typeof n.className === "string" ? n.className : "";
    if (hint.test(`${n.id} ${cls}`))
      return n.tagName.toLowerCase() + (n.id ? "#" + n.id : "") + named;
  }
  return null;
}"""


@dataclass
class Candidate:
    locator: Locator
    matches: int
    is_target: bool

    @property
    def kept(self) -> bool:
        return self.matches == 1 and self.is_target


def _quote(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def fallback_role(el: TraceElement) -> str | None:
    if el.attributes.get("role"):
        return el.attributes["role"]
    if el.tag == "input":
        kind = el.attributes.get("type", "text").lower()
        return INPUT_ROLES.get(kind, None if kind in ("password", "hidden", "file") else "textbox")
    if el.tag == "a" and "href" not in el.attributes:
        return None
    return TAG_ROLES.get(el.tag)


def stable_css(el: TraceElement) -> str | None:
    attrs = el.attributes
    el_id = attrs.get("id", "")
    if re.fullmatch(r"[A-Za-z][\w-]*", el_id) and not GENERATED_ID_RE.search(el_id):
        return f"#{el_id}"
    if attrs.get("name"):
        return f'{el.tag}[name="{_quote(attrs["name"])}"]'
    if el.tag == "a" and attrs.get("href"):
        return f'a[href="{_quote(attrs["href"])}"]'
    return None


def name_core(name: str) -> str | None:
    """The stable start of an accessible name that ends in a price or count:
    'Place demo order · $159.98' -> 'Place demo order', 'Cart (2)' -> 'Cart'."""
    core = re.split(r"\s+[·•|–—-]\s+|\s*\(|\s*\$|\s+\d", name, maxsplit=1)[0].strip()
    return core if len(core) >= 3 and core != name.strip() else None


def fingerprint_attrs(el: TraceElement) -> dict[str, str]:
    return {k: v for k, v in el.attributes.items() if k in FINGERPRINT_ATTRS}


class PageAnalyzer:
    """One headless, JavaScript-disabled browser page for analyzing recorded HTML."""

    def __enter__(self) -> PageAnalyzer:
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch()
        self.page = self._browser.new_context(java_script_enabled=False).new_page()
        return self

    def __exit__(self, *exc: Any) -> None:
        self._browser.close()
        self._pw.stop()

    def load(self, html: str) -> None:
        self.page.set_content(SCRIPT_RE.sub("", html))

    def has(self, xpath: str) -> bool:
        return self.page.locator(f"xpath={xpath}").count() == 1

    def text_lines(self) -> list[str]:
        return [line.strip() for line in self.page.locator("body").inner_text().splitlines() if line.strip()]

    def headings(self) -> list[str]:
        return [t.strip() for t in self.page.locator("h1, h2, h3").all_inner_texts() if t.strip()]

    def role_and_name(self, el: TraceElement) -> tuple[str | None, str | None]:
        """The element's computed ARIA role and accessible name, from its aria snapshot."""
        try:
            first = self.page.locator(f"xpath={el.xpath}").aria_snapshot().splitlines()[0].strip()
            if (m := SNAPSHOT_RE.match(first)) and m.group(1) not in NON_ROLES:
                name = m.group(2).replace('\\"', '"').replace("\\\\", "\\") if m.group(2) is not None else None
                return m.group(1), name
        except Exception:
            pass
        return fallback_role(el), el.ax_name

    def container(self, xpath: str) -> str | None:
        """e.g. 'dialog "Cookie consent"' if the element sits in a dialog, banner or popup."""
        found = self.page.locator(f"xpath={xpath}")
        return found.evaluate(CONTAINER_JS) if found.count() == 1 else None

    def verify(self, locator: Locator, xpath: str) -> Candidate:
        found = locator.to_playwright(self.page)
        matches = found.count()
        is_target = matches == 1 and bool(found.evaluate(IS_TARGET_JS, xpath))
        return Candidate(locator, matches, is_target)

    def candidates(self, el: TraceElement) -> tuple[str | None, str | None, list[Candidate]]:
        """Candidate locators in preference order, each verified on the loaded page."""
        role, name = self.role_and_name(el)
        attrs = el.attributes
        options: list[Locator] = []
        if attrs.get("data-testid"):
            options.append(Locator(testid=attrs["data-testid"]))
        if name:
            if role in FIELD_ROLES:
                options.append(Locator(label=name, exact=True))
            if role:
                options.append(Locator(role=role, name=name, exact=True))
                if core := name_core(name):  # substring match: survives a changing price or count
                    options.append(Locator(role=role, name=core))
            if role not in FIELD_ROLES:
                options.append(Locator(text=name, exact=True))
        elif role:
            options.append(Locator(role=role))
        if attrs.get("placeholder"):
            options.append(Locator(placeholder=attrs["placeholder"], exact=True))
        if css := stable_css(el):
            options.append(Locator(css=css))
        options.append(Locator(xpath=el.xpath))

        unique: list[Locator] = []
        for option in options:
            if option not in unique:
                unique.append(option)
        return role, name, [self.verify(option, el.xpath) for option in unique]
