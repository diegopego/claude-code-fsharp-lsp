"""bump_version.py bumps the plugin's semver in .claude-plugin/plugin.json with a
minimal in-place edit — it must preserve every other byte of the file, because a
release commit that reformats the manifest is noise. Driven as a subprocess: the
Makefile's release target relies on the new version being printed to stdout."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / ".claude" / "skills" / "maintain-docs" / "bump_version.py"

# A manifest with distinctive surrounding formatting the bump must not disturb.
MANIFEST = (
    '{\n'
    '  "name": "fsharp-lsp",\n'
    '  "version": "2.1.0",\n'
    '  "keywords": ["fsharp", "dotnet"]\n'
    '}\n'
)


def _run(plugin_json: Path, level: str):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--level", level, "--file", str(plugin_json)],
        capture_output=True, text=True, timeout=30)


def _bump(tmp_path, level: str):
    f = tmp_path / "plugin.json"
    f.write_text(MANIFEST, encoding="utf-8")
    r = _run(f, level)
    return r, f


def test_patch_bumps_the_last_component(tmp_path):
    r, f = _bump(tmp_path, "patch")
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.strip() == "2.1.1"
    assert '"version": "2.1.1"' in f.read_text(encoding="utf-8")


def test_minor_bumps_and_zeroes_patch(tmp_path):
    r, f = _bump(tmp_path, "minor")
    assert r.stdout.strip() == "2.2.0"
    assert '"version": "2.2.0"' in f.read_text(encoding="utf-8")


def test_major_bumps_and_zeroes_the_rest(tmp_path):
    r, f = _bump(tmp_path, "major")
    assert r.stdout.strip() == "3.0.0"
    assert '"version": "3.0.0"' in f.read_text(encoding="utf-8")


def test_only_the_version_line_changes(tmp_path):
    _, f = _bump(tmp_path, "patch")
    after = f.read_text(encoding="utf-8")
    # Every line except the version line is byte-identical, and count is unchanged.
    before_lines = MANIFEST.splitlines()
    after_lines = after.splitlines()
    assert len(before_lines) == len(after_lines)
    differing = [i for i, (a, b) in enumerate(zip(before_lines, after_lines)) if a != b]
    assert differing == [2], f"only the version line (index 2) should change, got {differing}"


def test_errors_when_no_semver_field(tmp_path):
    f = tmp_path / "plugin.json"
    f.write_text('{\n  "name": "fsharp-lsp"\n}\n', encoding="utf-8")
    r = _run(f, "patch")
    assert r.returncode != 0
    assert "version" in (r.stdout + r.stderr).lower()
