# claude-code-fsharp-lsp

A Claude Code plugin that registers [fsautocomplete](https://github.com/ionide/FsAutoComplete) (FSAC) as the F# language server, so Claude Code's `LSP` tool works on `.fs`, `.fsi` and `.fsx`. Three files do the work: `.lsp.json` registers the server, `skills/fsharp-code-intelligence/` teaches Claude how to use it, and `tools/check_fsharp_lsp.py` diagnoses the one way it can break silently.

See [README.md](README.md) for installation, prerequisites and usage.

## Settled facts

Measured, not reasoned. Do not re-derive these; if you doubt one, re-measure and say so.

**Claude Code's `LSP` tool has no F# capability without this plugin's `.lsp.json`.** It
is a generic client with a per-extension server registry, and nothing registers `.fs` out
of the box. So "Claude Code's LSP tool" and "this plugin" are not alternatives to weigh —
the former's F# support *is* the latter.

**An F# extension in the user's editor does not supply it either.** Verified 2026-07-20:
with this plugin disabled and Ionide 7.31.1 running healthily on four live FSAC
instances, an `LSP` hover on a `.fs` file returned `No LSP server available for file
type: .fs`. Ionide and this plugin drive *different installations* of FSAC — Ionide
bundles its own `fsautocomplete.dll`; this plugin runs the one on PATH.

**Three distinct failures, only one of them silent.** Do not describe them with one
sentence; a user whose PATH is broken reads "it hangs", sees a clear message instead, and
concludes they have a fourth unknown problem.

| symptom | cause |
|---|---|
| `No LSP server available for file type: .fs` | no server registered — plugin not installed or not enabled |
| `Couldn't find <file> in LoadedProjects` | server running; that file's project is outside the launch directory |
| a hang, or silence | server registered, binary will not start — almost always PATH. **the health check exists for this one** |

**The `LSP` tool's operations are all reads.** There is no rename. Refactoring is
`findReferences` for the positions, then an edit per site, then a build — in F# a missed
site is `FS0039`, a hard error, so the compiler catches what you miss.

**`disable` takes effect immediately; `enable` does not.** Disabling drops the server in
the running session. Enabling does not bring it back until the session restarts. A test
that enables and checks in the same session produces a false negative.

## History: the query CLI, removed in 2.0.0

Through 1.1.1 this plugin also shipped `tools/fsharp_lsp.py`, an 861-line standalone LSP
client offering `references`, `symbols` and `diagnostics` against any project on disk. It
worked. It was removed anyway, and the reasoning is worth keeping so it is not
reintroduced by accident:

- **The plugin never needed it.** Proven 2026-07-20 by moving every copy off disk (four,
  counting cached versions and the marketplace checkout), restarting so the server
  spawned with the file absent, and finding `hover` and `findReferences` unchanged —
  56 hits in 4 files, identical to the baseline minutes earlier.
- **It duplicated what the `LSP` tool already did**, byte for byte, at 25–30s per call
  against an instant warm server.
- **Its unique capability — querying a project outside the launch directory — is a
  reading case, not a refactoring one.** Nobody refactors a repo they are not working in,
  and if you are working in it, the `LSP` tool already answers.
- **`diagnostics` was a subproduct that generated more documentation errors than value.**
  Per-file results are actively misleading in F#, where compile order is semantic: a clean
  answer for the file you edited sits happily alongside a failing build, because the
  breakage is *below* it. Three separate documentation passes tried to caveat this and
  each produced a false claim. When prose keeps failing at one spot, the concept is wrong,
  not the wording.

Recoverable from commit `887342b` ("chore: release 1.1.1") if it is ever wanted
back — note there is no `v1.1.1` tag; tagging stopped at `v1.0.1` — most plausibly to
host a `rename`, since the `LSP` tool cannot write and a write path was already built and
verified there before being commented out.

## Hard constraints

These are decisions already made. Do not revisit them without asking.

**`tools/check_fsharp_lsp.py` stays standard-library-only.** No runtime dependencies, ever. pytest
is a dev dependency and must never be imported by it.

**`check_fsharp_lsp.py`'s .NET SDK line is diagnostic, never a gate.** Do not "improve" it into a check
that fails when some SDK version is missing. That was proposed once, with confidence, and
it was wrong: `fsautocomplete` ships net8.0/net9.0/net10.0 builds with `rollForward`, and
`dotnet tool install -g fsautocomplete` cannot succeed without an SDK at all — so anyone
holding the binary already has a working one. The line exists so a bug report arrives
carrying the version. `test_never_fails_over_the_dotnet_sdk` pins this.

**The session-start hook must never fail the session.** `--hook` reports problems on
stdout and always exits 0. Two tests pin this, deliberately using different failures —
one missing binary, one present-but-broken — because a contract that holds for only one
problem is not a contract.

**Distribution is self-hosted.** This repo is the single source of truth for the plugin's
files. A third-party catalogue may only ever *point at* this repo; its files must never be
copied into another organisation's repository. A vendored copy goes stale the moment this
repo moves on, and the copy — not the original — is what users install.

**Every release bumps `version` in `.claude-plugin/plugin.json`.** Claude Code re-pulls
github-sourced marketplaces automatically, so an unbumped version is how a stale copy
survives unnoticed.

**No PyPI package.** One published artifact.

## Running things

```bash
python3 -m pytest          # the whole suite — about a second, no .NET needed
python3 tools/check_fsharp_lsp.py    # is the environment actually usable?
python3 tools/check_fsharp_lsp.py --help
```

`pytest` is not on PATH as a bare command; always invoke it as `python3 -m pytest`.

`dotnet` needs no environment setup — it resolves from PATH. Do **not** export
`DOTNET_ROOT` or prepend a specific .NET install to PATH; see below for why that can
silently switch SDKs.

## Environment

- **No particular .NET SDK is required**, by this repo or by users. The suite no longer
  builds any F# project — see Testing approach.
- **Requires `fsautocomplete` on PATH.** Install it with `dotnet tool install -g fsautocomplete`, then make sure the global tools directory (`~/.dotnet/tools` on Linux and macOS) is on the PATH of the process that launches Claude Code — a login shell rc file is not always enough. Verify with `fsautocomplete --version` — that is the whole test, and it is what `check_fsharp_lsp.py` runs. **Nothing honours `FSAC_PATH` any more**: `.lsp.json` launches the server as a bare command and cannot honour it, so a check that did would be able to pass while the server fails.
- **Never export `DOTNET_ROOT` and never reorder PATH to favour one .NET install.** Multiple SDKs commonly coexist on one machine (a distro package, a user install under `~/.dotnet`, and on WSL the Windows one). Both `dotnet` and `fsautocomplete` already resolve correctly from PATH; forcing either variable can silently change which SDK builds the project, which is a confusing failure to diagnose.

## Testing approach

`tests/fake_fsac.py` is a stand-in for the FSAC binary that answers `--version`, and
`FAKE_FSAC_VERSION_FAILS` makes it fail the way a broken install does. It is tested
through a subprocess rather than an import, because the exit code and the stdout/stderr
split are part of what the hook depends on.

There is no integration leg any more and no .NET is needed: with the LSP client gone,
nothing in this repo speaks to a real server. The whole suite runs in about a second.

**Mutation-test the health-check suite before trusting it.** A health check that always
passes is the classic vacuous guard, and this suite has already shipped one: an earlier
version pointed at the stand-in through `FSAC_PATH`, so *no test entered the PATH
resolution branch at all* — deleting the lookup outright left the suite green, while the
real check reported healthy on the exact failure it exists for.

Verified 2026-07-20, after that was fixed, by breaking six things in turn and watching
the relevant tests fail each time, then restoring to green: the PATH lookup replaced by a
`~/.dotnet/tools` fallback (the original bug), `which()` never failing, the SDK version
parse, the `*/*.fsproj` glob, the hook's exit code, and `FSAC_PATH` being honoured again.

When you add a branch here, add the mutation with it. A branch no test enters is a branch
the next refactor can delete for free.
