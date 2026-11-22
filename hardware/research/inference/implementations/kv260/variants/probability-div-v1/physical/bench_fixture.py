"""Run a matched compact delivery block with resident on-chip weights."""
import argparse
import json
import os
from pathlib import Path
import time

import autonomous_comparison as comparison
import autonomous_runtime as runtime
import board_resident as resident
import energy_analysis as analysis
import energy_validation as energy
from measurement import CASES, HOMOGENEOUS_REPLIES, MODES, CheckedDelivery, mixed_order
import observer_lifecycle as bundle_tools
import observer_validation as validation
import resident_validation as prior


HERE = Path(__file__).resolve().parent


def run(config, output, mode, pair, smoke, homogeneous):
    if os.geteuid() != 0 or Path("/proc/sys/kernel/random/boot_id").read_text().strip() != config["boot"]:
        raise ValueError("Privileged fixture owner on the admitted boot required")
    if homogeneous and (smoke or pair not in (1, 2)):
        raise ValueError("Homogeneous energy blocks run in two matched passes")
    output.mkdir(mode=0o700)
    verify = prior.load_pinned(prior.ACCEPTANCE / "kv260_accept_checks.py", prior.CHECKS_PIN)
    model = verify.load_inputs(prior.ORIGINAL, prior.CANDIDATE, prior.ACCEPTANCE)
    references = prior.load_fresh(prior.SPEED, verify, model)
    bundle = HERE / f"fixture-bundle-{mode}"
    deadline = time.monotonic_ns() + config["arm_timeout_s"] * 1_000_000_000

    def remaining():
        if time.monotonic_ns() >= deadline:
            raise TimeoutError("Experiment 18 block deadline")

    with bundle_tools.open_arm(mode, resident, bundle, config["bundle_pins"][mode]) as runner:
        setup = validation.load_metadata(runner)
        validation.validate_load(setup, prior)
        energy.dump(output / "load.json", setup)
        port = runtime.Port(runner.session, HERE / "autonomous_mmio.so", runtime.SKIP_ABI)
        delivery = comparison.DeliveryBenchmark(runtime, port)
        checked = CheckedDelivery(delivery, config["replay"][mode], deadline)
        if smoke:
            cases = [(case, False) for case in CASES]
            try:
                block, _ = checked.run_block(runner, cases, references, remaining)
            except checked.BlockFailure as error:
                energy.dump(output / "smoke-partial.json", {"completed": error.completed, "error": str(error)})
                raise
            energy.dump(output / "smoke.json", block)
            return
        sampler = HERE / f"{mode}_sampler.py"
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
                       remaining, power, analysis, sampler)
        if runner.requests != len(warm) + len(timed):
            raise ValueError("Unexpected completed request count")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("mode", choices=MODES)
    parser.add_argument("pair", type=int, choices=range(1, 5))
    kind = parser.add_mutually_exclusive_group()
    kind.add_argument("--smoke", action="store_true")
    kind.add_argument("--homogeneous", choices=CASES)
    args = parser.parse_args()
    run(json.loads(args.config.read_text()), args.output, args.mode, args.pair, args.smoke, args.homogeneous)
