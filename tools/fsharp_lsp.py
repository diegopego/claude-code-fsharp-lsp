#!/usr/bin/env python3
"""READ-ONLY LSP queries for F#, driven straight from the shell.

This tool NEVER writes to your source files. It talks JSON-RPC to fsautocomplete
over stdio purely to ask questions:

    references    textDocument/references     all uses of a symbol
    diagnostics   textDocument/publishDiagnostics   compiler errors and warnings
    symbols       textDocument/documentSymbol  what is in a file

It exists because Claude Code's built-in LSP tool is confined to one workspace.
Its server is spawned when the session starts and loads the projects of the
directory Claude Code was launched in; ask it about a file outside that root and
it answers "Couldn't find <file> in LoadedProjects", with no way to point it
elsewhere. This tool takes the workspace root as an argument, so it can answer
questions about any project on disk.

Two lesser reasons. It spawns a fresh server per invocation, so it is immune to
the stale-project-graph failure mode of a long-lived server whose graph is built
once at `initialize` and never rebuilt. And `diagnostics` is not among the
built-in tool's operations at all.

It is NOT more complete than the built-in tool on the operations they share. An
earlier version of this file claimed it was — that `references` returned 56 hits
in 4 files where the built-in tool returned 42 in 2. That measurement was wrong.
Re-run at the correct 1-based position against a freshly started server, the
built-in tool returns the identical 56 in 4, byte-identical per file. The
discrepancy came from an off-by-one position and a stale orphaned server, not
from any limitation of the built-in tool.

It was originally written write-capable (`rename` and `code-action`, both
verified working). Those paths are commented out below rather than deleted; see
the note at the end of this file.

Positions are given 1-based (line and column, as editors and Claude Code's LSP
tool report them) and converted to LSP's 0-based internally.

Usage:
    fsharp_lsp.py doctor       [PROJECT] [--hook]
    fsharp_lsp.py references   PROJECT FILE LINE COL [--no-config]
    fsharp_lsp.py diagnostics  PROJECT FILE [--verbose]
    fsharp_lsp.py symbols      PROJECT FILE

Start with `doctor`: it executes fsautocomplete rather than merely looking for
it, which is the difference between a diagnosis and a hang.

Exit codes: 0 ok | 1 nothing found | 2 LSP or environment error

PROJECT is the directory FSAC should load as the workspace root.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import queue
from pathlib import Path
from typing import Any

FSAC = os.environ.get("FSAC_PATH", str(Path.home() / ".dotnet/tools/fsautocomplete"))

# FSAC loads the whole MSBuild graph on initialize; the first load on a cold
# project is slow. Measured at 15-40s on this repo, so the ceiling is generous.
LOAD_TIMEOUT = 180.0
REQUEST_TIMEOUT = 120.0

# FSAC's code fixes are gated by configuration, not just by the presence of a
# diagnostic: with an empty {"FSharp": {}} it publishes diagnostics but offers no
# actions at all. These are the switches Ionide sets; unionCaseStubGeneration is
# the one that produces the missing-match-cases fix.
FSHARP_SETTINGS = {
    "FSharp": {
        "unionCaseStubGeneration": True,
        "recordStubGeneration": True,
        "interfaceStubGeneration": True,
        "abstractClassStubGeneration": True,
        "resolveNamespaces": True,
        "simplifyNameAnalyzer": True,
        "unusedOpensAnalyzer": True,
        "unusedDeclarationsAnalyzer": True,
        "addPrivateAccessModifier": True,
    }
}


class LspError(RuntimeError):
    pass


class LspClient:
    """Minimal JSON-RPC client over stdio. Handles the parts that deadlock if
    ignored: server-initiated requests must be answered, and notifications
    arrive interleaved with the response we are waiting for."""

    def __init__(self, command: str, root: Path):
        self.root = root.resolve()
        self._next_id = 0
        self._responses: dict[int, dict] = {}
        self._responses_lock = threading.Lock()
        self._arrived = threading.Condition(self._responses_lock)
        self._log: queue.Queue[str] = queue.Queue()
        # FSAC's code fixes are diagnostic-driven: each registers against a
        # warning/error code, so textDocument/codeAction returns nothing unless
        # the matching diagnostic is passed back in the request context.
        self.diagnostics: dict[str, list] = {}
        self._diag_arrived = threading.Condition()

        try:
            self.proc = subprocess.Popen(
                [command],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                cwd=str(self.root),
            )
        except FileNotFoundError:
            raise FileNotFoundError(
                f"fsautocomplete not found at {command}. Install it with "
                f"'dotnet tool install -g fsautocomplete', or point FSAC_PATH "
                f"at the binary."
            ) from None
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    # -- wire format ------------------------------------------------------

    def _write(self, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        assert self.proc.stdin is not None
        self.proc.stdin.write(header + body)
        self.proc.stdin.flush()

    def _read_loop(self) -> None:
        stream = self.proc.stdout
        assert stream is not None
        while True:
            length = None
            # Headers, terminated by a blank line.
            while True:
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
                msg = json.loads(body)
            except json.JSONDecodeError:
                continue
            self._dispatch(msg)

    def _dispatch(self, msg: dict) -> None:
        if "id" in msg and "method" not in msg:
            with self._arrived:
                self._responses[msg["id"]] = msg
                self._arrived.notify_all()
            return
        if "id" in msg and "method" in msg:
            # Server -> client request. Answering keeps FSAC from blocking.
            method = msg["method"]
            if method == "workspace/configuration":
                items = msg.get("params", {}).get("items", [])
                result = [{} for _ in items]
            else:
                result = None
            self._write({"jsonrpc": "2.0", "id": msg["id"], "result": result})
            return
        method = msg.get("method", "")
        if method == "textDocument/publishDiagnostics":
            params = msg.get("params", {})
            with self._diag_arrived:
                self.diagnostics[params.get("uri", "")] = params.get("diagnostics", [])
                self._diag_arrived.notify_all()
        elif method == "window/logMessage":
            self._log.put(str(msg.get("params", {}).get("message", "")))

    def wait_for_diagnostics(self, uri: str, timeout: float = 20.0) -> list:
        """Wait for a non-empty publish for this file. A clean file legitimately
        never produces one, so a timeout is not an error - it returns []."""
        with self._diag_arrived:
            self._diag_arrived.wait_for(
                lambda: self.diagnostics.get(uri), timeout=timeout
            )
            return self.diagnostics.get(uri, [])

    # -- rpc --------------------------------------------------------------

    def request(self, method: str, params: dict, timeout: float = REQUEST_TIMEOUT) -> Any:
        self._next_id += 1
        rid = self._next_id
        self._write({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        with self._arrived:
            deadline_met = self._arrived.wait_for(
                lambda: rid in self._responses, timeout=timeout
            )
            if not deadline_met:
                raise LspError(f"{method}: no response after {timeout:.0f}s")
            msg = self._responses.pop(rid)
        if "error" in msg:
            raise LspError(f"{method}: {msg['error'].get('message', msg['error'])}")
        return msg.get("result")

    def notify(self, method: str, params: dict) -> None:
        self._write({"jsonrpc": "2.0", "method": method, "params": params})

    # -- lifecycle --------------------------------------------------------

    def initialize(self, send_config: bool = True) -> None:
        self.request(
            "initialize",
            {
                "processId": os.getpid(),
                "rootUri": self.root.as_uri(),
                "workspaceFolders": [
                    {"uri": self.root.as_uri(), "name": self.root.name}
                ],
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
                        "codeAction": {
                            "codeActionLiteralSupport": {
                                "codeActionKind": {"valueSet": []}
                            },
                            "resolveSupport": {"properties": ["edit"]},
                        },
                        "synchronization": {"didSave": True, "didChange": 1},
                        "publishDiagnostics": {"relatedInformation": True},
                        "documentSymbol": {"hierarchicalDocumentSymbolSupport": True},
                    },
                },
            },
            timeout=LOAD_TIMEOUT,
        )
        self.notify("initialized", {})
        # FSAC only starts checking files once it has configuration; Ionide sends
        # this and without it no diagnostics are ever published.
        if send_config:
            self.notify("workspace/didChangeConfiguration", {"settings": FSHARP_SETTINGS})

    def drain_log(self) -> list[str]:
        out = []
        while True:
            try:
                out.append(self._log.get_nowait())
            except queue.Empty:
                return out

    def open(self, path: Path) -> str:
        uri = path.resolve().as_uri()
        self.notify(
            "textDocument/didOpen",
            {
                "textDocument": {
                    "uri": uri,
                    "languageId": "fsharp",
                    "version": 1,
                    "text": path.read_text(encoding="utf-8"),
                }
            },
        )
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


# -- WorkspaceEdit ---------------------------------------------------------


def uri_to_path(uri: str) -> Path:
    from urllib.parse import unquote, urlparse

    return Path(unquote(urlparse(uri).path))


# DISABLED - write machinery. Everything below applies a WorkspaceEdit to disk,
# which is exactly what this tool no longer does. Kept verbatim (it was verified
# working: 56 edits / 4 files, build green, 32 tests) so the capability can be
# restored by uncommenting these plus cmd_rename, cmd_code_action, and their two
# subparser blocks in main().
#
# def collect_edits(edit: dict) -> dict[Path, list[dict]]:
#     """Normalise both WorkspaceEdit shapes into {path: [TextEdit]}."""
#     out: dict[Path, list[dict]] = {}
#     for uri, edits in (edit.get("changes") or {}).items():
#         out.setdefault(uri_to_path(uri), []).extend(edits)
#     for change in edit.get("documentChanges") or []:
#         if "textDocument" not in change:
#             # Create/Rename/Delete file operations - not produced by a symbol
#             # rename, and applying them blind would be worse than refusing.
#             raise LspError(f"unsupported file operation in WorkspaceEdit: {change}")
#         path = uri_to_path(change["textDocument"]["uri"])
#         out.setdefault(path, []).extend(change.get("edits", []))
#     return out
#
#
# def apply_edits(path: Path, edits: list[dict]) -> str:
#     """Apply TextEdits to one file's text. Edits are applied last-position-first
#     so earlier offsets stay valid as the text shifts."""
#     lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
#
#     def offset(pos: dict) -> int:
#         line, char = pos["line"], pos["character"]
#         return sum(len(l) for l in lines[:line]) + char
#
#     text = "".join(lines)
#     resolved = sorted(
#         ((offset(e["range"]["start"]), offset(e["range"]["end"]), e["newText"]) for e in edits),
#         key=lambda t: t[0],
#         reverse=True,
#     )
#     for start, end, new in resolved:
#         text = text[:start] + new + text[end:]
#     return text
#
#
# def report(by_file: dict[Path, list[dict]], root: Path) -> int:
#     total = 0
#     for path in sorted(by_file):
#         edits = by_file[path]
#         total += len(edits)
#         try:
#             shown = path.relative_to(root)
#         except ValueError:
#             shown = path
#         lines = sorted({e["range"]["start"]["line"] + 1 for e in edits})
#         print(f"  {shown}: {len(edits)} edit(s) at line(s) {', '.join(map(str, lines))}")
#     return total


