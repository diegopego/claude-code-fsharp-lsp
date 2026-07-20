# claude-code-fsharp-lsp

[![tests](https://github.com/diegopego/claude-code-fsharp-lsp/actions/workflows/tests.yml/badge.svg)](https://github.com/diegopego/claude-code-fsharp-lsp/actions/workflows/tests.yml)

F# code intelligence for [Claude Code](https://claude.com/claude-code), in two parts:

1. **An LSP plugin** — wires [fsautocomplete](https://github.com/ionide/FsAutoComplete)
   (FSAC) into Claude Code's built-in `LSP` tool, so `goToDefinition`, `hover`,
   `findReferences`, `documentSymbol` and call hierarchy work on `.fs`, `.fsi` and
   `.fsx` files. There is no official F# plugin; this is that wiring.
2. **A read-only query CLI** — `tools/fsharp_lsp.py`, which drives its own FSAC
   process to answer questions the built-in tool cannot: anything about a project
   outside the current workspace, and compiler diagnostics.

## Prerequisites

```bash
dotnet tool install -g fsautocomplete
```

**`~/.dotnet/tools` must be on the PATH of the process that launches Claude Code**,
or the plugin will not find the server. This is the most common installation
failure — a login shell that has it is not enough if your editor or launcher does
not inherit that PATH. Verify with:

```bash
fsautocomplete --version
```

Python 3.9+ is needed for the CLI (standard library only — nothing to pip install).

## Install the plugin

```
/plugin marketplace add diegopego/claude-code-fsharp-lsp
/plugin install fsharp-lsp@claude-code-fsharp-lsp
```

## Use the CLI

Copy `tools/fsharp_lsp.py` into whatever repository you want to query.

```bash
python3 tools/fsharp_lsp.py doctor      [PROJECT]
python3 tools/fsharp_lsp.py references  PROJECT FILE LINE COL [--no-config]
python3 tools/fsharp_lsp.py diagnostics PROJECT FILE [--verbose]
python3 tools/fsharp_lsp.py symbols     PROJECT FILE
```

**Start with `doctor`.** It checks that `fsautocomplete` is not merely installed but actually
runs, reports which of `FSAC_PATH`, your `PATH` or the default location supplied it, and —
given a `PROJECT` — that the directory really holds a restored `.fsproj`. Each of those
failures is otherwise silent: when the server cannot start, Claude Code's built-in `LSP` tool
hangs rather than reporting anything.

The plugin also runs `doctor` at the start of every session. It prints nothing unless
something is wrong.

`PROJECT` is the directory FSAC loads as the workspace root — the one holding the
`.fsproj`, which is often not the repository root. Positions are **1-based**, as an
editor reports them. Exit codes: `0` ok, `1` nothing found, `2` LSP or environment
error. If FSAC lives somewhere unusual, set `FSAC_PATH`.

Expect 2–6s warm, up to ~40s on a cold project — FSAC loads the whole MSBuild graph
on startup.

## What it will not do

- **It cannot write.** No rename, no code actions, no formatting. The rename and
  code-action paths were built and verified, then deliberately switched off; they
  remain in the file, commented out, with notes on what they did. Formatting is
  Fantomas's job and needs none of this machinery.
- **`.fsi` signature files and type providers are untested.**
- **It is F#-only.** The `languageId` is fixed; this is not a general LSP client.
- **One server per invocation.** For casual navigation the built-in tool's warm
  server is faster.

## Tests

```bash
python3 -m pytest                  # unit tests, seconds — no .NET needed
python3 -m pytest -m integration   # real fsautocomplete, needs the .NET SDK
```

Unit tests drive a scripted fake LSP server (`tests/fake_fsac.py`) over real
JSON-RPC framing. Integration tests drive real FSAC against a small F# project in
`tests/fixtures/SampleProject`.

## License

MIT — see [LICENSE](LICENSE).
