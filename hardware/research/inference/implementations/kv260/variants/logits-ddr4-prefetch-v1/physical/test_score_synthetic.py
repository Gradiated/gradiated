"""Exercise scorer on a deterministic synthetic fixture built from archived receipt shapes."""

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from score_fixture import HOMOGENEOUS_ORDER, MATRIX, MODES, ORDER, load, score
from measurement import ON_CHIP_CLOCKS, HOMOGENEOUS_REPLIES, SESSIONS, scored_positions


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
            count = scored_positions(header)
            reads, beats, useful = (count * n for n in (320, 2560, 20480))
            hidden = 1599 if mode == "prefetch" else 0
            extra = count * (2880 + 3680 - hidden)
            clocks = header["request_cycles"]
            extra_per_position = extra // count
            clocks["first"] += extra_per_position
            clocks["last"] += (count - 1) * extra_per_position
            clocks["done"] += extra
            row["ddr_counters_checked_ns"] = row["verified_ns"]
            row["ddr_counters"] = {
                "magic": 0x44445233, "mode": "ddr", "fault": False, "safe_release": False,
                "dma_base": "0x04000000", "hardware_base": "0x04000000", "dma_bytes": 20480,
                "transport_busy": False, "counter_saturated": False,
                "projection_count": count, "projections": count,
                "useful_bytes": useful, "reads": reads, "beats": beats,
                "faults": 0, "extra_clocks": extra, "ar_stalls": 0,
                "response_waits": count * 3680, "response_wait": count * 3680,
                "projection_clocks": count * 1680 + extra,
            }
        (target / name).write_text(json.dumps(val))
    version, raw = (source / "sampler.stdout").read_bytes().split(b"\n", 1)
    (target / "sampler.stdout").write_bytes(version + b"\n" + json.dumps(shift(json.loads(raw))).encode())
    (target / "sampler.stderr").touch()
    timing = {"setup_begin_ns": 1, "ready_ns": 2}
    (target / "load.json").write_text(json.dumps({
        "timing": timing,
        "matrix_setup_ns": 1000,
        "matrix_upload": {"dma_bytes": 20480, "dma_base": "0x04000000",
                          "hardware_base": "0x04000000", "matrix_sha256": MATRIX},
        "selected_status": {"safe_release": False, "mode": "ddr", "magic": 0x44445233,
                            "dma_base": "0x04000000", "hardware_base": "0x04000000"},
    }))
    (target / "quiesced.json").write_text(json.dumps({
        "magic": 0x44445233, "mode": "bram", "safe_release": True, "transport_busy": False,
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
    (root / "watchdog.json").write_text(json.dumps({"request_timeout_ns": 5_000_000_000}))
    sequence = 1
    for session, mode, rounds, series, prompts, smoke in SESSIONS:
        if smoke:
            target = root / f"smoke-{session}-{mode}"
            simulated_arm(target, 1, mode, sequence)
            warm = load(target / "warmup.json")
            copy = {r["case"]: r for r in warm["requests"]}
            for index, case in enumerate(ON_CHIP_CLOCKS):
                row = copy[case]
                head = row["observed"]["header"]
                shift = index * 10**9 + warm["begin_ns"] - head["admitted_ns"]
                head["admitted_ns"] += shift
                head["done_ns"] += shift
                head["output_ns"] = [v + shift for v in head["output_ns"]]
                for key in ("verified_ns", "ddr_counters_checked_ns"):
                    row[key] += shift
            warm["requests"] = list(copy[case] for case in ON_CHIP_CLOCKS)
            warm["begin_ns"] = warm["requests"][0]["observed"]["header"]["admitted_ns"]
            warm["end_ns"] = warm["requests"][-1]["verified_ns"]
            (target / "smoke.json").write_text(json.dumps(warm))
            sequence += 1
        for number in rounds:
            simulated_arm(root / f"p{number}-{mode}", number, mode, sequence)
            sequence += 1
        for case in prompts:
            target = root / f"homogeneous-p{series}-{case}-{mode}"
            simulated_homogeneous(target, series, case, mode, sequence)
            sequence += 1


class ScoreTest(unittest.TestCase):
    def test_complete_abba_score(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            make_fixture(root)
            report = score(root, HISTORIC)
            self.assertEqual(len(report["arms"]), 8)
            self.assertEqual(len(report["homogeneous_arms"]), 12)
            self.assertEqual(sum(len(a["requests"]) for a in report["homogeneous_arms"].values()), 152)
            self.assertEqual(sum(len(a["requests"]) for a in report["arms"].values()), 48)
            self.assertEqual(sum(len(a) for a in report["smokes"].values()), 9)
            prefetch = report["timing"]["prefetch"]["encoded-hello"]
            self.assertEqual(len(prefetch["hp0_projection_mb_s"]), 8)
            self.assertEqual(prefetch["hidden_clocks"], [91 * 1599] * 8)
            self.assertEqual(report["timing"]["sequential"]["encoded-hello"]["hidden_clocks"], [0] * 8)

    def test_prefetch_without_overlap_fails_counter_gate(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            make_fixture(root)
            file = root / "p1-prefetch/block.json"
            block = load(file)
            row = block["requests"][0]
            fixture = row["ddr_counters"]
            hidden = 1599 * fixture["projection_count"]
            fixture["extra_clocks"] += hidden
            fixture["projection_clocks"] += hidden
            row["observed"]["header"]["request_cycles"]["done"] += hidden
            file.write_text(json.dumps(block))
            with self.assertRaisesRegex(ValueError, "did not hide"):
                score(root, HISTORIC)


if __name__ == "__main__":
    unittest.main()