# -- commands --------------------------------------------------------------


# DISABLED - rename. Verified working before being switched off: renaming a
# single type produced 56 edits across 4 files (including the separate test
# project), after which the build was clean under TreatWarningsAsErrors and all
# 32 tests passed. Left here verbatim rather than deleted.
#
# def cmd_rename(args) -> int:
#     root, file = Path(args.project), Path(args.file)
#     client = LspClient(FSAC, root)
#     try:
#         client.initialize()
#         uri = client.open(file)
#         result = client.request(
#             "textDocument/rename",
#             {
#                 "textDocument": {"uri": uri},
#                 "position": {"line": args.line - 1, "character": args.col - 1},
#                 "newName": args.newname,
#             },
#         )
#         if not result:
#             print("REFUSED: server returned no WorkspaceEdit "
#                   "(symbol may not support rename)", file=sys.stderr)
#             return 3
#         by_file = collect_edits(result)
#         total = sum(len(e) for e in by_file.values())
#         if total == 0:
#             print("REFUSED: WorkspaceEdit is empty - 0 edits. This is the silent "
#                   "no-op failure mode; nothing was written.", file=sys.stderr)
#             return 3
#
#         print(f"{'APPLY' if args.apply else 'DRY-RUN'}: "
#               f"rename -> '{args.newname}' | {len(by_file)} file(s), {total} edit(s)")
#         report(by_file, root.resolve())
#
#         if args.expect is not None and total != args.expect:
#             print(f"MISMATCH: expected {args.expect} edit(s), server returned {total}. "
#                   f"Nothing written.", file=sys.stderr)
#             return 4
#
#         if not args.apply:
#             print("\n(dry run - pass --apply to write)")
#             return 0
#         for path, edits in by_file.items():
#             path.write_text(apply_edits(path, edits), encoding="utf-8")
#         print(f"\nWrote {len(by_file)} file(s).")
#         return 0
#     finally:
#         client.shutdown()


