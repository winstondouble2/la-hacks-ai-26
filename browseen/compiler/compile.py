"""Turn a recorded trace into a program.

v0 is deterministic. v1 adds one LLM pass (annotate.py) for intents, optional steps,
param descriptions and the success text; without it the v0 output is used as is.

  normalize  Browser Use actions -> the actions worth replaying (with a reason for each drop)
  locators   candidates verified on the recorded page (locators.py)
  params     recorded input values -> $params (params.py)
  checks     pre: page URL, target unique/enabled; post: field value, URL change, text that
             names an input (this is what catches a wrong-item click); success: the final page
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from browseen.compiler.annotate import LLMResult, StepContext
from browseen.compiler.locators import PageAnalyzer, fingerprint_attrs
from browseen.compiler.params import mentions_input, param_type, templatize, url_path, url_pattern
from browseen.program import Action, Change, Check, Fingerprint, Locator, Param, Program, Step, Target, save
from browseen.recorder.trace import Trace, TraceAction, TraceStep

ACTIONS = {"navigate": "navigate", "click": "click", "input": "fill", "select_dropdown": "select", "send_keys": "press"}
NEEDS_ELEMENT = {"click", "fill", "select"}
DROPPED = {
    "done": "the agent's own finish (success is checked instead)",
    "wait": "waiting is handled by the checks",
    "scroll": "Playwright scrolls to each target itself",
    "find_text": "read-only", "search_page": "read-only", "find_elements": "read-only",
    "dropdown_options": "read-only", "screenshot": "read-only", "save_as_pdf": "read-only",
    "read_file": "file tool", "write_file": "file tool", "replace_file": "file tool",
}
MAX_NEW_TEXT = 80


@dataclass
class ReportLine:
    trace_step: int
    action: str
    outcome: str  # kept | dropped | unsupported
    detail: str = ""


@dataclass
class CompileReport:
    run_id: str
    lines: list[ReportLine] = field(default_factory=list)
    locators: dict[str, list[str]] = field(default_factory=dict)  # program step id -> verdict per candidate
    warnings: list[str] = field(default_factory=list)
    llm: LLMResult | None = None

    def add(self, step: TraceStep, action: TraceAction, outcome: str, detail: str = "") -> None:
        self.lines.append(ReportLine(step.number, action.name, outcome, detail))

    def render(self) -> str:
        out = [f"compile report for {self.run_id}"]
        for line in sorted(self.lines, key=lambda line: line.trace_step):  # stable: keeps action order
            out.append(f"  trace step {line.trace_step:<2} {line.action:<16} {line.outcome:<11} {line.detail}")
            if line.outcome == "kept" and (verdicts := self.locators.get(line.detail.split()[0])):
                out.extend(f"      {v}" for v in verdicts)
        if self.llm:
            u = self.llm.usage
            status = "used" if self.llm.annotation else "not used"
            note = f", {self.llm.note}" if self.llm.note else ""
            out.append(f"  LLM pass ({status}): {self.llm.model}, {u.tokens:,} tokens, ${u.usd:.4f}{note}")
        out.extend(f"  warning: {w}" for w in self.warnings)
        return "\n".join(out)


@dataclass
class Kept:
    step: TraceStep
    action: TraceAction
    type: str
    last_in_step: bool
    only_in_step: bool


def _read(run_dir: Path, rel: str | None) -> str | None:
    return (run_dir / rel).read_text() if rel and (run_dir / rel).exists() else None


def normalize(trace: Trace, run_dir: Path, report: CompileReport) -> list[Kept]:
    """The actions worth replaying, in order. Every dropped action gets a reason in the report."""
    kept: list[Kept] = []
    for step in trace.steps:
        for i, action in enumerate(step.actions):
            if step.number == 0 and action.name == "navigate":
                report.add(step, action, "dropped", "initial navigation (the program's start_url)")
            elif action.error:
                report.add(step, action, "dropped", f"failed: {action.error[:80]}")
            elif action.name in DROPPED:
                report.add(step, action, "dropped", DROPPED[action.name])
            elif action.name == "extract":
                report.add(step, action, "dropped", "extraction isn't compiled yet")
                report.warnings.append(f"trace step {step.number}: extract dropped; the program won't return that data")
            elif action.name not in ACTIONS or (ACTIONS[action.name] in NEEDS_ELEMENT and action.element is None):
                why = "no element (coordinate click?)" if action.name in ACTIONS else "not supported by compiler v0"
                report.add(step, action, "unsupported", why)
                report.warnings.append(f"trace step {step.number}: {action.name} skipped ({why}); the program may not replay")
            else:
                kept.append(Kept(step, action, ACTIONS[action.name], i == len(step.actions) - 1, len(step.actions) == 1))

    merged: list[Kept] = []
    for k in kept:
        prev = merged[-1] if merged else None
        if prev and k.type == prev.type == "fill" and k.action.element.xpath == prev.action.element.xpath:
            report.add(prev.step, prev.action, "dropped", "superseded by a later input into the same field")
            merged[-1] = k
        else:
            merged.append(k)

    final: list[Kept] = []
    for k in merged:
        before, after = _read(run_dir, k.step.html_before), _read(run_dir, k.step.html_after)
        if (k.type == "click" and k.only_in_step and before is not None and before == after
                and url_path(k.step.url) == url_path(k.step.url_after)):
            report.add(k.step, k.action, "dropped", "the click changed nothing (a mis-click)")
        else:
            final.append(k)
    return final


def _templated(locator: Locator, inputs: dict[str, Any]) -> Locator:
    """Put $params into a verified locator's text fields; never into CSS or XPath."""
    data = locator.model_dump(exclude_none=True)
    for key in ("name", "label", "text", "placeholder"):
        if key in data:
            data[key] = templatize(data[key], inputs)
    return Locator(**data)


