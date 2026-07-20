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
> Verified by disabling this plugin with Ionide running and healthy and asking
> Claude Code for hover on a `.fs` file:
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
not inherit that PATH. Verify with the version flag; the check that matters is
whether the binary *runs*, not whether the install reported success:

<!-- evidence: fsac-version -->
```
$ fsautocomplete --version
0.83.0+96fabed8e9181b74e19e211717626c204c32b2c2
```

Python 3.9+ is used by the session-start health check (standard library only —
nothing to pip install). No particular .NET SDK version is required: if
`dotnet tool install` worked, yours is fine.

## Install

```
/plugin marketplace add diegopego/claude-code-fsharp-lsp
/plugin install fsharp-lsp@claude-code-fsharp-lsp
```

Then restart. Disabling a plugin drops its server immediately, but enabling one
does not bring it back until the session restarts — worth knowing before you
conclude the install failed.

## What changes after you install

Nothing you type. That is the point, and it is why the plugin is easy to
overlook: F# code intelligence simply starts working, and Claude reaches for it
on its own. Ask in plain language —

> where is `renew` used?
>
> what type does `isOverdue` return?
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

The snippets below are all real, captured against the `demo/` project in this
repository — a small library-lending example you can clone and reproduce.

## The refactoring loop

Claude Code's `LSP` tool is entirely reads — nine operations, not one a write. So
renaming is the one thing it cannot do, and the one thing this plugin adds a tool
for. The loop is: look with the compiler, commit to what you saw, let the
compiler have the last word.

Take a real request against the demo: **rename `renew` to `renewLoan`.**

### 1. The reflex answer isn't a reference

A text search is the natural first move, and you would run a good one — anchor
the word, so `renewalLimit`, `RenewalsUsed` and the comments never enter the
count:

<!-- evidence: grep-renew -->
```
$ grep -rnw renew demo --include='*.fs' | sort
demo/LibraryLending.Consumer/Memberships.fs:8:    members |> List.map (renew today)
demo/LibraryLending.Consumer/Renewals.fs:8:    loans |> List.choose (renew today)
demo/LibraryLending/Loan.fs:21:let renew (today: DateOnly) (loan: Loan) =
demo/LibraryLending/Member.fs:11:let renew (today: DateOnly) (m: Member) =
```

The regex is airtight — four hits, every one the exact word `renew`. Two of them
are the wrong function. A library renews two different things, and the demo has a
function for each: `Loan.renew` extends a loan, `Member.renew` extends a
membership. The two declarations differ only in a parameter type, and the two
call sites — `(renew today)` mapped over `loans` in one file, over `members` in
the other — are all but identical. The task is to rename the loan one, and `grep`
cannot see that `Member.fs:11` and `Memberships.fs:8` belong to the other
function, because nothing in the characters says so. No pattern separates them:
the difference is which definition the name resolves to, which is a question about
meaning, not spelling. A count you cannot audit is not a reference count.

### 2. Ask the compiler instead

`findReferences` at the loan declaration returns the compiler's list — every real
site, `line:column`, grouped by file. It keeps two of grep's four and drops the
other two: `Member.renew` and its call are a different binding, and the compiler
knows it even though the spelling is identical. What remains **crosses the project
boundary**: the definition lives in the library, the use in a separate consumer
project.

<!-- evidence: findreferences-renew -->
```
Found 2 references across 2 files:

demo/LibraryLending.Consumer/Renewals.fs:
  Line 8:27

demo/LibraryLending/Loan.fs:
  Line 21:5
```

Two references, exact to the character. Column 27 of `Renewals.fs` line 8 is
where `renew` starts, not where the line does. That is the number to act on.

### 3. Look before you write

`rename_fsharp_symbol.py` with no flags is a dry run: it prints every edit it
would make and changes nothing, so seeing the blast radius is always safe. The
rename is semantic, not textual — it rewrites the two loan sites and leaves
`Member.renew`, the identically-spelled membership function grep could not tell
apart, untouched.

<!-- evidence: rename-dryrun -->
```
$ python3 tools/rename_fsharp_symbol.py demo demo/LibraryLending/Loan.fs 21 5 renewLoan
DRY RUN: rename -> 'renewLoan' | 2 file(s), 2 edit(s)
  LibraryLending/Loan.fs
    21:5  renew -> renewLoan
  LibraryLending.Consumer/Renewals.fs
    8:27  renew -> renewLoan

(dry run — pass --apply to write)
```

Two edits, matching the two references exactly. That agreement is the thing to
check before writing — and `--expect` then enforces it.

### 4. Commit to the count

`--apply --expect N`, where N is the count from step 2. If the server returns a
different number, nothing is written and it exits 4. That is what makes step 2
load-bearing rather than decorative: a rename landing one line off is confident,
plausible, and wrong.

