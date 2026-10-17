"""Program format: what the compiler (B) writes and the runtime and healer (A) execute.

One YAML file per version: programs/<name>/v<N>.yaml. Versions are append-only, so a
rollback is just loading an older file. B owns this format; tell A and D before changing it.

Parameters: any string may contain $name or ${name} (declared under `params`); $$ is a literal $.
Use ${name} when the placeholder is directly followed by a letter or digit ("${product}Qty").
Call Program.resolved(params) once per run to get a copy with them substituted.

  python -m browseen.program validate programs/buy-item/v1.yaml
  python -m browseen.program schema          # writes programs/program.schema.json
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

PROGRAMS_DIR = Path("programs")
PARAM_RE = re.compile(r"\$(?:(\$)|\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))")  # $$, ${name}, $name


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")  # a typo in a YAML key fails loudly


def _one_of(model: BaseModel, kinds: tuple[str, ...]) -> str:
    """The single field in `kinds` that is set; raises if none or several are."""
    present = [k for k in kinds if getattr(model, k) is not None]
    if len(present) != 1:
        raise ValueError(f"{type(model).__name__} needs exactly one of {', '.join(kinds)}; got {present or 'none'}")
    return present[0]


class Param(_Model):
    type: Literal["string", "integer", "number", "boolean"] = "string"
    example: str | int | float | bool | None = None
    description: str = ""


LOCATOR_KINDS = ("testid", "role", "label", "placeholder", "text", "css", "xpath")


class Locator(_Model):
    """One way to find an element. Exactly one kind is set.

    `name` only goes with `role`; `exact` goes with role, label, placeholder or text.
    `xpath` must be absolute (/html/...); Browser Use records it without the leading slash.
    """

    testid: str | None = None
    role: str | None = None
    name: str | None = None
    label: str | None = None
    placeholder: str | None = None
    text: str | None = None
    css: str | None = None
    xpath: str | None = None
    exact: bool | None = None

    @model_validator(mode="after")
    def _check(self) -> Locator:
        kind = _one_of(self, LOCATOR_KINDS)
        if self.name is not None and kind != "role":
            raise ValueError("`name` is only allowed with `role`")
        if self.exact is not None and kind not in ("role", "label", "placeholder", "text"):
            raise ValueError("`exact` is only allowed with role, label, placeholder or text")
        return self

    @property
    def kind(self) -> str:
        return _one_of(self, LOCATOR_KINDS)

    def to_playwright(self, page: Any) -> Any:
        """The Playwright locator for this. `page` can be a Page, Frame or Locator."""
        kind = self.kind
        if kind == "testid":
            return page.get_by_test_id(self.testid)
        if kind == "role":
            return page.get_by_role(self.role, name=self.name, exact=self.exact)
        if kind == "label":
            return page.get_by_label(self.label, exact=self.exact)
        if kind == "placeholder":
            return page.get_by_placeholder(self.placeholder, exact=self.exact)
        if kind == "text":
            return page.get_by_text(self.text, exact=self.exact)
        if kind == "css":
            return page.locator(self.css)
        return page.locator(f"xpath={self.xpath}")

    def describe(self) -> str:
        """Short form for logs, events and diffs, e.g. role=button[name="Add to cart"]."""
        if self.kind == "role":
            return f'role={self.role}[name="{self.name}"]' if self.name is not None else f"role={self.role}"
        return f"{self.kind}={getattr(self, self.kind)}"


class Fingerprint(_Model):
    """What the element looked like when recorded. Tier-1 healing fuzzy-matches against it."""

    tag: str
    role: str | None = None
    name: str | None = None
    attributes: dict[str, str] = Field(default_factory=dict)
    xpath: str | None = None
    near: str | None = None  # nearby heading or label text, if known


class Target(_Model):
    locators: list[Locator] = Field(min_length=1)  # tried in order
    fingerprint: Fingerprint | None = None


ActionType = Literal["navigate", "click", "fill", "select", "check", "uncheck", "press", "extract"]
_REQUIRED_ACTION_FIELD = {"navigate": "url", "fill": "value", "select": "value", "press": "key", "extract": "into"}


class Action(_Model):
    type: ActionType
    value: str | None = None  # fill / select
    url: str | None = None  # navigate
    key: str | None = None  # press, e.g. "Enter"
    into: str | None = None  # extract: name of the output variable

    @model_validator(mode="after")
    def _check(self) -> Action:
        needed = _REQUIRED_ACTION_FIELD.get(self.type)
        if needed and getattr(self, needed) is None:
            raise ValueError(f"action `{self.type}` needs `{needed}`")
        return self


CHECK_KINDS = ("url_matches", "text_visible", "exists", "absent", "target_unique", "target_enabled", "target_value")


class Check(_Model):
    """One condition on the page. Exactly one kind is set.

    The target_* kinds refer to the step's own target, so they can't be used without one
    (and never in the program's `success` list).
    """

    url_matches: str | None = None  # regex, searched in the page URL
    text_visible: str | None = None  # this text is visible somewhere on the page
    exists: Locator | None = None  # at least one element matches
    absent: Locator | None = None  # no element matches (e.g. a popup is gone)
    target_unique: Literal[True] | None = None  # the step's target matches exactly one element
    target_enabled: Literal[True] | None = None
    target_value: str | None = None  # the step's target (an input) has this value

    @model_validator(mode="after")
    def _check(self) -> Check:
        _one_of(self, CHECK_KINDS)
        if self.url_matches is not None:
            re.compile(self.url_matches)
        return self

    @property
    def kind(self) -> str:
        return _one_of(self, CHECK_KINDS)

    @property
    def uses_target(self) -> bool:
        return self.kind.startswith("target_")


class Step(_Model):
    id: str = Field(pattern=r"^s\d+[a-z]?$")  # s1, s2, …; heals may insert s4a
    intent: str
    action: Action
    target: Target | None = None
    when: Check | None = None  # optional step: skipped unless this check passes
    pre: list[Check] = Field(default_factory=list)
    post: list[Check] = Field(default_factory=list)
    timeout_ms: int = Field(default=5000, gt=0)

    @model_validator(mode="after")
    def _check(self) -> Step:
        if self.target is None and self.action.type not in ("navigate", "press"):
            raise ValueError(f"step {self.id}: action `{self.action.type}` needs a target")
        checks = [self.when, *self.pre, *self.post]
        if self.target is None and any(c is not None and c.uses_target for c in checks):
            raise ValueError(f"step {self.id}: target_* checks need a target")
        return self


class Change(_Model):
    """One entry in a program's history: how this version came to be."""

    version: int = Field(ge=1)
    source: Literal["recorded", "compiled", "healed", "manual"]
    step: str | None = None
    tier: Literal[1, 2, 3] | None = None
    reason: str = ""
    at: datetime | None = None


class Program(_Model):
    program: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    version: int = Field(ge=1)
    task: str
    start_url: str
    params: dict[str, Param] = Field(default_factory=dict)
    steps: list[Step] = Field(min_length=1)
    success: list[Check] = Field(default_factory=list)
    history: list[Change] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self) -> Program:
        ids = [s.id for s in self.steps]
        if dupes := sorted({i for i in ids if ids.count(i) > 1}):
            raise ValueError(f"duplicate step ids: {dupes}")
        if any(c.uses_target for c in self.success):
            raise ValueError("success checks can't use target_* kinds")
        if undeclared := sorted(_param_refs(self._templated()) - set(self.params)):
            raise ValueError(f"undeclared params: {undeclared} (declare them under `params`)")
        return self

    def _templated(self) -> dict[str, Any]:
        """The parts of the program where $params are substituted."""
        return self.model_dump(mode="json", include={"task", "start_url", "steps", "success"})

    def step(self, step_id: str) -> Step:
        return next(s for s in self.steps if s.id == step_id)

    def resolved(self, params: dict[str, Any]) -> Program:
        """A copy with every $param replaced by its value. Call once per run."""
        if missing := sorted(set(self.params) - set(params)):
            raise KeyError(f"missing params: {missing}")
        if unknown := sorted(set(params) - set(self.params)):
            raise KeyError(f"unknown params: {unknown}")
        values = {k: _as_text(v) for k, v in params.items()}
        data = self.model_dump(mode="json")
        data.update(_substitute(self._templated(), values))
        return Program.model_validate(data)

    def bump(self, *, source: str, reason: str, step: str | None = None, tier: int | None = None) -> Program:
        """A copy with the next version number and a history entry. Edit the copy, then save() it."""
        new = self.model_copy(deep=True)
        new.version += 1
        new.history.append(
            Change(version=new.version, source=source, step=step, tier=tier, reason=reason,
                   at=datetime.now(timezone.utc).replace(microsecond=0))
        )
        return new

    def to_yaml(self) -> str:
        data = _drop_empty(self.model_dump(mode="json", exclude_none=True))
        return yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=120)


