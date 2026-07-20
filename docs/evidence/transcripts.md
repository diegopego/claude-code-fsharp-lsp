# Captured evidence

Verbatim tool and `LSP`-tool output, captured against the committed `demo/`
project by the `maintain-docs` skill. This file is the single source of every
snippet in `README.md` and `docs/index.html`; do not hand-edit it — re-run
`/maintain-docs`.

Home directories are anonymised (`/home/you`); repo-relative `demo/…` paths are
kept as-is. Everything else is byte-for-byte, except two trims noted at their
blocks (a hover command-link and an MSBuild project suffix).

Provenance fields: `captured` date · `fsac` version · `plugin-hash` (first 12
chars of the working-tree manifest the gate matched) · `project`.

### fsac-version
captured: 2026-07-20 · fsac: 0.83.0 · plugin-hash: 37d551e13f40 · project: demo
```
$ fsautocomplete --version
0.83.0+96fabed8e9181b74e19e211717626c204c32b2c2
```

### check-healthy
captured: 2026-07-20 · fsac: 0.83.0 · plugin-hash: 37d551e13f40 · project: demo
```
$ python3 tools/check_fsharp_lsp.py demo
  ok    python 3.10
  ok    fsautocomplete 0.83.0  (/home/you/.dotnet/tools/fsautocomplete)
  ok    dotnet sdk 10.0.110
  ok    2 restored project(s) under demo
```

### check-broken
captured: 2026-07-20 · fsac: 0.83.0 · plugin-hash: 37d551e13f40 · project: demo
```
$ python3 tools/check_fsharp_lsp.py
  ok    python 3.10
  ok    dotnet sdk 10.0.110
  FAIL  fsautocomplete is not on PATH. Install it with 'dotnet tool install -g fsautocomplete', then make sure the global tools directory (~/.dotnet/tools on Linux and macOS) is on the PATH of the process that launches Claude Code. A login shell rc file is not always enough, and that gap is the most common cause of this.
$ echo $?
2
```

### grep-renew
captured: 2026-07-20 · fsac: 0.83.0 · plugin-hash: 37d551e13f40 · project: demo
```
$ grep -rn renew demo --include='*.fs'
demo/LibraryLending.Consumer/Renewals.fs:6:/// Renew a batch of loans, keeping only the ones that could be renewed.
demo/LibraryLending.Consumer/Renewals.fs:7:let renewAll (today: DateOnly) (loans: Loan list) =
demo/LibraryLending.Consumer/Renewals.fs:8:    loans |> List.choose (renew today)
demo/LibraryLending/Loan.fs:7:/// A loan may be renewed at most this many times.
demo/LibraryLending/Loan.fs:8:let renewalLimit = 2
demo/LibraryLending/Loan.fs:19:/// Extend the due date by two weeks — unless the renewal limit is
demo/LibraryLending/Loan.fs:21:let renew (today: DateOnly) (loan: Loan) =
demo/LibraryLending/Loan.fs:22:    if loan.RenewalsUsed >= renewalLimit then None
```

### findreferences-renew
captured: 2026-07-20 · fsac: 0.83.0 · plugin-hash: 37d551e13f40 · project: demo
```
Found 2 references across 2 files:

demo/LibraryLending.Consumer/Renewals.fs:
  Line 8:27

demo/LibraryLending/Loan.fs:
  Line 21:5
```

### hover-isoverdue
captured: 2026-07-20 · fsac: 0.83.0 · plugin-hash: 37d551e13f40 · project: demo
(trailing VS Code command-link line trimmed; signature and docs verbatim)
```
val isOverdue:
   today: DateOnly ->
   loan : Loan
       -> bool

A loan is overdue once its due date has passed.

Full name: LibraryLending.Loan.isOverdue
Assembly: LibraryLending
```

### rename-dryrun
captured: 2026-07-20 · fsac: 0.83.0 · plugin-hash: 37d551e13f40 · project: demo
```
$ python3 tools/rename_fsharp_symbol.py demo demo/LibraryLending/Loan.fs 21 5 renewLoan
DRY RUN: rename -> 'renewLoan' | 2 file(s), 2 edit(s)
  LibraryLending/Loan.fs
    21:5  renew -> renewLoan
  LibraryLending.Consumer/Renewals.fs
    8:27  renew -> renewLoan

(dry run — pass --apply to write)
```

### rename-apply
captured: 2026-07-20 · fsac: 0.83.0 · plugin-hash: 37d551e13f40 · project: demo
```
$ python3 tools/rename_fsharp_symbol.py demo demo/LibraryLending/Loan.fs 21 5 renewLoan --apply --expect 2
APPLY: rename -> 'renewLoan' | 2 file(s), 2 edit(s)
  LibraryLending/Loan.fs
    21:5  renew -> renewLoan
  LibraryLending.Consumer/Renewals.fs
    8:27  renew -> renewLoan

Wrote 2 file(s).
```

### build-fs0039
captured: 2026-07-20 · fsac: 0.83.0 · plugin-hash: 37d551e13f40 · project: demo
(absolute path reduced to repo-relative; MSBuild `[…fsproj]` suffix trimmed)
```
$ dotnet build --no-incremental demo/LibraryLending.slnx
demo/LibraryLending.Consumer/Renewals.fs(8,27): error FS0039: The value or constructor 'renew' is not defined. Maybe you want one of the following:   renewLoan   renewalLimit
```
