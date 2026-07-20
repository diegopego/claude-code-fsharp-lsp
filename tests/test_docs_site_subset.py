"""The landing page may omit README facts but must never add one. Every shell
command shown on the site must appear in a README fenced block."""
import re
from pathlib import Path

from doc_blocks import site_term_commands

ROOT = Path(__file__).resolve().parent.parent


def _readme_fenced_text() -> str:
    # Fences are anchored to the start of a line, so a blockquoted fence
    # (`> ```) does not mis-pair and swallow the prose between real code blocks.
    md = (ROOT / "README.md").read_text(encoding="utf-8")
    return "\n".join(m.group(1) for m in
                     re.finditer(r"^```[^\n]*\n(.*?)\n```", md,
                                 re.MULTILINE | re.DOTALL))


def test_site_adds_no_command_absent_from_readme():
    html = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
    readme_text = _readme_fenced_text()
    for cmd in site_term_commands(html):
        body = cmd[1:].strip()  # drop the leading '$'
        assert body in readme_text, f"site shows a command not in README: {body!r}"
