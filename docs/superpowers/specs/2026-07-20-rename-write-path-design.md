# Restoring the `rename` write path

**Date:** 2026-07-20
**Status:** design approved, not yet implemented
**Target release:** 1.2.0

## What this changes

`tools/fsharp_lsp.py` gains one write subcommand, `rename`, driven by Claude
through the plugin's skill. `code-action` stays commented out.

This reverses the "stays read-only for now" constraint in CLAUDE.md. That
constraint recorded a deferral, not a prohibition — the code was verified
working before it was switched off, and this spec closes the gaps that made it
feel half-trusted.

## Why `code-action` is not included

Decided, not deferred-by-omission. The file's own notes record why: on this
repo's most common trigger (FS0025) the offered fix generates

```fsharp
| SomeCase(_, _) -> failwith "Not Implemented"
```

which restores exhaustiveness by converting a compile error into a runtime
failure — silencing the exact signal `TreatWarningsAsErrors` exists to produce.
It is a good way to *locate* missing cases and a bad thing to apply. It also
never had `--expect`, so it has no equivalent of the divergence guard below.

## The threat model

`--apply` is invoked by an agent, not a human reading output. Five failure
modes, and what answers each:

| Failure | Guard | Status |
|---|---|---|
| Server returns no WorkspaceEdit | refuse, exit 3 | already in the commented code |
| Server returns an **empty** WorkspaceEdit — the silent no-op of oraios/serena#725, where a rename reported success having changed 0 files while leaving 17 references untouched | refuse, exit 3 | already in the commented code |
| Position was off by one, so a confident rename lands on the wrong symbol | `--expect N` mismatch, exit 4 | exists, but optional — **made mandatory under `--apply`** |
| Apply diverges from what the dry run showed | same `--expect` | **new consequence of making it mandatory** |
| A bad rename cannot be undone | refuse to touch files with uncommitted changes, exit 5 | **new** |

### Correction to an earlier reading

The ROADMAP and the file's notes both describe a staleness gap: "if a file
changes between the dry run and `--apply`, the offsets may be stale and nothing
checks." Reading `cmd_rename` closely, this is not what the code does. Each
invocation issues its own `textDocument/rename` and applies *that* response;
`--apply` never replays offsets captured during a dry run. There is no stale-
offset bug to fix.

The real exposure is divergence the caller does not notice: the agent sees a
dry run reporting 56 edits, then invokes `--apply`, and the server — with the
file since changed — returns 57. The old code would write all 57 without
comment. Mandatory `--expect` is the fix, and it is cheaper and stronger than
re-issuing the request would have been.

This spec supersedes that line in the notes; the notes get corrected as part of
the work.

## Design

### Mandatory `--expect` under `--apply`

`--apply` without `--expect N` is refused at argument-parsing time. Dry runs
keep `--expect` optional.

This gives the agent a required two-step workflow: establish the count, then
commit to it. The count is not guesswork — `references` already reports every
hit with its position, so the expected number is derived from a compiler answer
rather than invented.

### Recoverability check

Before any write, every target file must be tracked by git and free of
uncommitted changes. Implementation: `git -C <root> status --porcelain --` over
the target paths; any output means refuse. Refuse likewise when the directory is
not a git repository.

New exit code **5**, with a message naming the offending files.

**There is deliberately no `--no-git-check` escape hatch.** A flag an agent can
pass to skip a safety check is a check that will be skipped. The cost is that
`--apply` is unavailable in a non-git project — an accepted limitation, listed
below, revisitable if a user asks.

The property this buys is worth stating plainly: *every rename this tool applies
is reversible with `git checkout --`.* That is verifiable. "The agent was
careful" is not.

### Newline preservation — a defect fix

The commented `apply_edits` uses `Path.read_text()` and `Path.write_text()`.
Both use text mode with `newline=None`: reading collapses CRLF to `\n`, writing
translates `\n` back to `os.linesep`. On a CRLF checkout — routine in a repo with
Windows contributors — renaming one symbol would rewrite **every line ending in
the file**, turning a 3-line diff into a whole-file diff.

This was never observed because verification happened in this repo, which is LF
throughout.

Fix: read and write with `newline=""` so terminators survive the round trip
byte-for-byte. Offset arithmetic stays correct — line lengths then include the
`\r\n`, matching the text being indexed.

