"""Exercise scorer on a deterministic synthetic fixture built from archived receipt shapes."""

from copy import deepcopy
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from score_fixture import HOMOGENEOUS_ORDER, MATRIX, MODES, ORDER, load, score
from measurement import CONTROL_CLOCKS, HOMOGENEOUS_REPLIES, TRANSFER_COUNTS


def archived_reference():
    override = os.environ.get("KV260_EXP13_EVIDENCE")
    if override:
        return Path(override)
    for parent in Path(__file__).resolve().parents:
        archive = parent / ".agents/runtime/hardware/inference/outputs"
        if archive.is_dir():
            return archive / "attention-exp-pair-v2-20261117T232821Z-e72da4"
    return Path("/nonexistent-exp13-evidence")


HISTORIC = archived_reference()


def simulated_arm(target, pair, mode, sequence):
    source = HISTORIC / f"p{(pair-1) % 3 + 1}-candidate"
    shift_ns = sequence * 10**14

    def shift(value, key=None):
        if isinstance(value, dict):
            return {name: shift(item, name) for name, item in value.items()}
        if isinstance(value, list):
            return [shift(item, key) for item in value]
        if type(value) is int and ((key and key.endswith("_ns")) or key in ("active", "idle_before", "idle_after")) and value > 10**12:
            return value + shift_ns
        return value

    target.mkdir()
    for name in ("warmup.json", "block.json", "arm.json", "spi-boundary.json", "sampler-process.json"):
        val = shift(load(source / name))
        for row in val.get("requests", []):
            header = row["observed"]["header"]
            count = header["context_count"]
            reads, beats, useful = (count * n for n in TRANSFER_COUNTS[mode])
            extra = reads + beats + beats * 12
            if mode != "bram":
                clocks = header["request_cycles"]
                extra_per_position = extra // count
                clocks["first"] += len(header["prefix_ids"]) * extra_per_position
                clocks["last"] += (len(header["prefix_ids"]) + len(header["output_ids"]) - 1) * extra_per_position
                clocks["done"] += extra
            row["ddr_counters_checked_ns"] = row["verified_ns"]
            row["ddr_counters"] = {
                "magic": 0x44445232, "mode": mode, "fault": False,
                "transport_busy": False, "counter_saturated": False,
                "projection_count": count, "projections": count,
                "useful_bytes": useful, "reads": reads, "beats": beats,
                "faults": 0, "extra_clocks": extra, "ar_stalls": 0,
                "response_waits": beats * 12, "response_wait": beats * 12,
                "projection_clocks": count * 2112 + extra,
            }
        (target / name).write_text(json.dumps(val))
    version, raw = (source / "sampler.stdout").read_bytes().split(b"\n", 1)
    (target / "sampler.stdout").write_bytes(version + b"\n" + json.dumps(shift(json.loads(raw))).encode())
    (target / "sampler.stderr").touch()
    (target / "load.json").write_text(json.dumps({
        "matrix_setup_ns": 1000,
        "matrix_upload": {"dma_bytes": 2048, "dma_base": "0x04000000",
                          "hardware_base": "0x04000000", "matrix_sha256": MATRIX},
        "selected_status": {"mode": mode, "magic": 0x44445232,
                            "dma_base": "0x04000000", "hardware_base": "0x04000000"},
    }))
    (target / "quiesced.json").write_text(json.dumps({
        "magic": 0x44445232, "mode": "bram", "safe_release": True, "transport_busy": False,
        "dma_bytes": 0, "hardware_base": "0x00000000",
    }))