# DISABLED - code actions. The LISTING half was read-only and harmless; the
# APPLY half is not, so the whole command goes. Verified before switching off:
# on an FS0025 it offered "Generate union pattern match cases (kind=quickfix,
# edit=yes)" and applied it cleanly - but see the note at the end of this file
# about why applying that particular fix is a bad idea in this repo.
#
# def cmd_code_action(args) -> int:
#     root, file = Path(args.project), Path(args.file)
#     client = LspClient(FSAC, root)
#     try:
#         client.initialize()
#         uri = client.open(file)
#         start = {"line": args.line - 1, "character": args.col - 1}
#         end = {
#             "line": (args.end_line or args.line) - 1,
#             "character": (args.end_col or args.col) - 1,
#         }
#         published = client.wait_for_diagnostics(uri)
#         # Pass back only the diagnostics whose lines touch the requested range;
#         # that is what a code fix keys off.
#         in_range = [
#             d for d in published
#             if d["range"]["start"]["line"] <= end["line"]
#             and d["range"]["end"]["line"] >= start["line"]
#         ]
#         print(f"({len(published)} diagnostic(s) in file, {len(in_range)} at this range)")
#         actions = client.request(
#             "textDocument/codeAction",
#             {
#                 "textDocument": {"uri": uri},
#                 "range": {"start": start, "end": end},
#                 "context": {"diagnostics": in_range},
#             },
#         ) or []
#         if not actions:
#             print("No code actions offered at that position.")
#             return 1
#         for i, a in enumerate(actions):
#             title = a.get("title", "<command>")
#             kind = a.get("kind", "-")
#             has_edit = "edit" in a
#             print(f"  [{i}] {title}  (kind={kind}, edit={'yes' if has_edit else 'no'})")
#         if args.pick is None:
#             print("\n(listing only - pass --pick INDEX [--apply] to apply one)")
#             return 0
#
#         chosen = actions[args.pick]
#         edit = chosen.get("edit")
#         if edit is None:
#             resolved = client.request("codeAction/resolve", chosen)
#             edit = (resolved or {}).get("edit")
#         if edit is None:
#             print(f"REFUSED: action '{chosen.get('title')}' carries no edit "
#                   f"(it is a command, which this tool does not execute).", file=sys.stderr)
#             return 3
#         by_file = collect_edits(edit)
#         total = sum(len(e) for e in by_file.values())
#         print(f"\n{'APPLY' if args.apply else 'DRY-RUN'}: {chosen.get('title')} | "
#               f"{len(by_file)} file(s), {total} edit(s)")
#         report(by_file, root.resolve())
#         if not args.apply:
#             print("\n(dry run - pass --apply to write)")
#             return 0
#         for path, edits in by_file.items():
#             path.write_text(apply_edits(path, edits), encoding="utf-8")
#         print(f"\nWrote {len(by_file)} file(s).")
#         return 0
#     finally:
#         client.shutdown()


