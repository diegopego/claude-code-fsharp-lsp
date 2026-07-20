"""The demo project is a documentation instrument: its job is to make even an
*anchored* grep over-count, so the README's grep-vs-compiler story survives a
competent search. A naive substring grep (matching `renewalLimit`, comments) is a
strawman any real search discards; the real false positives come from a homograph
— a second function also named `renew`. `Loan.renew` renews a loan, `Member.renew`
renews a membership, and no word-boundary regex can tell them apart. If this stops
being true, the central story collapses back into that strawman."""
import re
from pathlib import Path

DEMO = Path(__file__).resolve().parent.parent / "demo"

# The loan `renew` has exactly two real references: its definition and one call.
# This is the count `findReferences` returns (see the findreferences-renew
# evidence block); keep the two in lockstep.
LOAN_RENEW_REFERENCES = 2


def _fs_lines():
    for path in sorted(DEMO.rglob("*.fs")):
        yield from path.read_text(encoding="utf-8").splitlines()


def test_anchored_grep_overcounts_because_renew_is_a_homograph():
    lines = list(_fs_lines())
    # The good regex a real search uses — word-anchored, case-sensitive.
    anchored = sum(1 for ln in lines if re.search(r"\brenew\b", ln))
    # Two *distinct* functions are declared `renew`: the homograph itself.
    definitions = sum(1 for ln in lines if re.search(r"\blet renew\b", ln))

    assert definitions >= 2, (
        "the decoy needs a second function named `renew` (the membership "
        f"homograph); found {definitions} `let renew` definition(s)")
    # Anchoring the word does NOT remove the false positives, because the second
    # `renew` is spelled identically. If it did, grep would agree with the
    # compiler and the story would have no answer.
    assert anchored > LOAN_RENEW_REFERENCES, (
        "an anchored grep no longer over-counts the loan symbol: "
        f"anchored={anchored}, true references={LOAN_RENEW_REFERENCES}")