def simulated_homogeneous(target, pair, case, mode, sequence):
    simulated_arm(target, pair, mode, sequence)
    block = load(target / "block.json")
    warm = load(target / "warmup.json")
    arm = load(target / "arm.json")
    original = next(row for row in block["requests"] if row["case"] == case)
    warm_row = next(row for row in warm["requests"] if row["case"] == case)
    warm["requests"] = [warm_row]
    warm["begin_ns"] = warm_row["observed"]["header"]["admitted_ns"]
    warm["end_ns"] = warm_row["verified_ns"]
    arm["idle_context"] = original["observed"]["header"]["context_count"]
    begin, end = block["begin_ns"], block["end_ns"]
    span = original["verified_ns"] - original["observed"]["header"]["admitted_ns"]
    old_begin = original["observed"]["header"]["admitted_ns"]
    count = HOMOGENEOUS_REPLIES[case]

    def transform(value, key, first, duration):
        if isinstance(value, dict):
            return {k: transform(v, k, first, duration) for k, v in value.items()}
        if isinstance(value, list):
            return [transform(v, key, first, duration) for v in value]
        if type(value) is int and key.endswith("_ns") and value > 10**12:
            return first + ((value - old_begin) * duration // span)
        return value

    block["requests"] = []
    duration = (end - begin) // count
    for index in range(count):
        first = begin + index * duration
        width = (end - first) if index == count - 1 else duration
        block["requests"].append(transform(original, "", first, width))
    for name, payload in (("block.json", block), ("warmup.json", warm), ("arm.json", arm)):
        (target / name).write_text(json.dumps(payload))


def make_fixture(root):
    for number, (pair, mode) in enumerate(ORDER):
        simulated_arm(root / f"p{pair}-{mode}", pair, mode, number)
    for number, (pair, case, mode) in enumerate(HOMOGENEOUS_ORDER, len(ORDER)):
        simulated_homogeneous(root / f"homogeneous-p{pair}-{case}-{mode}",
                              pair, case, mode, number)
    for mode in MODES:
        smoke = root / f"smoke-{mode}"
        smoke.mkdir()
        warm = load(root / f"p1-{mode}" / "warmup.json")
        copy = {r["case"]: r for r in warm["requests"]}
        rows = warm["requests"]
        for index, case in enumerate(CONTROL_CLOCKS):
            row = copy[case]
            old = row["observed"]["header"]["admitted_ns"]
            first = rows[index]["observed"]["header"]["admitted_ns"]
            delta = first - old

            def shift(value, key=None):
                if isinstance(value, dict):
                    return {k: shift(v, k) for k, v in value.items()}
                if isinstance(value, list):
                    return [shift(v, key) for v in value]
                if type(value) is int and key and key.endswith("_ns") and value > 10**12:
                    return value + delta
                return value

            copy[case] = shift(row)
        # Give each smoke reply ample room before the following admission.
        for index, case in enumerate(CONTROL_CLOCKS):
            row = copy[case]
            source = row["observed"]["header"]["admitted_ns"]
            shift_by = (index + 1) * 10**9
            row["verified_ns"] += shift_by
            row["ddr_counters_checked_ns"] += shift_by
            head = row["observed"]["header"]
            head["admitted_ns"] = source + shift_by
            head["done_ns"] += shift_by
            head["output_ns"] = [n + shift_by for n in head["output_ns"]]
        warm["requests"] = list(copy[case] for case in CONTROL_CLOCKS)
        warm["begin_ns"] = warm["requests"][0]["observed"]["header"]["admitted_ns"]
        warm["end_ns"] = warm["requests"][-1]["verified_ns"]
        (smoke / "smoke.json").write_text(json.dumps(warm))


class ScoreTest(unittest.TestCase):
    @unittest.skipUnless(HISTORIC.exists(), "historic private receipts unavailable")
    def test_score_all_modes_without_pooling_single_prompt_energy(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            make_fixture(root)
            report = score(root, HISTORIC)
            self.assertEqual(len(report["arms"]), 16)
            self.assertEqual(len(report["homogeneous_arms"]), 24)
            self.assertEqual(sum(len(a["requests"]) for a in report["homogeneous_arms"].values()), 304)
            self.assertEqual(sum(len(a["requests"]) for a in report["arms"].values()), 96)
            self.assertEqual(len(report["timing"]["bram"]["encoded-hello"]["reads"]), 8)
            self.assertEqual(len(report["energy_pairs_pct"]["1"]), 6)
            self.assertGreater(report["timing_pairs_pct"]["1"]["encoded-hello"]
                               ["scalar_vs_bram"]["request_clocks"], 0)

    @unittest.skipUnless(HISTORIC.exists(), "historic private receipts unavailable")
    def test_rejects_nonquiescent_buffer(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            make_fixture(root)
            receipt = root / "p2-row" / "quiesced.json"
            bad = deepcopy(load(receipt))
            bad["dma_bytes"] = 2048
            receipt.write_text(json.dumps(bad))
            with self.assertRaisesRegex(ValueError, "DMA teardown did not verify"):
                score(root, HISTORIC)


if __name__ == "__main__":
    unittest.main()
