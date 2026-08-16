#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

from request_state_observer import (
    make_event,
    pass_through,
    request_rows,
    split_by_lengths,
)


class ObserverFixtureTest(unittest.TestCase):
    def test_rids_exclude_padding_and_follow_row_reordering(self):
        self.assertEqual(
            request_rows(["rid-b", "rid-a"], [9, 4, 0, 0]),
            [(0, 9, "rid-b"), (1, 4, "rid-a")],
        )
        self.assertEqual(
            request_rows(["rid-a", "rid-c"], [4, 9]),
            [(0, 4, "rid-a"), (1, 9, "rid-c")],
        )

    def test_slot_recycling_is_physical_telemetry_not_logical_identity(self):
        self.assertEqual(request_rows(["rid-old"], [6]), [(0, 6, "rid-old")])
        self.assertEqual(request_rows(["rid-new"], [6]), [(0, 6, "rid-new")])

    def test_rid_contract_fails_closed(self):
        with self.assertRaises(ValueError):
            request_rows(None, [1])
        with self.assertRaises(ValueError):
            request_rows(["rid-a", "rid-b"], [1])
        with self.assertRaises(ValueError):
            request_rows(["rid-a", "rid-a"], [1, 2])

    def test_split_contract(self):
        self.assertEqual(split_by_lengths([1, 2, 3], [2, 1]), [[1, 2], [3]])
        with self.assertRaises(ValueError):
            split_by_lengths([1, 2], [1])

    def test_pass_through_identity(self):
        sentinel = object()
        observed = []
        returned = pass_through(lambda: sentinel, observed.append)
        self.assertIs(returned, sentinel)
        self.assertEqual(observed, [sentinel])

    def test_event_is_deterministic_and_complete(self):
        digest = hashlib.sha256(b"fixture-kv").hexdigest()
        kwargs = {
            "arm": "dflash-depth4-c32",
            "phase": "first_target_step",
            "request_id": "fixture-rid-25",
            "request_slot": 9,
            "sequence_length_before": 4214,
            "sequence_length_after": 4215,
            "kv_locations": [101],
            "kv_content_sha256": digest,
            "payload": {
                "verified_id": 236814,
                "target_top1": [3496, 10, 11, 12],
                "accepted_prefix": [],
                "bonus_token": 3496,
                "emitted_stream_tokens": [3496],
            },
        }
        left = make_event(**kwargs)
        right = make_event(**kwargs)
        self.assertEqual(left, right)
        self.assertEqual(len(left["event_sha256"]), 64)

    def test_serialized_consumer_localizes_request_25_first_verifier(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            capture = root / "capture"
            (capture / "states").mkdir(parents=True)
            prior = {"control": {}, "candidate": {}}
            for arm in ("ar-c32", "dflash-depth4-c32"):
                rows = [
                    {
                        "index": index,
                        "request_id": f"fixture-{arm}-{index}",
                        "request_sha256": hashlib.sha256(str(index).encode()).hexdigest(),
                        "token_ids": [index, 3496],
                        "prompt_tokens": 4214,
                        "completion_tokens": 358,
                        "cached_tokens": 535,
                        "finish_reason": {"type": "length", "length": 358},
                    }
                    for index in range(32)
                ]
                terminal = {
                    "pass": True,
                    "complete_requests": 32,
                    "raw_token_ids_present": True,
                    "rows": rows,
                }
                arm_root = capture / "results" / arm
                arm_root.mkdir(parents=True)
                (arm_root / "TERMINAL.json").write_text(json.dumps(terminal))
                prior["control" if arm == "ar-c32" else "candidate"] = terminal
                events = []
                for phase in ("target_prefill", "first_target_step"):
                    for index in range(32):
                        if phase == "target_prefill":
                            payload = {
                                "target_prefill_output": index,
                                "target_top1": index,
                                "prompt_cache_accounting": {
                                    "prefix_tokens": 535,
                                    "fresh_tokens": 3679,
                                    "total_tokens": 4214,
                                },
                            }
                            before, after = 535, 4214
                        else:
                            target = 3496
                            if arm == "dflash-depth4-c32" and index == 25:
                                target = 759
                            payload = {
                                "verified_id": index,
                                "target_top1": target if arm == "ar-c32" else [target, 2, 3, 4],
                                "accepted_prefix": [],
                                "bonus_token": target,
                                "emitted_stream_tokens": [target],
                            }
                            if arm != "ar-c32":
                                payload["commit_length"] = 1
                            before, after = 4214, 4215
                        events.append(
                            make_event(
                                arm=arm,
                                phase=phase,
                                request_id=f"fixture-{arm}-{index}",
                                request_slot=index + 10,
                                sequence_length_before=before,
                                sequence_length_after=after,
                                kv_locations=[index + 100],
                                kv_content_sha256=hashlib.sha256(
                                    f"{phase}-{index}".encode()
                                ).hexdigest(),
                                payload=payload,
                            )
                        )
                (capture / "states" / f"{arm}.jsonl").write_text(
                    "".join(json.dumps(event, sort_keys=True) + "\n" for event in events)
                )
            prior_path = root / "prior.json"
            prior_path.write_text(json.dumps(prior))
            result_path = root / "result.json"
            terminal_path = root / "terminal.json"
            process = subprocess.run(
                [
                    "python3",
                    str(pathlib.Path(__file__).with_name("summarize_request_state_capture.py")),
                    "--root",
                    str(capture),
                    "--prior",
                    str(prior_path),
                    "--result",
                    str(result_path),
                    "--terminal",
                    str(terminal_path),
                ],
                check=False,
            )
            self.assertEqual(process.returncode, 0)
            terminal = json.loads(terminal_path.read_text())
            self.assertEqual(terminal["classification"], "localized_first_target_verifier")
            self.assertEqual(
                terminal["first_differing_captured_state"]["request_index"], 25
            )
            candidate_result = root / "candidate-result.json"
            candidate_terminal = root / "candidate-terminal.json"
            process = subprocess.run(
                [
                    "python3",
                    str(
                        pathlib.Path(__file__).with_name(
                            "summarize_candidate_request_state_capture.py"
                        )
                    ),
                    "--ar-terminal",
                    str(capture / "results" / "ar-c32" / "TERMINAL.json"),
                    "--candidate-terminal",
                    str(
                        capture
                        / "results"
                        / "dflash-depth4-c32"
                        / "TERMINAL.json"
                    ),
                    "--candidate-states",
                    str(capture / "states" / "dflash-depth4-c32.jsonl"),
                    "--result",
                    str(candidate_result),
                    "--terminal",
                    str(candidate_terminal),
                ],
                check=False,
            )
            self.assertEqual(process.returncode, 0)
            terminal = json.loads(candidate_terminal.read_text())
            self.assertEqual(
                terminal["classification"], "localized_first_target_verifier"
            )
            self.assertEqual(
                terminal["first_differing_captured_state"]["request_index"], 25
            )

    def test_cpu_kv_digest_layout_is_bounded_and_deterministic(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = pathlib.Path(temporary) / "capture.jsonl"
            os.environ["REQUEST_STATE_CAPTURE"] = str(output)
            os.environ["REQUEST_STATE_ARM"] = "ar-c32"
            path = pathlib.Path(__file__).with_name(
                "request_state_capture_sitecustomize.py"
            )
            spec = importlib.util.spec_from_file_location("fixture_sitecustomize", path)
            module = importlib.util.module_from_spec(spec)
            assert spec.loader is not None
            spec.loader.exec_module(module)
            sys.settrace(None)
            raw = bytes(range(24))
            kwargs = {
                "layer_planes": 4,
                "flat_count": 3,
                "sample_itemsize": 2,
                "offsets": [(0, 2), (2, 3)],
            }
            first = module._hash_plane_segments(raw, **kwargs)
            second = module._hash_plane_segments(raw, **kwargs)
            self.assertEqual(first, second)
            expected = hashlib.sha256(
                raw[0:4] + raw[6:10] + raw[12:16] + raw[18:22]
            ).hexdigest()
            self.assertEqual(first[0], expected)
            self.assertEqual(
                module._split_locations([10, 11, 12, 0, 0], [2, 1]),
                [[10, 11], [12]],
            )


if __name__ == "__main__":
    unittest.main()
