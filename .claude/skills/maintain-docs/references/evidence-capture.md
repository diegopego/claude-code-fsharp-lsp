# Evidence capture

Capture runs only past a green gate (see `SKILL.md`), in a session rooted at the
repo root — so the demo's projects are inside the launch directory and the `LSP`
tool answers for them.

Write everything to `docs/evidence/transcripts.md`. This file is the single
source of every snippet the README and site show; it is committed.

## Block format

Each block is a `### <id>` heading, one provenance line, then one fenced code
block holding the verbatim output:

    ### <id>
    captured: <YYYY-MM-DD> · fsac: <version> · plugin-hash: <hash> · project: demo
    ```
    <verbatim output>
    ```

- `<hash>` is the first 12 chars of what `check_plugin_current.py` matched — it
  makes a block's provenance auditable later.
- `<version>` is the `fsautocomplete --version` string, truncated at `+`.

## Anonymisation (applied once, here)

Replace the real home directory with `/home/you` (e.g.
`/home/diego/.dotnet/tools/fsautocomplete` → `/home/you/.dotnet/tools/fsautocomplete`).
Keep repo-relative `demo/…` paths exactly — they are reproducible by anyone who
clones the repo. Nothing else is edited: counts, versions, and error text are
byte-for-byte.

## Restore discipline

`rename-apply` and `build-fs0039` mutate `demo/`. After each, run:

```bash
git restore demo/
```

Before finishing capture, assert the demo is clean:

```bash
git status --porcelain demo/   # must print nothing
```

A run that leaves `demo/` dirty is a failed run — do not commit its evidence.

## Capture order and server state

The `LSP` tool drives one **long-lived** `fsautocomplete`. A `git restore` — like
any shell-level edit — changes files without notifying it, so its cached analysis
goes stale and `findReferences`/`hover` silently **under-report** (the
cross-project use of `renew` drops out, leaving fewer references than the code
actually has). That is a poisoned capture, and nothing in the output says so.

So capture every `LSP`-tool block — `findreferences-renew`, `hover-isoverdue` —
**before** the first mutate-and-restore. The id order below already does this;
keep it. If you must re-query the `LSP` tool after a `git restore`, **restart the
session first** — the running server will not re-sync from a restore, and no
amount of re-querying recovers it. `rename-dryrun`/`rename-apply` are exempt:
`rename_fsharp_symbol.py` spawns a fresh server per run, so it is unaffected by
the desync and stays correct after restores.

## The evidence ids

The demo defines the loan renewal `renew` in `demo/LibraryLending/Loan.fs` (the
rename target) and a second, unrelated `renew` in `demo/LibraryLending/Member.fs`
(a membership renewal) — the homograph that makes even an anchored text search
return false positives.

Positions are 1-based. The rename commands below take the loan `renew`'s line and
column as `<line> <col>`; **re-derive them every capture** — e.g.
`grep -n 'let renew ' demo/LibraryLending/Loan.fs` for the line — and never
hard-code them here, since any edit above the function shifts them.

### fsac-version
The verify step from the README's prerequisites.
```bash
fsautocomplete --version
```

### check-healthy
The health check against the demo, all `ok` lines. `demo` is the workspace root
(it holds the `.slnx` and both projects); build first so the projects are restored.
```bash
dotnet build demo/LibraryLending.slnx
python3 tools/check_fsharp_lsp.py demo
```

### check-broken
The same check with `fsautocomplete` **not** on PATH — the `FAIL … PATH` line and
the exit code. Run it in a shell whose PATH excludes `~/.dotnet/tools` (do not
uninstall anything); capture both the output and `echo $?` → `2`.

### grep-renew
The reflex search, done well: anchor the word and pipe to `sort` for a stable,
reproducible order (bare `grep -r` traversal order is filesystem-dependent). It
returns more hits than the loan rename has real references — the `Loan.renew`
sites and the unrelated `Member.renew` sites — because grep matches the spelling,
not the binding. The extra hits are false positives for the loan rename; that is
the point `findReferences` then disproves. This block has no `.NET`/`fsac`
dependency, but keep the uniform provenance line.
```bash
grep -rnw renew demo --include='*.fs' | sort
```

### findreferences-renew
The `LSP` tool's `findReferences` at the `Loan.renew` declaration (in
`demo/LibraryLending/Loan.fs`). Expect only the loan sites — the definition in
`Loan.fs` and the cross-project call in `LibraryLending.Consumer/Renewals.fs` —
and **not** the `Member.renew` sites `grep` returned. This is the story's proof
that the compiler answers about the binding, not the spelling, and crosses the
project boundary as it does. Record the reference count; it is the `N` for
`rename-apply`.

### hover-isoverdue
The `LSP` tool's `hover` on `isOverdue` (same file). Its type signature — captured
verbatim in the block — is the read-only story.

### rename-dryrun
The dry run — no flags, writes nothing. Uses the loan `renew` position re-derived
above as `<line> <col>`:
```bash
python3 tools/rename_fsharp_symbol.py demo demo/LibraryLending/Loan.fs <line> <col> renewLoan
```

### rename-apply
The applied rename, guarded by the count from `findreferences-renew` (`<N>`). Then
restore.
```bash
python3 tools/rename_fsharp_symbol.py demo demo/LibraryLending/Loan.fs <line> <col> renewLoan --apply --expect <N>
git restore demo/
```

### build-fs0039  (optional — needs the .NET SDK)
The compiler's last word. Rename **one** call site of `renew` wrong by hand (e.g.
edit only `Renewals.fs` to call `renewLoan` while leaving the declaration named
`renew`), then build and capture the `FS0039` line. Restore afterwards.
```bash
dotnet build --no-incremental demo/LibraryLending.slnx
git restore demo/
```
If `dotnet` is absent, **skip this block** and write a short gap note in its place
in the evidence file — never fabricate the error.
