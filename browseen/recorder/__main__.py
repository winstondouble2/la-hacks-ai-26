"""Same as `python -m browseen record ...` / `python -m browseen show runs/<run_id>`."""

from browseen.observability import init_sentry

init_sentry()  # also loads .env, which browser_use reads at import time

import sys  # noqa: E402

from browseen.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(prog="python -m browseen.recorder"))
