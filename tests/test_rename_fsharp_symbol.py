"""Tests for tools/rename_fsharp_symbol.py.

Every guard in the design's safety table gets a test here, and every one of
them must be watched to fail before it is trusted — this is the first tool in
the plugin that can damage a user's source, so a guard nobody has seen fail is
not evidence.

The tests drive the real script in a subprocess against tests/fake_fsac.py,
which speaks enough LSP to answer a rename with a scripted WorkspaceEdit. The
stand-in is reached through PATH, not through an environment variable, because
PATH resolution is what the shipped tool does and bypassing it is how this
repo's suite once shipped a guard that could not fail.
"""

import json


def edit(line, start_col, end_col, new_text):
    """A TextEdit in LSP's 0-based coordinates."""
    return {
        "range": {
            "start": {"line": line, "character": start_col},
            "end": {"line": line, "character": end_col},
        },
        "newText": new_text,
    }


def test_dry_run_reports_the_edits_and_writes_nothing(fsharp_project, run_rename):
    """The default must be safe: an agent running this to see the blast radius
    must not change anything by doing so."""
    src = fsharp_project / "Library.fs"
    before = src.read_bytes()

    result = run_rename(
        fsharp_project, src, line=3, col=5, new_name="twice",
        workspace_edit={"changes": {src.as_uri(): [
            edit(2, 4, 10, "twice"),
            edit(5, 19, 25, "twice"),
            edit(5, 27, 33, "twice"),
        ]}},
    )

    assert result.returncode == 0, result.stderr
    assert src.read_bytes() == before, "dry run must not touch the file"
    assert "3 edit(s)" in result.stdout
    assert "Library.fs" in result.stdout
    assert "--apply" in result.stdout, "must say how to actually write"


def test_apply_writes_exactly_the_scripted_edits(fsharp_project, run_rename):
    src = fsharp_project / "Library.fs"

    result = run_rename(
        fsharp_project, src, line=3, col=5, new_name="twice",
        workspace_edit={"changes": {src.as_uri(): [
            edit(2, 4, 10, "twice"),
            edit(4, 18, 24, "twice"),
            edit(4, 26, 32, "twice"),
        ]}},
        args=("--apply",),
    )

    assert result.returncode == 0, result.stderr
    assert src.read_text(encoding="utf-8") == (
        "module Library\n"
        "\n"
        "let twice x = x * 2\n"
        "\n"
        "let quadruple x = twice (twice x)\n"
    )


def test_expect_mismatch_refuses_and_writes_nothing(fsharp_project, run_rename):
    """The count the caller believed and the count the server returned must
    agree, or nothing happens. This is the guard against a confident rename of
    the wrong symbol."""
    src = fsharp_project / "Library.fs"
    before = src.read_bytes()

    result = run_rename(
        fsharp_project, src, line=3, col=5, new_name="twice",
        workspace_edit={"changes": {src.as_uri(): [edit(2, 4, 10, "twice")]}},
        args=("--apply", "--expect", "3"),
    )

    assert result.returncode == 4, result.stdout + result.stderr
    assert src.read_bytes() == before
    assert "3" in result.stderr and "1" in result.stderr


def test_a_file_changing_under_us_refuses_and_writes_nothing(
        fsharp_project, run_rename):
    """Offsets are computed against the text the server was given. If the file
    moves between then and the write, applying them corrupts it."""
    src = fsharp_project / "Library.fs"

    result = run_rename(
        fsharp_project, src, line=3, col=5, new_name="twice",
        workspace_edit={"changes": {src.as_uri(): [edit(2, 4, 10, "twice")]}},
        args=("--apply",),
        extra_env={"FAKE_FSAC_TOUCHES_FILE": str(src)},
    )

    assert result.returncode == 5, result.stdout + result.stderr
    assert "changed" in result.stderr.lower()
    # The outside change stays; what must not happen is the rename
    # landing on top of it.
    assert "twice" not in src.read_text(encoding="utf-8")


