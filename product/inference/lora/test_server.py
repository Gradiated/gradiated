import http.client
import json
import tempfile
import threading
import unittest
from unittest import mock

from fixtures import archive, grant, settings
from loader import Loader
from server import create_server


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.payload = archive()
        self.spec = grant(self.payload)
        self.loader = Loader(
            settings(),
            self.temp.name,
            1,
            set(),
            fetch=lambda spec, path, hosts: path.write_bytes(self.payload),
        )
        self.name = self.loader.register_metadata(self.spec)
        self.loader.resolve = lambda name, workspace: self.spec
        self.loader.ready = True
        self.loader.engine = mock.Mock(return_value=b"ok")
        self.front = create_server(self.loader, 0)
        threading.Thread(target=self.front.serve_forever, daemon=True).start()
        self.addCleanup(self.front.server_close)
        self.addCleanup(self.front.shutdown)

    def request(self, method, path, body=None):
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.front.server_port, timeout=5
        )
        self.addCleanup(connection.close)
        connection.request(
            method, path, json.dumps(body) if body is not None else None, {}
        )
        response = connection.getresponse()
        return response.status, response.read()

    def test_control_service_never_forwards_inference_or_admin_routes(self):
        for method, path in (
            ("POST", "/v1/chat/completions"),
            ("POST", "/v1/completions"),
            ("POST", "/v1/load_lora_adapter"),
            ("POST", "/v1/unload_lora_adapter"),
            ("GET", "/v1/models"),
            ("GET", "/metrics"),
        ):
            status, _ = self.request(
                method, path, {"model": "base"} if method == "POST" else None
            )
            self.assertEqual(status, 404)
        self.loader.engine.assert_not_called()

    def test_control_listener_is_loopback_only(self):
        self.assertEqual(self.front.server_address[0], "127.0.0.1")

    def test_prepare_registers_adapter_through_native_api_and_returns_boot_identity(
        self,
    ):
        status, body = self.request(
            "POST",
            "/internal/adapters/prepare",
            {
                "name": self.spec["version"]["name"],
                "workspace_id": self.spec["workspace_id"],
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["boot_id"], self.loader.boot_id)
        self.assertEqual(
            self.loader.engine.call_args.args[:2], ("POST", "/v1/load_lora_adapter")
        )
        _, metrics = self.request("GET", "/internal/adapters/metrics")
        self.assertIn(b"gradiated_lora_registrations_total 1", metrics)
        self.assertNotIn(self.name.encode(), metrics)

    def test_resolve_returns_verified_files_without_calling_vllm(self):
        status, body = self.request(
            "POST",
            "/internal/adapters/resolve",
            {
                "name": self.spec["version"]["name"],
                "workspace_id": self.spec["workspace_id"],
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["path"], str(self.loader.root / self.name))
        self.loader.engine.assert_not_called()
        self.assertTrue(self.loader.entries[self.name]["pinned"])

    def test_capacity_rejection_does_not_change_readiness(self):
        with self.loader.admission, self.loader.admission:
            status, _ = self.request(
                "POST",
                "/internal/adapters/prepare",
                {
                    "name": self.spec["version"]["name"],
                    "workspace_id": self.spec["workspace_id"],
                },
            )
        self.assertEqual(status, 503)
        self.assertEqual(self.request("GET", "/health")[0], 200)
        _, metrics = self.request("GET", "/internal/adapters/metrics")
        self.assertIn(
            b'gradiated_lora_operations_total{action="prepare",outcome="capacity"} 1',
            metrics,
        )
        self.assertGreater(self.loader.last_capacity_rejection, 0)

    def test_grant_failure_is_observable_without_exposing_credentials(self):
        self.loader.resolve = mock.Mock(side_effect=OSError("secret-signed-url"))
        with self.assertLogs(level="WARNING") as logs:
            status, _ = self.request(
                "POST",
                "/internal/adapters/resolve",
                {
                    "name": self.spec["version"]["name"],
                    "workspace_id": self.spec["workspace_id"],
                },
            )
        self.assertEqual(status, 503)
        self.assertNotIn("secret-signed-url", "".join(logs.output))
        _, metrics = self.request("GET", "/internal/adapters/metrics")
        self.assertIn(
            b'gradiated_lora_operations_total{action="resolve",outcome="failed"} 1',
            metrics,
        )
        self.assertGreater(self.loader.last_failure, 0)
        self.assertNotIn(self.spec["workspace_id"].encode(), metrics)

    def test_invalid_workspace_and_body_are_rejected_before_native_loading(self):
        for body in (
            {"name": self.spec["version"]["name"]},
            {"name": self.spec["version"]["name"], "workspace_id": ""},
            {
                "name": self.spec["version"]["name"],
                "workspace_id": "01980000-0000-7000-8000-000000000002",
            },
        ):
            status, _ = self.request("POST", "/internal/adapters/prepare", body)
            self.assertIn(status, (422, 503))
        self.loader.engine.assert_not_called()

    def test_probe_checks_served_identity_and_usage(self):
        self.loader.engine.side_effect = [
            b"ok",
            json.dumps(
                {
                    "model": f"{self.spec['workspace_id']}/{self.spec['version']['name']}",
                    "choices": [{}],
                    "usage": {"completion_tokens": 1},
                }
            ).encode(),
        ]
        status, _ = self.request(
            "POST",
            "/internal/adapters/probe",
            {
                "name": self.spec["version"]["name"],
                "workspace_id": self.spec["workspace_id"],
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(
            self.loader.engine.call_args.args[:2], ("POST", "/v1/chat/completions")
        )


if __name__ == "__main__":
    unittest.main()
