# Design: the `maintain-docs` skill

**Date:** 2026-07-20
**Status:** implemented 2026-07-20 (see `docs/plans/2026-07-20-maintain-docs-skill.md`).
This document has since been reconciled with the shipped code; where the built
demo or skill diverged from the original proposal, the notes below flag it — the
divergences are the `renew` homograph and the three helper scripts.

A project-local Claude Code skill that regenerates this repo's `README.md` and
`docs/index.html` from **real, captured tool output** rather than from prose the
author hopes is still true. It exists because the two documents have already
drifted — the landing page carries concrete transcripts the README only
describes — and because a stale plugin can silently poison any story about how
Claude behaves.

The skill is invoked by the maintainer as `/maintain-docs`. It is **not** part of
the shipped plugin and must never reach a plugin user.

---

## Why this exists

Two problems, both observed in this repo, not hypothetical:

1. **Snippets rot silently.** The plugin's whole reason for being is that a
   `grep` count is not a reference count — yet the docs' `grep`-vs-compiler
   numbers were hand-written and anonymised (`~/src/orderboard`) from a private
   project (`~/devel/parity-fsharp/fsharp-orderboard`) no reader can reproduce.
   The `HANDOFF.md` record shows this exact failure once already shipped: a
   docstring claimed "42 hits in 2 files" that a fresh server contradicted with
   "56 in 4."
2. **A stale plugin narrates the wrong workflow.** Claude's *behaviour* in a
   story — which tool it reaches for, what it says — comes from the **installed**
   skill. The session writing these docs today is following `fsharp-lsp-queries`
   from cached 1.1.1, a skill that documents `fsharp_lsp.py`, a tool removed in
   2.0.0. Evidence captured from such a session would describe a tool that no
   longer exists.

