---
name: fsharp-lsp-queries
description: Use when you need a compiler-accurate answer about F# code — every reference to a symbol, the diagnostics for a file, or the symbols a file defines — and especially when the file belongs to a project outside the directory Claude Code was launched in, where the built-in LSP tool answers "Couldn't find <file> in LoadedProjects".
---

# Asking fsautocomplete directly

`tools/fsharp_lsp.py` answers questions about F# code by driving its own
`fsautocomplete` process. It is read-only: it cannot rename, apply a code
action, or format. It never writes to your source files.

## When to use this instead of the built-in LSP tool

Reach for the built-in `LSP` tool first for navigation — it is served by a
warm, long-lived server and answers instantly.

Use this CLI when:

- **The file is outside the current workspace.** The built-in tool's server
  loads the projects of the directory Claude Code was launched in, and nothing
  else. This CLI takes the workspace root as an argument.
- **You need diagnostics.** Compiler errors and warnings are not among the
  built-in tool's operations.
- **The answer must be trustworthy rather than fast** — before a rename, or
  when a reference count is about to be relied upon. A fresh server per call
  cannot be serving a stale project graph.

## Usage

```bash
python3 tools/fsharp_lsp.py references  PROJECT FILE LINE COL [--no-config]
python3 tools/fsharp_lsp.py diagnostics PROJECT FILE [--verbose]
python3 tools/fsharp_lsp.py symbols     PROJECT FILE
```

`PROJECT` is the directory FSAC loads as the workspace root — the one holding
the `.fsproj`, which is often **not** the repository root.

Positions are **1-based**, line and column, exactly as an editor reports them.
Passing `line - 1` lands on the attribute or doc comment above your target and
returns confident results for the wrong symbol.

Exit codes: `0` ok, `1` nothing found, `2` LSP or environment error.

Expect 2–6s on a warm project and up to ~40s on a cold one — FSAC loads the
whole MSBuild graph on startup.

## Interpreting the answers

**A name in F# is often both a type and a module.** `grep -c` conflates the
two, and additionally counts comments, string literals, and substrings of
longer identifiers. When a count matters, take it from `references` and
reconcile any difference with the textual count deliberately, rather than
assuming the larger number is the right one.

**`--no-config` exists for A/B-ing.** FSAC gates some behaviour behind
`workspace/didChangeConfiguration`; running with and without it and diffing
the output tells you whether configuration is responsible for what you see.

## When something does not work

Run the check rather than guessing:

```bash
python3 tools/fsharp_lsp.py doctor PROJECT
```

It executes `fsautocomplete` rather than merely looking for it, names which source supplied
the binary, and verifies the project is restored. A hanging or silent built-in `LSP` tool is
almost always one of those three things.

## Prerequisites

`fsautocomplete` (`dotnet tool install -g fsautocomplete`) and Python 3.9+.
If the binary is not at `~/.dotnet/tools/fsautocomplete`, set `FSAC_PATH`.