<!-- evidence: rename-apply -->
```
$ python3 tools/rename_fsharp_symbol.py demo demo/LibraryLending/Loan.fs 21 5 renewLoan --apply --expect 2
APPLY: rename -> 'renewLoan' | 2 file(s), 2 edit(s)
  LibraryLending/Loan.fs
    21:5  renew -> renewLoan
  LibraryLending.Consumer/Renewals.fs
    8:27  renew -> renewLoan

Wrote 2 file(s).
```

`PROJECT` is the directory fsautocomplete loads as the workspace root — here
`demo`, which holds the `.slnx` and both projects, and is often not the repo
root. `LINE` and `COL` are 1-based, as an editor reports them.

### 5. Let the compiler have the last word

F# closes the loop in a way most languages cannot. Anything the rename did not
reach is `FS0039` — *the value or constructor is not defined* — a hard error,
with no configuration required to make it one. Here is a rename that renamed the
declaration but missed the cross-project call:

<!-- evidence: build-fs0039 -->
```
$ dotnet build --no-incremental demo/LibraryLending.slnx
demo/LibraryLending.Consumer/Renewals.fs(8,27): error FS0039: The value or constructor 'renew' is not defined. Maybe you want one of the following:   renewLoan   renewalLimit
```

The compiler even names the near-misses — `renewLoan`, `renewalLimit` — the
identifiers an unanchored text search sweeps in. Manual renaming is far safer in
F# than in a dynamically typed language, and this is why: the failure is loud,
immediate, and points at the line.

`--no-incremental` is not decoration. A repeat build re-reports nothing, so
warnings you have not fixed can look as though they went away; and an error
suppresses the warnings in every file compiled after it, since F# stops there.

## Reading without renaming

Most questions never touch a write. `hover` establishes a type before you change
anything — here, whether `isOverdue` takes the date or the loan first:

<!-- evidence: hover-isoverdue -->
```
val isOverdue:
   today: DateOnly ->
   loan : Loan
       -> bool

A loan is overdue once its due date has passed.

Full name: LibraryLending.Loan.isOverdue
Assembly: LibraryLending
```

The signature is the compiler's, doc comment included. `goToDefinition`,
`documentSymbol`, `workspaceSymbol`, `goToImplementation` and the call-hierarchy
operations answer the rest — all reads, all exact.

## When F# is not working

Three distinct failures, and only one is silent. Read the message before reaching
for anything:

| what you see | what it means |
|---|---|
| `No LSP server available for file type: .fs` | no server is registered — the plugin is not installed or not enabled |
| `Couldn't find <file> in LoadedProjects` | a server **is** running; that file belongs to a project outside the directory Claude Code was launched in. Open a session there |
| a hang, or silence | the server is registered but the binary will not start — almost always the PATH problem above |

Only the third is silent, and the plugin runs `check_fsharp_lsp.py` at every
session start to catch it — printing nothing unless something is wrong. Run by
hand it reports every check. Against a working install, with a project directory
passed as the optional argument:

<!-- evidence: check-healthy -->
```
$ python3 tools/check_fsharp_lsp.py demo
  ok    python 3.10
  ok    fsautocomplete 0.83.0  (/home/you/.dotnet/tools/fsautocomplete)
  ok    dotnet sdk 10.0.110
  ok    2 restored project(s) under demo
```

And against a broken one — the binary is installed here, it is simply not on
PATH, and the check refuses to be reassured by finding it elsewhere:

<!-- evidence: check-broken -->
```
$ python3 tools/check_fsharp_lsp.py
  ok    python 3.10
  ok    dotnet sdk 10.0.110
  FAIL  fsautocomplete is not on PATH. Install it with 'dotnet tool install -g fsautocomplete', then make sure the global tools directory (~/.dotnet/tools on Linux and macOS) is on the PATH of the process that launches Claude Code. A login shell rc file is not always enough, and that gap is the most common cause of this.
$ echo $?
2
```

Claude Code launches the server as a bare command, so a copy the shell cannot
resolve is a copy the server cannot start. The check *executes* fsautocomplete
rather than testing for a file, because a binary that exists but dies on startup
produces the same silent hang. Pass a project directory and it also checks the
directory holds a restored `.fsproj`.

## Tests

```bash
python3 -m pytest
```

About a second, no .NET needed. `tests/fake_fsac.py` stands in for the binary: it
answers `--version` so the health check can be tested against a healthy install, a
missing one and a present-but-broken one, and it speaks enough LSP to answer a
rename with a scripted edit — including the malformed ones each guard exists for.
The `demo/` project is the documentation instrument: every snippet above is
captured from it, and a test asserts the two-`renew` decoy still makes an
*anchored* `grep` over-count the loan symbol.

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
