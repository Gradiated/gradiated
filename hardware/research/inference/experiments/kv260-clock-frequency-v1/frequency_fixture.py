"""Run one matched Exp24 measurement block under the caller's board supervisor."""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import sys
import time

import autonomous_comparison as comparison
import autonomous_runtime as runtime
import board_resident as resident
import clock_boundary
import energy_analysis as analysis
import energy_validation as energy
from measurement import CASES, HOMOGENEOUS_REPLIES, MODES, REQUEST_NS, CheckedDelivery, mixed_order
import observer_lifecycle as bundle_tools
import observer_validation as validation
import resident_validation as prior


HERE = Path(__file__).resolve().parent


def prepare_bundle(config, destination=None):
    """Build the one rate-pinned native bundle used for A and B."""
    clock_boundary.validate_config(config)
    destination = Path(destination) if destination is not None else HERE / "fixture-bundle-candidate"
    source_pin = bundle_tools.prepare_bundle(prior.CANDIDATE, HERE, destination, resident, config["pins"])
    manifest_path = destination / "package.json"
    source = destination / "board_bos.py"
    manifest = clock_boundary.read_json(manifest_path)
    bundle_tools.pinned(manifest_path, source_pin)
    old = bundle_tools.pinned(source, manifest["files"][source.name])
    rates = tuple(config["clock_contract"]["pl0"][mode]["configured_hz"] for mode in MODES)
    new = native_source(old, rates)
    source.write_bytes(new)
    manifest["files"][source.name] = bundle_tools.file_pin(new)
    manifest["clock_comparison"] = {"configured_rates_hz": rates, "prior_manifest": source_pin}
    manifest_path.unlink()
    clock_boundary.write_json(manifest_path, manifest)
    return bundle_tools.file_pin(manifest_path.read_bytes())


def native_source(old, rates):
    if len(rates) != 2 or not all(type(rate) is int and rate > 0 for rate in rates):
        raise ValueError("Two exact rate pins are required for the new native bundle")
    new = bundle_tools.rewritten(old, b"40000000 <= rate <= 50000000", f"rate in {rates!r}".encode())
    new = bundle_tools.rewritten(new, b"PL0 is not enabled at a supported <=50 MHz rate",
                                 b"PL0 is not enabled at one of the two qualified configured rates")
    compile(new, "board_bos.py", "exec")
    return new


@contextmanager
def bracket(capture):
    capture("before")
    try:
        yield
    finally:
        ongoing = sys.exc_info()[1]
        try:
            capture("after")
        except Exception as exc:
            if ongoing is None:
                raise
            ongoing.add_note(f"Final clock readback also failed: {exc}")


def temperatures():
    started = time.monotonic_ns()
    sources = []
    for zone in sorted(Path("/sys/class/thermal").glob("thermal_zone[0-9]*")):
        sources.append((zone/"temp", zone/"type", zone.name))
    for hwmon in sorted(Path("/sys/class/hwmon").glob("hwmon[0-9]*")):
        try:
            name = (hwmon/"name").read_text().strip()
        except OSError:
            name = hwmon.name
        for temp in sorted(hwmon.glob("temp[0-9]*_input")):
            stem = temp.name.removesuffix("_input")
            sources.append((temp, hwmon/f"{stem}_label", f"{name}/{stem}"))

    rows = []
    for data, label, fallback in sources:
        begin = time.monotonic_ns()
        try:
            name = label.read_text().strip() or fallback
        except OSError:
            name = fallback
        row = {"path":str(data), "label":name, "unit":"millidegrees Celsius", "begin_ns":begin}
        try:
            row["value"] = int(data.read_text().strip())
        except (OSError, ValueError) as error:
            row["unavailable"] = str(error)
        row["end_ns"] = time.monotonic_ns()
        rows.append(row)
    return {"begin_ns":started, "end_ns":time.monotonic_ns(), "sensors":rows}


