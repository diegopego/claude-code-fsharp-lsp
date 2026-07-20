#!/usr/bin/env python3
"""Refuse to capture documentation evidence unless the INSTALLED plugin is
byte-identical to the working tree.

Claude's behaviour in a doc story comes from the *installed* skill. Capturing
from a stale install narrates a tool that may no longer exist. This checks
content identity — .lsp.json + skills/** + tools/** — against every plugin copy
cached under any marketplace, and exits non-zero with the fix if none match.

This is the on-disk half of the gate. The in-session half (is *this session*
running the current skill?) is a human/Claude check, described in SKILL.md.

Why content hashes and not version numbers: a local install copies the files
into a version-keyed cache dir, and you can reinstall at the same version. A
version check would see 2.1.0 == 2.1.0 while the bytes differ — the exact
false-green this exists to prevent.

Standard library only. Exit: 0 identical | 2 stale or absent.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

EXIT_OK = 0
EXIT_STALE = 2

# The plugin is these three things; nothing else is hashed.
PLUGIN_FILE = ".lsp.json"
PLUGIN_DIRS = ("skills", "tools")


def manifest_hash(root: Path) -> str:
    """A stable hash of every plugin file's relative path and contents."""
    files: list[Path] = []
    lsp = root / PLUGIN_FILE
    if lsp.is_file():
        files.append(lsp)
    for sub in PLUGIN_DIRS:
        d = root / sub
        if d.is_dir():
            files += [p for p in d.rglob("*")
                      if p.is_file() and "__pycache__" not in p.parts
                      and p.suffix != ".pyc"]
    parts = []
    for p in sorted(files, key=lambda p: p.relative_to(root).as_posix()):
        rel = p.relative_to(root).as_posix()
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
        parts.append(f"{rel}:{digest}")
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def installed_copies(cache_root: Path) -> list[Path]:
    """Every cached plugin dir, across all marketplaces:
    <cache>/<marketplace>/fsharp-lsp/<version>/"""
    return sorted(d for d in cache_root.glob("*/fsharp-lsp/*") if d.is_dir())


RECONCILE = (
    "Reconcile before capturing:\n"
    "  1. Add a local marketplace pointing at this working tree.\n"
    "  2. /plugin install fsharp-lsp@<that-marketplace>\n"
    "  3. RESTART the session — enabling does not take effect until then.\n"
    "  4. Re-run /maintain-docs."
)


def check(working_tree: Path, cache_root: Path) -> int:
    want = manifest_hash(working_tree)
    copies = installed_copies(cache_root)
    if not copies:
        print(f"fsharp-lsp not installed under {cache_root}. {RECONCILE}")
        return EXIT_STALE
    for copy in copies:
        if manifest_hash(copy) == want:
            print(f"  ok    installed plugin matches working tree ({copy})")
            return EXIT_OK
    listing = "\n".join(f"    {c}" for c in copies)
    print("Installed plugin(s) differ from the working tree:\n"
          f"{listing}\n{RECONCILE}")
    return EXIT_STALE


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--working-tree", type=Path,
                   default=Path(__file__).resolve().parents[3],
                   help="repo root holding .lsp.json/skills/tools (default: this repo)")
    p.add_argument("--cache-root", type=Path,
                   default=Path.home() / ".claude" / "plugins" / "cache",
                   help="Claude Code plugin cache root")
    args = p.parse_args()
    return check(args.working_tree, args.cache_root)


if __name__ == "__main__":
    raise SystemExit(main())
