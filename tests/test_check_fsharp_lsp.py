"""Tests for tools/check_fsharp_lsp.py.

The check exists for exactly one failure: fsautocomplete not resolving on PATH,
or resolving to something that will not run. That failure reports nothing — the
LSP tool hangs, because the server dies before the handshake completes. The
other two ways F# breaks announce themselves in the tool's own error message and
need no diagnosis.

So the tests that matter most are the ones covering PATH resolution, "present
but broken", and the hook's never-fail contract. Everything here reaches the
binary the way `.lsp.json` does — through PATH — because a fixture that pointed
at the stand-in some other way would leave the resolution untested, and the
resolution is the point.
"""

import shutil

import pytest


# ── PATH resolution: the reason this script exists ──────────────────────────

def test_reports_healthy_and_exits_zero(run_check):
    result = run_check()

    assert result.returncode == 0, result.stderr
    assert "0.0.0-fake" in result.stdout
    assert "FAIL" not in result.stderr


def test_flags_fsautocomplete_missing_from_path(run_check, python_only_path):
    """The failure the whole script is for: nothing on PATH answers to the name.

    Claude Code launches the server as a bare command, so this is fatal — and it
    reports nothing on its own, which is why the check has to."""
    result = run_check(path_dirs=[python_only_path])

    assert result.returncode == 2
    assert "fsautocomplete is not on PATH" in result.stderr
    assert "dotnet tool install -g fsautocomplete" in result.stderr
    assert "PATH of the process that launches Claude Code" in result.stderr


def test_a_binary_outside_path_does_not_count_as_healthy(run_check, python_only_path,
                                                         fsac_on_path):
    """Installed but unreachable is still broken.

    A binary sitting in ~/.dotnet/tools is no use to a server launched as a bare
    command, so the check must not go looking for one and must not be reassured
    by finding one. This pins that: the stand-in exists on disk, and is simply
    not on PATH."""
    installed = fsac_on_path()
    assert (installed / "fsautocomplete").exists()

    result = run_check(path_dirs=[python_only_path])

    assert result.returncode == 2
    assert "not on PATH" in result.stderr


def test_reports_where_on_path_the_binary_came_from(run_check, fsac_on_path,
                                                    python_only_path):
    """"Which fsautocomplete answered?" is the first question of any bug report."""
    bin_dir = fsac_on_path()
    result = run_check(path_dirs=[bin_dir, python_only_path])

    assert result.returncode == 0, result.stderr
    assert str(bin_dir / "fsautocomplete") in result.stdout


def test_fsac_path_is_not_honoured(run_check, python_only_path, fsac_on_path):
    """`.lsp.json` cannot honour FSAC_PATH, so neither may this.

    Honouring it would let the check pass while the server fails, which is worse
    than not checking."""
    installed = fsac_on_path()
    result = run_check(path_dirs=[python_only_path],
                       extra_env={"FSAC_PATH": str(installed / "fsautocomplete")})

    assert result.returncode == 2
    assert "not on PATH" in result.stderr


# ── presence is not health ──────────────────────────────────────────────────

def test_flags_a_binary_that_is_present_but_broken(run_check):
    """On PATH, runs, and fails — the other half of the silent hang."""
    result = run_check(extra_env={"FAKE_FSAC_VERSION_FAILS": "1"})

    assert result.returncode == 2
    assert "exited 1" in result.stderr
    assert "could not resolve runtime" in result.stderr


# ── the .NET SDK line is diagnostic, never a gate ───────────────────────────

def test_never_fails_over_the_dotnet_sdk(run_check, python_only_path, fsac_on_path):
    """An earlier version of this check was going to fail the run when no .NET 10
    SDK was present. That was wrong: `dotnet tool install -g fsautocomplete`
    cannot succeed without some SDK, and FSAC ships net8.0/net9.0/net10.0
    builds, so anyone who installed it at all has a working one. All the check
    earns is putting the version in the output so a bug report carries it."""
    bin_dir = fsac_on_path()
    assert shutil.which("dotnet", path=str(bin_dir)) is None

    result = run_check(path_dirs=[bin_dir, python_only_path])

    assert result.returncode == 0, result.stderr
    assert "FAIL" not in result.stderr


