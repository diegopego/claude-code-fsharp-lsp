import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
FAKE = Path(__file__).resolve().parent / "fake_fsac.py"

sys.path.insert(0, str(TOOLS))


@pytest.fixture
def scenario(tmp_path):
    """Write a scenario dict to disk and return its path."""
    def _write(data):
        path = tmp_path / "scenario.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path
    return _write


@pytest.fixture
def fsfile(tmp_path):
    """Create a real .fs file for the client to didOpen."""
    def _write(name="Library.fs", text="module Library\n\nlet answer = 42\n"):
        path = tmp_path / name
        path.write_text(text, encoding="utf-8")
        return path
    return _write


@pytest.fixture
def client(tmp_path, monkeypatch):
    """An LspClient wired to the fake server, shut down at teardown."""
    from fsharp_lsp import LspClient

    created = []

    def _make(scenario_path=None, root=None):
        if scenario_path is not None:
            monkeypatch.setenv("FAKE_FSAC_SCENARIO", str(scenario_path))
        instance = LspClient(str(FAKE), root or tmp_path)
        created.append(instance)
        return instance

    yield _make
    for instance in created:
        instance.shutdown()


@pytest.fixture
def run_cli(tmp_path):
    """Run the CLI in a subprocess with FSAC_PATH pointed at the fake."""
    def _run(args, scenario_path=None, extra_env=None):
        env = dict(os.environ)
        env["FSAC_PATH"] = str(FAKE)
        if scenario_path is not None:
            env["FAKE_FSAC_SCENARIO"] = str(scenario_path)
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            [sys.executable, str(TOOLS / "fsharp_lsp.py"), *args],
            capture_output=True, text=True, env=env, timeout=60,
        )
    return _run
