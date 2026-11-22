"""Create a boot-anchored Experiment 16 packet after offline release."""

import argparse
from hashlib import sha256
import json
from pathlib import Path

EXPERIMENT_15 = "output-projection-ddr4-burst-20261119T111700Z-e69dad"
CONTROL_ID = "attention-exp-pair-v2-20261117T232821Z-e72da4"
CONTROL_BUILD = "attention-exp-pair-v2-build-20261117T225852Z"
CONTROL = "gradiated-tiny-attention-exp-pair-v2-50mhz.bit.bin"
CONTROL_PROGRAM = "kv260-attention-exp-pair-v2-program.dtbo"
CONTROL_INTERFACE = "kv260-interface.dtbo"
OLD_FIXTURE = "gradiated-tiny-output-projection-ddr4-burst-v1-50mhz.bit.bin"
DDR = "gradiated-tiny-logits-ddr4-burst-v1-50mhz.bit.bin"
DDR_PROGRAM = "kv260-logits-ddr4-burst-program.dtbo"
DMA = "kv260-logits-ddr4-dma-direct.dtbo"
DRIVER_SHA = "b4ec24defa36f20248f09f913f30326db467f691d8aa4b098b092e944f57b3d4"
MATRIX_SHA = "7a77c0b9cd6f66e1f68d6905c5f2962bf58d92543fbb5e5dbb18980ee9f4a787"


def checked(path, checksum=None):
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Expected a regular input file: {path}")
    value = path.read_bytes()
    if checksum and sha256(value).hexdigest() != checksum:
        raise ValueError(f"Pin differs: {path}")
    return value


def pin(data):
    return {"sha256": sha256(data).hexdigest(), "bytes": len(data)}


def replace(source, old, new):
    if source.count(old) != 1:
        raise ValueError(f"Expected exactly one occurrence of {old!r}")
    return source.replace(old, new, 1)


def save(dir_, name, data):
    with (dir_ / name).open("xb") as stream:
        stream.write(data)


