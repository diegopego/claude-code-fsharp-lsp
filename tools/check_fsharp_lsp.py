#!/usr/bin/env python3
"""Check that Claude Code will be able to start the F# language server.

`.lsp.json` tells Claude Code to run `fsautocomplete` for .fs/.fsi/.fsx —
launched through `fsac_sync_proxy.py`, the sibling script that keeps the
server's buffers synced to the disk (its docstring carries the why). The
server itself is a **bare command**, so the main thing that decides whether
F# works is whether `fsautocomplete` resolves on the PATH of the process that
launched Claude Code.

This script asks exactly that question, the same way, and nothing more. It does
not look in `~/.dotnet/tools` or anywhere else. Finding a binary there would
prove nothing, because the server cannot use it either — and reporting it as
healthy would be worse than saying nothing at all.

Why it exists: of the three ways F# support breaks, two announce themselves.

    "No LSP server available for file type: .fs"
        No server is registered. The plugin is not installed or not enabled.

    "Couldn't find <file> in LoadedProjects"
        A server IS running; that file belongs to a project outside the
        directory Claude Code was launched in.

    a hang, or silence
        fsautocomplete is not on PATH, or is there but will not run. NOTHING
        reports this — the server dies before the LSP handshake completes, so
        the tool waits rather than failing.

Only the third is silent, and it is the one this script exists for.

Presence is not health, so the check EXECUTES the binary rather than testing for
a file: one that exists but dies on startup produces the same silent hang.

Usage:
    check_fsharp_lsp.py [PROJECT] [--hook]

PROJECT is optional: the directory holding the .fsproj — often NOT the repo
root — checked for existence and for having been restored.

--hook is how the plugin runs this at session start: silent when healthy, and
never fails the session.

Exit codes: 0 healthy | 2 something is wrong (always 0 under --hook)
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

INSTALL_HINT = (
    "Install it with 'dotnet tool install -g fsautocomplete', then make sure the "
    "global tools directory (~/.dotnet/tools on Linux and macOS) is on the PATH of "
    "the process that launches Claude Code. A login shell rc file is not always "
    "enough, and that gap is the most common cause of this."
)


def check(project: str | None, hook: bool) -> int:
    problems: list[str] = []
    notes: list[str] = []

    if sys.version_info < (3, 9):
        problems.append(
            f"Python {sys.version_info.major}.{sys.version_info.minor} is too old; "
            f"3.9 or newer is required.")
    else:
        notes.append(f"python {sys.version_info.major}.{sys.version_info.minor}")

    # The whole point: resolve it the way .lsp.json will. PATH, nothing else.
    binary = shutil.which("fsautocomplete")
    if binary is None:
        problems.append(f"fsautocomplete is not on PATH. {INSTALL_HINT}")
    else:
        try:
            probe = subprocess.run([binary, "--version"], capture_output=True,
                                   text=True, timeout=30)
        except OSError as e:
            problems.append(f"fsautocomplete at {binary} could not be executed: {e}")
        except subprocess.TimeoutExpired:
            problems.append(
                f"fsautocomplete at {binary} did not answer --version within 30s. "
                f"It is on PATH but not healthy; the LSP tool will hang on it.")
        else:
            if probe.returncode != 0:
                detail = (probe.stderr or probe.stdout).strip().splitlines()
                problems.append(
                    f"fsautocomplete at {binary} exited {probe.returncode} for "
                    f"--version: {detail[0] if detail else '(no output)'}")
            else:
                version = probe.stdout.strip().split("+")[0] or "unknown"
                notes.append(f"fsautocomplete {version}  ({binary})")

    # The server is launched through the sync proxy sitting beside this script.
    # If that file is missing or does not parse, the launch dies before the LSP
    # handshake — the same silent hang as a missing binary, so it is checked
    # the same way: by what would actually run, not by mere presence.
    proxy = Path(__file__).resolve().parent / "fsac_sync_proxy.py"
    try:
        compile(proxy.read_text(encoding="utf-8"), str(proxy), "exec")
    except OSError as e:
        problems.append(
            f"fsac_sync_proxy.py is unreadable: {e}. The plugin launches "
            f"fsautocomplete through it, so the LSP tool will hang. Reinstall "
            f"the plugin.")
    except SyntaxError as e:
        problems.append(
            f"fsac_sync_proxy.py does not parse (line {e.lineno}): {e.msg}. "
            f"The plugin launches fsautocomplete through it, so the LSP tool "
            f"will hang. Reinstall the plugin.")
    else:
        if os.environ.get("FSHARP_LSP_SYNC", "").lower() == "off":
            notes.append("sync proxy present but OFF (FSHARP_LSP_SYNC=off): "
                         "server buffers will go stale after edits")
        else:
            notes.append("sync proxy ok")

    # Diagnostic, never a gate. 'dotnet tool install -g fsautocomplete' cannot
    # succeed without an SDK, and FSAC ships net8.0/net9.0/net10.0 builds — so
    # anyone holding the binary already has a working one. All this earns is
    # that a bug report arrives carrying the version.
    dotnet = shutil.which("dotnet")
    if dotnet is None:
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
            notes.append("dotnet sdk " + (", ".join(sdks) if sdks
                                          else "none reported"))

    if project:
        root = Path(project)
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
                        f"'dotnet restore' in {root} — fsautocomplete loads through "
                        f"MSBuild and cannot analyse an unrestored project.")
                else:
                    notes.append(f"{len(found)} restored project(s) under {root}")

    # Hook mode: say nothing when healthy, and never fail the session.
    if hook:
        for p in problems:
            print(f"fsharp-lsp: {p}")
        return 0

    for n in notes:
        print(f"  ok    {n}")
    for p in problems:
        print(f"  FAIL  {p}", file=sys.stderr)
    return 2 if problems else 0


def main() -> int:
    p = argparse.ArgumentParser(
        prog="check_fsharp_lsp.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("project", nargs="?",
                   help="optional: also check this workspace root is usable — the "
                        "directory holding the .fsproj, often NOT the repo root")
    p.add_argument("--hook", action="store_true",
                   help="silent when healthy; report to stdout and always exit 0")
    args = p.parse_args()
    return check(args.project, args.hook)


if __name__ == "__main__":
    sys.exit(main())
