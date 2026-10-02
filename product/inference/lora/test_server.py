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
        self.loader.ready = True
        self.loader.engine = mock.Mock(return_value=b"ok")
        self.front = create_server(self.loader, 0, "synthetic-control-token")
        threading.Thread(target=self.front.serve_forever, daemon=True).start()
        self.addCleanup(self.front.server_close)
        self.addCleanup(self.front.shutdown)

    def request(self, method, path, body=None, authenticated=True):
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.front.server_port, timeout=5
        )
        self.addCleanup(connection.close)
        headers = (
            {"X-Gradiated-Adapter-Control": "synthetic-control-token"}
            if authenticated
            else {}
        )
        connection.request(
            method, path, json.dumps(body) if body is not None else None, headers
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

    def test_private_routes_require_control_token(self):
        for method, path in (
            ("POST", "/internal/adapters/prepare"),
            ("POST", "/internal/adapters/probe"),
            ("GET", "/internal/adapters"),
            ("GET", "/internal/adapters/metrics"),
        ):
            status, _ = self.request(
                method,
                path,
                {"name": self.name, "workspace_id": self.spec["workspace_id"]}
                if method == "POST"
                else None,
                authenticated=False,
            )
            self.assertEqual(status, 403)
        self.loader.engine.assert_not_called()

    def test_prepare_registers_adapter_through_native_api_and_returns_boot_identity(
        self,
    ):
        status, body = self.request(
            "POST",
            "/internal/adapters/prepare",
            {"name": self.name, "workspace_id": self.spec["workspace_id"]},
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["boot_id"], self.loader.boot_id)
        self.assertEqual(
            self.loader.engine.call_args.args[:2], ("POST", "/v1/load_lora_adapter")
        )
        _, metrics = self.request("GET", "/internal/adapters/metrics")
        self.assertIn(b"gradiated_lora_registrations_total 1", metrics)
        self.assertNotIn(self.name.encode(), metrics)

    def test_capacity_rejection_does_not_change_readiness(self):
        with self.loader.admission, self.loader.admission:
            status, _ = self.request(
                "POST",
                "/internal/adapters/prepare",
                {"name": self.name, "workspace_id": self.spec["workspace_id"]},
            )
        self.assertEqual(status, 503)
        self.assertEqual(self.request("GET", "/health")[0], 200)

    def test_invalid_workspace_and_body_are_rejected_before_native_loading(self):
        for body in (
            {"name": self.name},
            {"name": self.name, "workspace_id": ""},
            {"name": self.name, "workspace_id": "01980000-0000-7000-8000-000000000002"},
        ):
            status, _ = self.request("POST", "/internal/adapters/prepare", body)
            self.assertIn(status, (422, 503))
        self.loader.engine.assert_not_called()

    def test_probe_checks_served_identity_and_usage(self):
        self.loader.engine.side_effect = [
            b"ok",
            json.dumps(
                {"model": self.name, "choices": [{}], "usage": {"completion_tokens": 1}}
            ).encode(),
        ]
        status, _ = self.request(
            "POST",
            "/internal/adapters/probe",
            {"name": self.name, "workspace_id": self.spec["workspace_id"]},
        )
        self.assertEqual(status, 200)
        self.assertEqual(
            self.loader.engine.call_args.args[:2], ("POST", "/v1/chat/completions")
        )


if __name__ == "__main__":
    unittest.main()
