"""conflict_check.py warns when fsharp-lsp is installed from more than one source
(marketplace). Two installs register the .fs LSP server twice and spawn two
fsautocomplete processes — a real failure this repo has seen (HANDOFF.md: one
FSAC reached 5.4 GB). install-dev-plugin runs this first and refuses on a conflict.

A conflict is 2+ distinct marketplaces for the same plugin name. The same plugin
under two SCOPES of one marketplace is not a conflict — it is one registration."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / ".claude" / "skills" / "maintain-docs" / "conflict_check.py"


def _run(installed: dict, tmp_path):
    f = tmp_path / "installed_plugins.json"
    f.write_text(json.dumps(installed), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--installed-json", str(f)],
        capture_output=True, text=True, timeout=30)


def test_single_marketplace_is_no_conflict(tmp_path):
    r = _run({"plugins": {
        "fsharp-lsp@claude-code-fsharp-lsp": [{"scope": "local"}]}}, tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr


def test_two_scopes_of_one_marketplace_is_no_conflict(tmp_path):
    # project + local of the SAME marketplace is one registration, not a conflict.
    r = _run({"plugins": {"fsharp-lsp@claude-code-fsharp-lsp": [
        {"scope": "project"}, {"scope": "local"}]}}, tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr


def test_two_marketplaces_is_a_conflict(tmp_path):
    r = _run({"plugins": {
        "fsharp-lsp@claude-code-fsharp-lsp": [{"scope": "local"}],
        "fsharp-lsp@fsharp-lsp-local": [{"scope": "user"}],
    }}, tmp_path)
    assert r.returncode != 0
    out = (r.stdout + r.stderr).lower()
    assert "claude-code-fsharp-lsp" in out and "fsharp-lsp-local" in out


def test_not_installed_is_no_conflict(tmp_path):
    r = _run({"plugins": {}}, tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr


def test_other_plugins_are_ignored(tmp_path):
    r = _run({"plugins": {
        "typescript-lsp@official": [{}],
        "some-plugin@other-marketplace": [{}],
        "fsharp-lsp@claude-code-fsharp-lsp": [{"scope": "local"}],
    }}, tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
