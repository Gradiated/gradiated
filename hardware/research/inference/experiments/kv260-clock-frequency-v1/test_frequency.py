"""Offline tests for the Exp24 clock fixture and standard mixed/prompt power score."""

from copy import deepcopy
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase, main

from prepare_fixture import pin, prepare


REPO = Path.cwd()
TEMP = TemporaryDirectory()
PACKET = Path(TEMP.name) / "packet"
prepare(REPO, PACKET)
sys.path.insert(0, str(PACKET))

import autonomous_comparison as comparison
import clock_boundary as clock
from frequency_fixture import native_source
from measurement import CASES, HOMOGENEOUS_REPLIES, MODES, REQUEST_NS, SESSIONS, mixed_order
from score_frequency import audit, findings


CONFIG = clock.read_json(PACKET / "measurement-plan.json")
CONFIG["clock_contract"] = {
    "pl0": {mode: {"configured_hz": hz, "parent": "iopll", "parent_hz": 999_999_990,
                   "dividers": {"div0": div, "div1": 1}, "enabled": True}
            for mode, hz, div in zip(MODES, (50_000_000, 52_631_579), (20, 19), strict=True)},
    "unrelated_clocks": {"spi1_ref": ["iopll", 199_999_998]},
}
TEMPLATE = {row["case"]: row["observed"]["header"]
            for row in clock.read_json(PACKET / "reference/p1-candidate/warmup.json")["requests"]}
PERIOD = 50_000_000
NS = 1_000_000_000


def snapshot(mode):
    return {"boot": CONFIG["boot"], "image": deepcopy(CONFIG["image"]),
            "pl0": deepcopy(CONFIG["clock_contract"]["pl0"][mode]),
            "unrelated_clocks": deepcopy(CONFIG["clock_contract"]["unrelated_clocks"])}


