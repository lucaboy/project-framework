#!/usr/bin/env python3
"""Dependency-free project generator. Dry-run by default; no remote operations."""
from __future__ import annotations

import argparse
import base64
import difflib
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit

import adoption

PACKAGE = Path(__file__).resolve().parent.parent
VERSION = (PACKAGE / "VERSION").read_text(encoding="utf-8").strip()
OPENSPEC = "2.0.0"
STATE = ".project/template-state.json"
PENDING = ".project/local/framework-pending.json"
CHOICES = ("name", "slug", "provider", "tracker", "profile", "kind", "workspace_url")
TOKEN = re.compile(r"@@([A-Z_]+)@@")
PROJECT_OWNED = {
    "README.md", ".project/config.json", "openspec/config.yaml",
    "docs/INDEX.md", "docs/PRODUCT.md", "docs/ARCHITECTURE.md",
    "docs/UI.md", "docs/INFRASTRUCTURE.md", "docs/SECURITY.md",
    "docs/MARKETING.md", "docs/CLIENTS.md",
    ".claude/settings.json", ".codex/hooks.json", ".codex/config.toml",
    # Stubs that every project is expected to edit: an upstream change must not block updates.
    ".env.example", ".github/workflows/ci.yml", "bitbucket-pipelines.yml",
}


class Problem(Exception):
    pass


