# Landing-page section map

`docs/index.html` derives **one-way** from `README.md`. The site may present a
README fact differently, or omit it; it may never introduce a fact the README
lacks.

## Two invariants

1. **Edit only `<body>` content, only the sections mapped below. Never touch
   `<style>`.** Its CSS comments record decisions (e.g. why there are no
   scroll-triggered reveals); regenerating would erase the reasoning. If a new
   style is genuinely needed, that is a human edit, not a generation step.
2. **No added facts.** Every shell command shown in a `.term` block must appear in
   a README fenced block. `tests/test_docs_site_subset.py` enforces this.

## Section map

| README section | index.html destination | notes |
|---|---|---|
| Title + intro paragraph | `.hero` (`h1`, `.lead`) | the hero framing is the site's own presentation |
| — | `.roles` (You / Claude cards) | **site-only presentation**, adds no fact; keep |
| Ionide callout + `No LSP server` | `.callout` in hero + its `.term` | |
| What ships (four-file table) | `#what` `.parts` grid | |
| The rename stories | `#refactor` `.steps` | the stepped-tutorial chrome is site-only presentation |
| Prerequisites + install | `#install` `.steps` + `.copyrow`s | `fsac-version` → the "confirm it runs" term |
| When F# is not working | `#trouble` | `check-healthy` and `check-broken` terms |

Anything not in this map is left as-is.

## The line transform (fenced block → `.term`)

A README fenced block becomes a `.term` structure. Each output line is one
`<div class="line">`; wrap the content in the span class chosen by what the line
is:

| line content | span class |
|---|---|
| the shell prompt `$` | `prompt` (on the `$`), `cmd` on the command text |
| a success/`ok` line | `ok` |
| an error / `FAIL` line | `fail` |
| a warning / secondary state | `amber` |
| a path or a heading line (e.g. `Found N references`) | `path` |
| muted / explanatory output | `dim` |

Add the `wraps` class to `.term-body` when any command is long enough to wrap, so
it wraps with a hanging indent rather than hiding behind a scrollbar.

Home directories are already anonymised in the evidence (`/home/you`); do not
re-transform. Keep repo-relative `demo/…` paths as-is.

## What the site deliberately omits

The README's `Tests`, `Names disambiguated`, and `License` sections have no
landing-page home — the site links to GitHub for the rest. Omission is allowed;
addition is not.
