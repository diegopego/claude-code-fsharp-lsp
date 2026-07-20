def test_initialize_then_request_round_trips(client, scenario, fsfile):
    path = fsfile()
    scenario_path = scenario({
        "responses": {
            "textDocument/documentSymbol": [
                {"name": "answer",
                 "range": {"start": {"line": 2, "character": 4},
                           "end": {"line": 2, "character": 10}}}
            ]
        }
    })
    lsp = client(scenario_path)
    lsp.initialize()
    uri = lsp.open(path)
    result = lsp.request("textDocument/documentSymbol", {"textDocument": {"uri": uri}})

    assert result == [
        {"name": "answer",
         "range": {"start": {"line": 2, "character": 4},
                   "end": {"line": 2, "character": 10}}}
    ]


import json


def _recorded(record_path):
    """Every message the fake server received, in order."""
    return [json.loads(line) for line in
            record_path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_answers_server_initiated_configuration_request(client, scenario, fsfile, tmp_path):
    """A server->client request that goes unanswered deadlocks FSAC. The client
    must reply with one empty object per requested item."""
    record = tmp_path / "record.jsonl"
    scenario_path = scenario({
        "record_path": str(record),
        "server_requests_after_initialized": [
            {"method": "workspace/configuration", "params": {"items": [{}, {}]}}
        ],
        "responses": {"textDocument/documentSymbol": []},
    })
    lsp = client(scenario_path)
    lsp.initialize()
    uri = lsp.open(fsfile())
    # A request after the server-initiated one proves we did not deadlock.
    lsp.request("textDocument/documentSymbol", {"textDocument": {"uri": uri}})

    replies = [m for m in _recorded(record) if "id" in m and "method" not in m]
    assert len(replies) == 1
    assert replies[0]["result"] == [{}, {}]


def test_did_change_configuration_is_sent_by_default(client, scenario, tmp_path):
    record = tmp_path / "record.jsonl"
    lsp = client(scenario({"record_path": str(record)}))
    lsp.initialize()
    lsp.request("shutdown", {})  # ordering barrier: config was written first

    methods = [m.get("method") for m in _recorded(record)]
    assert "workspace/didChangeConfiguration" in methods


def test_did_change_configuration_is_skipped_when_disabled(client, scenario, tmp_path):
    record = tmp_path / "record.jsonl"
    lsp = client(scenario({"record_path": str(record)}))
    lsp.initialize(send_config=False)
    lsp.request("shutdown", {})

    methods = [m.get("method") for m in _recorded(record)]
    assert "workspace/didChangeConfiguration" not in methods


def test_open_sends_file_contents_and_fsharp_language_id(client, scenario, fsfile, tmp_path):
    record = tmp_path / "record.jsonl"
    lsp = client(scenario({"record_path": str(record)}))
    lsp.initialize()
    path = fsfile(text="module Library\n\nlet answer = 42\n")
    uri = lsp.open(path)
    lsp.request("shutdown", {})

    opens = [m for m in _recorded(record) if m.get("method") == "textDocument/didOpen"]
    assert len(opens) == 1
    doc = opens[0]["params"]["textDocument"]
    assert doc["uri"] == uri
    assert doc["languageId"] == "fsharp"
    assert doc["text"] == "module Library\n\nlet answer = 42\n"


def test_publish_diagnostics_are_captured_for_the_opened_uri(client, scenario, fsfile):
    scenario_path = scenario({
        "publish_diagnostics_on_open": [
            {"range": {"start": {"line": 4, "character": 13},
                       "end": {"line": 4, "character": 32}},
             "severity": 1, "code": 39,
             "message": "The value or constructor 'nope' is not defined."}
        ]
    })
    lsp = client(scenario_path)
    lsp.initialize()
    uri = lsp.open(fsfile())

    diagnostics = lsp.wait_for_diagnostics(uri, timeout=10.0)
    assert len(diagnostics) == 1
    assert diagnostics[0]["code"] == 39


def test_log_messages_are_drained(client, scenario):
    lsp = client(scenario({"log_messages": ["loading project", "project loaded"]}))
    lsp.initialize()
    lsp.request("shutdown", {})  # barrier: the notifications have been dispatched

    assert lsp.drain_log() == ["loading project", "project loaded"]


import pytest

from fsharp_lsp import LspError


def test_error_response_raises_lsp_error(client, scenario, fsfile):
    scenario_path = scenario({
        "errors": {"textDocument/references": {"code": -32602,
                                               "message": "No references found at position"}}
    })
    lsp = client(scenario_path)
    lsp.initialize()
    uri = lsp.open(fsfile())

    with pytest.raises(LspError) as excinfo:
        lsp.request("textDocument/references", {"textDocument": {"uri": uri}})
    assert "No references found at position" in str(excinfo.value)


def test_unanswered_request_times_out_with_lsp_error(client, scenario, fsfile):
    scenario_path = scenario({"hang": ["textDocument/references"]})
    lsp = client(scenario_path)
    lsp.initialize()
    uri = lsp.open(fsfile())

    with pytest.raises(LspError) as excinfo:
        lsp.request("textDocument/references", {"textDocument": {"uri": uri}}, timeout=1.0)
    assert "no response after 1s" in str(excinfo.value)


def test_wait_for_diagnostics_returns_empty_when_none_published(client, scenario, fsfile):
    """A clean file legitimately never publishes, so a timeout is not an error."""
    lsp = client(scenario({}))
    lsp.initialize()
    uri = lsp.open(fsfile())

    assert lsp.wait_for_diagnostics(uri, timeout=1.0) == []