def emit(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def digest(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def safe_path(root, relative):
    path = PurePosixPath(relative)
    if not relative or path.is_absolute() or ".." in path.parts or "\\" in relative:
        raise Problem(f"Path not allowed: {relative!r}")
    current = root
    for part in path.parts:
        current = current / part
        if current.is_symlink():
            raise Problem(f"Symbolic link not allowed: {current}")
    return current


def file_mode(path):
    """mkstemp creates 0600 files: keep an existing mode, otherwise honor the umask."""
    try:
        return stat.S_IMODE(path.stat().st_mode)
    except FileNotFoundError:
        umask = os.umask(0)
        os.umask(umask)
        return 0o666 & ~umask


def write_atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = file_mode(path)
    fd, temporary = tempfile.mkstemp(prefix=".framework-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def pending_plan(root):
    """Validate the complete journal before resuming any writes."""
    journal = json.loads(safe_path(root, PENDING).read_text(encoding="utf-8"))
    if (not isinstance(journal, dict) or journal.get("schema_version") != 1
            or journal.get("action") not in {"init", "update"} or not isinstance(journal.get("files"), dict)):
        raise Problem("Unrecognized recovery journal.")
    writes, conflicts = {}, []
    for name, entry in journal["files"].items():
        if name == PENDING or not isinstance(entry, dict):
            raise Problem("Invalid recovery journal.")
        path = safe_path(root, name)
        data = base64.b64decode(entry["content"], validate=True)
        if digest(data) != entry["after"]:
            raise Problem("Corrupt content in recovery journal: " + name)
        if path.exists() and not path.is_file():
            conflicts.append(name)
            continue
        current = digest(path.read_bytes()) if path.is_file() else None
        if current == entry["after"]:
            continue
        if current != entry["before"]:
            conflicts.append(name)
        else:
            writes[name] = data
    if STATE not in journal["files"]:
        raise Problem("Recovery journal is missing its manifest.")
    return journal, writes, conflicts


def finish_pending(root):
    journal, writes, conflicts = pending_plan(root)
    if conflicts:
        raise Problem("Recovery blocked: files changed after planning: " + ", ".join(conflicts))
    # The manifest is always the final project file, including after a partial application.
    for name in [n for n in writes if n != STATE] + ([STATE] if STATE in writes else []):
        write_atomic(safe_path(root, name), writes[name])
    if journal.get("git_init") and existing_git(root) is None:
        result = subprocess.run(["git", "init", "-b", "main", str(root)], capture_output=True, text=True)
        if result.returncode:
            raise Problem("Files created, but git init failed. Resume with recover: " + result.stderr.strip())
    safe_path(root, PENDING).unlink()
    if journal.get("created_local"):
        try:
            safe_path(root, PENDING).parent.rmdir()
        except OSError:
            pass  # Other local state may have appeared during an interrupted operation.


def apply_files(root, writes, state, action, git_init=False):
    """Persist the plan first. A retry can finish it without guessing the original state."""
    pending = safe_path(root, PENDING)
    if pending.exists():
        raise Problem("Incomplete operation: run framework.py recover DIRECTORY before continuing.")
    entries = {}
    for name, data in {**writes, STATE: json_bytes(state)}.items():
        path = safe_path(root, name)
        entries[name] = {"before": digest(path.read_bytes()) if path.is_file() else None,
                         "after": digest(data), "content": base64.b64encode(data).decode("ascii")}
    journal = {"schema_version": 1, "action": action, "version": VERSION, "git_init": git_init, "files": entries,
               "created_local": not pending.parent.exists()}
    write_atomic(pending, json_bytes(journal))
    os.chmod(pending, 0o600)
    finish_pending(root)


def recover(args, root):
    if not safe_path(root, PENDING).is_file():
        raise Problem("No incomplete operation to recover.")
    journal, writes, conflicts = pending_plan(root)
    if conflicts:
        emit({"status": "conflict", "files": conflicts, "writes": 0,
              "message": "Files changed after interruption: nothing written. Compare against the plan before retrying."})
        return 2
    if args.apply:
        finish_pending(root)
    emit({"status": "recovered" if args.apply else "plan", "action": journal["action"],
          "version": journal["version"], "files": sorted(writes), "git_init": journal.get("git_init", False),
          "remote_operations": [], "next": "Resume project configuration and verification."})
    return 0


def validate_answers(answers):
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", answers["slug"]):
        raise Problem("Slug: use lowercase letters, digits and single hyphens.")
    if not answers["name"].strip() or any(ord(c) < 32 for c in answers["name"]):
        raise Problem("Name must be nonempty and on one line.")
    if answers["provider"] not in {"github", "bitbucket"}:
        raise Problem("Unsupported provider.")
    if answers["tracker"] not in {"jira", "github"}:
        raise Problem("Unsupported tracker.")
    if answers["provider"] == "bitbucket" and answers["tracker"] == "github":
        raise Problem("Use Jira with Bitbucket; a parallel GitHub tracker is not created.")
    if answers["profile"] not in {"generic", "web"}:
        raise Problem("Unsupported profile.")
    if answers["kind"] not in {"single", "workspace", "component"}:
        raise Problem("Unsupported kind: use single, workspace or component.")
    link = urlsplit(answers["workspace_url"])
    if answers["workspace_url"] and answers["kind"] != "component":
        raise Problem("--workspace-url requires --kind component.")
    if answers["workspace_url"] and (link.scheme != "https" or not link.hostname or link.username
                                     or link.password or link.query or link.fragment):
        raise Problem("--workspace-url: use the workspace HTTPS URL without credentials, queries or fragments.")


def render(answers):
    validate_answers(answers)
    values = {"NAME": answers["name"], "SLUG": answers["slug"], "VERSION": VERSION,
              "OPENSPEC": OPENSPEC,
              # The workspace repository may be connected later: update --workspace-url fills it in.
              "WORKSPACE": answers["workspace_url"] or "URL not linked yet: ask the project maintainer"}
    files = {}
    component = answers["kind"] == "component"
    # A component repository only carries its own short instructions: the method lives in the workspace.
    for layer in ["component"] if component else ["common", answers["provider"]]:
        directory = PACKAGE / "assets" / "project" / layer
        for source in sorted(directory.rglob("*")):
            if "__pycache__" in source.parts or source.suffix in {".pyc", ".pyo"} or source.name == ".DS_Store":
                continue
            if not source.is_file():
                continue
            if source.is_symlink():
                raise Problem(f"Symbolic-link asset not allowed: {source}")
            # Instruction files are stored as *.tmpl: under their real names the clients
            # would load them as live rules of this package while it is read or maintained.
            relative = source.relative_to(directory).as_posix().removesuffix(".tmpl")
            if relative.startswith(".github/ISSUE_TEMPLATE/") and answers["tracker"] != "github":
                continue
            raw = source.read_text(encoding="utf-8")
            unknown = set(TOKEN.findall(raw)) - values.keys()
            if unknown:
                raise Problem(f"Unknown tokens in {relative}: {sorted(unknown)}")
            files[relative] = TOKEN.sub(lambda m: values[m.group(1)], raw).encode()
    if component:
        if answers.get("root_override"):
            files["AGENTS.override.md"] = files["AGENTS.md"]
        return files
    config = {
        "schema_version": 2, "name": answers["name"], "slug": answers["slug"], "kind": answers["kind"],
        "profile": answers["profile"], "provider": answers["provider"],
        "tracker": answers["tracker"], "default_branch": "main",
        "purpose": "", "content_language": "", "commands": [], "command_timeout_seconds": 600,
        "repositories": [], "documents": [],
        "automation": {"tracker": "guided", "documentation": "guided"},
        "integrations": {"repository_url": "", "jira_url": "", "jira_project_key": "",
                         "confluence_url": "", "confluence_space_key": "", "hub_url": "", "map_url": ""},
    }
    files[".project/config.json"] = json_bytes(config)
    files[".project/dependencies.json"] = json_bytes({
        "openspec": {"package": "@fission-ai/openspec", "version": OPENSPEC,
                     "minimum_node": "22.12.0", "profile": "core",
                     "skills": ["openspec-apply-change", "openspec-archive-change", "openspec-explore",
                                "openspec-propose", "openspec-sync-specs", "openspec-update-change"],
                     "tools": ["codex", "claude"]},
    })
    if answers["profile"] == "web":
        files["docs/ARCHITECTURE.md"] += (
            "\n## Areas to map\n\n"
            "Identify frontend, backend, API contracts, UI and infrastructure in the actual repository. "
            "Describe dependencies and commands by area before splitting work between agents.\n"
        ).encode()
    if answers.get("root_override"):
        files["AGENTS.override.md"] = files["AGENTS.md"]
    if answers["kind"] == "workspace":
        # Application repositories are cloned into repos/ and keep their own history and pipelines:
        # the workspace pipeline can only check the structure.
        files[".gitignore"] += b"repos/\n"
        for name, line in ((".github/workflows/ci.yml", b"      - run: python3 scripts/project.py verify\n"),
                           ("bitbucket-pipelines.yml", b"            - python3 scripts/project.py verify\n")):
            if name in files:
                files[name] = files[name].replace(line, b"")
    branch = json.dumps(answers.get("default_branch", "main")).encode()
    if ".github/workflows/ci.yml" in files:
        files[".github/workflows/ci.yml"] = files[".github/workflows/ci.yml"].replace(b"branches: [main]", b"branches: [" + branch + b"]")
    if "bitbucket-pipelines.yml" in files:
        files["bitbucket-pipelines.yml"] = files["bitbucket-pipelines.yml"].replace(b"    main:\n", b"    " + branch + b":\n")
    return files


def suggested_names(answers):
    """Names to propose when the user wants new remote resources; nothing is created here."""
    slug = answers["slug"]
    words = slug.split("-")
    key = ("".join(word[0] for word in words) if len(words) > 1 else slug[:4]).upper()[:10]
    if not key[0].isalpha():
        key = ("P" + key)[:10]
    if len(key) < 2:
        key += "X"
    workspace = answers["kind"] == "workspace"
    return {"repository": slug + "-workspace" if workspace else slug, "jira_project_key": key,
            "confluence_space_key": key, "hub_page_title": answers["name"] + " — Hub"}


def existing_git(root):
    """Read only this repository; never infer state from an ancestor checkout."""
    if not root.exists():
        return None
    def read(*argv):
        result = subprocess.run(["git", "-C", str(root), *argv], capture_output=True, text=True)
        return result.stdout.strip() if result.returncode == 0 else ""
    if not shutil.which("git"):
        return None
    top = read("rev-parse", "--show-toplevel")
    if not top or Path(top).resolve() != root.resolve():
        return None
    remote = read("config", "--get", "remote.origin.url")
    match = re.fullmatch(r"git@(?P<host>github\.com|bitbucket\.org):(?P<path>[^\s]+)", remote)
    if match:
        repository = "https://" + match["host"] + "/" + match["path"].removesuffix(".git").rstrip("/")
    else:
        parsed = urlsplit(remote)
        repository = ("https://" + parsed.hostname + parsed.path.removesuffix(".git").rstrip("/")) if (
            parsed.scheme == "https" and parsed.hostname in {"github.com", "bitbucket.org"}
            and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment) else ""
    branch = read("symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD").removeprefix("origin/")
    if not branch:
        branches = read("for-each-ref", "--format=%(refname:short)", "refs/heads").splitlines()
        branch = "main" if "main" in branches else "master" if "master" in branches else read("branch", "--show-current") or "main"
    return {"repository_url": repository, "default_branch": branch}


def enclosing_repository(root):
    """Top level of an ancestor checkout that contains the destination, if any."""
    if not shutil.which("git"):
        return None
    probe = root
    while not probe.exists():
        probe = probe.parent
    result = subprocess.run(["git", "-C", str(probe), "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    top = result.stdout.strip()
    if result.returncode or not top or Path(top).resolve() == root:
        return None
    # A workspace ignores repos/: a repository created there is meant to be a separate one.
    ignored = subprocess.run(["git", "-C", top, "check-ignore", "-q", str(root)], capture_output=True)
    return None if ignored.returncode == 0 else top


def occupied(root):
    """Version-control metadata alone, as in a fresh clone, is not project content."""
    return root.exists() and any(child.name not in {".git", ".DS_Store"} for child in root.iterdir())


def version_tuple(text):
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", str(text))
    if not match:
        raise Problem(f"Unrecognized standard version: {text!r}")
    return tuple(map(int, match.groups()))


def unified(current, incoming, name, limit=120):
    lines = list(difflib.unified_diff(current.decode("utf-8", "replace").splitlines(),
                                      incoming.decode("utf-8", "replace").splitlines(),
                                      "project/" + name, "skill/" + name, lineterm=""))
    if len(lines) > limit:
        lines = lines[:limit] + [f"... {len(lines) - limit} lines omitted"]
    return "\n".join(lines)


def git_cautions(root):
    """An update can only be reviewed and undone against a state saved in Git."""
    if not shutil.which("git"):
        return []

    def run(*argv):
        return subprocess.run(["git", "-C", str(root), *argv], capture_output=True, text=True)

    top = run("rev-parse", "--show-toplevel")
    if top.returncode or Path(top.stdout.strip()).resolve() != root:
        return ["This directory is not a Git repository root: the update cannot be "
                "compared or undone with Git."]
    if run("rev-parse", "--verify", "-q", "HEAD").returncode:
        return ["The repository has no commits: propose an initial commit before applying, "
                "otherwise there is no saved state to restore."]
    return []


def load_state(root):
    path = safe_path(root, STATE)
    if not path.is_file():
        raise Problem("Standard not initialized: missing .project/template-state.json.")
    state = json.loads(path.read_text(encoding="utf-8"))
    if state.get("schema_version") != 1:
        raise Problem("Unsupported manifest version.")
    validate_answers(state["answers"])
    for relative in state["files"]:
        safe_path(root, relative)
    return state


def init(args, root):
    slug = args.slug or re.sub(r"[^a-z0-9]+", "-", args.name.lower()).strip("-")
    answers = {"name": args.name, "slug": slug, "provider": args.provider, "tracker": args.tracker,
               "profile": args.profile, "kind": args.kind, "workspace_url": (args.workspace_url or "").rstrip("/")}
    if safe_path(root, "AGENTS.override.md").exists():
        answers["root_override"] = True
    repository = existing_git(root)
    if repository and repository["default_branch"] != "main":
        answers["default_branch"] = repository["default_branch"]
    files = render(answers)
    if safe_path(root, STATE).exists():
        state = load_state(root)
        # Only what the user chose identifies the project: the branch and the override file are
        # observed from the checkout and may legitimately differ between two runs.
        if any(state["answers"].get(key) != answers[key] for key in CHOICES):
            raise Problem("Project already initialized with different options; it will not be reconfigured.")
        emit({"status": "already_initialized", "path": str(root),
              "version": state["template_version"],
              "next": "To resume work on this computer, run python3 scripts/project.py doctor in the "
                      "project. Use update only to change the standard version."})
        return 0
    if occupied(root) and not args.adopt:
        raise Problem("Directory is not empty. Read existing files, then use --adopt to add the standard.")
    if repository and ".project/config.json" in files:
        project_config = json.loads(files[".project/config.json"])
        project_config["default_branch"] = repository["default_branch"]
        project_config["integrations"]["repository_url"] = repository["repository_url"]
        remote = repository["repository_url"]
        if remote and ((urlsplit(remote).hostname == "bitbucket.org") != (args.provider == "bitbucket")):
            raise Problem("Selected provider differs from origin; select the existing provider before adoption.")
        files[".project/config.json"] = json_bytes(project_config)
    report = None
    if args.adopt:
        writes, entries, report = adoption.prepare(root, files, safe_path, PROJECT_OWNED)
        conflicts = report["blocking_collisions"]
        if answers["kind"] == "component":
            # No review file is written in an application repository: report only what was touched.
            report = {key: report[key] for key in ("merged", "preserved", "blocking_collisions", "manifests_found", "notes")}
        if safe_path(root, ".project/adoption.json").exists():
            conflicts.append(".project/adoption.json")
    else:
        writes = files
        entries = {name: adoption.metadata(data, adoption.ownership(name, data, PROJECT_OWNED), name)
                   for name, data in files.items()}
        conflicts = [name for name in files if safe_path(root, name).exists()]
    if conflicts:
        emit({"status": "conflict", "files": conflicts, "writes": 0,
              "message": "No files written: listed paths already contain content "
                         "different from the standard's reserved content."})
        return 2
    if report and answers["kind"] != "component":
        writes[".project/adoption.json"] = json_bytes(report)
        entries[".project/adoption.json"] = adoption.metadata(writes[".project/adoption.json"], "project", ".project/adoption.json")
    state = {"schema_version": 1, "template_version": VERSION, "answers": answers, "files": entries}
    # Check every path before the first write, including manifest path.
    safe_path(root, STATE)
    warnings = []
    outer = enclosing_repository(root) if repository is None else None
    if outer:
        warnings.append(f"Destination is inside repository {outer}. The standard expects the root of the "
                        "repository: CI and hooks are not discovered in a subdirectory. "
                        "No nested repository is created.")
    git_init = bool(args.git and repository is None and not outer)
    if args.apply:
        apply_files(root, writes, state, "init", git_init)
    options = {key: answers[key] for key in CHOICES}
    options["default_branch"] = answers.get("default_branch", "main")
    emit({"status": "created" if args.apply else "plan", "path": str(root),
          "version": VERSION, "options": options, "files": sorted([*writes, STATE]), "git_init": git_init,
          "warnings": warnings, "adoption": report, "remote_operations": [],
          "suggested_names": None if answers["kind"] == "component" else suggested_names(answers),
          "next": {"component": "In AGENTS.md, outside the managed section, write the verification command for this "
                                "repository and its conventions; register the same command in the workspace with "
                                "project.py repo. AGENTS.md, CLAUDE.md and .project/ files are added: "
                                "exclude them from release archives.",
                   "workspace": "Register repositories with project.py repo, clone them with repos --apply, then configure "
                                "OpenSpec, integrations, the hub page and checks."}.get(
              answers["kind"], "Complete .project/config.json and the review listed in .project/adoption.json."
              if report else "Complete .project/config.json, then OpenSpec, integrations and checks.")})
    return 0


def update(args, root):
    state = load_state(root)
    original_version = state["template_version"]
    if version_tuple(original_version) > version_tuple(VERSION):
        raise Problem(f"The project uses standard {original_version}, newer than this skill ({VERSION}). "
                      "Update the skill: no file will be downgraded.")
    if args.workspace_url:
        if state["answers"]["kind"] != "component":
            raise Problem("--workspace-url is only valid for a component repository.")
        state["answers"]["workspace_url"] = args.workspace_url.rstrip("/")
        validate_answers(state["answers"])
    incoming = render(state["answers"])
    keep = set(args.keep)
    unknown = sorted(keep - incoming.keys())
    if unknown:
        raise Problem(f"--keep names files not managed by the standard: {unknown}")
    # A conflict needs three different versions: the recorded upstream base, the project and the skill.
    # --keep leaves the project version in place and records the skill version as the new base.
    changes, conflicts, adopted, kept = {}, {}, {}, []
    # Git on Windows often checks text files out with CRLF. Managed content is compared with LF
    # endings, and a file that had CRLF gets them back when it is rewritten.
    windows = set()
    for name, data in incoming.items():
        prior = state["files"].get(name)
        if prior and prior.get("ownership") == "block":
            path = safe_path(root, name)
            original = path.read_bytes() if path.is_file() else b""
            current = original.replace(b"\r\n", b"\n")
            try:
                current_body = adoption.block_content(current, name)
            except ValueError as error:
                conflicts[name] = str(error)
                continue
            new_body = adoption.managed_body(name, data).rstrip(b"\n") + b"\n"
            base, new_hash = prior["block_sha256"], digest(new_body)
            if current_body == new_body:
                adopted[name] = adoption.metadata(current, "block", name)
            elif new_hash == base:
                pass  # Upstream unchanged: a local edit inside the section is not a conflict.
            elif digest(current_body) == base:
                # Preserve every byte outside the managed section, even with mixed line endings.
                changes[name] = adoption.replace_block(original, new_body, name)
                adopted[name] = adoption.metadata(changes[name], "block", name)
            elif name in keep:
                adopted[name] = {**adoption.metadata(current, "block", name), "block_sha256": new_hash}
                kept.append(name)
            else:
                conflicts[name] = unified(current_body, new_body, name)
            continue
        if prior and (name in PROJECT_OWNED or prior.get("ownership") == "project"):
            continue
        path = safe_path(root, name)
        current = path.read_bytes() if path.is_file() else None
        if name in PROJECT_OWNED and prior is None:
            if current is not None and name in {".claude/settings.json", ".codex/hooks.json"}:
                merged = adoption.merge_hooks(current, data)
                if merged != current:
                    changes[name] = merged
                adopted[name] = adoption.metadata(merged, "project", name)
            elif current is None:
                changes[name] = data
                adopted[name] = adoption.metadata(data, "project", name)
            else:
                adopted[name] = adoption.metadata(current, "project", name)
            continue
        old_hash = prior["sha256"] if prior else None
        new_hash = digest(data)
        if current is not None and b"\r\n" in current:
            windows.add(name)
            current = current.replace(b"\r\n", b"\n")
        if current is not None and digest(current) == new_hash:
            adopted[name] = {"sha256": new_hash, "ownership": "template"}
        elif (current is None and prior is None) or (current is not None and digest(current) == old_hash):
            changes[name] = data
            adopted[name] = {"sha256": new_hash, "ownership": "template"}
        elif new_hash != old_hash:
            if name in keep:
                adopted[name] = {"sha256": new_hash, "ownership": "template"}
                kept.append(name)
            else:
                conflicts[name] = unified(current or b"", data, name)
        # An unchanged upstream template never resurrects a user-deleted file.
    if conflicts:
        emit({"status": "conflict", "files": sorted(conflicts), "diffs": conflicts, "writes": 0,
              "warnings": update_warnings(root, bool(changes or conflicts)),
              "message": "No files written: these files changed in both the project and the skill.",
              "next": "On a branch, manually integrate the needed changes from each diff (- project, + skill), "
                      "then retry with --keep PATH for each file whose project version is retained."})
        return 2
    unused = sorted(keep - set(kept))
    if unused:
        raise Problem(f"--keep applies only to conflicting files; these are not: {unused}")
    changes = {name: data.replace(b"\n", b"\r\n") if name in windows else data for name, data in changes.items()}
    if args.apply:
        state["files"].update(adopted)
        state["template_version"] = VERSION
        apply_files(root, changes, state, "update")
    emit({"status": "updated" if args.apply else "plan", "path": str(root),
          "from_version": original_version,
          "to_version": VERSION, "files": sorted(changes), "kept_project_versions": sorted(kept),
          "warnings": update_warnings(root, bool(changes)),
          "preserved_project_files": sorted(name for name in PROJECT_OWNED if name in incoming),
          "remote_operations": []})
    return 0


def update_warnings(root, changing_templates):
    if not changing_templates:
        return git_cautions(root)
    return git_cautions(root) + [
        "Managed instructions and templates are supplied in English; an update may replace their previous language. "
        "Project-owned documents and content_language are preserved. Review references/procedure.md#language-during-updates before applying."
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    create = sub.add_parser("init", help="Plan or create a project.")
    create.add_argument("destination", type=Path)
    create.add_argument("--name", required=True)
    create.add_argument("--slug")
    create.add_argument("--provider", choices=["github", "bitbucket"], default="github")
    create.add_argument("--tracker", choices=["jira", "github"], default="jira")
    create.add_argument("--profile", choices=["generic", "web"], default="generic")
    create.add_argument("--kind", choices=["single", "workspace", "component"], default="single",
                        help="single: one repository; workspace: a project with multiple repositories; "
                             "component: an application repository belonging to a workspace.")
    create.add_argument("--workspace-url", help="Workspace URL for --kind component; it can be added later with update.")
    create.add_argument("--adopt", action="store_true")
    create.add_argument("--git", action="store_true", help="Initialize Git without commits or remotes.")
    revise = sub.add_parser("update", help="Update managed files, preserving project changes.")
    revise.add_argument("destination", type=Path)
    revise.add_argument("--workspace-url", help="Link a component repository to the now-known workspace.")
    revise.add_argument("--keep", action="append", default=[], metavar="PATH",
                        help="Resolve a conflict by keeping the project version; repeatable.")
    resume = sub.add_parser("recover", help="Resume an interrupted init/update from its saved local plan.")
    resume.add_argument("destination", type=Path)
    for command in [create, revise, resume]:
        command.add_argument("--apply", action="store_true", help="Write the planned files.")
    args = parser.parse_args()
    if args.destination.is_symlink():
        raise Problem("Destination cannot be a symbolic link.")
    root = args.destination.expanduser().resolve()
    if root == PACKAGE or PACKAGE in root.parents:
        raise Problem("Generate the project outside the skill directory.")
    if root.exists() and not root.is_dir():
        raise Problem("Destination must be a directory.")
    if args.action != "recover" and safe_path(root, PENDING).exists():
        raise Problem("Incomplete operation: run framework.py recover DIRECTORY, then add --apply.")
    return globals()[args.action](args, root)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (Problem, OSError, ValueError, KeyError, TypeError) as error:
        emit({"status": "error", "message": str(error)})
        sys.exit(2)
