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

## The evidence ids

Positions below are 1-based. `renew` is declared at `demo/LibraryLending/Loan.fs`
**line 21, column 5** (verify with `grep -n 'let renew ' demo/LibraryLending/Loan.fs`
before capturing — if the file changes, re-derive it).

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

### findreferences-renew
The `LSP` tool's `findReferences` at the `renew` declaration
(`demo/LibraryLending/Loan.fs`, line 21, col 5). Expect the definition in
`Loan.fs` and the cross-project call in `LibraryLending.Consumer/Renewals.fs` —
this is the story's proof that the answer crosses a project boundary a
library-directory `grep` never sees. Record the reference count; it is the `N`
for `rename-apply`.

### hover-isoverdue
The `LSP` tool's `hover` on `isOverdue` (same file). Its type signature
(`DateOnly -> Loan -> bool`) is the read-only story.

### rename-dryrun
The dry run — no flags, writes nothing.
```bash
python3 tools/rename_fsharp_symbol.py demo demo/LibraryLending/Loan.fs 21 5 renewLoan
```

### rename-apply
The applied rename, guarded by the count from `findreferences-renew`. Then
restore.
```bash
python3 tools/rename_fsharp_symbol.py demo demo/LibraryLending/Loan.fs 21 5 renewLoan --apply --expect <N>
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
