# SPDX-FileCopyrightText: 2026 MASH project contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Локальные проверки оптимизации, шаблонов и защитных условий OpenCloud."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
ROLE = ROOT / 'roles/mash/opencloud'


class OpenCloudTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='mash-opencloud-test-')
        self.path = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def optimize(self, variables):
        inventory = self.path / 'vars.yml'
        inventory.write_text(yaml.safe_dump(variables))
        command = [sys.executable, str(ROOT / 'bin/optimize.py'), '--vars-paths=' + str(inventory)]
        for kind, source, dest in [
            ('requirements', 'requirements.yml', 'requirements.yml'),
            ('setup', 'setup.yml', 'setup.yml'),
            ('group-vars', 'group_vars_mash_servers', 'group-vars.yml'),
        ]:
            command += ['--src-' + kind + '-yml-path=' + str(ROOT / 'templates' / source)]
            command += ['--dst-' + kind + '-yml-path=' + str(self.path / dest)]
        result = subprocess.run(command, capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)
        play = yaml.safe_load((self.path / 'setup.yml').read_text())
        self.assertIn('mash/opencloud', [r['role'] for r in play[0]['roles']])
        migration = next(r for r in play[0]['roles'] if r['role'] == 'mash/opencloud_migrations')
        if any(r['role'] == 'galaxy/systemd_service_manager' for r in play[0]['roles']):
            manager = next(r for r in play[0]['roles'] if r['role'] == 'galaxy/systemd_service_manager')
            self.assertGreater(play[0]['roles'].index(migration), play[0]['roles'].index(manager))
        requirements = yaml.safe_load((self.path / 'requirements.yml').read_text())
        self.assertNotIn('opencloud', [r['name'] for r in requirements])
        return yaml.safe_load((self.path / 'group-vars.yml').read_text())

    def render(self, overrides=None, validate=False, hash_seed='random'):
        variables = {
            'opencloud_enabled': True,
            'opencloud_hostname': 'cloud.example.test',
            'opencloud_base_path': '/srv/storage/opencloud',
            'opencloud_required_mount_path': '',
            'opencloud_admin_password': 'AcceptanceOnly-Password-A7!',
            'opencloud_uid': '1000', 'opencloud_gid': '1000',
            'traefik_enabled': False,
            'mash_playbook_reverse_proxy_type': 'none',
            'mash_playbook_reverse_proxyable_services_additional_network': 'traefik',
            'opencloud_container_labels_traefik_enabled': True,
            'opencloud_container_labels_traefik_entrypoints': 'web-secure',
            'opencloud_container_labels_traefik_tls_certResolver': 'default',
        }
        variables.update(overrides or {})
        self.optimize(variables)
        files = [
            ROOT / 'roles/mash/playbook_base/defaults/main.yml',
            ROOT / 'roles/galaxy/systemd_docker_base/defaults/main.yml',
            ROLE / 'defaults/main.yml', self.path / 'group-vars.yml',
        ]
        for dependency in ['eurooffice', 'tika']:
            if any(k.startswith(dependency + '_') for k in variables):
                files.insert(2, ROOT / 'roles/galaxy' / dependency / 'defaults/main.yml')
        tasks = []
        if validate:
            tasks.append({'name': 'Validate fixture', 'ansible.builtin.import_tasks': str(ROLE / 'tasks/validate_config.yml')})
        for template in ['env', 'labels', 'csp.yaml', 'app-registry.yaml', 'systemd/opencloud.service']:
            tasks.append({'name': 'Render ' + template, 'ansible.builtin.template': {
                'src': str(ROLE / 'templates' / (template + '.j2')),
                'dest': str(self.path / Path(template).name), 'mode': '0600',
            }})
        play = [{'name': 'Render OpenCloud fixture', 'hosts': 'localhost', 'gather_facts': False,
                 'vars_files': [str(f) for f in files], 'tasks': tasks}]
        (self.path / 'render.yml').write_text(yaml.safe_dump(play))
        (self.path / 'extra.json').write_text(json.dumps(variables))
        result = subprocess.run([
            'ansible-playbook', '-i', 'localhost,', '-c', 'local',
            str(self.path / 'render.yml'), '-e', '@' + str(self.path / 'extra.json'),
        ], capture_output=True, text=True, cwd=ROOT,
            env={**os.environ, 'ANSIBLE_NOCOLOR': '1', 'PYTHONHASHSEED': hash_seed})
        return result

    def test_disabled_role_survives_optimization_without_external_dependencies(self):
        variables = self.optimize({})
        self.assertIs(variables['opencloud_enabled'], False)
        result = self.render()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        env = (self.path / 'env').read_text()
        self.assertIn('FRONTEND_FULL_TEXT_SEARCH_ENABLED=false', env)
        self.assertNotIn('COLLABORATION_APP_ADDR=', env)

    def test_existing_office_and_tika_are_wired_without_new_public_ports(self):
        result = self.render({
            'eurooffice_enabled': True, 'eurooffice_hostname': 'office.example.test',
            'tika_enabled': True, 'opencloud_required_mount_path': '/srv/storage',
        })
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        env = (self.path / 'env').read_text()
        self.assertIn('COLLABORATION_APP_ADDR=https://office.example.test', env)
        self.assertIn('COLLABORATION_WOPI_SRC=https://cloud.example.test', env)
        self.assertIn('SEARCH_EXTRACTOR_TIKA_TIKA_URL=http://mash-tika:9998', env)
        self.assertIn('OC_INSECURE=false', env)
        self.assertIn('COLLABORATION_APP_INSECURE=false', env)
        unit = (self.path / 'opencloud.service').read_text()
        self.assertIn('RequiresMountsFor=/srv/storage/opencloud/config /srv/storage/opencloud/data', unit)
        self.assertIn('ConditionPathIsMountPoint=/srv/storage', unit)
        self.assertIn('network connect mash-tika mash-opencloud', unit)
        self.assertNotIn(' -p ', unit)
        csp = yaml.safe_load((self.path / 'csp.yaml').read_text())
        self.assertIn('https://office.example.test', csp['directives']['frame-src'])
        registry = yaml.safe_load((self.path / 'app-registry.yaml').read_text())
        editable = [x for x in registry['app_registry']['mimetypes'] if x['allow_creation'] and x['default_app'] == 'EuroOffice']
        self.assertEqual({x['extension'] for x in editable}, {'docx', 'xlsx', 'pptx'})
        self.assertEqual({x['default_app'] for x in editable}, {'EuroOffice'})
        self.assertTrue(next(x for x in registry['app_registry']['mimetypes'] if x['extension'] == 'md')['allow_creation'])

    def test_missing_mount_fails_before_installation(self):
        result = self.render({'opencloud_required_mount_path': str(self.path / 'missing-mount')}, validate=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Verify the required OpenCloud storage filesystem', result.stdout)
        self.assertFalse((self.path / 'env').exists())

    def test_network_order_is_stable_across_ansible_processes(self):
        units = []
        for seed in ['1', '2', '3']:
            result = self.render({'tika_enabled': True}, hash_seed=seed)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            units.append((self.path / 'opencloud.service').read_text())
        self.assertTrue(all(unit == units[0] for unit in units))
        self.assertLess(units[0].index('network connect traefik '), units[0].index('network connect mash-tika '))

    def test_missing_office_endpoint_fails_before_installation(self):
        result = self.render({'opencloud_collaboration_enabled': True, 'opencloud_collaboration_app_url': ''}, validate=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Validate required OpenCloud settings', result.stdout)
        self.assertFalse((self.path / 'env').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