@pytest.mark.skipif(shutil.which("dotnet") is None, reason="no dotnet on PATH — most CI images have one, so this usually runs")
def test_reports_the_sdk_version_when_there_is_one(run_check):
    """Asserts a version, not the literal words "dotnet sdk".

    The line reads "dotnet sdk none reported" when the parse yields nothing, so
    matching the label alone would pass with the parsing broken."""
    result = run_check()

    assert result.returncode == 0, result.stderr
    sdk_line = next(l for l in result.stdout.splitlines() if "dotnet sdk" in l)
    assert "none reported" not in sdk_line
    assert any(ch.isdigit() for ch in sdk_line), sdk_line


def test_says_so_when_dotnet_is_absent(run_check, fsac_on_path, python_only_path):
    result = run_check(path_dirs=[fsac_on_path(), python_only_path])

    assert result.returncode == 0, result.stderr
    assert "dotnet not on PATH" in result.stdout


# ── the hook must never fail the session ────────────────────────────────────

def test_hook_mode_is_silent_when_healthy(run_check):
    result = run_check(["--hook"])

    assert result.returncode == 0
    assert result.stdout.strip() == ""
    assert result.stderr.strip() == ""


def test_hook_mode_warns_on_stdout_and_still_exits_zero(run_check, python_only_path):
    """A session-start hook must never fail the session."""
    result = run_check(["--hook"], path_dirs=[python_only_path])

    assert result.returncode == 0
    assert "fsautocomplete is not on PATH" in result.stdout


def test_hook_mode_survives_a_broken_binary_too(run_check):
    """The never-fail contract has to hold for every problem, not just the one
    the previous test happens to use. A hook that exits non-zero on a broken
    install would break the session it was meant to warn about."""
    result = run_check(["--hook"], extra_env={"FAKE_FSAC_VERSION_FAILS": "1"})

    assert result.returncode == 0
    assert "fsharp-lsp:" in result.stdout
    assert result.stderr.strip() == ""


# ── the optional PROJECT argument ───────────────────────────────────────────

def test_rejects_a_project_directory_with_no_fsproj(run_check, tmp_path):
    (tmp_path / "Library.fs").write_text("module Library\n", encoding="utf-8")
    result = run_check([str(tmp_path)])

    assert result.returncode == 2
    assert "no .fsproj under" in result.stderr
    assert "often not the repo root" in result.stderr


def test_detects_an_unrestored_project(run_check, tmp_path):
    (tmp_path / "Sample.fsproj").write_text(
        "<Project Sdk=\"Microsoft.NET.Sdk\"></Project>\n", encoding="utf-8")
    result = run_check([str(tmp_path)])

    assert result.returncode == 2
    assert "not restored: Sample.fsproj" in result.stderr
    assert "dotnet restore" in result.stderr


def test_accepts_a_restored_project(run_check, tmp_path):
    """The counterpart to the test above — without it, "not restored" could be
    reported for every project and the suite would stay green."""
    (tmp_path / "Sample.fsproj").write_text(
        "<Project Sdk=\"Microsoft.NET.Sdk\"></Project>\n", encoding="utf-8")
    obj = tmp_path / "obj"
    obj.mkdir()
    (obj / "project.assets.json").write_text("{}", encoding="utf-8")

    result = run_check([str(tmp_path)])

    assert result.returncode == 0, result.stderr
    assert "1 restored project(s)" in result.stdout


def test_finds_a_project_one_level_down(run_check, tmp_path):
    """PROJECT is often a repo root with the .fsproj in a subdirectory, so the
    glob descends one level. Without this the `*/*.fsproj` half never runs."""
    nested = tmp_path / "src"
    nested.mkdir()
    (nested / "Sample.fsproj").write_text(
        "<Project Sdk=\"Microsoft.NET.Sdk\"></Project>\n", encoding="utf-8")
    obj = nested / "obj"
    obj.mkdir()
    (obj / "project.assets.json").write_text("{}", encoding="utf-8")

    result = run_check([str(tmp_path)])

    assert result.returncode == 0, result.stderr
    assert "1 restored project(s)" in result.stdout


def test_rejects_a_project_directory_that_does_not_exist(run_check, tmp_path):
    result = run_check([str(tmp_path / "nowhere")])

    assert result.returncode == 2
    assert "does not exist" in result.stderr
