import json
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from tempfile import TemporaryDirectory

import server


class BridgeIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        self.bridge_root = root / "bridge"
        self.codex_root = root / "inference-foundry"
        self.bridge_root.mkdir(parents=True)
        (root / "docs").mkdir()
        (root / "docs" / "REPORT.md").write_text("# Claude report\n", encoding="utf-8")
        (self.bridge_root / "status.json").write_text(
            json.dumps({"text": "claude status", "updated": "now"}), encoding="utf-8"
        )
        (self.bridge_root / "inbox.jsonl").write_text(
            json.dumps({"ts": "1", "text": "claude-only-inbox"}) + "\n",
            encoding="utf-8",
        )
        (self.bridge_root / "outbox.jsonl").write_text(
            json.dumps({"ts": "2", "text": "claude-only-outbox"}) + "\n",
            encoding="utf-8",
        )
        (self.bridge_root / "lablog.jsonl").write_text("", encoding="utf-8")

        dashboard = self.codex_root / "dashboard"
        dashboard.mkdir(parents=True)
        (dashboard / "index.html").write_text(
            "<!doctype html><title>Inference Foundry Codex</title>", encoding="utf-8"
        )
        (dashboard / "status.json").write_text(
            json.dumps({"phase": "calibration", "updated": "today"}), encoding="utf-8"
        )
        (dashboard / "inbox.jsonl").write_text(
            json.dumps({"ts": "3", "text": "codex-only-inbox"}) + "\n",
            encoding="utf-8",
        )
        (dashboard / "outbox.jsonl").write_text(
            json.dumps({"ts": "4", "text": "codex-only-outbox"}) + "\n",
            encoding="utf-8",
        )
        (dashboard / "prompt-token").write_text("test-codex-token\n", encoding="utf-8")
        (dashboard / ".monitor-heartbeat").write_text("active\n", encoding="utf-8")
        summary = self.codex_root / "experiments" / "qwen3-8b"
        summary.mkdir(parents=True)
        (summary / "summary-v0.json").write_text(
            json.dumps({"weighted_cost_reduction": 0.3467}), encoding="utf-8"
        )
        (summary / "README.md").write_text("# Experiment report\n", encoding="utf-8")
        validation = self.codex_root / "validation"
        (validation / "results").mkdir(parents=True)
        (validation / "results" / "qwen3-0.6b-int4-sweep-v1.json").write_text(
            json.dumps({"status": "measured"}), encoding="utf-8"
        )
        (validation / "README.md").write_text("# Validation report\n", encoding="utf-8")
        docs = self.codex_root / "docs"
        docs.mkdir()
        (docs / "OVERNIGHT_REPORT_2026-07-12.md").write_text(
            "# Overnight decision report\n", encoding="utf-8"
        )
        (docs / "WAKEUP_BRIEF_2026-07-12.md").write_text(
            "# Wake-up brief\n", encoding="utf-8"
        )
        (docs / "GLM_CO_DESIGN.md").write_text(
            "# GLM co-design dossier\n", encoding="utf-8"
        )
        (docs / "BUSINESS_VALIDATION.md").write_text(
            "# Business validation dossier\n", encoding="utf-8"
        )
        (docs / "SIMULATOR_LANDSCAPE.md").write_text(
            "# Simulator landscape\n", encoding="utf-8"
        )
        (docs / "OPTIMIZATION_DECISIONS.md").write_text(
            "# Model-specific optimization decisions\n", encoding="utf-8"
        )
        (docs / "CUSTOM_HARDWARE_FEASIBILITY.md").write_text(
            "# Custom hardware feasibility audit\n", encoding="utf-8"
        )

        handler = server.handler_for_roots(
            bridge_root=str(self.bridge_root),
            codex_root=str(self.codex_root),
            codex_prompt_token_path=str(dashboard / "prompt-token"),
        )
        self.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.httpd.server_port}"

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=2)
        self.temporary_directory.cleanup()

    def request(self, path, method="GET", payload=None, raw_body=None, headers=None):
        data = raw_body
        headers = dict(headers or {})
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self.base_url + path, data=data, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=2) as response:
                return response.status, response.read(), response.headers
        except urllib.error.HTTPError as error:
            return error.code, error.read(), error.headers

    def test_main_dashboard_links_to_codex_and_codex_serves_its_dashboard(self):
        status, body, _ = self.request("/")
        self.assertEqual(status, 200)
        self.assertIn(b'href="/codex"', body)

        status, body, headers = self.request("/codex")
        self.assertEqual(status, 200)
        self.assertEqual(body, b"<!doctype html><title>Inference Foundry Codex</title>")
        self.assertIn("text/html", headers["Content-Type"])

    def test_codex_state_contains_only_codex_files_and_parsed_results(self):
        status, body, headers = self.request(
            "/api/codex-state",
            headers={"X-Codex-Prompt-Token": "test-codex-token"},
        )
        state = json.loads(body)

        self.assertEqual(status, 200)
        self.assertIn("application/json", headers["Content-Type"])
        self.assertEqual(state["status"]["phase"], "calibration")
        self.assertEqual(state["summary"]["weighted_cost_reduction"], 0.3467)
        self.assertEqual(state["validation"]["status"], "measured")
        self.assertTrue(state["session_active"])
        self.assertEqual({message["who"] for message in state["chat"]}, {"me", "codex"})
        encoded = json.dumps(state)
        self.assertIn("codex-only-inbox", encoded)
        self.assertIn("codex-only-outbox", encoded)
        self.assertNotIn("claude-only-inbox", encoded)
        self.assertNotIn("claude-only-outbox", encoded)

    def test_unauthenticated_codex_state_never_exposes_message_text(self):
        status, body, _ = self.request("/api/codex-state")
        state = json.loads(body)

        self.assertEqual(status, 200)
        self.assertEqual(state["chat"], [])
        self.assertEqual(state["chat_summary"]["inbox_count"], 1)
        self.assertEqual(state["chat_summary"]["outbox_count"], 1)
        self.assertEqual(state["chat_summary"]["latest_inbox_timestamp"], "3")
        self.assertEqual(state["chat_summary"]["latest_outbox_timestamp"], "4")
        encoded = json.dumps(state)
        self.assertNotIn("codex-only-inbox", encoded)
        self.assertNotIn("codex-only-outbox", encoded)

        status, body, _ = self.request("/codex/status.json")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["phase"], "calibration")

    def test_codex_prompt_is_validated_and_never_touches_claude_inbox(self):
        claude_before = (self.bridge_root / "inbox.jsonl").read_bytes()
        prompt = '<script>alert("render client-side")</script>'

        status, body, _ = self.request(
            "/codex/prompt",
            method="POST",
            payload={"text": prompt},
            headers={"X-Codex-Prompt-Token": "test-codex-token"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"ok": True})
        self.assertEqual((self.bridge_root / "inbox.jsonl").read_bytes(), claude_before)
        record = json.loads(
            (self.codex_root / "dashboard" / "inbox.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()[-1]
        )
        self.assertEqual(record["text"], prompt)

        status, _, _ = self.request(
            "/codex/prompt",
            method="POST",
            raw_body=b"not-json",
            headers={"X-Codex-Prompt-Token": "test-codex-token"},
        )
        self.assertEqual(status, 400)
        status, _, _ = self.request(
            "/codex/prompt",
            method="POST",
            payload={"text": "x" * 20001},
            headers={"X-Codex-Prompt-Token": "test-codex-token"},
        )
        self.assertEqual(status, 413)

    def test_codex_prompt_rejects_missing_or_wrong_access_token(self):
        inbox_before = (self.codex_root / "dashboard" / "inbox.jsonl").read_bytes()

        missing_status, _, _ = self.request(
            "/codex/prompt", method="POST", payload={"text": "not authorized"}
        )
        wrong_status, _, _ = self.request(
            "/codex/prompt",
            method="POST",
            payload={"text": "still not authorized"},
            headers={"X-Codex-Prompt-Token": "wrong"},
        )

        self.assertEqual(missing_status, 401)
        self.assertEqual(wrong_status, 401)
        self.assertEqual(
            (self.codex_root / "dashboard" / "inbox.jsonl").read_bytes(), inbox_before
        )

    def test_codex_markdown_routes_render_and_missing_files_fall_back_safely(self):
        status, body, headers = self.request("/codex/report")
        self.assertEqual(status, 200)
        self.assertIn(b"Experiment report", body)
        self.assertIn("text/html", headers["Content-Type"])

        (self.codex_root / "validation" / "README.md").unlink()
        status, body, _ = self.request("/codex/validation")
        self.assertEqual(status, 200)
        self.assertIn(b"not available", body.lower())

    def test_codex_decision_dossier_routes_render(self):
        routes = {
            "/codex/wakeup": b"Wake-up brief",
            "/codex/overnight": b"Overnight decision report",
            "/codex/glm": b"GLM co-design dossier",
            "/codex/business": b"Business validation dossier",
            "/codex/simulators": b"Simulator landscape",
            "/codex/decisions": b"Model-specific optimization decisions",
            "/codex/hardware": b"Custom hardware feasibility audit",
        }
        for route, expected in routes.items():
            status, body, headers = self.request(route)
            self.assertEqual(status, 200)
            self.assertIn(expected, body)
            self.assertIn("text/html", headers["Content-Type"])

    def test_existing_claude_prompt_route_still_uses_only_claude_inbox(self):
        codex_before = (self.codex_root / "dashboard" / "inbox.jsonl").read_bytes()

        status, _, _ = self.request("/prompt", method="POST", payload={"text": "claude"})
        state_status, state_body, _ = self.request("/api/state")

        self.assertEqual(status, 200)
        self.assertEqual(state_status, 200)
        self.assertIn("claude", (self.bridge_root / "inbox.jsonl").read_text(encoding="utf-8"))
        encoded_state = state_body.decode("utf-8")
        self.assertIn("claude-only-inbox", encoded_state)
        self.assertIn("claude-only-outbox", encoded_state)
        self.assertNotIn("codex-only-inbox", encoded_state)
        self.assertNotIn("codex-only-outbox", encoded_state)
        self.assertEqual(
            (self.codex_root / "dashboard" / "inbox.jsonl").read_bytes(), codex_before
        )


if __name__ == "__main__":
    unittest.main()
