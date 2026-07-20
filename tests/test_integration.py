import os
import shutil
import subprocess
from pathlib import Path

import pytest

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "SampleProject"
# PATH first, then the tool's own default. Both work on a correctly set up machine.
FSAC = Path(os.environ.get("FSAC_PATH")
            or shutil.which("fsautocomplete")
            or Path.home() / ".dotnet/tools/fsautocomplete")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not FSAC.exists(), reason=f"fsautocomplete not present at {FSAC}"),
    pytest.mark.skipif(shutil.which("dotnet") is None, reason="the .NET SDK is not installed"),
]


@pytest.fixture(scope="session", autouse=True)
def restored_fixture_project():
    """FSAC loads through MSBuild, which needs a restored project.

    Inherits the ambient environment deliberately: `dotnet` resolves from PATH,
    and forcing DOTNET_ROOT can switch the active SDK where several coexist."""
    result = subprocess.run(["dotnet", "restore"], cwd=str(FIXTURE),
                            capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, f"dotnet restore failed:\n{result.stdout}\n{result.stderr}"


@pytest.fixture
def real_cli(run_cli):
    """run_cli, but pointed at the real fsautocomplete instead of the fake."""
    def _run(args):
        return run_cli(args, extra_env={"FSAC_PATH": str(FSAC),
                                        "FAKE_FSAC_SCENARIO": ""})
    return _run


def test_symbols_finds_the_real_declarations(real_cli):
    result = real_cli(["symbols", str(FIXTURE), str(FIXTURE / "Library.fs")])

    assert result.returncode == 0, result.stderr
    assert "answer" in result.stdout
    assert "double" in result.stdout


def test_references_crosses_files_in_the_real_project(real_cli):
    """`double` is declared on line 7 of Library.fs at column 5, and used twice
    inside `quadruple` in Consumer.fs. With includeDeclaration that is 3 hits
    across 2 files. A different number is a real disagreement — investigate it,
    do not just edit the expected value."""
    result = real_cli(["references", str(FIXTURE), str(FIXTURE / "Library.fs"), "7", "5"])

    assert result.returncode == 0, result.stderr
    assert "3 reference(s) in 2 file(s)" in result.stdout
    assert "Library.fs: 1" in result.stdout
    assert "Consumer.fs: 2" in result.stdout


def test_diagnostics_reports_the_deliberate_error(real_cli):
    result = real_cli(["diagnostics", str(FIXTURE), str(FIXTURE / "Broken.fs")])

    assert result.returncode == 0, result.stderr
    assert "error 39" in result.stdout
    assert "nonExistentFunction" in result.stdout


def test_clean_file_reports_no_diagnostics(real_cli):
    result = real_cli(["diagnostics", str(FIXTURE), str(FIXTURE / "Library.fs")])

    assert result.returncode == 0, result.stderr
    assert "No diagnostics." in result.stdout