The fix is a documentation instrument (a demo F# project committed in the repo),
an evidence file captured from a verified-current plugin, and a hard gate that
refuses to capture from anything else.

---

## Architecture

Three phases, strictly ordered. Nothing downstream runs if the gate fails.

```
gate  →  capture  →  generate ( README  →  landing page )
```

Five committed artefacts:

| artefact | path | role |
|---|---|---|
| the skill | `.claude/skills/maintain-docs/` | the instructions; project-local, never shipped |
| the demo project | `demo/LibraryLending/` | real F# the tools run against — the documentation instrument |
| the evidence file | `docs/evidence/transcripts.md` | verbatim tool/LSP output with provenance; the only legal source of snippets |
| README | `README.md` | generated from evidence + a fixed outline |
| landing page | `docs/index.html` | derived one-way from the README |

### Why `.claude/skills/`, not `skills/`

The repo's `skills/` directory **is the plugin**: anything there ships to
everyone who installs `fsharp-lsp`. A documentation-maintenance skill has no
place in a stranger's plugin list, and it references files (`demo/`, the
evidence, this repo's README) that are meaningless outside this repo.

`.claude/skills/` holds the *project's own* skills, loaded only when this repo is
the workspace and never bundled into the plugin the repo ships. A plugin user
receives only the plugin's `skills/fsharp-code-intelligence`, never this.

This requires one `.gitignore` change: `.claude/` is currently ignored
wholesale; keep that and add an un-ignore for the skills subtree so it can be
committed.

```gitignore
.claude/
!.claude/skills/
!.claude/skills/**
```

---

## The demo project

Library lending. Didactic domain, plain names, no cryptic identifiers. Every name
must read as code someone meant; every decoy must be one a real library system
would genuinely contain, because a planted-looking decoy makes the whole
`grep`-vs-compiler story feel rigged.

**Dependency-free.** A plain F# library plus a small consumer project that
references it — no test framework, no NuGet. `dotnet restore` / `dotnet build`
need nothing off the network. The second project exists so `findReferences`
visibly crosses a project boundary that a `grep` of the library directory never
sees.

### Layout

```
demo/
  LibraryLending.slnx                # solution over both projects (as built)
  LibraryLending/
    LibraryLending.fsproj          # library: Book, Member, Loan
    Book.fs
    Member.fs                      # Member — and Member.renew, the homograph (as built)
    Loan.fs
  LibraryLending.Consumer/
    LibraryLending.Consumer.fsproj # references LibraryLending
    Renewals.fs                    # calls Loan.renew across the project boundary
    Memberships.fs                 # calls Member.renew across the project boundary (as built)
```

Compile order in the `.fsproj` is `Book.fs`, `Member.fs`, `Loan.fs` (F#'s order
is semantic — `Loan` opens the other two).

### Source (as built; the original proposal is preserved, with one addition)

> **Divergence from the proposal:** the built demo added a second, genuine
> `renew` — `Member.renew` — turning the single-`renew` decoy into a *homograph*.
> `Book.fs` and `Loan.fs` are as proposed; `Member.fs` below carries the
> addition, and the consumer gained `Memberships.fs` to give it a cross-project
> use site. This is a role added beyond the proposal, not just a renamed one.

`Book.fs`
```fsharp
module LibraryLending.Book

type Book =
    { Title: string
      Author: string
      CopiesOnShelf: int }

/// A book can be lent when at least one copy is on the shelf.
let isAvailable (book: Book) = book.CopiesOnShelf > 0
```

`Member.fs`
```fsharp
module LibraryLending.Member

open System

type Member =
    { Name: string
      LoansAllowed: int
      MembershipExpires: DateOnly }

/// Renew a membership: push its expiry date out by a year.
let renew (today: DateOnly) (m: Member) =
    { m with MembershipExpires = today.AddYears 1 }
```

`Loan.fs`
```fsharp
module LibraryLending.Loan

open System
open LibraryLending.Book
open LibraryLending.Member

/// A loan may be renewed at most this many times.
let renewalLimit = 2

type Loan =
    { Book: Book
      Borrower: Member
      DueDate: DateOnly
      RenewalsUsed: int }

/// A loan is overdue once its due date has passed.
let isOverdue (today: DateOnly) (loan: Loan) = today > loan.DueDate

/// Extend the due date by two weeks — unless the renewal limit is
/// reached, or the loan is already overdue.
let renew (today: DateOnly) (loan: Loan) =
    if loan.RenewalsUsed >= renewalLimit then None
    elif isOverdue today loan then None
    else Some { loan with
                  DueDate = loan.DueDate.AddDays 14
                  RenewalsUsed = loan.RenewalsUsed + 1 }
```

`Renewals.fs` calls `Loan.renew` and `Memberships.fs` calls `Member.renew` (both
in the consumer project), giving each `renew` a use site outside its defining
project.

### The decoys and the stories they unlock — all naturally occurring

| decoy / shape | story it makes real |
|---|---|
| two genuine `renew` functions — `Loan.renew` and `Member.renew` — a homograph | `grep renew` cannot tell them apart; `findReferences` / rename on one leaves the other untouched — semantic, not textual (the `doubleTrouble` role, occurring naturally) |
| `renew` beside `renewalLimit` and `RenewalsUsed` | `grep renew` also over-counts on substring matches the compiler never confuses with the function |
| each `renew` used from `LibraryLending.Consumer` (`Renewals.fs`, `Memberships.fs`) | `findReferences` crosses a project boundary a library-dir `grep` never sees |
| `isOverdue : DateOnly -> Loan -> bool` | a `hover` whose type signature is worth reading |

---

## Phase 1 — the gate

One question: **is the plugin that will narrate these stories the same code the
working tree holds?** On any failure the gate prints the fix and stops. It never
captures, never half-writes.

Two independent signals — each catches what the other misses:

1. **On-disk identity (content hash).** Hash `.lsp.json`, every file under
   `skills/`, and every file under `tools/` in the working tree; compare against
   the installed copy under
   `~/.claude/plugins/cache/claude-code-fsharp-lsp/fsharp-lsp/<version>/`. A match
   means what is installed *is* the working tree, regardless of version number.
   This catches "edited the skill, forgot to reinstall" — the false-green a
   version check waves through.
2. **In-session liveness.** The gate reads its own available-skills list:
   `fsharp-code-intelligence` must be **present** and `fsharp-lsp-queries` (the
   retired 1.1.1 skill) must be **absent**. This proves *this running session*
   loaded the current skill — not merely that the right bytes sit on disk.
   Disabling a plugin takes effect immediately, but enabling does not until
   restart, so on-disk identity alone can hold while the session still runs the
   old skill.

### Why hashes, not version numbers

The gate's real question is content identity; a version number is only a proxy
for it, and the proxy has two failure modes this repo cares about:

- **False green:** edit a skill, leave `version` alone, reinstall — versions
  match on both sides while the content differs. This is the same species of bug
  (confident, plausible, wrong) that the "settled facts" discipline in
  `CLAUDE.md` exists to prevent.
- **Forced ceremony:** a version check would couple "fix a typo in a doc story"
  to cutting a release. The `CLAUDE.md` version-bump rule is about the marketplace
  re-pulling for **end users**; a local authoring reinstall is not a release and
  must not require a bump.

Hashing declines to overload the version field; it does not weaken the release
rule.

### On failure

Print the exact reconciliation and halt:
- add a local marketplace pointing at the working tree,
- `/plugin install fsharp-lsp@…`,
- **restart** the session (enabling does not take effect until then),
- re-run `/maintain-docs`.

---

## Phase 2 — capture

Runs only past a green gate, in this session: the repo root is the launch
directory, so the demo's `.fsproj` is in scope and the `LSP` tool answers for it.
Capture writes every snippet the docs need, verbatim, to
`docs/evidence/transcripts.md`, each block carrying provenance.

### Evidence block format

```
### findReferences-renew
captured: 2026-07-20 · fsac: 0.83.0 · plugin-hash: a1b2c3… · project: demo/LibraryLending
​```
<verbatim output, byte for byte>
​```
```

The `plugin-hash` is the same working-tree hash the gate computed; it makes
staleness detectable after the fact — a block whose hash does not match the
current tree was captured from a different plugin.

### What capture runs

- **Direct tool invocations** (working tree, always current):
  - `python3 tools/check_fsharp_lsp.py demo/LibraryLending` — healthy transcript
  - a broken-PATH invocation — the `FAIL … PATH` transcript and its exit code `2`
  - `python3 tools/rename_fsharp_symbol.py … renew … renewLoan` — dry run
  - the same with `--apply --expect N` — the applied transcript
  - `fsautocomplete --version` — the verify output
- **`LSP`-tool operations** (through the installed plugin — the reason the gate
  exists): `hover` on `isOverdue`, `findReferences` on `renew`, a call-hierarchy
  query.
- **The build close:** rename one site deliberately wrong, `dotnet build
  --no-incremental`, capture the `FS0039` error.

### Restore discipline

`--apply` and the `FS0039` build both mutate the demo. Each mutating step is
followed by `git restore demo/`, and capture ends by asserting `git status` on
`demo/` is clean. A capture that would leave `demo/` dirty is a **failed**
capture.

### The one soft dependency

The `FS0039` block needs `dotnet` and a demo restore — the only snippet that
costs a real build (seconds) and needs the SDK. It is worth it: that block is the
payoff of the rename story ("the compiler has the last word"). If `dotnet` is
absent the gate detects it and capture **skips only that block**, recording the
gap in the evidence file rather than fabricating output. Everything else is
instant and SDK-free.

---

## Phase 3a — README generation

A **regenerator**, not a from-scratch writer. The current README's voice and
structure are good and hard-won; the skill preserves them and refreshes the
evidence-bound parts. It carries two fixed inputs.

### The section outline (order is fixed so structure cannot drift)

1. Title + the one-paragraph "Claude Code's LSP tool doesn't speak F#; this is
   the plugin."
2. Ionide-doesn't-carry-over callout — **bound to** the `No LSP server available`
   evidence block.
3. Prerequisites — install `fsautocomplete`, the PATH warning, verify (now
   **showing** the `--version` output).
4. Install — two commands.
5. What changes after you install — the plain-language prompts.
6. What ships — the file table.
7. **The refactoring stories** — the heart (below).
8. Diagnostics — build, `--no-incremental`.
9. When F# is not working — the three-failures table, now **showing** the healthy
   and broken check transcripts.
10. Tests · Names disambiguated · License.

### First-pass restructure: site-only facts move into the README

Because the landing page will derive one-way from the README and may never add a
fact the README lacks, everything currently living only on the site must be
pulled into the README on this first pass, or it is lost. All of it is concrete
output — exactly what the evidence-driven README wants:

| site-only today | new README home |
|---|---|
| `fsautocomplete --version` → `0.83.0+…` shown | Prerequisites, the verify block |
| healthy `check_fsharp_lsp.py` → four `ok` lines | When F# is not working, healthy transcript |
| broken check → `FAIL … PATH`, `echo $?` → `2` | When F# is not working, broken transcript |
| `findReferences` terminal block | the rename story |
| dry-run rename terminal block | the rename story |
| `dotnet build` → `FS0039` block | the rename story's close |

The prose-only descriptions become prose **plus** the evidence block they were
describing. The site keeps only its *presentation* extras (the `You`/`Claude`
roles cards, the stepped-tutorial chrome) — those are styling, not facts.

### The stories (section 7)

Each story follows one fixed narrative shape, and every output line is bound to
an evidence ID:

> **Prompt** (plain language) → **What Claude reaches for first** (its *own*
> `Grep`/`Glob`, over-counting included) → **What the compiler says** (the
> plugin's `LSP`/rename output, verbatim from evidence) → **What Claude does with
> the gap.**

**Primary story — rename `Loan.renew` to `renewLoan`:**
- **Prompt:** "rename `renew` to `renewLoan`" — and note there are *two* `renew`s.
- **Grep first (Claude's reflex):** `grep -rn renew demo/` hits both `renew`
  functions (`Loan.renew`, `Member.renew`), their consumer call sites, and the
  `renewalLimit` / `RenewalsUsed` substrings — the count is wrong, and worse, it
  cannot tell the target `renew` from the homograph. The doc shows why.
- **Compiler (this plugin):** `findReferences` at the `Loan.renew` declaration →
  its true sites only, crossing into the Consumer project and leaving
  `Member.renew` alone; then the dry-run rename showing the same count.
- **Action:** `--apply --expect N` with N from `findReferences`, then `dotnet
  build` → the `FS0039` proof (or the recorded gap if the SDK was absent).

One well-chosen story exercises `grep`-vs-compiler, cross-project references,
semantic-vs-textual, and the compiler-has-the-last-word close. A short second
story (`hover` on `isOverdue` to establish a return type before a change) covers
the read-only path.

### Two hard rules

1. **No snippet without evidence.** Every fenced-output block cites an evidence
   ID; a missing ID fails the phase loudly rather than inventing plausible
   output. This is the anti-`fsharp_lsp.py`-staleness guard, mechanized.
2. **Prose may be rewritten; facts may not be invented.** The skill may rephrase,
   but any *claim of fact* (a count, a version, a path, an exit code) must trace
   to evidence or to a file in the repo.

---

## Phase 3b — landing page derivation

One-way, from the README, under an explicit section map.

### The section map

The skill carries a table mapping each README section to its destination in
`index.html`, plus what the site deliberately omits, plus the first-pass reverse
moves (site-only → README) recorded above so nothing is orphaned.

### Two invariants

1. **The site may omit a README fact; it may never add one absent from the
   README.** After the first pass every transcript on the site traces to a README
   block, which traces to evidence.
2. **The `<style>` block is never regenerated.** Its CSS comments record
   decisions (e.g. "No scroll-triggered reveals: sections that enter and leave
   the viewport between frames never get an IntersectionObserver callback"). The
   skill edits only `<body>` content, and only the sections the map names.

### The snippet transform (mechanical, documented)

README fenced block → `.term` structure: each line a `<div class="line">` with a
span class chosen by content — `prompt` for `$`, and `ok` / `fail` / `amber` /
`dim` / `path` for output — plus the `wraps` class for long commands. Home
directories are anonymised (`/home/diego` → `/home/you`); repo-relative `demo/…`
paths are kept as-is, since they are reproducible.

---

## Skill file layout

```
.claude/skills/maintain-docs/
  SKILL.md                       # three-phase workflow, the gate, the two hard rules
  check_plugin_current.py        # Phase-1 gate, on-disk half: installed plugin == working tree, by content hash (as built)
  refresh_plugin.py              # the on-failure reconcile: mirrors the working tree into the active install, no version bump (as built)
  bump_version.py                # release helper: minimal in-place bump of version in plugin.json (as built)
  references/readme-outline.md   # section outline + voice rules
  references/site-section-map.md # README→HTML map, omissions, line-class transform
  references/evidence-capture.md # exact capture commands + restore discipline
```

> The three `.py` helpers were not in the original layout — the proposal
> described the gate narratively (Phase 1) and left the reconcile steps as prose.
> The build materialised them as scripts; `check_plugin_current.py` is the gate
> the "On failure" section below calls for, and `refresh_plugin.py` is its
> inverse. `bump_version.py` serves `CLAUDE.md`'s every-release-bumps rule.

Invoked as `/maintain-docs`.

---

## Testing

In this repo's spirit — a guard nobody has watched fail is not evidence — the
skill's checkable claims get pytest coverage that needs no .NET:

- **The decoy actually fools `grep`.** `grep -c renew` on the committed demo
  returns **more** than the reference count. If this stops being true, the central
  story is broken and a test says so.
- **The site adds no transcript the README lacks.** Parse both; assert every
  `.term` block's command line appears in a README fenced block.
- **Capture leaves `demo/` git-clean.** The restore discipline, asserted (the
  test can run the restore-and-check sequence without invoking a real server by
  operating on a scratch copy, or assert the documented sequence exists — detail
  for the plan).

These join the existing standard-library-only suite; no new runtime dependency,
and `pytest` stays a dev-only import.

---

## Explicit non-goals

- **Not shipped to plugin users.** Lives in `.claude/skills/`, outside the
  plugin's `skills/`.
- **Does not touch the plugin's own files.** It reads `.lsp.json`, `skills/`,
  `tools/` for hashing; it never edits them.
- **Does not regenerate the site `<style>`.** Body content only.
- **Does not fabricate output.** A missing evidence ID or an absent SDK is
  recorded as a gap, never filled with a plausible guess.
- **No second job for the demo project.** It is a documentation instrument; it is
  not a test fixture for the rename tool (that stays `fake_fsac.py`), though a
  future task could reuse it as an honest integration fixture.
