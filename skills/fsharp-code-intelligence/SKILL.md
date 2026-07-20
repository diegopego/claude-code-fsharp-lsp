---
name: fsharp-code-intelligence
description: Use whenever working with F# code — reading it, navigating it, or establishing a fact about it before a change. Covers how to get compiler-accurate answers about .fs/.fsi/.fsx in Claude Code: which LSP operations answer which question, why a grep count is not a reference count, how to refactor when no rename operation exists, and what the three distinct "F# is not working" failures mean.
---

# F# code intelligence

Claude Code's `LSP` tool has no F# capability of its own. This plugin's
`.lsp.json` is what registers `fsautocomplete` for `.fs`, `.fsi` and `.fsx`; the
navigation you get *is* this plugin. An F# extension in the user's editor —
Ionide, say — does not supply it and cannot substitute for it: Claude Code keeps
its own LSP client and its own server registry.

**If the `LSP` tool is not in your toolset, it is deferred rather than absent.**
Load its schema before concluding that F# has no server:

```
ToolSearch "select:LSP"
```

This matters more than it sounds. `Grep` and `Bash` are always loaded, so they
are what you reach for by reflex; a tool whose schema has not been fetched is not
reached for at all. That asymmetry, not a judgement about which tool is better,
is the usual reason F# work drifts into being done by text search.

## Locate with search, confirm with the compiler

A search tool is a legitimate way in. You cannot call `findReferences` without a
line and column, and finding that position is what `Grep` and `Glob` are for.
The mistake is stopping there and reporting what the text search returned.

So: grep to *locate*, LSP to *establish*. Once you hold a position, ask the
compiler — and let its answer be the one you act on and quote. A count that came
from `grep -c` is not a reference count; it conflates a type with a module of
the same name, and adds comments, string literals and substrings of longer
identifiers. Never state one as if it were.

The same applies to a file listing. `ls src/*.fs` does not descend, and an F#
project's directory layout is not its compilation order — the `.fsproj` is.
`workspaceSymbol` and the call-hierarchy operations will find code that a
directory glob walks straight past.

Positions are **1-based**, line and column, as an editor reports them. Passing
`line - 1` lands on the attribute or doc comment above your target and returns a
confident answer about the wrong symbol.

## Which operation answers which question

| question | operation |
|---|---|
| where is this defined? | `goToDefinition` |
| what is its type, and what do the docs say? | `hover` |
| everywhere it is used, with positions | `findReferences` |
| what does this file define? | `documentSymbol` |
| find it by name, anywhere in the workspace | `workspaceSymbol` |
| who calls this? | `incomingCalls` |
| what does this call? | `outgoingCalls` |
| implementations of an interface or abstract member | `goToImplementation` |

That is eight of the tool's nine operations. The ninth, `prepareCallHierarchy`, is a precursor some clients need before the call
operations; here `incomingCalls` and `outgoingCalls` take a position directly, so it never has to be called.

## Renaming a symbol

The `LSP` tool's nine operations are all reads, so renaming is the one thing it
cannot do. `tools/rename_fsharp_symbol.py` is the other half of the same
workflow — read with the tool, write with this — not an alternative to it.

```bash
python3 tools/rename_fsharp_symbol.py PROJECT FILE LINE COL NEW_NAME [--expect N] [--apply]
```

**Look first, then commit to what you saw.**

1. `findReferences` at the declaration. This is how you decide whether to rename
   at all: it gives the compiler's list of every site, `line:column`, grouped by
   file and crossing project boundaries — a symbol in the main project shows its
   uses in the test project too. Count them.
2. Run the rename with no flags. Dry run is the default, so this writes nothing;
   it prints every edit as `line:col  old -> new`.
3. Run it again with `--apply --expect N`, where N is the count from step 1.
   `--expect` is what makes step 1 load-bearing rather than decorative: if the
   server returns a different number, nothing is written and it exits 4.
4. Build. In F# a missed site is `FS0039`, *the value or constructor is not
   defined* — a hard error needing no configuration.

`PROJECT` is the directory holding the `.fsproj`, often **not** the repo root.
Positions are 1-based, as everywhere else here.

**Read the exit code rather than assuming success.** Every non-zero one means
nothing was written:

| exit | meaning |
|---|---|
| 3 | refused. The position holds no renameable symbol, the server returned an edit changing nothing, or the edit carried a file operation. Note fsautocomplete declines Active Patterns and Active Pattern Cases outright |
| 4 | the edit count did not match `--expect` |
| 5 | the file changed while the rename was being computed, so the edits describe text that no longer exists |

It renames a symbol and nothing else — no renaming files, no moving a symbol
between modules, no extract or inline, and it never touches the `.fsproj`, where
F#'s compile order is semantic and a file move is a human decision.

*If the plugin is not installed*, fall back to editing each site from
`findReferences` by hand and letting the build catch what you miss.

## When F# is not working

Three distinct failures, and only one of them is silent. Read the message before
reaching for anything:

| what you see | what it means |
|---|---|
| `No LSP server available for file type: .fs` | no server is registered — this plugin is not installed or not enabled |
| `Couldn't find <file> in LoadedProjects` | a server **is** running; that file belongs to a project outside the directory Claude Code was launched in. Open a session there, or work from the build output |
| a hang, or silence | the server is registered but the binary will not start — almost always `~/.dotnet/tools` missing from the PATH of the process that launched Claude Code |

Only the third is silent. The plugin runs its health check at session start, so
it usually announces itself — but you can ask the same question directly, and it
needs no plugin file:

```bash
fsautocomplete --version
```

`.lsp.json` launches the server as a **bare command**, so PATH is the whole
question: if the shell resolves it, so will Claude Code. `command not found` is
the diagnosis, and the fix is to put the global tools directory (`~/.dotnet/tools`)
on the PATH of the process that launched Claude Code. A binary sitting in that
directory but not on PATH is no use to anyone — do not report it as installed.

One caveat worth stating to the user: your shell's PATH is not necessarily the
PATH of the process that launched their editor.

## Diagnostics are not among the operations

The server publishes compiler errors and warnings continuously, but the `LSP`
tool has no operation to read them. For "did my edit break anything", build:

```bash
dotnet build --no-incremental
```

`--no-incremental` matters. A repeat build re-reports nothing, so warnings you
have not fixed can appear to have gone away. An error also suppresses the
warnings in every file compiled after it, since F# stops there — fix errors
first, then read the warnings.

F#'s compilation order is semantic, so the file your edit breaks is usually one
you did not touch: it is below yours in the `.fsproj`. Never conclude from a
clean-looking file that the project compiles.
