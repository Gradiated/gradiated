import copy
import unittest
from lockfiles import changed_importers


class LockfileSelectionTest(unittest.TestCase):
    def fixture(self):
        return {'lockfileVersion': '9.0', 'settings': {}, 'importers': {
            '.': {}, 'services/console': {'dependencies': {'ui': {'version': '1.0'}}},
            'services/worker': {'dependencies': {'queue': {'version': '1.0'}}}},
            'packages': {'ui@1.0': {'resolution': 'ui'}, 'queue@1.0': {'resolution': 'queue'}, 'leaf@1.0': {'resolution': 'a'}},
            'snapshots': {'ui@1.0': {'dependencies': {'leaf': '1.0'}}, 'queue@1.0': {}, 'leaf@1.0': {}}}

    def test_transitive_update_only_selects_its_consumers(self):
        before = self.fixture()
        after = copy.deepcopy(before)
        after['packages']['leaf@1.0']['resolution'] = 'b'
        self.assertEqual(changed_importers(before, after), ['services/console'])

    def test_unused_package_change_does_not_invalidate_workspaces(self):
        before = self.fixture()
        after = copy.deepcopy(before)
        after['packages']['unused@1.0'] = {}
        after['snapshots']['unused@1.0'] = {}
        self.assertEqual(changed_importers(before, after), [])

    def test_settings_change_requires_full_validation(self):
        before = self.fixture()
        after = copy.deepcopy(before)
        after['settings']['autoInstallPeers'] = False
        self.assertIsNone(changed_importers(before, after))

    def test_unknown_resolution_falls_back_to_full_validation(self):
        before = self.fixture()
        del before['snapshots']['leaf@1.0']
        self.assertIsNone(changed_importers(before, self.fixture()))

    def test_removed_importer_is_detected(self):
        before = self.fixture()
        after = copy.deepcopy(before)
        del after['importers']['services/console']
        self.assertEqual(changed_importers(before, after), ['services/console'])
