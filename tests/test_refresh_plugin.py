"""refresh_plugin.py pushes the working tree's plugin files into the active
installed copy, so an unpublished change reaches the running plugin without a
version bump. It is the inverse of check_plugin_current.py: the gate detects a
stale copy, this makes the copy current.

Driven as a subprocess, and one test proves the pair are duals — after a refresh
the gate goes green."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / ".claude" / "skills" / "maintain-docs"
REFRESH = SKILL / "refresh_plugin.py"
GATE = SKILL / "check_plugin_current.py"


def _working_tree(base: Path, marker: str) -> Path:
    base.mkdir(parents=True, exist_ok=True)
    (base / ".lsp.json").write_text(f'{{"fsharp": {{"{marker}": true}}}}', encoding="utf-8")
    (base / "skills" / "fsharp-code-intelligence").mkdir(parents=True)
    (base / "skills" / "fsharp-code-intelligence" / "SKILL.md").write_text(marker, encoding="utf-8")
    (base / "tools").mkdir()
    (base / "tools" / "check_fsharp_lsp.py").write_text(f"# {marker}\n", encoding="utf-8")
    (base / ".claude-plugin").mkdir()
    (base / ".claude-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
    (base / "hooks").mkdir()
    (base / "hooks" / "hooks.json").write_text("{}", encoding="utf-8")
    # scaffolding that must NOT be pushed into the plugin install
    (base / ".git").mkdir()
    (base / ".git" / "HEAD").write_text("ref", encoding="utf-8")
    (base / "tests").mkdir()
    (base / "tests" / "junk.py").write_text("x", encoding="utf-8")
    return base


def _run(args):
    return subprocess.run([sys.executable, str(REFRESH), *args],
                          capture_output=True, text=True, timeout=60)


def test_sync_into_dest_replaces_stale_plugin_files(tmp_path):
    wt = _working_tree(tmp_path / "repo", "fresh")
    dest = tmp_path / "cache" / "claude-code-fsharp-lsp" / "fsharp-lsp" / "2.1.0"
    dest.mkdir(parents=True)
    (dest / ".lsp.json").write_text('{"fsharp": {"stale": true}}', encoding="utf-8")
    (dest / "skills" / "fsharp-code-intelligence").mkdir(parents=True)
    (dest / "skills" / "fsharp-code-intelligence" / "SKILL.md").write_text("stale", encoding="utf-8")

    r = _run(["--working-tree", str(wt), "--dest", str(dest)])
    assert r.returncode == 0, r.stdout + r.stderr
    assert (dest / ".lsp.json").read_text() == '{"fsharp": {"fresh": true}}'
    assert (dest / "skills" / "fsharp-code-intelligence" / "SKILL.md").read_text() == "fresh"
    assert (dest / "tools" / "check_fsharp_lsp.py").read_text() == "# fresh\n"
    # scaffolding is not pushed into the plugin install
    assert not (dest / ".git").exists()
    assert not (dest / "tests").exists()


def test_after_sync_the_gate_is_green(tmp_path):
    """The whole point: refresh makes check_plugin_current.py pass."""
    wt = _working_tree(tmp_path / "repo", "fresh")
    dest = tmp_path / "cache" / "claude-code-fsharp-lsp" / "fsharp-lsp" / "2.1.0"
    dest.mkdir(parents=True)
    _run(["--working-tree", str(wt), "--dest", str(dest)])
    gate = subprocess.run(
        [sys.executable, str(GATE),
         "--working-tree", str(wt), "--cache-root", str(tmp_path / "cache")],
        capture_output=True, text=True, timeout=60)
    assert gate.returncode == 0, gate.stdout + gate.stderr


def test_discovers_install_path_from_installed_json(tmp_path):
    wt = _working_tree(tmp_path / "repo", "fresh")
    dest = tmp_path / "cache" / "mp" / "fsharp-lsp" / "2.1.0"
    dest.mkdir(parents=True)
    installed = tmp_path / "installed_plugins.json"
    installed.write_text(json.dumps({"plugins": {
        "fsharp-lsp@some-marketplace": [{"installPath": str(dest)}]}}), encoding="utf-8")
    r = _run(["--working-tree", str(wt), "--installed-json", str(installed)])
    assert r.returncode == 0, r.stdout + r.stderr
    assert (dest / ".lsp.json").read_text() == '{"fsharp": {"fresh": true}}'


def test_duplicate_scopes_sync_the_shared_path_once(tmp_path):
    """project and local scopes commonly list the same installPath; it must be
    synced once, not once per scope."""
    wt = _working_tree(tmp_path / "repo", "fresh")
    dest = tmp_path / "cache" / "mp" / "fsharp-lsp" / "2.1.0"
    dest.mkdir(parents=True)
    installed = tmp_path / "installed_plugins.json"
    installed.write_text(json.dumps({"plugins": {"fsharp-lsp@mp": [
        {"scope": "project", "installPath": str(dest)},
        {"scope": "local", "installPath": str(dest)},
    ]}}), encoding="utf-8")
    r = _run(["--working-tree", str(wt), "--installed-json", str(installed)])
    assert r.returncode == 0, r.stdout + r.stderr
    assert (r.stdout + r.stderr).count("synced") == 1


def test_nonzero_when_no_install_is_found(tmp_path):
    wt = _working_tree(tmp_path / "repo", "fresh")
    installed = tmp_path / "installed_plugins.json"
    installed.write_text(json.dumps({"plugins": {}}), encoding="utf-8")
    r = _run(["--working-tree", str(wt), "--installed-json", str(installed)])
    assert r.returncode != 0
    assert "no installed" in (r.stdout + r.stderr).lower()