def _intent(k: Kept, role: str | None, name: str | None, action: Action, inputs: dict[str, Any]) -> str:
    label = f"'{templatize(name, inputs)}'" if name else f"the {k.action.element.tag if k.action.element else 'page'}"
    if k.type == "click":
        return f"Open the {label} link" if role == "link" else f"Click {label}"
    if k.type == "fill":
        return f"Enter {action.value} into {label}"
    if k.type == "select":
        return f"Choose {action.value} in {label}"
    if k.type == "press":
        return f"Press {action.key}"
    return f"Go to {action.url}"


def _input_line(lines: list[str], inputs: dict[str, Any]) -> str | None:
    """The shortest text line that names a recorded input, e.g. '2 × Blue Mug'."""
    hits = [line for line in lines if mentions_input(line, inputs)]
    return min(hits, key=len) if hits else None


def _effect_checks(k: Kept, pa: PageAnalyzer, run_dir: Path, inputs: dict[str, Any], report: CompileReport,
                   step_id: str, target_locator: Locator | None = None) -> list[Check]:
    """Post-checks for what a click / key press / navigation did to the page.

    `target_locator` is the step's first verified locator (recorded literals, not $params).
    """
    checks: list[Check] = []
    changed_url = k.step.url_after and url_path(k.step.url) != url_path(k.step.url_after)
    if changed_url:
        checks.append(Check(url_matches=url_pattern(k.step.url_after)))
    after = _read(run_dir, k.step.html_after)
    if after is None:
        return checks
    pa.load(after)
    after_lines = pa.text_lines()
    named = _input_line(after_lines, inputs)
    # A click that made its own target go away (dismissing a banner or popup).
    target_gone = target_locator is not None and target_locator.to_playwright(pa.page).count() == 0
    if changed_url:
        if named:
            checks.append(Check(text_visible=templatize(named, inputs)))
        return checks
    before = _read(run_dir, k.step.html_before)
    before_lines = set()
    if before is not None:
        pa.load(before)
        before_lines = set(pa.text_lines())
    new = [line for line in after_lines if line not in before_lines and len(line) <= MAX_NEW_TEXT]
    if named and named in new:
        checks.append(Check(text_visible=templatize(named, inputs)))
    elif new:
        checks.append(Check(text_visible=templatize(new[0], inputs)))
    elif target_gone:
        checks.append(Check(absent=_templated(target_locator, inputs)))
    else:
        report.warnings.append(f"{step_id}: no visible effect recorded, so no post-check")
    return checks


def _success(trace: Trace, pa: PageAnalyzer, run_dir: Path, inputs: dict[str, Any]) -> tuple[list[Check], list[str]]:
    """The success checks, plus the final page's text lines (the LLM pass picks from them)."""
    final = next((s for s in reversed(trace.steps) if s.html_after), None)
    if final is None:
        return [], []
    pa.load(_read(run_dir, final.html_after) or "")
    lines = pa.text_lines()
    line = _input_line(pa.headings(), inputs) or _input_line(lines, inputs)
    if line:
        return [Check(text_visible=templatize(line, inputs))], lines
    url = final.url_after or final.url
    return ([Check(url_matches=url_pattern(url))] if url else []), lines


Annotator = Callable[..., tuple[Program, LLMResult]]


