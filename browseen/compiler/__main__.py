"""Same as `python -m browseen compile runs/<run_id> [--name NAME] [--no-llm] [--dry-run]`."""

from browseen.observability import init_sentry

init_sentry()  # loads .env (ANTHROPIC_API_KEY); the Anthropic call shows up in Sentry

import sys  # noqa: E402

from browseen.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(["compile", *sys.argv[1:]], prog="python -m browseen.compiler"))
