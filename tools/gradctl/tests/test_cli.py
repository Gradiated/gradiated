"""gradctl's agent contract: the catalog, the --json envelope, exit codes and the tailnet gate."""

import io
import json
import os
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

import _path  # noqa: F401
from gradctl import cli, tailnet
from gradctl.core import Meta

LAUNCHER = Path(__file__).resolve().parents[1] / 'gradctl'
CONNECTED = {'connected': True, 'reason': None, 'dns_name': 'test.tail186117.ts.net'}
OFFLINE = {'connected': False, 'reason': 'tailscaled is not running or did not answer'}


def run(*argv, state=CONNECTED, env=None):
    """Run gradctl in-process; returns (exit code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.object(tailnet, 'check', return_value=state), \
            mock.patch.dict(os.environ, env or {}, clear=False), redirect_stdout(out), redirect_stderr(err):
        code = cli.run(list(argv))
    return code, out.getvalue(), err.getvalue()


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.entries = cli.catalog(cli.build_parser())

    def test_every_command_describes_itself(self):
        self.assertGreater(len(self.entries), 30)
        for entry in self.entries:
            with self.subTest(entry['command']):
                self.assertTrue(entry['summary'])
                self.assertIn(entry['effects'], ('read', 'write', 'destructive'))
                self.assertNotIn('json', [argument['name'] for argument in entry['arguments']])

    def test_commands_that_delete_say_so(self):
        destructive = {e['command'] for e in self.entries if e['effects'] == 'destructive'}
        self.assertEqual(destructive, {'compute down', 'gpu lease release'})

    def test_only_catalog_tailnet_and_bootstrap_commands_skip_the_tailnet(self):
        # aws login and env build are how a new machine gets the key that joins it.
        exempt = {e['command'] for e in self.entries if not e['tailnet']}
        self.assertEqual(exempt, {'commands', 'version', 'tailnet status', 'tailnet join', 'aws login',
                                  'env build'})

    def test_replaces_the_old_entry_points(self):
        names = {e['command'] for e in self.entries}
        for command in ('devex start', 'devex check', 'env build', 'aws login', 'compute search', 'compute up',
                        'compute down', 'gpu lease acquire', 'gpu render-config', 'github-apps create'):
            self.assertIn(command, names)

    def test_every_repository_tool_exists(self):
        from gradctl import repotools
        root = LAUNCHER.parents[2]
        for tool in repotools.TOOLS:
            for step in tool.steps:
                paths = [part for part in step if '/' in part and not part.startswith('-')
                         and part.endswith(('.py', '.mjs', '.sh'))]
                for path in paths:
                    with self.subTest(command=f'{tool.group} {tool.name}', path=path):
                        self.assertTrue((root / path).is_file())

    def test_commands_json_is_one_document(self):
        code, out, _ = run('commands', '--json', state=OFFLINE)
        self.assertEqual(code, 0)
        body = json.loads(out)
        self.assertTrue(body['ok'])
        self.assertEqual(body['data']['exit_codes']['3'].split(':')[0], 'tailnet_required')
        search = next(e for e in body['data']['commands'] if e['command'] == 'compute search')
        self.assertEqual(search['aliases'], ['prices'])
        provider = next(a for a in search['arguments'] if a['name'] == 'provider')
        self.assertTrue(provider['repeatable'])


class EnvelopeTests(unittest.TestCase):
    def test_usage_errors_are_exit_2_and_json(self):
        code, out, _ = run('--json', 'compute', 'nope')
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out)['error']['code'], 'usage')

    def test_a_group_without_a_command_is_a_usage_error(self):
        code, out, _ = run('--json', 'gpu')
        self.assertEqual((code, json.loads(out)['error']['code']), (2, 'usage'))

    def test_json_flag_works_after_the_command(self):
        code, out, _ = run('version', '--json')
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)['command'], 'version')

    def test_json_flag_works_after_a_group(self):
        code, out, _ = run('devex', '--json', 'skills')
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)['command'], 'devex skills')

    def test_json_inside_a_remote_command_is_not_gradctls(self):
        args, _ = cli.build_parser().parse_known_args(['compute', 'ssh', 'box', 'gh', 'pr', 'list', '--json', 'x'])
        self.assertFalse(getattr(args, 'json', False))
        self.assertEqual(args.command, ['gh', 'pr', 'list', '--json', 'x'])

    def test_a_failing_repository_tool_exits_1(self):
        code, out, _ = run('--json', 'gpu', 'render-config', '--no-such-flag', env={'GRADCTL_REPO': str(LAUNCHER.parents[2])})
        body = json.loads(out)
        self.assertEqual((code, body['ok']), (1, False))
        # The tool's own code (2 here, or 1 without PyYAML) stays in data.
        self.assertNotEqual(body['data']['steps'][0]['exit_code'], 0)

    def test_no_user_lookup_while_parsing(self):
        with mock.patch('getpass.getuser', side_effect=OSError('no user')):
            code, _, _ = run('--json', 'version')
        self.assertEqual(code, 0)

    def test_unknown_arguments_are_refused_unless_forwarded(self):
        code, out, _ = run('--json', 'devex', 'skills', '--bogus')
        self.assertEqual((code, json.loads(out)['error']['code']), (2, 'usage'))

    def test_sys_exit_messages_become_failures(self):
        with mock.patch('gradctl.devex.skills_report', side_effect=SystemExit('broken')):
            code, out, _ = run('--json', 'devex', 'skills')
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out)['error'], {'code': 'failed', 'message': 'broken', 'hint': None})


class GateTests(unittest.TestCase):
    def test_commands_refuse_to_run_off_the_tailnet(self):
        code, out, _ = run('--json', 'devex', 'skills', state=OFFLINE, env={'GITHUB_ACTIONS': ''})
        self.assertEqual(code, 3)
        body = json.loads(out)
        self.assertEqual(body['error']['code'], 'tailnet_required')
        self.assertIn('gradctl tailnet join', body['error']['hint'])

    def test_github_actions_runs_only_offline_commands(self):
        code, _, _ = run('devex', 'skills', state=OFFLINE, env={'GITHUB_ACTIONS': 'true'})
        self.assertEqual(code, 0)
        code, _, _ = run('gpu', 'lease', 'status', state=OFFLINE, env={'GITHUB_ACTIONS': 'true'})
        self.assertEqual(code, 3)

    def test_needed(self):
        with mock.patch.dict(os.environ, {'GITHUB_ACTIONS': 'true'}):
            self.assertFalse(tailnet.needed(Meta('x', network=False)))
            self.assertTrue(tailnet.needed(Meta('x', network=True)))
        with mock.patch.dict(os.environ, {'GITHUB_ACTIONS': ''}):
            self.assertTrue(tailnet.needed(Meta('x', network=False)))
            self.assertFalse(tailnet.needed(Meta('x', tailnet=False)))

    def test_evaluate(self):
        status = {'BackendState': 'Running', 'CurrentTailnet': {'Name': 'gradiated.com'},
                  'MagicDNSSuffix': 'tail186117.ts.net', 'Self': {'HostName': 'me', 'DNSName': 'me.tail186117.ts.net.'}}
        self.assertTrue(tailnet.evaluate(status)['connected'])
        self.assertEqual(tailnet.evaluate(status)['dns_name'], 'me.tail186117.ts.net')
        other = {**status, 'CurrentTailnet': {'Name': 'example.com'}, 'MagicDNSSuffix': 'tail1.ts.net'}
        self.assertIn('not the gradiated.com tailnet', tailnet.evaluate(other)['reason'])
        self.assertFalse(tailnet.evaluate({**status, 'BackendState': 'NeedsLogin'})['connected'])
        self.assertFalse(tailnet.evaluate(None)['connected'])


class ProcessTests(unittest.TestCase):
    """Through the launcher, so real file descriptors are involved."""

    def test_json_stdout_stays_clean_when_a_command_prints(self):
        script = (
            'import subprocess, sys; sys.path.insert(0, sys.argv[1]);'
            'from gradctl import core;'
            'with_ = core.stdout_to_stderr();'
            'with_.__enter__(); print("python noise"); subprocess.run(["echo", "child noise"]); with_.__exit__(None, None, None);'
            'core.emit_json({"ok": True})'
        )
        result = subprocess.run([sys.executable, '-c', script, str(LAUNCHER.parent / 'src')],
                                capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout), {'ok': True})
        self.assertIn('python noise', result.stderr)
        self.assertIn('child noise', result.stderr)

    def test_launcher_runs_without_install(self):
        result = subprocess.run([str(LAUNCHER), '--json', 'version'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['data']['version'], cli.VERSION)


if __name__ == '__main__':
    unittest.main()
