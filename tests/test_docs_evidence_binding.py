"""Every evidence-marked block in the README must exist in the evidence file and
match it byte-for-byte. This mechanizes the skill's 'no snippet without
evidence' rule as a committed guard."""
from pathlib import Path

from doc_blocks import evidence_blocks, readme_evidence_refs

ROOT = Path(__file__).resolve().parent.parent
REQUIRED = {"fsac-version", "check-healthy", "check-broken",
            "findreferences-renew", "hover-isoverdue",
            "rename-dryrun", "rename-apply"}  # build-fs0039 is optional (needs SDK)


def test_every_readme_evidence_block_binds_to_the_evidence_file():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    evidence = evidence_blocks(
        (ROOT / "docs" / "evidence" / "transcripts.md").read_text(encoding="utf-8"))
    refs = readme_evidence_refs(readme)
    assert refs, "README has no evidence-marked blocks"
    for ident, body in refs:
        assert ident in evidence, f"README cites unknown evidence id: {ident}"
        assert body == evidence[ident], f"README block for {ident} != evidence"


def test_required_stories_are_present():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    cited = {ident for ident, _ in readme_evidence_refs(readme)}
    missing = REQUIRED - cited
    assert not missing, f"README is missing required evidence blocks: {missing}"