def block(order, start, mode):
    rows = []
    hz = CONFIG["clock_contract"]["pl0"][mode]["configured_hz"]
    def duration(clocks):
        return (clocks * NS + hz - 1) // hz
    for index, case in enumerate(order):
        admitted = start + index * 260_000_000
        header = deepcopy(TEMPLATE[case])
        counters = header["request_cycles"]
        n = len(header["output_ids"])
        begin = admitted + 50_000
        done = begin + duration(counters["done"]) + 10_000
        header.update(admitted_ns=admitted, done_ns=done,
                      output_ns=[begin + duration(counters["first"] + k * (counters["last"] - counters["first"]) // (n-1))
                                 for k in range(n)])
        header["timing"]["inference_begin_ns"] = begin
        rows.append(dict(case=case, observed=dict(frames=[], header=header), verified_ns=done + 100_000))
    return dict(begin_ns=start, end_ns=rows[-1]["verified_ns"], requests=rows)


def write_boundary(path, name, when, mode):
    clock.write_json(path / f"clock-{name}.json", {"begin_ns":when, "end_ns":when+10, "readback":snapshot(mode)})


def power_block(path, start, mode, warm, timed):
    start += 3 * NS
    warmup = block(warm, start - 2 * NS, mode)
    active = block(timed, start + 3 * NS, mode)
    begin, stop = active["begin_ns"], active["end_ns"]
    phases = {"active": [begin, stop], "idle_before": [start + 500_000_000, start + 2_500_000_000],
              "idle_after": [stop + 500_000_000, stop + 2_500_000_000]}
    sensor = {"state": "test"}
    spi = {"before": dict(begin_ns=begin-1000, end_ns=begin-500, active_ms=1, transfers=1),
           "after": dict(begin_ns=stop+500, end_ns=stop+1000, active_ms=1, transfers=1)}
    end = start + 350 * PERIOD
    arm = {"idle_context": TEMPLATE[timed[-1]]["context_count"], "before":sensor, "after":sensor,
           "schedule_start_ns":start, "phases":phases, "spi":spi}
    trace = {"schema":"kv260-power-pairs-sampler-v1", "uid":1000, "before":sensor, "after":sensor,
             "start_ns":start, "slots":350, "period_ns":PERIOD, "max_late_ns":PERIOD//2,
             "end_ns":end, "process_cpu_ns":0, "missed":[],
             "samples":[dict(slot=i,begin_ns=start+i*PERIOD,end_ns=start+i*PERIOD+1000,raw="311") for i in range(350)]}
    path.mkdir()
    for name, data in (("warmup",warmup),("block",active),("arm",arm),("spi-boundary",spi),("sampler-process",{"exit":0}),
                       ("load",{"timing":{"setup_begin_ns":1,"ready_ns":2}}),
                       ("power-eligibility", {"admitted":True,"max_contributing_gap_ns":75_000_000})):
        clock.write_json(path / f"{name}.json", data)
    (path / "sampler.stdout").write_text("READY\n"+json.dumps(trace))
    (path / "sampler.stderr").touch()
    for edge, when in (("before",warmup["begin_ns"]-1000),("active-before",begin-2000),("active-after",stop+2000), ("after",end+1000)):
        write_boundary(path, edge, when, mode)
    for edge, when in (("before",warmup["begin_ns"]-100),("after",end+100)):
        clock.write_json(path / f"temperatures-{edge}.json", {"begin_ns":when,"end_ns":when+10,
                         "sensors":[{"label":"synthetic", "value":27000}]})


def evidence(root):
    clock.write_json(root / "watchdog.json", {"request_timeout_ns": REQUEST_NS})
    now = 1000 * NS
    for session, mode, rounds, series, prompts, smoke in SESSIONS:
        if smoke:
            path = root / f"smoke-{session}-{mode}"
            path.mkdir()
            data = block(CASES, now, mode)
            clock.write_json(path / "smoke.json", data)
            write_boundary(path, "before", now-1000, mode)
            write_boundary(path, "after", data["end_ns"]+1000, mode)
            now += 100 * NS
        for pair in rounds:
            power_block(root / f"p{pair}-{mode}", now, mode, *mixed_order(pair))
            now += 100 * NS
        for case in prompts:
            power_block(root / f"homogeneous-p{series}-{case}-{mode}", now, mode, [case], [case] * HOMOGENEOUS_REPLIES[case])
            now += 100 * NS


class FrequencyTest(TestCase):
    def test_complete_synthetic_abba(self):
        with TemporaryDirectory() as name:
            root = Path(name)
            evidence(root)
            score = audit(root, PACKET, CONFIG)
            self.assertEqual(score["counts"], {"smoke": 9, "warmups": 36, "timed": 200, "powered_blocks": 20})
            self.assertEqual(len(score["clock_readbacks"]), 23)
            self.assertAlmostEqual(score["configured_rate_prediction"]["device_time_ratio"], 0.95)
            for group in score["pooled_energy"].values():
                self.assertEqual(group["control"]["useful_tokens"], group["candidate"]["useful_tokens"])
                self.assertLess(group["candidate"]["gross_j_answer"], group["control"]["gross_j_answer"])
            self.assertIn("Configured".lower(), findings(score).lower())

    def test_16_divider_contract(self):
        values = deepcopy(CONFIG)
        values["clock_contract"]["pl0"]["candidate"].update(configured_hz=62_500_000, dividers={"div0":16,"div1":1})
        with self.assertRaisesRegex(ValueError, "lacks admitted timing"):
            clock.validate_config(values)
        values["qualified_rates_hz"]["62500000"] = 62_503_906
        clock.validate_config(values)
        values["clock_contract"]["pl0"]["candidate"]["dividers"]["div0"] = 19
        with self.assertRaisesRegex(ValueError, "reconciled"):
            clock.validate_config(values)

    def test_rate_image_unrelated_clock_and_enable_changes_rejected_with_receipt(self):
        for key, value in (("boot", "changed"), ("image", {}), ("unrelated_clocks", {}),
                           ("pl0", {**snapshot("candidate")["pl0"], "enabled": False})):
            with self.subTest(key=key), TemporaryDirectory() as name:
                path = Path(name)
                observed = {**snapshot("candidate"), key: value}
                now = iter((1, 2)).__next__
                with self.assertRaisesRegex(ValueError, "differs"):
                    clock.capture(path, "before", CONFIG, "candidate", lambda: observed, now)
                self.assertEqual(clock.read_json(path / "clock-before.json")["readback"], observed)

    def test_cycle_mismatch_rejected(self):
        with TemporaryDirectory() as name:
            root = Path(name)
            evidence(root)
            path = root / "p1-candidate/block.json"
            damaged = clock.read_json(path)
            damaged["requests"][0]["observed"]["header"]["request_cycles"]["first"] += 1
            path.write_text(json.dumps(damaged))
            with self.assertRaisesRegex(ValueError, "FPGA clocks"):
                audit(root, PACKET, CONFIG)

    def test_missing_power_slot_rejected(self):
        with TemporaryDirectory() as name:
            root = Path(name)
            evidence(root)
            path = root / "p1-candidate/sampler.stdout"
            trace = json.loads(path.read_text().split("\n", 1)[1])
            removed = trace["samples"].pop(65)
            trace["missed"].append({"slot":removed["slot"], "observed_ns":removed["begin_ns"]+PERIOD//2})
            path.write_text("READY\n"+json.dumps(trace))
            with self.assertRaisesRegex(ValueError, "gap over 75 ms"):
                audit(root, PACKET, CONFIG)

    def test_native_and_host_guards_allow_the_qualified_rate_only(self):
        src = REPO / "hardware/research/inference/implementations/kv260/tools/board_bos.py"
        observed = native_source(src.read_bytes(), (50_000_000, 52_631_579))
        self.assertIn(b"rate in (50000000, 52631579)", observed)
        row = block([CASES[0]], 1000, "candidate")["requests"][0]
        header = row["observed"]["header"]
        header["timing"].update(index=0, clear=None, previous_context_count=0,
                                inference_end_ns=header["done_ns"]+1)
        header["returned_ns"] = header["done_ns"]+2
        runtime = SimpleNamespace(VOCAB=320, compare_reference=lambda *args: None)
        with self.assertRaisesRegex(ValueError, "work or output"):
            comparison.verify_row(runtime, row, None, 0, 0, 1, True)
        self.assertEqual(comparison.verify_row(runtime, row, None, 0, 0, 1, True, 52_631_579), header["context_count"])

    def test_separate_qualified_image_derives_both_names(self):
        with TemporaryDirectory() as name:
            root = Path(name)
            new_image = "gradiated-tiny-test-alt-62p5mhz.bit.bin"
            new_dtbo = "kv260-test-alt-program.dtbo"
            new_overlay = "gradiated-tiny-test-alt-program"
            image_bytes, overlay_bytes = b"synthetic image", b"synthetic overlay"
            (root / "server/offline-package").mkdir(parents=True)
            (root / "server/offline-package" / new_image).write_bytes(image_bytes)
            (root / "server" / new_dtbo).write_bytes(overlay_bytes)
            receipt = root / "offline-acceptance.json"
            rates = (50_000_000, 62_500_000)
            accepted = {"passed": True, "board_programmed": False, "same_image_for_all_passing_rates": True,
                        "protocol_sha256": CONFIG["protocol_sha256"], "qualified_nominal_rates_hz": rates,
                        "timing_profiles": {str(hz): {"admitted": True, "nominal_rate_hz": hz, "upper_qualified_rate_hz": hz,
                                                       "setup_slack_ns": 1.0, "hold_slack_ns": 0.01, "pulse_width_slack_ns": 8.0}
                                            for hz in rates}, "firmware": {"filename": new_image, **pin(image_bytes)},
                        "program_overlay": {"filename": new_dtbo, **pin(overlay_bytes)}, "live_program_overlay": new_overlay}
            clock.write_json(receipt, accepted)
            output = root / "alternate"
            prepare(REPO, output, receipt)
            config = {**clock.read_json(output / "measurement-plan.json"), "clock_contract": deepcopy(CONFIG["clock_contract"])}
            config["clock_contract"]["pl0"]["candidate"].update(configured_hz=62_500_000, dividers={"div0":16,"div1":1})
            clock.validate_config(config)
            observed = config["image"]
            self.assertEqual(observed, {"name": new_image, "sha256": pin(image_bytes)["sha256"]})
            self.assertEqual(config["overlay"], {"name": new_dtbo, "live": new_overlay})
            for mode in MODES:
                clock.verify_snapshot(config, mode, {**snapshot(mode), "image": observed, "pl0": config["clock_contract"]["pl0"][mode]})
            helper = (output / "observer_lifecycle.py").read_text()
            self.assertIn(f"OBSERVER_FILE = '{new_image}'", helper)
            self.assertIn(f"OBSERVER_OVERLAY = '{new_overlay}'", helper)
            self.assertIn(f"OBS_DTBO = '{new_dtbo}'", helper)
            self.assertIn(new_image, (output / "candidate_sampler.py").read_text())
            (root / "server" / new_dtbo).write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "Invalid source digest"):
                prepare(REPO, root / "invalid", receipt)

    def test_unmatched_fixture_image_fails_config(self):
        config = deepcopy(CONFIG)
        config["image"]["sha256"] = "f"*64
        with self.assertRaisesRegex(ValueError, "Same-firmware"):
            clock.validate_config(config)


if __name__ == "__main__":
    main()
