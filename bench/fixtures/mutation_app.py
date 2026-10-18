"""Run with: uvicorn bench.fixtures.mutation_app:app --port 8011."""

from html import escape
from hashlib import sha256
from threading import RLock
from urllib.parse import urlencode, urlsplit
from uuid import uuid4

from fastapi import FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from bench.telemetry import TokenTracker

SUPPORTED_MUTATIONS = {"M00", "M01", "M02", "M03", "M04", "M09", "M11", "M14"}
PRODUCT = "Blue Wireless Headphones"
MUTATION_LABELS = {
    "M00": "Baseline — no page change",
    "M01": "Selector churn — IDs and classes rotate; test ID removed",
    "M02": "Wrapper insertion — extra DOM containers surround the product action",
    "M03": "Sibling reorder — secondary action moves ahead of Add to cart",
    "M04": "Text rename — Add to cart becomes Add to bag",
    "M09": "Popup — an extra blocking step appears after search",
    "M11": "Flow split — review and confirm becomes a new required step after cart",
    "M14": "A/B layout — seed selects a deterministic page variant",
}
DEMO_SCENARIOS = [
    ("M00", 7, "Baseline control", "The unchanged product flow establishes the control case."),
    ("M00", 7, "Baseline repeat", "The exact M00 case repeats. Once the runtime is connected, this is where replay and cache evidence belongs."),
    ("M01", 7, "Selector drift", "Hidden selector attributes changed; the visible button did not."),
    ("M02", 7, "Wrapper insertion", "Extra DOM structure now surrounds the same product action."),
    ("M03", 7, "Sibling reorder", "A nearby action moved ahead of Add to cart; verification catches the wrong choice."),
    ("M04", 7, "Text rename", "The product action now says Add to bag."),
    ("M09", 7, "Blocking popup", "Search inserts a new popup step before the product action."),
    ("M11", 7, "Flow split", "Add to cart is no longer enough: review and confirmation are required."),
    ("M11", 7, "Flow-split repeat", "The exact M11 flow repeats. Once a real repair is saved, this is the proof point for reusing it."),
    ("M14", 3, "Layout variant", "The checkout action moved into a distinct panel."),
]


