"""ROLE A TEST FIXTURE: serves the mini shop to Playwright without a server.

Requests to http://localhost:8765/ (the start_url of programs/buy-item) are answered from
B's fixture in browseen/recorder/fixtures/mini_shop, read-only. A test can swap single files
for the variants in pages/ (renamed button, duplicates, slow content, near-match products...).
Every other request is aborted, so the tests never touch the network.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[3]
MINI_SHOP = ROOT / "browseen" / "recorder" / "fixtures" / "mini_shop"
PAGES = Path(__file__).resolve().parent / "pages"
BASE = "http://localhost:8765/"
TYPES = {".html": "text/html; charset=utf-8", ".js": "application/javascript; charset=utf-8"}


class FixtureSite:
    """`overrides` maps a served file name (e.g. "product.html") to a file in pages/.
    `abort` lists file names whose requests fail at the network level."""

    def __init__(self, overrides: dict[str, str] | None = None, abort: tuple[str, ...] = ()):
        self.overrides = dict(overrides or {})
        self.abort = set(abort)
        self.requests: list[str] = []  # served file names, in order

    def count(self, name: str) -> int:
        return self.requests.count(name)

    async def install(self, context) -> None:
        await context.route("**/*", lambda route: route.abort())  # registered first, so it is the fallback
        await context.route(f"{BASE}**", self._handle)

    async def _handle(self, route) -> None:
        name = urlsplit(route.request.url).path.lstrip("/") or "index.html"
        self.requests.append(name)
        if name in self.abort:
            await route.abort()
            return
        root = PAGES if name in self.overrides else MINI_SHOP
        path = (root / (self.overrides.get(name) or name)).resolve()
        if not path.is_relative_to(root) or not path.is_file():  # nothing outside the fixture folders
            await route.fulfill(status=404, content_type=TYPES[".html"], body="<h1>Not found</h1>")
            return
        await route.fulfill(path=path, content_type=TYPES.get(path.suffix, "application/octet-stream"))
