from html.parser import HTMLParser
from urllib.parse import urlsplit

from fastapi.testclient import TestClient

from testbed.app import create_app


class ProductLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and attrs.get("class") == "product-link":
            self.urls.append(attrs["href"])


def test_search_link_opens_correct_product(tmp_path):
    with TestClient(create_app(tmp_path / "catalog.sqlite3")) as client:
        results = client.get("/search", params={"q": "Blue Wireless Headphones"})
        links = ProductLinks()
        links.feed(results.text)
        assert len(links.urls) == 1
        detail = client.get(urlsplit(links.urls[0]).path)
        assert detail.status_code == 200
        assert '<h1 id="product-name">Blue Wireless Headphones</h1>' in detail.text
        assert 'data-testid="product-price">$79.99</p>' in detail.text
        assert "Over-ear comfort for your everyday soundtrack." in detail.text
        assert '<h1 id="product-name">Blue Mug</h1>' not in detail.text
        assert 'A few good companions.' in detail.text
