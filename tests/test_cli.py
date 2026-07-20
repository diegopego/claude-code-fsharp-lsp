import json


def _recorded(record_path):
    return [json.loads(line) for line in
            record_path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_symbols_lists_names_and_exits_zero(run_cli, scenario, fsfile, tmp_path):
    path = fsfile()
    scenario_path = scenario({
        "responses": {
            "textDocument/documentSymbol": [
                {"name": "answer", "range": {"start": {"line": 2, "character": 4},
                                             "end": {"line": 2, "character": 10}}},
                {"name": "double", "range": {"start": {"line": 4, "character": 4},
                                             "end": {"line": 4, "character": 10}}},
            ]
        }
    })
    result = run_cli(["symbols", str(tmp_path), str(path)], scenario_path)

    assert result.returncode == 0
    assert "2 top-level symbol(s):" in result.stdout
    # Reported 1-based: LSP line 2 is displayed as line 3.
    assert "answer  (line 3)" in result.stdout
    assert "double  (line 5)" in result.stdout


def test_symbols_exits_one_when_nothing_found(run_cli, scenario, fsfile, tmp_path):
    scenario_path = scenario({"responses": {"textDocument/documentSymbol": []}})
    result = run_cli(["symbols", str(tmp_path), str(fsfile())], scenario_path)

    assert result.returncode == 1
    assert "0 top-level symbol(s):" in result.stdout


def test_lsp_error_exits_two_and_reports_on_stderr(run_cli, scenario, fsfile, tmp_path):
    scenario_path = scenario({
        "errors": {"textDocument/documentSymbol": {"code": -32603, "message": "boom"}}
    })
    result = run_cli(["symbols", str(tmp_path), str(fsfile())], scenario_path)

    assert result.returncode == 2
    assert "LSP ERROR:" in result.stderr
    assert "boom" in result.stderr


def test_references_converts_one_based_position_to_zero_based(run_cli, scenario, fsfile, tmp_path):
    """CLI line 47 column 6 must reach the server as line 46 character 5."""
    record = tmp_path / "record.jsonl"
    scenario_path = scenario({
        "record_path": str(record),
        "responses": {"textDocument/references": []},
    })
    run_cli(["references", str(tmp_path), str(fsfile()), "47", "6"], scenario_path)

    requests = [m for m in _recorded(record) if m.get("method") == "textDocument/references"]
    assert len(requests) == 1
    assert requests[0]["params"]["position"] == {"line": 46, "character": 5}
    assert requests[0]["params"]["context"] == {"includeDeclaration": True}


def test_references_groups_hits_by_file(run_cli, scenario, fsfile, tmp_path):
    scenario_path = scenario({
        "responses": {
            "textDocument/references": [
                {"uri": "file:///proj/Library.fs",
                 "range": {"start": {"line": 4, "character": 4},
                           "end": {"line": 4, "character": 10}}},
                {"uri": "file:///proj/Consumer.fs",
                 "range": {"start": {"line": 4, "character": 25},
                           "end": {"line": 4, "character": 31}}},
                {"uri": "file:///proj/Consumer.fs",
                 "range": {"start": {"line": 4, "character": 32},
                           "end": {"line": 4, "character": 38}}},
            ]
        }
    })
    result = run_cli(["references", str(tmp_path), str(fsfile()), "5", "5"], scenario_path)

    assert result.returncode == 0
    assert "WITH config: 3 reference(s) in 2 file(s)" in result.stdout
    assert "/proj/Consumer.fs: 2" in result.stdout
    assert "/proj/Library.fs: 1" in result.stdout


def test_references_no_config_flag_changes_the_label(run_cli, scenario, fsfile, tmp_path):
    record = tmp_path / "record.jsonl"
    scenario_path = scenario({
        "record_path": str(record),
        "responses": {"textDocument/references": []},
    })
    result = run_cli(
        ["references", str(tmp_path), str(fsfile()), "5", "5", "--no-config"], scenario_path)

    assert "WITHOUT config: 0 reference(s) in 0 file(s)" in result.stdout
    methods = [m.get("method") for m in _recorded(record)]
    assert "workspace/didChangeConfiguration" not in methods


def test_diagnostics_reports_none_for_a_clean_file(run_cli, scenario, fsfile, tmp_path):
    result = run_cli(["diagnostics", str(tmp_path), str(fsfile())], scenario({}))

    assert result.returncode == 0
    assert "No diagnostics." in result.stdout


def test_diagnostics_formats_severity_code_and_one_based_line(run_cli, scenario, fsfile, tmp_path):
    scenario_path = scenario({
        "publish_diagnostics_on_open": [
            {"range": {"start": {"line": 2, "character": 13},
                       "end": {"line": 2, "character": 32}},
             "severity": 1, "code": 39,
             "message": "The value or constructor 'nope' is not defined.\nsecond line"}
        ]
    })
    result = run_cli(["diagnostics", str(tmp_path), str(fsfile())], scenario_path)

    assert result.returncode == 0
    assert "line 3: [error 39] The value or constructor 'nope' is not defined." in result.stdout
    # Only the first line of a multi-line message is printed.
    assert "second line" not in result.stdout


def test_missing_fsac_binary_exits_two_with_actionable_message(run_cli, fsfile, tmp_path):
    missing = tmp_path / "not-a-real-fsautocomplete"
    result = run_cli(["symbols", str(tmp_path), str(fsfile())],
                     extra_env={"FSAC_PATH": str(missing)})

    assert result.returncode == 2
    assert "Traceback" not in result.stderr
    assert "fsautocomplete not found" in result.stderr
    assert str(missing) in result.stderr
    assert "dotnet tool install -g fsautocomplete" in result.stderr


def test_doctor_reports_healthy_and_exits_zero(run_cli, tmp_path):
    result = run_cli(["doctor"])

    assert result.returncode == 0, result.stderr
    assert "0.0.0-fake" in result.stdout
    assert "FAIL" not in result.stdout and "FAIL" not in result.stderr


def test_doctor_flags_a_missing_binary(run_cli, tmp_path):
    missing = tmp_path / "not-a-real-fsautocomplete"
    result = run_cli(["doctor"], extra_env={"FSAC_PATH": str(missing)})

    assert result.returncode == 2
    assert "fsautocomplete not found" in result.stderr
    assert str(missing) in result.stderr
    assert "dotnet tool install -g fsautocomplete" in result.stderr


def test_doctor_flags_a_binary_that_is_present_but_broken(run_cli):
    """Presence is not health. This is the failure that makes the built-in LSP
    tool hang instead of reporting anything."""
    result = run_cli(["doctor"], extra_env={"FAKE_FSAC_VERSION_FAILS": "1"})

    assert result.returncode == 2
    assert "exited 1" in result.stderr
    assert "could not resolve runtime" in result.stderr


def test_doctor_hook_mode_is_silent_when_healthy(run_cli):
    result = run_cli(["doctor", "--hook"])

    assert result.returncode == 0
    assert result.stdout.strip() == ""
    assert result.stderr.strip() == ""


def test_doctor_hook_mode_warns_on_stdout_and_still_exits_zero(run_cli, tmp_path):
    """A session-start hook must never fail the session."""
    result = run_cli(["doctor", "--hook"],
                     extra_env={"FSAC_PATH": str(tmp_path / "gone")})

    assert result.returncode == 0
    assert "fsautocomplete not found" in result.stdout


def test_doctor_rejects_a_project_directory_with_no_fsproj(run_cli, tmp_path):
    (tmp_path / "Library.fs").write_text("module Library\n", encoding="utf-8")
    result = run_cli(["doctor", str(tmp_path)])

    assert result.returncode == 2
    assert "no .fsproj under" in result.stderr
    assert "often not the repo root" in result.stderr


def test_doctor_detects_an_unrestored_project(run_cli, tmp_path):
    (tmp_path / "Sample.fsproj").write_text(
        "<Project Sdk=\"Microsoft.NET.Sdk\"></Project>\n", encoding="utf-8")
    result = run_cli(["doctor", str(tmp_path)])

    assert result.returncode == 2
    assert "not restored: Sample.fsproj" in result.stderr
    assert "dotnet restore" in result.stderr
