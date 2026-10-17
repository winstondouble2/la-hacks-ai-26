"""Browser Use setup shared by the recorder (B) and the tier-3 healer (A).

Each setting below fixes a real failure we hit with Claude Opus 5.5. browser_use is
imported inside the functions because it reads its env vars (telemetry!) at import
time: callers must load .env first, which init_sentry() does.
"""

from typing import Any

MODEL = "claude-opus-5-5"
FALLBACK_MODEL = "claude-opus-4-8"
# Chromium on macOS can hang at startup on a keychain prompt (browser-use #5415).
CHROME_ARGS = ["--use-mock-keychain", "--password-store=basic"]


def make_llm(model: str = MODEL) -> Any:
    from browser_use import ChatAnthropic

    return ChatAnthropic(
        model=model,
        # Opus 5.5 rejects forced tool_choice (HTTP 400); setting thinking makes the wrapper use "auto".
        thinking={"type": "adaptive"},
        # Thinking tokens count toward max_tokens, so the 8192 default risks truncated output.
        max_tokens=16000,
        # Server-side fallback: if Opus 5.5 refuses a step, Anthropic retries it on this model.
        fallbacks=[{"model": FALLBACK_MODEL}],
    )


def make_profile(headless: bool = False) -> Any:
    from browser_use import BrowserProfile

    # No default extensions: they include a cookie-banner auto-dismisser, and we want the
    # agent to see pages exactly as served.
    return BrowserProfile(headless=headless, args=CHROME_ARGS, enable_default_extensions=False)


def make_agent(task: str, *, headless: bool = False, model: str = MODEL, **kwargs: Any) -> Any:
    """A Browser Use Agent with our fixes. Extra kwargs (initial_actions, browser_session, …) pass through."""
    from browser_use import Agent

    if "browser_session" not in kwargs and "browser" not in kwargs:
        kwargs.setdefault("browser_profile", make_profile(headless))
    return Agent(
        task=task,
        llm=make_llm(model),
        # Browser Use's default output has a "thinking" field, which Opus 5.5 refuses as
        # reasoning extraction (stop_reason "refusal").
        use_thinking=False,
        # The judge makes extra LLM calls; we verify success ourselves.
        use_judge=False,
        **kwargs,
    )
