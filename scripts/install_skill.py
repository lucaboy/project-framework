#!/usr/bin/env python3
"""Install this complete skill. Preview by default; never overwrite an installation."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys

PACKAGE = Path(__file__).resolve().parent.parent


def skipped(directory, names):
    """Leave out local clutter everywhere, and repository-only entries at the package root."""
    drop = {name for name in names if name in {".DS_Store", "__pycache__"} or name.endswith(".zip")}
    if Path(directory) == PACKAGE:
        # Only here: assets/ ships a .gitignore that every generated project needs.
        drop |= {".git", ".gitignore", ".gitattributes", ".github", "tests", "dist"} & set(names)
    return drop


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", choices=["codex", "claude", "both"], default="codex")
    parser.add_argument("--project", type=Path, help="Install in a project instead of the personal profile.")
    parser.add_argument("--base", type=Path, help="Explicit base directory for a portable personal installation.")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.project and args.base:
        parser.error("Choose either --project or --base.")
    base = (args.project or args.base or Path.home()).expanduser().resolve()
    clients = ["codex", "claude"] if args.client == "both" else [args.client]
    destinations = []
    for client in clients:
        # Codex reads personal and project skills from .agents/skills; CODEX_HOME holds configuration only.
        client_root = base / (".agents" if client == "codex" else ".claude")
        safety_root = base
        if client == "claude" and not args.project and not args.base and os.environ.get("CLAUDE_CONFIG_DIR"):
            client_root = Path(os.environ["CLAUDE_CONFIG_DIR"]).expanduser().resolve()
            safety_root = client_root
        path = client_root / "skills" / "project-framework"
        if PACKAGE == path or PACKAGE in path.parents or path in PACKAGE.parents:
            raise ValueError("Installation cannot contain or be contained in the source package.")
        current = safety_root
        for part in path.relative_to(safety_root).parts:
            current /= part
            if current.is_symlink():
                raise ValueError("Symbolic-link destination not allowed: " + str(current))
        if path.exists():
            raise ValueError("Skill already present; refusing to overwrite: " + str(path))
        destinations.append(path)
    if args.apply:
        for path in destinations:
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(PACKAGE, path, ignore=skipped)
    print(json.dumps({"status": "installed" if args.apply else "plan", "paths": list(map(str, destinations)),
                      "note": "Open a new session to check that the client discovers the skill."}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as error:
        print(json.dumps({"status": "error", "message": str(error)}))
        sys.exit(2)
