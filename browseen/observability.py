"""Sentry setup. Call init_sentry() once, before any agent code runs."""

import os

import sentry_sdk
from dotenv import load_dotenv


def init_sentry() -> None:
    load_dotenv()

    sentry_sdk.init(
        dsn=os.environ.get("SENTRY_DSN"),
        environment=os.environ.get("SENTRY_ENVIRONMENT", "development"),
        # Falls back to the git SHA when unset.
        release=os.environ.get("SENTRY_RELEASE"),
        send_default_pii=True,
        # Tracing: every agent run / compiled step becomes a span.
        # Lower to 0.1-0.2 if this ever sees real traffic.
        traces_sample_rate=1.0,
        # Profiling, tied to active spans.
        profile_session_sample_rate=1.0,
        profile_lifecycle="trace",
        # Structured logs.
        enable_logs=True,
    )
