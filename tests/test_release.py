"""Release behavior: localization, publication evidence, preservation and concurrent metadata."""
import errno
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from unittest import mock

import test_framework as base


class ReleaseTests(base.ProjectFixture):
    def module(self):
        spec = importlib.util.spec_from_file_location('release_project', self.project / 'scripts/project.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_language_requires_a_choice_and_preview_does_not_save_it(self):
        script = self.create()
        path = self.project / '.project/config.json'
        original = path.read_bytes()
        self.assertEqual(json.loads(base.run(script, 'language').stdout)['status'], 'confirmation_required')
        self.assertFalse(json.loads(base.run(script, 'hub').stdout)['language_confirmed'])
        self.assertIn('confirm the language', base.run(script, 'hub', '--text').stdout)
        result = base.run(script, 'language', '--set', '日本語')
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(json.loads(result.stdout)['content_language'], '日本語')
        self.assertEqual(path.read_bytes(), original)
        for invalid in ('', ' ', 'English\nFrench', 'x' * 81):
            self.assertEqual(base.run(script, 'language', '--set', invalid, '--apply').returncode, 2)
        self.assertEqual(path.read_bytes(), original)

    def test_confirmed_language_survives_update_and_clone_without_translating_user_content(self):
        script = self.create()
        original = 'Decisione del cliente: conservare questo testo.\n'
        document = self.project / 'docs/PRODUCT.md'
        document.write_text(original)
        for chosen in ('Italiano', 'English', '日本語', 'العربية'):
            result = base.run(script, 'language', '--set', chosen, '--apply')
            self.assertEqual(result.returncode, 0, result.stdout)
            value = json.loads(base.run(script, 'hub').stdout)
            self.assertEqual(value['manifest']['content_language'], chosen)
            self.assertTrue(value['language_confirmed'])
            self.assertEqual(value['draft_language'], 'English')
        self.assertEqual(base.run(base.FRAMEWORK, 'update', self.project, '--apply').returncode, 0)
        self.assertEqual(document.read_text(), original)
        self.commit()
        clone = self.base / 'clone'
        subprocess.run(['git', 'clone', '-q', str(self.project), str(clone)], check=True)
        value = json.loads(base.run(clone / 'scripts/project.py', 'language').stdout)
        self.assertEqual(value['content_language'], 'العربية')
        self.assertEqual((clone / 'docs/PRODUCT.md').read_text(), original)
        self.assertFalse((clone / '.project/local').exists())

    def test_update_explains_managed_language_and_preserves_authored_content(self):
        starter = self.newer_skill()
        (starter / 'assets/project/common/.project/WORKFLOW.md').write_text('# Regole operative\nIstruzioni distribuite.\n')
        result = base.run(starter / 'scripts/framework.py', 'init', self.project, '--name', 'Example', '--apply')
        self.assertEqual(result.returncode, 0, result.stdout)
        script = self.project / 'scripts/project.py'
        self.assertEqual(base.run(script, 'language', '--set', 'Italiano', '--apply').returncode, 0)
        document = self.project / 'docs/PRODUCT.md'
        document.write_text('Decisioni e contenuti del progetto.\n')
        config = (self.project / '.project/config.json').read_bytes()
        before = {p.relative_to(self.project).as_posix(): p.read_bytes()
                  for p in self.project.rglob('*') if p.is_file()}
        preview = base.run(base.FRAMEWORK, 'update', self.project)
        self.assertEqual(preview.returncode, 0, preview.stdout)
        report = json.loads(preview.stdout)
        self.assertIn('.project/WORKFLOW.md', report['files'])
        self.assertTrue(any('English' in warning for warning in report['warnings']))
        self.assertEqual(before, {p.relative_to(self.project).as_posix(): p.read_bytes()
                                 for p in self.project.rglob('*') if p.is_file()})
        applied = base.run(base.FRAMEWORK, 'update', self.project, '--apply')
        self.assertEqual(applied.returncode, 0, applied.stdout)
        self.assertTrue((self.project / '.project/WORKFLOW.md').read_text().startswith('# Working protocol'))
        self.assertEqual((self.project / '.project/config.json').read_bytes(), config)
        self.assertEqual(document.read_text(), 'Decisioni e contenuti del progetto.\n')
        self.assertEqual(json.loads(base.run(script, 'language').stdout)['content_language'], 'Italiano')

    def test_old_config_has_pending_language_and_invalid_types_are_rejected(self):
        script = self.create()
        path = self.project / '.project/config.json'
        value = json.loads(path.read_text())
        del value['content_language']
        path.write_text(json.dumps(value))
        self.assertEqual(json.loads(base.run(script, 'language').stdout)['status'], 'confirmation_required')
        for invalid in (None, True, [], 'English\nFrench'):
            path.write_text(json.dumps({**value, 'content_language': invalid}))
            self.assertEqual(base.run(script, 'doctor').returncode, 2)

    def published_document(self):
        script = self.create()
        (self.project / 'docs/contract.txt').write_text('contract v1\n')
        result = base.run(script, 'doc', '--id', 'api', '--type', 'api', '--source', 'docs/contract.txt',
                          '--page-url', 'https://example.invalid/pages/1', '--published', '--apply')
        self.assertEqual(result.returncode, 0, result.stdout)
        return script

    def test_changing_published_page_clears_evidence_until_reattested(self):
        script = self.published_document()
        result = base.run(script, 'doc', '--id', 'api', '--page-url', 'https://example.invalid/pages/2', '--apply')
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(json.loads(base.run(script, 'docs').stdout)['documents'][0]['state'], 'never_published')
        self.assertEqual(base.run(script, 'doc', '--id', 'api', '--published', '--apply').returncode, 0)
        self.assertEqual(json.loads(base.run(script, 'docs').stdout)['documents'][0]['state'], 'current')

    def test_changing_source_path_with_identical_bytes_clears_evidence(self):
        script = self.published_document()
        shutil.copyfile(self.project / 'docs/contract.txt', self.project / 'docs/other.txt')
        result = base.run(script, 'doc', '--id', 'api', '--source', 'docs/other.txt', '--apply')
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(json.loads(base.run(script, 'docs').stdout)['documents'][0]['state'], 'never_published')

    def test_same_publication_target_or_title_edit_keeps_evidence(self):
        script = self.published_document()
        result = base.run(script, 'doc', '--id', 'api', '--source', 'docs/contract.txt',
                          '--page-url', 'https://example.invalid/pages/1/', '--title', 'API contract', '--apply')
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(json.loads(base.run(script, 'docs').stdout)['documents'][0]['state'], 'current')

    def test_update_preserves_exact_bytes_outside_a_mixed_newline_managed_section(self):
        self.project.mkdir()
        prefix = b'# Existing rules\r\n\nPreserve these bytes.\r\n'
        path = self.project / 'AGENTS.md'
        path.write_bytes(prefix)
        result = base.run(base.FRAMEWORK, 'init', self.project, '--name', 'Legacy', '--adopt', '--apply')
        self.assertEqual(result.returncode, 0, result.stdout)
        suffix = b'\nHuman addition.\r\n'
        path.write_bytes(path.read_bytes() + suffix)
        before = path.read_bytes()
        newer = self.newer_skill()
        template = newer / 'assets/project/common/AGENTS.md.tmpl'
        template.write_text(template.read_text() + '\nNew managed rule.\n')
        result = base.run(newer / 'scripts/framework.py', 'update', self.project, '--apply')
        self.assertEqual(result.returncode, 0, result.stdout)
        after = path.read_bytes()
        self.assertEqual(after.split(b'<!-- project-framework:begin -->')[0], before.split(b'<!-- project-framework:begin -->')[0])
        self.assertEqual(after.split(b'<!-- project-framework:end -->')[1], before.split(b'<!-- project-framework:end -->')[1])
        self.assertIn(b'New managed rule.', after)

    def test_adoption_rejects_existing_crlf_markers_without_manifest(self):
        self.project.mkdir()
        path = self.project / 'AGENTS.md'
        original = b'<!-- project-framework:begin -->\r\nExisting\r\n<!-- project-framework:end -->\r\n'
        path.write_bytes(original)
        result = base.run(base.FRAMEWORK, 'init', self.project, '--name', 'Legacy', '--adopt', '--apply')
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertEqual(path.read_bytes(), original)
        self.assertFalse((self.project / '.project/config.json').exists())

    def test_lock_io_errors_are_not_retried_as_contention(self):
        self.create()
        module = self.module()
        if not module.fcntl:
            self.skipTest('POSIX locking error simulation')
        with mock.patch.object(module.fcntl, 'flock', side_effect=OSError(errno.ENOSYS, 'unsupported')), \
             mock.patch.object(module.time, 'sleep', side_effect=AssertionError('unexpected retry')):
            with self.assertRaises(OSError) as raised:
                with module.local_lock('unsupported', wait=True):
                    self.fail('lock acquired')
        self.assertEqual(raised.exception.errno, errno.ENOSYS)

    def test_waiting_for_metadata_lock_has_a_deadline(self):
        self.create()
        module = self.module()
        if not module.fcntl:
            self.skipTest('POSIX contention simulation')
        with mock.patch.object(module.fcntl, 'flock', side_effect=BlockingIOError(errno.EAGAIN, 'busy')), \
             mock.patch.object(module.time, 'monotonic', side_effect=[0, 31]):
            with self.assertRaises(ValueError):
                with module.local_lock('busy', wait=True):
                    self.fail('lock acquired')

    def slow_cli(self):
        """Widen the read/write window in a temporary fixture to expose lost updates deterministically."""
        wrapper = self.base / 'slow_cli.py'
        wrapper.write_text('import importlib.util, sys, time\n'
                           f'spec=importlib.util.spec_from_file_location("fixture", {str(self.project / "scripts/project.py")!r})\n'
                           'm=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n'
                           'original=m.config\n'
                           'def slow():\n    value=original(); time.sleep(0.5); return value\n'
                           'm.config=slow\n'
                           'try:\n    sys.exit(m.main())\n'
                           'except ValueError as e:\n    print(str(e)); sys.exit(2)\n')
        return wrapper

    def concurrent(self, wrapper, arguments):
        processes = [subprocess.Popen([sys.executable, str(wrapper), *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                      text=True, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}) for args in arguments]
        outputs = [process.communicate(timeout=15) for process in processes]
        return processes, outputs

    def test_parallel_config_updates_preserve_both_repository_registrations(self):
        result = base.run(base.FRAMEWORK, 'init', self.project, '--name', 'Workspace', '--kind', 'workspace', '--apply')
        self.assertEqual(result.returncode, 0, result.stdout)
        processes, outputs = self.concurrent(self.slow_cli(), [['repo', '--name', name, '--apply'] for name in ('frontend', 'backend')])
        self.assertEqual([p.returncode for p in processes], [0, 0], outputs)
        value = json.loads((self.project / '.project/config.json').read_text())
        self.assertEqual(sorted(entry['name'] for entry in value['repositories']), ['backend', 'frontend'])

    def test_parallel_checkpoint_claims_do_not_overwrite_an_active_owner(self):
        self.create()
        args = ['checkpoint', '--task', 'APP-1', '--summary', 'Work', '--apply', '--owner']
        processes, outputs = self.concurrent(self.slow_cli(), [[*args, owner] for owner in ('agent-a', 'agent-b')])
        self.assertEqual(sorted(p.returncode for p in processes), [0, 2], outputs)
        winner = next(owner for owner, p in zip(('agent-a', 'agent-b'), processes) if p.returncode == 0)
        checkpoint = json.loads((self.project / 'docs/tasks/APP-1.json').read_text())
        self.assertEqual(checkpoint['owner'], winner)

    def test_complete_installation_and_generated_projects_keep_template_license(self):
        destination = self.base / 'installation'
        result = base.run(base.INSTALL, '--base', destination, '--client', 'both', '--apply')
        self.assertEqual(result.returncode, 0, result.stdout)
        expected = (base.PACKAGE / 'LICENSE').read_bytes()
        for path in json.loads(result.stdout)['paths']:
            self.assertEqual((Path(path) / 'LICENSE').read_bytes(), expected)
            self.assertFalse((Path(path) / 'tests').exists())
            self.assertFalse(list(Path(path).rglob('.DS_Store')))
        for kind in ('single', 'workspace', 'component'):
            target = self.base / kind
            result = base.run(base.FRAMEWORK, 'init', target, '--name', 'Licensed', '--kind', kind, '--apply')
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertEqual((target / '.project/LICENSE').read_bytes(), expected)

    def test_checkpoint_before_first_commit_warns_then_records_recoverable_revision(self):
        script = self.create()
        args = ['checkpoint', '--task', 'APP-1', '--owner', 'agent-a', '--summary', 'Initial work', '--apply']
        before = json.loads(base.run(script, *args).stdout)
        self.assertIsNone(before['checkpoint']['revision']['git_head'])
        self.assertTrue(before['warnings'])
        self.commit()
        after = json.loads(base.run(script, *args).stdout)
        head = subprocess.check_output(['git', '-C', str(self.project), 'rev-parse', 'HEAD'], text=True).strip()
        self.assertEqual(after['checkpoint']['revision']['git_head'], head)
        self.assertEqual(after['warnings'], [])
