"""The demo project is a documentation instrument: its whole job is to make a
substring grep over-count, so the README's grep-vs-compiler story has a real
answer. If this stops being true, the central story is broken."""
import re
from pathlib import Path

DEMO = Path(__file__).resolve().parent.parent / "demo"


def _fs_lines():
    for path in sorted(DEMO.rglob("*.fs")):
        yield from path.read_text(encoding="utf-8").splitlines()


def test_substring_grep_overcounts_the_renew_identifier():
    lines = list(_fs_lines())
    substring = sum(1 for ln in lines if "renew" in ln.lower())
    identifier = sum(1 for ln in lines if re.search(r"\brenew\b", ln))

    # The real symbol must exist and be referenced (definition + a use site).
    assert identifier >= 2, "expected at least a definition and one use of `renew`"
    # A naive `grep renew` sees renewalLimit / RenewalsUsed / renewAll too.
    assert substring > identifier, (
        f"decoy is not fooling grep: substring={substring} identifier={identifier}")
