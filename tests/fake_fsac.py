#!/usr/bin/env python3
"""A stand-in for the fsautocomplete binary.

It wears three hats, because three different tools drive it.

`--version` is what check_fsharp_lsp.py needs: the check works by EXECUTING the
binary rather than looking for it on disk, so testing it needs something
executable that behaves like FSAC's version flag. Set FAKE_FSAC_VERSION_FAILS to
make it exit non-zero with a runtime error on stderr — the "present but broken"
case, which is the failure that makes the LSP tool hang instead of reporting
anything.

With no arguments it speaks LSP over stdio, which is what rename_fsharp_symbol.py
needs. It answers `initialize` and `shutdown`, and replies to
`textDocument/rename` with whatever WorkspaceEdit is scripted in
FAKE_FSAC_RENAME — the JSON is used verbatim, so a test can script a hostile
response as easily as a well-formed one. Absent that variable it answers null,
which is FSAC's way of saying the symbol cannot be renamed.

Set FAKE_FSAC_TRANSCRIPT to a path and every incoming message — notifications
included — is appended there as one JSON line. That is what
fsac_sync_proxy.py's tests assert against: the proxy's whole contract is *what
reaches the server and in which order*, and only the server can testify to
that. A body that does not parse as JSON is recorded as {"unparseable": true}
rather than crashing, because a proxy forwards bytes it does not understand and
a stand-in that dies on them would be testing its own fragility.

The framing is real Content-Length framing rather than line-delimited JSON. A
stand-in speaking a simpler protocol would let a client with broken framing pass
its tests.
"""

import json
import os
import sys


def read_message(stream):
    """Read one Content-Length framed message. Returns None at end of stream."""
    length = None
    while True:
        line = stream.readline()
        if not line:
            return None
        line = line.strip()
        if not line:
            break
        if line.lower().startswith(b"content-length:"):
            length = int(line.split(b":", 1)[1])
    if length is None:
        return None
    body = stream.read(length)
    if not body:
        return None
    try:
        msg = json.loads(body)
    except json.JSONDecodeError:
        msg = {"unparseable": True}
    if transcript := os.environ.get("FAKE_FSAC_TRANSCRIPT"):
        with open(transcript, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(msg) + "\n")
    return msg


def write_message(stream, payload):
    body = json.dumps(payload).encode("utf-8")
    stream.write(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body)
    stream.flush()


def scripted_rename(params):
    if record := os.environ.get("FAKE_FSAC_RECORD"):
        # So a test can assert on what actually went over the wire — the
        # 1-based-to-0-based conversion is invisible from the outside otherwise.
        with open(record, "w", encoding="utf-8") as fh:
            json.dump(params, fh)

    if victim := os.environ.get("FAKE_FSAC_TOUCHES_FILE"):
        # Simulate the file changing underneath us between the point the client
        # sent its content and the point it would write. Doing it here makes the
        # race deterministic instead of a sleep and a prayer.
        with open(victim, "a", encoding="utf-8") as fh:
            fh.write("\nlet addedBehindOurBack = 1\n")

    raw = os.environ.get("FAKE_FSAC_RENAME")
    if raw is None:
        # FSAC returns null when the symbol does not support rename — Active
        # Patterns, for instance.
        return None
    return json.loads(raw)


def serve() -> int:
    stdin, stdout = sys.stdin.buffer, sys.stdout.buffer
    while True:
        msg = read_message(stdin)
        if msg is None:
            return 0
        method, rid = msg.get("method"), msg.get("id")
        if method == "exit":
            return 0
        if rid is None:
            continue  # a notification; nothing here needs to act on one
        if method == "initialize":
            result = {"capabilities": {"renameProvider": True}}
        elif method == "textDocument/rename":
            result = scripted_rename(msg.get("params", {}))
        elif method == "shutdown":
            result = None
        else:
            write_message(stdout, {
                "jsonrpc": "2.0", "id": rid,
                "error": {"code": -32601, "message": f"unexpected {method}"},
            })
            continue
        write_message(stdout, {"jsonrpc": "2.0", "id": rid, "result": result})


def main() -> int:
    if "--version" in sys.argv[1:]:
        if os.environ.get("FAKE_FSAC_VERSION_FAILS"):
            print("fake failure: could not resolve runtime", file=sys.stderr)
            return 1
        print("0.0.0-fake")
        return 0

    if not sys.argv[1:]:
        return serve()

    print(f"fake_fsac: unexpected argv {sys.argv[1:]}", file=sys.stderr)
    return 64


if __name__ == "__main__":
    sys.exit(main())
