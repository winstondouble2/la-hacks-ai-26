"""Local catalog storage; keep persistence separate from HTTP and templates."""
import sqlite3
from pathlib import Path

PRODUCTS = [
    ("blue-headphones", "Blue Wireless Headphones", "Over-ear comfort for your everyday soundtrack.", 7999),
    ("blue-mug", "Blue Mug", "A ceramic companion for slow mornings.", 1800),
    ("red-kettle", "Red Kettle", "A little color for your daily ritual.", 4500),
    ("sage-lamp", "Sage Table Lamp", "A softer light for your favorite corner.", 6800),
    ("canvas-tote", "Everyday Canvas Tote", "Room for the little things and the big plans.", 3200),
    ("pocket-speaker", "Pocket Speaker", "Good sound. Wherever the day takes you.", 4900),
    ("daily-notebook", "Daily Notebook", "A fresh page for your next good idea.", 1600),
    ("steel-bottle", "Daybreak Water Bottle", "A refillable companion for the everyday.", 2800),
]


def initialize(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE IF NOT EXISTS products (id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL, price_cents INTEGER NOT NULL)")
        db.executemany("INSERT OR IGNORE INTO products VALUES (?, ?, ?, ?)", PRODUCTS)


def search_products(path: Path, query: str) -> list[dict]:
    with sqlite3.connect(path) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute(
            "SELECT * FROM products WHERE instr(lower(name), lower(?)) > 0 ORDER BY name",
            (query.strip(),),
        ).fetchall()
    return [dict(row) for row in rows]


def get_product(path: Path, product_id: str) -> dict | None:
    with sqlite3.connect(path) as db:
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    return dict(row) if row is not None else None
