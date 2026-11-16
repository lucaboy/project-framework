#!/usr/bin/env python3
"""Project state, repositories, documents, checks and checkpoints (Python >=3.10)."""
from __future__ import annotations

import argparse
import errno
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit

try:
    import fcntl
except ImportError:  # Windows: the same lock is taken on the first byte of the file.
    fcntl = None
    import msvcrt

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ".project/config.json"
REPORT = ".project/local/verification.json"
SKIP = {".git", "node_modules", ".venv", "venv", "__pycache__", ".pytest_cache", "dist", "build", "coverage"}
LOCAL = (".project/local/", "docs/tasks/")
NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,59}")
DOCUMENT_TYPES = ("api", "flow", "infrastructure", "other")
AUTOMATION = ("guided", "automatic", "manual")
WORDS = 200


def emit(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def path_for(relative):
    path = Path(relative)
    # Test the text as given: on Windows str(path) always contains backslashes.
    if path.is_absolute() or ".." in path.parts or "\\" in str(relative):
        raise ValueError("Path not allowed (use / as separator): " + str(relative))
    current = ROOT
    for part in path.parts:
        current /= part
        if current.is_symlink():
            raise ValueError("Symbolic link not allowed: " + str(current))
    return current


def read_json(relative):
    return json.loads(path_for(relative).read_text(encoding="utf-8"))


def save_json(relative, data):
    path = path_for(relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    # mkstemp creates 0600 files: keep an existing mode, otherwise honor the umask.
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except FileNotFoundError:
        umask = os.umask(0)
        os.umask(umask)
        mode = 0o666 & ~umask
    fd, temporary = tempfile.mkstemp(prefix=".project-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def local_lock(name, wait=False):
    """Process lock held through the operating system, which releases it even after a killed process."""
    path = path_for(f".project/local/locks/{name}.lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as stream:
        deadline = time.monotonic() + 30
        while True:
            try:
                if fcntl:
                    fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                else:
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError as error:
                if error.errno not in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                    raise  # Unsupported locking or I/O errors must not become an endless retry.
                if not wait or time.monotonic() >= deadline:
                    raise ValueError("Another operation holds the local lock; wait and retry.") from None
                time.sleep(0.1)
        try:
            yield
        finally:
            if fcntl:
                fcntl.flock(stream, fcntl.LOCK_UN)
            else:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


def validate_https(value):
    # Same rule as preflight.clean_url: a link saved here must never break the session checks.
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.port not in (None, 443)):
        raise ValueError("Use an HTTPS URL without credentials, queries, fragments or custom ports.")
    return value.rstrip("/")


def one_line(text, limit):
    if not text.strip() or len(text) > limit or any(ord(c) < 32 for c in text):
        raise ValueError(f"Use one line of text, at most {limit} characters.")
    return text.strip()


def check_commands(commands):
    if not isinstance(commands, list):
        raise ValueError("commands must be a list of argument arrays.")
    for command in commands:
        if not isinstance(command, list) or not command or any(not isinstance(x, str) or not x for x in command):
            raise ValueError("Each command must be an array of nonempty strings; no implicit shell.")


def config():
    value = read_json(CONFIG)
    if value.get("schema_version") != 2:
        raise ValueError("Unsupported configuration schema.")
    if value.get("provider") not in {"github", "bitbucket"} or value.get("tracker") not in {"jira", "github"}:
        raise ValueError("Invalid provider/tracker.")
    if value["provider"] == "bitbucket" and value["tracker"] == "github":
        raise ValueError("The Bitbucket/GitHub tracker combination is not supported by this standard.")
    if value.get("kind") not in {"single", "workspace"}:
        raise ValueError("kind must be single or workspace.")
    language = value.setdefault("content_language", "")
    if not isinstance(language, str) or (language and one_line(language, 80) != language):
        raise ValueError("content_language must be empty or a confirmed language on one line (max 80 characters).")
    check_commands(value.get("commands"))
    timeout = value.setdefault("command_timeout_seconds", 600)
    if not isinstance(timeout, int) or not 1 <= timeout <= 7200:
        raise ValueError("Command timeout: integer from 1 to 7200 seconds.")
    names = set()
    for entry in value.setdefault("repositories", []):
        if not isinstance(entry, dict) or not NAME.fullmatch(str(entry.get("name", ""))) or entry["name"] in names:
            raise ValueError("Repository name missing, invalid or duplicated.")
        names.add(entry["name"])
        if entry.get("url"):
            validate_https(entry["url"])
        check_commands(entry.setdefault("commands", []))
    if names and value["kind"] != "workspace":
        raise ValueError("repositories is only supported in a workspace.")
    identifiers = set()
    for entry in value.setdefault("documents", []):
        if (not isinstance(entry, dict) or not NAME.fullmatch(str(entry.get("id", ""))) or entry["id"] in identifiers
                or entry.get("type") not in DOCUMENT_TYPES or not isinstance(entry.get("source") or "", str)):
            raise ValueError("Document has an invalid id, type or source.")
        identifiers.add(entry["id"])
    automation = value.setdefault("automation", {})
    for key in ("tracker", "documentation"):
        if automation.setdefault(key, "guided") not in AUTOMATION:
            raise ValueError("automation: use guided, automatic or manual.")
    for key in ("hub_url", "map_url"):
        value.setdefault("integrations", {}).setdefault(key, "")
    return value


def git(*arguments, root=None):
    if not shutil.which("git"):
        return None
    result = subprocess.run(["git", "-C", str(root or ROOT), *arguments], capture_output=True)
    return result.stdout if result.returncode == 0 else None


def excluded(value):
    """Paths that never count as sources of the project root."""
    return LOCAL + ("repos/",) if value["kind"] == "workspace" else LOCAL


def source_names(root):
    """Tracked files always count. SKIP only hides local outputs that Git does not track."""
    def split(raw):
        return {p.decode("utf-8", "surrogateescape") for p in raw.split(b"\0") if p}

    def local_output(name):
        return any(part in SKIP for part in Path(name).parts)

    tracked = git("ls-files", "-z", "--cached", root=root)
    if tracked is not None:
        others = git("ls-files", "-z", "--others", "--exclude-standard", root=root) or b""
        return split(tracked) | {name for name in split(others) if not local_output(name)}
    # Without Git, .gitignore cannot be honored: every file outside SKIP is treated as a source.
    found = set()
    for directory, children, files in os.walk(root):
        links = [c for c in children if (Path(directory) / c).is_symlink()]
        children[:] = [c for c in children if c not in SKIP]
        found.update((Path(directory) / name).relative_to(root).as_posix() for name in [*files, *links])
    return {name for name in found if not local_output(name)}


def fingerprint(root=None, skip=LOCAL, strict=False):
    """strict refuses an uninitialized submodule: checks must not run against half a checkout."""
    root = root or ROOT
    result = hashlib.sha256()
    # Git lists a submodule as one gitlink, not the files in its checkout.
    stages = git("ls-files", "--stage", "-z", root=root) or b""
    submodules = set()
    for record in stages.split(b"\0"):
        if not record:
            continue
        metadata, name = record.split(b"\t", 1)
        mode, _oid, _stage = metadata.split()
        if mode == b"160000":
            submodules.add(name.decode("utf-8", "surrogateescape"))
    for name in sorted(source_names(root)):
        parts = Path(name).parts
        if name.startswith(skip):
            continue
        if Path(name).is_absolute() or ".." in parts:
            raise ValueError("Invalid path in Git index.")
        path = root / name
        if path.is_symlink():
            content = b"symlink:" + os.fsencode(os.readlink(path))
        elif name in submodules:
            head = git("rev-parse", "HEAD", root=path) if (path / ".git").exists() else None
            if head:
                content = b"submodule:" + head.strip() + b":" + fingerprint(path, skip=(), strict=strict).encode()
            elif strict:
                raise ValueError(f"Uninitialized submodule: {path}. Restore it before verification.")
            else:
                # Recording work in progress must stay possible; no proof made with the submodule matches this.
                content = b"submodule:uninitialized"
        elif path.is_file():
            mode = b"executable:" if path.stat().st_mode & 0o111 else b"file:"
            content = mode + path.read_bytes()
        else:
            content = b"missing"
        result.update(os.fsencode(name) + b"\0" + hashlib.sha256(content).digest())
    return result.hexdigest()


def revision(root=None, skip=LOCAL, strict=False):
    root = root or ROOT
    head = git("rev-parse", "HEAD", root=root)
    branch = git("branch", "--show-current", root=root)
    status = git("status", "--porcelain", root=root)
    return {"git_head": head.decode().strip() if head else None,
            "git_branch": branch.decode().strip() if branch and branch.strip() else None,
            "working_tree_dirty": bool(status.strip()) if status is not None else None,
            "source_fingerprint": fingerprint(root, skip, strict)}


def registered(value):
    return {entry["name"]: entry for entry in value["repositories"]}


def repository_identity(path):
    top = git("rev-parse", "--show-toplevel", root=path)
    common = git("rev-parse", "--git-common-dir", root=path)
    if not top or not common or Path(os.fsdecode(top).strip()).resolve() != path.resolve():
        raise ValueError(f"Not a Git repository root: {path}.")
    directory = Path(os.fsdecode(common).strip())
    return (path / directory).resolve()


def checkouts(value, selectors):
    """Resolve NAME or NAME=PATH: repos/NAME by default, or a worktree of that repository."""
    known, result = registered(value), {}
    for selector in selectors:
        name, _, override = selector.partition("=")
        if name not in known:
            raise ValueError(f"Unregistered repository: {name}. Use project.py repo to register it.")
        if override:
            path = Path(override).expanduser()
            path = (path if path.is_absolute() else Path.cwd() / path).resolve()
        else:
            path = path_for("repos/" + name)
        if not (path / ".git").exists():
            raise ValueError(f"Repository {name} missing at {path}: run project.py repos --apply.")
        expected = path_for("repos/" + name)
        if repository_identity(path) != repository_identity(expected):
            raise ValueError(f"Path {path} is not a worktree of repository {name}.")
        result[name] = path
    return result


def repository_state(entry):
    path = ROOT / "repos" / entry["name"]
    state = {"name": entry["name"], "role": entry.get("role", ""), "url": entry.get("url", ""),
             "path": "repos/" + entry["name"], "cloned": (path / ".git").exists(),
             "commands_configured": bool(entry.get("commands"))}
    if state["cloned"]:
        branch, head, dirty = (git(*argv, root=path) for argv in (
            ("branch", "--show-current"), ("rev-parse", "--short", "HEAD"), ("status", "--porcelain")))
        state.update(branch=(branch or b"").decode().strip() or None, head=(head or b"").decode().strip() or None,
                     dirty=bool(dirty.strip()) if dirty is not None else None)
    return state


def document_states(value):
    states = []
    for entry in value["documents"]:
        if not entry.get("source"):
            # The page itself is the authoritative text (product, business, decisions): nothing to compare.
            state = "page_authoritative" if entry.get("page_url") else "never_published"
        else:
            source = path_for(entry["source"])
            current = hashlib.sha256(source.read_bytes()).hexdigest() if source.is_file() else None
            state = ("missing_source" if current is None else "never_published" if not entry.get("published_sha256")
                     else "current" if entry["published_sha256"] == current else "stale")
        states.append({"id": entry["id"], "type": entry["type"], "title": entry.get("title", ""),
                       "source": entry.get("source") or "", "page_url": entry.get("page_url", ""), "state": state})
    return states


def open_tasks():
    directory = path_for("docs/tasks")
    items = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(directory.glob("*.json"))] if directory.exists() else []
    return [{key: item.get(key) for key in ["id", "summary", "owner", "status", "next_action", "repositories"]}
            for item in items]


def doctor(_args):
    value = config()
    required = ["AGENTS.md", "CLAUDE.md", ".project/WORKFLOW.md", ".project/INTEGRATIONS.md", ".project/TEMPLATES.md",
                ".project/REVIEW.md", "scripts/preflight.py", "docs/INDEX.md", "openspec/config.yaml",
                ".project/dependencies.json", ".project/template-state.json"]
    missing = [item for item in required if not path_for(item).is_file()]
    pipeline = ".github/workflows/ci.yml" if value["provider"] == "github" else "bitbucket-pipelines.yml"
    if not path_for(pipeline).is_file():
        missing.append(pipeline)
    workspace = value["kind"] == "workspace"
    commands = any(entry["commands"] for entry in value["repositories"]) if workspace else bool(value["commands"])
    warnings = []
    if not value["content_language"]:
        warnings.append("Content language not confirmed: suggest the user's language, ask once, then use project.py language --set LANGUAGE --apply.")
    pending = path_for(".project/local/framework-pending.json").exists()
    if pending:
        warnings.append("Interrupted setup: use framework.py recover from the skill before continuing.")
    if not value.get("purpose", "").strip():
        warnings.append("Define the product purpose in .project/config.json.")
    if not commands:
        warnings.append("Application commands not configured: verify cannot pass.")
    if workspace:
        if not value["repositories"]:
            warnings.append("No repositories registered: add them with project.py repo.")
        unchecked = [entry["name"] for entry in value["repositories"] if not entry["commands"]]
        if unchecked and commands:
            warnings.append("Repositories without verification commands: " + ", ".join(unchecked)
                            + ". They cannot be delivered until checks are configured.")
        absent = [entry["name"] for entry in value["repositories"] if not (ROOT / "repos" / entry["name"] / ".git").exists()]
        if absent:
            warnings.append("Repositories missing on this computer: " + ", ".join(absent)
                            + ". Run project.py repos --apply.")
    links = value["integrations"]
    if not links["repository_url"]:
        warnings.append("Project repository not linked: without its URL the map cannot support "
                        "resuming on another computer. Use project.py link --repository-url.")
    if value["tracker"] == "jira" and not links["jira_url"]:
        warnings.append("Tracker not linked: tasks do not yet have an authoritative source. Use project.py link.")
    if links["confluence_url"] and not (links["hub_url"] and links["map_url"]):
        warnings.append("Confluence is linked but the hub or project map is missing: see project.py hub.")
    programs = {command[0] for entry in ([value] + value["repositories"]) for command in entry["commands"]}
    absent = sorted(name for name in programs if not shutil.which(name))
    if absent:
        warnings.append("Verification programs missing on this computer: " + ", ".join(absent) + ".")
    if not shutil.which("git"):
        warnings.append("Git unavailable: verify cannot exclude files ignored by .gitignore "
                        "and fails if checks create local output.")
    outdated = [item["id"] for item in document_states(value) if item["state"] not in {"current", "page_authoritative"}]
    if outdated:
        warnings.append("Documents to publish or update: " + ", ".join(outdated) + ". See project.py docs.")
    dependencies = read_json(".project/dependencies.json")
    if path_for(".project/adoption.json").is_file():
        adoption = read_json(".project/adoption.json")
        if adoption.get("status") != "reviewed":
            warnings.append("Adoption incomplete: read .project/adoption.json and check the actual project.")
        elif not adoption.get("evidence"):
            warnings.append("Adoption marked reviewed without evidence: in the evidence field of "
                            ".project/adoption.json list the checks performed and their results.")
    # OpenSpec may create supported client links into the shared .agents directory.
    expected_skills = dependencies["openspec"].get("skills", ["openspec-propose"])
    missing_skills = {client: [skill for skill in expected_skills if not (ROOT / directory / skill / "SKILL.md").is_file()]
                      for client, directory in {"codex": ".agents/skills", "claude": ".claude/skills"}.items()}
    clients = {client: not missing for client, missing in missing_skills.items()}
    if not all(clients.values()):
        warnings.append("OpenSpec workflows not installed: run this script's openspec command when needed.")
    # The CLI lives in .project/local, which Git ignores: a clone on another computer has the workflows only.
    local_cli = (ROOT / ".project/local/openspec/node_modules/@fission-ai/openspec/bin/openspec.js").is_file()
    if all(clients.values()) and not local_cli:
        warnings.append("Local OpenSpec CLI missing on this computer: run python3 scripts/project.py openspec --apply.")
    hooks = {}
    for client, relative in {"codex": ".codex/hooks.json", "claude": ".claude/settings.json"}.items():
        path = path_for(relative)
        groups = json.loads(path.read_text(encoding="utf-8")).get("hooks", {}).get("SessionStart", []) if path.is_file() else []
        hooks[client] = any("scripts/preflight.py" in h.get("command", "") and "hook --client " + client in h.get("command", "")
                            for group in groups for h in group.get("hooks", []))
    if not all(hooks.values()):
        warnings.append("Startup hooks incomplete: AGENTS.md requires the agent to run preflight.")
    emit({"framework_ready": not missing and not pending, "kind": value["kind"], "application_commands_configured": commands,
          "missing": missing, "warnings": warnings, "openspec_version": dependencies["openspec"]["version"],
          "openspec_clients_ready": clients, "openspec_missing_skills": missing_skills,
          "openspec_local_cli": local_cli, "startup_hooks_configured": hooks,
          "startup_hooks_activation": "Check in the client: loading, support and trust cannot be inferred from files."})
    return 1 if missing or pending else 0


def executable(argv):
    """Resolve the program as a shell would: on Windows npm, npx and similar tools are .cmd files."""
    return [shutil.which(argv[0]) or argv[0], *argv[1:]]


def stop_tree(process):
    """End a check together with everything it started."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


def run_command(command, root, timeout):
    # Its own process group: an interrupted or timed-out check leaves nothing running behind the lock.
    group = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    process = subprocess.Popen(executable(command), cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, errors="replace", **group)
    try:
        output, errors = process.communicate(timeout=timeout)
    except BaseException:
        stop_tree(process)
        process.communicate()
        raise
    return process.returncode, output + errors


def run_checks(commands, root, skip, timeout):
    """Run the configured commands in one tree and describe the state they were run against."""
    before = revision(root, skip, strict=True)
    entry = {"status": "passed", "at": stamp(), "revision": before, "checks": []}
    for command in commands:
        try:
            returncode, output = run_command(command, root, timeout)
            # Keep full logs out of checkpoints and version control.
            sys.stderr.write(output[-12000:])
            entry["checks"].append({"argv": command, "returncode": returncode})
            if returncode:
                entry["status"] = "failed"
        except (subprocess.TimeoutExpired, OSError) as error:
            entry["checks"].append({"argv": command, "error": type(error).__name__})
            entry["status"] = "failed"
    entry["revision"] = revision(root, skip, strict=True)
    if entry["revision"]["source_fingerprint"] != before["source_fingerprint"]:
        entry["source_changed_during_checks"] = True
        entry["status"] = "failed"
    if not commands:
        entry["status"] = "not_configured"
    return entry


def verification_scope(value, name=None):
    """Bind evidence to the configured checks, not only to application file contents."""
    target = registered(value)[name] if name else value
    scope = {"schema": 2, "commands": target["commands"], "timeout": value["command_timeout_seconds"],
             "repository": target.get("url", "") if name else value["integrations"].get("repository_url", ""),
             "runner": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    return hashlib.sha256(json.dumps(scope, sort_keys=True).encode()).hexdigest()


def proof_current(entry, value, root, name=None, source=None):
    target = registered(value)[name] if name else value
    return bool(target["commands"] and entry.get("scope") == verification_scope(value, name)
                and entry.get("revision", {}).get("source_fingerprint") == (source or fingerprint(root)))


def store_proof(name, entry):
    # A short lock protects read/merge/write; checks in different repositories stay parallel.
    with local_lock("verification-report", wait=True):
        if name is None:
            save_json(REPORT, entry)
        else:
            report = read_json(REPORT) if path_for(REPORT).is_file() else {}
            entries = report.setdefault("repositories", {})
            entries[name] = entry
            report.update(status=entry["status"], at=stamp(), verified_now=[name], not_verified={})
            save_json(REPORT, report)


def verify_one(value, path, name=None):
    with local_lock("verify-repo-" + name if name else "verify-project"):
        scope = verification_scope(value, name)
        # Persist BEFORE any command or fingerprint operation: a crash cannot revive an old pass.
        pending = {"status": "incomplete", "at": stamp(), "scope": scope, "path": str(path)}
        store_proof(name, pending)
        commands = registered(value)[name]["commands"] if name else value["commands"]
        entry = run_checks(commands, path, LOCAL, value["command_timeout_seconds"])
        entry.update(scope=scope, path=str(path))
        # A configuration edited while checks ran cannot be certified by that run.
        if scope != verification_scope(config(), name):
            entry.update(status="failed", configuration_changed_during_checks=True)
        store_proof(name, entry)
        return entry


def verify(args):
    value = config()
    path_for(REPORT)  # Refuse unsafe output paths before executing commands.
    # A termination request unwinds normally, so running checks are stopped before the lock is released.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    if value["kind"] == "single":
        if args.repo:
            raise ValueError("--repo is only valid in a workspace.")
        report = verify_one(value, ROOT)
    else:
        known = registered(value)
        selectors = args.repo or [name for name, entry in known.items()
                                  if entry["commands"] and (ROOT / "repos" / name / ".git").exists()]
        # A run that covers only part of the project says so: a silent pass would read as "all verified".
        left_out = {} if args.repo else {
            name: "commands not configured" if not entry["commands"] else "not cloned"
            for name, entry in known.items() if name not in selectors}
        report = {"status": "not_configured", "at": stamp(), "verified_now": []}
        outcomes = []
        for name, path in checkouts(value, selectors).items():
            entry = verify_one(value, path, name)
            report["verified_now"].append(name)
            outcomes.append(entry["status"])
        if outcomes:
            report["status"] = next(s for s in ("failed", "not_configured", "passed") if s in outcomes)
        report["not_verified"] = left_out
        with local_lock("verification-report", wait=True):
            current = read_json(REPORT) if path_for(REPORT).is_file() else {}
            report["repositories"] = current.get("repositories", {})
            save_json(REPORT, report)
    emit(report)
    return {"passed": 0, "failed": 1}.get(report["status"], 2)


def link(args):
    value = config()
    fields = {"repository_url": args.repository_url, "jira_url": args.jira_url,
              "confluence_url": args.confluence_url, "hub_url": args.hub_url, "map_url": args.map_url}
    for key, url in fields.items():
        if url is not None:
            value["integrations"][key] = validate_https(url)
    if args.jira_project_key:
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{1,19}", args.jira_project_key):
            raise ValueError("Invalid Jira key.")
        value["integrations"]["jira_project_key"] = args.jira_project_key
    if args.confluence_space_key:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,255}", args.confluence_space_key):
            raise ValueError("Invalid Confluence space key.")
        value["integrations"]["confluence_space_key"] = args.confluence_space_key
    if args.apply:
        save_json(CONFIG, value)
    emit({"status": "linked_unverified" if args.apply else "plan", "integrations": value["integrations"],
          "remote_operations": [], "note": "Saving URLs does not verify access, webhooks, permissions or billing."})
    return 0


def integrations(_args):
    value = config()
    emit({"provider": value["provider"], "tracker": value["tracker"],
          "items": {key: {"value": url, "status": "linked_unverified" if url else "pending"}
                    for key, url in value["integrations"].items()},
          "remote_operations": [], "guide": ".project/INTEGRATIONS.md"})
    return 0


def repo(args):
    value = config()
    if value["kind"] != "workspace":
        raise ValueError("Component repositories can only be registered in a workspace.")
    if not NAME.fullmatch(args.name):
        raise ValueError("Repository name: lowercase letters, digits and hyphens.")
    known = registered(value)
    entry = known.get(args.name) or {"name": args.name, "role": "", "url": "", "default_branch": "main", "commands": []}
    if args.url is not None:
        entry["url"] = validate_https(args.url)
    if args.role is not None:
        entry["role"] = one_line(args.role, 120)
    if args.default_branch:
        entry["default_branch"] = one_line(args.default_branch, 100)
    if args.commands is not None:
        commands = json.loads(args.commands)
        check_commands(commands)
        entry["commands"] = commands
    if args.name not in known:
        value["repositories"].append(entry)
    if args.apply:
        save_json(CONFIG, value)
    emit({"status": "saved" if args.apply else "plan", "repository": entry, "remote_operations": [],
          "next": "python3 scripts/project.py repos --apply clones missing repositories into repos/."})
    return 0


def repos(args):
    value = config()
    if value["kind"] != "workspace":
        raise ValueError("This project has a single repository: this directory.")
    attempts = []
    if args.apply:
        for entry in value["repositories"]:
            path = path_for("repos/" + entry["name"])
            if not entry.get("url") or (path.exists() and any(path.iterdir())):
                continue  # Nothing to clone from, or a directory that must not be touched.
            url = entry["url"]
            if args.ssh:
                parsed = urlsplit(url)
                url = f"git@{parsed.hostname}:{parsed.path.strip('/')}.git"
            path.parent.mkdir(parents=True, exist_ok=True)
            result = subprocess.run(["git", "clone", url, str(path)], stdout=sys.stderr, stderr=sys.stderr,
                                    env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
            attempts.append({"name": entry["name"], "returncode": result.returncode})
    updates = []
    if args.update:
        quiet = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
        for entry in value["repositories"]:
            path = ROOT / "repos" / entry["name"]
            if not (path / ".git").exists():
                continue
            state = repository_state(entry)
            fetched = subprocess.run(["git", "-C", str(path), "fetch", "--quiet"], capture_output=True, env=quiet)
            # Only a clean checkout on the default branch is moved: work in progress is never touched.
            reason = ("fetch failed" if fetched.returncode else "uncommitted changes" if state["dirty"]
                      else f"on branch {state['branch']}" if state["branch"] != entry.get("default_branch", "main") else "")
            if not reason:
                pulled = subprocess.run(["git", "-C", str(path), "pull", "--ff-only", "--quiet"], capture_output=True, env=quiet)
                reason = "" if pulled.returncode == 0 else "local branch cannot be fast-forwarded"
            updates.append({"name": entry["name"], "action": "updated" if not reason else "left_as_is", "reason": reason})
    states = [repository_state(entry) for entry in value["repositories"]]
    missing = [state["name"] for state in states if not state["cloned"]]
    emit({"status": "synced" if args.apply or not missing else "plan", "repositories": states,
          "clone_attempts": attempts, "updates": updates, "missing": missing,
          "network": "repos --apply clones missing repositories using the user's Git credentials; "
                     "existing repositories are not modified unless --update is requested."})
    return 1 if any(attempt["returncode"] for attempt in attempts) else 0


def doc(args):
    value = config()
    if not NAME.fullmatch(args.id):
        raise ValueError("Document id: lowercase letters, digits and hyphens.")
    known = {entry["id"]: entry for entry in value["documents"]}
    entry = known.get(args.id) or {"id": args.id, "type": None, "title": "", "source": None,
                                   "page_url": "", "published_sha256": ""}
    previous_target = (entry.get("source"), entry.get("page_url"))
    if args.type:
        entry["type"] = args.type
    if args.title is not None:
        entry["title"] = one_line(args.title, 120)
    if args.source is not None:
        path_for(args.source)
        entry["source"] = args.source
    if args.page_url is not None:
        entry["page_url"] = validate_https(args.page_url)
    if previous_target != (entry.get("source"), entry.get("page_url")):
        entry["published_sha256"] = ""
    if not entry["type"] or not (entry["source"] or entry["page_url"]):
        raise ValueError("A new document requires --type and --source, or --page-url when the page is authoritative.")
    if args.published:
        if not entry["source"]:
            raise ValueError("--published records a repository source hash: this document has no repository source.")
        source = path_for(entry["source"])
        if not source.is_file() or not entry["page_url"]:
            raise ValueError("Recording publication requires an existing source file and --page-url.")
        entry["published_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
    if args.id not in known:
        value["documents"].append(entry)
    if args.apply:
        save_json(CONFIG, value)
    absent = [] if not entry["source"] or path_for(entry["source"]).is_file() else [
        "The source does not exist in this checkout: the document remains missing_source until the file "
        "is available in the default branch."]
    emit({"status": "saved" if args.apply else "plan", "document": entry, "warnings": absent, "remote_operations": [],
          "note": "Create or update the page in the client: this command only records source, page and attested published version."})
    return 0


def docs(_args):
    states = document_states(config())
    emit({"documents": states, "to_update": [item["id"] for item in states if item["state"] not in {"current", "page_authoritative"}],
          "guide": ".project/WORKFLOW.md"})
    return 0


def tracker_reference(value):
    links = value["integrations"]
    if value["tracker"] == "github":
        repository = links["repository_url"].rstrip("/").removesuffix(".git")
        return {"type": "github", "url": repository + "/issues" if repository else "", "project_key": ""}
    return {"type": "jira", "url": links["jira_url"], "project_key": links["jira_project_key"]}


def proof_status(entry, value, path, name=None):
    commands = registered(value)[name]["commands"] if name else value["commands"]
    if not commands:
        return "not_configured"
    if not entry:
        return "none"
    if entry.get("status") == "incomplete":
        return "incomplete"
    try:
        if name:
            checkouts(value, [name + "=" + str(path)])
        return entry.get("status", "none") if proof_current(entry, value, path, name) else "outdated"
    except (ValueError, OSError):
        return "outdated"


def overview(value):
    """One compact picture of the project for people and for a chat that starts."""
    report = read_json(REPORT) if path_for(REPORT).is_file() else {}
    links = value["integrations"]
    data = {"project": value["name"], "kind": value["kind"], "purpose": value.get("purpose", ""),
            "tracker": tracker_reference(value), "content_language": value["content_language"],
            "hub_url": links["hub_url"], "automation": value["automation"]}
    if value["kind"] == "workspace":
        proofs = report.get("repositories") if isinstance(report.get("repositories"), dict) else {}
        data["repositories"] = []
        for entry in value["repositories"]:
            state = repository_state(entry)
            proof = proofs.get(entry["name"])
            default = ROOT / "repos" / entry["name"]
            state["verification"] = "none" if entry["commands"] else "not_configured"
            if proof:
                # A proof belongs to the checkout it was run in, which may be a worktree of the repository.
                where = Path(proof.get("path") or default)
                state["verification"] = proof_status(proof, value, where, entry["name"])
                if where != default:
                    state["verified_in"] = str(where)
            data["repositories"].append(state)
    else:
        data["verification"] = proof_status(report, value, ROOT)
    data["open_tasks"] = [task for task in open_tasks() if task["status"] != "done"]
    data["documents_to_update"] = [item["id"] for item in document_states(value) if item["state"] not in {"current", "page_authoritative"}]
    return data


def status(args):
    data = overview(config())
    if not args.text:
        emit(data)
        return 0
    labels = {"passed": "passed", "failed": "failed", "outdated": "rerun needed, sources or checks changed",
              "incomplete": "running or interrupted; wait for completion or rerun verify",
              "none": "never run", "not_configured": "not configured"}
    lines = [f"{data['project']} ({data['kind']})" + (f": {data['purpose']}" if data["purpose"] else "")]
    tracker = data["tracker"]
    lines.append("Tasks: " + (tracker["url"] + (f" [{tracker['project_key']}]" if tracker["project_key"] else "")
                                if tracker["url"] else "tracker not linked"))
    lines.append("Hub: " + (data["hub_url"] or "not linked"))
    lines.append("Content language: " + (data["content_language"] or "confirmation required"))
    for item in data.get("repositories", []):
        where = "not cloned on this computer"
        if item["cloned"]:
            where = f"branch {item.get('branch') or '-'}, commit {item.get('head') or '-'}" \
                + (", uncommitted changes" if item.get("dirty") else "")
        check = labels.get(item["verification"], item["verification"])
        if item.get("verified_in"):
            check += " in worktree " + item["verified_in"]
        lines.append(f"- {item['name']} ({item['role'] or 'role not specified'}): {where}; verification {check}")
    if "verification" in data:
        lines.append("Verification: " + labels.get(data["verification"], data["verification"]))
    for task in data["open_tasks"]:
        lines.append(f"- {task['id']} [{task['status']}] {task['owner']}: {task['summary']}"
                     + (f" -> {task['next_action']}" if task["next_action"] else ""))
    if not data["open_tasks"]:
        lines.append("No open checkpoints.")
    if data["documents_to_update"]:
        lines.append("Documents to update: " + ", ".join(data["documents_to_update"]))
    print("\n".join(lines))
    return 0


def hub(args):
    """Render the generated map page, a child of the hub page; publishing happens in the client."""
    value = config()
    links = value["integrations"]
    tracker = tracker_reference(value)
    manifest = {"project_framework": 2, "name": value["name"], "slug": value["slug"], "kind": value["kind"],
                "content_language": value["content_language"],
                "repository": links["repository_url"],
                "tracker": tracker,
                "confluence": {"url": links["confluence_url"], "space_key": links["confluence_space_key"]},
                "repositories": [{key: entry.get(key, "") for key in ("name", "role", "url", "default_branch")}
                                 for entry in value["repositories"]]}
    start = "workspace" if value["kind"] == "workspace" else "repository"
    lines = ["_Generated by `python3 scripts/project.py hub`: replace as a whole; do not edit manually._",
             "_English draft: translate prose to the confirmed content language before publishing; preserve the JSON manifest._", ""]
    lines += [f"- **Tasks**: {tracker['url'] or 'not linked'}"
              + (f" (project {tracker['project_key']})" if tracker["project_key"] else ""),
              f"- **Starting point for agents**: {links['repository_url'] or 'not linked'} "
              f"({start}: clone it and open the chat at its root)",
              "- **Working together**: `docs/GUIDE.md` in the same repository", ""]
    if value["repositories"]:
        lines += ["| Repository | Role | URL |", "| --- | --- | --- |"]
        lines += [f"| {entry['name']} | {entry.get('role', '')} | {entry.get('url', '')} |" for entry in value["repositories"]]
        lines.append("")
    documents = [item for item in document_states(value) if item["page_url"]]
    if documents:
        lines += ["| Document | Type | Page |", "| --- | --- | --- |"]
        lines += [f"| {item['title'] or item['id']} | {item['type']} | {item['page_url']} |" for item in documents]
        lines.append("")
    lines += ["```json", json.dumps(manifest, ensure_ascii=False, indent=2), "```"]
    markdown = "\n".join(lines) + "\n"
    if not value["content_language"]:
        markdown = "**Draft: confirm the language of tasks and Confluence documentation before publishing.**\n\n" + markdown
    if args.text:
        print(markdown, end="")
        return 0
    warnings = [] if links["repository_url"] else [
        "Project repository not linked: this map cannot tell a new agent where to resume. "
        "Link its URL with link --repository-url and regenerate the page."]
    if not value["content_language"]:
        warnings.append("Content language requires user confirmation before publication.")
    emit({"title": value["name"] + " — Project map", "markdown": markdown, "manifest": manifest,
          "content_language": value["content_language"], "language_confirmed": bool(value["content_language"]),
          "draft_language": "English",
          "warnings": warnings, "remote_operations": [],
          "note": "Publish this content as a child of the hub page and replace the generated child on each "
                  "update. Do not rewrite the human-authored hub page."})
    return 0


def language(args):
    """Record the user's explicitly confirmed content language; never infer consent from locale."""
    value = config()
    if args.set is not None:
        value["content_language"] = one_line(args.set, 80)
    elif args.apply:
        raise ValueError("--apply requires --set with the user's confirmed language.")
    if args.apply:
        save_json(CONFIG, value)
    emit({"status": "saved" if args.apply else "plan" if args.set is not None else "configured" if value["content_language"] else "confirmation_required",
          "content_language": value["content_language"], "remote_operations": [],
          "note": "Set only after the user explicitly chooses. Applies to future task and documentation content; existing content is not translated."})
    return 0


def checkpoint(args):
    value = config()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", args.task):
        raise ValueError("Invalid task ID: use APP-123 or GH-12, for example.")
    workspace = value["kind"] == "workspace"
    if args.repo and not workspace:
        raise ValueError("--repo is only valid in a workspace.")
    chosen = checkouts(value, args.repo)
    relative = f"docs/tasks/{args.task}.json"
    previous = read_json(relative) if path_for(relative).exists() else None
    if previous and previous["owner"] != args.owner and previous["status"] in {"in_progress", "blocked", "review"}:
        if args.transfer_from != previous["owner"]:
            raise ValueError("Different owner: use --transfer-from after coordinating the handoff in the tracker.")
    text = " ".join([args.summary, args.next, *args.completed, *args.blocker, *args.evidence])
    if len(text.split()) > WORDS:
        raise ValueError(f"Checkpoint exceeds {WORDS} words: keep current state only and link details.")
    current = revision(ROOT, excluded(value))
    states = {name: revision(path) for name, path in chosen.items()}
    proof = None
    if args.status in {"review", "done"}:
        if args.domain != "software":
            if not args.evidence:
                raise ValueError("For non-software delivery, supply at least one evidence or artifact reference with --evidence.")
        else:
            # The fingerprint is the proof: a later commit or checkpoint with identical sources keeps it valid.
            report = read_json(REPORT) if path_for(REPORT).is_file() else {}
            if workspace:
                if not chosen:
                    raise ValueError("In a workspace, select delivered repositories with --repo.")
                entries = report.get("repositories") if isinstance(report.get("repositories"), dict) else {}
                proof = {name: entries.get(name) for name in chosen}
                targets = {name: states[name]["source_fingerprint"] for name in chosen}
            else:
                proof, targets = {"project": report}, {"project": current["source_fingerprint"]}
            for name, wanted in targets.items():
                entry = proof[name] or {}
                if entry.get("status") != "passed" or not proof_current(
                        entry, value, chosen[name] if workspace else ROOT, name if workspace else None, source=wanted):
                    selector = next((s for s in reversed(args.repo) if s.partition("=")[0] == name), name)
                    where = f" for {name}: run verify --repo {shlex.quote(selector)}" if workspace else ": run verify"
                    raise ValueError("Missing passing verification for current sources" + where + " and retry.")
            if not workspace:
                proof = proof["project"]
    data = {"id": args.task, "summary": args.summary, "domain": args.domain,
            "owner": args.owner, "status": args.status, "updated_at": stamp(),
            "completed": args.completed, "blockers": args.blocker, "next_action": args.next,
            "evidence": args.evidence, "repositories": sorted(chosen), "revision": current,
            "repository_revisions": states, "verification": proof if args.domain == "software" else None}
    if args.apply:
        save_json(relative, data)
    uncommitted = [name for name, state in {"project": current, **states}.items() if not state.get("git_head")]
    emit({"status": "saved" if args.apply else "plan", "path": relative, "checkpoint": data,
          "warnings": ["No committed revision for " + ", ".join(uncommitted)
                       + ". Before cross-computer handoff, commit the code, refresh this checkpoint, then commit and push the checkpoint too."] if uncommitted else [],
          "coordination": "This file is not a distributed lock. Coordinate ownership and release in the tracker."})
    return 0


def tasks(_args):
    emit(open_tasks())
    return 0


def openspec(args):
    spec = read_json(".project/dependencies.json")["openspec"]
    package = path_for(".project/tooling/package.json")
    lock = path_for(".project/tooling/package-lock.json")
    if json.loads(package.read_text(encoding="utf-8"))["dependencies"][spec["package"]] != spec["version"]:
        raise ValueError("OpenSpec version differs between manifest and package.json.")
    locked = json.loads(lock.read_text(encoding="utf-8"))
    if locked["packages"]["node_modules/" + spec["package"]]["version"] != spec["version"]:
        raise ValueError("OpenSpec version differs in the lockfile.")
    tool_root = path_for(".project/local/openspec")
    cli = tool_root / "node_modules" / "@fission-ai" / "openspec" / "bin" / "openspec.js"
    install = ["npm", "ci", "--prefix", str(tool_root), "--ignore-scripts", "--no-audit", "--no-fund"]
    # The template already supplies config.yaml, including the language context.
    # OpenSpec 2 rejects --language when that config exists.
    command = ["node", str(cli), "init", ".", "--tools", ",".join(spec["tools"]),
               "--profile", spec["profile"], "--no-animation"]
    environment = {"XDG_CONFIG_HOME": str(path_for(".project/local/xdg")),
                   "npm_config_cache": str(path_for(".project/local/npm-cache")),
                   "OPENSPEC_TELEMETRY": "0"}
    if not args.apply:
        emit({"status": "plan", "install_argv": install, "init_argv": command, "environment": environment,
              "network": "npm downloads versions with integrity hashes pinned in the lockfile.",
              "scope": "OpenSpec files in the project; no global installation."})
        return 0
    for binary in ["node", "npm"]:
        if not shutil.which(binary):
            raise ValueError(f"Missing {binary}. OpenSpec requires Node >=22.12.0 and npm.")
    install, command = executable(install), executable(command)
    node_version = re.match(r"v?(\d+)\.(\d+)\.(\d+)", subprocess.check_output(executable(["node", "--version"]), text=True).strip())
    if not node_version or tuple(map(int, node_version.groups())) < (22, 12, 0):
        raise ValueError("OpenSpec requires Node >=22.12.0.")
    env = {**os.environ, **environment}
    tool_root.mkdir(parents=True, exist_ok=True)
    # The npm prefix is ignored project-local state; no personal npm configuration is edited.
    for source in [package, lock]:
        destination = path_for(".project/local/openspec/" + source.name)
        destination.write_bytes(source.read_bytes())
    result = subprocess.run(install, cwd=ROOT, env=env)
    if result.returncode:
        return result.returncode
    result = subprocess.run(command, cwd=ROOT, env=env)
    if result.returncode:
        return result.returncode
    expected = [f"{directory}/{skill}/SKILL.md" for directory in [".agents/skills", ".claude/skills"]
                for skill in spec.get("skills", ["openspec-propose"])]
    missing = [name for name in expected if not (ROOT / name).is_file()]
    emit({"status": "initialized" if not missing else "incomplete", "version": spec["version"], "missing": missing})
    return 1 if missing else 0


def spec(args):
    """Run the local CLI used by OpenSpec workflows, with the same local config."""
    executable = path_for(".project/local/openspec/node_modules/@fission-ai/openspec/bin/openspec.js")
    if not executable.is_file() or not shutil.which("node"):
        raise ValueError("Local OpenSpec CLI missing: run python3 scripts/project.py openspec --apply.")
    arguments = args.argv[1:] if args.argv[:1] == ["--"] else args.argv
    env = {**os.environ, "XDG_CONFIG_HOME": str(path_for(".project/local/xdg")),
           "OPENSPEC_TELEMETRY": "0"}
    return subprocess.run([shutil.which("node"), str(executable), *arguments], cwd=ROOT, env=env).returncode


def preflight(args):
    import preflight as checks
    return checks.entry(["check", *args.argv])


def main():
    if sys.argv[1:2] == ["preflight"]:
        import preflight as checks
        return checks.entry(["check", *sys.argv[2:]])
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    entry = sub.add_parser("language", help="Show or save the user's confirmed task/document language (any language).")
    entry.add_argument("--set", metavar="LANGUAGE")
    entry.add_argument("--apply", action="store_true")
    selector = "NAME or NAME=PATH for a worktree; repeatable."
    entry = sub.add_parser("status", help="Project overview: repositories, verification, open tasks and documents.")
    entry.add_argument("--text", action="store_true", help="Brief readable text instead of JSON.")
    sub.add_parser("doctor", help="Check the standard's structure; see warnings for remaining setup.")
    entry = sub.add_parser("verify", help="Run configured application commands and record local evidence.")
    entry.add_argument("--repo", action="append", default=[], metavar="NAME[=PATH]", help=selector)
    entry = sub.add_parser("repo", help="Register or update a workspace repository; --apply saves.")
    entry.add_argument("--name", required=True)
    for field in ["url", "role", "default-branch"]:
        entry.add_argument("--" + field)
    entry.add_argument("--commands", help='Verification commands as JSON, for example \'[["npm","test"]]\'.')
    entry.add_argument("--apply", action="store_true")
    entry = sub.add_parser("repos", help="Workspace repository status; --apply clones missing repositories.")
    entry.add_argument("--apply", action="store_true")
    entry.add_argument("--ssh", action="store_true", help="Clone using SSH instead of HTTPS.")
    entry.add_argument("--update", action="store_true",
                       help="Fetch and fast-forward clean default-branch checkouts; leave other checkouts in place.")
    entry = sub.add_parser("hub", help="Generate the Project map draft, a child of the hub page.")
    entry.add_argument("--text", action="store_true", help="Markdown only instead of JSON.")
    entry = sub.add_parser("doc", help="Register a document: repository source and published page.")
    entry.add_argument("--id", required=True)
    entry.add_argument("--type", choices=DOCUMENT_TYPES)
    for field in ["title", "source", "page-url"]:
        entry.add_argument("--" + field)
    entry.add_argument("--published", action="store_true", help="Attest that the current source has been published.")
    entry.add_argument("--apply", action="store_true")
    sub.add_parser("docs", help="List documents and publication/update needs.")
    sub.add_parser("integrations", help="Show saved integration links and status.")
    connection = sub.add_parser("link", help="Save service URLs with --apply, without verifying access.")
    for field in ["repository-url", "jira-url", "jira-project-key", "confluence-url", "confluence-space-key", "hub-url", "map-url"]:
        connection.add_argument("--" + field)
    connection.add_argument("--apply", action="store_true")
    task = sub.add_parser("checkpoint", help="Prepare current task state; --apply saves it.")
    for field in ["task", "owner", "summary"]:
        task.add_argument("--" + field, required=True)
    task.add_argument("--status", choices=["todo", "in_progress", "blocked", "review", "done"], default="in_progress")
    task.add_argument("--domain", choices=["software", "ui", "infrastructure", "security", "marketing", "sales", "other"], default="software")
    task.add_argument("--next", default="")
    for field in ["completed", "blocker", "evidence"]:
        task.add_argument("--" + field, action="append", default=[])
    task.add_argument("--repo", action="append", default=[], metavar="NAME[=PATH]", help=selector)
    task.add_argument("--transfer-from")
    task.add_argument("--apply", action="store_true")
    sub.add_parser("tasks", help="Summarize checkpoints in docs/tasks.")
    entry = sub.add_parser("openspec", help="Preview OpenSpec setup; --apply installs from the lockfile.")
    entry.add_argument("--apply", action="store_true")
    cli = sub.add_parser("spec", add_help=False, help="Run the local OpenSpec CLI without implicit installation.")
    cli.add_argument("argv", nargs=argparse.REMAINDER)
    checks = sub.add_parser("preflight", add_help=False, help="Session checks for tools and service access.")
    checks.add_argument("argv", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.action in {"repo", "doc", "link", "language", "checkpoint"} and args.apply:
        # Protect read-modify-write within this checkout; this is not a distributed claim.
        with local_lock("project-metadata", wait=True):
            return globals()[args.action](args)
    return globals()[args.action](args)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, KeyError, TypeError) as error:
        emit({"status": "error", "message": str(error)})
        sys.exit(2)
