"""The gate that refuses to capture evidence from a plugin that is not the
working tree. It compares content hashes, not version numbers, because a
version check waves through 'edited the skill, forgot to reinstall'.

Driven as a subprocess: the exit code is the contract the skill depends on."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / ".claude" / "skills" / "maintain-docs" / "check_plugin_current.py"


def _plugin_tree(base: Path, lsp_body: str):
    """Write a minimal plugin layout: .lsp.json + skills/ + tools/."""
    base.mkdir(parents=True, exist_ok=True)
    (base / ".lsp.json").write_text(lsp_body, encoding="utf-8")
    (base / "skills").mkdir(exist_ok=True)
    (base / "skills" / "SKILL.md").write_text("skill\n", encoding="utf-8")
    (base / "tools").mkdir(exist_ok=True)
    (base / "tools" / "t.py").write_text("print(1)\n", encoding="utf-8")
    return base


def _run(working_tree: Path, cache_root: Path):
    return subprocess.run(
        [sys.executable, str(SCRIPT),
         "--working-tree", str(working_tree),
         "--cache-root", str(cache_root)],
        capture_output=True, text=True, timeout=60,
    )


def test_exit_zero_when_an_installed_copy_matches(tmp_path):
    wt = _plugin_tree(tmp_path / "wt", '{"fsharp": {}}')
    _plugin_tree(
        tmp_path / "cache" / "some-marketplace" / "fsharp-lsp" / "2.1.0",
        '{"fsharp": {}}')
    r = _run(wt, tmp_path / "cache")
    assert r.returncode == 0, r.stdout + r.stderr


def test_exit_two_when_content_differs(tmp_path):
    wt = _plugin_tree(tmp_path / "wt", '{"fsharp": {"changed": true}}')
    _plugin_tree(
        tmp_path / "cache" / "some-marketplace" / "fsharp-lsp" / "2.1.0",
        '{"fsharp": {}}')  # older content
    r = _run(wt, tmp_path / "cache")
    assert r.returncode == 2
    assert "restart" in (r.stdout + r.stderr).lower()


def test_exit_two_when_nothing_is_installed(tmp_path):
    wt = _plugin_tree(tmp_path / "wt", '{"fsharp": {}}')
    (tmp_path / "cache").mkdir()
    r = _run(wt, tmp_path / "cache")
    assert r.returncode == 2
    assert "install" in (r.stdout + r.stderr).lower()
