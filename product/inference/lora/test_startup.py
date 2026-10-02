import tempfile
import unittest

from fixtures import settings
from loader import Loader
from startup import start_preload


class StartupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.loader = Loader(settings(), self.temp.name, 1, set())
        self.loader.ready = False

    def test_empty_production_list_loads_nothing_and_serves_base(self):
        start_preload(self.loader, list)
        self.assertEqual(self.loader.entries, {})
        self.assertTrue(self.loader.ready)

    def test_base_is_ready_before_production_list_or_preload_completes(self):
        def targets():
            self.assertTrue(self.loader.ready)
            return []

        start_preload(self.loader, targets)

    def test_metadata_outage_does_not_close_base_readiness(self):
        def targets():
            raise OSError("private-url-token")

        with self.assertLogs(level="WARNING") as logs:
            start_preload(self.loader, targets)
        self.assertNotIn("private-url-token", "".join(logs.output))
        self.assertTrue(self.loader.ready)