def cmd_references(args) -> int:
    """Every use of a symbol, as file, line and column -- the compiler's answer
    to "where would a rename have to touch?", which is the question the built-in
    LSP tool cannot answer for a project outside the workspace.

    The per-file count is kept alongside the positions: it is what reconciles
    against a textual grep, and --no-config exists to A/B the
    didChangeConfiguration hypothesis by diffing two runs."""
    root, file = Path(args.project), Path(args.file)
    client = LspClient(FSAC, root)
    try:
        client.initialize(send_config=not args.no_config)
        uri = client.open(file)
        refs = client.request(
            "textDocument/references",
            {
                "textDocument": {"uri": uri},
                "position": {"line": args.line - 1, "character": args.col - 1},
                "context": {"includeDeclaration": True},
            },
        ) or []
        # Keep the per-file count -- it is what reconciles against a textual
        # grep -- but print the position of every hit underneath it, 1-based.
        # A count alone says a symbol is used twice without saying where, which
        # is the half of the answer a refactor cannot act on.
        by_file: dict[Path, list[tuple[int, int]]] = {}
        for r in refs:
            start = r["range"]["start"]
            by_file.setdefault(uri_to_path(r["uri"]), []).append(
                (start["line"] + 1, start["character"] + 1))
        label = "WITHOUT config" if args.no_config else "WITH config"
        print(f"{label}: {len(refs)} reference(s) in {len(by_file)} file(s)")
        for path in sorted(by_file):
            try:
                shown = path.relative_to(root.resolve())
            except ValueError:
                shown = path
            hits = sorted(by_file[path])
            print(f"  {shown}: {len(hits)}")
            for line, col in hits:
                print(f"    {line}:{col}")
        return 0
    finally:
        client.shutdown()