def compile_trace(trace: Trace, run_dir: Path, name: str,
                  annotate_with: Annotator | None = None) -> tuple[Program, CompileReport]:
    """Compile a trace. Pass annotate_with=annotate for the v1 LLM pass."""
    run_dir = Path(run_dir)
    report = CompileReport(trace.run_id)
    inputs = trace.inputs
    kept = normalize(trace, run_dir, report)
    if not kept:
        raise ValueError("nothing to compile: no replayable actions in the trace")

    steps: list[Step] = []
    contexts: list[StepContext] = []
    with PageAnalyzer() as pa:
        for index, k in enumerate(kept, 1):
            step_id = f"s{index}"
            params = k.action.params
            if k.type == "click":
                action = Action(type="click")
            elif k.type in ("fill", "select"):
                action = Action(type=k.type, value=templatize(str(params.get("text", "")), inputs))
            elif k.type == "press":
                action = Action(type="press", key=str(params.get("keys", "")))
            else:
                action = Action(type="navigate", url=templatize(str(params.get("url", "")), inputs))

            target, role, el_name, container, pre, post = None, None, None, None, [], []
            first_literal: Locator | None = None
            if k.type in NEEDS_ELEMENT:
                el = k.action.element
                found = False
                for html in (_read(run_dir, k.step.html_before), _read(run_dir, k.step.html_after)):
                    if html is not None:
                        pa.load(html)
                        if found := pa.has(el.xpath):
                            break
                if not found:
                    report.warnings.append(f"{step_id}: recorded element not found on the saved page; XPath only")
                    locators, role, el_name = [Locator(xpath=el.xpath)], None, el.ax_name
                    report.locators[step_id] = [f"? {el.xpath} (unverified)"]
                else:
                    role, el_name, candidates = pa.candidates(el)
                    container = pa.container(el.xpath)
                    locators = [_templated(c.locator, inputs) for c in candidates if c.kept]
                    first_literal = next((c.locator for c in candidates if c.kept and not c.locator.xpath), None)
                    report.locators[step_id] = [
                        f"{'✓' if c.kept else '✗'} {c.locator.describe()}"
                        + ("" if c.kept else f"  ({c.matches} matches{'' if c.is_target or not c.matches else ', not the recorded element'})")
                        for c in candidates]
                target = Target(locators=locators, fingerprint=Fingerprint(
                    tag=el.tag, role=role, name=el_name or el.ax_name, attributes=fingerprint_attrs(el), xpath=el.xpath))
                if k.step.url:
                    pre.append(Check(url_matches=url_pattern(k.step.url)))
                pre.append(Check(target_unique=True))
                if k.type == "click":
                    pre.append(Check(target_enabled=True))
                else:
                    post.append(Check(target_value=action.value))

            if k.type in ("click", "press", "navigate") and k.last_in_step:
                post.extend(_effect_checks(k, pa, run_dir, inputs, report, step_id, first_literal))

            intent = _intent(k, role, el_name, action, inputs)
            steps.append(Step(id=step_id, intent=intent, action=action, target=target, pre=pre, post=post))
            report.add(k.step, k.action, "kept", f"{step_id} {k.type}: {intent}")
            contexts.append(StepContext(
                id=step_id, action=k.type, value=action.value, role=role,
                name=templatize(el_name, inputs) if el_name else None, page=url_path(k.step.url),
                agent_goal=templatize(k.step.goal, inputs) if k.step.goal else None,
                container=container, intent=intent))

        success, final_lines = _success(trace, pa, run_dir, inputs)

    program = Program(
        program=name, version=1, task=trace.task_template, start_url=trace.start_url,
        params={k: Param(type=param_type(v), example=v) for k, v in inputs.items()},
        steps=steps, success=success,
        history=[Change(version=1, source="compiled", reason=f"compiled from {trace.run_id} (compiler v0, no LLM)",
                        at=datetime.now(timezone.utc).replace(microsecond=0))],
    )
    if annotate_with is not None:
        program, report.llm = annotate_with(program, contexts, final_lines, inputs, report.warnings)
        if report.llm.annotation is not None:
            program.history[0].reason = f"compiled from {trace.run_id} (compiler v1: 1 LLM pass)"
    return program, report


def compile_run(run_dir: Path, name: str, programs_dir: Path, *, dry_run: bool = False,
                annotate_with: Annotator | None = None) -> tuple[Program, CompileReport, Path | None]:
    """Compile runs/<run_id>/ into programs/<name>/v1.yaml. Refuses an existing program folder."""
    from browseen.recorder.trace import load_trace

    if (Path(programs_dir) / name).exists():
        raise FileExistsError(f"{Path(programs_dir) / name} already exists; pick another --name")
    program, report = compile_trace(load_trace(run_dir), Path(run_dir), name, annotate_with)
    path = None if dry_run else save(program, programs_dir)
    return program, report, path
