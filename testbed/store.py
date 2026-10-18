"""The complete storefront. Demo navigation pins a run; only reload advances it."""
import json
import sqlite3
from contextlib import contextmanager
from hashlib import sha256
from urllib.parse import urlencode
from uuid import uuid4

from fastapi import Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse

from bench.fixtures.mutation_app import DEMO_SCENARIOS, SUPPORTED_MUTATIONS
from bench.telemetry import TokenTracker
from testbed.database import get_product, search_products

CATEGORIES = {
    "blue-headphones": "Tech", "pocket-speaker": "Tech", "blue-mug": "Home",
    "red-kettle": "Home", "sage-lamp": "Home", "canvas-tote": "Everyday",
    "daily-notebook": "Everyday", "steel-bottle": "Everyday",
}
FEATURES = {
    "blue-headphones": ["Wireless listening", "Soft over-ear cushions", "Adjustable headband"],
    "blue-mug": ["Glazed ceramic", "Comfortable loop handle", "Made for slow mornings"],
    "red-kettle": ["Easy-pour spout", "Stay-cool handle", "A bright kitchen accent"],
    "sage-lamp": ["Soft ambient light", "Compact metal shade", "Bedside or desk-ready"],
    "canvas-tote": ["Natural canvas", "Roomy everyday carry", "Comfortable shoulder straps"],
    "pocket-speaker": ["Wireless audio", "Compact design", "Easy everyday controls"],
    "daily-notebook": ["Lay-flat pages", "Hardcover binding", "A place for every idea"],
    "steel-bottle": ["Reusable steel", "Screw-top lid", "Easy to take along"],
}

# Describe the storefront's actual mutations, including changes that have no
# visual effect. Keep these in presenter controls, outside the shopping flow.
CASE_NOTES = {
    "M00": "Normal shopping flow. Nothing on the product page changes.",
    "M01": "The Add to cart button looks identical, but its HTML ID and class change and its test ID is removed. Tests whether a saved selector can recover.",
    "M02": "The product page looks identical, but two extra HTML containers wrap Add to cart. Tests selectors that depend on the old page structure.",
    "M03": "On the product page, Save for later moves above Add to cart. Saving an item does not count as ordering it.",
    "M04": "On the product page, Add to cart is renamed Add to bag. The shopping action stays the same.",
    "M09": "Search for a product to trigger a blocking newsletter popup. Dismiss it before continuing to shop.",
    "M11": "Click Add to cart to reach an extra review page. Confirm and add to cart is required before checkout.",
    "M14": "On the product page, odd seeds move the purchase controls into a separate panel below the product details. Even seeds keep them inline.",
}


