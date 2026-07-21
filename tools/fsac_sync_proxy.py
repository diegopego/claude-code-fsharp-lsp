#!/usr/bin/env python3
"""Keep fsautocomplete's buffers in sync with the disk, from inside the wire.

Claude Code's interactive LSP client opens a document once — the first time a
file is queried — and then never tells the server about a write again. Measured
at the wire on 2026-07-21: after an Edit-tool change, the client sent no
didChange at all (its headless `-p` client sends a correct full-text didChange
v2 for the same action). The server's buffer therefore stays frozen at
first-query content for the whole session, and every later answer about that
file describes the past. Nothing on the client side can be configured to fix
this, and there is no mid-session server restart.

What the plugin does control is the command line the server is launched with.
This proxy sits between the client and the real fsautocomplete:

    client -> fsac_sync_proxy.py -> fsautocomplete

In Claude Code the disk is the truth — every mutation path (Edit tool, sed,
git reset) lands there before the next tool call. So, before forwarding any
client request, the proxy re-reads what the client has opened; where the disk
deviates from what the server was last given, it injects didClose + didOpen
with the current disk content. Files the client never opened are watched via
a stat baseline and server-opened when they change, because in F# a change to
one file invalidates every file after it in compile order. After any injection,
every tracked document also gets a same-text didChange with a bumped version —
without that nudge FSAC keeps answering about dependents from its previous
typecheck (measured: the cross-file case stays stale forever otherwise).

Client bytes are forwarded verbatim, never re-serialised: parsing is a
read-only side channel, so a parsing bug here can corrupt tracking but not
traffic. The sync layer itself fails open — an unreadable file or an internal
error skips the injection and the request goes through as if this proxy were
not there, which degrades to exactly the stale behaviour it exists to fix.

FSHARP_LSP_SYNC=off        pure byte pass-through, no parsing at all — the
                           valve for the day the upstream client is fixed.
FSHARP_LSP_SYNC_SETTLE_MS  how long buffers settle before a query runs after
                           a sync (default 1000). The server typechecks
                           asynchronously; a request racing the re-check gets
                           the previous answer.
FSHARP_LSP_SYNC_LOG        append wire-level diagnostics to this path.

Standard library only. argv is the real server command; bare `fsautocomplete`
by default, resolved from PATH exactly as .lsp.json used to launch it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

SETTLE_MS = int(os.environ.get("FSHARP_LSP_SYNC_SETTLE_MS", "1000"))
LOG_PATH = os.environ.get("FSHARP_LSP_SYNC_LOG")
SOURCE_SUFFIXES = (".fs", ".fsi", ".fsx")
SKIP_DIRS = {"obj", "bin", ".git", "node_modules", "packages", "paket-files"}


def log(message: str) -> None:
    if LOG_PATH:
        try:
            with open(LOG_PATH, "a", encoding="utf-8") as fh:
                fh.write(message + "\n")
        except OSError:
            pass


def read_frame(stream) -> tuple[bytes, dict | None] | None:
    """One Content-Length frame: (raw bytes to forward, parsed body or None).

    The raw bytes are what actually gets forwarded; the parsed body only feeds
    the tracking. A body that does not parse is forwarded anyway — the server
    is entitled to its own opinion about bytes this proxy does not understand.
    """
    header = b""
    length = None
    while True:
        line = stream.readline()
        if not line:
            return None
        header += line
        stripped = line.strip()
        if not stripped:
            break
        if stripped.lower().startswith(b"content-length:"):
            length = int(stripped.split(b":", 1)[1])
    if length is None:
        return None
    body = stream.read(length)
    if len(body) < length:
        return None
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        parsed = None
    return header + body, parsed


def write_frame(stream, payload: dict) -> None:
    body = json.dumps(payload).encode("utf-8")
    stream.write(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body)
    stream.flush()


def uri_to_path(uri: str) -> str:
    return unquote(urlparse(uri).path)


def read_disk(path: str) -> str | None:
    """The file's exact current text, or None for anything unreadable.

    newline="" for the same reason rename_fsharp_symbol.py reads that way: the
    default would translate CRLF on the way in, making disk and didOpen text
    disagree forever on a CRLF checkout — a resync on every single request.
    """
    try:
        with open(path, encoding="utf-8", newline="") as fh:
            return fh.read()
    except (OSError, UnicodeDecodeError):
        return None


class SyncProxy:
    def __init__(self, server_cmd: list[str]):
        self.server = subprocess.Popen(
            server_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        # uri -> text the server was last given (didOpen/didChange, forwarded
        # or injected). Disk deviating from this is what triggers a resync.
        self.given: dict[str, str] = {}
        # uri -> highest document version seen or sent; touches bump past it.
        self.versions: dict[str, int] = {}
        # path -> (mtime_ns, size) for workspace files the client never opened.
        self.unopened: dict[str, tuple[int, int]] = {}
        # monotonic instant of the last buffer change the server has not yet
        # had SETTLE_MS to digest; None once settled.
        self.dirty_since: float | None = None

    # -- observation (read-only against forwarded traffic) ------------------

    def observe(self, msg: dict) -> None:
        method = msg.get("method")
        if method == "initialize":
            self.scan_workspace(msg.get("params") or {})
        elif method == "textDocument/didOpen":
            doc = msg["params"]["textDocument"]
            self.given[doc["uri"]] = doc["text"]
            self.bump_version(doc["uri"], doc.get("version", 1))
        elif method == "textDocument/didChange":
            doc = msg["params"]["textDocument"]
            self.bump_version(doc["uri"], doc.get("version", 1))
            changes = msg["params"].get("contentChanges") or []
            if len(changes) == 1 and "range" not in changes[0]:
                self.given[doc["uri"]] = changes[0]["text"]
            else:
                # Incremental edits are not replayed here; forgetting the text
                # forces a disk comparison to resync on the next request, which
                # is conservative and always ends at the disk's truth.
                self.given.pop(doc["uri"], None)
            self.dirty_since = time.monotonic()
        elif method == "textDocument/didClose":
            self.given.pop(msg["params"]["textDocument"]["uri"], None)

    def bump_version(self, uri: str, seen: int) -> None:
        self.versions[uri] = max(self.versions.get(uri, 0), seen)

    def scan_workspace(self, params: dict) -> None:
        root_uri = params.get("rootUri")
        if not root_uri:
            folders = params.get("workspaceFolders") or []
            root_uri = folders[0]["uri"] if folders else None
        if not root_uri:
            log("no rootUri; workspace watching disabled")
            return
        root = uri_to_path(root_uri)
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for name in filenames:
                if name.endswith(SOURCE_SUFFIXES):
                    path = os.path.join(dirpath, name)
                    try:
                        stat = os.stat(path)
                        self.unopened[path] = (stat.st_mtime_ns, stat.st_size)
                    except OSError:
                        continue
        log(f"watching {len(self.unopened)} unopened workspace files under {root}")

    # -- injection ----------------------------------------------------------

    def sync(self, sin) -> None:
        """Bring the server's view of every known file up to the disk's.

        Runs before each forwarded request. Fails open: a problem here skips
        the injection, never the request.
        """
        injected = False
        for uri in list(self.given):
            disk = read_disk(uri_to_path(uri))
            if disk is None or disk == self.given[uri]:
                continue
            log(f"resync {uri}")
            write_frame(sin, {"jsonrpc": "2.0", "method": "textDocument/didClose",
                              "params": {"textDocument": {"uri": uri}}})
            write_frame(sin, {"jsonrpc": "2.0", "method": "textDocument/didOpen",
                              "params": {"textDocument": {
                                  "uri": uri, "languageId": "fsharp",
                                  "version": 1, "text": disk}}})
            self.given[uri] = disk
            injected = True

        for path, baseline in list(self.unopened.items()):
            try:
                stat = os.stat(path)
            except OSError:
                del self.unopened[path]
                continue
            if (stat.st_mtime_ns, stat.st_size) == baseline:
                continue
            disk = read_disk(path)
            if disk is None:
                continue
            uri = Path(path).as_uri()
            log(f"server-open changed unopened file {path}")
            write_frame(sin, {"jsonrpc": "2.0", "method": "textDocument/didOpen",
                              "params": {"textDocument": {
                                  "uri": uri, "languageId": "fsharp",
                                  "version": 1, "text": disk}}})
            self.given[uri] = disk
            del self.unopened[path]
            injected = True

        if injected:
            # The nudge that makes dependents re-typecheck. Same text, bumped
            # version, sent to every tracked doc — the exact configuration the
            # bench validated; without it cross-file answers stay stale forever.
            for uri in list(self.given):
                version = self.versions.get(uri, 1) + 1
                self.versions[uri] = version
                write_frame(sin, {"jsonrpc": "2.0",
                                  "method": "textDocument/didChange",
                                  "params": {
                                      "textDocument": {"uri": uri, "version": version},
                                      "contentChanges": [{"text": self.given[uri]}]}})
            self.dirty_since = time.monotonic()

    def settle(self) -> None:
        """Give the server its asynchronous typecheck time after buffer churn.

        A request racing the re-check is answered from the previous typecheck —
        both the bench and one live `-p` run caught exactly that. Only elapses
        what is still owed, so a query minutes after an edit pays nothing.
        """
        if self.dirty_since is None:
            return
        owed = SETTLE_MS / 1000.0 - (time.monotonic() - self.dirty_since)
        self.dirty_since = None
        if owed > 0:
            time.sleep(owed)

    # -- pumps --------------------------------------------------------------

    def pump_client(self) -> None:
        cin = sys.stdin.buffer
        sin = self.server.stdin
        assert sin is not None
        while True:
            frame = read_frame(cin)
            if frame is None:
                break
            raw, msg = frame
            if msg is not None:
                is_request = "id" in msg and "method" in msg
                try:
                    self.observe(msg)
                    if is_request and msg["method"] not in ("shutdown", "initialize"):
                        self.sync(sin)
                        self.settle()
                except Exception as exc:  # fail open: stale beats broken
                    log(f"sync layer failed open: {exc!r}")
            sin.write(raw)
            sin.flush()
        try:
            sin.close()
        except OSError:
            pass

    def pump_server(self) -> None:
        out = sys.stdout.buffer
        src = self.server.stdout
        assert src is not None
        while True:
            chunk = src.read1(65536)  # type: ignore[attr-defined]
            if not chunk:
                break
            out.write(chunk)
            out.flush()

    def run(self) -> int:
        threading.Thread(target=self.pump_server, daemon=True).start()
        self.pump_client()
        try:
            self.server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.server.kill()
        return self.server.returncode or 0


def passthrough(server_cmd: list[str]) -> int:
    """FSHARP_LSP_SYNC=off: both directions pumped raw, nothing parsed.

    Deliberately not the SyncProxy with injections disabled: when the valve
    exists because this proxy itself is suspected, the off position must not
    run its parser either.
    """
    server = subprocess.Popen(server_cmd, stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    assert server.stdin is not None and server.stdout is not None

    def pump(src, dst):
        while True:
            chunk = src.read1(65536) if hasattr(src, "read1") else src.read(65536)
            if not chunk:
                break
            dst.write(chunk)
            dst.flush()
        try:
            dst.close()
        except OSError:
            pass

    threading.Thread(target=pump, args=(server.stdout, sys.stdout.buffer),
                     daemon=True).start()
    pump(sys.stdin.buffer, server.stdin)
    try:
        server.wait(timeout=10)
    except subprocess.TimeoutExpired:
        server.kill()
    return server.returncode or 0


def main() -> int:
    server_cmd = sys.argv[1:] or ["fsautocomplete"]
    if os.environ.get("FSHARP_LSP_SYNC", "").lower() == "off":
        return passthrough(server_cmd)
    return SyncProxy(server_cmd).run()


if __name__ == "__main__":
    sys.exit(main())
