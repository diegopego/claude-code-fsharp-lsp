# claude-code-fsharp-lsp

A Claude Code plugin that registers [fsautocomplete](https://github.com/ionide/FsAutoComplete) (FSAC) as the F# language server, so Claude Code's `LSP` tool works on `.fs`, `.fsi` and `.fsx`. Five files do the work: `.lsp.json` registers the server, `tools/fsac_sync_proxy.py` sits on the server's stdio and keeps its buffers synced to the disk (Claude Code's own client does not), `skills/fsharp-code-intelligence/` teaches Claude how to use it, `tools/check_fsharp_lsp.py` diagnoses the ways it can break silently, and `tools/rename_fsharp_symbol.py` does the one thing the `LSP` tool cannot.

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

**Claude Code's interactive LSP client never tells the server about a write.**
Measured at the wire 2026-07-21 (Claude Code 2.1.215): after an Edit-tool
change, the interactive client sent **no `didChange` at all** — while the
headless `-p` client sent a correct full-text `didChange` v2 for the same
action. Without intervention the server's buffer freezes at first-query
content for the whole session (measured 2026-07-20: 40+ minutes, Edit did not
resync, hover past the frozen buffer's last line errored while the disk had
more lines). Killing the server does not recover — the client keeps a zombie
connection refusing every call — and no mid-session restart exists. That is
why `.lsp.json` launches FSAC through `tools/fsac_sync_proxy.py`, and why that
proxy is wired the exact way the bench validated: resync from disk before each
request, server-open changed never-opened files, then a same-text bumped-version
`didChange` to every tracked doc — without that last nudge, cross-file answers
stay stale forever (measured; FSAC does not re-typecheck dependents on its
own). `FSHARP_LSP_SYNC=off` reduces the proxy to a pure byte pass-through.
FSAC itself accepts a rangeless full-text `didChange` regardless of version
number — also measured, so version games are not the failure mode here.

**The `LSP` tool's operations are all reads.** That is why
`tools/rename_fsharp_symbol.py` exists and why it is not a duplicate of anything: it is
the write end of the same workflow, not a rival to it. The distinction is load-bearing —
the query CLI this repo removed died of *overlapping* the `LSP` tool, so anything living here
must fill a gap the `LSP` tool cannot reach at all. Verified 2026-07-20 against
fsautocomplete 0.83.0: renaming `double` produced 4 edits across 2 files, left the
unrelated `doubleTrouble` alone, and the project built clean.

**`disable` takes effect immediately; `enable` does not.** Disabling drops the server in
the running session. Enabling does not bring it back until the session restarts. A test
that enables and checks in the same session produces a false negative.

## History: the query CLI, since removed

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
back — note there is no `v1.1.1` tag; tagging stopped at `v1.0.1`. The `rename` it also
carried, commented out, since shipped as its own single-purpose tool rather than as a
subcommand; two of its defects only surfaced on the way (see that commit). Nothing else
in that file is wanted.

## Hard constraints

These are decisions already made. Do not revisit them without asking.

**All three tools stay standard-library-only.** No runtime dependencies, ever.
pytest is a dev dependency and must never be imported by any of them.

**The sync proxy fails open and forwards client bytes verbatim.** An internal
error skips the injection, never the request — stale beats broken, because the
proxy's failure mode must never be worse than the bug it fixes. Client frames
are forwarded raw, not re-serialised: parsing stays a read-only side channel,
so a parsing bug can corrupt tracking but not traffic. `FSHARP_LSP_SYNC=off`
must remain a *pure* pass-through that runs no parser at all — when the valve
exists because the proxy itself is suspected, the off position must not run
the suspect's code. Each of these is pinned by a mutation-verified test.

**`rename_fsharp_symbol.py` renames a symbol and never grows a second job.** No
`references`, no `symbols`, no `diagnostics` — the `LSP` tool answers those, and
*overlapping it* is precisely what killed the query CLI this repo removed. A need that does not
fit "rename one symbol" is a different tool with a different name, not a flag on this one.

**Dry run stays the default there, and every guard keeps a mutation test.** An
exploratory run must never write. The guards are listed in commit `b4c2aa7`; each was
broken in turn and watched to fail. The first attempt at the file-operation test survived
deletion of its own guard, because a *different* guard caught the case and the assertion
was only `!= 0` — when adding a guard, assert the specific refusal, not merely failure.

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

## Running things

```bash
python3 -m pytest          # the whole suite — about a second, no .NET needed
python3 tools/check_fsharp_lsp.py    # is the environment actually usable?
python3 tools/check_fsharp_lsp.py --help
```

`pytest` is not on PATH as a bare command; always invoke it as `python3 -m pytest`.

The `Makefile` is the workflow entrypoint — run `make help` for targets grouped by
phase. Note `make test` does more than bare `python3 -m pytest`: it first syncs the
working tree into the installed plugin and gates docs consistency; `make verify` is
the pre-release gate, and `make release LEVEL=…` / `make publish` carry the release
discipline the Hard constraints describe.

`dotnet` needs no environment setup — it resolves from PATH. Do **not** export
`DOTNET_ROOT` or prepend a specific .NET install to PATH; see below for why that can
silently switch SDKs.

## Environment

- **No particular .NET SDK is required**, by this repo or by users. The suite no longer
  builds any F# project — see Testing approach.
- **Requires `fsautocomplete` on PATH** — without it the `LSP` tool hangs with no diagnosis. See README for install; verify with `fsautocomplete --version` (what `check_fsharp_lsp.py` runs). **Nothing honours `FSAC_PATH` any more**: `.lsp.json` launches the server as a bare command, so a check that honoured it could pass while the server fails.
- **Never export `DOTNET_ROOT` and never reorder PATH to favour one .NET install.** Multiple SDKs commonly coexist on one machine (a distro package, a user install under `~/.dotnet`, and on WSL the Windows one). Both `dotnet` and `fsautocomplete` already resolve correctly from PATH; forcing either variable can silently change which SDK builds the project, which is a confusing failure to diagnose.

## Testing approach

`tests/fake_fsac.py` is a stand-in for the FSAC binary that answers `--version`, and
`FAKE_FSAC_VERSION_FAILS` makes it fail the way a broken install does. It is tested
through a subprocess rather than an import, because the exit code and the stdout/stderr
split are part of what the hook depends on. Its third hat, `FAKE_FSAC_TRANSCRIPT`,
records every message it receives: the sync proxy's whole contract is what reaches the
server and in which order, and only the server can testify to that, so the proxy tests
drive real frames through a real subprocess pipeline and assert on the transcript.

There is no integration leg and no .NET is needed: the suite never speaks to a real
server — the proxy tests reach the stand-in as bare `fsautocomplete` on PATH, the same
resolution production uses. The whole suite runs in about a second.

**Mutation-test the health-check suite before trusting it.** A health check that always
passes is the classic vacuous guard, and this suite has already shipped one: an earlier
version pointed at the stand-in through `FSAC_PATH`, so *no test entered the PATH
resolution branch at all* — deleting the lookup outright left the suite green, while the
real check reported healthy on the exact failure it exists for.

When you add a branch here, add the mutation with it. A branch no test enters is a branch
the next refactor can delete for free.
