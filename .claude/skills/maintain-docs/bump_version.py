#!/usr/bin/env python3
"""Bump the plugin's version in .claude-plugin/plugin.json.

Every release bumps this version (CLAUDE.md): Claude Code re-pulls github-sourced
marketplaces, so an unbumped version is how a stale copy survives unnoticed. This
does a MINIMAL in-place edit of the version string — it rewrites nothing else, so
a release commit stays a one-line diff — and prints the new version to stdout for
the Makefile's release target to put in the commit message.

Standard library only. Exit: 0 bumped | 2 no semver version field.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_NO_FIELD = 2

_VERSION = re.compile(r'("version"\s*:\s*")(\d+)\.(\d+)\.(\d+)(")')


def bump(text: str, level: str) -> tuple[str, str]:
    """Return (new_text, new_version). Only the version span is rewritten."""
    m = _VERSION.search(text)
    if not m:
        raise ValueError('no "version": "x.y.z" field found')
    major, minor, patch = int(m.group(2)), int(m.group(3)), int(m.group(4))
    if level == "major":
        major, minor, patch = major + 1, 0, 0
    elif level == "minor":
        minor, patch = minor + 1, 0
    elif level == "patch":
        patch += 1
    else:  # argparse restricts this, but keep the guard honest
        raise ValueError(f"unknown level: {level}")
    new_version = f"{major}.{minor}.{patch}"
    # Replace only the digits between group 1 (the `"version": "`) and group 5
    # (the closing quote), leaving every surrounding byte untouched.
    new_text = text[:m.start(2)] + new_version + text[m.end(4):]
    return new_text, new_version


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--level", choices=("patch", "minor", "major"), default="patch")
    p.add_argument("--file", type=Path,
                   default=Path(__file__).resolve().parents[3] / ".claude-plugin" / "plugin.json",
                   help="the plugin manifest (default: this repo's plugin.json)")
    args = p.parse_args()

    text = args.file.read_text(encoding="utf-8")
    try:
        new_text, new_version = bump(text, args.level)
    except ValueError as e:
        print(f"ERROR: {e} in {args.file}", file=sys.stderr)
        return EXIT_NO_FIELD
    args.file.write_text(new_text, encoding="utf-8")
    print(new_version)
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
