import contextlib
from datetime import datetime, timedelta, timezone
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from unittest import mock
import test_framework as base


class PreflightTests(base.ProjectFixture):
    def setUp(self):
        super().setUp()
        self.project = self.base / "project con spazi"
        self.script = self.create()
        spec = importlib.util.spec_from_file_location("fixture_preflight", self.project / "scripts/preflight.py")
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.module.ROOT = self.project

    def links(self, **links):
        path = self.project / ".project/config.json"
        config = json.loads(path.read_text())
        config["integrations"].update(links)
        path.write_text(json.dumps(config))

    def check(self, session="chat-a", *options):
        result = base.run(self.script, "preflight", "--session", session, *options)
        return result, json.loads(result.stdout)

    def invoke(self, *argv):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = self.module.main(list(argv))
        return code, json.loads(output.getvalue())

    def record(self, status="verified_read", session="chat-a", service="jira", **extra):
        target = self.module.targets(self.module.configuration())[service]
        args = ["record", "--session", session, "--service", service, "--status", status,
                "--target", json.dumps(target)]
        for key, value in extra.items():
            args.extend(["--" + key, value])
        return self.invoke(*args)

    def test_offline_preflight_reports_missing_targets_without_blocking_local_work(self):
        result, report = self.check()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue(report["ready_for_requested_reads"])
        self.assertEqual(report["services"]["jira"]["status"], "not_configured")
        result, report = self.check("chat-a", "--require", "jira")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertEqual(report["blocked"], ["jira"])

    def test_configured_mcp_target_needs_actual_agent_probe(self):
        self.links(jira_url="https://example.atlassian.net", jira_project_key="APP")
        result, report = self.check()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(report["agent_checks"], ["jira"])
        self.assertFalse(report["services"]["jira"]["read_access"])

    def test_same_session_read_evidence_unblocks_required_dependency(self):
        self.links(jira_url="https://example.atlassian.net", jira_project_key="APP")
        self.check("chat-a", "--require", "jira")
        code, report = self.record(identity="account-id", tool="get_project", evidence="Project APP ID 10001 read")
        self.assertEqual(code, 0)
        self.assertTrue(report["ready_for_requested_reads"])
        result, report = self.check("chat-a", "--require", "jira")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(report["services"]["jira"]["write_access"], "unverified")

    def test_new_chat_cannot_reuse_old_chat_authentication_evidence(self):
        self.links(jira_url="https://example.atlassian.net", jira_project_key="APP")
        self.check()
        self.record(identity="account-id", tool="get_project", evidence="Project APP read")
        result, report = self.check("chat-b", "--require", "jira")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(report["services"]["jira"]["status"], "agent_check_required")

    def test_refresh_discards_same_session_evidence_after_account_change(self):
        self.links(jira_url="https://example.atlassian.net", jira_project_key="APP")
        self.check()
        self.record(identity="old-account", tool="get_project", evidence="Project APP read")
        result, report = self.check("chat-a", "--refresh", "--require", "jira")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(report["services"]["jira"]["status"], "agent_check_required")

    def test_changed_target_invalidates_evidence_and_recording_against_old_scope(self):
        self.links(jira_url="https://example.atlassian.net", jira_project_key="APP")
        self.check()
        self.record(identity="account-id", tool="get_project", evidence="Project APP read")
        self.links(jira_project_key="OTHER")
        with self.assertRaises(ValueError):
            self.record(identity="account-id", tool="get_project", evidence="Project APP read")
        result, report = self.check("chat-a", "--require", "jira")
        self.assertEqual(result.returncode, 2)

    def test_expired_or_future_dated_evidence_is_not_reused(self):
        self.links(jira_url="https://example.atlassian.net", jira_project_key="APP")
        for offset in [-601, 30]:
            self.check()
            self.record(identity="account-id", tool="get_project", evidence="Project APP read")
            path = self.module.session_path("chat-a")
            data = json.loads(path.read_text())
            data["services"]["jira"]["checked_at"] = (datetime.now(timezone.utc) + timedelta(seconds=offset)).isoformat()
            path.write_text(json.dumps(data))
            result, report = self.check("chat-a", "--require", "jira")
            self.assertEqual(result.returncode, 2)

    def test_failed_recheck_replaces_previous_success(self):
        self.links(jira_url="https://example.atlassian.net", jira_project_key="APP")
        self.check("chat-a", "--require", "jira")
        self.record(identity="account-id", tool="get_project", evidence="Project APP read")
        self.record(status="auth_required", tool="get_project", evidence="401 from current read")
        result, report = self.check("chat-a", "--require", "jira")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(report["services"]["jira"]["status"], "auth_required")

    def test_record_rejects_unsubstantiated_success_wrong_target_and_credentials(self):
        self.links(jira_url="https://example.atlassian.net", jira_project_key="APP")
        self.check()
        with self.assertRaises(ValueError):
            self.record()
        with self.assertRaises(ValueError):
            self.record(identity="account-id", tool="get_project", evidence="Authorization: Bearer SECRET")
        with self.assertRaises(ValueError):
            self.invoke("record", "--session", "chat-a", "--service", "jira", "--status", "verified_read",
                        "--target", '{"url":"https://wrong.atlassian.net","key":"APP"}',
                        "--identity", "account-id", "--tool", "get_project", "--evidence", "Read")

    def test_github_cli_performs_identity_and_exact_repository_gets_without_write_probe(self):
        self.links(repository_url="https://github.com/example/demo")
        calls = []
        def command(argv):
            calls.append(argv)
            if argv[0] == "gh" and "user" in argv:
                return 0, "demo-user\n", ""
            if argv[0] == "gh":
                return 0, json.dumps({"name": "example/demo", "permissions": {"push": True}}), ""
            return 0, "v24.22.2", ""
        with mock.patch.object(self.module.shutil, "which", return_value="/mock/tool"), mock.patch.object(self.module, "run", side_effect=command):
            code, report = self.invoke("check", "--session", "chat-a", "--live", "--require", "repository")
        self.assertEqual(code, 0)
        item = report["services"]["repository"]
        self.assertEqual(item["source"], "gh_api")
        self.assertEqual(item["write_access"], "reported_allowed")
        self.assertEqual(len([x for x in calls if x[0] == "gh"]), 2)
        self.assertTrue(all(x[1] == "api" for x in calls if x[0] == "gh"))

    def test_github_cli_errors_are_distinguished_and_raw_output_is_redacted(self):
        self.links(repository_url="https://github.com/example/demo")
        for message, expected in [("HTTP 401 bad credentials", "auth_required"),
                                  ("HTTP 403 forbidden", "access_denied"),
                                  ("HTTP 404 not found", "not_found_or_denied"),
                                  ("cannot resolve host", "network_error"),
                                  ("HTTP 429 rate limit", "unverified")]:
            with self.subTest(expected=expected), mock.patch.object(self.module.shutil, "which", return_value="/mock/tool"), \
                    mock.patch.object(self.module, "run", return_value=(1, "", message + " Bearer PRIVATE")):
                code, report = self.invoke("check", "--session", "chat-a", "--live", "--require", "repository")
            self.assertEqual(code, 2)
            self.assertEqual(report["services"]["repository"]["status"], expected)
            self.assertNotIn("PRIVATE", json.dumps(report))

    def test_unknown_github_host_never_receives_cli_credentials(self):
        self.links(repository_url="https://enterprise.example/example/demo")
        with mock.patch.object(self.module, "run", return_value=(0, "v24.22.2", "")) as calls:
            code, report = self.invoke("check", "--session", "chat-a", "--live", "--require", "repository")
        self.assertEqual(code, 2)
        self.assertEqual(report["services"]["repository"]["status"], "agent_check_required")
        self.assertFalse(any(call.args[0][0] == "gh" for call in calls.call_args_list))

    def test_subprocess_checks_have_timeout_and_disable_interactive_prompts(self):
        with mock.patch.object(self.module.subprocess, "run") as command:
            command.return_value = subprocess.CompletedProcess([], 0, "ok", "")
            self.module.run(["gh", "api", "user"])
            self.assertEqual(command.call_args.kwargs["timeout"], 8)
            self.assertEqual(command.call_args.kwargs["env"]["GH_PROMPT_DISABLED"], "1")

    def test_both_session_start_hooks_produce_context_and_separate_reports(self):
        script = self.project / "scripts/preflight.py"
        for client in ("codex", "claude"):
            payload = {"session_id": "new-" + client, "cwd": str(self.project), "hook_event_name": "SessionStart", "source": "startup"}
            result = subprocess.run([sys.executable, str(script), "hook", "--client", client],
                                    input=json.dumps(payload), text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            output = json.loads(result.stdout)["hookSpecificOutput"]
            self.assertEqual(output["hookEventName"], "SessionStart")
            self.assertIn("new-" + client, output["additionalContext"])
            self.assertIn("Project Framework: session preflight", output["additionalContext"])
            self.assertTrue(self.module.session_path("new-" + client).is_file())

    def test_session_paths_and_config_urls_cannot_escape_or_expose_secrets(self):
        with self.assertRaises(ValueError):
            self.module.session_path("../escape")
        self.links(jira_url="https://user:SECRET@example.atlassian.net", jira_project_key="APP")
        result = base.run(self.script, "preflight", "--session", "chat-a", "--live")
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("SECRET", result.stdout + result.stderr)

    def test_reports_are_ignored_by_git_and_do_not_modify_project_configuration(self):
        before = (self.project / ".project/config.json").read_bytes()
        self.check()
        path = self.module.session_path("chat-a")
        result = subprocess.run(["git", "-C", str(self.project), "check-ignore", str(path)], capture_output=True)
        self.assertEqual(result.returncode, 0)
        self.assertEqual((self.project / ".project/config.json").read_bytes(), before)

    def test_shared_hook_checks_active_worktree_instead_of_main_checkout(self):
        other = self.base / "worktree con spazi"
        result = base.run(base.FRAMEWORK, "init", other, "--name", "Worktree", "--apply", "--git")
        self.assertEqual(result.returncode, 0, result.stdout)
        payload = {"session_id": "worktree-chat", "cwd": str(other), "hook_event_name": "SessionStart", "source": "startup"}
        result = subprocess.run([sys.executable, str(self.project / "scripts/preflight.py"), "hook", "--client", "claude"],
                                input=json.dumps(payload), text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(list((other / ".project/local/preflight").glob("*.json")))
        self.assertFalse((self.project / ".project/local/preflight").exists())

    def test_configured_hook_commands_work_from_subdirectories_with_spaces(self):
        folder = self.project / "cartella con spazi"
        folder.mkdir()
        configs = [(".codex/hooks.json", "codex"), (".claude/settings.json", "claude")]
        for relative, client in configs:
            settings = json.loads((self.project / relative).read_text())
            command = settings["hooks"]["SessionStart"][0]["hooks"][0]["command"]
            payload = {"session_id": "command-" + client, "cwd": str(folder), "hook_event_name": "SessionStart", "source": "startup"}
            import os
            result = subprocess.run(command, shell=True, cwd=folder, input=json.dumps(payload), text=True, capture_output=True,
                                    env={**os.environ, "CLAUDE_PROJECT_DIR": str(self.project)})
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(json.loads(result.stdout)["hookSpecificOutput"]["hookEventName"], "SessionStart")

    def test_command_line_errors_name_the_problem_without_echoing_input(self):
        self.links(jira_url="https://example.atlassian.net", jira_project_key="APP")
        self.check()
        direct = self.project / "scripts/preflight.py"
        common = ["record", "--session", "chat-a", "--service", "jira", "--status", "verified_read",
                  "--identity", "account-id", "--tool", "get_project", "--evidence", "Read"]
        result = base.run(direct, *common, "--target", '{"url":"https://wrong.atlassian.net","key":"APP"}')
        self.assertEqual(result.returncode, 2)
        self.assertIn("configured target", json.loads(result.stdout)["message"])
        result = base.run(direct, *common, "--target", "non-json SECRET-TOKEN")
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("SECRET-TOKEN", result.stdout + result.stderr)
        # A failure that was not anticipated stays generic on both entry points.
        (self.project / ".project/config.json").write_text('{"schema_version": 1, "token": "SECRET-TOKEN"')
        for result in (base.run(self.script, "preflight", "--session", "chat-a"),
                       base.run(direct, "check", "--session", "chat-a")):
            self.assertEqual(result.returncode, 2)
            self.assertIn("Preflight incomplete", json.loads(result.stdout)["message"])
            self.assertNotIn("SECRET-TOKEN", result.stdout + result.stderr)

    def test_reports_left_by_old_chats_are_removed(self):
        self.check("chat-old")
        old = self.module.session_path("chat-old")
        unrelated = old.parent / "notes.json"
        unrelated.write_text("{}")
        stale = time.time() - 2 * 86400
        for path in (old, unrelated):
            os.utime(path, (stale, stale))
        self.check("chat-new")
        self.assertFalse(old.exists())
        self.assertTrue(unrelated.exists())
        self.assertTrue(self.module.session_path("chat-new").is_file())
