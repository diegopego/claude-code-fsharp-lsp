# claude-code-fsharp-lsp

[![tests](https://github.com/diegopego/claude-code-fsharp-lsp/actions/workflows/tests.yml/badge.svg)](https://github.com/diegopego/claude-code-fsharp-lsp/actions/workflows/tests.yml)

Claude Code ships an `LSP` tool, but it does not speak F#. That tool is generic —
it has code intelligence for a language only where a plugin has registered a
server for that extension, and nothing listens on `.fs` out of the box. There is
no official F# plugin. This is that plugin.

Installing it makes `goToDefinition`, `hover`, `findReferences`, `documentSymbol`,
`workspaceSymbol`, `goToImplementation` and call hierarchy work on `.fs`, `.fsi`
and `.fsx`, served by [fsautocomplete](https://github.com/ionide/FsAutoComplete)
(FSAC).

> **Ionide in your editor does not carry over.** Claude Code keeps its own LSP
> client and its own server registry; a VS Code extension registers with VS Code.
> The two even drive different installations of FSAC — Ionide bundles its own.
> Verified by disabling this plugin with Ionide 7.31.1 running and healthy, four
> live FSAC instances serving the editor, and asking Claude Code for hover on a
> `.fs` file:
>
> ```
> No LSP server available for file type: .fs
> ```

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

Python 3.9+ is used by the session-start health check (standard library only —
nothing to pip install). No particular .NET SDK version is required: if
`dotnet tool install` worked, yours is fine.

## Install

```
/plugin marketplace add diegopego/claude-code-fsharp-lsp
/plugin install fsharp-lsp@claude-code-fsharp-lsp
```

## What changes after you install

Nothing you type. That is the point, and it is why the plugin is easy to
overlook: F# code intelligence simply starts working, and Claude reaches for it
on its own. Ask in plain language —

> where is `advance` used?
>
> what type does `parseWire` return?
>
> who calls this function?

— and Claude answers from the compiler rather than from a text search. You never
name a line, a column, or a tool.

**To confirm it took**, open a session in an F# project and ask Claude for hover
on any `.fs` symbol. A type signature means it is live. See
[When F# is not working](#when-f-is-not-working) for what the failures look like.

## What ships

| file | what it does |
|---|---|
| `.lsp.json` | registers `fsautocomplete` for `.fs`, `.fsi`, `.fsx`. This is the plugin |
| `skills/fsharp-code-intelligence/` | teaches Claude which operation answers which question, and why a `grep` count is not a reference count |
| `tools/check_fsharp_lsp.py` | health check, run automatically at session start |
| `tools/rename_fsharp_symbol.py` | semantic rename — the one operation the `LSP` tool has no equivalent for |

## Renaming

Claude Code's `LSP` tool cannot write — its nine operations are all reads — so
renaming is the one thing it structurally cannot do, and `rename_fsharp_symbol.py`
duplicates nothing. It is the write end of the same workflow: navigate with the
`LSP` tool, rename with this.

```bash
python3 tools/rename_fsharp_symbol.py PROJECT FILE LINE COL NEW_NAME
```

**Dry run is the default.** It prints every edit it would make and changes
nothing, so looking is always safe. Add `--apply` to write, and `--expect N` to
refuse unless exactly N edits come back — take N from `findReferences` at the
same position, so the number is the compiler's rather than a guess.

`PROJECT` is the directory holding the `.fsproj`, which is often not the repo
root. `LINE` and `COL` are 1-based, as an editor reports them.

It is semantic, not textual: renaming `double` leaves `doubleTrouble` alone, and
reaches use sites in other projects that a search of the current directory never
sees. Every non-zero exit means nothing was written — `3` refused, `4` the count
did not match `--expect`, `5` the file changed underneath it.

Then build. In F# a missed site is `FS0039` — *the value or constructor is not
defined* — a hard error needing no configuration, which is why refactoring F# is
far safer than in a dynamically typed language: the failure is loud.

It renames a symbol and nothing else. No renaming files, no moving symbols
between modules, no extract or inline, no formatting — that last one is
[Fantomas](https://fsprojects.github.io/fantomas/)'s job. fsautocomplete itself
declines to rename Active Patterns and Active Pattern Cases.

## Diagnostics

The server publishes compiler errors and warnings continuously, but Claude Code's
`LSP` tool has no operation to read them. For "did my edit break anything", build:

```bash
dotnet build --no-incremental
```

`--no-incremental` matters more than it looks. A repeat build re-reports nothing,
so warnings you have not fixed can appear to have gone away. An error also
suppresses the warnings in every file compiled after it, since F# stops there.

## When F# is not working

Three distinct failures, and only one is silent. Read the message before reaching
for anything:

| what you see | what it means |
|---|---|
| `No LSP server available for file type: .fs` | no server is registered — the plugin is not installed or not enabled |
| `Couldn't find <file> in LoadedProjects` | a server **is** running; that file belongs to a project outside the directory Claude Code was launched in. Open a session there |
| a hang, or silence | the server is registered but the binary will not start — almost always the PATH problem above |

Only the third is silent, and the plugin runs its health check at every session
start to catch it — printing nothing unless something is wrong. To ask the same
question yourself, no plugin file needed:

```bash
fsautocomplete --version
```

That is the entire test. Claude Code launches the server as a bare command, so if
your shell resolves it, so will Claude Code; if `command not found`, that is the
problem and the fix is the PATH note above. Run it in the same environment that
launches Claude Code — a terminal that works proves nothing about an editor
launched from a desktop menu.

The plugin's check adds only two things: it can also verify that a project
directory holds a restored `.fsproj`, and it reports your .NET SDKs so that **if
you open an issue, pasting its output** answers the version questions up front.

```bash
python3 ~/.claude/plugins/cache/claude-code-fsharp-lsp/fsharp-lsp/*/tools/check_fsharp_lsp.py [PROJECT]
```

`PROJECT` is the directory holding the `.fsproj`, which is often not the repo root.

## Tests

```bash
python3 -m pytest
```

About a second, no .NET needed. `tests/fake_fsac.py` stands in for the binary: it
answers `--version` so the health check can be tested against a healthy install, a
missing one and a present-but-broken one, and it speaks enough LSP to answer a
rename with a scripted edit — including the malformed ones each guard exists for.

## Names, disambiguated

Five near-identical names orbit this project, and `/plugin install
fsharp-lsp@claude-code-fsharp-lsp` puts two of them in one line.

| name | what it is |
|---|---|
| `claude-code-fsharp-lsp` | this repository, and the marketplace you add |
| `fsharp-lsp` | the plugin you install |
| `fsharp-code-intelligence` | the skill inside it |
| `fsautocomplete` / FSAC | the F# language server. Not ours — [Ionide's](https://github.com/ionide/FsAutoComplete) |
| Ionide | the VS Code extension. Also not ours, and it does not carry over |

## License

MIT — see [LICENSE](LICENSE).
