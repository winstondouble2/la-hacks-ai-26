"""Checks made before a run starts: params, supported actions, URLs, run ids.

These raise ValueError (the CLI prints it as an error) and nothing is launched or written.
"""

from __future__ import annotations

import re
import secrets
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

from browseen.program import Param, Program

SUPPORTED_ACTIONS = ("navigate", "click", "fill", "select", "check", "uncheck", "press")  # extract: later
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_INT_RE = re.compile(r"-?\d+")
_NUM_RE = re.compile(r"-?\d+(\.\d+)?")


def new_run_id() -> str:
    """r_<UTC time>-<random>: sortable like the recorder's ids, and safe for parallel runs."""
    return f"r_{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-{secrets.token_hex(4)}"


def check_run_id(run_id: str) -> str:
    if not RUN_ID_RE.fullmatch(run_id):
        raise ValueError(f"invalid run id {run_id!r}: use letters, digits, '-' or '_' (max 64)")
    return run_id


def _type_ok(param: Param, value: Any) -> bool:
    if param.type == "boolean":
        return isinstance(value, bool) or (isinstance(value, str) and value.lower() in ("true", "false"))
    if isinstance(value, bool):
        return False
    if param.type == "integer":
        return isinstance(value, int) or (isinstance(value, str) and _INT_RE.fullmatch(value) is not None)
    if param.type == "number":
        return isinstance(value, (int, float)) or (isinstance(value, str) and _NUM_RE.fullmatch(value) is not None)
    return isinstance(value, (str, int, float))  # the CLI turns "007" into 7


def _check_url(where: str, url: str) -> None:
    if urlsplit(url).scheme not in ("http", "https"):
        raise ValueError(f"{where}: only http(s) URLs can be opened, got {url!r}")


def prepare(program: Program, params: dict[str, Any]) -> Program:
    """The program with params substituted, after checking everything that can be checked
    without a browser."""
    if not program.success:
        # The schema allows an empty list, but a run with nothing to verify could only "succeed"
        # because no action errored. Refuse it rather than report an unverified success.
        raise ValueError(f"{program.program} v{program.version} has no success checks; "
                         "a compiled run needs at least one to report success")
    if unsupported := [f"{s.id} ({s.action.type})" for s in program.steps if s.action.type not in SUPPORTED_ACTIONS]:
        raise ValueError(f"the runtime doesn't support these steps yet: {', '.join(unsupported)}")
    try:
        resolved = program.resolved(params)
    except KeyError as e:
        raise ValueError(e.args[0]) from e
    if bad := [f"{k} must be {program.params[k].type}, got {v!r}"
               for k, v in params.items() if not _type_ok(program.params[k], v)]:
        raise ValueError("bad params: " + "; ".join(bad))
    _check_url("start_url", resolved.start_url)
    for step in resolved.steps:
        if step.action.type == "navigate":
            _check_url(f"step {step.id}", step.action.url)
    return resolved