def make(args):
    source = Path(__file__).resolve().parent
    root = args.repo / ".agents/runtime/hardware/inference/outputs"
    project = args.repo / "hardware/research/inference"
    old = root / EXPERIMENT_15
    prior = old / "preparation/packet"
    prior_config = json.loads(checked(prior / "config.json",
                          json.loads((old / "invocation.json").read_text())["config_sha256"]))
    old_record = json.loads((project / "results" / EXPERIMENT_15 / "run.json").read_text())
    old_pins = {row["role"]: row for row in old_record["artifacts"]}
    data = {}
    preserved = (
        "autonomous_comparison.py", "autonomous_mmio.so", "autonomous_runtime.py",
        "benchmark_validation.py", "board_resident.py", "board_resident_benchmark.py",
        "energy_analysis.py", "energy_validation.py", "kv260_accept.py", "kv260_speed_inventory.py",
        "observer_lifecycle.py", "observer_validation.py", "resident_validation.py",
        "wrapper_validation.py", "power_sampler.py", "readback.py",
    )
    for name in preserved:
        data[name] = checked(prior / name, prior_config["pins"][name]["sha256"])
    for name in ("outcome", "restored"):
        evidence = old_pins[name]
        data[f"prior-{name}.json"] = checked(args.repo / evidence["path"], evidence["sha256"])
    restored = json.loads(data["prior-restored.json"])
    if restored["boot_id"] != prior_config["boot"] or restored["taint"] != "12288":
        raise ValueError("Previous restoration does not anchor the planned boot")
    for name in ("bench_fixture.py", "measurement.py", "lifecycle.py"):
        data[name] = checked(source / name)
    weights = source.parent / "host/weights.py"
    data["weights.py"] = checked(weights if weights.is_file() else args.weights)
    data["kv260_ddr4_weights.ko"] = checked(args.driver, DRIVER_SHA)
    data["matrix.bin"] = checked(args.matrix, MATRIX_SHA)
    if len(data["matrix.bin"]) != 20480:
        raise ValueError("Expected the complete packed logits copy")
    template = checked(prior / "fixture_sampler.py", prior_config["pins"]["fixture_sampler.py"]["sha256"])
    data["bram_sampler.py"] = replace(template, OLD_FIXTURE.encode(), CONTROL.encode())
    data["ddr_sampler.py"] = replace(template, OLD_FIXTURE.encode(), DDR.encode())
    stock = checked(prior / "stock_sampler.py", prior_config["pins"]["stock_sampler.py"]["sha256"])
    data["stock_sampler.py"] = replace(stock, b'"6.8.0-1015-xilinx", "0", "operating"',
                                     b'"6.8.0-1015-xilinx", "12288", "operating"')
    old_comparison = json.loads((root / CONTROL_ID / "assets.json").read_text())
    control_build = root / CONTROL_BUILD / "server"
    control_run = json.loads((project / "results" / CONTROL_BUILD / "run.json").read_text())
    data[CONTROL] = checked(control_build / "offline-package" / CONTROL,
                            control_run["implementation"]["sha256"])
    pin_control_program = next((a.get("sha256") for a in control_run["artifacts"]
                                if a["path"].endswith(CONTROL_PROGRAM)), None)
    if not pin_control_program:
        raise ValueError("Exact Exp13 program overlay pin unavailable")
    data[CONTROL_PROGRAM] = checked(control_build / CONTROL_PROGRAM, pin_control_program)
    data[CONTROL_INTERFACE] = checked(args.control_interface, old_comparison["interface_sha256"])
    release = json.loads(checked(args.release / "offline-acceptance.json"))
    rtl = release.get("rtl_replay", {})
    if (release.get("passed") is not True or release.get("generated_psu_matches_exp15") is not True
            or release.get("routed_hp0", {}).get("arlen") != 7
            or rtl.get("run") != "logits-ddr4-burst-rtl-20261119T120140Z"
            or rtl.get("rtl_source_manifest_sha256") != "072afd4a0eaeb744a12393c8ee94540981b4a472ecc18161bcd211c404c467f3"):
        raise ValueError("Candidate offline release or exact RTL transfer qualification did not pass")
    for name in (CONTROL, CONTROL_PROGRAM):
        if sha256(data[name]).hexdigest() != release["control_firmware_assets"][name]:
            raise ValueError("Control artifact differs from its verified release")
    candidate_pins = release["firmware_assets"]
    assets = {
        "firmware": DDR, "program_overlay": DDR_PROGRAM, "dma_overlay": DMA,
        "interface_overlay": prior_config["interface_overlay"],
        "afi_restore_overlay": prior_config["afi_restore_overlay"], "driver": "kv260_ddr4_weights.ko",
    }
    for key, name in assets.items():
        if key == "driver":
            continue
        where = args.release / "server"
        where = where / "offline-package" if key == "firmware" else where
        data[name] = checked(where / name, candidate_pins[name])
    config = {
        **assets, "boot": restored["boot_id"], "allow_module_load": True, "fixture_taint": 12288,
        "project_state": prior_config["project_state"],
        "restoration_anchor": {"state": "prior-restored.json", "outcome": "prior-outcome.json"},
        "arms": {
            "bram": {"firmware": CONTROL, "program_overlay": CONTROL_PROGRAM,
                     "interface_overlay": CONTROL_INTERFACE},
            "ddr": {k: assets[k] for k in ("firmware", "program_overlay", "interface_overlay")},
        },
        "pins": {name: pin(value) for name, value in sorted(data.items())},
    }
    args.out.mkdir(mode=0o700)
    for name, value in data.items():
        save(args.out, name, value)
    save(args.out, "config.json", (json.dumps(config, sort_keys=True, indent=2) + "\n").encode())


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("repo", "release", "driver", "matrix", "control_interface", "out"):
        p.add_argument("--" + name.replace("_", "-"), type=Path, required=True)
    p.add_argument("--weights", type=Path, help="Optional staged weights.py for offline checks.")
    make(p.parse_args())
