import argparse
import json
import os
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import _path  # noqa: F401
from gradctl import repos
from gradctl.core import CliError, Context, UsageError

RECORD = {'id': '01a1d0db-6dc4-758a-b9f9-b79fc8eaaaac', 'name': 'Acme', 'slug': 'acme',
          'installations': [{'id': 42, 'account': 'acme'}]}
REPOSITORIES = [{'full_name': 'acme/trainer', 'private': True, 'default_branch': 'main'},
                {'full_name': 'acme/evals', 'private': True, 'default_branch': 'main'}]


def context(**args):
    defaults = {'organization': 'acme', 'environment': 'dev', 'into': None, 'repo': None}
    return Context(args=argparse.Namespace(**{**defaults, **args}), command='repos', json=True)


def github(path, token, method='GET'):
    if path == '/app/installations/42/access_tokens':
        return {'token': 'ghs_secret'}
    if path.startswith('/installation/repositories'):
        return {'repositories': REPOSITORIES}
    raise AssertionError(path)


class ReposTests(unittest.TestCase):
    def setUp(self):
        patches = [mock.patch.object(repos, 'database_query', return_value=json.loads(json.dumps(RECORD))),
                   mock.patch.object(repos, 'app_credentials', return_value=('1', 'key')),
                   mock.patch.object(repos, 'app_jwt', return_value='jwt'),
                   mock.patch.object(repos, 'github', side_effect=github)]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def test_list_never_returns_the_token(self):
        result = repos.list_command(context())
        self.assertEqual([r['full_name'] for r in result.data['installations'][0]['repositories']],
                         ['acme/trainer', 'acme/evals'])
        self.assertNotIn('ghs_secret', json.dumps(result.data) + result.text)

    def test_an_uninstalled_app_is_reported_not_raised(self):
        def gone(path, token, method='GET'):
            raise CliError('not found', 'github_404')
        with mock.patch.object(repos, 'github', side_effect=gone):
            result = repos.list_command(context())
        self.assertEqual(result.data['installations'][0]['error'], 'no longer installed')

    def test_rejects_anything_but_an_id_or_slug(self):
        for organization in ("acme'; drop table organizations; --", 'Acme Corp', ''):
            with self.subTest(organization=organization), self.assertRaises(UsageError):
                repos.list_command(context(organization=organization))

    def test_unknown_organization_and_missing_installation(self):
        with mock.patch.object(repos, 'database_query', return_value=None), self.assertRaises(CliError) as error:
            repos.list_command(context())
        self.assertEqual(error.exception.code, 'not_found')
        with mock.patch.object(repos, 'database_query', return_value={**RECORD, 'installations': []}), \
                self.assertRaises(CliError) as error:
            repos.list_command(context())
        self.assertEqual(error.exception.code, 'not_installed')

    def test_clone_passes_the_token_as_a_header_only(self):
        with TemporaryDirectory() as into, mock.patch.object(subprocess, 'run') as run:
            run.return_value = subprocess.CompletedProcess([], 0, '', '')
            result = repos.clone_command(context(into=into, repo=['trainer']))
            (command,), _ = run.call_args
        self.assertEqual([c['repository'] for c in result.data['cloned']], ['acme/trainer'])
        self.assertIn('https://github.com/acme/trainer.git', command)
        self.assertFalse(any('ghs_secret' in part for part in command))
        self.assertTrue(any(part.startswith('http.https://github.com/.extraheader=AUTHORIZATION: basic ')
                            for part in command))
        self.assertEqual(Path(command[-1]), Path(into).resolve() / 'acme' / 'trainer')

    def test_clone_skips_existing_directories(self):
        with TemporaryDirectory() as into, mock.patch.object(subprocess, 'run') as run:
            (Path(into) / 'acme' / 'evals').mkdir(parents=True)
            run.return_value = subprocess.CompletedProcess([], 0, '', '')
            result = repos.clone_command(context(into=into))
        self.assertEqual([c['repository'] for c in result.data['cloned']], ['acme/trainer'])
        self.assertEqual(result.data['skipped'][0]['reason'], 'already exists')


class CredentialTests(unittest.TestCase):
    def test_restricted_users_get_an_access_error(self):
        denied = subprocess.CompletedProcess([], 254, '', 'An error occurred (AccessDeniedException)')
        with mock.patch.object(repos.shutil, 'which', return_value='/bin/aws'), \
                mock.patch.object(subprocess, 'run', return_value=denied), self.assertRaises(CliError) as error:
            repos.aws_secret(repos.APP_SECRETS['prod'])
        self.assertEqual(error.exception.code, 'access_denied')
        self.assertIn('readonly', error.exception.hint)

    def test_app_keys_stay_outside_the_restricted_namespace(self):
        for secret in (*repos.APP_SECRETS.values(), repos.PROD_DATABASE_SECRET):
            self.assertFalse(secret.startswith('gradiated/dev/'), secret)

    def test_a_downloaded_key_overrides_the_secret(self):
        with TemporaryDirectory() as directory:
            key = Path(directory, 'app.pem')
            key.write_text('pem')
            with mock.patch.dict(os.environ, {'GITHUB_APP_ID': '7', 'GITHUB_APP_PRIVATE_KEY_PATH': str(key)}):
                self.assertEqual(repos.app_credentials('dev'), ('7', 'pem'))


if __name__ == '__main__':
    unittest.main()
