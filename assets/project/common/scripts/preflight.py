#!/usr/bin/env python3
"""Session-scoped, read-only integration checks. Never install tools or perform login."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit
import uuid

ROOT = Path(__file__).resolve().parent.parent
TTL = 600
IDENTITY = {}
SERVICES = ("repository", "jira", "confluence")
OUTCOMES = ("verified_read", "auth_required", "access_denied", "not_found_or_denied",
            "unavailable", "network_error", "unverified")


class Notice(ValueError):
    """A fixed message written in this file: safe to show because it never echoes input."""


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def emit(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def local_path(relative):
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise Notice("Local path not allowed.")
    current = ROOT
    for part in path.parts:
        current /= part
        if current.is_symlink():
            raise Notice("Local symbolic-link path not allowed.")
    return current


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".preflight-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(value, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def session_path(session):
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,200}", session):
        raise Notice("Invalid session ID.")
    key = hashlib.sha256(session.encode()).hexdigest()[:24]
    return local_path(f".project/local/preflight/{key}.json")


def configuration():
    value = json.loads(local_path(".project/config.json").read_text(encoding="utf-8"))
    if value.get("schema_version") != 2:
        raise Notice("Unsupported project configuration.")
    return value


def clean_url(value):
    if not value:
        return ""
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.port not in (None, 443)):
        raise Notice("Use HTTPS URLs without credentials, queries, fragments or custom ports.")
    return value.rstrip("/")


def targets(value):
    links = value.get("integrations", {})
    return {
        "repository": {"provider": value["provider"], "url": clean_url(links.get("repository_url", ""))},
        "jira": {"url": clean_url(links.get("jira_url", "")), "key": links.get("jira_project_key", "")},
        "confluence": {"url": clean_url(links.get("confluence_url", "")), "key": links.get("confluence_space_key", "")},
    }


def configured(service, target):
    return bool(target["url"] and (service == "repository" or target["key"]))


def components(value):
    """Application repositories of a workspace: each one is a destination of its own."""
    if value.get("kind") != "workspace":
        return {}
    return {entry["name"]: {"provider": value["provider"], "url": clean_url(entry.get("url", ""))}
            for entry in value.get("repositories", []) if isinstance(entry, dict) and entry.get("name")}


def scope_hash(value):
    scope = {"targets": targets(value), "tracker": value["tracker"], "repositories": components(value)}
    return hashlib.sha256(json.dumps(scope, sort_keys=True).encode()).hexdigest()


def run(argv):
    try:
        result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, errors="replace",
                                timeout=8, env={**os.environ, "GH_PROMPT_DISABLED": "1", "GIT_TERMINAL_PROMPT": "0"})
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "network timeout"
    except OSError:
        return 127, "", "tool unavailable"


def failure(code, text):
    text = text.lower()
    if re.search(r"\b401\b|not logged|authentication required|gh auth login|bad credentials", text):
        return "auth_required"
    if re.search(r"\b404\b", text):
        return "not_found_or_denied"
    if re.search(r"rate limit|\b429\b", text):
        return "unverified"
    if re.search(r"\b403\b|forbidden", text):
        return "access_denied"
    if code == 124 or re.search(r"connect|resolve|timeout|network|tls|certificate", text):
        return "network_error"
    return "unverified"


def github_probe(target):
    """CLI fallback only for github.com; other hosts are delegated to the client."""
    parsed = urlsplit(target["url"])
    path = parsed.path.removesuffix(".git").strip("/")
    if parsed.hostname != "github.com" or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", path):
        return None
    if not shutil.which("gh"):
        return None
    # One identity call per run, however many repositories are probed.
    identity = IDENTITY.get("login")
    if identity is None:
        code, output, error = run(["gh", "api", "--hostname", "github.com", "user", "--jq", ".login"])
        if code:
            return {"status": failure(code, output + error), "source": "gh_api", "identity": None,
                    "read_access": False, "write_access": "unverified"}
        identity = output.strip()
    if not re.fullmatch(r"[A-Za-z0-9_\[\]-]{1,100}", identity):
        return {"status": "unverified", "source": "gh_api", "identity": None,
                "read_access": False, "write_access": "unverified"}
    IDENTITY["login"] = identity
    code, output, error = run(["gh", "api", "--hostname", "github.com", "repos/" + path,
                               "--jq", '{name: .full_name, permissions: .permissions}'])
    if code:
        return {"status": failure(code, output + error), "source": "gh_api", "identity": identity,
                "read_access": False, "write_access": "unverified"}
    try:
        repository = json.loads(output)
        if repository["name"].lower() != path.lower():
            raise ValueError("Unexpected repository")
        permissions = repository.get("permissions") or {}
    except (ValueError, KeyError, TypeError):
        return {"status": "unverified", "source": "gh_api", "identity": identity,
                "read_access": False, "write_access": "unverified"}
    return {"status": "verified_read", "source": "gh_api", "identity": identity,
            "read_access": True, "write_access": "reported_allowed" if permissions.get("push") is True else "unverified",
            "evidence": "GET /user + GET /repos/" + path,
            "note": "A push role does not prove token scopes or branch rules; no write performed."}


def tool_inventory(value):
    tools = {}
    for name in ("git", "node", "npm", "gh", "codex", "claude"):
        available = bool(shutil.which(name))
        item = {"available": available}
        if available and name in ("git", "node"):
            code, out, _ = run([name, "--version"])
            item["version"] = out.strip()[:100] if not code else "unverified"
        tools[name] = item
    node = tools["node"].get("version", "")
    match = re.search(r"v?(\d+)\.(\d+)\.(\d+)", node)
    tools["node"]["meets_openspec_minimum"] = bool(match and tuple(map(int, match.groups())) >= (22, 12, 0))
    tools["openspec_local"] = {"available": local_path(
        ".project/local/openspec/node_modules/@fission-ai/openspec/bin/openspec.js").is_file()}
    dependencies = json.loads(local_path(".project/dependencies.json").read_text(encoding="utf-8"))["openspec"]
    expected = dependencies.get("skills", ["openspec-propose"])
    tools["openspec_workflows"] = {
        client: {"missing": [skill for skill in expected if not (ROOT / folder / skill / "SKILL.md").is_file()]}
        for client, folder in {"codex": ".agents/skills", "claude": ".claude/skills"}.items()}
    # The programs the configured checks start: a missing one is known now, not when verify fails.
    commands = list(value.get("commands", []))
    for entry in value.get("repositories", []):
        commands += entry.get("commands", []) if isinstance(entry, dict) else []
    programs = sorted({command[0] for command in commands if isinstance(command, list) and command})
    tools["verification_programs"] = {"missing": [name for name in programs if not shutil.which(name)]}
    tools["note"] = "Availability on this terminal's PATH: a desktop app may be in use without its CLI."
    return tools


def load_current(session, value):
    path = session_path(session)
    if not path.is_file():
        return None
    report = json.loads(path.read_text(encoding="utf-8"))
    if report.get("session") != session or report.get("scope") != scope_hash(value):
        return None
    return report


def prune(directory):
    """Evidence expires within minutes: drop the reports left behind by chats older than a day."""
    try:
        for path in directory.glob("*.json"):
            if (re.fullmatch(r"[0-9a-f]{24}\.json", path.name) and not path.is_symlink()
                    and path.stat().st_mtime < time.time() - 86400):
                path.unlink()
    except OSError:
        pass


def fresh(item):
    try:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(item["checked_at"])).total_seconds()
        return 0 <= age <= TTL
    except (ValueError, KeyError, TypeError):
        return False


def check(args):
    value = configuration()
    session = args.session or os.environ.get("CODEX_THREAD_ID") or str(uuid.uuid4())
    old = load_current(session, value)
    items = {}
    for service, target in targets(value).items():
        item = {"target": target, "status": "not_configured", "source": "local_configuration",
                "read_access": False, "write_access": "unverified"}
        if configured(service, target):
            item["status"] = "agent_check_required"
            previous = (old or {}).get("services", {}).get(service)
            if not args.refresh and previous and previous.get("source") == "agent_readonly_probe" and fresh(previous):
                item = previous
            elif args.live and service == "repository" and target["provider"] == "github":
                result = github_probe(target)
                if result:
                    item.update(result)
                    item["checked_at"] = now()
        items[service] = item
    repositories = {}
    for name, target in components(value).items():
        item = {"target": target, "status": "not_configured", "source": "local_configuration",
                "read_access": False, "write_access": "unverified"}
        if target["url"]:
            item["status"] = "agent_check_required"
            previous = (old or {}).get("repositories", {}).get(name)
            if not args.refresh and previous and previous.get("source") == "agent_readonly_probe" and fresh(previous):
                item = previous
            elif args.live and getattr(args, "components", True) and target["provider"] == "github":
                result = github_probe(target)
                if result:
                    item.update(result)
                    item["checked_at"] = now()
        repositories[name] = item
    required = args.require or []
    blocked = [name for name in required if items[name]["status"] != "verified_read" or not fresh(items[name])]
    report = {"schema_version": 1, "session": session, "scope": scope_hash(value), "at": now(),
              "tools": tool_inventory(value), "services": items, "repositories": repositories,
              "required": required, "blocked": blocked, "ready_for_requested_reads": not blocked,
              "agent_checks": [name for name, item in items.items() if item["status"] == "agent_check_required"]
              + ["repository:" + name for name, item in repositories.items() if item["status"] == "agent_check_required"],
              "guide": ".project/INTEGRATIONS.md", "ttl_seconds": TTL,
              "note": "No remote writes, installations or login. Test MCP/plugins in the current client."}
    save(session_path(session), report)
    prune(session_path(session).parent)
    emit(report)
    return 2 if blocked else 0


def record(args):
    value = configuration()
    report = load_current(args.session, value)
    if report is None:
        raise Notice("Preflight missing or targets changed: run check for this session.")
    if args.repo:
        # A workspace repository is recorded with --service repository --repo NAME.
        target = components(value).get(args.repo) if args.service == "repository" else None
        if not target or not target["url"]:
            raise Notice("Repository not registered in the workspace or missing its URL.")
    else:
        target = targets(value)[args.service]
        if not configured(args.service, target):
            raise Notice("Target not configured; link the actual resource first.")
    try:
        supplied = json.loads(args.target)
    except ValueError:
        supplied = None
    if supplied != target:
        raise Notice("The read does not match the configured target.")
    if args.status == "verified_read" and not (args.identity and args.tool and args.evidence):
        raise Notice("A verified read requires identity, tool and evidence of the actual read.")
    for field in (args.identity, args.tool, args.evidence):
        if field and (len(field) > 500 or any(ord(c) < 32 for c in field)
                      or re.search(r"(?i)bearer\s|authorization:|gh[pousr]_[A-Za-z0-9]+|://[^ /]+@", field)):
            raise Notice("Record only short references without credentials or raw output.")
    section = report.setdefault("repositories", {}) if args.repo else report["services"]
    section[args.repo or args.service] = {
        "target": target, "status": args.status, "source": "agent_readonly_probe", "checked_at": now(),
        "identity": args.identity, "tool": args.tool, "evidence": args.evidence,
        "read_access": args.status == "verified_read", "write_access": "unverified",
        "note": "Agent attestation based on reads in the client; the Python process cannot see MCP tools."}
    report["blocked"] = [name for name in report["required"] if report["services"][name]["status"] != "verified_read"
                         or not fresh(report["services"][name])]
    report["ready_for_requested_reads"] = not report["blocked"]
    report["agent_checks"] = [name for name, item in report["services"].items() if item["status"] == "agent_check_required"] + [
        "repository:" + name for name, item in report.get("repositories", {}).items() if item["status"] == "agent_check_required"]
    save(session_path(args.session), report)
    emit(report)
    return 0


def hook(args):
    global ROOT
    payload = json.load(sys.stdin)
    # Claude can run a shared hook from the main checkout while cwd is a worktree.
    # Check that active worktree, not the checkout containing the hook script.
    cwd = Path(payload.get("cwd", str(ROOT))).resolve()
    active = next((p for p in [cwd, *cwd.parents] if (p / ".project/config.json").is_file()
                   and (p / ".project/template-state.json").is_file()), None)
    if active is None:
        raise Notice("No initialized project in the active directory.")
    ROOT = active
    session = payload.get("session_id") or str(uuid.uuid4())
    # Hook output must remain compact; run checks without exposing raw command output.
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()):
        # The hook has a short timeout: application repositories are probed by the full preflight.
        check(argparse.Namespace(session=session, require=[], live=True, refresh=True, components=False))
    report = load_current(session, configuration())
    status = ", ".join(f"{name}={item['status']}" for name, item in report["services"].items())
    context = (f"Project Framework: session preflight {session}. {status}. "
               "Read AGENTS.md and .project/WORKFLOW.md. Before using external services read "
               ".project/INTEGRATIONS.md, discover available tools and complete MCP/plugin read probes "
               "for the configured targets. Record actual results with scripts/preflight.py record "
               f"--session {session}; do not reuse results from other chats. "
               "An unavailable service blocks only operations that depend on it. "
               "Do not install tools or start login from the hook. OAuth may need user interaction. "
               "A successful read does not prove write permissions.")
    emit({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}})
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    checks = sub.add_parser("check")
    checks.add_argument("--session")
    checks.add_argument("--live", action="store_true", help="Allow GitHub CLI reads when configured.")
    checks.add_argument("--refresh", action="store_true", help="Ignore previous evidence, including in this session.")
    checks.add_argument("--require", action="append", choices=SERVICES, default=[])
    evidence = sub.add_parser("record")
    evidence.add_argument("--session", required=True)
    evidence.add_argument("--service", choices=SERVICES, required=True)
    evidence.add_argument("--status", choices=OUTCOMES, required=True)
    evidence.add_argument("--target", required=True, help="Exact target JSON object from the report.")
    evidence.add_argument("--repo", help="With --service repository: a workspace repository name.")
    evidence.add_argument("--identity")
    evidence.add_argument("--tool")
    evidence.add_argument("--evidence")
    start = sub.add_parser("hook")
    start.add_argument("--client", choices=("codex", "claude"), required=True)
    args = parser.parse_args(argv)
    return globals()[args.action](args)


def entry(argv=None):
    """Command-line entry shared with project.py, so both paths report errors the same way."""
    try:
        return main(argv)
    except Notice as error:
        emit({"status": "error", "error": "Notice", "message": str(error)})
    except (ValueError, OSError, KeyError, TypeError) as error:
        # Avoid echoing exception contents: malformed config may contain credentials.
        emit({"status": "error", "error": type(error).__name__,
              "message": "Preflight incomplete: check configuration, arguments and local paths."})
    return 2


if __name__ == "__main__":
    sys.exit(entry())
