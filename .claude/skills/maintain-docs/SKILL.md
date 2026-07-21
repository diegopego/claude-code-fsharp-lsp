---
name: maintain-docs
description: Regenerate this repo's README.md and docs/index.html from real, captured tool output. Use when the README or landing page needs updating, when the demo stories change, or after a plugin change that affects what Claude sees. Runs a hard gate first and refuses to fabricate any snippet.
---

# maintain-docs

Regenerates `README.md`, then `docs/index.html`, from evidence captured against
the committed `demo/` project (a two-project F# library-lending solution). Three
phases, strictly ordered. **Nothing downstream runs if the gate fails.**

This skill is project-local — it lives in `.claude/skills/`, never ships with the
plugin, and only makes sense inside this repository.

## Why the gate exists

Claude's *behaviour* in a documentation story — which tool it reaches for, what
it narrates — comes from the **installed** skill, not the working tree. Capturing
from a stale install describes a tool that may no longer exist (this repo shipped
`fsharp_lsp.py` through 1.1.1 and has since removed it). So before any capture, we
prove the installed plugin is the working tree.

## Phase 1 — gate (both signals must pass)

1. **On-disk identity.** Run:

   ```bash
   python3 .claude/skills/maintain-docs/check_plugin_current.py
   ```

   Exit 0 prints `ok    installed plugin matches working tree`. Any non-zero exit
   prints reconciliation steps — **STOP and relay them. Do not capture.**

2. **In-session liveness.** Confirm from your own available-skills list that
   `fsharp-code-intelligence` is present and `fsharp-lsp-queries` (the retired
   1.1.1 skill) is **absent**. If the retired skill is present, this session is
   stale even though step 1 may have passed — the on-disk copy is current but
   *this session* did not load it. Instruct a restart and STOP.

Both signals are needed: step 1 catches "edited the skill, forgot to reinstall";
step 2 catches "reinstalled but did not restart". Disabling a plugin takes effect
immediately; enabling does not until restart.

## Phase 2 — capture

Follow `references/evidence-capture.md` exactly. It lists every evidence id, the
command that produces it, and the restore discipline. In short:

- Write every block **verbatim** to `docs/evidence/transcripts.md`, home-directory
  anonymised (`/home/<user>` → `/home/you`), each under a `### <id>` heading with a
  provenance line.
- **Restore after every mutation.** `rename … --apply` and the `FS0039` build both
  change `demo/`; run `git restore demo/` after each, and before finishing assert
  `git status --porcelain demo/` is empty. A run that leaves `demo/` dirty is a
  failed run.
- **Never fabricate.** If `dotnet` is absent, skip only `build-fs0039` and record
  the gap in the evidence file. A missing id is a gap, never a guess.

## Phase 3a — README

Follow `references/readme-outline.md`: the fixed section order, the voice rules,
and the story shape. Two hard rules:

1. **No snippet without evidence.** Every fenced output block is immediately
   preceded by `<!-- evidence: <id> -->`, and its body is copied byte-for-byte
   from that evidence block. A cited id that is not in the evidence file is a
   failure — stop, do not invent output.
2. **Prose may be rewritten; facts may not be invented.** Any count, version,
   path, or exit code must trace to an evidence block or to a file in the repo.

## Phase 3b — landing page

Follow `references/site-section-map.md`: the README→HTML section map, the
deliberate omissions, and the mechanical line transform. Two invariants:

1. **Edit only `<body>` content, only the mapped sections. Never regenerate
   `<style>`** — its comments record decisions that regeneration would erase.
2. **The site may omit a README fact; it may never add one the README lacks.**

## Verify before done

Run `python3 -m pytest`. The binding test (`test_docs_evidence_binding.py`) and
the subset test (`test_docs_site_subset.py`) must be green — they mechanize the
two hard rules above. Then confirm `git status --porcelain demo/` is empty.
