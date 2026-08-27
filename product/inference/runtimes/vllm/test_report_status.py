from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from report_status import StatusUploader, classify_runtime


class CountingServer(HTTPServer):
    accepted_connections = 0

    def get_request(self):
        request, address = super().get_request()
        self.accepted_connections += 1
        return request, address


class StatusHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    reports: list[dict[str, object]] = []

    def do_POST(self):
        length = int(self.headers["Content-Length"])
        self.reports.append(json.loads(self.rfile.read(length)))
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, format, *args):
        pass


class ReportStatusTests(unittest.TestCase):
    def test_classifies_runtime_pressure(self):
        status = classify_runtime(
            True,
            "vllm:num_requests_running 4\nvllm:kv_cache_usage_perc 0.2\n",
            maximum_concurrency=4,
            kv_usage_limit=0.9,
        )
        self.assertTrue(status.healthy)
        self.assertFalse(status.accepting_requests)
        self.assertEqual(status.reason_code, "concurrency_full")

    def test_reuses_one_http_connection(self):
        StatusHandler.reports = []
        server = CountingServer(("127.0.0.1", 0), StatusHandler)
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            uploader = StatusUploader(
                f"http://127.0.0.1:{server.server_port}/v1/deployment-status",
                "test-token",
                1,
            )
            uploader.upload({"sequence": 1})
            uploader.upload({"sequence": 2})
            uploader.client.close()
            self.assertEqual(server.accepted_connections, 1)
            self.assertEqual(StatusHandler.reports, [{"sequence": 1}, {"sequence": 2}])
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