def create_app(path_prefix: str = "", home_path: str | None = None) -> FastAPI:
    """Create the fixture standalone or mounted below a parent application."""
    path_prefix = path_prefix.rstrip("/")
    if path_prefix and not path_prefix.startswith("/"):
        raise ValueError("path_prefix must start with '/'")
    if home_path is not None and not home_path.startswith("/"):
        raise ValueError("home_path must start with '/'")
    app = FastAPI(title="Browseen mutation fixture")
    states: dict[str, dict] = {}
    state_lock = RLock()
    telemetry = TokenTracker()
    # Cookies are scoped to a host, not a port. Keep the standalone fixture and
    # the shop-mounted lab from advancing each other's guided-demo sequence.
    demo_cookie_name = "browseen_demo_next" + (path_prefix.replace("/", "_") or "_fixture")

    def validate(mutation: str, seed: int, run_id: str) -> None:
        if mutation not in SUPPORTED_MUTATIONS:
            raise HTTPException(status_code=400, detail="Unsupported mutation")
        if not run_id.strip() or len(run_id) > 100:
            raise HTTPException(status_code=400, detail="Invalid run_id")
        if seed < 0:
            raise HTTPException(status_code=400, detail="Seed must be nonnegative")

    def validate_run_id(run_id: str) -> None:
        if not run_id.strip() or len(run_id) > 100:
            raise HTTPException(status_code=400, detail="Invalid run_id")

    def state_for(run_id: str) -> dict:
        with state_lock:
            return states.setdefault(run_id, {"searched": False, "popup_dismissed": False, "cart": [], "saved_for_later": False, "order_confirmed": False})

    def fixture_url(mutation: str, seed: int, run_id: str) -> str:
        return f"{path_prefix}/fixture?" + urlencode({"mut": mutation, "seed": seed, "run_id": run_id})

    def endpoint(path: str) -> str:
        return f"{path_prefix}{path}"

    def action_return_url(mutation: str, seed: int, run_id: str, return_to: str) -> str:
        if not return_to:
            return fixture_url(mutation, seed, run_id)
        parsed = urlsplit(return_to)
        if parsed.scheme or parsed.netloc or parsed.path != endpoint("/demo"):
            raise HTTPException(status_code=400, detail="Invalid return_to")
        return return_to

    def page(mutation: str, seed: int, run_id: str, demo_context: dict | None = None) -> str:
        state = state_for(run_id)
        button_name = "Add to bag" if mutation == "M04" else "Add to cart"
        added_button_name = "Added to bag" if mutation == "M04" else "Added to cart"
        layout_variant = "side-panel" if mutation == "M14" and seed % 2 else "inline"
        selector_token = sha256(f"M01:{seed}".encode()).hexdigest()[:8]
        if mutation == "M01":
            product_button_attributes = f'id="action-{selector_token}" class="action-{selector_token}"'
        else:
            product_button_attributes = 'id="add-to-cart" class="add-button" data-testid="add-to-cart" data-action="add-product"'
        popup_active = mutation == "M09" and state["searched"] and not state["popup_dismissed"]
        continuation_fields = ""
        demo_header = ""
        demo_script = ""
        if demo_context:
            current_url = endpoint("/demo") + "?" + urlencode({
                "current": demo_context["index"], "run_id": run_id,
            })
            continuation_fields = f'<input type="hidden" name="return_to" value="{escape(current_url)}">'
            telemetry_url = endpoint("/__telemetry") + "?" + urlencode({"run_id": run_id})
            home_link = f'<a href="{escape(home_path)}">Test cases</a>' if home_path else ""
            demo_header = f"""
            <header class="store-header"><a class="browseen-brand" href="{escape(home_path or endpoint('/demo'))}">browseen<span>shop</span></a><nav><a class="active" href="{endpoint('/demo')}">Shop</a>{home_link}<a href="{endpoint('/demo/reset')}">Reset demo</a></nav></header>
            <aside class="demo-strip" data-testid="demo-current" data-mutation="{mutation}" data-scenario-index="{demo_context['index']}"><span>Demo mode</span><strong>{mutation} · {escape(demo_context['title'])}</strong><small>View {demo_context['index'] + 1} of {len(DEMO_SCENARIOS)} · Reload to change the site</small></aside>
            <details class="run-diagnostics" data-testid="demo-telemetry" data-telemetry-url="{escape(telemetry_url)}"><summary>Run diagnostics</summary><div class="diagnostics-body"><p class="telemetry-status" data-testid="telemetry-status">Waiting for the runtime to report usage.</p><div class="telemetry-totals"><span>Model calls: <strong data-telemetry="calls">—</strong></span><span>Input: <strong data-telemetry="input">—</strong></span><span>Output: <strong data-telemetry="output">—</strong></span><span>Cache hits: <strong data-telemetry="cache">—</strong></span></div><a href="{escape(telemetry_url)}">Open run data</a></div></details>
            """
            history_cleanup = f"history.replaceState(null, '', '{endpoint('/demo')}');" if demo_context["resuming"] else ""
            demo_script = f"""<script>
              const panel = document.querySelector('[data-telemetry-url]');
              const status = panel.querySelector('[data-testid="telemetry-status"]');
              const update = (name, value) => panel.querySelector(`[data-telemetry="${{name}}"]`).textContent = value;
              async function refreshTelemetry() {{ try {{ const report = await fetch(panel.dataset.telemetryUrl, {{cache: 'no-store'}}).then(response => response.json()); if (report.status === 'awaiting_runtime_events') return; const totals = report.totals; status.textContent = 'Live provider-reported usage for this run.'; update('calls', totals.new_model_calls); update('input', totals.input_tokens); update('output', totals.output_tokens); update('cache', totals.cache_hits); }} catch (error) {{ status.textContent = 'Telemetry is temporarily unavailable.'; }} }}
              refreshTelemetry(); window.setInterval(refreshTelemetry, 2000); {history_cleanup}
            </script>"""
        cart_summary = ""
        if state["cart"]:
            cart_summary = """
            <aside aria-live="polite" data-testid="cart-summary">
              <strong>Cart: 1 item · $79.99</strong>
              <p>Blue Wireless Headphones · Quantity 1</p>
            </aside>
            """
        save_summary = ""
        if state["saved_for_later"]:
            save_summary = """
            <aside aria-live="polite" data-testid="save-summary">
              <strong>Saved for later</strong>
              <p>Checkout has not started, so independent verification must fail.</p>
            </aside>
            """
        confirmation_panel = ""
        if mutation == "M11" and state["cart"] and not state["order_confirmed"]:
            confirmation_panel = f"""
            <aside class="confirmation-panel" data-testid="order-confirmation-step">
              <p class="eyebrow">ONE MORE STEP</p>
              <h2>Review your order</h2>
              <p>Your item is in the cart, but checkout now has a separate confirmation step.</p>
              <form action="{endpoint('/__confirm')}" method="post">
                <input type="hidden" name="mut" value="{escape(mutation)}">
                <input type="hidden" name="seed" value="{seed}">
                <input type="hidden" name="run_id" value="{escape(run_id)}">
                {continuation_fields}
                <button type="submit">Review and confirm order</button>
              </form>
            </aside>
            """
        elif mutation == "M11" and state["order_confirmed"]:
            confirmation_panel = """
            <aside class="order-confirmed" data-testid="order-confirmed">
              <strong>Order confirmed</strong>
              <p>The inserted review step is complete.</p>
            </aside>
            """
        if state["cart"]:
            product_action = f'<button type="button" {product_button_attributes} disabled>{added_button_name}</button>'
        else:
            product_action = f'<button type="submit" {product_button_attributes}>{button_name}</button>'
        action_form = f"""
        <form action="{endpoint('/__add')}" method="post">
          <input type="hidden" name="mut" value="{escape(mutation)}">
          <input type="hidden" name="seed" value="{seed}">
          <input type="hidden" name="run_id" value="{escape(run_id)}">
          {continuation_fields}
          {product_action}
        </form>
        """
        save_form = f"""
        <form action="{endpoint('/__save')}" method="post">
          <input type="hidden" name="mut" value="{escape(mutation)}">
          <input type="hidden" name="seed" value="{seed}">
          <input type="hidden" name="run_id" value="{escape(run_id)}">
          {continuation_fields}
          <button type="submit" class="secondary-action">Save for later</button>
        </form>
        """
        if mutation == "M02":
            action_form = f'<div class="action-shell"><div class="action-inner">{action_form}</div></div>'
        if state["cart"]:
            product_controls = action_form
        elif mutation == "M03":
            product_controls = f'<div class="action-controls">{save_form}{action_form}</div>'
        else:
            product_controls = f'<div class="action-controls">{action_form}{save_form}</div>'
        if layout_variant == "side-panel":
            product_area = f"""
            <section class="split-layout" data-testid="split-layout">
              <article class="product-card" aria-label="{PRODUCT}">
                <p class="eyebrow">PRODUCT</p>
                <h2>{PRODUCT}</h2><p class="price">$79.99</p>
              </article>
              <aside class="checkout-panel" aria-label="Checkout panel" data-testid="checkout-panel">
                <p class="eyebrow">CHECKOUT</p>
                <h2>Ready to check out?</h2>
                <p>Add this item from the separate checkout panel.</p>
                {product_controls}
              </aside>
            </section>
            """
        else:
            product_area = f"""
            <article class="product-card inline-layout" aria-label="{PRODUCT}">
              <p class="eyebrow">PRODUCT</p>
              <h2>{PRODUCT}</h2><p class="price">$79.99</p>
              {product_controls}
            </article>
            """
        popup = ""
        if popup_active:
            popup = f"""
            <div role="dialog" aria-modal="true" aria-labelledby="popup-title" data-testid="newsletter-popup">
              <h2 id="popup-title">Before you continue</h2>
              <p>Join our synthetic newsletter.</p>
              <form action="{endpoint('/__dismiss')}" method="post">
                <input type="hidden" name="mut" value="{escape(mutation)}">
                <input type="hidden" name="seed" value="{seed}">
                <input type="hidden" name="run_id" value="{escape(run_id)}">
                {continuation_fields}
                <button type="submit">Close popup</button>
              </form>
            </div>
            """
        lab_navigation = (
            f'<a class="lab-back" href="{escape(home_path)}">← Back to Browseen test cases</a>'
            if home_path and not demo_context else ""
        )
        return f"""<!doctype html>
        <html lang="en"><head><meta charset="utf-8"><title>{'Browseen demo' if demo_context else f'Mutation fixture {escape(mutation)}'}</title>
        <style>
          :root {{ color: #173a31; background: #f5f2eb; font-family: Arial, sans-serif; }}
          * {{ box-sizing: border-box; }}
          body {{ margin: 0; }}
          main {{ max-width: 940px; margin: 0 auto; padding: 44px 28px 64px; }}
          h1, h2 {{ font-family: Georgia, serif; }}
          h1 {{ font-size: 36px; margin: 0 0 28px; }}
          .lab-back {{ display: inline-block; margin-bottom: 22px; color: #315e50; font-size: 14px; text-underline-offset: 4px; }}
          .store-header {{ display: flex; justify-content: space-between; align-items: center; padding-bottom: 22px; border-bottom: 1px solid #ccd8cf; }} .browseen-brand {{ color: #173a31; font-size: 25px; font-weight: 800; text-decoration: none; }} .browseen-brand span {{ margin-left: 7px; font-size: 12px; font-weight: 400; letter-spacing: 1px; }} .store-header nav {{ display: flex; gap: 18px; }} .store-header nav a {{ color: #315e50; font-size: 14px; text-decoration: none; }} .store-header nav a.active {{ color: #173a31; font-weight: 700; }}
          .demo-strip {{ display: flex; gap: 12px; align-items: center; margin: 18px 0; padding: 10px 13px; border-radius: 7px; background: #e5ece7; color: #38594f; font-size: 12px; }} .demo-strip span {{ font-weight: 700; letter-spacing: .8px; text-transform: uppercase; }} .demo-strip strong {{ color: #173a31; }} .demo-strip small {{ margin-left: auto; color: #587066; }}
          .run-diagnostics {{ margin: 0 0 26px; }} .run-diagnostics summary {{ width: fit-content; color: #315e50; font-size: 13px; cursor: pointer; text-underline-offset: 3px; }} .diagnostics-body {{ display: grid; grid-template-columns: 1fr auto; gap: 12px 28px; align-items: center; margin-top: 10px; padding: 14px 16px; border: 1px solid #cbd8cf; border-radius: 8px; background: #fff; }} .telemetry-status {{ margin: 0; color: #4d655d; font-size: 13px; }} .telemetry-totals {{ display: flex; flex-wrap: wrap; gap: 14px; color: #315e50; font-size: 13px; }} .diagnostics-body a {{ color: #315e50; font-size: 13px; text-underline-offset: 4px; }}
          h2 {{ font-size: 27px; margin: 8px 0; }}
          .mutation-note {{ display: inline-block; margin: 0 0 6px; padding: 8px 10px; border-radius: 999px; background: #e5ece7; color: #38594f; font-size: 13px; }}
          form[role="search"] {{ display: flex; gap: 10px; align-items: end; margin: 24px 0 28px; }}
          label {{ display: block; font-weight: 700; }}
          input {{ display: block; margin-top: 7px; padding: 10px; border: 1px solid #aebbb3; border-radius: 4px; font: inherit; }}
          button {{ margin-top: 7px; padding: 10px 15px; border: 0; border-radius: 4px; background: #1d5545; color: white; font: inherit; cursor: pointer; }}
          button:disabled {{ background: #80968d; cursor: default; }}
          .action-controls {{ display: flex; flex-wrap: wrap; gap: 10px; align-items: end; }}
          .action-controls form {{ margin: 0; }}
          .secondary-action {{ background: transparent; color: #315e50; border: 1px solid #9bb2a8; }}
          .action-shell {{ padding: 10px; border: 1px dashed #779a8d; border-radius: 8px; }}
          .action-inner {{ padding: 2px; }}
          .product-card {{ min-height: 230px; padding: 28px; border: 1px solid #ccd8cf; border-radius: 12px; background: white; box-shadow: 0 9px 24px rgba(23, 58, 49, .08); }}
          .inline-layout {{ max-width: 480px; }}
          .eyebrow {{ margin: 0; color: #5d766c; font-size: 11px; font-weight: 700; letter-spacing: 1.8px; }}
          .price {{ margin: 10px 0 18px; font-size: 22px; font-weight: 700; }}
          .split-layout {{ display: grid; grid-template-columns: minmax(0, 1fr) 285px; gap: 28px; align-items: stretch; }}
          .checkout-panel {{ padding: 28px; border-radius: 12px; background: #1d5545; color: white; box-shadow: 0 9px 24px rgba(23, 58, 49, .16); }}
          .checkout-panel .eyebrow {{ color: #c0d9c7; }}
          .checkout-panel h2 {{ font-size: 26px; }}
          .checkout-panel button {{ width: 100%; background: #f3c56b; color: #173a31; font-weight: 700; }}
          .checkout-panel button:disabled {{ background: #c5d1ca; }}
          [data-testid="cart-summary"] {{ max-width: 480px; margin-top: 24px; padding: 17px 20px; border-left: 5px solid #e29d38; background: #fff; }}
          [data-testid="save-summary"] {{ max-width: 480px; margin-top: 24px; padding: 17px 20px; border-left: 5px solid #b74b46; background: #fff3f0; }}
          .confirmation-panel {{ max-width: 480px; margin-top: 24px; padding: 24px; border-radius: 12px; background: #fcf0cf; border: 1px solid #e1b553; }}
          .order-confirmed {{ max-width: 480px; margin-top: 24px; padding: 17px 20px; border-left: 5px solid #2d8064; background: #e8f4ed; }}
          [role="dialog"] {{ max-width: 440px; margin-top: 24px; padding: 22px; border: 2px solid #b74b46; border-radius: 12px; background: #fff3f0; }}
          @media (max-width: 650px) {{ main {{ padding: 28px 18px; }} h1 {{ font-size: 30px; }} .split-layout {{ grid-template-columns: 1fr; }} .store-header {{ align-items: start; }} .store-header nav {{ flex-wrap: wrap; justify-content: end; }} .demo-strip, .diagnostics-body {{ display: block; }} .demo-strip small {{ display: block; margin: 5px 0 0; }} .telemetry-totals {{ margin-top: 10px; }} form[role="search"] {{ display: block; }} form[role="search"] button {{ width: 100%; }} }}
        </style></head>
        <body data-mutation="{escape(mutation)}" data-seed="{seed}" data-run-id="{escape(run_id)}" data-layout-variant="{layout_variant}">
          <main>
            {demo_header}
            {lab_navigation}
            {'' if demo_context else '<h1>Locator and workflow mutation fixture</h1>'}
            {'' if demo_context else f'<p class="mutation-note" data-testid="mutation-description"><strong>{escape(mutation)}</strong> · {escape(MUTATION_LABELS[mutation])}</p>'}
            <form action="{endpoint('/__search')}" method="post" role="search">
              <input type="hidden" name="mut" value="{escape(mutation)}">
              <input type="hidden" name="seed" value="{seed}">
              <input type="hidden" name="run_id" value="{escape(run_id)}">
              {continuation_fields}
              <label for="product-search">Search products</label>
              <input id="product-search" name="query" value="{PRODUCT}">
              <button type="submit">Search</button>
            </form>
            {product_area}
            {cart_summary}
            {save_summary}
            {confirmation_panel}
            {popup}
            {demo_script}
          </main>
        </body></html>"""

    @app.get("/fixture", response_class=HTMLResponse)
    def fixture(
        mut: str = Query(default="M00"), seed: int = Query(default=7),
        run_id: str = Query(default="manual"),
    ):
        validate(mut, seed, run_id)
        return page(mut, seed, run_id)

    @app.get("/demo", response_class=HTMLResponse)
    def demo(request: Request, current: int | None = Query(default=None), run_id: str | None = Query(default=None)):
        resuming = current is not None or run_id is not None
        if resuming:
            if current is None or run_id is None:
                raise HTTPException(status_code=400, detail="current and run_id must be provided together")
            validate_run_id(run_id)
            index = current % len(DEMO_SCENARIOS)
        else:
            raw_index = request.cookies.get(demo_cookie_name, "0")
            index = int(raw_index) if raw_index.isdigit() else 0
            index %= len(DEMO_SCENARIOS)
            run_id = f"demo-{index + 1}-{uuid4().hex[:8]}"
        mutation, seed, title, description = DEMO_SCENARIOS[index]
        response = HTMLResponse(page(mutation, seed, run_id, {
            "index": index, "title": title, "description": description, "resuming": resuming,
        }))
        if not resuming:
            response.set_cookie(demo_cookie_name, str((index + 1) % len(DEMO_SCENARIOS)), httponly=True, samesite="lax")
        return response

    @app.get("/demo/case/{mutation}")
    def start_demo_at_case(mutation: str):
        """Enter the polished demo at a selected real fixture case."""
        try:
            index = next(index for index, scenario in enumerate(DEMO_SCENARIOS) if scenario[0] == mutation)
        except StopIteration as error:
            raise HTTPException(status_code=404, detail="No guided-demo scenario for mutation") from error
        response = RedirectResponse(endpoint("/demo"), status_code=303)
        response.set_cookie(demo_cookie_name, str(index), httponly=True, samesite="lax")
        return response

    @app.get("/demo/reset")
    def reset_demo():
        response = RedirectResponse(endpoint("/demo"), status_code=303)
        response.delete_cookie(demo_cookie_name)
        return response

    @app.post("/__reset")
    def reset(mut: str = Form(), seed: int = Form(), run_id: str = Form()):
        validate(mut, seed, run_id)
        with state_lock:
            states[run_id] = {"searched": False, "popup_dismissed": False, "cart": [], "saved_for_later": False, "order_confirmed": False}
        telemetry.clear(run_id)
        return {"run_id": run_id, "reset": True}

    @app.post("/__telemetry/usage")
    def report_usage(
        run_id: str = Form(), stage: str = Form(), model: str = Form(),
        input_tokens: int = Form(), output_tokens: int = Form(),
    ):
        """Accept provider-returned token counts from a benchmark runtime."""
        validate_run_id(run_id)
        try:
            event = telemetry.record_provider_usage(
                run_id, stage=stage, model=model,
                input_tokens=input_tokens, output_tokens=output_tokens,
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return {"run_id": run_id, "event": event.as_dict()}

    @app.post("/__telemetry/cache-hit")
    def report_cache_hit(run_id: str = Form(), stage: str = Form()):
        """Accept an explicit cache event; it never adds new token usage."""
        validate_run_id(run_id)
        try:
            event = telemetry.record_cache_hit(run_id, stage=stage)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return {"run_id": run_id, "event": event.as_dict()}

    @app.get("/__telemetry")
    def telemetry_summary(run_id: str = Query()):
        validate_run_id(run_id)
        return telemetry.summary(run_id)

    @app.post("/__search", response_class=RedirectResponse)
    def search(
        mut: str = Form(), seed: int = Form(), run_id: str = Form(), query: str = Form(),
        return_to: str = Form(default=""),
    ):
        validate(mut, seed, run_id)
        if query != PRODUCT:
            raise HTTPException(status_code=422, detail="Fixture requires the exact product")
        with state_lock:
            state_for(run_id)["searched"] = True
        return RedirectResponse(action_return_url(mut, seed, run_id, return_to), status_code=303)

    @app.post("/__dismiss", response_class=RedirectResponse)
    def dismiss(mut: str = Form(), seed: int = Form(), run_id: str = Form(), return_to: str = Form(default="")):
        validate(mut, seed, run_id)
        if mut != "M09" or not state_for(run_id)["searched"]:
            raise HTTPException(status_code=409, detail="No active popup")
        with state_lock:
            state_for(run_id)["popup_dismissed"] = True
        return RedirectResponse(action_return_url(mut, seed, run_id, return_to), status_code=303)

    @app.post("/__add", response_class=RedirectResponse)
    def add(mut: str = Form(), seed: int = Form(), run_id: str = Form(), return_to: str = Form(default="")):
        validate(mut, seed, run_id)
        state = state_for(run_id)
        if mut == "M09" and state["searched"] and not state["popup_dismissed"]:
            raise HTTPException(status_code=409, detail="Popup blocks the product action")
        with state_lock:
            updated_state = state_for(run_id)
            updated_state["cart"] = [{"product": PRODUCT, "quantity": 1, "total_cents": 7999}]
            updated_state["order_confirmed"] = mut != "M11"
        return RedirectResponse(action_return_url(mut, seed, run_id, return_to), status_code=303)

    @app.post("/__save", response_class=RedirectResponse)
    def save(mut: str = Form(), seed: int = Form(), run_id: str = Form(), return_to: str = Form(default="")):
        validate(mut, seed, run_id)
        with state_lock:
            state_for(run_id)["saved_for_later"] = True
        return RedirectResponse(action_return_url(mut, seed, run_id, return_to), status_code=303)

    @app.post("/__confirm", response_class=RedirectResponse)
    def confirm(mut: str = Form(), seed: int = Form(), run_id: str = Form(), return_to: str = Form(default="")):
        validate(mut, seed, run_id)
        state = state_for(run_id)
        if mut != "M11" or not state["cart"]:
            raise HTTPException(status_code=409, detail="No order is ready for confirmation")
        with state_lock:
            state_for(run_id)["order_confirmed"] = True
        return RedirectResponse(action_return_url(mut, seed, run_id, return_to), status_code=303)

    @app.get("/__verify")
    def verify(run_id: str = Query()):
        validate_run_id(run_id)
        state = state_for(run_id)
        cart = state["cart"]
        checks = {
            "product": len(cart) == 1 and cart[0]["product"] == PRODUCT,
            "quantity": len(cart) == 1 and cart[0]["quantity"] == 1,
            "total": len(cart) == 1 and cart[0]["total_cents"] == 7999,
            "not_saved_for_later": not state["saved_for_later"],
            "order_confirmed": state["order_confirmed"],
        }
        return {"run_id": run_id, "success": all(checks.values()), "checks": checks}

    return app


app = create_app()
