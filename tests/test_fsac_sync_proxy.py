"""fsac_sync_proxy.py — what reaches the server, and in which order.

The proxy's whole contract is the traffic it delivers to fsautocomplete, so
every test here drives the proxy as a subprocess speaking real Content-Length
frames, with the stand-in server recording each message it receives
(FAKE_FSAC_TRANSCRIPT). Assertions are made against that transcript — the only
witness that can testify about injections.

The stand-in is reached as bare `fsautocomplete` on PATH, exactly the
resolution production uses: the proxy's default argv is the same bare command
.lsp.json used to launch directly. Pointing at it any other way would leave
that path untested — the lesson the health-check suite already paid for once.

Each guard here was mutation-tested: the injection, the disk comparison, the
touch loop, the workspace scan, the valve and the fail-open were each broken
in turn and the corresponding test watched to fail. Assertions are specific
(which method, which text, which order) rather than "something happened",
because the suite's job is to notice the next refactor deleting one branch.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PROXY = ROOT / "tools" / "fsac_sync_proxy.py"


def frame(payload: dict) -> bytes:
    body = json.dumps(payload).encode("utf-8")
    return f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body


def did_open(path: Path, text: str) -> dict:
    return {"jsonrpc": "2.0", "method": "textDocument/didOpen",
            "params": {"textDocument": {"uri": path.as_uri(),
                                        "languageId": "fsharp",
                                        "version": 1, "text": text}}}


def initialize(root: Path) -> dict:
    return {"jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"rootUri": root.as_uri()}}


def some_request(rid: int = 9) -> dict:
    """Any request that is neither initialize nor shutdown triggers a sync."""
    return {"jsonrpc": "2.0", "id": rid, "method": "textDocument/documentSymbol",
            "params": {"textDocument": {"uri": "file:///irrelevant"}}}


class MutateThen:
    """A step in the payload list that runs a side effect mid-conversation.

    The mutation has to happen after earlier frames are sent and before later
    ones — interleaving a callable in the payload list keeps each test's
    timeline readable top to bottom. May return extra payloads to send.
    """

    def __init__(self, fn):
        self.fn = fn


class AwaitReply:
    """Block until one response frame comes back through the proxy.

    Sending is buffered, so a frame being written proves nothing about the
    proxy having processed it. Where a test depends on a side effect of that
    processing — the workspace stat baseline taken at initialize — the reply is
    the only reliable "it happened" signal: it exists because the stand-in
    answered, which requires the proxy to have observed and forwarded first.
    """


@pytest.fixture
def run_proxy(fsac_on_path, tmp_path):
    """Feed frames to the proxy, wait for it to drain, return the transcript.

    Closing stdin is the shutdown path: the proxy sees EOF, closes the
    stand-in's stdin, and both exit. Only then is the transcript read, so
    ordering in it is the pipeline's real delivery order.
    """
    def _run(payloads, extra_env=None):
        transcript = tmp_path / "transcript.jsonl"
        env = dict(os.environ)
        env["PATH"] = os.pathsep.join([str(fsac_on_path()), env.get("PATH", "")])
        env["FAKE_FSAC_TRANSCRIPT"] = str(transcript)
        env["FSHARP_LSP_SYNC_SETTLE_MS"] = "0"
        if extra_env:
            env.update(extra_env)
        proc = subprocess.Popen(
            [sys.executable, str(PROXY)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, env=env)
        assert proc.stdin is not None

        def send(item):
            if isinstance(item, AwaitReply):
                proc.stdin.flush()
                header = b""
                length = None
                while True:
                    line = proc.stdout.readline()
                    assert line, "proxy closed stdout while a reply was awaited"
                    if not line.strip():
                        break
                    if line.strip().lower().startswith(b"content-length:"):
                        length = int(line.strip().split(b":", 1)[1])
                    header += line
                assert length is not None
                proc.stdout.read(length)
            elif isinstance(item, MutateThen):
                for extra in item.fn(None) or []:
                    send(extra)
            elif isinstance(item, bytes):
                proc.stdin.write(item)
            else:
                proc.stdin.write(frame(item))

        for item in payloads:
            send(item)
        proc.stdin.close()
        proc.wait(timeout=30)
        received = []
        if transcript.exists():
            with open(transcript, encoding="utf-8") as fh:
                received = [json.loads(line) for line in fh if line.strip()]
        return received, proc

    return _run


def methods(received: list[dict]) -> list[str]:
    return [m.get("method", "?") for m in received]


def source(tmp_path: Path, name: str = "Library.fs",
           text: str = "let answer = 42\n") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


# -- pass-through ------------------------------------------------------------


def test_clean_disk_forwards_the_client_traffic_and_nothing_else(run_proxy, tmp_path):
    fs = source(tmp_path)
    received, _ = run_proxy([
        initialize(tmp_path),
        did_open(fs, fs.read_text()),
        some_request(),
    ])
    assert methods(received) == [
        "initialize", "textDocument/didOpen", "textDocument/documentSymbol"]


def test_unparseable_client_frame_is_forwarded_not_dropped(run_proxy, tmp_path):
    garbage = b"Content-Length: 9\r\n\r\nnot json!"
    received, proc = run_proxy([
        initialize(tmp_path),
        garbage,
        some_request(),
    ])
    # The stand-in records what it could not parse; the request after it still
    # arrived, so the stream survived bytes the proxy did not understand.
    assert {"unparseable": True} in received
    assert "textDocument/documentSymbol" in methods(received)
    assert proc.returncode == 0


# -- resync ------------------------------------------------------------------


def test_disk_change_is_resynced_before_the_request_runs(run_proxy, tmp_path):
    fs = source(tmp_path)
    opened = fs.read_text()

    def mutate(_):
        fs.write_text("let answer = 43\nlet extra = 1\n", encoding="utf-8")
        return []

    received, _ = run_proxy([
        initialize(tmp_path),
        did_open(fs, opened),
        MutateThen(mutate),
        some_request(),
    ])
    seq = methods(received)
    close_at = seq.index("textDocument/didClose")
    reopen_at = seq.index("textDocument/didOpen", close_at)
    request_at = seq.index("textDocument/documentSymbol")
    assert close_at < reopen_at < request_at
    reopened = received[reopen_at]["params"]["textDocument"]
    assert reopened["uri"] == fs.as_uri()
    assert reopened["text"] == "let answer = 43\nlet extra = 1\n"


def test_resync_touches_every_tracked_doc_with_a_bumped_version(run_proxy, tmp_path):
    changed = source(tmp_path, "Changed.fs")
    dependent = source(tmp_path, "Dependent.fs", "let dep = 1\n")

    received, _ = run_proxy([
        initialize(tmp_path),
        did_open(changed, changed.read_text()),
        did_open(dependent, dependent.read_text()),
        MutateThen(lambda _: changed.write_text("let answer = 99\n",
                                                encoding="utf-8") and []),
        some_request(),
    ])
    touches = [m for m in received
               if m.get("method") == "textDocument/didChange"
               and m["params"]["textDocument"]["uri"] == dependent.as_uri()]
    assert touches, "the untouched dependent never got its nudge"
    touch = touches[0]
    assert touch["params"]["contentChanges"] == [{"text": "let dep = 1\n"}]
    assert touch["params"]["textDocument"]["version"] > 1


def test_never_opened_workspace_file_is_server_opened_on_change(run_proxy, tmp_path):
    watched = source(tmp_path, "NeverOpened.fs", "let hidden = 1\n")

    received, _ = run_proxy([
        initialize(tmp_path),
        AwaitReply(),   # the stat baseline is taken while observing initialize
        MutateThen(lambda _: watched.write_text("let hidden = 2\n",
                                                encoding="utf-8") and []),
        some_request(),
    ])
    opens = [m for m in received
             if m.get("method") == "textDocument/didOpen"
             and m["params"]["textDocument"]["uri"] == watched.as_uri()]
    assert opens, "the changed never-opened file was not server-opened"
    assert opens[0]["params"]["textDocument"]["text"] == "let hidden = 2\n"


def test_behaved_client_didchange_causes_no_resync(run_proxy, tmp_path):
    """The -p client sends a correct full-text didChange; the proxy must not
    churn on top of it — disk and tracking already agree."""
    fs = source(tmp_path)
    new_text = "let answer = 43\n"

    def client_syncs(_):
        fs.write_text(new_text, encoding="utf-8")
        return [{"jsonrpc": "2.0", "method": "textDocument/didChange",
                 "params": {"textDocument": {"uri": fs.as_uri(), "version": 2},
                            "contentChanges": [{"text": new_text}]}}]

    received, _ = run_proxy([
        initialize(tmp_path),
        did_open(fs, fs.read_text()),
        MutateThen(client_syncs),
        some_request(),
    ])
    assert "textDocument/didClose" not in methods(received)


# -- the valve and failing open ----------------------------------------------


def test_valve_off_injects_nothing_and_still_forwards(run_proxy, tmp_path):
    fs = source(tmp_path)
    received, proc = run_proxy([
        initialize(tmp_path),
        did_open(fs, fs.read_text()),
        MutateThen(lambda _: fs.write_text("let answer = 43\n",
                                           encoding="utf-8") and []),
        some_request(),
    ], extra_env={"FSHARP_LSP_SYNC": "off"})
    assert methods(received) == [
        "initialize", "textDocument/didOpen", "textDocument/documentSymbol"]
    assert proc.returncode == 0


def test_hostile_frame_fails_open_not_dead(run_proxy, tmp_path):
    """A didOpen with no text field raises inside the tracking code. The sync
    layer must swallow that and forward the traffic — stale beats broken."""
    fs = source(tmp_path)
    hostile = {"jsonrpc": "2.0", "method": "textDocument/didOpen",
               "params": {"textDocument": {"uri": fs.as_uri()}}}
    received, proc = run_proxy([
        initialize(tmp_path),
        hostile,
        some_request(),
    ])
    assert "textDocument/documentSymbol" in methods(received)
    assert proc.returncode == 0


def test_unreadable_tracked_file_fails_open(run_proxy, tmp_path):
    fs = source(tmp_path)
    received, proc = run_proxy([
        initialize(tmp_path),
        did_open(fs, fs.read_text()),
        MutateThen(lambda _: fs.unlink() or []),
        some_request(),
    ])
    assert "textDocument/didClose" not in methods(received)
    assert "textDocument/documentSymbol" in methods(received)
    assert proc.returncode == 0
