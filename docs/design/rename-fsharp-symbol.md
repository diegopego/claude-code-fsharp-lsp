# Design: `rename_fsharp_symbol.py`

**Status:** design, not implemented
**Target:** 2.1.0
**Supersedes:** the 1.2.0 write-path design, which planned to add `rename` as a
subcommand of a general query CLI. That CLI was removed in 2.0.0; this document
starts from why, so the same shape is not rebuilt by accident.

---

## The vacuum this fills

Claude Code's `LSP` tool has nine operations and **every one of them is a read**.
There is no `textDocument/rename`, no code actions, no formatting. So today there
is no semantic rename for F# in Claude Code by any route at all.

The workaround the skill currently teaches — `findReferences`, edit each site,
`findReferences` again, build — works, and F# makes it unusually safe because a
missed site is `FS0039`, a hard error. But it is N edits done by hand, each an
opportunity to fat-finger, and it cannot see what the compiler sees about
shadowing or scope.

**This is the distinction that matters, and it must survive into the docs:** the
tool removed in 2.0.0 *duplicated* capability the `LSP` tool already had. This one
*fills a vacuum*. That is the whole difference, and it is the sentence that stops
the next reader asking whether the plugin needs it.

## What went wrong last time

Worth stating plainly, because the failure was not technical — the old rename path
was built and verified working before being switched off.

The old CLI offered `references`, `symbols` and `diagnostics`. Every one of those
overlapped something the `LSP` tool already did, or nearly did. Nobody — including
a Claude Code instance reading the plugin's own skill — could state cleanly when to
use which. Consequences, all observed:

- Documentation could not explain the boundary, so three separate passes at it each
  produced a false claim.
- An agent with the plugin installed concluded the plugin was redundant for
  navigation, because the docs argued the CLI's case and left the wiring implicit.
- `diagnostics` in particular reported per-file results in a language whose compile
  order is semantic, so a clean answer routinely coexisted with a failing build.

**The rule this produces:** a tool in this plugin may exist only where the `LSP`
tool cannot reach at all. Overlap is what destroyed the last one.

## Scope

**Does:** rename one F# symbol across the workspace, via `textDocument/rename`.

**Does not, ever:**

- grow a second subcommand — no `references`, no `symbols`, no `diagnostics`;
  those exist in the `LSP` tool and belong there
- rename files, move symbols between modules, extract, or inline
- format (that is Fantomas, which needs none of this)
- touch the `.fsproj` — in F# compile order is semantic, and a refactor needing a
  file moved is a human decision

If a future need does not fit "rename one symbol", it is a different tool with a
different name, not a flag on this one.

## Name

`tools/rename_fsharp_symbol.py`, matching `check_fsharp_lsp.py`: imperative verb,
then exactly what it acts on. It should be impossible to read the filename and
wonder what it does.

## Interface

```
rename_fsharp_symbol.py PROJECT FILE LINE COL NEW_NAME [--apply] [--expect N]
```

| argument | meaning |
|---|---|
| `PROJECT` | directory FSAC loads as workspace root — the one holding the `.fsproj`, often **not** the repo root |
| `FILE` | the `.fs`/`.fsi`/`.fsx` file, resolved from the current directory, **not** from `PROJECT` |
| `LINE` `COL` | **1-based**, as an editor reports them |
| `NEW_NAME` | the replacement identifier |

**Dry run is the default.** It prints every edit it would make, grouped by file, as
`line:col  old → new`, and exits 0. `--apply` is required to write. This is not
politeness: an agent that runs the command to *see* the blast radius must not
change anything by doing so.

Positions are 1-based on the command line and converted to LSP's 0-based
internally. This convention is load-bearing — `line - 1` lands on the attribute or
doc comment above the target and renames a different symbol with full confidence.

## Safety, and what each guard is for

| guard | failure it prevents | exit |
|---|---|---|
| dry run by default | an exploratory run mutating source | 0 |
| `--expect N` | the edit count differing from what the caller believed; abort before writing | 4 |
| refuse an empty `WorkspaceEdit` | reporting success having changed nothing — the [oraios/serena#725](https://github.com/oraios/serena/issues/725) shape, where a rename claimed success while leaving 17 references untouched | 3 |
| refuse `WorkspaceEdit` file operations | a create/rename/delete arriving unnoticed inside an edit | 3 |
| re-read and compare before writing | a file changed between dry run and `--apply`, making offsets stale | 5 |

That last row is new. The old implementation had no conflict detection and said so
in its own notes; it is cheap to add — hash the files named in the dry run, verify
at apply — and without it `--expect` is guarding the wrong end of the operation.

**Not atomic.** It writes file by file, so a crash mid-run leaves a partial
application. Recoverable from git, and the docs must say so rather than implying
transactionality.

## Known limits, to document rather than discover

- **FSAC itself refuses to rename Active Patterns and Active Pattern Cases.** The
  tool must surface that refusal as its own message, not as a confusing empty
  result.
- **`.fsi` signature files: untested.** Whether rename reaches declarations there
  was never established. Either test it or say it is unknown — do not assume.
- **Type providers: untested.**
- **One FSAC per invocation**, so tens of seconds on a real solution. Acceptable
  here in a way it never was for queries: rename is rare, deliberate, and you are
  going to read the dry run anyway.

## The documentation contract

The point of failure last time was documentation, so it is specified here rather
than left to taste.

**`--help` must stand alone.** Someone who runs it with no arguments learns: what
it renames, that positions are 1-based, that dry run is the default, and that
`--apply` writes. No cross-reference required.

**The skill replaces its manual workflow with this tool.** Today
`fsharp-code-intelligence` teaches "refactoring without a rename operation". That
section becomes: *to rename an F# symbol, use `rename_fsharp_symbol.py`* — with the
locate step (`findReferences` to see the blast radius first) kept, because that is
still how you decide whether to rename at all.

The manual N-edit sequence does **not** stay as a documented alternative. Two
sanctioned ways to do one thing is precisely the ambiguity that broke the last
tool. It survives only as a one-line fallback for "the plugin is not installed".

**The README gains a `Renaming` section** stating the tool is the way, and — first
sentence — that the `LSP` tool cannot write, so this is not a duplicate of anything.

**Nothing anywhere describes it as an alternative to the `LSP` tool.** It is the
continuation of the same workflow: read with the tool, write with this.

## Tests

Unit, against the stand-in — extend `tests/fake_fsac.py` to answer
`textDocument/rename` with a scripted `WorkspaceEdit`:

- dry run prints edits and writes nothing (assert file mtimes and contents unchanged)
- `--apply` writes exactly the scripted edits
- empty `WorkspaceEdit` → exit 3, nothing written
- `WorkspaceEdit` containing a file operation → exit 3, nothing written
- `--expect` mismatch → exit 4, nothing written
- a file modified between dry run and apply → exit 5, nothing written
- 1-based conversion: position `7 5` reaches LSP `{line: 6, character: 4}`

Integration is optional and, if added, must not resurrect a fixture project whose
only purpose is to be broken. A temp project built by the test is enough.

**Mutation-test every guard before trusting it**, and record it. Each row of the
safety table above must be broken in turn and the corresponding test watched to
fail. A guard nobody has seen fail is not evidence — and this is the first tool in
this plugin that can damage a user's source, so the bar is higher than for the
health check.

## What would make this fail review

- a second subcommand
- `--apply` as the default, or any path where an exploratory run writes
- documentation that positions it against the `LSP` tool rather than after it
- a guard shipped without a mutation test
- the words "read-only" surviving anywhere in the plugin's prose, since they will
  no longer be true
