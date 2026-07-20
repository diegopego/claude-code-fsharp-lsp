"""The skill's files must exist and its SKILL.md must carry a name/description
front-matter block, or Claude Code will not surface /maintain-docs."""
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent / ".claude" / "skills" / "maintain-docs"


def test_skill_files_exist():
    assert (SKILL / "SKILL.md").is_file()
    for ref in ("readme-outline.md", "site-section-map.md", "evidence-capture.md"):
        assert (SKILL / "references" / ref).is_file(), ref


def test_skill_frontmatter_has_name_and_description():
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---\n")
    header = text.split("---\n", 2)[1]
    assert "name:" in header and "description:" in header


def test_skill_documents_the_evidence_ids():
    text = (SKILL / "references" / "evidence-capture.md").read_text(encoding="utf-8")
    for ident in ("fsac-version", "check-healthy", "check-broken",
                  "findreferences-renew", "hover-isoverdue",
                  "rename-dryrun", "rename-apply", "build-fs0039"):
        assert ident in text, ident