def _strings(obj: Any) -> Iterator[str]:
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)


def _param_refs(obj: Any) -> set[str]:
    return {m.group(2) or m.group(3) for s in _strings(obj) for m in PARAM_RE.finditer(s) if not m.group(1)}


def _as_text(value: Any) -> str:
    return str(value).lower() if isinstance(value, bool) else str(value)


def param_refs(text: str) -> set[str]:
    """The $params used in a string."""
    return _param_refs(text)


def substitute(text: str, values: dict[str, Any]) -> str:
    """Fill $params in one string ($$ becomes $). Raises KeyError for a param with no value."""
    return _substitute(text, {k: _as_text(v) for k, v in values.items()})


def _substitute(obj: Any, values: dict[str, str]) -> Any:
    if isinstance(obj, str):
        return PARAM_RE.sub(lambda m: "$" if m.group(1) else values[m.group(2) or m.group(3)], obj)
    if isinstance(obj, dict):
        return {k: _substitute(v, values) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_substitute(v, values) for v in obj]
    return obj


def _drop_empty(obj: Any) -> Any:
    """Leave empty lists, dicts and strings out of the YAML, so files stay short."""
    if isinstance(obj, dict):
        return {k: _drop_empty(v) for k, v in obj.items() if v not in ([], {}, "")}
    if isinstance(obj, list):
        return [_drop_empty(v) for v in obj]
    return obj


