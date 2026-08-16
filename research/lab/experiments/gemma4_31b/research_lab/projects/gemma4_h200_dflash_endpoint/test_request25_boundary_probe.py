#!/usr/bin/env python3
"""Deterministic CPU fixtures for the request-25 boundary probe."""

from __future__ import annotations

import hashlib
import importlib.util
import pathlib
import unittest

from request25_boundary_probe import (
    hash_plane_segments,
    make_boundary_record,
    request_rows,
    row_major_slice,
    select_request_row,
    semantic_request_sha256,
)
from request25_payload_adapter import (
    REQUEST_INPUT_IDS_SHA256,
    REQUEST_SEMANTIC_SHA256,
    is_request25,
)

ROOT = pathlib.Path(__file__).resolve().parent
EXPECTED_REQUEST_SHA = (
    "ee2edfa7a9ff571b0268966f506c4cb868868ab880ac87c2684b055d48a0e150"
)
EXPECTED_SOURCE = {
    "dflash_info.py": "f17c37c1d0047e75f3214ec67cf2b02dd52cfcec35cf0daaaee0407f892a0e53",
    "dflash_info_v2.py": "eb976179a5ec54d607bfaf66e087c04d1c39617f312c105081974a3a8aa9de08",
    "dflash_utils.py": "f6935ff13d8b0c24ab2b443509ba8425918f8b4a6fafc520cd8a875f91891030",
    "dflash_worker_v2.py": "8fbddb39f4b33b4ac55b1919bc58fa846acb60892886199251d3592a5223050f",
}


def load_runner():
    spec = importlib.util.spec_from_file_location(
        "dflash_endpoint_runner", ROOT / "dflash_endpoint_runner.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Request25BoundaryProbeTest(unittest.TestCase):
    def test_request25_identity_preserves_exact_body(self):
        runner = load_runner()
        prefix = runner.tokens("common-prefix", runner.COMMON_TOKENS)
        suffix = runner.tokens(
            "suffix-25", runner.PROMPT_TOKENS - runner.COMMON_TOKENS
        )
        suffix[0] = 200025
        body = {
            "input_ids": prefix + suffix,
            "sampling_params": {
                "max_new_tokens": runner.OUTPUT_TOKENS,
                "min_new_tokens": runner.OUTPUT_TOKENS,
                "ignore_eos": True,
                "temperature": 0,
                "sampling_seed": 20260718,
            },
            "stream": True,
        }
        self.assertEqual(semantic_request_sha256(body), EXPECTED_REQUEST_SHA)
        before = dict(body)
        self.assertTrue(is_request25(body))
        self.assertEqual(body, before)
        self.assertNotIn("rid", body)

    def test_request25_only_logical_rid_selection_excludes_padding(self):
        request_rid = "runtime-generated-request-25-rid"
        rids = ["req-a", request_rid, "req-c"]
        slots = [5, 13, 8, 0, 0]
        self.assertEqual(
            request_rows(rids, slots),
            [(0, 5, "req-a"), (1, 13, request_rid), (2, 8, "req-c")],
        )
        self.assertEqual(select_request_row(rids, slots, request_rid), (1, 13))
        self.assertIsNone(select_request_row(rids, slots, "missing"))

    def test_slot_rebinding_cannot_replace_logical_identity(self):
        slots = [13, 5, 0]
        request_rid = "runtime-generated-request-25-rid"
        self.assertEqual(
            select_request_row(["new-request", request_rid], slots, request_rid),
            (1, 5),
        )
        self.assertNotEqual(
            select_request_row(["new-request", request_rid], slots, request_rid),
            (0, 13),
        )

    def test_row_position_length_and_output_location_alignment(self):
        self.assertEqual(
            row_major_slice(
                list(range(12)), row=1, rows=3, width=4, field="input_ids"
            ),
            [4, 5, 6, 7],
        )
        with self.assertRaisesRegex(ValueError, "rows\\*width"):
            row_major_slice(
                list(range(11)), row=1, rows=3, width=4, field="positions"
            )

    def test_pre_post_labels_are_not_swapped(self):
        digest = "0" * 64
        record = make_boundary_record(
            request_id="runtime-generated-request-25-rid",
            request_index=25,
            request_semantic_sha256=EXPECTED_REQUEST_SHA,
            request_input_ids_sha256=REQUEST_INPUT_IDS_SHA256,
            request_row=1,
            request_slot=13,
            input_ids=[236814, 174501, 74443, 104105],
            positions=[4214, 4215, 4216, 4217],
            seq_len=4,
            seq_len_cpu=4,
            out_cache_loc=[70, 71, 72, 73],
            req_to_token_prefix=[11, 12, 13, 14],
            pre_forward_kv_sha256=digest,
            kv_digest_stats={"scheme": "fixture"},
            raw_first_position_top1=759,
            post_adjustment_first_position_top1=3496,
            source_binding_sha256="1" * 64,
        )
        boundary = record["logits_boundary"]
        self.assertEqual(boundary["raw_first_position_top1"], 759)
        self.assertEqual(boundary["post_adjustment_first_position_top1"], 3496)
        self.assertEqual(len(record["record_sha256"]), 64)

    def test_plane_digest_covers_every_plane_for_selected_segment(self):
        raw = bytes(range(12))
        observed = hash_plane_segments(
            raw,
            layer_planes=2,
            flat_count=6,
            sample_itemsize=1,
            offsets=[(1, 3)],
        )
        self.assertEqual(observed, [hashlib.sha256(bytes([1, 2, 7, 8])).hexdigest()])

    def test_exact_source_hashes_and_trace_anchors(self):
        packet_source = pathlib.Path(
            __import__("os").environ["REQUEST25_FIXTURE_SOURCE_ROOT"]
        )
        for name, expected in EXPECTED_SOURCE.items():
            self.assertEqual(
                hashlib.sha256((packet_source / name).read_bytes()).hexdigest(),
                expected,
            )
        worker = (packet_source / "dflash_worker_v2.py").read_text().splitlines()
        self.assertIn("target_out =", worker[527])
        self.assertIn("if sampling_info is not None:", worker[536])
        self.assertIn("candidates = draft_tokens", worker[543])
        info = (packet_source / "dflash_info.py").read_text()
        utils = (packet_source / "dflash_utils.py").read_text()
        self.assertIn("def prepare_for_v2_verify(", info)
        self.assertIn("def apply_dflash_verify_logits_adjustments(", utils)


if __name__ == "__main__":
    unittest.main()
