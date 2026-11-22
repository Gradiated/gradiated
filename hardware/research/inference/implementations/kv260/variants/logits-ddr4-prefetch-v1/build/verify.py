"""Verify the recovered Experiment 17 route, exact Experiment 16 control and release."""
import argparse
from collections import Counter
import importlib.util
import json
from pathlib import Path
import sys
import tarfile
from tempfile import TemporaryDirectory

from prepare import BASE_FIRMWARE, BASE_INPUT, BASE_PROGRAM, CHANGED_MODULES, DMA, FIRMWARE, PROGRAM, module_pins

CONTROL_ID = "logits-ddr4-burst-build-20261119T115915Z"
CONTROL_ARCHIVE = "6f2fba1a81698ca269dbfbc6cc7a63c564c10136d64a4e50a43d3b8cbedaf467"
CONTROL_DCP = "70281d404d0abbb157a74392a904f1b62f7a3d4f0b9120c50919f9c03256db64"
CONTROL_AUDIT = "4e852bd46a0722096ba93fe8ab1e43645aeab80d4054ec240079d2740f87ddce"
CONTROL_RUN = "05954557b90dd1207918d2689a46dd384be59ba74f2e7c584bf54f576c79fc9f"
FIXED = ("kv260-ddr4-interface.dtbo", "kv260-ddr4-afi-restore.dtbo", DMA + ".dtbo")
REPORTS = Path("build/reports")
CENSUS = "ddr-primitives.tsv"


def load(path):
    return json.loads(path.read_text())


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    saved = sys.modules.pop("prepare", None)
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(value)
    finally:
        sys.path.pop(0)
        sys.modules.pop("prepare", None)
        if saved is not None:
            sys.modules["prepare"] = saved
    return value


def verifiers(repo):
    variants = repo / "hardware/research/inference/implementations/kv260/variants"
    return tuple(module(variants / variant / "build/verify.py", variant) for variant in (
        "output-projection-ddr4-v1", "output-projection-ddr4-burst-v1", "logits-ddr4-burst-v1",
    ))


def timing(common, root):
    values = dict(line.split(maxsplit=1) for line in (root / REPORTS / "metrics.txt").read_text().splitlines())
    common.check(values["clock"] == "clk_pl_0 period_ns 20.000" and
                 all(values[key] == "1" for key in ("fully_placed", "fully_routed")) and
                 all(values[key] == "0" for key in (*common.ZERO_METRICS, "native_no_clock",
                                                     "unused_ps_clock_outputs")) and
                 all(float(values[key]) >= 0 for key in ("setup_slack_ns", "hold_slack_ns")),
                 "Incomplete routing or open setup/hold timing at 20 ns")
    return values


def accept_control(common, burst, serial, repo, control, control_rtl):
    old_result = repo / "hardware/research/inference/results" / CONTROL_ID
    old_run = old_result / "run.json"
    audit_path = old_result / "audit-manifest.json"
    common.check(common.sha(old_run) == CONTROL_RUN and common.sha(audit_path) == CONTROL_AUDIT,
                 "Experiment 16 durable record pins differ")
    common.check(common.sha(control / "build-input.tar.gz") == BASE_INPUT and
                 common.sha(control / "server.tar.gz") == CONTROL_ARCHIVE and
                 common.sha(control / "server/build/route/route.dcp") == CONTROL_DCP,
                 "Experiment 16 build input, full archive or routed checkpoint differs")
    old = load(old_run)
    configuration = old["device"]["configuration"]
    common.check(old["status"] == "passed" and configuration["tool"] == "Vivado 2025.2" and
                 configuration["clock_hz"] == 50_000_000 and configuration["threads"] == 2 and
                 configuration["part"] == "xck26-sfvc784-2LV-c", "Control configuration differs")
    control_server = control / "server"
    with tarfile.open(control / "server.tar.gz") as archive:
        for name in (serial.PSU_INIT, "source-manifest.json"):
            common.check(archive.extractfile(name).read() == (control_server / name).read_bytes(),
                         f"Extracted Experiment 16 bytes differ from the pinned archive: {name}")
    prior = load(control / "offline-acceptance.json")
    audit = load(audit_path)["files"]
    for path in (control / "offline-acceptance.json",
                 control_server / REPORTS / "metrics.txt",
                 control_server / REPORTS / "utilization-hierarchical.rpt",
                 control_server / REPORTS / CENSUS,
                 control_server / REPORTS / "ddr-routed-hp0.tsv",
                 control_server / "build/generate/ddr-interfaces.txt"):
        expected = audit[str(path.relative_to(repo))]
        common.check(common.sha(path) == expected["sha256"] and path.stat().st_size == expected["bytes"],
                     f"Control data differs from its archived pin: {path}")
    old_modules = module_pins(load(control_server / "source-manifest.json")["files"])
    common.check(old_modules == load(control_rtl), "Experiment 16 compiled module list differs from replay")
    clock = timing(common, control_server)
    common.check(prior["timing"] == clock, "Control timing differs from accepted route")
    burst.verify_bd(common, control_server)
    hp0 = serial.verify_pins(common, control_server / REPORTS / "ddr-routed-hp0.tsv")
    common.check(hp0 == prior["routed_hp0"], "Control native HP0 differs from accepted route")
    assets = {
        name: common.sha(control_server / path) for name, path in (
            (BASE_FIRMWARE + ".bit.bin", "offline-package/" + BASE_FIRMWARE + ".bit.bin"),
            (BASE_PROGRAM, BASE_PROGRAM), *((name, name) for name in FIXED),
        )
    }
    common.check(assets == prior["firmware_assets"], "Control deployment asset hashes differ")
    return old_run, old_modules, clock, hp0, assets


