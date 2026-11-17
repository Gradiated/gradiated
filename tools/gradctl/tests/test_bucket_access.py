"""gradctl compute s3: VMs get expiring credentials for named bucket paths only."""

import argparse
import json
import subprocess
import unittest
from unittest import mock

import _path  # noqa: F401
from gradctl.compute import commands
from gradctl.core import UsageError

BUCKET = 'gradiated-dev-training-873716897517'
ISSUED = {'Credentials': {'AccessKeyId': 'ASIATEST', 'SecretAccessKey': 'temp-secret', 'SessionToken': 'token',
                          'Expiration': '2026-11-18T12:00:00+00:00'}}
SECRETS = {'DEV_TRAINING_AWS_ACCESS_KEY_ID': 'AKIAUSER', 'DEV_TRAINING_AWS_SECRET_ACCESS_KEY': 'user-secret',
           'DEV_TRAINING_S3_BUCKET': BUCKET}


class PathTests(unittest.TestCase):
    def test_paths_are_plain_prefixes(self):
        self.assertEqual(commands.bucket_path('bildy/run-7/'), 'bildy/run-7')
        self.assertEqual(commands.bucket_path('kimi/opd_v2.1/seed=3'), 'kimi/opd_v2.1/seed=3')
        for bad in ('', '/', '/bildy', 'bildy/*', 'bildy/../other', 'a//b', './x', 'bildy run', 'b?'):
            with self.assertRaises(argparse.ArgumentTypeError, msg=bad):
                commands.bucket_path(bad)


class PolicyTests(unittest.TestCase):
    def statements(self, writes, reads):
        return {s['Sid']: s for s in commands.bucket_policy(BUCKET, writes, reads)['Statement']}

    def test_writes_only_the_write_paths_and_reads_every_path(self):
        found = self.statements(['bildy/run-8'], ['bildy/run-7'])
        arn = f'arn:aws:s3:::{BUCKET}'
        self.assertEqual(found['Write']['Resource'], [f'{arn}/bildy/run-8/*'])
        self.assertEqual(found['Read']['Resource'], [f'{arn}/bildy/run-7/*', f'{arn}/bildy/run-8/*'])
        self.assertNotIn('s3:DeleteObject', found['Read']['Action'])

    def test_listing_stops_at_the_path_boundary(self):
        prefixes = self.statements(['bildy/run-8'], [])['List']['Condition']['StringLike']['s3:prefix']
        # Not the bare 'bildy/run-8', which would also list bildy/run-80/.
        self.assertEqual(prefixes, ['bildy/run-8/', 'bildy/run-8/*'])

    def test_read_only_access_has_no_write_statement(self):
        self.assertNotIn('Write', self.statements([], ['bildy/run-7']))

    def test_nothing_reaches_the_whole_bucket_or_another_bucket(self):
        for statement in commands.bucket_policy(BUCKET, ['a/b'], ['c'])['Statement']:
            resources = statement['Resource'] if isinstance(statement['Resource'], list) else [statement['Resource']]
            for resource in resources:
                self.assertTrue(resource.startswith(f'arn:aws:s3:::{BUCKET}'))
                self.assertNotEqual(resource, f'arn:aws:s3:::{BUCKET}/*')


class MintTests(unittest.TestCase):
    def test_mints_an_expiring_scoped_token_without_the_key_on_the_command_line(self):
        done = subprocess.CompletedProcess([], 0, stdout=json.dumps(ISSUED), stderr='')
        with mock.patch.object(commands, 'secret', SECRETS.get), \
                mock.patch.dict('os.environ', {'AWS_PROFILE': 'gradiated-developer', 'AWS_SESSION_TOKEN': 'mine'}), \
                mock.patch('subprocess.run', return_value=done) as run:
            issued = commands.bucket_credentials('a-very-long-vm-name-for-a-training-run', BUCKET,
                                                 ['bildy/run-8'], [], 24)
        self.assertEqual(issued['AccessKeyId'], 'ASIATEST')
        argv, environment = run.call_args.args[0], run.call_args.kwargs['env']
        self.assertEqual(argv[:3], ['aws', 'sts', 'get-federation-token'])
        name = argv[argv.index('--name') + 1]
        self.assertTrue(name.startswith('dt-') and len(name) <= 32)
        self.assertEqual(argv[argv.index('--duration-seconds') + 1], '86400')
        self.assertNotIn('user-secret', ' '.join(argv))
        self.assertEqual((environment['AWS_ACCESS_KEY_ID'], environment['AWS_SECRET_ACCESS_KEY']),
                         ('AKIAUSER', 'user-secret'))
        # The caller's own AWS identity must not be used or mixed in.
        self.assertNotIn('AWS_PROFILE', environment)
        self.assertNotIn('AWS_SESSION_TOKEN', environment)

    def s3_args(self, **overrides):
        return argparse.Namespace(**{'name': 'exp', 'provider': None, 'path': None, 'read': None, 'hours': 24,
                                     **overrides})

    def test_paths_are_required(self):
        with self.assertRaises(UsageError):
            commands.s3(self.s3_args())

    def test_a_read_path_cannot_sit_inside_a_writable_one(self):
        for read in ('bildy', 'bildy/old-run', 'bildy/old-run/step-9'):
            with self.assertRaises(UsageError, msg=read):
                commands.s3(self.s3_args(path=['bildy'], read=[read]))
        # A sibling sharing a name prefix is not inside it.
        with mock.patch.object(commands, 'located', side_effect=SystemExit('stop before SSH')), \
                self.assertRaises(SystemExit):
            commands.s3(self.s3_args(path=['bildy/run-8'], read=['bildy/run-80']))

    def test_hours_stay_within_what_aws_allows(self):
        with self.assertRaises(UsageError):
            commands.s3(self.s3_args(path=['bildy/run-8'], hours=48))

    def test_installs_the_temporary_credentials_on_every_machine(self):
        vm = {'state': 'RUNNING', 'machines': [{}, {}]}
        with mock.patch.object(commands, 'secret', SECRETS.get), \
                mock.patch.object(commands, 'located', return_value=object()), \
                mock.patch.object(commands, 'find', return_value=vm), \
                mock.patch.object(commands, 'ssh_command', return_value=['ssh', 'vm']), \
                mock.patch.object(commands, 'bucket_credentials', return_value=ISSUED['Credentials']) as mint, \
                mock.patch('subprocess.run') as run:
            result = commands.s3(self.s3_args(path=['bildy/run-8'], read=['bildy/run-7']))
        mint.assert_called_once_with('exp', BUCKET, ['bildy/run-8'], ['bildy/run-7'], 24)
        self.assertEqual(run.call_count, 2)
        # A credential_process document, which SDKs re-read near expiry, so renewals reach running jobs.
        installed = json.loads(run.call_args.kwargs['input'])
        self.assertEqual((installed['Version'], installed['SessionToken'], installed['Expiration']),
                         (1, 'token', '2026-11-18T12:00:00+00:00'))
        self.assertNotIn('AKIAUSER', run.call_args.kwargs['input'])
        script = run.call_args.args[0][-1]
        self.assertIn('credential_process', script)
        self.assertIn('rm -f ~/.aws/credentials', script)
        self.assertEqual(result.data['expires_at'], '2026-11-18T12:00:00+00:00')


if __name__ == '__main__':
    unittest.main()
