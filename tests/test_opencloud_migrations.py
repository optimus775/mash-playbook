# SPDX-FileCopyrightText: 2026 MASH project contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Проверки выполнения и повторного запуска миграции без настоящего Docker."""

import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

import jinja2

ROOT = Path(__file__).resolve().parents[1]


class SearchMigrationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='opencloud migration ')
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.marker = self.path / 'search-v5.done'
        self.counter = self.path / 'calls'
        journal = self.path / 'journalctl'
        journal.write_text('''#!/bin/sh
if [ "${TEST_RESULT:-success}" = extraction_failure ]; then
    echo '{"service":"search","level":"error","message":"failed to extract resource content"}'
fi
''')
        journal.chmod(0o755)
        fake = self.path / 'docker.py'
        fake.write_text('''import json, os, sys, time
from pathlib import Path
if sys.argv[1] == 'inspect':
    print(os.environ.get('TEST_IMAGE', 'docker.io/opencloudeu/opencloud-rolling:8.0.1'))
else:
    (Path(__file__).parent / 'arguments.json').write_text(json.dumps(sys.argv[1:]))
    counter = Path(__file__).parent / 'calls'
    counter.write_text(str(int(counter.read_text()) + 1) if counter.exists() else '1')
    time.sleep(0.15)
    mode = os.environ.get('TEST_RESULT', 'success')
    if mode == 'partial': print('[1/2] failed to index space test: unavailable')
    elif mode == 'cancelled': print('aborted, indexing has been stopped')
    elif mode == 'failure': sys.exit(1)
    else: print('[1/1] indexed space test in 1s')
''')
        environment = jinja2.Environment()
        environment.filters['quote'] = shlex.quote
        template = environment.from_string((ROOT / 'roles/mash/opencloud/templates/search-migration.sh.j2').read_text())
        self.script = self.path / 'run.sh'
        self.script.write_text(template.render(
            opencloud_migrations_path=str(self.path), opencloud_search_index_generation='v5',
            devture_systemd_docker_base_host_command_docker='/usr/bin/env python3 ' + shlex.quote(str(fake)),
            opencloud_identifier='mash-opencloud', opencloud_version='8.0.1',
            opencloud_container_image='docker.io/opencloudeu/opencloud-rolling:8.0.1',
            opencloud_search_reindex_insecure=True,
            opencloud_search_reindex_concurrency=1,
        ))

    def run_migration(self, **environment):
        return subprocess.run(['/bin/sh', str(self.script)], capture_output=True, text=True,
                              env={**os.environ, 'PATH': str(self.path) + os.pathsep + os.environ['PATH'], **environment})

    def test_success_is_persisted_and_second_run_skips_rescan(self):
        first = self.run_migration()
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertTrue(self.marker.exists())
        import json
        args = json.loads((self.path / 'arguments.json').read_text())
        self.assertEqual(args[args.index('--concurrency') + 1], '1')
        marker = self.marker.stat().st_mtime_ns
        second = self.run_migration()
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(self.counter.read_text(), '1')
        self.assertEqual(self.marker.stat().st_mtime_ns, marker)

    def test_partial_errors_and_cancellation_do_not_record_success(self):
        for mode in ['partial', 'cancelled', 'failure', 'extraction_failure']:
            with self.subTest(mode=mode):
                result = self.run_migration(TEST_RESULT=mode)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.marker.exists())
        self.assertEqual(self.run_migration().returncode, 0)
        self.assertTrue(self.marker.exists())

    def test_previous_container_image_cannot_be_migrated(self):
        result = self.run_migration(TEST_IMAGE='docker.io/opencloudeu/opencloud:7.2.4')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.marker.exists())
        self.assertFalse(self.counter.exists())

    def test_concurrent_invocations_reindex_only_once(self):
        processes = [subprocess.Popen(['/bin/sh', str(self.script)], stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE, text=True,
                                      env={**os.environ, 'PATH': str(self.path) + os.pathsep + os.environ['PATH']}) for _ in range(2)]
        for process in processes:
            _, stderr = process.communicate(timeout=15)
            self.assertEqual(process.returncode, 0, stderr)
        self.assertEqual(self.counter.read_text(), '1')


if __name__ == '__main__':
    unittest.main(verbosity=2)
