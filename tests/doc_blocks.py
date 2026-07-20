"""Parsers shared by the documentation-consistency tests. Deliberately small and
regex-based: the documents are generated, so their shape is known and fixed."""
import re

_FENCE = r"```[^\n]*\n(.*?)\n```"


def evidence_blocks(md: str) -> dict[str, str]:
    """Map each `### id` heading to the body of the fenced block that follows."""
    out: dict[str, str] = {}
    for m in re.finditer(r"^###[ \t]+(\S+)[ \t]*\n(.*?)(?=^###[ \t]|\Z)",
                         md, re.MULTILINE | re.DOTALL):
        ident, section = m.group(1), m.group(2)
        fence = re.search(_FENCE, section, re.DOTALL)
        if fence:
            out[ident] = fence.group(1).strip("\n")
    return out


def readme_evidence_refs(md: str) -> list[tuple[str, str]]:
    """Each `<!-- evidence: id -->` immediately followed by a fenced block."""
    out: list[tuple[str, str]] = []
    for m in re.finditer(
            r"<!--[ \t]*evidence:[ \t]*(\S+?)[ \t]*-->[ \t]*\n" + _FENCE,
            md, re.DOTALL):
        out.append((m.group(1), m.group(2).strip("\n")))
    return out


def _strip_tags(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html)


def site_term_commands(html: str) -> list[str]:
    """Plain text of each `.line` that begins with the shell prompt `$`."""
    cmds: list[str] = []
    for body in re.finditer(r'<div class="term-body[^"]*">(.*?)</div>\s*</div>',
                            html, re.DOTALL):
        for line in re.finditer(r'<div class="line">(.*?)</div>',
                                body.group(1), re.DOTALL):
            text = _strip_tags(line.group(1)).strip()
            text = re.sub(r"\s+", " ", text)
            if text.startswith("$"):
                cmds.append(text)
    return cmds
