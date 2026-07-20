import json
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


@pytest.fixture
def fsharp_project(tmp_path):
    """A throwaway workspace holding one F# file.

    Built by the test rather than checked in. A fixture project whose only
    purpose is to sit in the repository being slightly wrong is the thing 2.0.0
    deleted, and there is no reason to grow another.
    """
    project = tmp_path / "SampleProject"
    project.mkdir()
    (project / "Library.fs").write_text(
        "module Library\n"
        "\n"
        "let double x = x * 2\n"
        "\n"
        "let quadruple x = double (double x)\n",
        encoding="utf-8",
    )
    (project / "SampleProject.fsproj").write_text(
        "<Project Sdk=\"Microsoft.NET.Sdk\">\n"
        "  <ItemGroup><Compile Include=\"Library.fs\" /></ItemGroup>\n"
        "</Project>\n",
        encoding="utf-8",
    )
    return project


@pytest.fixture
def run_rename(fsac_on_path):
    """Run rename_fsharp_symbol.py against the stand-in, reached through PATH.

    `workspace_edit` is what the stand-in will answer the rename with; pass
    `workspace_edit=None` for the "server refuses" case. Extra argv goes in
    `args`, so a test can add --apply or --expect without this fixture growing a
    parameter per flag.
    """
    def _run(project, file, line, col, new_name, workspace_edit=..., args=(),
             extra_env=None):
        env = dict(os.environ)
        env["PATH"] = os.pathsep.join([str(fsac_on_path()), env.get("PATH", "")])
        if workspace_edit is not ...:
            if workspace_edit is None:
                env.pop("FAKE_FSAC_RENAME", None)
            else:
                env["FAKE_FSAC_RENAME"] = json.dumps(workspace_edit)
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            [sys.executable, str(TOOLS / "rename_fsharp_symbol.py"),
             str(project), str(file), str(line), str(col), new_name, *args],
            capture_output=True, text=True, env=env, timeout=60,
        )
    return _run
