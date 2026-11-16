"""Regression tests for proof validity, real process races and interrupted framework."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import signal
import shlex
import subprocess
import sys
import time
from unittest import mock

import test_framework as base
import test_workspace as helpers

PASS = [[sys.executable, "-c", "assert 2 + 2 == 4"]]
FAIL = [[sys.executable, "-c", "raise SystemExit(1)"]]


class ReliabilityTests(base.ProjectFixture):
    git = helpers.WorkspaceTests.git
    workspace = helpers.WorkspaceTests.workspace
    remotes = helpers.WorkspaceTests.remotes
    repos = helpers.WorkspaceTests.repos
    checkpoint = helpers.WorkspaceTests.checkpoint

    def single(self):
        self.script = self.create()
        self.set_commands(PASS)

    def proof(self):
        return json.loads((self.project / ".project/local/verification.json").read_text())

    def states(self):
        value = json.loads(base.run(self.script, "status").stdout)
        return {item["name"]: item["verification"] for item in value["repositories"]}

    def start(self, *args):
        process = subprocess.Popen([sys.executable, str(self.script), "verify", *args],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                   env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, start_new_session=True)
        def cleanup():
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
            process.communicate(timeout=5)
        self.addCleanup(cleanup)
        return process

    def wait_for(self, path):
        end = time.monotonic() + 10
        while not path.exists() and time.monotonic() < end:
            time.sleep(.02)
        self.assertTrue(path.exists(), "Test process did not reach its synchronization point")

    def blocked_command(self, name):
        # Gates are outside the application tree: commands and source fingerprints stay identical.
        gate = self.base / (name + "-block")
        ready = self.base / (name + "-ready")
        release = self.base / (name + "-release")
        failure = self.base / (name + "-fail")
        code = ("from pathlib import Path\nimport time\n"
                f"if Path({str(gate)!r}).exists():\n"
                f" Path({str(ready)!r}).touch()\n"
                " deadline=time.monotonic()+10\n"
                f" while not Path({str(release)!r}).exists():\n"
                "  if time.monotonic()>deadline: raise SystemExit(9)\n"
                "  time.sleep(.02)\n"
                f"raise SystemExit(1 if Path({str(failure)!r}).exists() else 0)\n")
        return [[sys.executable, "-c", code]], gate, ready, release, failure

    def test_changed_or_removed_workspace_commands_invalidate_success(self):
        self.workspace(); self.remotes("backend")
        for commands in (FAIL, []):
            with self.subTest(commands=commands):
                base.run(self.script, "repo", "--name", "backend", "--commands", json.dumps(PASS), "--apply")
                self.assertEqual(base.run(self.script, "verify").returncode, 0)
                base.run(self.script, "repo", "--name", "backend", "--commands", json.dumps(commands), "--apply")
                self.assertEqual(self.states()["backend"], "outdated" if commands else "not_configured")
                self.assertEqual(self.checkpoint("--repo", "backend").returncode, 2)

    def test_timeout_repository_and_runner_changes_invalidate_success(self):
        self.workspace(); self.remotes("backend")
        config = self.project / ".project/config.json"
        for change in ("timeout", "repository", "runner"):
            with self.subTest(change=change):
                self.assertEqual(base.run(self.script, "verify").returncode, 0)
                value = json.loads(config.read_text())
                if change == "timeout":
                    value["command_timeout_seconds"] += 1
                elif change == "repository":
                    value["repositories"][0]["url"] += "-changed"
                else:
                    self.script.write_text(self.script.read_text() + "\n# Changed verification implementation\n")
                config.write_text(json.dumps(value))
                self.assertEqual(self.states()["backend"], "outdated")
                self.assertEqual(self.checkpoint("--repo", "backend").returncode, 2)

    def test_configuration_changed_during_checks_fails_that_run(self):
        self.workspace(); self.remotes("backend")
        commands, gate, ready, release, _ = self.blocked_command("backend")
        base.run(self.script, "repo", "--name", "backend", "--commands", json.dumps(commands), "--apply")
        gate.touch(); process = self.start("--repo", "backend"); self.wait_for(ready)
        base.run(self.script, "repo", "--name", "backend", "--commands", json.dumps(PASS), "--apply")
        release.touch(); output, error = process.communicate(timeout=10)
        self.assertEqual(process.returncode, 1, output + error)
        self.assertTrue(self.proof()["repositories"]["backend"]["configuration_changed_during_checks"])
        self.assertEqual(self.checkpoint("--repo", "backend").returncode, 2)

    def test_executable_mode_change_invalidates_success(self):
        self.single()
        command = self.project / "check.sh"
        command.write_text("#!/bin/sh\nexit 0\n"); command.chmod(0o755)
        self.set_commands([["./check.sh"]]); self.commit()
        self.assertEqual(base.run(self.script, "verify").returncode, 0)
        command.chmod(0o644)
        self.assertEqual(json.loads(base.run(self.script, "status").stdout)["verification"], "outdated")
        self.assertEqual(self.checkpoint().returncode, 2)
        self.assertEqual(base.run(self.script, "verify").returncode, 1)

    def test_submodule_edits_commits_and_missing_checkout_invalidate_success(self):
        self.single()
        library = self.base / "library"; library.mkdir()
        self.git(library, "init", "-q", "-b", "main")
        (library / "value.txt").write_text("good")
        self.git(library, "add", "."); self.git(library, "commit", "-qm", "library")
        self.git(self.project, "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(library), "library")
        self.set_commands([[sys.executable, "-c", "from pathlib import Path; assert Path('library/value.txt').read_text() == 'good'"]])
        self.commit()
        self.assertEqual(base.run(self.script, "verify").returncode, 0)
        checkout = self.project / "library"
        (checkout / "value.txt").write_text("bad")
        self.assertEqual(self.checkpoint().returncode, 2)
        self.assertEqual(base.run(self.script, "verify").returncode, 1)
        (checkout / "value.txt").write_text("good")
        self.assertEqual(base.run(self.script, "verify").returncode, 0)
        self.git(checkout, "commit", "--allow-empty", "-qm", "different submodule revision")
        self.assertEqual(self.checkpoint().returncode, 2)
        self.assertEqual(base.run(self.script, "verify").returncode, 0)
        self.git(self.project, "submodule", "deinit", "-f", "library")
        self.assertEqual(json.loads(base.run(self.script, "status").stdout)["verification"], "outdated")
        self.assertEqual(base.run(self.script, "verify").returncode, 2)
        self.assertEqual(self.proof()["status"], "incomplete")
        self.assertEqual(self.checkpoint().returncode, 2)

    def test_wrong_repository_cannot_be_used_as_a_worktree(self):
        self.workspace(); self.remotes("backend", "frontend")
        selector = "backend=" + str(self.project / "repos/frontend")
        self.assertEqual(base.run(self.script, "verify", "--repo", selector).returncode, 2)
        self.assertEqual(self.checkpoint("--repo", selector).returncode, 2)
        self.assertFalse((self.project / ".project/local/verification.json").exists())

    def test_worktree_error_keeps_the_exact_selector_in_the_suggested_command(self):
        self.workspace(); self.remotes("backend")
        worktree = self.base / "worktree with spaces"
        self.git(self.project / "repos/backend", "worktree", "add", "-q", "-b", "PC-1", str(worktree))
        selector = "backend=" + str(worktree)
        result = self.checkpoint("--repo", selector)
        self.assertEqual(result.returncode, 2)
        message = json.loads(result.stdout)["message"]
        self.assertIn("verify --repo " + shlex.quote(selector), message)

    def test_checkpoint_identifies_the_task_branch_to_resume_from_a_clone(self):
        self.workspace(); self.remotes("backend")
        worktree = self.base / "task-worktree"
        self.git(self.project / "repos/backend", "worktree", "add", "-q", "-b", "PC-1", str(worktree))
        (worktree / "app.py").write_text("value = 2\n")
        self.git(worktree, "commit", "-qam", "PC-1")
        self.git(worktree, "push", str(self.base / "remotes/backend"), "PC-1")
        selector = "backend=" + str(worktree)
        self.assertEqual(base.run(self.script, "verify", "--repo", selector).returncode, 0)
        self.assertEqual(self.checkpoint("--repo", selector).returncode, 0)
        self.commit()
        clone = self.base / "clone"
        self.git(self.base, "clone", "-q", str(self.project), str(clone))
        self.project = clone; self.script = clone / "scripts/project.py"
        self.assertEqual(self.repos("--apply").returncode, 0)
        checkpoint = json.loads((clone / "docs/tasks/PC-1.json").read_text())
        revision = checkpoint["repository_revisions"]["backend"]
        self.assertEqual(revision["git_branch"], "PC-1")
        checkout = clone / "repos/backend"
        self.assertEqual((checkout / "app.py").read_text(), "value = 1\n")
        self.git(checkout, "switch", "-q", "-c", revision["git_branch"], "origin/" + revision["git_branch"])
        self.assertEqual(self.git(checkout, "rev-parse", "HEAD").stdout.strip(), revision["git_head"])
        self.assertEqual((checkout / "app.py").read_text(), "value = 2\n")
        self.assertEqual(base.run(self.script, "verify", "--repo", "backend").returncode, 0)

    def test_parallel_repositories_keep_results_and_never_revive_old_success(self):
        self.workspace(); self.remotes("backend", "frontend")
        gates = {}
        for name in ("backend", "frontend"):
            commands, *paths = self.blocked_command(name)
            gates[name] = paths
            base.run(self.script, "repo", "--name", name, "--commands", json.dumps(commands), "--apply")
        self.assertEqual(base.run(self.script, "verify").returncode, 0)
        for gate, _, _, _ in gates.values(): gate.touch()
        gates["backend"][3].touch()
        backend = self.start("--repo", "backend"); frontend = self.start("--repo", "frontend")
        # Both must reach their commands concurrently, not under one long workspace lock.
        self.wait_for(gates["backend"][1]); self.wait_for(gates["frontend"][1])
        gates["backend"][2].touch(); backend.communicate(timeout=10)
        self.assertEqual(backend.returncode, 1)
        gates["frontend"][2].touch(); frontend.communicate(timeout=10)
        self.assertEqual(frontend.returncode, 0)
        self.assertEqual(self.states(), {"backend": "failed", "frontend": "passed"})
        self.assertEqual(self.checkpoint("--repo", "backend").returncode, 2)
        self.assertEqual(self.checkpoint("--repo", "frontend").returncode, 0)

    def test_interrupted_failure_blocks_delivery_and_releases_process_lock(self):
        self.single()
        command, gate, ready, release, failure = self.blocked_command("single")
        first = [sys.executable, "-c", f"from pathlib import Path; raise SystemExit(int(Path({str(failure)!r}).exists()))"]
        self.set_commands([first, *command])
        self.assertEqual(base.run(self.script, "verify").returncode, 0)
        gate.touch(); failure.touch()
        process = self.start(); self.wait_for(ready)
        contender = base.run(self.script, "verify")
        self.assertEqual(contender.returncode, 2)
        self.assertIn("holds the local lock", contender.stdout)
        self.assertEqual(self.checkpoint().returncode, 2)
        os.killpg(process.pid, signal.SIGTERM); process.communicate(timeout=5)
        self.assertEqual(self.proof()["status"], "incomplete")
        self.assertEqual(self.checkpoint().returncode, 2)
        release.touch(); failure.unlink()
        self.assertEqual(base.run(self.script, "verify").returncode, 0)
        self.assertEqual(self.checkpoint().returncode, 0)

    def test_github_tracker_is_consistent_in_status_and_hub(self):
        self.script = self.create(tracker="github")
        base.run(self.script, "link", "--repository-url", "https://github.com/org/project.git", "--apply")
        state = json.loads(base.run(self.script, "status").stdout)
        hub = json.loads(base.run(self.script, "hub").stdout)
        self.assertEqual(state["tracker"]["url"], "https://github.com/org/project/issues")
        self.assertEqual(state["tracker"], hub["manifest"]["tracker"])
        self.assertIn(state["tracker"]["url"], hub["markdown"])
        self.assertNotIn("[]", base.run(self.script, "status", "--text").stdout)


class RecoveryTests(base.ProjectFixture):
    def module(self, package=base.PACKAGE):
        with mock.patch.object(sys, "path", [str(package / "scripts"), *sys.path]):
            spec = importlib.util.spec_from_file_location("tested_framework", package / "scripts/framework.py")
            module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        return module

    def interrupt(self, module, action, args):
        write = module.write_atomic
        def fail(path, data):
            if path == self.project / module.STATE:
                raise OSError("simulated failure before final manifest")
            return write(path, data)
        with mock.patch.object(module, "write_atomic", side_effect=fail):
            with self.assertRaises(OSError):
                getattr(module, action)(args, self.project)
        self.assertTrue((self.project / module.PENDING).is_file())

    def interrupted_init(self, adopt=False):
        if adopt:
            self.project.mkdir()
            (self.project / "AGENTS.md").write_text("Preserve original instructions.\n")
            (self.project / "app.py").write_text("value = 42\n")
        module = self.module()
        args = argparse.Namespace(name="Recovery", slug=None, provider="github", tracker="jira", profile="generic",
                                  kind="single", workspace_url=None, adopt=adopt, git=True, apply=True)
        self.interrupt(module, "init", args)
        return module

    def snapshot(self):
        return {p.relative_to(self.project): p.read_bytes() for p in self.project.rglob("*") if p.is_file()}

    def test_new_project_recovers_from_saved_plan_including_git_init(self):
        module = self.interrupted_init()
        before = self.snapshot()
        result = base.run(base.FRAMEWORK, "recover", self.project)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(self.snapshot(), before)
        result = base.run(base.FRAMEWORK, "recover", self.project, "--apply")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(json.loads(result.stdout)["status"], "recovered")
        self.assertTrue((self.project / ".git").is_dir())
        self.assertFalse((self.project / module.PENDING).exists())
        self.assertEqual(base.run(self.project / "scripts/project.py", "doctor").returncode, 0)

    def test_adoption_recovers_without_duplicating_or_losing_original_content(self):
        module = self.interrupted_init(adopt=True)
        result = base.run(base.FRAMEWORK, "init", self.project, "--name", "Recovery", "--adopt", "--apply")
        self.assertEqual(result.returncode, 2)
        self.assertIn("recover", result.stdout)
        result = base.run(base.FRAMEWORK, "recover", self.project, "--apply")
        self.assertEqual(result.returncode, 0, result.stdout)
        text = (self.project / "AGENTS.md").read_text()
        self.assertTrue(text.startswith("Preserve original instructions.\n"))
        self.assertEqual(text.count("project-framework:begin"), 1)
        self.assertEqual((self.project / "app.py").read_text(), "value = 42\n")
        self.assertFalse((self.project / module.PENDING).exists())

    def test_recovery_refuses_all_writes_if_a_user_changed_a_planned_file(self):
        self.interrupted_init(adopt=True)
        path = self.project / "AGENTS.md"
        path.write_text(path.read_text() + "User edit after interruption.\n")
        before = self.snapshot()
        result = base.run(base.FRAMEWORK, "recover", self.project, "--apply")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertEqual(json.loads(result.stdout)["files"], ["AGENTS.md"])
        self.assertEqual(self.snapshot(), before)
        self.assertFalse((self.project / ".project/template-state.json").exists())

    def test_update_recovers_from_its_saved_plan(self):
        self.create(); self.commit()
        newer = self.newer_skill()
        template = newer / "assets/project/common/.project/REVIEW.md"
        template.write_text(template.read_text() + "\nAdditional review criterion.\n")
        module = self.module(newer)
        args = argparse.Namespace(workspace_url=None, keep=[], apply=True)
        self.interrupt(module, "update", args)
        doctor = base.run(self.project / "scripts/project.py", "doctor")
        self.assertEqual(doctor.returncode, 1)
        self.assertFalse(json.loads(doctor.stdout)["framework_ready"])
        result = base.run(base.FRAMEWORK, "recover", self.project, "--apply")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("Additional review criterion.", (self.project / ".project/REVIEW.md").read_text())
        self.assertEqual(base.run(self.project / "scripts/project.py", "doctor").returncode, 0)

    def test_recovery_rejects_paths_outside_the_project(self):
        module = self.interrupted_init()
        path = self.project / module.PENDING
        journal = json.loads(path.read_text())
        journal["files"]["../outside"] = journal["files"].pop("AGENTS.md")
        path.write_text(json.dumps(journal))
        before = self.snapshot()
        result = base.run(base.FRAMEWORK, "recover", self.project, "--apply")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse((self.base / "outside").exists())

    def test_malformed_recovery_journal_reports_an_error_without_writes(self):
        module = self.interrupted_init()
        path = self.project / module.PENDING
        original = json.loads(path.read_text())
        for damaged in ([], {**original, "files": []}, {**original, "files": {"AGENTS.md": []}}):
            with self.subTest(damaged=damaged):
                path.write_text(json.dumps(damaged))
                before = self.snapshot()
                result = base.run(base.FRAMEWORK, "recover", self.project, "--apply")
                self.assertEqual(result.returncode, 2)
                self.assertEqual(json.loads(result.stdout)["status"], "error")
                self.assertEqual(self.snapshot(), before)
