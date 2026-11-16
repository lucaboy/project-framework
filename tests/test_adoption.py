import json
from pathlib import Path
import shutil
import subprocess
import test_framework as base

PACKAGE, FRAMEWORK, run = base.PACKAGE, base.FRAMEWORK, base.run


class AdoptionTests(base.ProjectFixture):
    def adopt(self):
        return run(FRAMEWORK, "init", self.project, "--name", "Legacy", "--adopt", "--git", "--apply")

    def fixture(self):
        self.project.mkdir()
        originals = {
            "README.md": b"# Applicazione esistente\r\n\r\nSetup reale.\r\n",
            "AGENTS.md": b"Non modificare il contratto pubblico.\n",
            "AGENTS.override.md": b"Istruzione Codex specifica: usa unittest.\n",
            "CLAUDE.md": b"Controlla sempre gli errori HTTP.\n",
            ".gitignore": b"custom-output/\n",
            "app.py": b"def double(x):\n    return x * 2\n",
            ".github/workflows/ci.yml": b"name: Existing\non: [push]\njobs: {}\n",
            "docs/WORKFLOW.md": b"Il processo aziendale esistente.\n",
        }
        for name, data in originals.items():
            path = self.project / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        settings = {"env": {"TEAM_SETTING": "kept"}, "permissions": {"deny": ["Read(./private/**)"]},
                    "hooks": {"SessionStart": [
            {"hooks": [{"type": "command", "command": "python3 existing-hook.py"}]}]}}
        path = self.project / ".claude/settings.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(settings))
        return originals

    def test_adoption_preserves_code_pipeline_docs_and_merges_instructions(self):
        originals = self.fixture()
        result = self.adopt()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for name, before in originals.items():
            after = (self.project / name).read_bytes()
            if name in {"README.md", "AGENTS.md", "AGENTS.override.md", "CLAUDE.md", ".gitignore"}:
                self.assertTrue(after.startswith(before), name)
            else:
                self.assertEqual(after, before, name)
        settings = json.loads((self.project / ".claude/settings.json").read_text())
        self.assertEqual(settings["env"], {"TEAM_SETTING": "kept"})
        self.assertEqual(settings["hooks"]["SessionStart"][0]["hooks"][0]["command"], "python3 existing-hook.py")
        self.assertEqual(len(settings["hooks"]["SessionStart"]), 2)
        # The project's own deny rule stays first; the standard's rules are added once.
        self.assertEqual(settings["permissions"]["deny"][0], "Read(./private/**)")
        self.assertIn("Read(./.env)", settings["permissions"]["deny"])
        report = json.loads((self.project / ".project/adoption.json").read_text())
        self.assertTrue(report["review"])
        doctor = run(self.project / "scripts/project.py", "doctor")
        self.assertTrue(any("Adoption" in x for x in json.loads(doctor.stdout)["warnings"]))
        # Declaring the review done is not enough: the checks performed must be listed.
        path = self.project / ".project/adoption.json"
        for evidence, expected in (([], True), (["verify: 3 test superati"], False)):
            path.write_text(json.dumps({**report, "status": "reviewed", "evidence": evidence}))
            doctor = run(self.project / "scripts/project.py", "doctor")
            self.assertEqual(any("Adoption" in x for x in json.loads(doctor.stdout)["warnings"]), expected)

    def test_adoption_preview_has_no_changes(self):
        self.fixture()
        before = {p.relative_to(self.project): p.read_bytes() for p in self.project.rglob("*") if p.is_file()}
        result = run(FRAMEWORK, "init", self.project, "--name", "Legacy", "--adopt")
        self.assertEqual(result.returncode, 0, result.stdout)
        after = {p.relative_to(self.project): p.read_bytes() for p in self.project.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_existing_import_and_repeated_adoption_do_not_duplicate(self):
        self.fixture()
        claude = self.project / "CLAUDE.md"
        claude.write_text("@AGENTS.md\n\nRegola personale.\n")
        original = claude.read_bytes()
        self.assertEqual(self.adopt().returncode, 0)
        self.assertEqual(self.adopt().returncode, 0)
        self.assertEqual(claude.read_bytes(), original)
        self.assertEqual((self.project / "AGENTS.md").read_bytes().count(b"project-framework:begin"), 1)

    def test_update_changes_only_managed_blocks_and_preserves_local_additions(self):
        self.fixture()
        self.assertEqual(self.adopt().returncode, 0)
        newer = self.base / "newer"
        shutil.copytree(PACKAGE, newer)
        incoming = newer / "assets/project/common/AGENTS.md.tmpl"
        incoming.write_text(incoming.read_text() + "\nRegola della nuova versione.\n")
        local = self.project / "AGENTS.md"
        local.write_bytes(local.read_bytes() + b"\nRegola locale aggiunta dopo l'adozione.\n")
        result = run(newer / "scripts/framework.py", "update", self.project, "--apply")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue(local.read_text().startswith("Non modificare il contratto pubblico."))
        self.assertIn("Regola della nuova versione", local.read_text())
        self.assertTrue(local.read_text().endswith("Regola locale aggiunta dopo l'adozione.\n"))
        self.assertIn("Regola della nuova versione", (self.project / "AGENTS.override.md").read_text())

    def test_modified_managed_block_aborts_update_without_partial_writes(self):
        self.fixture()
        self.assertEqual(self.adopt().returncode, 0)
        local = self.project / "AGENTS.md"
        local.write_text(local.read_text().replace("# Project instructions", "# Regole modificate nel blocco"))
        newer = self.base / "newer"
        shutil.copytree(PACKAGE, newer)
        incoming = newer / "assets/project/common/AGENTS.md.tmpl"
        incoming.write_text(incoming.read_text() + "\nRegola upstream.\n")
        (newer / "assets/project/common/extra.txt").write_text("new")
        result = run(newer / "scripts/framework.py", "update", self.project, "--apply")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertFalse((self.project / "extra.txt").exists())

    def test_malformed_existing_hook_configuration_aborts_before_writes(self):
        self.fixture()
        (self.project / ".claude/settings.json").write_text("not json")
        before = (self.project / "AGENTS.md").read_bytes()
        result = self.adopt()
        self.assertEqual(result.returncode, 2)
        self.assertEqual((self.project / "AGENTS.md").read_bytes(), before)
        self.assertFalse((self.project / ".project/config.json").exists())

    def test_git_branch_and_safe_origin_are_preserved_without_commits(self):
        self.fixture()
        subprocess.run(["git", "init", "-b", "production", str(self.project)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(self.project), "remote", "add", "origin", "git@github.com:example/legacy.git"], check=True)
        result = self.adopt()
        self.assertEqual(result.returncode, 0, result.stdout)
        config = json.loads((self.project / ".project/config.json").read_text())
        self.assertEqual(config["default_branch"], "production")
        self.assertEqual(config["integrations"]["repository_url"], "https://github.com/example/legacy")
        branch = subprocess.check_output(["git", "-C", str(self.project), "branch", "--show-current"], text=True).strip()
        self.assertEqual(branch, "production")

    def test_update_adds_new_hooks_to_v1_without_overwriting_existing_settings(self):
        self.create()
        manifest = self.project / ".project/template-state.json"
        state = json.loads(manifest.read_text())
        for name in (".claude/settings.json", ".codex/hooks.json", ".codex/config.toml", "scripts/preflight.py"):
            del state["files"][name]
            (self.project / name).unlink()
        state["template_version"] = "1.0.0"
        manifest.write_text(json.dumps(state))
        settings = self.project / ".claude/settings.json"
        settings.write_text(json.dumps({"env": {"KEEP": "yes"}}))
        result = run(FRAMEWORK, "update", self.project, "--apply")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(json.loads(settings.read_text())["env"], {"KEEP": "yes"})
        self.assertTrue(json.loads(settings.read_text())["hooks"]["SessionStart"])
        self.assertTrue((self.project / "scripts/preflight.py").is_file())

    def test_local_edit_inside_a_section_conflicts_only_when_upstream_changes_it(self):
        self.fixture()
        self.assertEqual(self.adopt().returncode, 0)
        local = self.project / "AGENTS.md"
        local.write_text(local.read_text().replace("# Project instructions", "# Istruzioni adattate"))
        edited = local.read_bytes()
        result = run(FRAMEWORK, "update", self.project, "--apply")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(local.read_bytes(), edited)
        newer = self.newer_skill()
        update = newer / "scripts/framework.py"
        incoming = newer / "assets/project/common/AGENTS.md.tmpl"
        incoming.write_text(incoming.read_text() + "\n- Regola upstream.\n")
        value = json.loads(run(update, "update", self.project).stdout)
        self.assertEqual(value["files"], ["AGENTS.md"])
        self.assertIn("+- Regola upstream.", value["diffs"]["AGENTS.md"])
        result = run(update, "update", self.project, "--keep", "AGENTS.md", "--apply")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(local.read_bytes(), edited)
        # The other managed section still receives the release.
        self.assertIn("Regola upstream", (self.project / "AGENTS.override.md").read_text())
        value = json.loads(run(update, "update", self.project).stdout)
        self.assertEqual((value["status"], value["files"]), ("plan", []))
