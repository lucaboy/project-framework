"""Behavioral tests for generation, conservative updates and project state."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

PACKAGE = Path(__file__).resolve().parent.parent
FRAMEWORK = PACKAGE / "scripts/framework.py"
INSTALL = PACKAGE / "scripts/install_skill.py"


def run(script, *args, cwd=None):
    return subprocess.run([sys.executable, str(script), *map(str, args)], cwd=cwd,
                          capture_output=True, text=True,
                          env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})


class ProjectFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.project = self.base / "project"

    def tearDown(self):
        self.temp.cleanup()

    def create(self, provider="github", tracker="jira", profile="generic"):
        result = run(FRAMEWORK, "init", self.project, "--name", "Progetto demo",
                     "--provider", provider, "--tracker", tracker, "--profile", profile, "--git", "--apply")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return self.project / "scripts/project.py"

    def set_commands(self, commands):
        path = self.project / ".project/config.json"
        value = json.loads(path.read_text())
        value["commands"] = commands
        value["purpose"] = "Collaudo del protocollo"
        path.write_text(json.dumps(value))

    def commit(self, message="snapshot"):
        identity = ["-c", "user.name=Test", "-c", "user.email=test@example.invalid"]
        for argv in (["add", "-A"], [*identity, "commit", "-qm", message]):
            subprocess.run(["git", "-C", str(self.project), *argv], check=True, capture_output=True)

    def newer_skill(self):
        """A copy of this package whose templates a test can change, as a later release would."""
        newer = self.base / "newer-skill"
        shutil.copytree(PACKAGE, newer, ignore=shutil.ignore_patterns("__pycache__", ".git"))
        return newer


class ProjectTests(ProjectFixture):
    def test_dry_run_does_not_create_destination(self):
        result = run(FRAMEWORK, "init", self.project, "--name", "Demo")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(json.loads(result.stdout)["status"], "plan")
        self.assertFalse(self.project.exists())

    def test_provider_and_tracker_profiles(self):
        for provider, tracker in [("github", "jira"), ("github", "github"), ("bitbucket", "jira")]:
            with self.subTest(provider=provider, tracker=tracker):
                self.project = self.base / (provider + tracker)
                script = self.create(provider, tracker, "web")
                result = run(script, "doctor")
                self.assertEqual(result.returncode, 0, result.stdout)
                self.assertTrue(json.loads(result.stdout)["framework_ready"])
                self.assertFalse(json.loads(result.stdout)["application_commands_configured"])
                self.assertEqual((self.project / ".github/workflows/ci.yml").exists(), provider == "github")
                self.assertEqual((self.project / "bitbucket-pipelines.yml").exists(), provider == "bitbucket")
                self.assertEqual((self.project / ".github/ISSUE_TEMPLATE/task.yml").exists(), tracker == "github")
                self.assertIn("Areas to map", (self.project / "docs/ARCHITECTURE.md").read_text())

    def test_refuses_mixed_bitbucket_github_tracker(self):
        result = run(FRAMEWORK, "init", self.project, "--name", "Demo", "--provider", "bitbucket",
                     "--tracker", "github", "--apply")
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.project.exists())

    def test_adoption_collision_does_not_write_anything(self):
        self.project.mkdir()
        (self.project / "AGENTS.md").write_text("Regole esistenti")
        (self.project / "scripts").mkdir()
        (self.project / "scripts/project.py").write_text("# Strumento applicativo esistente")
        result = run(FRAMEWORK, "init", self.project, "--name", "Demo", "--adopt", "--apply")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(sorted(p.name for p in self.project.iterdir()), ["AGENTS.md", "scripts"])
        self.assertEqual((self.project / "AGENTS.md").read_text(), "Regole esistenti")

    def test_init_is_idempotent_and_preserves_project_configuration(self):
        self.create()
        self.set_commands([[sys.executable, "-c", "print('ok')"]])
        before = (self.project / ".project/config.json").read_bytes()
        result = run(FRAMEWORK, "init", self.project, "--name", "Progetto demo", "--apply")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(json.loads(result.stdout)["status"], "already_initialized")
        self.assertEqual((self.project / ".project/config.json").read_bytes(), before)

    def test_repeated_init_ignores_what_is_observed_from_the_checkout(self):
        self.create()
        # No commit yet: the current branch is the only one Git can report.
        subprocess.run(["git", "-C", str(self.project), "switch", "-c", "lavoro"], check=True, capture_output=True)
        result = run(FRAMEWORK, "init", self.project, "--name", "Progetto demo")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(json.loads(result.stdout)["status"], "already_initialized")
        result = run(FRAMEWORK, "init", self.project, "--name", "Progetto demo", "--profile", "web")
        self.assertEqual(result.returncode, 2, result.stdout)

    def test_plan_states_the_options_and_a_blocked_run_prints_one_document(self):
        result = run(FRAMEWORK, "init", self.project, "--name", "Demo", "--profile", "web")
        self.assertIn(".project/template-state.json", json.loads(result.stdout)["files"])
        self.assertEqual(json.loads(result.stdout)["options"],
                         {"name": "Demo", "slug": "demo", "provider": "github", "tracker": "jira",
                          "profile": "web", "kind": "single", "workspace_url": "", "default_branch": "main"})
        self.project.mkdir()
        (self.project / "scripts").mkdir()
        (self.project / "scripts/project.py").write_text("# Strumento applicativo esistente")
        for arguments in (["--adopt"], ["--adopt", "--apply"]):
            result = run(FRAMEWORK, "init", self.project, "--name", "Demo", *arguments)
            self.assertEqual(result.returncode, 2, result.stdout)
            value = json.loads(result.stdout)  # A single JSON document, whatever the mode.
            self.assertEqual((value["status"], value["files"]), ("conflict", ["scripts/project.py"]))
            self.assertTrue(value["message"])

    def test_edited_project_documents_survive_updates(self):
        self.create()
        product = self.project / "docs/PRODUCT.md"
        product.write_text("Decisione reale dell'utente")
        result = run(FRAMEWORK, "update", self.project, "--apply")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(product.read_text(), "Decisione reale dell'utente")

    def test_update_applies_untouched_files_but_aborts_all_writes_on_conflict(self):
        self.create()
        newer = self.base / "newer-skill"
        shutil.copytree(PACKAGE, newer, ignore=shutil.ignore_patterns("__pycache__", ".git"))
        incoming = newer / "assets/project/common/AGENTS.md.tmpl"
        incoming.write_text(incoming.read_text() + "\nNuova regola upstream.\n")
        result = run(newer / "scripts/framework.py", "update", self.project, "--apply")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("Nuova regola upstream", (self.project / "AGENTS.md").read_text())
        (self.project / "AGENTS.md").write_text("Istruzioni locali modificate")
        incoming.write_text(incoming.read_text() + "Seconda modifica upstream.\n")
        (newer / "assets/project/common/new-managed.txt").write_text("nuovo")
        old_state = (self.project / ".project/template-state.json").read_bytes()
        result = run(newer / "scripts/framework.py", "update", self.project, "--apply")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertEqual((self.project / "AGENTS.md").read_text(), "Istruzioni locali modificate")
        self.assertFalse((self.project / "new-managed.txt").exists())
        self.assertEqual((self.project / ".project/template-state.json").read_bytes(), old_state)

    def test_symlink_paths_are_rejected_before_writing(self):
        self.project.mkdir()
        outside = self.base / "outside"
        outside.mkdir()
        (self.project / "docs").symlink_to(outside, target_is_directory=True)
        result = run(FRAMEWORK, "init", self.project, "--name", "Demo", "--adopt", "--apply")
        self.assertEqual(result.returncode, 2)
        self.assertFalse(list(outside.iterdir()))
        self.assertFalse((self.project / "AGENTS.md").exists())

    def test_manifest_path_traversal_is_rejected(self):
        self.create()
        manifest = self.project / ".project/template-state.json"
        value = json.loads(manifest.read_text())
        value["files"]["../outside"] = {"sha256": "x", "ownership": "template"}
        manifest.write_text(json.dumps(value))
        result = run(FRAMEWORK, "update", self.project, "--apply")
        self.assertEqual(result.returncode, 2)
        self.assertFalse((self.base / "outside").exists())

    def test_application_verification_does_not_pass_without_commands(self):
        script = self.create()
        result = run(script, "verify")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertEqual(json.loads(result.stdout)["status"], "not_configured")

    def test_doctor_reports_partial_openspec_setup_for_each_client(self):
        script = self.create()
        dependencies = json.loads((self.project / ".project/dependencies.json").read_text())
        for name in dependencies["openspec"]["skills"]:
            skill = self.project / (".agents/skills/" + name + "/SKILL.md")
            skill.parent.mkdir(parents=True)
            skill.write_text("Test fixture")
        result = run(script, "doctor")
        self.assertEqual(result.returncode, 0, result.stdout)
        value = json.loads(result.stdout)
        self.assertEqual(value["openspec_clients_ready"], {"codex": True, "claude": False})
        self.assertTrue(any("OpenSpec" in warning for warning in value["warnings"]))

    def test_doctor_detects_missing_workflow_beyond_propose(self):
        script = self.create()
        dependencies = json.loads((self.project / ".project/dependencies.json").read_text())
        for folder in [".agents/skills", ".claude/skills"]:
            for name in dependencies["openspec"]["skills"]:
                skill = self.project / folder / name / "SKILL.md"
                skill.parent.mkdir(parents=True)
                skill.write_text("Test fixture")
        (self.project / ".claude/skills/openspec-archive-change/SKILL.md").unlink()
        result = run(script, "doctor")
        value = json.loads(result.stdout)
        self.assertTrue(value["openspec_clients_ready"]["codex"])
        self.assertFalse(value["openspec_clients_ready"]["claude"])
        self.assertEqual(value["openspec_missing_skills"]["claude"], ["openspec-archive-change"])

    def test_failing_checks_propagate_and_block_software_delivery(self):
        script = self.create()
        self.set_commands([[sys.executable, "-c", "raise SystemExit(7)"]])
        result = run(script, "verify")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertEqual(json.loads(result.stdout)["checks"][0]["returncode"], 7)
        result = run(script, "checkpoint", "--task", "APP-1", "--owner", "agent-a", "--summary", "Fix",
                     "--status", "done", "--apply")
        self.assertEqual(result.returncode, 2)
        self.assertFalse((self.project / "docs/tasks/APP-1.json").exists())

    def test_current_verification_allows_checkpoint_but_stale_proof_does_not(self):
        script = self.create()
        self.set_commands([[sys.executable, "-c", "print('verification fixture passed')"]])
        (self.project / "app.py").write_text("value = 1\n")
        self.assertEqual(run(script, "verify").returncode, 0)
        arguments = ["checkpoint", "--task", "APP-1", "--owner", "agent-a", "--summary", "Fix",
                     "--status", "review", "--apply"]
        result = run(script, *arguments)
        self.assertEqual(result.returncode, 0, result.stdout)
        # Changes to checkpoint metadata don't invalidate code evidence.
        self.assertEqual(run(script, *arguments).returncode, 0)
        (self.project / "app.py").write_text("value = 2\n")
        result = run(script, *arguments)
        self.assertEqual(result.returncode, 2, result.stdout)

    def test_checks_that_change_sources_require_a_new_verification(self):
        script = self.create()
        self.set_commands([[sys.executable, "-c", "from pathlib import Path; Path('app.py').write_text('changed')"]])
        result = run(script, "verify")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertTrue(json.loads(result.stdout)["source_changed_during_checks"])

    def test_nonsoftware_checkpoint_requires_evidence_and_preserves_owner(self):
        script = self.create()
        common = ["checkpoint", "--task", "MKT-1", "--summary", "Bozze campagna", "--domain", "marketing"]
        self.assertEqual(run(script, *common, "--owner", "agent-a", "--status", "done", "--apply").returncode, 2)
        result = run(script, *common, "--owner", "agent-a", "--status", "review", "--evidence", "docs/MARKETING.md", "--apply")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(run(script, *common, "--owner", "agent-b", "--apply").returncode, 2)
        self.assertEqual(run(script, *common, "--owner", "agent-b", "--transfer-from", "agent-a", "--apply").returncode, 0)

    def test_checkpoint_limit_and_identifier_validation(self):
        script = self.create()
        result = run(script, "checkpoint", "--task", "../escape", "--owner", "a", "--summary", "Task", "--apply")
        self.assertEqual(result.returncode, 2)
        result = run(script, "checkpoint", "--task", "APP-1", "--owner", "a", "--summary", "parola " * 501, "--apply")
        self.assertEqual(result.returncode, 2)

    def test_link_is_local_and_rejects_credentials_in_url(self):
        script = self.create()
        before = (self.project / ".project/config.json").read_bytes()
        result = run(script, "link", "--repository-url", "https://github.com/example/demo")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual((self.project / ".project/config.json").read_bytes(), before)
        result = run(script, "link", "--jira-url", "https://user:password@example.atlassian.net", "--apply")
        self.assertEqual(result.returncode, 2)
        self.assertEqual((self.project / ".project/config.json").read_bytes(), before)
        result = run(script, "link", "--repository-url", "https://github.com/example/demo", "--apply")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(json.loads(result.stdout)["status"], "linked_unverified")

    def test_openspec_preview_uses_pinned_lockfile_without_network(self):
        script = self.create()
        result = run(script, "openspec")
        self.assertEqual(result.returncode, 0, result.stdout)
        value = json.loads(result.stdout)
        self.assertIn("--ignore-scripts", value["install_argv"])
        self.assertIn("core", value["init_argv"])
        self.assertNotIn("--language", value["init_argv"])
        self.assertFalse((self.project / ".project/local").exists())
        lock = json.loads((self.project / ".project/tooling/package-lock.json").read_text())
        self.assertEqual(lock["packages"]["node_modules/@fission-ai/openspec"]["version"], "2.0.0")

    def test_openspec_setup_checks_the_node_version_before_installing(self):
        script = self.create()
        tools = self.base / "fake-tools"
        tools.mkdir()
        (tools / "npm").write_text("#!/bin/sh\nexit 0\n")
        (tools / "npm").chmod(0o755)
        outcomes = {"v22.11.0": 2, "v24.0.0-nightly20260101abcdef": 1}
        for version, expected in outcomes.items():
            # No network: a stand-in node reports the version and does nothing else.
            (tools / "node").write_text(f'#!/bin/sh\n[ "$1" = "--version" ] && echo {version}\nexit 0\n')
            (tools / "node").chmod(0o755)
            result = subprocess.run([sys.executable, str(script), "openspec", "--apply"], capture_output=True, text=True,
                                    env={**os.environ, "PATH": str(tools) + os.pathsep + os.environ["PATH"],
                                         "PYTHONDONTWRITEBYTECODE": "1"})
            self.assertEqual(result.returncode, expected, version + result.stdout)
        self.assertEqual(json.loads(result.stdout)["status"], "incomplete")

    def test_local_openspec_cli_requires_setup_without_implicit_download(self):
        script = self.create()
        result = run(script, "spec", "list", "--json")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("openspec --apply", json.loads(result.stdout)["message"])
        self.assertFalse((self.project / ".project/local").exists())

    def test_complete_skill_installation_for_both_clients(self):
        result = run(INSTALL, "--client", "both", "--base", self.base)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertFalse((self.base / ".agents").exists())
        result = run(INSTALL, "--client", "both", "--base", self.base, "--apply")
        self.assertEqual(result.returncode, 0, result.stdout)
        for client in [".agents", ".claude"]:
            installed = self.base / client / "skills/project-framework"
            self.assertTrue((installed / "SKILL.md").is_file())
            self.assertIn("name: project-framework\n", (installed / "SKILL.md").read_text())
            target = self.base / (client + "-project")
            result = run(installed / "scripts/framework.py", "init", target, "--name", "Installed", "--apply")
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertTrue((target / "scripts/project.py").is_file())
            # The copy leaves out the package's own .gitignore, never the one it distributes.
            self.assertTrue((target / ".gitignore").is_file())
            self.assertFalse((installed / ".gitignore").exists())
            self.assertFalse((installed / ".github").exists())
            self.assertFalse((installed / ".gitattributes").exists())
            self.assertTrue((target / ".github/workflows/ci.yml").is_file())
        result = run(INSTALL, "--client", "both", "--base", self.base, "--apply")
        self.assertEqual(result.returncode, 2)

    def test_personal_installation_uses_the_directories_each_client_reads(self):
        # HOME is replaced so that a personal installation can never reach the real profile.
        home = self.base / "home"
        home.mkdir()
        claude_root = self.base / "claude-config"
        result = subprocess.run([sys.executable, str(INSTALL), "--client", "both", "--apply"],
                                capture_output=True, text=True,
                                env={**os.environ, "HOME": str(home), "CODEX_HOME": str(self.base / "codex-config"),
                                     "CLAUDE_CONFIG_DIR": str(claude_root)})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        installed = home / ".agents/skills/project-framework"
        self.assertTrue((installed / "SKILL.md").is_file())
        self.assertTrue((claude_root / "skills/project-framework/SKILL.md").is_file())
        self.assertFalse((self.base / "codex-config").exists())
        self.assertFalse(list(installed.rglob(".DS_Store")))
        self.assertFalse((installed / "tests").exists())

    def test_generated_files_follow_umask_and_adoption_keeps_existing_modes(self):
        self.create()
        umask = os.umask(0)
        os.umask(umask)
        for name in ["README.md", "scripts/project.py", ".project/template-state.json"]:
            self.assertEqual(stat.S_IMODE((self.project / name).stat().st_mode), 0o666 & ~umask, name)
        legacy = self.base / "legacy"
        legacy.mkdir()
        readme = legacy / "README.md"
        readme.write_text("# Esistente\n")
        readme.chmod(0o664)
        result = run(FRAMEWORK, "init", legacy, "--name", "Legacy", "--adopt", "--apply")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("project-framework:begin", readme.read_text())
        self.assertEqual(stat.S_IMODE(readme.stat().st_mode), 0o664)

    def test_templates_are_read_as_utf8_whatever_the_locale(self):
        ascii_locale = {"LC_ALL": "C", "LANG": "C", "PYTHONUTF8": "0", "PYTHONCOERCECLOCALE": "0",
                        "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"}
        result = subprocess.run([sys.executable, str(FRAMEWORK), "init", str(self.project), "--name", "Demo", "--apply"],
                                capture_output=True, text=True, env={**os.environ, **ascii_locale})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Outcome and scope → task and proportionate plan", (self.project / "README.md").read_text(encoding="utf-8"))
        result = subprocess.run([sys.executable, str(self.project / "scripts/project.py"), "doctor"],
                                capture_output=True, text=True, env={**os.environ, **ascii_locale})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_fresh_clone_with_only_git_metadata_needs_no_adoption(self):
        subprocess.run(["git", "init", "-b", "trunk", str(self.project)], check=True, capture_output=True)
        result = run(FRAMEWORK, "init", self.project, "--name", "Demo", "--apply", "--git")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertFalse(json.loads(result.stdout)["git_init"])
        self.assertFalse((self.project / ".project/adoption.json").exists())
        self.assertEqual(json.loads((self.project / ".project/config.json").read_text())["default_branch"], "trunk")

    def test_destination_inside_another_repository_warns_and_never_nests_git(self):
        outer = self.base / "monorepo"
        subprocess.run(["git", "init", "-b", "main", str(outer)], check=True, capture_output=True)
        self.project = outer / "services/api"
        result = run(FRAMEWORK, "init", self.project, "--name", "Api", "--apply", "--git")
        self.assertEqual(result.returncode, 0, result.stdout)
        value = json.loads(result.stdout)
        self.assertFalse(value["git_init"])
        self.assertTrue(any("monorepo" in warning for warning in value["warnings"]))
        self.assertFalse((self.project / ".git").exists())
        self.assertTrue((self.project / "AGENTS.md").is_file())

    def test_instruction_templates_are_inert_inside_the_package(self):
        # Claude Code loads CLAUDE.md/AGENTS.md of a subdirectory as rules once it reads a file there.
        live = [p for p in (PACKAGE / "assets").rglob("*") if p.name in {"AGENTS.md", "CLAUDE.md", "CLAUDE.local.md"}]
        self.assertEqual(live, [])
        self.create()
        self.assertEqual((self.project / "CLAUDE.md").read_text().strip(), "@AGENTS.md")
        self.assertIn("# Project instructions", (self.project / "AGENTS.md").read_text())
        self.assertFalse(list(self.project.rglob("*.tmpl")))

    def test_plan_proposes_names_for_new_remote_resources(self):
        expected = {"Portale Clienti": ("portale-clienti", "PC"), "textstats": ("textstats", "TEXT"),
                    "3D Print": ("3d-print", "P3P"), "A": ("a", "AX")}
        for name, (repository, key) in expected.items():
            value = json.loads(run(FRAMEWORK, "init", self.base / repository, "--name", name).stdout)
            self.assertEqual(value["suggested_names"],
                             {"repository": repository, "jira_project_key": key, "confluence_space_key": key,
                              "hub_page_title": name + " — Hub"})
            self.assertEqual(value["remote_operations"], [])

    def test_clone_on_another_computer_reports_what_is_local_only(self):
        script = self.create()
        dependencies = json.loads((self.project / ".project/dependencies.json").read_text())
        for folder in [".agents/skills", ".claude/skills"]:
            for name in dependencies["openspec"]["skills"]:
                skill = self.project / folder / name / "SKILL.md"
                skill.parent.mkdir(parents=True)
                skill.write_text("Test fixture")
        run(script, "checkpoint", "--task", "APP-1", "--owner", "agent-a", "--summary", "Login", "--apply")
        self.commit()
        clone = self.base / "altro-computer"
        subprocess.run(["git", "clone", "-q", str(self.project), str(clone)], check=True, capture_output=True)
        value = json.loads(run(clone / "scripts/project.py", "doctor").stdout)
        self.assertTrue(value["framework_ready"])
        self.assertFalse(value["openspec_local_cli"])
        self.assertTrue(any("openspec --apply" in warning for warning in value["warnings"]))
        self.assertEqual(json.loads(run(clone / "scripts/project.py", "tasks").stdout)[0]["id"], "APP-1")
        result = run(FRAMEWORK, "init", clone, "--name", "Progetto demo")
        self.assertIn("doctor", json.loads(result.stdout)["next"])

    def test_update_says_when_git_holds_no_state_to_return_to(self):
        self.create()
        value = json.loads(run(FRAMEWORK, "update", self.project).stdout)
        self.assertTrue(any("commit" in warning for warning in value["warnings"]))
        self.commit()
        value = json.loads(run(FRAMEWORK, "update", self.project).stdout)
        self.assertEqual((value["status"], value["warnings"]), ("plan", []))

    def test_update_never_downgrades_a_newer_project(self):
        self.create()
        manifest = self.project / ".project/template-state.json"
        state = json.loads(manifest.read_text())
        state["template_version"] = "99.0.0"
        manifest.write_text(json.dumps(state))
        before = manifest.read_bytes()
        result = run(FRAMEWORK, "update", self.project, "--apply")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("99.0.0", json.loads(result.stdout)["message"])
        self.assertEqual(manifest.read_bytes(), before)

    def test_conflict_shows_the_diff_and_keep_resolves_it_until_upstream_changes_again(self):
        self.create()
        newer = self.newer_skill()
        update = newer / "scripts/framework.py"
        incoming = newer / "assets/project/common/AGENTS.md.tmpl"
        local = self.project / "AGENTS.md"
        local.write_text(local.read_text() + "\n- Regola locale del team.\n")
        incoming.write_text(incoming.read_text() + "\n- Regola upstream uno.\n")
        value = json.loads(run(update, "update", self.project).stdout)
        self.assertEqual(value["status"], "conflict")
        self.assertIn("+- Regola upstream uno.", value["diffs"]["AGENTS.md"])
        self.assertIn("-- Regola locale del team.", value["diffs"]["AGENTS.md"])
        # A path that is not in conflict is refused, so that a typo cannot pass silently.
        result = run(update, "update", self.project, "--keep", "AGENTS.md", "--keep", "CLAUDE.md", "--apply")
        self.assertEqual(result.returncode, 2, result.stdout)
        kept = local.read_text()
        result = run(update, "update", self.project, "--keep", "AGENTS.md", "--apply")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(json.loads(result.stdout)["kept_project_versions"], ["AGENTS.md"])
        self.assertEqual(local.read_text(), kept)
        self.assertEqual(json.loads(run(update, "update", self.project).stdout)["status"], "plan")
        incoming.write_text(incoming.read_text() + "- Regola upstream due.\n")
        self.assertEqual(json.loads(run(update, "update", self.project).stdout)["status"], "conflict")

    def test_stubs_meant_to_be_edited_never_block_updates(self):
        self.create()
        manifest = self.project / ".project/template-state.json"
        state = json.loads(manifest.read_text())
        for name in (".github/workflows/ci.yml", ".env.example"):
            state["files"][name]["ownership"] = "template"  # Simulate a manifest that classified a project-owned stub as a template.
            (self.project / name).write_text((self.project / name).read_text() + "# adattato dal progetto\n")
        manifest.write_text(json.dumps(state))
        newer = self.newer_skill()
        for name in ("github/.github/workflows/ci.yml", "common/.env.example"):
            template = newer / "assets/project" / name
            template.write_text(template.read_text() + "# modifica upstream\n")
        result = run(newer / "scripts/framework.py", "update", self.project, "--apply")
        self.assertEqual(result.returncode, 0, result.stdout)
        for name in (".github/workflows/ci.yml", ".env.example"):
            self.assertTrue((self.project / name).read_text().endswith("# adattato dal progetto\n"), name)

    def test_commit_or_checkpoint_after_verification_keeps_the_proof(self):
        script = self.create()
        self.set_commands([[sys.executable, "-c", "print('ok')"]])
        (self.project / "app.py").write_text("value = 1\n")
        self.commit()
        self.assertEqual(run(script, "verify").returncode, 0)
        arguments = ["checkpoint", "--task", "APP-1", "--owner", "agent-a", "--summary", "Fix", "--apply"]
        self.assertEqual(run(script, *arguments, "--status", "review").returncode, 0)
        # The checkpoint file made the tree dirty, then a commit moved HEAD: the sources are the same.
        self.assertEqual(run(script, *arguments, "--status", "done").returncode, 0)
        self.commit("checkpoint")
        self.assertEqual(run(script, *arguments, "--status", "done").returncode, 0)
        (self.project / "app.py").write_text("value = 2\n")
        self.assertEqual(run(script, *arguments, "--status", "done").returncode, 2)

    def test_tracked_files_count_even_inside_directories_named_like_outputs(self):
        script = self.create()
        self.set_commands([[sys.executable, "-c", "print('ok')"]])
        (self.project / ".gitignore").write_text(".project/local/\n")
        tool = self.project / "tools/build/generate.py"
        tool.parent.mkdir(parents=True)
        tool.write_text("value = 1\n")
        self.commit()
        self.assertEqual(run(script, "verify").returncode, 0)
        arguments = ["checkpoint", "--task", "APP-1", "--owner", "agent-a", "--summary", "Fix",
                     "--status", "review", "--apply"]
        # An untracked report in a well-known output directory is not a source change.
        (self.project / "coverage").mkdir()
        (self.project / "coverage/report.txt").write_text("100%\n")
        self.assertEqual(run(script, *arguments).returncode, 0)
        tool.write_text("value = 2\n")
        self.assertEqual(run(script, *arguments).returncode, 2)

    def test_without_git_known_outputs_do_not_fail_verification_and_doctor_says_so(self):
        script = self.create()
        self.set_commands([[sys.executable, "-c",
                            "from pathlib import Path; Path('node_modules').mkdir(exist_ok=True); "
                            "Path('node_modules/cache.txt').write_text('x')"]])
        empty = self.base / "no-tools"
        empty.mkdir()
        environment = {**os.environ, "PATH": str(empty), "PYTHONDONTWRITEBYTECODE": "1"}
        result = subprocess.run([sys.executable, str(script), "verify"], capture_output=True, text=True, env=environment)
        self.assertEqual(result.returncode, 0, result.stdout)
        result = subprocess.run([sys.executable, str(script), "doctor"], capture_output=True, text=True, env=environment)
        self.assertTrue(any("Git unavailable" in warning for warning in json.loads(result.stdout)["warnings"]))

    def test_link_rejects_what_the_session_checks_would_refuse(self):
        script = self.create()
        before = (self.project / ".project/config.json").read_bytes()
        for url in ["https://example.atlassian.net/browse?selectedIssue=APP-1",
                    "https://example.atlassian.net/#board", "https://example.atlassian.net:8443"]:
            result = run(script, "link", "--jira-url", url, "--jira-project-key", "APP", "--apply")
            self.assertEqual(result.returncode, 2, url)
        self.assertEqual((self.project / ".project/config.json").read_bytes(), before)
        result = run(script, "link", "--jira-url", "https://example.atlassian.net/", "--jira-project-key", "APP", "--apply")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(run(script, "preflight", "--session", "chat-a").returncode, 0)


if __name__ == "__main__":
    unittest.main()
