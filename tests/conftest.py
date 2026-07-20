import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
FAKE = Path(__file__).resolve().parent / "fake_fsac.py"


@pytest.fixture
def fsac_on_path(tmp_path):
    """Put a stand-in `fsautocomplete` on PATH, the way a real install would.

    The check resolves the binary with shutil.which, exactly as Claude Code
    resolves the bare command in .lsp.json. Pointing at the fake through an
    environment variable instead would leave that resolution untested — and the
    resolution is what the whole script is about.
    """
    def _install():
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir(exist_ok=True)
        target = bin_dir / "fsautocomplete"
        shutil.copy(FAKE, target)
        target.chmod(0o755)
        return bin_dir
    return _install


@pytest.fixture
def python_only_path(tmp_path):
    """A PATH holding python3 and nothing else.

    The stand-in is a `#!/usr/bin/env python3` script, so it needs python3
    reachable; emptying PATH outright would break the stand-in rather than the
    thing under test.
    """
    bin_dir = tmp_path / "bare"
    bin_dir.mkdir(exist_ok=True)
    link = bin_dir / "python3"
    if not link.exists():
        link.symlink_to(sys.executable)
    return bin_dir


@pytest.fixture
def run_check(fsac_on_path):
    """Run check_fsharp_lsp.py in a subprocess with the stand-in first on PATH.

    A subprocess rather than an import, because the exit code and the
    stdout/stderr split are part of what the session-start hook depends on.

    Pass `path_dirs` to replace PATH entirely — that is how the "not on PATH"
    case is reached.
    """
    def _run(args=(), extra_env=None, path_dirs=None):
        env = dict(os.environ)
        if path_dirs is None:
            env["PATH"] = os.pathsep.join(
                [str(fsac_on_path()), env.get("PATH", "")])
        else:
            env["PATH"] = os.pathsep.join(str(d) for d in path_dirs)
        # No longer honoured by the check; make sure a stray one cannot mask that.
        env.pop("FSAC_PATH", None)
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            [sys.executable, str(TOOLS / "check_fsharp_lsp.py"), *args],
            capture_output=True, text=True, env=env, timeout=60,
        )
    return _run