def test_crlf_line_endings_survive_a_rename(fsharp_project, run_rename):
    """A CRLF checkout must come back CRLF. Round-tripping through text mode
    rewrites every line ending, turning a three-line change into a whole-file
    diff."""
    src = fsharp_project / "Library.fs"
    src.write_bytes(
        b"module Library\r\n"
        b"\r\n"
        b"let double x = x * 2\r\n"
        b"\r\n"
        b"let quadruple x = double (double x)\r\n"
    )

    result = run_rename(
        fsharp_project, src, line=3, col=5, new_name="twice",
        workspace_edit={"changes": {src.as_uri(): [edit(2, 4, 10, "twice")]}},
        args=("--apply",),
    )

    assert result.returncode == 0, result.stderr
    assert src.read_bytes() == (
        b"module Library\r\n"
        b"\r\n"
        b"let twice x = x * 2\r\n"
        b"\r\n"
        b"let quadruple x = double (double x)\r\n"
    )


def test_positions_reach_the_server_zero_based(fsharp_project, run_rename, tmp_path):
    """1-based on the command line, 0-based on the wire. Getting this wrong
    renames the symbol on the line above with complete confidence."""
    src = fsharp_project / "Library.fs"
    record = tmp_path / "request.json"

    run_rename(
        fsharp_project, src, line=3, col=5, new_name="twice",
        workspace_edit={"changes": {src.as_uri(): [edit(2, 4, 10, "twice")]}},
        extra_env={"FAKE_FSAC_RECORD": str(record)},
    )

    sent = json.loads(record.read_text(encoding="utf-8"))
    assert sent["position"] == {"line": 2, "character": 4}
    assert sent["newName"] == "twice"


def test_apply_leaves_no_temporary_files_behind(fsharp_project, run_rename):
    src = fsharp_project / "Library.fs"

    run_rename(
        fsharp_project, src, line=3, col=5, new_name="twice",
        workspace_edit={"changes": {src.as_uri(): [edit(2, 4, 10, "twice")]}},
        args=("--apply",),
    )

    assert sorted(p.name for p in fsharp_project.iterdir()) == [
        "Library.fs", "SampleProject.fsproj"]


def test_a_server_refusal_is_reported_not_swallowed(fsharp_project, run_rename):
    """fsautocomplete answers null for a symbol it will not rename — Active
    Patterns among them. That must arrive as an explanation, not as an empty
    success."""
    src = fsharp_project / "Library.fs"

    result = run_rename(fsharp_project, src, line=3, col=5, new_name="twice",
                        workspace_edit=None, args=("--apply",))

    assert result.returncode == 3, result.stdout
    assert "Active Pattern" in result.stderr


def test_an_empty_workspace_edit_is_refused(fsharp_project, run_rename):
    """Reporting success having changed nothing is the failure shape this guard
    exists for: the caller believes the rename happened and every reference is
    still there."""
    src = fsharp_project / "Library.fs"
    before = src.read_bytes()

    result = run_rename(fsharp_project, src, line=3, col=5, new_name="twice",
                        workspace_edit={"changes": {}}, args=("--apply",))

    assert result.returncode == 3, result.stdout
    assert src.read_bytes() == before


def test_a_file_operation_in_the_edit_is_refused(fsharp_project, run_rename):
    """A symbol rename does not create, rename or delete files. One arriving
    means something is wrong, and applying it blind is worse than stopping."""
    src = fsharp_project / "Library.fs"
    before = src.read_bytes()

    result = run_rename(
        fsharp_project, src, line=3, col=5, new_name="twice",
        workspace_edit={"documentChanges": [
            {"kind": "delete", "uri": (fsharp_project / "Gone.fs").as_uri()},
        ]},
        args=("--apply",),
    )

    assert result.returncode == 3, result.stdout + result.stderr
    # Named specifically, not just "something went wrong". Asserting only on a
    # non-zero exit let this test pass with the guard deleted, because the edit
    # degenerated to zero changes and a different guard caught it.
    assert "file operation" in result.stderr
    assert src.read_bytes() == before