def cmd_diagnostics(args) -> int:
    root, file = Path(args.project), Path(args.file)
    client = LspClient(FSAC, root)
    try:
        client.initialize()
        uri = client.open(file)
        diags = client.wait_for_diagnostics(uri)
        if args.verbose:
            print("--- server log ---")
            for line in client.drain_log()[-40:]:
                print(f"  {line}")
            print(f"--- uris that published: {list(client.diagnostics)} ---")
        if not diags:
            print("No diagnostics.")
            return 0
        for d in diags:
            line = d["range"]["start"]["line"] + 1
            code = d.get("code", "-")
            sev = {1: "error", 2: "warning", 3: "info", 4: "hint"}.get(
                d.get("severity", 0), "?")
            print(f"  line {line}: [{sev} {code}] {d.get('message', '').splitlines()[0]}")
        return 0
    finally:
        client.shutdown()


def cmd_symbols(args) -> int:
    """Smoke test: proves FSAC started, loaded the project, and can analyse."""
    root, file = Path(args.project), Path(args.file)
    client = LspClient(FSAC, root)
    try:
        client.initialize()
        uri = client.open(file)
        syms = client.request(
            "textDocument/documentSymbol", {"textDocument": {"uri": uri}}
        ) or []
        print(f"{len(syms)} top-level symbol(s):")
        for s in syms:
            line = (s.get("range") or s.get("location", {}).get("range", {})) \
                .get("start", {}).get("line", -1)
            print(f"  {s.get('name')}  (line {line + 1})")
        return 0 if syms else 1
    finally:
        client.shutdown()


