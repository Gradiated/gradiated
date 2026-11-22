"""Run a matched, resident measurement or smoke check on an admitted fixture."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time

from measurement import CountedDelivery, CONTROL_CLOCKS, HOMOGENEOUS_REPLIES, MODES
from weights import Fixture
from contextlib import nullcontext
import autonomous_comparison as comparison
import autonomous_runtime as runtime
import board_resident as resident
import board_resident_benchmark as bench
import energy_analysis as analysis
import energy_validation as energy
import observer_lifecycle as lifecycle
import observer_validation as validation
import resident_validation as prior


HERE = Path(__file__).resolve().parent
MAGIC = 0x44445233


def block_cases(pair, prompt=None):
    if prompt is None:
        return validation.cases(bench, (pair - 1) % 3)
    return [(prompt,False)], [(prompt,True)]*HOMOGENEOUS_REPLIES[prompt]


def read_fixture(port, mode):
    data = port.state()
    if (data["magic"] != MAGIC or data["transport_busy"] or data["fault"]
            or data["counter_saturated"] or data["mode"] != mode
            or data["safe_release"] != (mode == "bram")
            or bool(int(data["status_raw"], 16) & 1) != (mode != "bram")):
        raise ValueError("DDR fixture did not finish in the selected idle mode")
    return {**data, "response_waits": data["response_wait"], "projections": data["projection_count"]}


def manifest_pin(path):
    data = path.read_bytes()
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def prepare_bundle(config, bundle, mode):
    """Create a fixture-specific bundle from the sealed conditioned package."""
    original = prior.CANDIDATE
    resident.sealed_runner(original)["checked_bundle"](original)
    manifest = json.loads(resident.read_pinned(original/"package.json", resident.PACKAGE_SHA256))
    original_runner = resident.read_pinned(original/"board_bos.py", resident.SEALED_RUNNER_SHA256)
    assets = config["arms"][mode]
    source = lifecycle.rewritten(
        original_runner, b"FIRMWARE = 'gradiated-tiny-50mhz.bit.bin'",
        f"FIRMWARE = '{assets['firmware']}'".encode())
    if mode == "ddr":
        source = lifecycle.rewritten(source, b"reg != (0, 0xa0000000, 0, 0x100)",
                                     b"reg != (0, 0xa0000000, 0, 0x60)")
    bundle.mkdir(mode=0o700)
    old_files = manifest["files"]
    replacements = {"board_bos.py", "gradiated-tiny-50mhz.bit.bin",
                    "kv260-program.dtbo", "kv260-interface.dtbo"}
    for name, pin in old_files.items():
        if name not in replacements:
            (bundle/name).write_bytes(lifecycle.pinned(original/name, pin))
    (bundle/"board_bos.py").write_bytes(source)
    for name, key in [(assets["firmware"], "firmware"), ("kv260-program.dtbo", "program_overlay"),
                      ("kv260-interface.dtbo", "interface_overlay")]:
        src = HERE/assets[key]
        (bundle/name).write_bytes(lifecycle.pinned(src, config["pins"][src.name]))
    manifest["supersedes_manifest_sha256"] = resident.PACKAGE_SHA256
    manifest["files"] = {p.name:manifest_pin(p) for p in sorted(bundle.iterdir())}
    (bundle/"package.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n")
    return manifest_pin(bundle/"package.json")


def run(config, output, mode, pair, smoke, homogeneous=None):
    if os.geteuid()!=0 or Path("/proc/sys/kernel/random/boot_id").read_text().strip()!=config["boot"]:
        raise ValueError("Privileged fixture owner on the admitted boot required")
    if homogeneous is not None and (smoke or pair not in (1,2) or homogeneous not in HOMOGENEOUS_REPLIES):
        raise ValueError("Homogeneous energy blocks are timed in two matched passes")
    output.mkdir(mode=0o700)
    verify = prior.load_pinned(prior.ACCEPTANCE/"kv260_accept_checks.py", prior.CHECKS_PIN)
    frozen = verify.load_inputs(prior.ORIGINAL, prior.CANDIDATE, prior.ACCEPTANCE)
    refs = prior.load_fresh(prior.SPEED, verify, frozen)
    bundle = HERE / f"fixture-bundle-{mode}"
    pin = config["bundle_pins"][mode]
    deadline=time.monotonic()+config["arm_timeout_s"]
    def remaining():
        if time.monotonic()>=deadline:
            raise TimeoutError("Experiment 16 arm deadline")
    with (Fixture() if mode == "ddr" else nullcontext()) as fixture:
        with lifecycle.open_arm("candidate", resident, bundle, pin) as runner:
            # Native begin resets and reloads the model before selecting its weight source.
            load_report = validation.load_metadata(runner)
            validation.validate_load(load_report, prior)
            try:
                if fixture is not None:
                    begin = time.monotonic_ns()
                    loaded = fixture.load(HERE / "matrix.bin")
                    base = int(loaded["dma_base"], 16)
                    if (loaded["dma_bytes"] != 20480 or loaded["dma_base"] != loaded["hardware_base"]
                            or not 0 < base <= 0x7fffb000 or base % 64 != 0):
                        raise ValueError("DMA upload or hardware address differs")
                    load_report["matrix_upload"] = loaded
                    fixture.select("ddr")
                    load_report["selected_status"] = read_fixture(fixture, "ddr")
                    load_report["matrix_setup_ns"] = time.monotonic_ns() - begin
                energy.dump(output/"load.json",load_report)
                port = runtime.Port(runner.session,HERE/"autonomous_mmio.so",runtime.SKIP_ABI)
                timed = comparison.DeliveryBenchmark(runtime,port)
                snapshot = (lambda: read_fixture(fixture, mode)) if fixture else None
                counted = CountedDelivery(timed, snapshot, mode,
                                          config["request_timeout_ns"],int(deadline*1e9))
                if smoke:
                    cases=[(c,False) for c in CONTROL_CLOCKS]
                    block,_=counted.run_block(runner,cases,refs,remaining)
                    energy.dump(output/"smoke.json",block)
                else:
                    sampler_path=HERE/f"{mode}_sampler.py"
                    pulse=energy.source(sampler_path,config["pins"][sampler_path.name]["sha256"])
                    energy.POWER_SAMPLER_PIN=config["pins"][sampler_path.name]["sha256"]
                    energy.block_summary=comparison.block_summary
                    warm,measured=block_cases(pair,homogeneous)
                    energy.run_arm(output,runner,(warm,measured,"on"),refs,counted,remaining,
                                   pulse,analysis,sampler_path)
                    if runner.requests != len(warm)+len(measured):
                        raise ValueError("Unexpected completed request count")
            finally:
                if fixture is not None:
                    fixture.clear()
                    final = fixture.state()
                    if (not final["safe_release"] or final["transport_busy"] or final["dma_bytes"]
                            or int(final["hardware_base"], 16) or final["mode"] != "bram"):
                        raise RuntimeError("DDR reader has not safely released the buffer")
                    energy.dump(output / "quiesced.json", final)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("config",type=Path)
    p.add_argument("output",type=Path)
    p.add_argument("mode",choices=MODES)
    p.add_argument("pair",type=int,choices=range(1, 5))
    kind=p.add_mutually_exclusive_group()
    kind.add_argument("--smoke",action="store_true")
    kind.add_argument("--homogeneous",choices=tuple(HOMOGENEOUS_REPLIES))
    a=p.parse_args()
    run(json.loads(a.config.read_text()),a.output,a.mode,a.pair,a.smoke,a.homogeneous)
