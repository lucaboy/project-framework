"""Multi-repository projects: workspace, application repositories, documents, hub and status."""
import json
import os
import subprocess
import sys
import test_framework as base

FRAMEWORK, run = base.FRAMEWORK, base.run
PASS = [sys.executable, "-c", "print('ok')"]
WORKSPACE_URL = "https://example.invalid/org/portale-workspace"


class WorkspaceTests(base.ProjectFixture):
    def git(self, directory, *argv):
        identity = ["-c", "user.name=Test", "-c", "user.email=test@example.invalid"]
        return subprocess.run(["git", "-C", str(directory), *identity, *argv], check=True, capture_output=True, text=True)

    def workspace(self):
        result = run(FRAMEWORK, "init", self.project, "--name", "Portale Clienti", "--kind", "workspace",
                     "--apply", "--git")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.script = self.project / "scripts/project.py"
        return json.loads(result.stdout)

    def remotes(self, *names):
        """Local repositories that stand in for the remote ones, reached through an HTTPS-looking URL."""
        for name in names:
            remote = self.base / "remotes" / name
            remote.mkdir(parents=True)
            subprocess.run(["git", "init", "-q", "-b", "main", str(remote)], check=True)
            (remote / "app.py").write_text("value = 1\n")
            self.git(remote, "add", "-A")
            self.git(remote, "commit", "-qm", "Primo commit")
            result = run(self.script, "repo", "--name", name, "--url", "https://example.invalid/org/" + name,
                         "--role", "Area " + name, "--commands", json.dumps([PASS]), "--apply")
            self.assertEqual(result.returncode, 0, result.stdout)
        return self.repos("--apply")

    def repos(self, *arguments):
        redirect = {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_VALUE_0": "https://example.invalid/org/",
                    "GIT_CONFIG_KEY_0": "url." + (self.base / "remotes").as_uri() + "/.insteadOf"}
        return subprocess.run([sys.executable, str(self.script), "repos", *arguments], capture_output=True, text=True,
                              env={**os.environ, **redirect, "PYTHONDONTWRITEBYTECODE": "1"})

    def checkpoint(self, *extra, status="review"):
        return run(self.script, "checkpoint", "--task", "PC-1", "--owner", "agent-a", "--summary", "Login",
                   "--status", status, "--apply", *extra)

    def test_workspace_holds_the_method_and_leaves_application_checks_to_each_repository(self):
        plan = self.workspace()
        self.assertEqual(plan["options"]["kind"], "workspace")
        self.assertEqual(plan["suggested_names"]["repository"], "portale-clienti-workspace")
        self.assertIn("repos/", (self.project / ".gitignore").read_text().splitlines())
        pipeline = (self.project / ".github/workflows/ci.yml").read_text()
        self.assertIn("project.py doctor", pipeline)
        self.assertNotIn("project.py verify", pipeline)
        doctor = json.loads(run(self.script, "doctor").stdout)
        self.assertTrue(doctor["framework_ready"])
        self.assertTrue(any("No repositories registered" in warning for warning in doctor["warnings"]))
        result = run(self.script, "verify")
        self.assertEqual((result.returncode, json.loads(result.stdout)["status"]), (2, "not_configured"))

    def test_registered_repositories_are_cloned_verified_and_proved_one_by_one(self):
        self.workspace()
        plan = json.loads(run(self.script, "repos").stdout)
        self.assertEqual((plan["repositories"], plan["status"]), ([], "synced"))
        result = self.remotes("backend", "frontend")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["missing"], [])
        self.assertTrue((self.project / "repos/backend/app.py").is_file())
        # The clones are not part of the workspace repository.
        listed = self.git(self.project, "status", "--porcelain", "--untracked-files=all").stdout
        self.assertNotIn("repos/", listed)
        self.assertEqual(self.checkpoint().returncode, 2)  # No repository named.
        self.assertEqual(self.checkpoint("--repo", "backend").returncode, 2)  # Not verified yet.
        # A repository without checks is named by doctor and by a run that leaves it out.
        self.assertEqual(run(self.script, "repo", "--name", "docs-site", "--role", "Sito", "--apply").returncode, 0)
        doctor = json.loads(run(self.script, "doctor").stdout)
        self.assertTrue(any("without verification commands: docs-site" in warning for warning in doctor["warnings"]))
        result = run(self.script, "verify")
        self.assertEqual(result.returncode, 0, result.stdout)
        value = json.loads(result.stdout)
        self.assertEqual(sorted(value["verified_now"]), ["backend", "frontend"])
        self.assertEqual(value["not_verified"], {"docs-site": "commands not configured"})
        self.assertEqual(self.checkpoint("--repo", "backend", "--repo", "frontend").returncode, 0)
        (self.project / "repos/backend/app.py").write_text("value = 2\n")
        state = {item["name"]: item["verification"] for item in json.loads(run(self.script, "status").stdout)["repositories"]}
        self.assertEqual(state, {"backend": "outdated", "frontend": "passed", "docs-site": "not_configured"})
        self.assertEqual(self.checkpoint("--repo", "backend").returncode, 2)
        self.assertEqual(self.checkpoint("--repo", "frontend").returncode, 0)
        # Verifying one repository keeps the proof of the other.
        self.assertEqual(run(self.script, "verify", "--repo", "backend").returncode, 0)
        self.assertEqual(self.checkpoint("--repo", "backend", "--repo", "frontend").returncode, 0)
        saved = json.loads((self.project / "docs/tasks/PC-1.json").read_text())
        self.assertEqual(saved["repositories"], ["backend", "frontend"])
        text = run(self.script, "status", "--text").stdout
        self.assertIn("Portale Clienti (workspace)", text)
        self.assertIn("- backend (Area backend): branch main, commit ", text)
        self.assertIn("uncommitted changes; verification passed", text)
        self.assertIn("PC-1 [review] agent-a: Login", text)

    def test_update_moves_only_clean_checkouts_on_their_default_branch(self):
        self.workspace()
        self.assertEqual(self.remotes("backend", "frontend", "infra").returncode, 0)
        for name in ("backend", "frontend", "infra"):
            remote = self.base / "remotes" / name
            (remote / "app.py").write_text("value = 9\n")
            self.git(remote, "commit", "-qam", "Novità remota")
        (self.project / "repos/frontend/app.py").write_text("lavoro in corso\n")
        self.git(self.project / "repos/infra", "switch", "-q", "-c", "PC-2-prova")
        result = self.repos("--update")
        self.assertEqual(result.returncode, 0, result.stdout)
        updates = {item["name"]: (item["action"], item["reason"]) for item in json.loads(result.stdout)["updates"]}
        self.assertEqual(updates["backend"], ("updated", ""))
        self.assertEqual(updates["frontend"], ("left_as_is", "uncommitted changes"))
        self.assertEqual(updates["infra"], ("left_as_is", "on branch PC-2-prova"))
        self.assertEqual((self.project / "repos/backend/app.py").read_text(), "value = 9\n")
        self.assertEqual((self.project / "repos/frontend/app.py").read_text(), "lavoro in corso\n")

    def test_a_worktree_of_a_repository_is_verified_where_the_agent_works(self):
        self.workspace()
        self.assertEqual(self.remotes("backend").returncode, 0)
        worktree = self.base / "worktrees/PC-1-login"
        self.git(self.project / "repos/backend", "worktree", "add", "-q", "-b", "PC-1-login", str(worktree))
        (worktree / "app.py").write_text("value = 3\n")
        selector = "backend=" + str(worktree)
        self.assertEqual(run(self.script, "verify", "--repo", selector).returncode, 0)
        self.assertEqual(self.checkpoint("--repo", selector).returncode, 0)
        # The proof belongs to the worktree: the main checkout has different sources.
        self.assertEqual(self.checkpoint("--repo", "backend").returncode, 2)
        state = json.loads(run(self.script, "status").stdout)["repositories"][0]
        self.assertEqual((state["verification"], state["verified_in"]), ("passed", str(worktree.resolve())))
        self.assertIn("verification passed in worktree", run(self.script, "status", "--text").stdout)
        self.assertEqual(run(self.script, "verify", "--repo", "unknown").returncode, 2)

    def test_application_repository_gets_short_instructions_that_point_to_the_workspace(self):
        existing = self.base / "backend"
        existing.mkdir()
        (existing / "AGENTS.md").write_text("# Backend\n\nTest: `pytest`.\n")
        (existing / "main.py").write_text("print('app')\n")
        # The workspace repository may not exist yet: the address is added when it is known.
        result = run(FRAMEWORK, "init", existing, "--name", "Portale Clienti", "--kind", "component", "--adopt", "--apply")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("status", json.loads(result.stdout)["adoption"])  # No review file to complete here.
        self.assertIn("URL not linked yet", (existing / "AGENTS.md").read_text())
        result = run(FRAMEWORK, "update", existing, "--workspace-url", WORKSPACE_URL, "--apply")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(run(FRAMEWORK, "update", existing, "--workspace-url", "http://insecure.example").returncode, 2)
        instructions = (existing / "AGENTS.md").read_text()
        self.assertNotIn("URL not linked yet", instructions)
        self.assertTrue(instructions.startswith("# Backend\n\nTest: `pytest`.\n"))
        self.assertIn(WORKSPACE_URL, instructions)
        self.assertEqual((existing / "CLAUDE.md").read_text().count("@AGENTS.md"), 1)
        for absent in ("scripts", ".project/config.json", ".project/adoption.json", "docs", ".github"):
            self.assertFalse((existing / absent).exists(), absent)
        self.assertTrue((existing / ".project/template-state.json").is_file())
        result = run(FRAMEWORK, "init", self.project, "--name", "Demo", "--workspace-url", WORKSPACE_URL)
        self.assertEqual(result.returncode, 2, result.stdout)  # Only a component points to a workspace.

    def test_new_application_repository_keeps_its_own_notes_across_updates(self):
        self.workspace()
        component = self.project / "repos/api"
        result = run(FRAMEWORK, "init", component, "--name", "Portale Clienti", "--kind", "component",
                     "--workspace-url", WORKSPACE_URL, "--apply", "--git")
        self.assertEqual(result.returncode, 0, result.stdout)
        value = json.loads(result.stdout)
        # repos/ is ignored by the workspace: a repository created there is a separate one.
        self.assertEqual((value["git_init"], value["warnings"]), (True, []))
        self.assertTrue((component / ".git").exists())
        instructions = component / "AGENTS.md"
        instructions.write_text("Test: `npm test`.\n" + instructions.read_text())
        newer = self.newer_skill()
        template = newer / "assets/project/component/AGENTS.md.tmpl"
        template.write_text(template.read_text().replace("<!-- project-framework:end -->",
                                                         "- Regola nuova per i repository applicativi.\n<!-- project-framework:end -->"))
        result = run(newer / "scripts/framework.py", "update", component, "--apply")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(json.loads(result.stdout)["files"], ["AGENTS.md"])
        self.assertIn("Test: `npm test`.", instructions.read_text())
        self.assertIn("Regola nuova per i repository applicativi.", instructions.read_text())

    def test_documents_are_tracked_from_source_to_published_page(self):
        script = self.create()
        contract = self.project / "docs/api.yaml"
        contract.write_text("openapi: 3.1.0\n")
        common = ["doc", "--id", "api-pubblica"]
        self.assertEqual(run(script, *common, "--title", "Contratto API", "--apply").returncode, 2)
        missing = json.loads(run(script, "doc", "--id", "futuro", "--type", "flow", "--source", "docs/flusso.mmd").stdout)
        self.assertTrue(missing["warnings"])  # Registering ahead of the file is allowed, never silent.
        result = run(script, *common, "--type", "api", "--title", "Contratto API", "--source", "docs/api.yaml", "--apply")
        self.assertEqual((result.returncode, json.loads(result.stdout)["warnings"]), (0, []))
        states = lambda: {item["id"]: item["state"] for item in json.loads(run(script, "docs").stdout)["documents"]}
        self.assertEqual(states(), {"api-pubblica": "never_published"})
        self.assertEqual(run(script, *common, "--published", "--apply").returncode, 2)  # No page yet.
        page = "https://example.atlassian.net/wiki/spaces/PC/pages/1"
        self.assertEqual(run(script, *common, "--page-url", page, "--published", "--apply").returncode, 0)
        self.assertEqual(states(), {"api-pubblica": "current"})
        contract.write_text("openapi: 3.1.0\ninfo: {title: Nuova}\n")
        self.assertEqual(states(), {"api-pubblica": "stale"})
        self.assertTrue(any("api-pubblica" in warning for warning in json.loads(run(script, "doctor").stdout)["warnings"]))
        self.assertEqual(json.loads(run(script, "status").stdout)["documents_to_update"], ["api-pubblica"])
        contract.unlink()
        self.assertEqual(states(), {"api-pubblica": "missing_source"})
        self.assertEqual(run(script, "doc", "--id", "x", "--type", "api", "--source", "../fuori.yaml").returncode, 2)

    def test_hub_section_lists_the_project_and_carries_a_manifest_an_agent_can_read(self):
        self.workspace()
        self.assertEqual(self.remotes("backend").returncode, 0)
        hub = "https://example.atlassian.net/wiki/spaces/PC/pages/2"
        result = run(self.script, "link", "--repository-url", WORKSPACE_URL, "--jira-url", "https://example.atlassian.net",
                     "--jira-project-key", "PC", "--hub-url", hub, "--map-url", hub + "/mappa", "--apply")
        self.assertEqual(result.returncode, 0, result.stdout)
        value = json.loads(run(self.script, "hub").stdout)
        self.assertEqual(value["title"], "Portale Clienti — Project map")
        self.assertEqual(value["remote_operations"], [])
        markdown = value["markdown"]
        self.assertIn("_Generated by", markdown)
        self.assertIn("Do not rewrite", value["note"])  # The human-written hub page is never edited.
        self.assertIn("| backend | Area backend | https://example.invalid/org/backend |", markdown)
        embedded = json.loads(markdown.split("```json\n")[1].split("\n```")[0])
        self.assertEqual(embedded, value["manifest"])
        self.assertEqual(embedded["project_framework"], 2)
        self.assertEqual((embedded["repository"], embedded["tracker"]["project_key"]), (WORKSPACE_URL, "PC"))
        self.assertEqual(embedded["repositories"][0]["name"], "backend")
        self.assertEqual(run(self.script, "hub", "--text").stdout, markdown)
        self.assertIn("Hub: " + hub, run(self.script, "status", "--text").stdout)

    def test_generated_project_ships_the_guide_the_reviewer_and_the_deny_rules(self):
        script = self.create()
        for name in ("docs/GUIDE.md", ".project/TEMPLATES.md", ".project/REVIEW.md", ".claude/agents/reviewer.md"):
            self.assertTrue((self.project / name).is_file(), name)
        self.assertIn("tools: Read, Grep, Glob", (self.project / ".claude/agents/reviewer.md").read_text())
        settings = json.loads((self.project / ".claude/settings.json").read_text())
        self.assertIn("Read(./.env)", settings["permissions"]["deny"])
        config = json.loads((self.project / ".project/config.json").read_text())
        self.assertEqual(config["automation"], {"tracker": "guided", "documentation": "guided"})
        self.assertEqual(run(script, "repo", "--name", "backend", "--apply").returncode, 2)  # Not a workspace.
        # The always-loaded instructions stay short.
        # Always-loaded instructions cost on every task: only what is specific to this standard stays there.
        self.assertLess(len((self.project / "AGENTS.md").read_text().split()), 240)
        self.assertIn("Where to look:", (self.project / ".project/TEMPLATES.md").read_text())
        self.assertLess(len((self.project / ".project/WORKFLOW.md").read_text().split()), 1040)

    def test_preflight_covers_workspace_repositories_and_the_programs_their_checks_need(self):
        self.workspace()
        self.assertEqual(self.remotes("backend").returncode, 0)
        run(self.script, "repo", "--name", "legacy", "--url", "https://example.invalid/org/legacy",
            "--commands", json.dumps([["programma-che-non-esiste", "check"]]), "--apply")
        report = json.loads(run(self.script, "preflight", "--session", "chat-a").stdout)
        self.assertEqual(sorted(report["repositories"]), ["backend", "legacy"])
        self.assertIn("repository:backend", report["agent_checks"])
        self.assertEqual(report["tools"]["verification_programs"]["missing"], ["programma-che-non-esiste"])
        doctor = json.loads(run(self.script, "doctor").stdout)
        self.assertTrue(any("programma-che-non-esiste" in warning for warning in doctor["warnings"]))
        # A read made in the client is recorded for that repository, not for the workspace one.
        target = json.dumps(report["repositories"]["backend"]["target"])
        direct = self.project / "scripts/preflight.py"
        result = run(direct, "record", "--session", "chat-a", "--service", "repository", "--repo", "backend",
                     "--status", "verified_read", "--target", target, "--identity", "utente", "--tool", "get_repository",
                     "--evidence", "Repository letto")
        self.assertEqual(result.returncode, 0, result.stdout)
        value = json.loads(result.stdout)
        self.assertEqual(value["repositories"]["backend"]["status"], "verified_read")
        self.assertNotIn("repository:backend", value["agent_checks"])
        self.assertEqual(value["services"]["repository"]["status"], "not_configured")
        result = run(direct, "record", "--session", "chat-a", "--service", "repository", "--repo", "sconosciuto",
                     "--status", "unverified", "--target", target)
        self.assertEqual(result.returncode, 2)

    def test_doctor_and_map_say_what_is_not_connected_yet(self):
        self.workspace()
        warnings = json.loads(run(self.script, "doctor").stdout)["warnings"]
        self.assertTrue(any("Project repository not linked" in warning for warning in warnings))
        self.assertTrue(any("Tracker not linked" in warning for warning in warnings))
        self.assertTrue(json.loads(run(self.script, "hub").stdout)["warnings"])
        run(self.script, "link", "--repository-url", WORKSPACE_URL, "--jira-url", "https://example.atlassian.net",
            "--jira-project-key", "PC", "--confluence-url", "https://example.atlassian.net/wiki",
            "--confluence-space-key", "PC", "--apply")
        warnings = json.loads(run(self.script, "doctor").stdout)["warnings"]
        self.assertFalse(any("not linked" in warning for warning in warnings))
        self.assertTrue(any("hub or project map" in warning for warning in warnings))
        run(self.script, "language", "--set", "English", "--apply")
        self.assertEqual(json.loads(run(self.script, "hub").stdout)["warnings"], [])

    def test_component_plan_points_out_release_pipelines_and_instructions_codex_would_miss(self):
        existing = self.base / "tema"
        (existing / ".github/workflows").mkdir(parents=True)
        (existing / ".github/workflows/deploy-production.yml").write_text("on:\n  push:\n    branches: [main]\n")
        (existing / ".github/workflows/ci.yml").write_text("on: [pull_request]\njobs: {}\n")
        (existing / "CLAUDE.md").write_text("# Tema\n\n" + "Regola di architettura da conoscere. " * 12)
        result = run(FRAMEWORK, "init", existing, "--name", "Portale Clienti", "--kind", "component", "--adopt")
        value = json.loads(result.stdout)
        notes = value["adoption"]["notes"]
        self.assertTrue(any("deploy-production.yml" in note and "ci.yml" not in note for note in notes))
        self.assertTrue(any("Codex does not read" in note for note in notes))
        self.assertIn("release archives", value["next"])
        self.assertIn(".project/template-state.json", value["files"])

    def test_page_that_is_its_own_source_is_listed_and_never_reported_as_outdated(self):
        script = self.create()
        page = "https://example.atlassian.net/wiki/spaces/PC/pages/9"
        self.assertEqual(run(script, "doc", "--id", "pubblicita", "--type", "other", "--title", "Pubblicità", "--apply").returncode, 2)
        result = run(script, "doc", "--id", "pubblicita", "--type", "other", "--title", "Pubblicità", "--page-url", page, "--apply")
        self.assertEqual((result.returncode, json.loads(result.stdout)["warnings"]), (0, []))
        value = json.loads(run(script, "docs").stdout)
        self.assertEqual((value["documents"][0]["state"], value["to_update"]), ("page_authoritative", []))
        self.assertEqual(run(script, "doc", "--id", "pubblicita", "--published", "--apply").returncode, 2)
        self.assertIn("| Pubblicità | other | " + page + " |", json.loads(run(script, "hub").stdout)["markdown"])
        self.assertIn("Area page", (self.project / ".project/TEMPLATES.md").read_text())