def cmd_doctor(args) -> int:
    """Check that everything this tool needs is present AND working.

    Presence is not health. A binary can exist, satisfy every "is it installed?"
    check, and fail the instant it runs - and when that happens Claude Code's
    built-in LSP tool hangs rather than reporting anything, because the server
    dies before the handshake completes. So every check here actually executes
    the thing it is checking."""
    problems: list[str] = []
    notes: list[str] = []

    if sys.version_info < (3, 9):
        problems.append(
            f"Python {sys.version_info.major}.{sys.version_info.minor} is too old; "
            f"3.9 or newer is required.")
    else:
        notes.append(f"python {sys.version_info.major}.{sys.version_info.minor}")

    # Report WHERE the binary came from: "not found" and "found, but the wrong
    # one" look identical to a user who does not know which source won.
    explicit = os.environ.get("FSAC_PATH")
    on_path = shutil.which("fsautocomplete")
    if explicit:
        binary, origin = explicit, "FSAC_PATH"
    elif on_path:
        binary, origin = on_path, "PATH"
    else:
        binary, origin = FSAC, "default location"

    if not Path(binary).exists():
        problems.append(
            f"fsautocomplete not found at {binary} (from {origin}). Install it with "
            f"'dotnet tool install -g fsautocomplete', put the install directory on "
            f"PATH, or set FSAC_PATH to the binary.")
    else:
        try:
            probe = subprocess.run([binary, "--version"], capture_output=True,
                                   text=True, timeout=30)
        except OSError as e:
            problems.append(f"fsautocomplete at {binary} could not be executed: {e}")
        except subprocess.TimeoutExpired:
            problems.append(
                f"fsautocomplete at {binary} did not answer --version within 30s. "
                f"It is present but not healthy; the LSP tool will hang on it.")
        else:
            if probe.returncode != 0:
                detail = (probe.stderr or probe.stdout).strip().splitlines()
                problems.append(
                    f"fsautocomplete at {binary} exited {probe.returncode} for "
                    f"--version: {detail[0] if detail else '(no output)'}")
            else:
                version = probe.stdout.strip().split("+")[0] or "unknown"
                notes.append(f"fsautocomplete {version}  ({origin}: {binary})")

    # Diagnostic, never a gate. 'dotnet tool install -g fsautocomplete' cannot
    # succeed without an SDK, and FSAC ships net8.0/net9.0/net10.0 builds - so
    # anyone holding the binary already has a working one. The .NET 10 floor
    # belongs to this repo's fixture, not to users. All this earns is that a bug
    # report arrives carrying the version instead of prompting a round trip.
    dotnet = shutil.which("dotnet")
    if not dotnet:
        notes.append("dotnet not on PATH (only matters if project loading fails)")
    else:
        try:
            sdk_probe = subprocess.run([dotnet, "--list-sdks"], capture_output=True,
                                       text=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            notes.append(f"dotnet at {dotnet} did not answer --list-sdks")
        else:
            # Each line is "<version> [<path>]"; the version is all we report.
            sdks = [line.split()[0] for line in sdk_probe.stdout.splitlines()
                    if line.strip()]
            notes.append(f"dotnet sdk {', '.join(sdks) if sdks else 'none installed'}")

    if args.project:
        root = Path(args.project)
        if not root.is_dir():
            problems.append(f"project directory does not exist: {root}")
        else:
            found = sorted(root.glob("*.fsproj")) + sorted(root.glob("*/*.fsproj"))
            if not found:
                problems.append(
                    f"no .fsproj under {root}. PROJECT must be the directory holding "
                    f"the project file, which is often not the repo root.")
            else:
                stale = [p for p in found
                         if not (p.parent / "obj" / "project.assets.json").exists()]
                if stale:
                    problems.append(
                        f"not restored: {', '.join(p.name for p in stale)}. Run "
                        f"'dotnet restore' in {root} - fsautocomplete loads through "
                        f"MSBuild and cannot analyse an unrestored project.")
                else:
                    notes.append(f"{len(found)} restored project(s) under {root}")

    # Hook mode: say nothing when healthy, and never fail the session.
    if args.hook:
        for p in problems:
            print(f"fsharp-lsp: {p}")
        return 0

    for n in notes:
        print(f"  ok    {n}")
    for p in problems:
        print(f"  FAIL  {p}", file=sys.stderr)
    return 2 if problems else 0


# Help for the positionals that are easy to get wrong. The module docstring
# covers both conventions, but argparse only shows that on the top-level
# `--help`; a reader who goes straight to `references --help` sees the
# subparser alone, so the warnings have to live on the arguments themselves.
HELP_PROJECT = ("workspace root for FSAC to load: the directory holding the "
                ".fsproj, which is often NOT the repository root")
HELP_FILE = "the .fs/.fsi/.fsx file to ask about"
HELP_LINE = ("1-based line, as an editor reports it; passing line-1 lands on "
             "the attribute or doc comment above the symbol and answers "
             "confidently about the wrong one")
HELP_COL = "1-based column, as an editor reports it"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    # DISABLED - the two write subcommands. Uncomment together with cmd_rename,
    # cmd_code_action and the WorkspaceEdit helpers to restore write capability.
    #
    # r = sub.add_parser("rename", help="textDocument/rename")
    # r.add_argument("project"); r.add_argument("file")
    # r.add_argument("line", type=int); r.add_argument("col", type=int)
    # r.add_argument("newname")
    # r.add_argument("--expect", type=int,
    #                help="fail unless exactly N edits are returned")
    # r.add_argument("--apply", action="store_true", help="write to disk")
    # r.set_defaults(func=cmd_rename)
    #
    # c = sub.add_parser("code-action", help="textDocument/codeAction")
    # c.add_argument("project"); c.add_argument("file")
    # c.add_argument("line", type=int); c.add_argument("col", type=int)
    # c.add_argument("--end-line", type=int); c.add_argument("--end-col", type=int)
    # c.add_argument("--pick", type=int, help="index of the action to apply")
    # c.add_argument("--apply", action="store_true", help="write to disk")
    # c.set_defaults(func=cmd_code_action)

    f = sub.add_parser("references", help="textDocument/references")
    f.add_argument("project", help=HELP_PROJECT)
    f.add_argument("file", help=HELP_FILE)
    f.add_argument("line", type=int, help=HELP_LINE)
    f.add_argument("col", type=int, help=HELP_COL)
    f.add_argument("--no-config", action="store_true",
                   help="skip didChangeConfiguration (to A/B its effect)")
    f.set_defaults(func=cmd_references)

    d = sub.add_parser("diagnostics", help="list diagnostics for a file")
    d.add_argument("project", help=HELP_PROJECT)
    d.add_argument("file", help=HELP_FILE)
    d.add_argument("--verbose", action="store_true", help="dump server log")
    d.set_defaults(func=cmd_diagnostics)

    s = sub.add_parser("symbols", help="smoke test: document symbols")
    s.add_argument("project", help=HELP_PROJECT)
    s.add_argument("file", help=HELP_FILE)
    s.set_defaults(func=cmd_symbols)

    doc = sub.add_parser("doctor", help="check that dependencies are present and working")
    doc.add_argument("project", nargs="?",
                     help="optional: also check this workspace root is usable")
    doc.add_argument("--hook", action="store_true",
                     help="silent when healthy; report to stdout and always exit 0")
    doc.set_defaults(func=cmd_doctor)

    args = p.parse_args()
    try:
        return args.func(args)
    except LspError as e:
        print(f"LSP ERROR: {e}", file=sys.stderr)
        return 2
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())


