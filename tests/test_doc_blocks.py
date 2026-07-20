from doc_blocks import evidence_blocks, readme_evidence_refs, site_term_commands

EVIDENCE = """\
# transcripts

### fsac-version
captured: 2026-07-20 · fsac: 0.83.0
```
$ fsautocomplete --version
0.83.0
```

### rename-dryrun
captured: 2026-07-20
```
DRY RUN: rename -> 'renewLoan' | 2 file(s), 2 edit(s)
```
"""

README = """\
## Prereqs

<!-- evidence: fsac-version -->
```
$ fsautocomplete --version
0.83.0
```

Some prose.
"""

SITE = """\
<div class="term-body wraps">
<div class="line"><span class="prompt">$</span> <span class="cmd">fsautocomplete --version</span></div>
<div class="line"><span class="dim">0.83.0</span></div>
</div>
"""


def test_evidence_blocks_indexes_by_id():
    blocks = evidence_blocks(EVIDENCE)
    assert set(blocks) == {"fsac-version", "rename-dryrun"}
    assert blocks["fsac-version"] == "$ fsautocomplete --version\n0.83.0"


def test_readme_evidence_refs_pairs_marker_with_block():
    refs = readme_evidence_refs(README)
    assert refs == [("fsac-version", "$ fsautocomplete --version\n0.83.0")]


def test_site_term_commands_extracts_prompt_lines_as_plain_text():
    cmds = site_term_commands(SITE)
    assert cmds == ["$ fsautocomplete --version"]