def initialize_store(path):
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE IF NOT EXISTS shop_runs (id TEXT PRIMARY KEY, state TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS shop_orders (run_id TEXT PRIMARY KEY, receipt TEXT NOT NULL)")


def install_store(app, templates, path):
    telemetry = TokenTracker()

    def validate_id(run_id):
        if not run_id or len(run_id) > 100 or not run_id.strip():
            raise HTTPException(400, "Invalid run ID")

    def new_run(index=0, mutation=None, seed=None, run_id=None):
        index %= len(DEMO_SCENARIOS)
        case = DEMO_SCENARIOS[index]
        run_id = run_id or "shop-" + uuid4().hex[:16]
        validate_id(run_id)
        state = dict(id=run_id, index=index, mutation=mutation or case[0], seed=case[1] if seed is None else seed,
                     cart={}, saved=[], searched=False, popup_dismissed=False, pending=None, order=None,
                     demo_mode=mutation is None)
        with sqlite3.connect(path) as db:
            db.execute("INSERT INTO shop_runs VALUES (?, ?)", (run_id, json.dumps(state)))
        return state

    def load(run_id):
        validate_id(run_id)
        with sqlite3.connect(path) as db:
            row = db.execute("SELECT state FROM shop_runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "This shopping session was not found. Open /shop to start again.")
        return json.loads(row[0])

    @contextmanager
    def edit(run_id):
        validate_id(run_id)
        with sqlite3.connect(path) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT state FROM shop_runs WHERE id = ?", (run_id,)).fetchone()
            if row is None:
                raise HTTPException(404, "Shopping session not found")
            state = json.loads(row[0])
            yield state, db
            db.execute("UPDATE shop_runs SET state = ? WHERE id = ?", (json.dumps(state), run_id))

    def session(request):
        run_id = request.query_params.get("run_id")
        mutation = request.query_params.get("mut")
        if mutation and mutation not in SUPPORTED_MUTATIONS:
            raise HTTPException(400, "Unsupported mutation")
        if run_id:
            try:
                state = load(run_id)
            except HTTPException as error:
                if error.status_code != 404 or not mutation:
                    raise
                try:
                    seed = int(request.query_params.get("seed", "7"))
                except ValueError:
                    raise HTTPException(400, "Invalid seed")
                if seed < 0:
                    raise HTTPException(400, "Invalid seed")
                index = next(i for i, case in enumerate(DEMO_SCENARIOS) if case[0] == mutation)
                state = new_run(index, mutation, seed, run_id)
            if mutation and state["mutation"] != mutation:
                raise HTTPException(409, "Run already belongs to another mutation")
            return state
        if request.cookies.get("browseen_shop_run"):
            try:
                return load(request.cookies["browseen_shop_run"])
            except HTTPException:
                pass
        return new_run()

    def product(product_id):
        item = get_product(path, product_id)
        if not item:
            raise HTTPException(404, "Product not found")
        return {**item, "category": CATEGORIES[item["id"]], "features": FEATURES[item["id"]]}

    def url(destination, run_id, **params):
        return destination + "?" + urlencode({"run_id": run_id, **params})

    def redirect(destination, state, **params):
        response = RedirectResponse(url(destination, state["id"], **params), 303)
        response.set_cookie("browseen_shop_run", state["id"], httponly=True, samesite="lax")
        return response

    def render(request, state, view, **context):
        lines = [{**product(key), "quantity": qty} for key, qty in state["cart"].items()]
        total = sum(line["price_cents"] * line["quantity"] for line in lines)
        churn = "action-" + sha256(f"M01:{state['seed']}".encode()).hexdigest()[:8]
        response = templates.TemplateResponse(request=request, name="store.html", context={
            "view": view, "state": state, "lines": lines, "total": total,
            "cart_count": sum(state["cart"].values()), "saved_count": len(state["saved"]),
            "case_title": DEMO_SCENARIOS[state["index"]][2], "churn": churn,
            "case_note": CASE_NOTES[state["mutation"]],
            "scenarios": DEMO_SCENARIOS, "case_notes": CASE_NOTES,
            "next_case": DEMO_SCENARIOS[(state["index"] + 1) % len(DEMO_SCENARIOS)],
            "link": lambda destination, **params: url(destination, state["id"], **params),
            "money": lambda cents: f"${cents / 100:,.2f}",
            "popup": state["mutation"] == "M09" and state["searched"] and not state["popup_dismissed"],
            **context,
        })
        response.set_cookie("browseen_shop_run", state["id"], httponly=True, samesite="lax")
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/lab/demo")
    def old_demo(request: Request):
        return redirect("/shop", session(request))

    @app.get("/lab/demo/reset")
    @app.get("/demo/reset")
    def reset_demo():
        return redirect("/shop", new_run())

    @app.get("/lab/demo/case/{mutation}")
    def select_case(mutation: str):
        if mutation not in SUPPORTED_MUTATIONS:
            raise HTTPException(404, "Unknown case")
        return redirect("/shop", new_run(next(i for i, case in enumerate(DEMO_SCENARIOS) if case[0] == mutation)))

    @app.post("/demo/advance")
    def advance(run_id: str = Form()):
        state = new_run(load(run_id)["index"] + 1)
        response = redirect("/shop", state)
        return response

    @app.get("/shop")
    @app.get("/search")
    def shop(request: Request, q: str = Query("", max_length=200), category: str = "All", sort: str = "featured"):
        state = session(request)
        if request.url.path == "/search" and q.strip():
            with edit(state["id"]) as (state, db):
                state["searched"] = True
        products = [product(p["id"]) for p in search_products(path, q)]
        if category != "All":
            products = [p for p in products if p["category"] == category]
        if sort in {"price-low", "price-high"}:
            products.sort(key=lambda p: p["price_cents"], reverse=sort == "price-high")
        else:
            products.sort(key=lambda p: p["id"] != "blue-headphones")
        return render(request, state, "shop", products=products, query=q, category=category, sort=sort)

    @app.get("/products/{product_id}", name="product_detail")
    def details(request: Request, product_id: str):
        state = session(request)
        return render(request, state, "product", product=product(product_id),
                      related=[product(key) for key in ("blue-mug", "canvas-tote", "pocket-speaker") if key != product_id])

    @app.get("/cart")
    def cart(request: Request):
        return render(request, session(request), "cart")

    @app.get("/saved")
    def saved(request: Request):
        state = session(request)
        return render(request, state, "saved", products=[product(key) for key in state["saved"]])

    @app.post("/cart/add")
    def add(run_id: str = Form(), product_id: str = Form(), quantity: int = Form(1, ge=1, le=10)):
        product(product_id)
        with edit(run_id) as (state, db):
            if state["mutation"] == "M09" and state["searched"] and not state["popup_dismissed"]:
                raise HTTPException(409, "Close the newsletter invitation before continuing")
            state["order"] = None
            if state["mutation"] == "M11":
                state["pending"] = {"product_id": product_id, "quantity": quantity}
                destination = "/cart/review"
            else:
                state["cart"][product_id] = min(10, state["cart"].get(product_id, 0) + quantity)
                destination = "/cart"
        return redirect(destination, state)

    @app.get("/cart/review")
    def review(request: Request):
        state = session(request)
        if not state["pending"]:
            return redirect("/cart", state)
        return render(request, state, "review", product=product(state["pending"]["product_id"]))

    @app.post("/cart/review")
    def confirm_review(run_id: str = Form()):
        with edit(run_id) as (state, db):
            if not state["pending"]:
                raise HTTPException(409, "No item to review")
            item = state["pending"]
            state["cart"][item["product_id"]] = min(10, state["cart"].get(item["product_id"], 0) + item["quantity"])
            state["pending"] = None
        return redirect("/cart", state)

    @app.post("/cart/update")
    def update(run_id: str = Form(), product_id: str = Form(), quantity: int = Form(ge=0, le=10)):
        with edit(run_id) as (state, db):
            if product_id not in state["cart"]:
                raise HTTPException(404, "Item not in cart")
            if quantity:
                state["cart"][product_id] = quantity
            else:
                del state["cart"][product_id]
        return redirect("/cart", state)

    @app.post("/saved/toggle")
    def toggle_saved(run_id: str = Form(), product_id: str = Form()):
        product(product_id)
        with edit(run_id) as (state, db):
            if product_id in state["saved"]:
                state["saved"].remove(product_id)
            else:
                state["saved"].append(product_id)
        return redirect("/saved", state)

    @app.post("/newsletter/dismiss")
    def dismiss(run_id: str = Form()):
        with edit(run_id) as (state, db):
            state["popup_dismissed"] = True
        return redirect("/search", state, q="Blue Wireless Headphones")

    @app.get("/checkout")
    def checkout(request: Request):
        state = session(request)
        if state["pending"]:
            return redirect("/cart/review", state)
        if not state["cart"]:
            return redirect("/cart", state)
        return render(request, state, "checkout", error=None, fields={})

    @app.post("/checkout")
    def place_order(request: Request, run_id: str = Form(), name: str = Form(""), address: str = Form(""),
                    city: str = Form(""), postal: str = Form("")):
        fields = {"name": name.strip(), "address": address.strip(), "city": city.strip(), "postal": postal.strip()}
        with edit(run_id) as (state, db):
            if state["order"]:
                return redirect("/order", state)
            if state["pending"] or not state["cart"]:
                raise HTTPException(409, "Complete your cart before checking out")
            if any(not value or len(value) > 200 for value in fields.values()):
                return render(request, state, "checkout", error="Please complete every delivery field (up to 200 characters each).", fields=fields)
            if not state["order"]:
                items = [{**product(key), "quantity": qty} for key, qty in state["cart"].items()]
                receipt = {"id": "BR-" + uuid4().hex[:8].upper(), "items": items, **fields,
                           "total_cents": sum(p["quantity"] * p["price_cents"] for p in items)}
                db.execute("INSERT OR REPLACE INTO shop_orders VALUES (?, ?)", (run_id, json.dumps(receipt)))
                state["order"] = receipt
                state["cart"] = {}
        return redirect("/order", state)

    @app.get("/order")
    def confirmation(request: Request):
        state = session(request)
        if not state["order"]:
            return redirect("/cart", state)
        return render(request, state, "order", order=state["order"])

    @app.get("/__verify")
    def verify(run_id: str, product_id: str = "blue-headphones", quantity: int = 1,
               name: str | None = None, address: str | None = None):
        validate_id(run_id)
        with sqlite3.connect(path) as db:
            row = db.execute("SELECT receipt FROM shop_orders WHERE run_id = ?", (run_id,)).fetchone()
        order = json.loads(row[0]) if row else None
        checks = {"order_exists": order is not None,
                  "exact_items": bool(order and len(order["items"]) == 1 and order["items"][0]["id"] == product_id and order["items"][0]["quantity"] == quantity),
                  "name": bool(order and (name is None or order["name"] == name)),
                  "address": bool(order and (address is None or order["address"] == address))}
        return {"run_id": run_id, "success": all(checks.values()), "checks": checks}

    @app.get("/__telemetry")
    def usage(run_id: str):
        load(run_id)
        return telemetry.summary(run_id)

    @app.post("/__telemetry/usage")
    def report(run_id: str = Form(), stage: str = Form(), model: str = Form(), input_tokens: int = Form(), output_tokens: int = Form()):
        load(run_id)
        try:
            event = telemetry.record_provider_usage(run_id, stage=stage, model=model, input_tokens=input_tokens, output_tokens=output_tokens)
        except ValueError as error:
            raise HTTPException(422, str(error))
        return {"run_id": run_id, "event": event.as_dict()}

    @app.post("/__telemetry/cache-hit")
    def cache_hit(run_id: str = Form(), stage: str = Form()):
        load(run_id)
        try:
            event = telemetry.record_cache_hit(run_id, stage=stage)
        except ValueError as error:
            raise HTTPException(422, str(error))
        return {"run_id": run_id, "event": event.as_dict()}
