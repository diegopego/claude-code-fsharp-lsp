#!/usr/bin/env python3
"""Warn when fsharp-lsp is installed from more than one source (marketplace).

Two installs of the same LSP plugin register the .fs server twice and spawn two
fsautocomplete processes — a real failure this repo has seen (HANDOFF.md: two F#
plugins active at once, one FSAC reaching 5.4 GB). `make use-dev-plugin` runs
this FIRST and refuses to add a third copy on top of a conflict.

A conflict is 2+ distinct marketplaces for one plugin name. The same plugin under
two SCOPES of one marketplace is a single registration, not a conflict.

Standard library only. Exit: 0 at most one source | 3 conflict.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

EXIT_OK = 0
EXIT_CONFLICT = 3


def sources(installed: dict, plugin: str) -> list[str]:
    """Distinct marketplaces the plugin is installed from, in first-seen order."""
    found: list[str] = []
    for key in installed.get("plugins", {}):
        name, _, marketplace = key.partition("@")
        if name == plugin and marketplace not in found:
            found.append(marketplace)
    return found


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--installed-json", type=Path,
                   default=Path.home() / ".claude" / "plugins" / "installed_plugins.json",
                   help="Claude Code's installed-plugins registry")
    p.add_argument("--plugin", default="fsharp-lsp",
                   help="plugin name to check (default: fsharp-lsp)")
    args = p.parse_args()

    try:
        data = json.loads(args.installed_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}

    markets = sources(data, args.plugin)
    if len(markets) > 1:
        listing = "\n".join(f"    - {m}" for m in markets)
        print(f"CONFLICT: {args.plugin} is installed from {len(markets)} sources:\n"
              f"{listing}\n"
              f"Two installs register the .fs server twice (double fsautocomplete). "
              f"Uninstall the extras with\n"
              f"    claude plugin uninstall {args.plugin}@<marketplace> --scope <scope>\n"
              f"and re-run.")
        return EXIT_CONFLICT

    print(f"  ok    {args.plugin}: {len(markets)} source(s) — no conflict")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
