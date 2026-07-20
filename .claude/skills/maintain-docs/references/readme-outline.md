# README outline

The README is *regenerated*, not rewritten from scratch. Its voice and structure
are hard-won; preserve them and refresh the evidence-bound parts.

## Fixed section order

Keep this order so structure cannot drift:

1. Title + one paragraph: Claude Code's `LSP` tool doesn't speak F#; this is the
   plugin.
2. The Ionide-doesn't-carry-over callout. Shows the `No LSP server available for
   file type: .fs` message. (This one is a documented constant, not a captured
   transcript — it requires disabling the plugin — so it is prose, not an
   `<!-- evidence: -->` block.)
3. Prerequisites — install `fsautocomplete`, the PATH warning, verify. Shows the
   `fsac-version` block.
4. Install — the two `/plugin` commands.
5. What changes after you install — the plain-language prompts.
6. What ships — the four-file table.
7. **The refactoring stories** — the heart (see below).
8. Diagnostics — build, `--no-incremental`.
9. When F# is not working — the three-failures table, showing `check-healthy` and
   `check-broken`.
10. Tests · Names disambiguated · License.

## First-pass restructure: pull site-only facts into the README

The landing page derives one-way from the README and may never add a fact the
README lacks. So on the first regeneration, every concrete transcript that today
lives only on the site must land in the README first, bound to evidence:

| was site-only | new README home | evidence id |
|---|---|---|
| `fsautocomplete --version` output | Prerequisites | `fsac-version` |
| healthy check (four `ok` lines) | When F# is not working | `check-healthy` |
| broken check (`FAIL … PATH`, exit `2`) | When F# is not working | `check-broken` |
| `findReferences` block | the rename story | `findreferences-renew` |
| dry-run rename block | the rename story | `rename-dryrun` |
| `dotnet build` → `FS0039` | the rename story's close | `build-fs0039` |

Prose-only descriptions become prose **plus** the evidence block they describe.

## The stories (section 7)

Each story follows one shape, and every output block is preceded by its
`<!-- evidence: <id> -->` marker with the body copied verbatim from the evidence
file:

> **Prompt** (plain language) → **What Claude reaches for first** (its own
> `Grep` — the *anchored* search a real model runs, which still returns a
> same-named but unrelated symbol) → **What the compiler says** (the plugin's
> `LSP`/rename output, from evidence) → **What Claude does with the gap.**

**Primary story — rename `renew` to `renewLoan`:**
- Prompt: "rename `renew` to `renewLoan`."
- Grep first, honestly: anchor the word (`grep -rnw renew demo | sort`) so the
  substring and comment noise never enters the count. It *still* returns four
  hits, because the demo defines two functions named `renew` — `Loan.renew` and
  `Member.renew` (a membership renewal). Two of the four are the wrong binding,
  and no regex separates identically spelled symbols. The strawman to avoid is a
  naive `grep -rn renew` whose only "false positives" are `renewalLimit` and
  comments — noise a competent search discards. The real point needs a homograph.
- Compiler: `findReferences` at the `Loan.renew` declaration
  (`findreferences-renew`) → the two loan sites only, dropping the two
  `Member.renew` hits grep returned, and crossing into the Consumer project; then
  the dry run (`rename-dryrun`) touching only those two, leaving `Member.renew`
  alone.
- Action: `--apply --expect N` with N from `findReferences`, then `dotnet build`
  (`build-fs0039`) — or the recorded gap if the SDK was absent.

**Secondary story — `hover` on `isOverdue`** (`hover-isoverdue`): establish a
return type before a change; the read-only path.

## Voice rules

- Lead with the fact, then the reason. Short declaratives.
- Name the failure mode precisely; never smear three distinct failures into one
  sentence.
- Every count, version, path, and exit code traces to evidence or to a repo file.
  Prose may be reworded freely; facts may not be invented.
- Prefer the compiler's word over an approximation: a `grep` count is not a
  reference count. The README proves it — an anchored, airtight regex still
  returns four hits where two are a different function also named `renew`, and
  only the compiler separates them.
