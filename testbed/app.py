"""Standalone shop. Run from the repo: uvicorn testbed.app:app --port 8001."""
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from bench.fixtures.mutation_app import create_app as create_mutation_app
from testbed.database import initialize
from testbed.store import install_store, initialize_store

ROOT = Path(__file__).resolve().parent
TEST_CASES = [
    {"id": "M00", "seed": 7, "level": "Baseline", "title": "Baseline control", "description": "The unchanged control case. Use it before and after a recorded run.", "accent": "control"},
    {"id": "M01", "seed": 7, "level": "Level 1", "title": "Selector drift", "description": "IDs and classes rotate while the visible product action stays the same.", "accent": "locator"},
    {"id": "M02", "seed": 7, "level": "Level 1", "title": "Wrapper insertion", "description": "New structural containers appear around the existing action.", "accent": "locator"},
    {"id": "M03", "seed": 7, "level": "Level 1", "title": "Sibling reorder", "description": "Save for later moves ahead of Add to cart; the verifier catches the wrong click.", "accent": "safety"},
    {"id": "M04", "seed": 7, "level": "Level 2", "title": "Text rename", "description": "The same product action is renamed from Add to cart to Add to bag.", "accent": "locator"},
    {"id": "M09", "seed": 7, "level": "Level 3", "title": "Blocking popup", "description": "Search inserts a required popup step before the product can be added.", "accent": "workflow"},
    {"id": "M11", "seed": 7, "level": "Level 3", "title": "Flow split", "description": "Adding to cart now needs a separate review and confirmation action.", "accent": "workflow"},
    {"id": "M14", "seed": 3, "level": "Level 3", "title": "Layout variant", "description": "A deterministic layout branch moves checkout into its own panel.", "accent": "layout"},
]


def create_app(database_path: Path | None = None) -> FastAPI:
    database_path = database_path or Path(os.environ.get("TESTBED_DATABASE", str(ROOT / "data" / "shop.sqlite3")))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        initialize(database_path)
        initialize_store(database_path)
        yield

    app = FastAPI(title="Browseen Shop", lifespan=lifespan)
    templates = Jinja2Templates(directory=str(ROOT / "templates"))
    app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")
    # Register storefront demo entry points before the legacy fixture mount.
    install_store(app, templates, database_path)
    app.mount("/lab", create_mutation_app(path_prefix="/lab", home_path="/test-cases"), name="test_lab")

    @app.get("/", include_in_schema=False)
    def home():
        return RedirectResponse("/shop")
    @app.get("/test-cases")
    def test_cases(request: Request):
        return templates.TemplateResponse(
            request=request, name="test_cases.html", context={"test_cases": TEST_CASES},
        )
    return app


app = create_app()