def measure(config, output, mode, pair, *, readback, smoke=False, homogeneous=None):
    """Measure one block. The supervisor exclusively owns the loaded rate and active image."""
    output = Path(output)
    clock_boundary.validate_config(config)
    if os.geteuid() != 0 or Path("/proc/sys/kernel/random/boot_id").read_text().strip() != config["boot"]:
        raise ValueError("Privileged fixture owner on the admitted boot required")
    if mode not in MODES or pair not in range(1, 5) or (homogeneous and (smoke or pair not in (1, 2) or homogeneous not in CASES)):
        raise ValueError("Unknown comparison block")
    image_name, _ = bundle_tools.image_spec("candidate")
    if image_name != config["image"]["name"]:
        raise ValueError("Loaded image identity differs from the common native bundle")
    output.mkdir(mode=0o700)
    configured_hz = config["clock_contract"]["pl0"][mode]["configured_hz"]
    def boundary(edge):
        if edge == "after":
            clock_boundary.write_json(output / "temperatures-after.json", temperatures())
        clock_boundary.capture(output, edge, config, mode, readback)
        if edge == "before":
            clock_boundary.write_json(output / "temperatures-before.json", temperatures())

    with bracket(boundary):
        verify = prior.load_pinned(prior.ACCEPTANCE / "kv260_accept_checks.py", prior.CHECKS_PIN)
        model = verify.load_inputs(prior.ORIGINAL, prior.CANDIDATE, prior.ACCEPTANCE)
        references = prior.load_fresh(prior.SPEED, verify, model)
        bundle = Path(config.get("bundle_path", HERE / "fixture-bundle-candidate"))
        manifest = clock_boundary.read_json(bundle / "package.json")
        bundle_tools.pinned(bundle / "package.json", config["bundle_pin"])
        rates = [config["clock_contract"]["pl0"][m]["configured_hz"] for m in MODES]
        if manifest["clock_comparison"]["configured_rates_hz"] != rates:
            raise ValueError("Native bundle derives from different configured rates")
        deadline = time.monotonic_ns() + config["arm_timeout_s"] * 1_000_000_000
        def remaining():
            if time.monotonic_ns() >= deadline:
                raise TimeoutError("Matched fabric-rate comparison block deadline")

        with bundle_tools.open_arm("candidate", resident, bundle, config["bundle_pin"]) as runner:
            setup = validation.load_metadata(runner)
            validation.validate_load(setup, prior)
            energy.dump(output / "load.json", setup)
            port = runtime.Port(runner.session, HERE / "autonomous_mmio.so", runtime.SKIP_ABI)
            delivery = comparison.DeliveryBenchmark(runtime, port, configured_hz=configured_hz)
            checked = CheckedDelivery(delivery, config["replay"][mode], deadline)
            if smoke:
                try:
                    block, _ = checked.run_block(runner, [(case, False) for case in CASES], references, remaining)
                except checked.BlockFailure as error:
                    energy.dump(output / "smoke-partial.json", {"completed": error.completed, "error": str(error)})
                    raise
                energy.dump(output / "smoke.json", block)
                if any(not 0 < (row["observed"]["header"]["done_ns"] - row["observed"]["header"]["admitted_ns"]) <= REQUEST_NS // 3
                       for row in block["requests"]):
                    raise ValueError("Smoke reply exceeds the frozen margin")
                return
            sampler = HERE / "candidate_sampler.py"
            energy.POWER_SAMPLER_PIN = config["pins"][sampler.name]["sha256"]
            energy.block_summary = comparison.block_summary
            power = energy.source(sampler, energy.POWER_SAMPLER_PIN)
            if homogeneous:
                warm = [(homogeneous, False)]
                timed = [(homogeneous, True)] * HOMOGENEOUS_REPLIES[homogeneous]
            else:
                warm_order, timed_order = mixed_order(pair)
                warm, timed = [(case, False) for case in warm_order], [(case, True) for case in timed_order]
            energy.run_arm(output, runner, (warm, timed, "on"), references, checked,
                           remaining, power, analysis, sampler, clock_boundary=boundary)
            verify_power_window(output)
            if runner.requests != len(warm) + len(timed):
                raise ValueError("Unexpected completed request count")


def verify_power_window(output):
    """Use the offline five-alignment rail gate on the completed trace."""
    arm = clock_boundary.read_json(output / "arm.json")
    block = clock_boundary.read_json(output / "block.json")
    ready, raw = (output / "sampler.stdout").read_bytes().split(b"\n", 1)
    if ready != b"READY":
        raise ValueError("INA260 sampler did not produce a ready receipt")
    samples = analysis.check_power(json.loads(raw), arm["schedule_start_ns"], arm["before"], arm["after"])
    rows = block["requests"]
    tokens = sum(len(row["observed"]["header"]["output_ns"]) for row in rows)
    result = analysis.rail(samples, arm["phases"], len(rows), tokens)
    gate = {"admitted": result["admitted"], "max_contributing_gap_ns": analysis.GAP_NS}
    if not gate["admitted"]:
        gate["reason"] = result["reason"]
    energy.dump(output / "power-eligibility.json", gate)
    if not gate["admitted"]:
        raise ValueError(f"INA260 integration window rejected: {gate['reason']}")
