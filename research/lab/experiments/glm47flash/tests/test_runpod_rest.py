import io
import json
import unittest
import urllib.error

from runpod_rest import (
    capture_http_error,
    sanitize_body,
    sanitize_headers,
    validate_openapi_object,
)


class RunPodErrorCaptureTests(unittest.TestCase):
    def test_sanitizes_headers_by_allowlist(self):
        headers = {
            "Content-Type": "application/json",
            "X-Request-Id": "request-17",
            "Authorization": "Bearer never-record-this",
            "Set-Cookie": "secret-cookie",
        }

        self.assertEqual(
            sanitize_headers(headers),
            {
                "content-type": "application/json",
                "x-request-id": "request-17",
            },
        )

    def test_sanitizes_structured_body_recursively(self):
        body = json.dumps(
            {
                "error": "invalid gpu",
                "apiKey": "never-record-this",
                "nested": {"authorization": "Bearer hidden", "reason": "unavailable"},
            }
        ).encode()

        sanitized = json.loads(sanitize_body(body))

        self.assertEqual(sanitized["error"], "invalid gpu")
        self.assertEqual(sanitized["apiKey"], "<redacted>")
        self.assertEqual(sanitized["nested"]["authorization"], "<redacted>")
        self.assertEqual(sanitized["nested"]["reason"], "unavailable")

    def test_sanitizes_bearer_token_in_text_body(self):
        body = b"failure for Bearer abc.def-123 on upstream"

        self.assertEqual(
            sanitize_body(body),
            "failure for Bearer <redacted> on upstream",
        )

    def test_captures_http_error_status_headers_and_body(self):
        error = urllib.error.HTTPError(
            "https://rest.runpod.io/v1/pods",
            500,
            "Internal Server Error",
            {"Content-Type": "application/json", "CF-Ray": "ray-1"},
            io.BytesIO(b'{"error":"gpu unavailable"}'),
        )

        captured = capture_http_error(error)

        self.assertEqual(captured["status"], 500)
        self.assertEqual(captured["reason"], "Internal Server Error")
        self.assertEqual(captured["headers"]["cf-ray"], "ray-1")
        self.assertEqual(captured["body"], '{"error":"gpu unavailable"}')

    def test_validates_array_item_enums(self):
        schema = {
            "type": "object",
            "properties": {
                "gpuTypeIds": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["NVIDIA L40S"]},
                },
                "gpuCount": {"type": "integer", "minimum": 1},
            },
        }

        self.assertEqual(
            validate_openapi_object(
                {"gpuTypeIds": ["NVIDIA L40S"], "gpuCount": 1}, schema
            ),
            [],
        )
        self.assertEqual(
            validate_openapi_object(
                {"gpuTypeIds": ["not-a-gpu"], "gpuCount": 0}, schema
            ),
            [
                "gpuCount must be >= 1",
                "gpuTypeIds[0] is not an allowed value",
            ],
        )


if __name__ == "__main__":
    unittest.main()
