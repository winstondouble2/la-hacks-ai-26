"""The python -m browseen command line (no API calls, no live browser except compile)."""

import importlib.machinery
import importlib.util
import shutil
import sys
import types
from pathlib import Path

import pytest

from browseen import cli
from browseen import program as P

ROOT = Path(__file__).resolve().parents[1]
PROGRAMS = ROOT / "programs"
RUN = ROOT / "tests" / "fixtures" / "run_mini_shop"
PARAMS = ["--param", "product=Red Kettle", "--param", "qty=1", "--param", "name=Alan Turing", "--param", "address=9 Elm Ave"]


@pytest.fixture
def programs(tmp_path):
    shutil.copytree(PROGRAMS / "buy-item", tmp_path / "buy-item")
    shutil.copytree(PROGRAMS / "mini-shop", tmp_path / "mini-shop")
    return tmp_path


def test_diff_shows_only_real_changes(programs, capsys):
    assert cli.main(["diff", "buy-item", "--programs-dir", str(programs)]) == 0
    out = capsys.readouterr().out
    assert "buy-item v1 → v2  (changed: s4)" in out
    assert "-      name: Add to cart" in out and "+      name: Add to bag" in out
    assert "{type: string" not in out  # v1's hand-written flow style doesn't show up as a change


def test_rollback_saves_a_copy_as_the_next_version(programs, capsys):
    assert cli.main(["rollback", "buy-item", "--to", "1", "--programs-dir", str(programs)]) == 0
    assert P.versions("buy-item", programs) == [1, 2, 3]
    v1, v3 = P.load(programs / "buy-item" / "v1.yaml"), P.load(programs / "buy-item" / "v3.yaml")
    assert v3.steps == v1.steps and v3.history[-1].reason == "rollback to v1"
    assert P.changed_steps(v1, v3) == {"added": [], "removed": [], "changed": []}


@pytest.mark.parametrize("to, message", [(9, "has no v9"), (2, "already the latest")])
def test_rollback_errors(programs, to, message):
    with pytest.raises(SystemExit, match=message):
        cli.main(["rollback", "buy-item", "--to", str(to), "--programs-dir", str(programs)])


def test_run_lists_missing_params(programs):
    with pytest.raises(SystemExit, match=r"missing params: \['address', 'name', 'qty'\]. mini-shop takes: --param"):
        cli.main(["run", "mini-shop", "--param", "product=Red Kettle", "--programs-dir", str(programs)])


@pytest.mark.skipif(importlib.util.find_spec("browseen.runtime") is not None, reason="A's runtime is present")
def test_run_without_the_runtime_says_so(programs):
    with pytest.raises(SystemExit, match="runtime isn't on this branch yet"):
        cli.main(["run", "mini-shop", *PARAMS, "--programs-dir", str(programs)])


def test_run_calls_the_runtime_contract(programs, monkeypatch):
    """The contract A implements: browseen.runtime.run_program(program, params, *, headless)."""
    calls = []
    fake = types.ModuleType("browseen.runtime")
    fake.__spec__ = importlib.machinery.ModuleSpec("browseen.runtime", None)
    fake.run_program = lambda program, params, *, headless, **options: calls.append((program, params, headless)) or types.SimpleNamespace(success=True)
    monkeypatch.setitem(sys.modules, "browseen.runtime", fake)

    assert cli.main(["run", "mini-shop", *PARAMS, "--headless", "--programs-dir", str(programs)]) == 0
    program, params, headless = calls[0]
    assert program.program == "mini-shop" and program.version == 1 and headless
    assert params == {"product": "Red Kettle", "qty": 1, "name": "Alan Turing", "address": "9 Elm Ave"}


def test_load_program_by_name_version_or_path(programs):
    assert cli.load_program("buy-item", root=programs).version == 2
    assert cli.load_program("buy-item", 1, root=programs).version == 1
    assert cli.load_program(str(programs / "buy-item" / "v1.yaml")).version == 1
    with pytest.raises(FileNotFoundError):
        cli.load_program("buy-item", 7, root=programs)


def test_show_and_compile(tmp_path, capsys):
    assert cli.main(["show", str(RUN)]) == 0
    assert "6 steps in 29.8s" in capsys.readouterr().out
    assert cli.main(["compile", str(RUN), "--name", "mini-shop", "--no-llm", "--programs-dir", str(tmp_path)]) == 0
    assert P.load(tmp_path / "mini-shop" / "v1.yaml").step("s1").target.locators[0].name == "$product"
