# claude-code-fsharp-lsp

A Claude Code plugin providing F# code intelligence via [fsautocomplete](https://github.com/ionide/FsAutoComplete) (FSAC), plus `tools/fsharp_lsp.py` — a standalone read-only CLI that answers questions about F# projects the built-in `LSP` tool cannot reach.

See [README.md](README.md) for installation, prerequisites and usage.

## Hard constraints

These are decisions already made. Do not revisit them without asking.

**`tools/fsharp_lsp.py` stays read-only.** The `rename` and `code-action` write paths were built, verified end to end, then deliberately commented out. Leave them commented. A tool that ships inside a repository must not be able to rewrite it.

**`tools/fsharp_lsp.py` stays standard-library-only.** No runtime dependencies, ever. pytest is a dev dependency and must never be imported by the tool.

**Positions on the CLI are 1-based**, line and column, as an editor reports them; the tool converts to LSP's 0-based internally. This convention is load-bearing — an off-by-one lands on the attribute or doc comment above the target and returns confident results for the wrong symbol.

**Distribution is self-hosted.** This repo is the single source of truth for the plugin's files. A third-party catalogue may only ever *point at* this repo; its files must never be copied into another organisation's repository. A vendored copy goes stale the moment this repo moves on, and the copy — not the original — is what users install.

**Every release bumps `version` in `.claude-plugin/plugin.json`.** Claude Code re-pulls github-sourced marketplaces automatically, so an unbumped version is how a stale copy survives unnoticed.

**No PyPI package.** One published artifact. Revisit only if a user asks after release.

## Running things

```bash
python3 -m pytest                  # unit tests — fast, no .NET needed
python3 -m pytest -m integration   # real fsautocomplete — needs the .NET SDK
python3 tools/fsharp_lsp.py doctor # is the environment actually usable?
python3 tools/fsharp_lsp.py --help
```

`pytest` is not on PATH as a bare command; always invoke it as `python3 -m pytest`.

`dotnet` needs no environment setup — it resolves from PATH. Do **not** export `DOTNET_ROOT` or prepend a specific .NET install to PATH; see below for why that can silently switch SDKs.

## Environment

- **Requires .NET SDK 10** and the F# fixture project targets `net10.0`.
- **Requires `fsautocomplete` on PATH.** Install it with `dotnet tool install -g fsautocomplete`, then make sure the global tools directory (`~/.dotnet/tools` on Linux and macOS) is on the PATH of the process that launches Claude Code — a login shell rc file is not always enough. Verify with `fsautocomplete --version`. The CLI honours `FSAC_PATH` if you need to point at a specific binary; the published `.lsp.json` uses the bare command name so it resolves from PATH like any other LSP plugin.
- **Never export `DOTNET_ROOT` and never reorder PATH to favour one .NET install.** Multiple SDKs commonly coexist on one machine (a distro package, a user install under `~/.dotnet`, and on WSL the Windows one). Both `dotnet` and `fsautocomplete` already resolve correctly from PATH; forcing either variable can silently change which SDK builds the project, which is a confusing failure to diagnose.

## Testing approach

Unit tests drive `tests/fake_fsac.py`, a scripted stand-in that speaks real Content-Length JSON-RPC over stdio. This exercises the real framing, threading and dispatch without any test seam in shipped code — `LspClient` spawns whatever `FSAC_PATH` points at, so the tests just point it somewhere else.

Integration tests drive real `fsautocomplete` against `tests/fixtures/SampleProject` and are excluded by default.

Expect FSAC to take 15–40s on a cold project and 2–6s warm.

## Note on the fixture project

`tests/fixtures/SampleProject/Broken.fs` is **deliberately uncompilable** — it exists so the diagnostics test has a certain error to find. If you have the F# LSP plugin active in a session opened here, it will report that error. That is expected, not a bug.
