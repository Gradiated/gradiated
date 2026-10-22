import json
import os
import unittest

from support import host_bundle, mode, temporary_root

from gradiated_host import seed


class Seed(unittest.TestCase):
    def setUp(self):
        self.layout = temporary_root(self)
        self.archive, self.digest = host_bundle()
        self.downloads = 0
        previous = os.umask(0o077)
        self.addCleanup(os.umask, previous)

    def download(self, url, destination):
        self.downloads += 1
        with open(destination, 'wb') as output:
            output.write(self.archive)

    def release(self, **changes):
        return {'sha256': self.digest, 'base_id': 'test-base', 'url': 'https://artifacts/host.tar.gz', **changes}

    def test_installs_a_bundle_the_service_accounts_can_read(self):
        destination = seed.install(self.layout, self.release(), self.download)
        self.assertEqual(destination, self.layout.state / 'host' / self.digest)
        for path in (self.layout.state, self.layout.state / 'host', destination, self.layout.install / 'recovery'):
            self.assertEqual(mode(path), 0o755, path)
        self.assertEqual(mode(destination / 'desmondd'), 0o755)
        self.assertEqual(mode(destination / 'host-agent.py'), 0o644)
        self.assertEqual((self.layout.install / 'supervise.py').read_text(), 'print("launcher")\n')
        self.assertEqual(mode(self.layout.install / 'supervise.py'), 0o644)
        self.assertFalse((self.layout.install / 'recovery' / '.bundle-sha256').exists())
        status = json.loads((self.layout.state / 'host' / 'status.json').read_text())
        self.assertEqual(status['current'], self.digest)

    def test_a_retry_downloads_nothing_and_keeps_the_launcher_and_its_selection(self):
        seed.install(self.layout, self.release(), self.download)
        status = self.layout.state / 'host' / 'status.json'
        status.write_text(json.dumps({'schema': 2, 'current': 'b' * 64}))
        launcher = self.layout.install / 'supervise.py'
        launcher.write_text('print("newer launcher")\n')
        seed.install(self.layout, self.release(), self.download)
        self.assertEqual(self.downloads, 1)
        self.assertEqual(json.loads(status.read_text())['current'], 'b' * 64)
        self.assertEqual(launcher.read_text(), 'print("newer launcher")\n')

    def test_a_bundle_for_another_base_is_refused_before_download(self):
        with self.assertRaisesRegex(ValueError, 'requires a different base'):
            seed.install(self.layout, self.release(base_id='ubuntu24-cuda13-amd64-v3'), self.download)
        self.assertEqual(self.downloads, 0)

    def test_refuses_a_bundle_for_another_base_or_with_the_wrong_digest(self):
        with self.assertRaises(ValueError):
            seed.install(self.layout, self.release(base_id='other-base'), self.download)
        with self.assertRaises(ValueError):
            seed.install(self.layout, self.release(sha256='c' * 64), self.download)
        self.assertFalse((self.layout.state / 'host' / ('c' * 64)).exists())

    def test_fetch_requires_https(self):
        with self.assertRaises(ValueError):
            seed.fetch('http://artifacts/host.tar.gz', self.layout.root / 'archive')


if __name__ == '__main__':
    unittest.main()
