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
        self.config = self.path / 'ansible.cfg'
        self.config.write_text('[defaults]\nroles_path = ' + str(ROOT / 'roles') + '\n')

    def ansible_environment(self, **extra):
        return {**os.environ, 'ANSIBLE_CONFIG': str(self.config), 'ANSIBLE_NOCOLOR': '1',
                'ANSIBLE_LOG_PATH': str(self.path / 'ansible.log'), **extra}

    def optimize(self, variables, all_components=False):
        inventory = self.path / 'inventory'
        host_vars = inventory / 'host_vars' / 'test'
        host_vars.mkdir(parents=True, exist_ok=True)
        (host_vars / 'vars.yml').write_text(yaml.safe_dump(variables))
        command = [
            sys.executable, str(ROOT / 'bin/optimize.py'),
            '--components-path=' + str(ROOT / 'components'),
            '--inventory-path=' + str(inventory), '--playbook-path=' + str(self.path),
            '--dst-requirements-yml-path=' + str(self.path / 'requirements.yml'),
            '--dst-setup-yml-path=' + str(self.path / 'setup.yml'),
            '--dst-group-vars-path=' + str(self.path / 'generated-group-vars'),
        ]
        if all_components:
            command.append('--all-components')
        result = subprocess.run(command, capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)
        requirements = yaml.safe_load((self.path / 'requirements.yml').read_text())
        self.assertNotIn('opencloud', [r['name'] for r in requirements])
        self.assertNotIn('opencloud_migrations', [r['name'] for r in requirements])
        group_vars = {}
        for path in sorted((self.path / 'generated-group-vars').rglob('*.yml')):
            group_vars.update(yaml.safe_load(path.read_text()) or {})
        (self.path / 'group-vars.yml').write_text(yaml.safe_dump(group_vars))
        return group_vars

    def setup_roles(self):
        return yaml.safe_load((self.path / 'setup.yml').read_text())[0]['roles']

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
        }
        variables.update(overrides or {})
        self.optimize(variables)
        # Load defaults just as the generated playbook's roles do, including shared services.
        files = [ROOT / 'roles' / entry['role'] / 'defaults/main.yml' for entry in self.setup_roles()]
        files = [path for path in files if path.is_file()] + [self.path / 'group-vars.yml']
        tasks = []
        if validate:
            tasks.append({'name': 'Validate fixture', 'ansible.builtin.import_tasks': str(ROLE / 'tasks/validate_config.yml')})
        for template in ['env', 'labels', 'csp.yaml', 'app-registry.yaml', 'systemd/opencloud.service']:
            tasks.append({'name': 'Render ' + template, 'ansible.builtin.template': {
                'src': str(ROLE / 'templates' / (template + '.j2')),
                'dest': str(self.path / Path(template).name), 'mode': '0600',
            }})
        tasks.append({'name': 'Render managed OpenCloud service registration', 'ansible.builtin.copy': {
            'content': "{{ devture_systemd_service_manager_services_list_auto | selectattr('groups', 'contains', 'opencloud') | list | to_json }}",
            'dest': str(self.path / 'managed-services.json'), 'mode': '0600',
        }})
        play = [{'name': 'Render OpenCloud fixture', 'hosts': 'localhost', 'gather_facts': False,
                 'vars_files': [str(f) for f in files], 'tasks': tasks}]
        (self.path / 'render.yml').write_text(yaml.safe_dump(play))
        (self.path / 'extra.json').write_text(json.dumps(variables))
        result = subprocess.run([
            'ansible-playbook', '-i', 'localhost,', '-c', 'local',
            str(self.path / 'render.yml'), '-e', '@' + str(self.path / 'extra.json'),
        ], capture_output=True, text=True, cwd=ROOT,
            env=self.ansible_environment(PYTHONHASHSEED=hash_seed))
        return result

    def test_unused_opencloud_is_omitted_from_optimized_playbook(self):
        variables = self.optimize({})
        self.assertNotIn('opencloud_enabled', variables)
        self.assertNotIn('mash/opencloud', [r['role'] for r in self.setup_roles()])
        self.assertNotIn('mash/opencloud_migrations', [r['role'] for r in self.setup_roles()])

    def test_disabled_role_remains_available_for_uninstallation(self):
        variables = self.optimize({'opencloud_enabled': False})
        self.assertIs(variables['opencloud_enabled'], False)
        self.assertIn('mash/opencloud', [r['role'] for r in self.setup_roles()])
        result = self.render({'opencloud_enabled': False})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads((self.path / 'managed-services.json').read_text()), [])

    def test_opencloud_without_optional_dependencies(self):
        result = self.render()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        env = (self.path / 'env').read_text()
        self.assertIn('FRONTEND_FULL_TEXT_SEARCH_ENABLED=false', env)
        self.assertNotIn('COLLABORATION_APP_ADDR=', env)
        self.assertEqual(json.loads((self.path / 'managed-services.json').read_text()), [{
            'name': 'mash-opencloud.service', 'priority': 2200,
            'restart_necessary': False, 'groups': ['mash', 'opencloud'],
        }])

    def test_local_roles_and_migration_order_in_optimized_and_full_playbooks(self):
        for all_components in [False, True]:
            with self.subTest(all_components=all_components):
                self.optimize({'opencloud_enabled': True}, all_components=all_components)
                roles = [r['role'] for r in self.setup_roles()]
                self.assertEqual(roles.count('mash/opencloud'), 1)
                self.assertEqual(roles.count('mash/opencloud_migrations'), 1)
                self.assertLess(roles.index('mash/opencloud'), roles.index('galaxy/systemd_service_manager'))
                self.assertGreater(roles.index('mash/opencloud_migrations'), roles.index('galaxy/systemd_service_manager'))
                migration = next(r for r in self.setup_roles() if r['role'] == 'mash/opencloud_migrations')
                self.assertEqual(migration['tags'], ['never', 'migrate-opencloud'])

    def test_optional_wiring_tracks_components_in_use(self):
        self.optimize({'opencloud_enabled': True})
        wiring = self.path / 'generated-group-vars' / 'opencloud' / 'with'
        self.assertFalse(wiring.exists())
        variables = {'opencloud_enabled': True, 'mash_playbook_reverse_proxy_type': 'playbook-managed-traefik', **{
            dependency + '_enabled': True for dependency in ['traefik', 'eurooffice', 'tika', 'exim_relay']
        }}
        self.optimize(variables)
        self.assertEqual({p.name for p in wiring.glob('*.yml')},
                         {'traefik.yml', 'eurooffice.yml', 'tika.yml', 'exim_relay.yml'})
        self.optimize({'opencloud_enabled': True})
        self.assertFalse(wiring.exists())

    def test_search_migration_requires_its_explicit_tag(self):
        self.optimize({'opencloud_enabled': True})
        setup = yaml.safe_load((self.path / 'setup.yml').read_text())
        migration = next(r for r in setup[0]['roles'] if r['role'] == 'mash/opencloud_migrations')
        play = [{
            'name': 'Check OpenCloud migration selection',
            'hosts': 'localhost', 'gather_facts': False,
            'vars': {
                'opencloud_enabled': True,
                'opencloud_version': '8.0.1',
                'opencloud_search_index_generation': 'v5',
                'opencloud_migrations_path': str(self.path / 'missing-migration-state'),
            },
            'roles': [migration],
        }]
        playbook = self.path / 'migration-selection.yml'
        playbook.write_text(yaml.safe_dump(play))
        cases = [
            (None, False), ('all', False), ('tagged', False), ('never', False),
            ('start', False), ('start-all', False), ('start-group', False),
            ('install-all,start', False), ('setup-all,start', False),
            ('install-opencloud,start-group', False), ('setup-opencloud,start-group', False),
            ('migrate-opencloud', True), ('start,migrate-opencloud', True),
        ]
        for tags, expected in cases:
            with self.subTest(tags=tags):
                # Real Ansible tag selection, but check mode prevents any API call or rescan.
                command = ['ansible-playbook', '-i', 'localhost,', '-c', 'local',
                           str(playbook), '--check']
                if tags is not None:
                    command += ['--tags', tags]
                result = subprocess.run(command, capture_output=True, text=True, cwd=ROOT,
                                        timeout=30, env=self.ansible_environment())
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual('Check whether this OpenCloud search migration is complete' in result.stdout,
                                 expected, result.stdout + result.stderr)

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

    def test_traefik_and_smtp_wiring(self):
        result = self.render({
            'traefik_enabled': True,
            'traefik_entrypoint_primary': 'fixture-secure',
            'traefik_certResolver_primary': 'fixture-resolver',
            'exim_relay_enabled': True,
            'exim_relay_sender_address': 'cloud@example.test',
        })
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        labels = (self.path / 'labels').read_text()
        self.assertIn('entrypoints=fixture-secure', labels)
        self.assertIn('tls.certResolver=fixture-resolver', labels)
        env = (self.path / 'env').read_text()
        self.assertIn('NOTIFICATIONS_SMTP_HOST=mash-exim-relay', env)
        self.assertIn('NOTIFICATIONS_SMTP_SENDER=cloud@example.test', env)
        unit = (self.path / 'opencloud.service').read_text()
        self.assertIn('mash-traefik.service', unit)
        self.assertIn('mash-exim-relay.service', unit)
        self.assertIn('network connect mash-exim-relay mash-opencloud', unit)

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