def footprint(serial, server):
    report = (server / REPORTS / "utilization-hierarchical.rpt").read_text()
    return {name: serial.row(report, instance) for name, instance in (
        ("fpga", "tiny_ps_axi_wrapper"), ("accelerator", "actual"),
        ("logits", "logits"), ("reader", "projection_reader"),
    )}


def buffer_halves(server):
    prefixes = ("low_reg", "high_reg")
    halves = {side: Counter() for side in prefixes}
    for line in (server / REPORTS / CENSUS).read_text().splitlines():
        path, primitive = line.split("\t")
        if "/projection_reader/" not in path:
            continue
        branch = path.split("/projection_reader/", 1)[1].split("/", 1)[0]
        for side in prefixes:
            if branch.startswith(side):
                halves[side][primitive] += 1
    return {side: dict(counts) for side, counts in halves.items()}


def account(common, serial, control, candidate):
    arms = {"control": control, "candidate": candidate}
    measured = {arm: footprint(serial, server) for arm, server in arms.items()}
    census = {arm: serial.primitive_counts(server / REPORTS / CENSUS) for arm, server in arms.items()}
    halves = {arm: buffer_halves(server) for arm, server in arms.items()}
    for arm, row in measured.items():
        common.check(census[arm]["embedding"] == {"RAMB36E2": 6, "RAMB18E2": 1},
                     f"{arm} embedding storage differs from Experiment 16")
        common.check(row["fpga"]["ramb36"] + row["fpga"]["ramb18"] / 2 == 31 and
                     row["fpga"]["dsp"] == 41 and row["logits"]["dsp"] == 8,
                     f"{arm} FPGA block storage or DSP count differs")
        common.check(all(row[group][key] == 0 for group in ("logits", "reader")
                         for key in ("ramb36", "ramb18", "uram")) and row["reader"]["dsp"] == 0,
                     f"{arm} reader or logits uses unexpected block storage or DSPs")
        common.check(halves[arm]["low_reg"] and halves[arm]["high_reg"] and
                     sum((Counter(part) for part in halves[arm].values()), Counter()) == Counter(census[arm]["reader"]),
                     f"{arm} staged halves cannot account for the reader memory primitives")
    hierarchy = {group: {arm: table[group] for arm, table in measured.items()}
                 for group in measured["control"]}
    device = {}
    for arm, hierarchy_rows in measured.items():
        row = hierarchy_rows["fpga"]
        device[arm] = {
            "lut": row["lut"], "register": row["register"], "dsp": row["dsp"],
            "bram_tile": row["ramb36"] + row["ramb18"] / 2,
        }
    buffers = {}
    for arm, group_count in (("control", 1), ("candidate", 2)):
        buffers[arm] = {
            "group_buffers": group_count, "bytes_per_group": 512,
            "bytes_total": group_count * 512, "physical_half_depth": group_count * 32,
            "physical_half_width_bits": 64, "routed_half_primitives": halves[arm],
            "routed_reader_lutram_luts": measured[arm]["reader"]["lutram"],
        }
    return hierarchy, device, census, buffers


