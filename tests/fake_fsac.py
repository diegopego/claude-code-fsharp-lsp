#!/usr/bin/env python3
"""A scripted stand-in for fsautocomplete, used to test fsharp_lsp.py.

Speaks the same Content-Length framed JSON-RPC over stdio as the real server,
so the client under test needs no seam. Behaviour comes from a JSON scenario
file named by $FAKE_FSAC_SCENARIO; with no scenario it answers every request
with null and never sends a notification.
"""

import json
import os
import sys


def read_message(stream):
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
    return json.loads(body)


def write_message(stream, payload):
    body = json.dumps(payload).encode("utf-8")
    stream.write(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body)
    stream.flush()


def main():
    if "--version" in sys.argv[1:]:
        if os.environ.get("FAKE_FSAC_VERSION_FAILS"):
            print("fake failure: could not resolve runtime", file=sys.stderr)
            return 1
        print("0.0.0-fake")
        return 0

    scenario = {}
    path = os.environ.get("FAKE_FSAC_SCENARIO")
    if path:
        with open(path, encoding="utf-8") as fh:
            scenario = json.load(fh)

    responses = scenario.get("responses", {})
    errors = scenario.get("errors", {})
    hang = set(scenario.get("hang", []))
    publish_on_open = scenario.get("publish_diagnostics_on_open")
    log_messages = scenario.get("log_messages", [])
    server_requests = scenario.get("server_requests_after_initialized", [])
    record_path = scenario.get("record_path")

    stdin, stdout = sys.stdin.buffer, sys.stdout.buffer
    next_server_id = 1000

    while True:
        msg = read_message(stdin)
        if msg is None:
            return 0
        if record_path:
            with open(record_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(msg) + "\n")

        method = msg.get("method")

        # Client -> server response (to one of our own requests). Nothing to do.
        if "id" in msg and not method:
            continue

        # Client -> server request.
        if "id" in msg and method:
            if method in hang:
                continue
            if method in errors:
                write_message(stdout, {"jsonrpc": "2.0", "id": msg["id"],
                                       "error": errors[method]})
                continue
            default = {} if method == "initialize" else None
            write_message(stdout, {"jsonrpc": "2.0", "id": msg["id"],
                                   "result": responses.get(method, default)})
            continue

        # Notifications.
        if method == "initialized":
            for text in log_messages:
                write_message(stdout, {"jsonrpc": "2.0", "method": "window/logMessage",
                                       "params": {"type": 3, "message": text}})
            for req in server_requests:
                write_message(stdout, {"jsonrpc": "2.0", "id": next_server_id,
                                       "method": req["method"],
                                       "params": req.get("params", {})})
                next_server_id += 1
        elif method == "textDocument/didOpen":
            if publish_on_open is not None:
                uri = msg["params"]["textDocument"]["uri"]
                write_message(stdout, {"jsonrpc": "2.0",
                                       "method": "textDocument/publishDiagnostics",
                                       "params": {"uri": uri,
                                                  "diagnostics": publish_on_open}})
        elif method == "exit":
            return 0


if __name__ == "__main__":
    sys.exit(main())