Related: compute line starts by scanning for `\n` only, rather than
`str.splitlines()`, which also breaks on vertical tab, form feed, and the
Unicode line/paragraph separators (U+2028, U+2029).
LSP does not treat those as line boundaries, so a form feed inside a string
literal would silently shift every offset below it. Exotic in F#, and cheap to
rule out.

### Atomic-enough writes

Current behaviour writes file by file, so a crash mid-run leaves a partial
application. New behaviour: compute all new contents in memory, write each to a
sibling temporary file, copy the original's mode onto it, then `os.replace` each
into place.

This is not a true multi-file transaction — a crash between two `os.replace`
calls still splits the batch. It reduces the window from "the duration of N file
writes" to "the gap between N renames", and each individual file is never seen
half-written. Combined with the git check, the residue is always recoverable.

Honest framing: the goal is recoverability, not atomicity. Claiming atomicity
would be a lie the code cannot back.

### Unchanged from the verified original

`collect_edits`, `report`, the dry-run-by-default posture, and the outright
refusal of WorkspaceEdit file operations (create/rename/delete) all return
verbatim. They were exercised and they were right.

## Exit codes after this change

```
0 ok
1 nothing found
2 LSP or environment error (includes --apply without --expect)
3 refused: no WorkspaceEdit, or an empty one
4 refused: edit count did not match --expect
5 refused: target files have uncommitted changes, or are not under git
```

## Testing

Unit tests extend `tests/fake_fsac.py` with scripted rename responses, covering
both WorkspaceEdit shapes (`changes` and `documentChanges`). No test seam enters
shipped code — the client spawns whatever `FSAC_PATH` names, as today.

Cases that must fail before they pass:

- dry run writes nothing to disk
- `--apply` without `--expect` is refused, exit 2
- `--expect` mismatch refuses and writes nothing, exit 4
- empty WorkspaceEdit refuses, exit 3
- a `documentChanges` entry carrying a file operation is refused
- uncommitted change to a target file refuses, exit 5, nothing written
- non-git directory refuses, exit 5
- **a CRLF file keeps CRLF, and only the renamed spans differ**
- file mode survives the write
- no `.tmp` residue after a successful apply
- no `.tmp` residue after a refusal

Integration test: rename a symbol in `tests/fixtures/SampleProject`, assert the
edit count, then restore with `git checkout --`.

## Documentation

The read-only claim is load-bearing in more places than the code. All of these
assert something that stops being true:

- `tools/fsharp_lsp.py` module docstring — "READ-ONLY", "NEVER writes", the
  usage block, exit codes, and the paragraph about the write paths being off
- the end-of-file notes — move `rename` from DISABLED to ACTIVE, correct the
  staleness line per the section above, and narrow "WHY THE WRITE PATHS ARE OFF"
  to `code-action` alone
- `CLAUDE.md` — rewrite the hard constraint
- `skills/fsharp-lsp-queries/SKILL.md` — currently states that neither half can
  rename and that there is therefore no semantic rename for F# in Claude Code by
  any route. That becomes the opposite. The skill must also teach the two-step
  workflow, since the agent is the caller.
- `README.md` — the "it cannot write" and "neither half can rename" bullets
- `docs/index.html` — the landing page narrative is built around step 4 being
  the human's, and the description meta tags say "read-only query CLI"
- `.claude-plugin/plugin.json` — `description` says "read-only", and `version`
  bumps to `1.2.0` (every release bumps it; an unbumped version is how a stale
  marketplace copy survives unnoticed)

## Accepted limitations

Listed so they are not mistaken for verified.

- `--apply` requires git. No escape hatch, by design.
- Not a multi-file transaction; see above.
- `.fsi` signature files and type providers remain untested — this repo has
  neither, so whether rename reaches declarations in a signature file is still
  unestablished.
- Does not touch the `.fsproj`. F#'s `<Compile Include>` ordering is semantic,
  and no rename this tool performs will reorder it.
- FSAC itself disables rename for Active Patterns and Active Pattern Cases.
- LSP `character` offsets are UTF-16 code units. A non-BMP character earlier on
  the same line — an emoji in a string literal — would shift the offset. Not
  handled, and not observed.
