#!/usr/bin/env python3
"""Push this working tree's plugin files into the active installed copy.

The plugin is installed as a COPY in the cache, keyed by version — editing the
repository does not reach the running plugin, and a same-version reinstall may
not refresh it. This mirrors the plugin's own files (.lsp.json, .claude-plugin,
skills, tools, hooks) from the working tree into the active install path, so an
unpublished change loads after a reload without a version bump.

It is the inverse of check_plugin_current.py: the gate DETECTS a stale copy,
this MAKES the copy current. Run it, RESTART the session, then run the gate to
confirm it went green. Scaffolding the plugin does not ship (.git, tests, docs,
demo, build output) is never copied.

Standard library only. Exit: 0 synced | 1 no install found.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

EXIT_OK = 0

# Exactly what the plugin ships and needs at runtime — nothing else is pushed.
PLUGIN_FILES = (".lsp.json",)
PLUGIN_DIRS = (".claude-plugin", "skills", "tools", "hooks")
_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", "bin", "obj")


def active_install_paths(installed_json: Path, plugin: str = "fsharp-lsp") -> list[Path]:
    """Every distinct installPath recorded for the plugin.

    Deduped: the same path is commonly listed under more than one scope
    (project and local), and syncing it twice is pointless.
    """
    try:
        data = json.loads(installed_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    seen: set[str] = set()
    out: list[Path] = []
    for key, entries in data.get("plugins", {}).items():
        if key.split("@", 1)[0] == plugin:
            for entry in entries:
                p = entry.get("installPath")
                if p and p not in seen:
                    seen.add(p)
                    out.append(Path(p))
    return out


def sync_into(working_tree: Path, dest: Path) -> list[str]:
    """Replace the plugin files under dest with the working tree's copies."""
    changed: list[str] = []
    for name in PLUGIN_FILES:
        src = working_tree / name
        if src.is_file():
            shutil.copy2(src, dest / name)
            changed.append(name)
    for name in PLUGIN_DIRS:
        src = working_tree / name
        if src.is_dir():
            target = dest / name
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(src, target, ignore=_IGNORE)
            changed.append(name + "/")
    return changed


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--working-tree", type=Path,
                   default=Path(__file__).resolve().parents[3],
                   help="repo root to push from (default: this repo)")
    p.add_argument("--installed-json", type=Path,
                   default=Path.home() / ".claude" / "plugins" / "installed_plugins.json",
                   help="Claude Code's installed-plugins registry")
    p.add_argument("--dest", type=Path,
                   help="push into this path directly instead of reading the registry")
    args = p.parse_args()

    dests = [args.dest] if args.dest else active_install_paths(args.installed_json)
    if not dests:
        # Not an error: this runs as a prerequisite of `make test`, which must
        # work on a machine where the plugin was never installed (fresh clone,
        # first use, CI). Nothing to sync is a fine outcome.
        print(f"no installed fsharp-lsp found in {args.installed_json}; "
              f"nothing to refresh.")
        return EXIT_OK

    for dest in dests:
        if not dest.is_dir():
            print(f"  skip (missing): {dest}")
            continue
        changed = sync_into(args.working_tree, dest)
        print(f"  synced {', '.join(changed)} -> {dest}")

    print("Restart any open Claude session to load the changes.")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
