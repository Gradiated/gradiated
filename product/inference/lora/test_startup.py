import tempfile
import unittest

from fixtures import settings
from manager import Manager
from startup import start_preload


class StartupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.manager = Manager(settings(), self.temp.name, 1, set())
        self.manager.engine_ready = self.manager.ready = False

    def test_empty_production_list_loads_nothing_and_serves_base(self):
        start_preload(self.manager, list)
        self.assertEqual(self.manager.entries, {})
        self.assertTrue(self.manager.ready)
        with self.manager.request("base"):
            pass

    def test_base_is_ready_before_production_list_or_preload_completes(self):
        def targets():
            self.assertTrue(self.manager.ready)
            with self.manager.request("base"):
                pass
            return []

        start_preload(self.manager, targets)

    def test_metadata_outage_does_not_close_base_readiness(self):
        def targets():
            raise OSError("private-url-token")

        with self.assertLogs(level="WARNING") as logs:
            start_preload(self.manager, targets)
        self.assertNotIn("private-url-token", "".join(logs.output))
        self.assertTrue(self.manager.ready)
        self.assertFalse(self.manager.failed)
        with self.manager.request("base"):
            pass
