import base64
import json
import pathlib
import subprocess
import tempfile
import unittest

from grad_research.science_tools.common import read_jsonl
from grad_research.science_tools.microscope import (
    CaptureSelector,
    Recorder,
    diff_events,
    tensor_metadata,
)


TOOL = pathlib.Path(__file__).parents[1] / "tools" / "lab-microscope"


class FakeTensor:
    shape = (2, 2)
    strides = (8, 4)
    dtype = "float32"
    device = "cpu"

    def __init__(self, values):
        self.values = values

    def tolist(self):
        return self.values

    def tobytes(self, order="C"):
        del order
        return json.dumps(self.values, separators=(",", ":")).encode()

    def data_ptr(self):
        return 1234


def event(layer, value, *, order=0):
    return {
        "schema_version": 1,
        "order": order,
        "kind": "tensor",
        "metadata": {
            "request_id": "r1",
            "sequence_id": 0,
            "layer": layer,
            "phase": "decode",
        },
        "payload": {"name": "hidden", "value": value},
    }


class ScienceMicroscopeTests(unittest.TestCase):
    def test_selector_filters_all_supported_coordinates(self):
        selector = CaptureSelector(
            request="r1",
            sequence=2,
            layer={3, 4},
            phase="decode",
            decode_step=5,
            draft_depth=2,
            tensor_role="kv",
            operation="copy",
            cycle=7,
        )
        coordinates = {
            "request_id": "r1",
            "sequence_id": 2,
            "layer": 4,
            "phase": "decode",
            "decode_step": 5,
            "draft_depth": 2,
            "tensor_role": "kv",
            "operation": "copy",
            "cycle": 7,
        }
        self.assertTrue(selector.matches(**coordinates))
        self.assertFalse(selector.matches(**{**coordinates, "cycle": 8}))
        self.assertFalse(selector.matches(**{**coordinates, "request_id": "r2"}))
        self.assertTrue(
            CaptureSelector(request="r1", sequence=2).matches(
                {"request": "r1", "sequence": 2}
            )
        )

    def test_recorder_filters_before_tensor_inspection_and_orders_events(self):
        class ExplodesIfInspected:
            @property
            def shape(self):
                raise AssertionError("unselected tensor was inspected")

        with tempfile.TemporaryDirectory() as temporary:
            capture = pathlib.Path(temporary) / "capture.jsonl"
            recorder = Recorder(
                capture,
                selector=CaptureSelector(layer=3),
                metadata={"run_id": "candidate"},
            )
            self.assertIsNone(recorder.tensor(ExplodesIfInspected(), layer=2))
            recorder.acceptance(
                accepted_prefix=[1, 2],
                bonus_token=3,
                committed_length=3,
                next_token=4,
                layer=3,
            )
            recorder.correlation(
                stream=1,
                event=2,
                operator="attention",
                kernel="flash",
                layer=3,
            )
            rows = read_jsonl(capture)
            self.assertEqual([row["order"] for row in rows], [0, 1])
            self.assertEqual(rows[0]["metadata"]["run_id"], "candidate")
            self.assertEqual(rows[1]["payload"]["kernel"], "flash")

    def test_tensor_metadata_digest_stats_and_pointers(self):
        first = tensor_metadata(
            FakeTensor([[1.0, 2.0], [3.0, 4.0]]),
            byte_mode="complete",
            max_bytes=128,
        )
        second = tensor_metadata(
            FakeTensor([[1.0, 2.0], [3.0, 4.0]]),
            byte_mode="complete",
            max_bytes=128,
        )
        changed = tensor_metadata(
            FakeTensor([[1.0, 2.0], [3.0, 5.0]]),
            byte_mode="complete",
            max_bytes=128,
        )

        self.assertEqual(first["shape"], [2, 2])
        self.assertEqual(first["stride"], [8, 4])
        self.assertEqual(first["dtype"], "float32")
        self.assertEqual(first["device"], "cpu")
        self.assertEqual(first["alias_pointer"], 1234)
        self.assertEqual(first["stats"]["mean"], 2.5)
        self.assertEqual(first["digest"], second["digest"])
        self.assertNotEqual(first["digest"], changed["digest"])

    def test_metadata_only_tensor_capture_does_not_materialize_values(self):
        class MetadataOnly:
            shape = (1_000_000,)
            dtype = "float16"
            device = "cuda:0"

            def tolist(self):
                raise AssertionError("metadata-only capture materialized tensor")

            def tobytes(self):
                raise AssertionError("metadata-only capture copied tensor")

        result = tensor_metadata(MetadataOnly())

        self.assertEqual(result["shape"], [1_000_000])
        self.assertEqual(result["capture_scope"], "none")
        self.assertNotIn("digest", result)
        self.assertNotIn("stats", result)

    def test_explicit_logits_kv_and_correlation_records(self):
        recorder = Recorder(enabled=True)
        logits = recorder.logits_topk([0.5, 2.0, 1.0], k=2, decode_step=3)
        kv = recorder.kv(
            source={"page": 1},
            destination={"page": 2},
            valid_length=128,
            ownership={"request_id": "r1"},
            decode_step=3,
        )
        correlation = recorder.correlation(
            stream="stream-1",
            event="event-2",
            operator="attention",
            kernel="flash_attention",
            decode_step=3,
        )

        self.assertEqual(
            [item["token_id"] for item in logits["payload"]["top_k"]],
            [1, 2],
        )
        self.assertEqual(kv["payload"]["valid_length"], 128)
        self.assertEqual(correlation["payload"]["kernel"], "flash_attention")

    def test_batched_logits_keep_token_ids_within_each_vocabulary_row(self):
        recorder = Recorder(enabled=True)

        captured = recorder.logits_topk([[0.1, 0.9, 0.2], [0.8, 0.3, 0.4]], k=2)

        self.assertEqual(captured["payload"]["row_count"], 2)
        self.assertEqual(
            [
                [item["token_id"] for item in row]
                for row in captured["payload"]["top_k_by_row"]
            ],
            [[1, 2], [0, 2]],
        )

    def test_diff_reports_first_divergent_field(self):
        result = diff_events(
            [event(0, 1), event(1, 2, order=1)],
            [event(0, 1), event(1, 9, order=1)],
        )
        self.assertFalse(result["equal"])
        self.assertEqual(result["difference"], "divergent_field")
        self.assertEqual(result["semantic_key"]["layer"], 1)
        self.assertEqual(result["path"], "$.payload.value")
        self.assertEqual(result["left_value"], 2)
        self.assertEqual(result["right_value"], 9)

    def test_diff_reports_missing_semantic_event(self):
        result = diff_events(
            [event(0, 1), event(1, 2, order=1)],
            [event(0, 1)],
        )
        self.assertFalse(result["equal"])
        self.assertEqual(result["difference"], "missing_event")
        self.assertEqual(result["missing_from"], "right")
        self.assertEqual(result["semantic_key"]["layer"], 1)
        self.assertEqual(result["path"], "$")

    def test_diff_honors_numeric_tolerance_and_ignored_fields(self):
        left = event(0, 1.0)
        right = event(0, 1.0005, order=99)
        left["payload"]["diagnostic"] = "control"
        right["payload"]["diagnostic"] = "candidate"
        result = diff_events(
            [left],
            [right],
            ignore_fields=["payload.diagnostic"],
            atol=0.001,
        )
        self.assertTrue(result["equal"])

    def test_diff_ignores_process_local_pointers_unless_requested(self):
        left = event(0, 1)
        right = event(0, 1)
        left["payload"]["tensor"] = {"data_ptr": 100, "storage_ptr": 100}
        right["payload"]["tensor"] = {"data_ptr": 900, "storage_ptr": 900}

        self.assertTrue(diff_events([left], [right])["equal"])
        self.assertFalse(
            diff_events([left], [right], compare_pointers=True)["equal"]
        )

    def test_diff_reports_reordered_events(self):
        result = diff_events(
            [event(0, 1), event(1, 2, order=1)],
            [event(1, 2), event(0, 1, order=1)],
        )

        self.assertFalse(result["equal"])
        self.assertEqual(result["difference"], "event_order_or_identity")
        self.assertEqual(result["left_index"], 0)
        self.assertEqual(result["right_index"], 0)

    def test_tolerance_compares_sampled_values_instead_of_digest(self):
        left_tensor = tensor_metadata(
            FakeTensor([[1.0, 2.0]]), byte_mode="sample", max_bytes=64
        )
        right_tensor = tensor_metadata(
            FakeTensor([[1.0001, 2.0001]]), byte_mode="sample", max_bytes=64
        )
        left = event(0, 1)
        right = event(0, 1)
        left["payload"]["tensor"] = left_tensor
        right["payload"]["tensor"] = right_tensor

        self.assertFalse(diff_events([left], [right])["equal"])
        self.assertTrue(diff_events([left], [right], atol=0.001)["equal"])

    def test_tolerance_never_hides_a_complete_tensor_digest_difference(self):
        left = event(0, 1)
        right = event(0, 1)
        left["payload"]["tensor"] = tensor_metadata(
            FakeTensor([[1.0, 2.0]]), byte_mode="complete", max_bytes=128
        )
        right["payload"]["tensor"] = tensor_metadata(
            FakeTensor([[2.0, 1.0]]), byte_mode="complete", max_bytes=128
        )

        result = diff_events([left], [right], atol=10.0)

        self.assertFalse(result["equal"])
        self.assertTrue(
            "digest" in result["path"] or "bytes" in result["path"]
        )

    def test_sampled_and_complete_bytes_are_bounded(self):
        value = bytes(range(64))
        sampled = tensor_metadata(value, byte_mode="sample", max_bytes=9)["bytes"]
        complete = tensor_metadata(value, byte_mode="complete", max_bytes=7)["bytes"]

        self.assertEqual(sampled["captured_bytes"], 9)
        self.assertEqual(len(base64.b64decode(sampled["data"])), 9)
        self.assertFalse(sampled["complete"])
        self.assertEqual(complete["captured_bytes"], 7)
        self.assertEqual(len(base64.b64decode(complete["data"])), 7)
        self.assertFalse(complete["complete"])

    def test_cli_import_summary_and_diff(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            source = root / "source.jsonl"
            selected = root / "selected.jsonl"
            other = root / "other.jsonl"
            source.write_text(
                "\n".join(json.dumps(row) for row in [event(0, 1), event(1, 2)])
                + "\n"
            )
            other.write_text(json.dumps(event(1, 2)) + "\n")

            capture = subprocess.run(
                [
                    str(TOOL),
                    "capture",
                    str(source),
                    str(selected),
                    "--layer",
                    "1",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(capture.returncode, 0, capture.stderr)
            self.assertEqual(json.loads(capture.stdout)["captured_event_count"], 1)

            summary = subprocess.run(
                [str(TOOL), "summary", str(selected)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(summary.returncode, 0, summary.stderr)
            self.assertEqual(json.loads(summary.stdout)["event_count"], 1)

            difference = subprocess.run(
                [str(TOOL), "diff", str(selected), str(other)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(difference.returncode, 0, difference.stderr)
            self.assertTrue(json.loads(difference.stdout)["equal"])

    def test_disabled_recorder_has_no_output(self):
        recorder = Recorder.disabled()
        self.assertIsNone(recorder.tensor(object(), layer=1))
        self.assertEqual(recorder.events, ())

    def test_recorder_requires_explicit_resume_for_existing_capture(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = pathlib.Path(temporary) / "capture.jsonl"
            first = Recorder(path)
            first.record("marker", {"value": 1})
            with self.assertRaisesRegex(Exception, "resume=True"):
                Recorder(path)
            resumed = Recorder(path, resume=True)
            resumed.record("marker", {"value": 2})

            rows = read_jsonl(path)
            self.assertEqual([row["payload"]["value"] for row in rows], [1, 2])


if __name__ == "__main__":
    unittest.main()
