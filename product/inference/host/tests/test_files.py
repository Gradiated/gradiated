import os
import unittest

from support import mode, temporary_root

from gradiated_host import files


class PrivateUmask(unittest.TestCase):
    """Enrollment runs under Tailscale SSH's umask 077; modes must not depend on it."""

    def setUp(self):
        self.layout = temporary_root(self)
        self.owner = (os.getuid(), os.getgid())
        previous = os.umask(0o077)
        self.addCleanup(os.umask, previous)

    def test_directories_and_missing_parents_get_explicit_modes(self):
        target = self.layout.root / 'a' / 'b' / 'c'
        files.directory(target, 0o750, self.owner)
        self.assertEqual(mode(target), 0o750)
        self.assertEqual(mode(target.parent), 0o755)
        self.assertEqual(mode(target.parent.parent), 0o755)

    def test_existing_parents_keep_their_modes(self):
        parent = self.layout.root / 'private'
        parent.mkdir(mode=0o700)
        files.directory(parent / 'child', 0o755, self.owner)
        self.assertEqual(mode(parent), 0o700)

    def test_written_files_get_exactly_the_requested_mode(self):
        for requested in (0o644, 0o600, 0o755):
            with self.subTest(mode=oct(requested)):
                path = self.layout.root / f'file-{requested:o}'
                files.write(path, 'data', requested, self.owner)
                self.assertEqual(mode(path), requested)
                self.assertEqual(path.read_text(), 'data')

    def test_write_replaces_atomically_and_leaves_no_temporary_files(self):
        path = self.layout.root / 'state.json'
        files.write(path, 'first', 0o600, self.owner)
        files.write(path, b'second', 0o644, self.owner)
        self.assertEqual(path.read_text(), 'second')
        self.assertEqual(mode(path), 0o644)
        self.assertEqual(sorted(p.name for p in self.layout.root.iterdir() if p.name.startswith('.')), [])

    def test_symbolic_links_are_refused(self):
        target = self.layout.root / 'target'
        target.write_text('kept')
        link = self.layout.root / 'link'
        link.symlink_to(target)
        with self.assertRaises(OSError):
            files.write(link, 'replaced', 0o600, self.owner)
        with self.assertRaises(OSError):
            files.directory(link, 0o755, self.owner)
        self.assertEqual(target.read_text(), 'kept')

    def test_logs_are_private(self):
        path = self.layout.logs / 'service.log'
        with files.log(path) as output:
            output.write(b'line\n')
        with files.log(path) as output:
            output.write(b'more\n')
        self.assertEqual(mode(path), 0o600)
        self.assertEqual(path.read_text(), 'line\nmore\n')


if __name__ == '__main__':
    unittest.main()