def program_path(name: str, version: int, root: Path = PROGRAMS_DIR) -> Path:
    return Path(root) / name / f"v{version}.yaml"


def load(path: str | Path) -> Program:
    return Program.model_validate(yaml.safe_load(Path(path).read_text()))


def save(program: Program, root: Path = PROGRAMS_DIR) -> Path:
    """Write programs/<name>/v<N>.yaml. Refuses to overwrite: bump() first."""
    path = program_path(program.program, program.version, root)
    if path.exists():
        raise FileExistsError(f"{path} already exists; versions are append-only, so bump() first")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(program.to_yaml())
    return path


def versions(name: str, root: Path = PROGRAMS_DIR) -> list[int]:
    found = (re.fullmatch(r"v(\d+)\.yaml", p.name) for p in (Path(root) / name).glob("v*.yaml"))
    return sorted(int(m.group(1)) for m in found if m)


def latest(name: str, root: Path = PROGRAMS_DIR) -> Program:
    if not (found := versions(name, root)):
        raise FileNotFoundError(f"no versions of {name!r} under {root}")
    return load(program_path(name, found[-1], root))


def rollback(name: str, to: int, root: Path = PROGRAMS_DIR) -> Program:
    """Save the next version as a copy of v`to`. Versions are append-only, so nothing is deleted."""
    current = latest(name, root)
    if to not in versions(name, root):
        raise FileNotFoundError(f"{name} has no v{to}; versions: {versions(name, root)}")
    if to == current.version:
        raise ValueError(f"v{to} is already the latest version of {name}")
    new = load(program_path(name, to, root)).model_copy(deep=True)
    new.version = current.version + 1
    new.history = [*current.history, Change(version=new.version, source="manual", reason=f"rollback to v{to}",
                                            at=datetime.now(timezone.utc).replace(microsecond=0))]
    save(new, root)
    return new


def diff(a: Program, b: Program) -> str:
    """Unified diff of two versions in normalized YAML, so formatting differences don't show."""
    return "".join(difflib.unified_diff(
        a.to_yaml().splitlines(keepends=True), b.to_yaml().splitlines(keepends=True),
        fromfile=f"{a.program}/v{a.version}", tofile=f"{b.program}/v{b.version}"))


def changed_steps(a: Program, b: Program) -> dict[str, list[str]]:
    """Step ids added, removed or changed between two versions."""
    old = {s.id: s for s in a.steps}
    new = {s.id: s for s in b.steps}
    return {
        "added": [i for i in new if i not in old],
        "removed": [i for i in old if i not in new],
        "changed": [i for i in new if i in old and new[i] != old[i]],
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m browseen.program")
    sub = parser.add_subparsers(dest="cmd", required=True)
    check = sub.add_parser("validate", help="check program files against the format")
    check.add_argument("files", nargs="+", type=Path)
    schema = sub.add_parser("schema", help="write the JSON Schema (for the dashboard's types)")
    schema.add_argument("--out", type=Path, default=PROGRAMS_DIR / "program.schema.json")
    args = parser.parse_args(argv)

    if args.cmd == "schema":
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(Program.model_json_schema(), indent=2) + "\n")
        print(f"wrote {args.out}")
        return

    failed = 0
    for path in args.files:
        try:
            prog = load(path)
        except (OSError, yaml.YAMLError, ValidationError) as e:
            failed += 1
            print(f"FAIL {path}\n{e}\n")
            continue
        print(f"ok   {path}: {prog.program} v{prog.version}, {len(prog.steps)} steps, params {list(prog.params)}")
        for s in prog.steps:
            first = s.target.locators[0].describe() if s.target else ""
            optional = "  (optional)" if s.when else ""
            print(f"     {s.id:<4} {s.action.type:<8} {first:<40} {s.intent}{optional}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
