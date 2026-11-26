import json
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import urllib.error

sys.path.insert(0, str(Path(__file__).parent))
from nanogpt_probe import NoRedirect, StreamObservation, body_for, probe, public_cases, summary, validate_geometry, verify_public_commit


class ProbeTest(unittest.TestCase):
    def test_high_concurrency_requires_explicit_opt_in(self):
        with self.assertRaisesRegex(ValueError, "allow-high-concurrency"):
            validate_geometry(["heabsy"], [32])
        self.assertEqual(validate_geometry(["heabsy"], [64], True), 64)
        with self.assertRaisesRegex(ValueError, "At most 64"):
            validate_geometry(["heabsy"], [32, 64], True)
        with self.assertRaisesRegex(ValueError, "unique"):
            validate_geometry(["heabsy"], [32, 32], True)

    def test_public_commit_must_be_verified_by_github(self):
        commit = "a" * 40
        with patch("nanogpt_probe.request") as req:
            req.return_value.__enter__.return_value = io.BytesIO(json.dumps({"sha": "b" * 40}).encode())
            with self.assertRaisesRegex(ValueError, "not verified"):
                verify_public_commit(commit)

    def test_spoofed_remote_cannot_upload_local_commit(self):
        with patch("nanogpt_probe.subprocess.check_output", side_effect=[
            b"https://github.com/PostHog/posthog-js.git\n", b"a" * 40 + b"\n"
        ]) as git, patch("nanogpt_probe.verify_public_commit", side_effect=ValueError("not public")):
            with self.assertRaisesRegex(ValueError, "not public"):
                public_cases(Path("/unused"), "HEAD")
        self.assertEqual(git.call_count, 2)
        self.assertTrue(all("--no-replace-objects" in call.args[0] for call in git.call_args_list))

    def test_provider_pin_and_auto(self):
        case = {"prompt": "public source"}
        body = body_for("arnict", case, 512)
        self.assertEqual(body["provider"], {"only": ["arnict"], "allow_fallbacks": False})
        self.assertNotIn("provider", body_for("auto", case, 512))

    def test_cache_buster_is_first_in_system_prompt(self):
        body = body_for("arnict", {"prompt": "public source"}, 512, "test-nonce")
        self.assertTrue(body["messages"][0]["content"].startswith("Probe nonce test-nonce."))

    def test_fragmented_stream_reasoning_and_usage(self):
        obs = StreamObservation()
        obs.feed(b': keepalive\n\ndata: {"choices":[{"delta":{"role":"assistant"}}]}\n\n', 1)
        self.assertIsNone(obs.first_delta)
        wire = b'data: {"choices":[{"delta":{"reasoning":"thinking"}}]}\n\n'
        obs.feed(wire[:17], 2)
        obs.feed(wire[17:], 3)
        obs.feed(b'data: {"choices":[{"delta":{"content":"answer"}}]}\r\n\r\n', 5)
        obs.feed(b'data: {"choices":[{"delta":{"content":"!"},"finish_reason":"stop"}]}\n\n', 7)
        obs.feed(b'data: {"usage":{"completion_tokens":21}}\n\ndata: [DONE]\n\n', 8)
        metrics = obs.metrics()
        self.assertEqual(metrics["first_delta_s"], 3)
        self.assertEqual(metrics["first_content_s"], 5)
        self.assertEqual(metrics["decode_tokens_per_s_estimate"], 5)
        self.assertEqual(metrics["tpot_ms_estimate"], 200)
        self.assertTrue(metrics["done"])

    def test_stream_error_is_not_success(self):
        obs = StreamObservation()
        obs.feed(b'data: {"error":{"code":"overloaded"}}\n\ndata: [DONE]\n\n', 1)
        self.assertEqual(obs.error_code, "overloaded")
        self.assertIsNone(obs.finish_reason)
        self.assertIsNone(obs.metrics()["decode_tokens_per_s_estimate"])

    def test_summary_keeps_failures_in_denominator(self):
        base = {"provider_requested": "arnict", "concurrency": 2, "finish_reason": "stop",
                "first_delta_s": 2, "first_content_s": 4, "elapsed_s": 8,
                "decode_tokens_per_s_estimate": 20, "http_status": 200, "status": "ok"}
        failure = {**base, "status": "timeout", "finish_reason": None, "first_delta_s": None}
        result = summary([base, failure])[0]
        self.assertEqual(result["request_success_fraction"], 0.5)
        self.assertEqual(result["timeouts"], 1)
        self.assertEqual(result["first_delta_s"]["median"], 2)
        json.dumps(result, allow_nan=False)

    def test_http_failure_is_preserved_without_response_body(self):
        error = urllib.error.HTTPError("https://nano-gpt.com", 429, "limited", {}, None)
        with patch("nanogpt_probe.request", side_effect=error):
            result, content = probe("arnict", {"id": "test", "sha256": "abc", "prompt": "public"},
                                    1, 0, "dummy-test-credential", 64, 1, float("inf"))
        self.assertEqual(result["status"], "http_error")
        self.assertEqual(result["http_status"], 429)
        self.assertEqual(content, "")
        self.assertNotIn("dummy-test-credential", json.dumps(result))

    def test_redirects_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "redirect_refused"):
            NoRedirect().redirect_request(None, None, 302, "moved", {}, "https://other.invalid")


if __name__ == "__main__":
    unittest.main()
