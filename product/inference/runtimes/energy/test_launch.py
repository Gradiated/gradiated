import os
import sys
import unittest
from types import ModuleType
from unittest.mock import Mock, patch

import launch
from middleware import EnergyMiddleware


class TokenizerManager:
    async def _send_one_request(self):
        return 'sent'

    async def _send_batch_request(self):
        return 'batch sent'


class LaunchTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('GRADIATED_REQUIRE_SGLANG') == '1', 'Requires the pinned installed SGLang bundle')
    def test_pinned_sglang_http_app_accepts_the_middleware(self):
        from sglang.srt.entrypoints.http_server import app
        from sglang.srt.managers.tokenizer_manager import TokenizerManager as InstalledManager

        original = list(app.user_middleware)
        methods = {name: getattr(InstalledManager, name) for name in ['_send_one_request', '_send_batch_request']}
        try:
            launch.install_dispatch_hooks(InstalledManager)
            app.add_middleware(EnergyMiddleware)
            self.assertIs(app.user_middleware[0].cls, EnergyMiddleware)
            for name, method in methods.items():
                self.assertIs(getattr(InstalledManager, name).__wrapped__, method)
        finally:
            app.user_middleware[:] = original
            for name, method in methods.items():
                setattr(InstalledManager, name, method)

    def test_installs_on_the_existing_app_and_runs_normal_sglang_entrypoint(self):
        server = ModuleType('sglang.srt.entrypoints.http_server')
        server.app = Mock()
        manager = ModuleType('sglang.srt.managers.tokenizer_manager')
        manager.TokenizerManager = TokenizerManager
        for arguments in [[], ['--tokenizer-worker-num', '1'], ['--tokenizer-worker-num=1'],
                          ['--tokenizer-worker-num=2', '--tokenizer-worker-num', '1']]:
            with self.subTest(arguments=arguments):
                server.app.reset_mock()
                with patch.dict(sys.modules, {'sglang.srt.entrypoints.http_server': server,
                                              'sglang.srt.managers.tokenizer_manager': manager}), \
                        patch.object(sys, 'argv', ['launch.py', '--model-path', 'model', *arguments]), \
                        patch.object(launch.runpy, 'run_module') as run:
                    launch.main()
                server.app.add_middleware.assert_called_once_with(EnergyMiddleware)
                run.assert_called_once_with('sglang.launch_server', run_name='__main__')

    def test_missing_middleware_dependencies_still_launch_sglang(self):
        with patch.dict(sys.modules, {'sglang.srt.entrypoints.http_server': None}), \
                patch.object(sys, 'argv', ['launch.py']), \
                patch.object(launch.runpy, 'run_module') as run, \
                self.assertLogs(level='WARNING'):
            launch.main()
        run.assert_called_once_with('sglang.launch_server', run_name='__main__')

    def test_multiple_tokenizer_workers_omit_estimates(self):
        server = ModuleType('sglang.srt.entrypoints.http_server')
        server.app = Mock()
        for arguments in [['--tokenizer-worker-num', '2'], ['--tokenizer-worker-num=2']]:
            with patch.dict(sys.modules, {'sglang.srt.entrypoints.http_server': server}), \
                    patch.object(sys, 'argv', ['launch.py', *arguments]), \
                    patch.object(launch.runpy, 'run_module') as run:
                launch.main()
            run.assert_called_once_with('sglang.launch_server', run_name='__main__')
        server.app.add_middleware.assert_not_called()


class DispatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_successful_dispatch_starts_attribution(self):
        class Manager:
            async def _send_one_request(self, reject=False):
                if reject:
                    raise ValueError('invalid prompt')
                return 'sent'

            async def _send_batch_request(self):
                return 'batch sent'

        with patch('middleware.mark_generation_started') as started:
            launch.install_dispatch_hooks(Manager)
            manager = Manager()
            self.assertEqual(await manager._send_one_request(), 'sent')
            self.assertEqual(await manager._send_batch_request(), 'batch sent')
            self.assertEqual(started.call_count, 2)
            with self.assertRaises(ValueError):
                await manager._send_one_request(reject=True)
            self.assertEqual(started.call_count, 2)


if __name__ == '__main__':
    unittest.main()
