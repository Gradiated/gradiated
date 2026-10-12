import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "forward_control", Path(__file__).parents[1] / "forward-control.py"
)
forward = importlib.util.module_from_spec(spec)
spec.loader.exec_module(forward)


class ControlEndpointTests(unittest.TestCase):
    def test_refuses_public_cluster_endpoints(self):
        for value in ["203.0.113.1", "127.0.0.1", "10.40.1.1", "::1"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                forward.routes({name: value for name in forward.ENDPOINTS})

    def test_requires_the_complete_known_endpoint_set(self):
        with self.assertRaises(ValueError):
            forward.routes({"api": "100.64.0.1"})
        with self.assertRaises(ValueError):
            forward.routes({**{name: "100.64.0.1" for name in forward.ENDPOINTS}, "database": "100.64.0.2"})
