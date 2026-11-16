"""Behaviour that must hold on every platform: half checkouts, interrupted checks, CRLF files, missing python3."""
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import test_framework as base

FRAMEWORK, run = base.FRAMEWORK, base.run
PASS = [[sys.executable, "-c", "print('ok')"]]


class PortabilityTests(base.ProjectFixture):
    def git(self, directory, *argv):
        options = ["-c", "user.name=Test", "-c", "user.email=test@example.invalid", "-c", "protocol.file.allow=always"]
        return subprocess.run(["git", "-C", str(directory), *options, *argv], check=True, capture_output=True, text=True)

    def checkpoint(self, script, status):
        return run(script, "checkpoint", "--task", "APP-1", "--owner", "agent-a", "--summary", "Lavoro",
                   "--status", status, "--apply")

    def sleeper(self, marker):
        """A check that records its own process id outside the project and then hangs."""
        return [[sys.executable, "-c", "import os, sys, time; open(sys.argv[1], 'w').write(str(os.getpid())); time.sleep(60)",
                 str(marker)]]

    def gone(self, pid):
        for _ in range(100):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return True
            time.sleep(.05)
        return False

    def wait_for(self, path):
        for _ in range(400):
            if path.exists() and path.read_text():
                return int(path.read_text())
            time.sleep(.02)
        self.fail("the check did not start")

    def test_work_in_progress_can_be_recorded_in_a_clone_with_an_uninitialized_submodule(self):
        self.create()
        self.set_commands(PASS)
        library = self.base / "library"
        library.mkdir()
        self.git(library, "init", "-q", "-b", "main")
        (library / "value.txt").write_text("x")
        self.git(library, "add", "-A")
        self.git(library, "commit", "-qm", "library")
        self.git(self.project, "submodule", "add", "-q", str(library), "vendor/library")
        self.commit()
        clone = self.base / "clone"
        self.git(self.base, "clone", "-q", str(self.project), str(clone))  # Submodules are not initialized.
        script = clone / "scripts/project.py"
        self.assertEqual(self.checkpoint(script, "in_progress").returncode, 0)
        # Checks still refuse to run against half a checkout, and nothing can be delivered from it.
        result = run(script, "verify")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Uninitialized submodule", json.loads(result.stdout)["message"])
        self.assertEqual(self.checkpoint(script, "review").returncode, 2)

    def test_interrupted_verification_stops_the_checks_it_started(self):
        script = self.create()
        marker = self.base / "check.pid"
        self.set_commands(self.sleeper(marker))
        process = subprocess.Popen([sys.executable, str(script), "verify"], stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        child = self.wait_for(marker)
        process.send_signal(signal.SIGTERM)
        process.communicate(timeout=10)
        self.assertEqual(process.returncode, 143)
        self.assertTrue(self.gone(child), "the check was still running after interruption")
        self.assertEqual(json.loads(run(script, "status").stdout)["verification"], "incomplete")
        self.set_commands(PASS)
        self.assertEqual(run(script, "verify").returncode, 0)  # The lock was released only after the check ended.

    def test_timed_out_check_is_stopped_and_fails_the_run(self):
        script = self.create()
        marker = self.base / "check.pid"
        self.set_commands(self.sleeper(marker))
        path = self.project / ".project/config.json"
        path.write_text(json.dumps({**json.loads(path.read_text()), "command_timeout_seconds": 1}))
        result = run(script, "verify")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertEqual(json.loads(result.stdout)["checks"][0]["error"], "TimeoutExpired")
        self.assertTrue(self.gone(int(marker.read_text())))

    def test_update_accepts_files_checked_out_with_windows_line_endings(self):
        self.create()
        for name in ("AGENTS.md", "scripts/project.py", ".gitignore"):
            path = self.project / name
            path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))  # What Git does with core.autocrlf.
        newer = self.newer_skill()
        template = newer / "assets/project/common/AGENTS.md.tmpl"
        template.write_text(template.read_text() + "- Regola della nuova versione.\n")
        value = json.loads(run(newer / "scripts/framework.py", "update", self.project).stdout)
        self.assertEqual((value["status"], value["files"]), ("plan", ["AGENTS.md"]))
        result = run(newer / "scripts/framework.py", "update", self.project, "--apply")
        self.assertEqual(result.returncode, 0, result.stdout)
        updated = (self.project / "AGENTS.md").read_bytes()
        self.assertIn(b"- Regola della nuova versione.\r\n", updated)
        self.assertNotIn(b"\n", updated.replace(b"\r\n", b""))  # Still CRLF throughout.
        self.assertEqual(json.loads(run(newer / "scripts/framework.py", "update", self.project).stdout)["files"], [])

    def test_managed_section_is_updated_in_an_adopted_file_with_windows_line_endings(self):
        self.project.mkdir()
        (self.project / "AGENTS.md").write_bytes(b"# Regole esistenti\r\n\r\nUsa pytest.\r\n")
        self.assertEqual(run(FRAMEWORK, "init", self.project, "--name", "Legacy", "--adopt", "--apply").returncode, 0)
        path = self.project / "AGENTS.md"
        path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
        newer = self.newer_skill()
        template = newer / "assets/project/common/AGENTS.md.tmpl"
        template.write_text(template.read_text() + "- Regola della nuova versione.\n")
        result = run(newer / "scripts/framework.py", "update", self.project, "--apply")
        self.assertEqual(result.returncode, 0, result.stdout)
        updated = path.read_bytes()
        self.assertTrue(updated.startswith(b"# Regole esistenti\r\n\r\nUsa pytest.\r\n"))
        self.assertIn(b"- Regola della nuova versione.\r\n", updated)

    def test_session_hooks_run_where_only_python_is_installed(self):
        self.create()
        tools = self.base / "only-python"
        tools.mkdir()
        (tools / "python").symlink_to(sys.executable)  # No python3 on PATH, as on a typical Windows setup.
        command = json.loads((self.project / ".claude/settings.json").read_text())["hooks"]["SessionStart"][0]["hooks"][0]["command"]
        payload = {"session_id": "chat-win", "cwd": str(self.project), "hook_event_name": "SessionStart", "source": "startup"}
        result = subprocess.run(command, shell=True, input=json.dumps(payload), text=True, capture_output=True,
                                env={"PATH": str(tools), "CLAUDE_PROJECT_DIR": str(self.project), "HOME": str(self.base)})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["hookSpecificOutput"]["hookEventName"], "SessionStart")

    def test_programs_are_resolved_like_a_shell_would(self):
        self.create()
        spec = importlib.util.spec_from_file_location("fixture_project", self.project / "scripts/project.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertTrue(Path(module.executable(["git", "status"])[0]).is_absolute())
        self.assertEqual(module.executable(["programma-inesistente", "x"]), ["programma-inesistente", "x"])
