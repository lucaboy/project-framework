"""Conservative adoption of existing repositories; no application commands executed."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re


def markers(name):
    if name == ".gitignore":
        return b"# >>> project-framework >>>\n", b"# <<< project-framework <<<\n"
    return b"<!-- project-framework:begin -->\n", b"<!-- project-framework:end -->\n"


def block_bounds(data, name):
    start, end = markers(name)
    starts = list(re.finditer(re.escape(start.rstrip(b"\n")) + rb"\r?\n", data))
    ends = list(re.finditer(re.escape(end.rstrip(b"\n")) + rb"\r?\n", data))
    if len(starts) != 1 or len(ends) != 1:
        raise ValueError("Managed section missing, duplicated or damaged: " + name)
    first, last = starts[0].end(), ends[0].start()
    if first > last:
        raise ValueError("Invalid managed section: " + name)
    return first, last, b"\r\n" if starts[0].group().endswith(b"\r\n") else b"\n"


def block_content(data, name):
    first, last, _ = block_bounds(data, name)
    return data[first:last].replace(b"\r\n", b"\n")


def replace_block(current, body, name, append=False):
    start, end = markers(name)
    body = body.replace(b"\r\n", b"\n").rstrip(b"\n") + b"\n"
    if start.rstrip(b"\n") in current or end.rstrip(b"\n") in current:
        first, last, newline = block_bounds(current, name)
        if append:
            raise ValueError("Section already present without a manifest: inspect " + name)
        return current[:first] + body.replace(b"\n", newline) + current[last:]
    if not append:
        raise ValueError("Managed section removed: " + name)
    separator = b"\n\n" if current and not current.endswith(b"\n") else b"\n" if current else b""
    return current + separator + start + body + end


def metadata(data, ownership, name):
    item = {"sha256": hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest(), "ownership": ownership}
    if ownership == "block":
        item["block_sha256"] = hashlib.sha256(block_content(data, name)).hexdigest()
    return item


def ownership(name, data, project_owned):
    """A template that ships its own markers is managed as a section from the first write."""
    if markers(name)[0] in data:
        return "block"
    return "project" if name in project_owned else "template"


def managed_body(name, incoming):
    if markers(name)[0] in incoming:
        return block_content(incoming, name)
    if name == "README.md":
        return ("## Agent workflow\n\n"
                "Shared instructions are in `AGENTS.md`; workflow and access checks "
                "are in `.project/WORKFLOW.md` and `.project/INTEGRATIONS.md`. "
                "Run `python3 scripts/project.py doctor` for local status.\n").encode()
    return incoming


def merge_hooks(current, incoming):
    existing = json.loads(current)
    template = json.loads(incoming)
    if not isinstance(existing, dict) or not isinstance(existing.setdefault("hooks", {}), dict):
        raise ValueError("Invalid hooks configuration.")
    for event, groups in template["hooks"].items():
        dest = existing["hooks"].setdefault(event, [])
        if not isinstance(dest, list):
            raise ValueError("Invalid hooks event: " + event)
        for group in groups:
            # Same command under another matcher does not cover the requested events.
            commands = {h.get("command") for g in dest if isinstance(g, dict) and g.get("matcher", "") == group.get("matcher", "")
                        for h in g.get("hooks", []) if isinstance(h, dict)}
            if not all(h.get("command") in commands for h in group["hooks"]):
                dest.append(group)
    # Deny rules are additive too: the project's own rules stay, the standard's are added once.
    wanted = template.get("permissions", {}).get("deny", [])
    if wanted:
        permissions = existing.setdefault("permissions", {})
        if not isinstance(permissions, dict) or not isinstance(permissions.setdefault("deny", []), list):
            raise ValueError("Invalid permissions configuration.")
        permissions["deny"].extend(rule for rule in wanted if rule not in permissions["deny"])
    return (json.dumps(existing, ensure_ascii=False, indent=2) + "\n").encode()


def inventory(root):
    names = {"package.json", "pyproject.toml", "requirements.txt", "go.mod", "Cargo.toml",
             "composer.json", "Gemfile", "Dockerfile", "docker-compose.yml", "compose.yaml",
             "pnpm-lock.yaml", "yarn.lock", "package-lock.json", "Makefile", "justfile"}
    found = []
    skip = {".git", "node_modules", ".venv", "venv", "vendor", "dist", "build", ".project"}
    # Bounded traversal, never follow links or execute discovered package scripts.
    visited = 0
    for directory, children, files in os.walk(root, followlinks=False):
        children[:] = sorted(c for c in children if c not in skip and not (Path(directory) / c).is_symlink())
        visited += 1
        for name in sorted(names.intersection(files)):
            path = Path(directory) / name
            if not path.is_symlink():
                found.append(path.relative_to(root).as_posix())
        if visited >= 1000 or len(found) >= 80:
            break
    return found[:80]


def release_notes(root):
    """Pipelines that publish on merge make a harmless-looking pull request a release."""
    pipelines = sorted((root / ".github/workflows").glob("*.y*ml")) if (root / ".github/workflows").is_dir() else []
    pipelines += [root / "bitbucket-pipelines.yml"] if (root / "bitbucket-pipelines.yml").is_file() else []
    releasing = []
    for path in pipelines[:40]:
        if path.is_symlink():
            continue
        text = path.read_bytes()[:200000].lower()
        if any(word in text or word in path.name.lower().encode() for word in (b"deploy", b"release", b"publish")):
            releasing.append(path.relative_to(root).as_posix())
    if not releasing:
        return []
    return ["Release pipelines detected (" + ", ".join(releasing) + "): before proposing a PR, check what "
            "merging into the default branch triggers and ensure release archives exclude AGENTS.md, CLAUDE.md and .project/."]


def prepare(root, files, safe_path, project_owned):
    """Preflight all collisions before the caller writes any bytes."""
    writes, entries, merged, preserved, conflicts = {}, {}, [], [], []
    notes = release_notes(root)
    review = ["Derive purpose, commands and dependencies from the actual project; run relevant checks.",
              "Check directory-specific instructions and resolve conflicting rules."]
    if safe_path(root, "AGENTS.override.md").is_file():
        files = {**files, "AGENTS.override.md": files["AGENTS.md"]}
    for name, incoming in files.items():
        path = safe_path(root, name)
        if not path.exists():
            writes[name] = incoming
            entries[name] = metadata(incoming, ownership(name, incoming, project_owned), name)
            continue
        if not path.is_file():
            conflicts.append(name)
            continue
        current = path.read_bytes()
        if name in {"AGENTS.md", "AGENTS.override.md", "CLAUDE.md", ".gitignore", "README.md"}:
            if name == "CLAUDE.md" and len(current.split()) > 40:
                notes.append("CLAUDE.md already contains instructions that Codex does not read: propose moving "
                             "shared rules into AGENTS.md, keeping the import in CLAUDE.md.")
            if name == "CLAUDE.md" and any(line.strip() in (b"@AGENTS.md", b"@./AGENTS.md") for line in current.splitlines()):
                entries[name] = metadata(current, "project", name)
                preserved.append(name)
            else:
                writes[name] = replace_block(current, managed_body(name, incoming), name, append=True)
                entries[name] = metadata(writes[name], "block", name)
                merged.append(name)
        elif name in {".claude/settings.json", ".codex/hooks.json"}:
            writes[name] = merge_hooks(current, incoming)
            # User settings are never replaced by future template updates.
            entries[name] = metadata(writes[name], "project", name)
            merged.append(name)
        elif name in project_owned or name == ".codex/config.toml" or name == ".env.example" or name.startswith(".github/") or name == "bitbucket-pipelines.yml":
            # config.json is reserved: silently adopting a foreign schema would break the runtime.
            if name == ".project/config.json":
                conflicts.append(name)
                continue
            entries[name] = metadata(current, "project", name)
            preserved.append(name)
            if name.endswith(("ci.yml", "bitbucket-pipelines.yml")):
                review.append("Existing CI preserved: integrate doctor/verify only after mapping its actual checks.")
            if name == "openspec/config.yaml":
                review.append("Existing OpenSpec config preserved: compare and integrate relevant context and rules.")
            if name == ".codex/config.toml":
                review.append("Codex config preserved: check that hooks are enabled and the project is trusted.")
        elif current == incoming:
            entries[name] = metadata(current, "template", name)
            preserved.append(name)
        else:
            conflicts.append(name)
    report = {"schema_version": 1, "status": "requires_project_review", "merged": merged,
              "preserved": preserved, "blocking_collisions": conflicts, "manifests_found": inventory(root),
              "review": list(dict.fromkeys(review + notes)), "notes": notes, "evidence": [],
              "application_commands_executed": [],
              "note": "No migration of code, backlog or remote services; the generator has not executed "
                      "application commands. After review, list the checks performed and their "
                      "results in evidence, then set status to reviewed."}
    return writes, entries, report