def verify_archive(repo, work, control, tested, root):
    common, burst, serial = verifiers(repo)
    tested_record = load(tested)
    old_run, old_modules, old_timing, old_hp0, old_assets = accept_control(
        common, burst, serial, repo, control, work / "control-rtl-manifest.json")
    source_pin = common.sha(work / "admitted-source-manifest.json")
    admission = load(work / "admission.json")
    common.check(admission["manifest_sha256"] == source_pin, "Admitted source manifest hash differs")
    receipt = common.recover(work / "server.tar.gz", work / "server.receipt.json", root, source_pin)
    common.check(receipt["passed"] and load(root / "build-outcome.json")["passed"], "Candidate build did not complete")
    for phase in common.PHASES:
        phase_run = load(root / f"build/{phase}/phase.json")
        common.check(phase_run["phase"] == phase and phase_run["returncode"] == 0 and
                     phase_run["expected_output_exists"] and not phase_run["timed_out"], f"Incomplete {phase}")
    manifest = load(root / "source-manifest.json")
    candidate_rtl = work / "candidate-rtl-manifest.json"
    current_modules = module_pins(manifest["files"])
    common.check(manifest["protocol_sha256"] == common.sha(work / "admitted-protocol.md") and
                 old_modules == manifest["reused_control_modules"] and
                 manifest["reused_control_input_sha256"] == BASE_INPUT and
                 manifest["files"]["implementation/tools/ddr-shell.tcl"] ==
                 load(control / "server/source-manifest.json")["files"]["implementation/tools/ddr-shell.tcl"] and
                 current_modules.keys() == old_modules.keys() and
                 {name for name in old_modules if current_modules[name] != old_modules[name]} == CHANGED_MODULES,
                 "Admitted protocol, source changes or matched HP0 shell differs")
    common.check(tested_record["conditions"]["control_source_manifest_sha256"] ==
                 common.sha(work / "control-rtl-manifest.json"), "Control source differs from exact replay")
    replay = burst.verify_rtl(common, root, candidate_rtl, tested)
    candidate_timing = timing(common, root)
    old_server = control / "server"
    for filename in ("constraints-before.txt", "constraints-after.txt"):
        constraints = (root / REPORTS / filename).read_bytes()
        common.check(constraints == (old_server / REPORTS / filename).read_bytes() and
                     b"changed_rules 0\nwaiver_objects 0\nloop_allow_nets 0\nclock_route_overrides 0\n" in constraints,
                     f"Candidate route constraint guard differs: {filename}")
    common.check(common.ps_writes((root / serial.PSU_INIT).read_text()) ==
                 common.ps_writes((old_server / serial.PSU_INIT).read_text()),
                 "Candidate and control generated PS writes differ")
    burst.verify_bd(common, root)
    hp0 = serial.verify_pins(common, root / REPORTS / "ddr-routed-hp0.tsv")
    common.check(hp0 == old_hp0, "Candidate and control native HP0 parameters differ")
    hierarchy, device, census, buffers = account(common, serial, old_server, root)
    common.check(device["control"] == load(old_run)["conditions"]["resources"],
                 "Control routed totals differ from Experiment 16")
    serial.FIRMWARE, serial.PROGRAM = FIRMWARE, PROGRAM
    assets = serial.verify_package(common, root, control, "gradiated,kv260-ddr4-logits-v1")
    common.check(all(assets[name] == old_assets[name] for name in FIXED),
                 "DMA, interface or restoration overlay differs from control")
    common.check(assets[FIRMWARE + ".bit.bin"] != old_assets[BASE_FIRMWARE + ".bit.bin"],
                 "Candidate unexpectedly has the control image")
    return {
        "passed": True, "board_programmed": False,
        "control_checkpoint_sha256": CONTROL_DCP,
        "candidate_checkpoint_sha256": common.sha(root / "build/route/route.dcp"),
        "control_resources": device["control"], "resources": device["candidate"],
        "resource_accounting": {"hierarchy": hierarchy, "primitive_counts": census, "buffers": buffers},
        "control_timing": old_timing, "timing": candidate_timing, "routed_hp0": hp0,
        "generated_psu_matches_control": True, "rtl_replay": replay,
        "control_firmware_assets": old_assets, "firmware_assets": assets,
        "archive_sha256": receipt["sha256"], "archive_members": receipt["files"],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("repo", "work", "control", "tested"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    release = args.work / "server"
    acceptance = args.work / "offline-acceptance.json"
    if release.exists() or acceptance.exists():
        raise FileExistsError("This local work directory already has a published release")
    with TemporaryDirectory(prefix="verify-", dir=args.work) as scratch:
        root = Path(scratch) / "server"
        result = verify_archive(**vars(args), root=root)
        report = Path(scratch) / acceptance.name
        report.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        root.rename(release)
        report.rename(acceptance)
