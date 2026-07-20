#!/usr/bin/env python3
"""Rename one F# symbol across a workspace, using fsautocomplete.

Claude Code's LSP tool has nine operations and every one of them is a read, so
there is no semantic rename for F# by any other route. This fills that gap and
nothing else: it renames a symbol. It does not list references, report
diagnostics or enumerate symbols — the LSP tool already does those, against a
warm server, and duplicating it is what got this plugin's previous CLI removed.

    rename_fsharp_symbol.py PROJECT FILE LINE COL NEW_NAME [--apply] [--expect N]

PROJECT is the directory fsautocomplete loads as the workspace root — the one
holding the .fsproj, which is often NOT the repository root. FILE resolves from
the current directory. LINE and COL are 1-based, as an editor reports them;
passing line-1 lands on the attribute or doc comment above your target and
renames a different symbol with complete confidence.

DRY RUN IS THE DEFAULT. It prints every edit it would make and writes nothing,
so running it to see the blast radius is always safe. --apply writes.

Standard library only, and it resolves `fsautocomplete` from PATH exactly as
.lsp.json does.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

# fsautocomplete loads the whole MSBuild graph on initialize, so a real solution
# takes tens of seconds before it can answer anything. The ceiling is generous
# because the alternative — timing out on a large but healthy project — looks
# exactly like a hang to the caller.
LOAD_TIMEOUT = 180.0
REQUEST_TIMEOUT = 120.0

EXIT_OK = 0
EXIT_NOTHING = 1
EXIT_ENV = 2
EXIT_REFUSED = 3
EXIT_MISMATCH = 4
EXIT_CONFLICT = 5


class LspError(RuntimeError):
    pass


class Refused(RuntimeError):
    """The server answered, and the answer is one this tool declines to apply.

    Distinct from LspError because it is not an environment or protocol
    problem: the exchange worked and the result is being turned down.
    """


class LspClient:
    """Minimal JSON-RPC client over stdio.

    It handles the two things that deadlock when ignored: server-initiated
    requests have to be answered, and notifications arrive interleaved with the
    response being waited on.
    """

    def __init__(self, command: str, root: Path):
        self.root = root.resolve()
        self._next_id = 0
        self._responses: dict[int, dict] = {}
        self._arrived = threading.Condition()

        self.proc = subprocess.Popen(
            [command],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            cwd=str(self.root),
        )
        threading.Thread(target=self._read_loop, daemon=True).start()

    # -- wire format ------------------------------------------------------

    def _write(self, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        assert self.proc.stdin is not None
        self.proc.stdin.write(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body)
        self.proc.stdin.flush()

    def _read_loop(self) -> None:
        stream = self.proc.stdout
        assert stream is not None
        while True:
            length = None
            while True:  # headers, terminated by a blank line
                line = stream.readline()
                if not line:
                    return
                line = line.strip()
                if not line:
                    break
                if line.lower().startswith(b"content-length:"):
                    length = int(line.split(b":", 1)[1])
            if length is None:
                continue
            body = stream.read(length)
            if not body:
                return
            try:
                self._dispatch(json.loads(body))
            except json.JSONDecodeError:
                continue

    def _dispatch(self, msg: dict) -> None:
        if "id" in msg and "method" not in msg:
            with self._arrived:
                self._responses[msg["id"]] = msg
                self._arrived.notify_all()
            return
        if "id" in msg and "method" in msg:
            # Server -> client request. Answering keeps the server from blocking
            # on us; workspace/configuration is the one FSAC actually sends.
            items = msg.get("params", {}).get("items", [])
            result = [{} for _ in items] if msg["method"] == "workspace/configuration" else None
            self._write({"jsonrpc": "2.0", "id": msg["id"], "result": result})

    # -- rpc --------------------------------------------------------------

    def request(self, method: str, params: dict, timeout: float = REQUEST_TIMEOUT) -> Any:
        self._next_id += 1
        rid = self._next_id
        self._write({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        with self._arrived:
            if not self._arrived.wait_for(lambda: rid in self._responses, timeout=timeout):
                raise LspError(f"{method}: no response after {timeout:.0f}s")
            msg = self._responses.pop(rid)
        if "error" in msg:
            raise LspError(f"{method}: {msg['error'].get('message', msg['error'])}")
        return msg.get("result")

    def notify(self, method: str, params: dict) -> None:
        self._write({"jsonrpc": "2.0", "method": method, "params": params})

    # -- lifecycle --------------------------------------------------------

    def initialize(self) -> None:
        self.request(
            "initialize",
            {
                "processId": os.getpid(),
                "rootUri": self.root.as_uri(),
                "workspaceFolders": [{"uri": self.root.as_uri(), "name": self.root.name}],
                # Without this FSAC answers "Couldn't find <file> in LoadedProjects".
                "initializationOptions": {"AutomaticWorkspaceInit": True},
                "capabilities": {
                    "workspace": {
                        "applyEdit": True,
                        "workspaceEdit": {"documentChanges": True},
                        "configuration": True,
                    },
                    "textDocument": {
                        "rename": {"prepareSupport": False},
                        "synchronization": {"didSave": True, "didChange": 1},
                    },
                },
            },
            timeout=LOAD_TIMEOUT,
        )
        self.notify("initialized", {})

    def open(self, path: Path) -> str:
        uri = path.resolve().as_uri()
        self.notify("textDocument/didOpen", {
            "textDocument": {
                "uri": uri,
                "languageId": "fsharp",
                "version": 1,
                "text": read_source(path),
            }
        })
        return uri

    def shutdown(self) -> None:
        try:
            self.request("shutdown", {}, timeout=10)
            self.notify("exit", {})
        except Exception:
            pass
        try:
            self.proc.terminate()
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()


# -- source text -----------------------------------------------------------


def read_source(path: Path) -> str:
    """Read a file preserving its line terminators exactly.

    newline="" matters. The default translates CRLF to \\n on the way in and
    back to os.linesep on the way out, so on a CRLF checkout a one-symbol rename
    would rewrite every line ending in the file — a three-line change arriving
    as a whole-file diff.
    """
    with open(path, encoding="utf-8", newline="") as fh:
        return fh.read()


def line_starts(text: str) -> list[int]:
    """Offset at which each line begins.

    Scans for \\n only, rather than using str.splitlines, which also breaks on
    vertical tab, form feed and U+2028/U+2029. LSP does not count those as line
    boundaries, so a form feed inside a string literal would silently shift
    every offset below it.
    """
    starts = [0]
    for i, ch in enumerate(text):
        if ch == "\n":
            starts.append(i + 1)
    return starts


def apply_edits(text: str, edits: list[dict]) -> str:
    """Apply TextEdits to one file's text, last position first so that earlier
    offsets stay valid as the text shifts."""
    starts = line_starts(text)

    def offset(pos: dict) -> int:
        return starts[pos["line"]] + pos["character"]

    resolved = sorted(
        ((offset(e["range"]["start"]), offset(e["range"]["end"]), e["newText"])
         for e in edits),
        key=lambda t: t[0],
        reverse=True,
    )
    for start, end, new in resolved:
        text = text[:start] + new + text[end:]
    return text


def write_atomically(path: Path, text: str) -> None:
    """Replace a file's contents without ever leaving it half-written.

    A sibling temporary followed by os.replace means a reader either sees the
    old file or the new one. Across several files this is still not a
    transaction — a crash between two replaces splits the batch — so the claim
    here is per-file atomicity, not an atomic rename.
    """
    tmp = path.with_name(f".{path.name}.rename-tmp")
    try:
        with open(tmp, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        shutil.copymode(path, tmp)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def uri_to_path(uri: str) -> Path:
    return Path(unquote(urlparse(uri).path))


def collect_edits(edit: dict) -> dict[Path, list[dict]]:
    """Normalise both WorkspaceEdit shapes into {path: [TextEdit]}."""
    out: dict[Path, list[dict]] = {}
    for uri, edits in (edit.get("changes") or {}).items():
        out.setdefault(uri_to_path(uri), []).extend(edits)
    for change in edit.get("documentChanges") or []:
        if "textDocument" not in change:
            # A create/rename/delete file operation. A symbol rename does not
            # produce one, so this is either a server bug or something this tool
            # has no business applying blind.
            raise Refused(
                f"the edit contains a file operation, not a text change: "
                f"{change}. Renaming a symbol does not create, rename or delete "
                f"files, so this is not something to apply blind.")
        path = uri_to_path(change["textDocument"]["uri"])
        out.setdefault(path, []).extend(change.get("edits", []))
    return out


def report(by_file: dict[Path, list[dict]], root: Path) -> None:
    """Print every edit as `line:col  old -> new`, so the caller can see what
    would change rather than only how much."""
    for path in sorted(by_file):
        try:
            shown = path.relative_to(root)
        except ValueError:
            shown = path
        print(f"  {shown}")
        text = read_source(path)
        starts = line_starts(text)
        for e in sorted(by_file[path],
                        key=lambda e: (e["range"]["start"]["line"],
                                       e["range"]["start"]["character"])):
            start, end = e["range"]["start"], e["range"]["end"]
            old = text[starts[start["line"]] + start["character"]:
                       starts[end["line"]] + end["character"]]
            print(f"    {start['line'] + 1}:{start['character'] + 1}"
                  f"  {old} -> {e['newText']}")


# -- command ---------------------------------------------------------------


def resolve_fsac() -> str:
    """Find fsautocomplete the way .lsp.json does: as a bare command on PATH.

    Deliberately not overridable by an environment variable. A tool that could
    be pointed elsewhere would be able to succeed against a binary the plugin's
    own server never uses.
    """
    found = shutil.which("fsautocomplete")
    if not found:
        raise LspError(
            "fsautocomplete is not on PATH. Install it with "
            "'dotnet tool install -g fsautocomplete' and make sure the global "
            "tools directory (~/.dotnet/tools) is on the PATH of the process "
            "that launched this. Run tools/check_fsharp_lsp.py to confirm.")
    return found


def cmd_rename(args) -> int:
    root, file = Path(args.project), Path(args.file)
    if not file.exists():
        print(f"ERROR: {file} does not exist", file=sys.stderr)
        return EXIT_ENV

    client = LspClient(resolve_fsac(), root)
    try:
        client.initialize()
        uri = client.open(file)
        # What the server was given. Every offset it returns is relative to
        # this, so if the file no longer matches, the offsets describe a text
        # that no longer exists.
        sent = read_source(file)
        result = client.request("textDocument/rename", {
            "textDocument": {"uri": uri},
            "position": {"line": args.line - 1, "character": args.col - 1},
            "newName": args.newname,
        })
    finally:
        client.shutdown()

    if not result:
        print("REFUSED: the server returned no edit. Either the position holds "
              "no renameable symbol, or it is one fsautocomplete declines to "
              "rename — it refuses Active Patterns and Active Pattern Cases "
              "outright.", file=sys.stderr)
        return EXIT_REFUSED

    by_file = collect_edits(result)
    total = sum(len(e) for e in by_file.values())
    if total == 0:
        print("REFUSED: the server returned an edit containing no changes. "
              "Nothing was written. This is the silent no-op shape, where a "
              "rename reports success having changed nothing.", file=sys.stderr)
        return EXIT_REFUSED

    print(f"{'APPLY' if args.apply else 'DRY RUN'}: rename -> '{args.newname}' | "
          f"{len(by_file)} file(s), {total} edit(s)")
    report(by_file, root.resolve())

    if args.expect is not None and total != args.expect:
        print(f"MISMATCH: expected {args.expect} edit(s), the server returned "
              f"{total}. Nothing was written. Either the position is not the "
              f"symbol you meant, or the code moved since you counted.",
              file=sys.stderr)
        return EXIT_MISMATCH

    if not args.apply:
        print("\n(dry run — pass --apply to write)")
        return EXIT_OK

    if read_source(file) != sent:
        print(f"CONFLICT: {file} changed while the rename was being computed. "
              f"The edits describe the earlier text, so applying them now would "
              f"corrupt the file. Nothing was written.", file=sys.stderr)
        return EXIT_CONFLICT

    # Compute everything before writing anything, so a file that fails to read
    # or a stale offset stops the batch while it is still entirely on disk.
    staged: list[tuple[Path, str]] = []
    for path, edits in sorted(by_file.items()):
        current = read_source(path)
        staged.append((path, apply_edits(current, edits)))

    for path, text in staged:
        write_atomically(path, text)
    print(f"\nWrote {len(staged)} file(s).")
    return EXIT_OK


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("project", help=(
        "workspace root for fsautocomplete to load: the directory holding the "
        ".fsproj, which is often NOT the repository root"))
    p.add_argument("file", help="the .fs/.fsi/.fsx file holding the symbol")
    p.add_argument("line", type=int, help=(
        "1-based line, as an editor reports it; passing line-1 lands on the "
        "attribute or doc comment above the symbol and renames the wrong one"))
    p.add_argument("col", type=int, help="1-based column, as an editor reports it")
    p.add_argument("newname", help="the replacement identifier")
    p.add_argument("--expect", type=int, metavar="N", help=(
        "refuse unless the server returns exactly N edits. Take N from the LSP "
        "tool's findReferences at the same position, so the number is the "
        "compiler's rather than a guess"))
    p.add_argument("--apply", action="store_true", help=(
        "write the edits to disk. Without this nothing is modified, so an "
        "exploratory run is always safe"))

    args = p.parse_args()
    try:
        return cmd_rename(args)
    except Refused as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return EXIT_REFUSED
    except LspError as e:
        print(f"LSP ERROR: {e}", file=sys.stderr)
        return EXIT_ENV
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return EXIT_ENV


if __name__ == "__main__":
    sys.exit(main())