# =============================================================================
# CAPABILITIES AND LIMITS  (recorded 2026-07-18, when the write paths were
# switched off). Everything under "verified" was observed running against a
# real multi-project F# solution, not inferred from documentation.
# =============================================================================
#
# ---------------------------------------------------------------------------
# ACTIVE - read-only, verified
# ---------------------------------------------------------------------------
#
#   references    every use of a symbol.  56 refs / 4 files for one type,
#                 byte-identical per file to Claude Code's built-in tool
#                 measured at the same position.  The two agree; see the
#                 correction in the module docstring.
#   diagnostics   compiler errors and warnings.  Caught an FS0025 as
#                 "error 25" (it was an error there, not a warning, because
#                 Directory.Build.props set TreatWarningsAsErrors).
#   symbols       41 symbols in one implementation file, 36 in one test file.
#
# Independent of the Claude Code plugin: it spawns its own fsautocomplete, so
# it kept working while the plugin's LSP was wedged.
#
# ---------------------------------------------------------------------------
# DISABLED - write paths, commented out above (they DID work)
# ---------------------------------------------------------------------------
#
#   rename        renaming one type produced 56 edits across 4 files
#                 including the separate test project; the build was then clean
#                 under TreatWarningsAsErrors and all 32 tests passed.  It is
#                 semantic, not textual: an unrelated member whose name merely
#                 contained the same substring was correctly left alone.
#                 Guards that were exercised: dry-run by default, --apply
#                 required to write, --expect N aborts on a count mismatch
#                 (exit 4), an empty WorkspaceEdit is refused (exit 3) rather
#                 than reported as success - that last one guards the failure
#                 mode in oraios/serena#725, where a rename reported success
#                 having changed 0 files while leaving 17 references untouched.
#
#   code-action   listed and applied "Generate union pattern match cases".
#                 IMPORTANT: that fix generates
#                     | SomeCase(_, _) -> failwith "Not Implemented"
#                 which restores exhaustiveness by turning a COMPILE error into
#                 a RUNTIME bomb - silencing the exact signal this repo turned
#                 on TreatWarningsAsErrors to produce.  Use such a fix to
#                 LOCATE missing cases; write the arms by hand.
#                 Also note code actions are gated by CONFIG, not just by the
#                 presence of a diagnostic: with {"FSharp": {}} FSAC offers
#                 none at all.  The switches are in FSHARP_SETTINGS above.
#
# ---------------------------------------------------------------------------
# WHAT IT CANNOT DO - even with the write paths restored
# ---------------------------------------------------------------------------
#
# Scope of the operation:
#   * Renames symbols only.  No renaming files, no moving a symbol between
#     modules or files, no extract-function, no inline.
#   * No formatting (no textDocument/formatting).  Use the Fantomas CLI, which
#     needs none of this machinery.
#   * FSAC itself disables rename for Active Patterns and Active Pattern Cases.
#
# F#-specific, unverified:
#   * Does not touch the .fsproj.  If a refactor needs a file moved or added,
#     the <Compile Include> ordering is on you - and in F# that order is
#     semantic, not cosmetic.
#   * .fsi signature files: UNTESTED.  This repo has none, so whether rename
#     reaches declarations there was never established.
#   * Type providers: UNTESTED.
#
# Engineering debt in this file:
#   * Covered by tests/ - unit tests drive a scripted fake server, integration
#     tests drive real fsautocomplete against tests/fixtures/SampleProject.
#     Run: python3 -m pytest        (unit only, seconds)
#          python3 -m pytest -m integration   (needs the .NET SDK, ~1 minute)
#   * No conflict detection: if a file changes between the dry run and --apply,
#     the offsets may be stale and nothing checks.
#   * Not atomic: writes file by file, so a crash mid-run leaves a partial
#     application (recoverable via git, but still).
#   * Refuses WorkspaceEdit file operations (create/rename/delete) outright -
#     deliberate, preferring refusal over blind application, but a gap.
#   * --expect existed only on rename, never on code-action.
#   * Spawns a fresh FSAC per invocation (~2-6s warm, up to ~40s cold).  Not a
#     long-lived server; for casual navigation inside the current workspace a
#     warm built-in server is faster and just as complete.
#   * F# only: languageId and the FSAC path are fixed (FSAC_PATH overrides the
#     binary).  This is not a general LSP client.
#
# ---------------------------------------------------------------------------
# WHY THE WRITE PATHS ARE OFF
# ---------------------------------------------------------------------------
#
# Not because they failed - they were verified end to end.  They are off by
# request, so that a tool living in this repository cannot modify source.  The
# read-only half is the part with no downside: it answers questions the
# built-in tool cannot reach - projects outside the current workspace, and
# diagnostics - and it cannot damage anything.
# =============================================================================
