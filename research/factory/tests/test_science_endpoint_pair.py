import http.server
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import threading
import time
import unittest

from grad_research.science_tools.endpoint_pair import (
    compare_endpoint_pair,
    run_endpoint_pair,
)


TOOL = pathlib.Path(__file__).parents[1] / "tools" / "lab-endpoint-pair"


class EndpointState:
    def __init__(self) -> None:
        self.requests: list[tuple[str, bytes, str | None]] = []
        self.started_at: list[tuple[str, float]] = []
        self.lock = threading.Lock()


class EndpointHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    state: EndpointState

    def do_POST(self) -> None:
        size = int(self.headers["Content-Length"])
        body = self.rfile.read(size)
        with self.state.lock:
            self.state.requests.append((self.path, body, self.headers.get("X-Test")))
            self.state.started_at.append((self.path, time.monotonic()))
        payload = json.loads(body)
        case = payload["case"]
        if case == "error" and self.path == "/candidate":
            self._send_json(
                500,
                {
                    "error": {"message": "candidate failed"},
                    "usage": {"total_tokens": 1},
                },
            )
            return
        if case == "stream":
            parts = [
                b'data: {"choices":[{"delta":{"content":"hel"},'
                b'"finish_reason":null,"token_ids":[7]}]}\n\n',
                b'data: {"choices":[{"delta":{"content":"lo"},'
                b'"finish_reason":"stop","token_ids":[8]}],'
                b'"usage":{"prompt_tokens":3,"completion_tokens":2,'
                b'"total_tokens":5}}\n\n',
                b"data: [DONE]\n\n",
            ]
            response = b"".join(parts)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            for part in parts:
                self.wfile.write(part)
                self.wfile.flush()
            return
        if case == "stream_error":
            parts = [
                b'data: {"error":{"message":"input_ids required"}}\n\n',
                b"data: [DONE]\n\n",
            ]
            response = b"".join(parts)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            for part in parts:
                self.wfile.write(part)
                self.wfile.flush()
            return
        delay = payload.get("delay", 0)
        if delay:
            time.sleep(delay)
        self._send_json(
            200,
            {
                "choices": [
                    {
                        "message": {"content": f"answer:{payload['prompt']}"},
                        "finish_reason": "stop",
                        "token_ids": [1, 2, 3],
                    }
                ],
                "usage": {
                    "prompt_tokens": 4,
                    "completion_tokens": 3,
                    "total_tokens": 7,
                },
            },
        )

    def _send_json(self, status: int, value: object) -> None:
        body = json.dumps(value, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Set-Cookie", "provider-session=do-not-record")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


class LocalEndpoint:
    def __init__(self) -> None:
        self.state = EndpointState()
        handler = type("BoundEndpointHandler", (EndpointHandler,), {})
        handler.state = self.state
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> "LocalEndpoint":
        self.thread.start()
        return self

    def __exit__(self, *args: object) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    @property
    def root(self) -> str:
        host, port = self.server.server_address
        return f"http://{host}:{port}"


def write_workload(path: pathlib.Path, rows: list[dict[str, object]]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


def request_metadata(
    run_dir: pathlib.Path, arm: str, index: int
) -> dict[str, object]:
    directories = sorted((run_dir / "arms" / arm / "requests").iterdir())
    return json.loads((directories[index] / "metadata.json").read_text())


class EndpointPairTests(unittest.TestCase):
    def test_json_and_streaming_preserve_evidence_and_identical_bodies(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, LocalEndpoint() as endpoint:
            root = pathlib.Path(temporary)
            workload = root / "workload.jsonl"
            write_workload(
                workload,
                [
                    {
                        "request_id": "json-1",
                        "payload": {"case": "json", "prompt": "one"},
                    },
                    {
                        "request_id": "stream-1",
                        "payload": {
                            "case": "stream",
                            "prompt": "two",
                            "stream": True,
                        },
                    },
                ],
            )
            run_dir = root / "run"

            result = run_endpoint_pair(
                workload_path=workload,
                output_dir=run_dir,
                control_url=f"{endpoint.root}/control",
                candidate_url=f"{endpoint.root}/candidate",
                arm_order="candidate,control",
                seed=19,
                headers={"X-Test": "paired"},
                timeout_seconds=2,
            )

            self.assertTrue(result["complete"])
            self.assertTrue(result["all_requests_successful"])
            requests = endpoint.state.requests
            self.assertEqual(
                [path for path, _, _ in requests],
                ["/candidate", "/candidate", "/control", "/control"],
            )
            self.assertEqual([header for _, _, header in requests], ["paired"] * 4)
            self.assertEqual(requests[0][1], requests[2][1])
            self.assertEqual(requests[1][1], requests[3][1])
            self.assertEqual(json.loads(requests[0][1])["seed"], 19)

            json_metadata = request_metadata(run_dir, "control", 0)
            self.assertTrue(json_metadata["complete"])
            self.assertTrue(json_metadata["successful"])
            self.assertEqual(json_metadata["output_text"], "answer:one")
            self.assertEqual(json_metadata["token_ids"], [1, 2, 3])
            self.assertEqual(json_metadata["finish_reason"], "stop")
            self.assertEqual(json_metadata["usage"]["total_tokens"], 7)
            self.assertTrue(pathlib.Path(json_metadata["response"]["path"]).is_file())

            stream_metadata = request_metadata(run_dir, "control", 1)
            self.assertTrue(stream_metadata["streaming_response"])
            self.assertTrue(stream_metadata["transport_complete"])
            self.assertTrue(stream_metadata["protocol_complete"])
            self.assertEqual(stream_metadata["output_text"], "hello")
            self.assertEqual(stream_metadata["token_ids"], [7, 8])
            self.assertEqual(stream_metadata["event_count"], 3)
            events_path = pathlib.Path(stream_metadata["events"]["path"])
            events = [
                json.loads(line) for line in events_path.read_text().splitlines()
            ]
            self.assertEqual(events[-1]["data"], "[DONE]")
            raw_response = pathlib.Path(stream_metadata["response"]["path"]).read_bytes()
            self.assertEqual(raw_response, b"".join(part for part in [
                b'data: {"choices":[{"delta":{"content":"hel"},'
                b'"finish_reason":null,"token_ids":[7]}]}\n\n',
                b'data: {"choices":[{"delta":{"content":"lo"},'
                b'"finish_reason":"stop","token_ids":[8]}],'
                b'"usage":{"prompt_tokens":3,"completion_tokens":2,'
                b'"total_tokens":5}}\n\n',
                b"data: [DONE]\n\n",
            ]))

    def test_http_errors_are_preserved_as_complete_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, LocalEndpoint() as endpoint:
            root = pathlib.Path(temporary)
            workload = root / "workload.jsonl"
            write_workload(
                workload,
                [
                    {
                        "request_id": "error-1",
                        "payload": {"case": "error", "prompt": "fail"},
                    }
                ],
            )
            run_dir = root / "run"

            result = run_endpoint_pair(
                workload_path=workload,
                output_dir=run_dir,
                control_url=f"{endpoint.root}/control",
                candidate_url=f"{endpoint.root}/candidate",
                timeout_seconds=2,
            )

            self.assertTrue(result["complete"])
            self.assertFalse(result["all_requests_successful"])
            candidate = request_metadata(run_dir, "candidate", 0)
            self.assertEqual(candidate["status"], 500)
            self.assertEqual(candidate["error"]["kind"], "http")
            self.assertTrue(candidate["transport_complete"])
            self.assertTrue(candidate["complete"])
            self.assertFalse(candidate["successful"])
            self.assertIn(
                b"candidate failed",
                pathlib.Path(candidate["response"]["path"]).read_bytes(),
            )

    def test_stream_application_errors_are_not_successful(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, LocalEndpoint() as endpoint:
            root = pathlib.Path(temporary)
            workload = root / "workload.jsonl"
            write_workload(
                workload,
                [
                    {
                        "request_id": "stream-error-1",
                        "payload": {"case": "stream_error", "stream": True},
                    }
                ],
            )
            run_dir = root / "run"

            result = run_endpoint_pair(
                workload_path=workload,
                output_dir=run_dir,
                control_url=f"{endpoint.root}/control",
                candidate_url=f"{endpoint.root}/candidate",
                timeout_seconds=2,
            )

            self.assertTrue(result["complete"])
            self.assertFalse(result["all_requests_successful"])
            metadata = request_metadata(run_dir, "control", 0)
            self.assertTrue(metadata["transport_complete"])
            self.assertTrue(metadata["protocol_complete"])
            self.assertTrue(metadata["complete"])
            self.assertFalse(metadata["successful"])
            self.assertEqual(metadata["error"]["kind"], "application")
            self.assertEqual(metadata["error"]["message"], "input_ids required")

    def test_resume_skips_complete_requests_and_retries_only_incomplete_one(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, LocalEndpoint() as endpoint:
            root = pathlib.Path(temporary)
            workload = root / "workload.jsonl"
            write_workload(
                workload,
                [
                    {
                        "request_id": "resume-1",
                        "payload": {"case": "json", "prompt": "resume"},
                    }
                ],
            )
            run_dir = root / "run"
            arguments = {
                "workload_path": workload,
                "output_dir": run_dir,
                "control_url": f"{endpoint.root}/control",
                "candidate_url": f"{endpoint.root}/candidate",
                "timeout_seconds": 2,
            }

            run_endpoint_pair(**arguments)
            self.assertEqual(len(endpoint.state.requests), 2)
            run_endpoint_pair(**arguments)
            self.assertEqual(len(endpoint.state.requests), 2)

            candidate_dir = next(
                (run_dir / "arms" / "candidate" / "requests").iterdir()
            )
            metadata_path = candidate_dir / "metadata.json"
            metadata = json.loads(metadata_path.read_text())
            metadata["complete"] = False
            metadata_path.write_text(json.dumps(metadata))

            resumed = run_endpoint_pair(**arguments)

            self.assertTrue(resumed["complete"])
            self.assertEqual(len(endpoint.state.requests), 3)
            self.assertEqual(endpoint.state.requests[-1][0], "/candidate")

    def test_comparison_matches_ids_and_reports_equivalence_and_deltas(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, LocalEndpoint() as endpoint:
            root = pathlib.Path(temporary)
            workload = root / "workload.jsonl"
            write_workload(
                workload,
                [
                    {
                        "request_id": "compare-1",
                        "payload": {"case": "json", "prompt": "same"},
                    },
                    {
                        "request_id": "compare-2",
                        "payload": {"case": "stream", "prompt": "same", "stream": True},
                    },
                ],
            )
            run_dir = root / "run"
            run_endpoint_pair(
                workload_path=workload,
                output_dir=run_dir,
                control_url=f"{endpoint.root}/control",
                candidate_url=f"{endpoint.root}/candidate",
                parallel_arms=True,
                compare_latency=True,
                timeout_seconds=2,
            )

            report = compare_endpoint_pair(run_dir=run_dir)

            self.assertEqual(report["matched_request_count"], 2)
            self.assertEqual(report["exact_output_equivalent_count"], 2)
            self.assertEqual(report["exact_token_equivalent_count"], 2)
            self.assertTrue(report["latency_comparable"])
            self.assertEqual(
                [row["request_id"] for row in report["requests"]],
                ["compare-1", "compare-2"],
            )
            for row in report["requests"]:
                self.assertTrue(row["exact_output_equivalent"])
                self.assertTrue(row["exact_token_equivalent"])
                self.assertIsInstance(row["latency_delta_seconds"], float)
                self.assertEqual(
                    row["usage_delta_candidate_minus_control"]["total_tokens"], 0
                )
                self.assertNotIn("acceptable", row)

            cli_report = root / "cli-comparison.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "compare",
                    "--run-dir",
                    str(run_dir),
                    "--output",
                    str(cli_report),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(
                json.loads(cli_report.read_text())["matched_request_count"], 2
            )

    def test_cli_reads_secret_header_from_environment_without_recording_value(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, LocalEndpoint() as endpoint:
            root = pathlib.Path(temporary)
            workload = root / "workload.jsonl"
            write_workload(
                workload,
                [{"request_id": "env-1", "payload": {"case": "json", "prompt": "env"}}],
            )
            environment = os.environ.copy()
            environment["SCIENCE_TEST_AUTH"] = "Bearer do-not-record"
            completed = subprocess.run(
                [
                    str(TOOL),
                    "run",
                    "--workload",
                    str(workload),
                    "--output-dir",
                    str(root / "run"),
                    "--control-url",
                    f"{endpoint.root}/control?signed=do-not-record",
                    "--candidate-url",
                    f"{endpoint.root}/candidate?signed=do-not-record",
                    "--header-env",
                    "Authorization=SCIENCE_TEST_AUTH",
                ],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            run_text = (root / "run" / "run.json").read_text()
            self.assertNotIn("do-not-record", run_text)
            self.assertIn("authorization", run_text)
            metadata = request_metadata(root / "run", "control", 0)
            self.assertNotIn("set-cookie", metadata["response_headers"])
            self.assertIn("set-cookie", metadata["response_header_value_sha256"])

    def test_comparison_excludes_unsuccessful_or_corrupted_arms(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, LocalEndpoint() as endpoint:
            root = pathlib.Path(temporary)
            workload = root / "workload.jsonl"
            write_workload(
                workload,
                [{"request_id": "invalid-1", "payload": {"case": "json", "prompt": "x"}}],
            )
            run_dir = root / "run"
            run_endpoint_pair(
                workload_path=workload,
                output_dir=run_dir,
                control_url=f"{endpoint.root}/control",
                candidate_url=f"{endpoint.root}/candidate",
                timeout_seconds=2,
            )
            candidate_dir = next(
                (run_dir / "arms" / "candidate" / "requests").iterdir()
            )
            metadata_path = candidate_dir / "metadata.json"
            metadata = json.loads(metadata_path.read_text())
            metadata["successful"] = False
            metadata_path.write_text(json.dumps(metadata))

            report = compare_endpoint_pair(run_dir=run_dir)

            self.assertEqual(report["matched_request_count"], 0)
            self.assertEqual(report["exact_output_equivalent_count"], 0)
            self.assertFalse(report["requests"][0]["matched"])
            self.assertTrue(report["requests"][0]["both_present"])

    def test_cli_returns_nonzero_when_an_arm_has_http_errors(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, LocalEndpoint() as endpoint:
            root = pathlib.Path(temporary)
            workload = root / "workload.jsonl"
            write_workload(
                workload,
                [{"request_id": "error-cli", "payload": {"case": "error", "prompt": "x"}}],
            )
            completed = subprocess.run(
                [
                    str(TOOL),
                    "run",
                    "--workload",
                    str(workload),
                    "--output-dir",
                    str(root / "run"),
                    "--control-url",
                    f"{endpoint.root}/control",
                    "--candidate-url",
                    f"{endpoint.root}/candidate",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 1, completed.stderr)
            result = json.loads(completed.stdout)
            self.assertTrue(result["artifact_complete"])
            self.assertFalse(result["all_requests_successful"])

    def test_parallel_arms_replay_the_same_concurrent_schedule(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, LocalEndpoint() as endpoint:
            root = pathlib.Path(temporary)
            workload = root / "workload.jsonl"
            write_workload(
                workload,
                [
                    {
                        "request_id": f"parallel-{index}",
                        "payload": {
                            "case": "json",
                            "prompt": str(index),
                            "delay": 0.15,
                        },
                        "scheduled_offset_seconds": 0,
                    }
                    for index in range(2)
                ],
            )

            result = run_endpoint_pair(
                workload_path=workload,
                output_dir=root / "run",
                control_url=f"{endpoint.root}/control",
                candidate_url=f"{endpoint.root}/candidate",
                concurrency=2,
                parallel_arms=True,
                timeout_seconds=2,
            )

            self.assertTrue(result["complete"])
            self.assertEqual(result["contract"]["concurrency"], 2)
            self.assertTrue(result["contract"]["parallel_arms"])
            starts = [started for _, started in endpoint.state.started_at]
            self.assertEqual(len(starts), 4)
            self.assertLess(max(starts) - min(starts), 0.12)


if __name__ == "__main__":
    unittest.main()
