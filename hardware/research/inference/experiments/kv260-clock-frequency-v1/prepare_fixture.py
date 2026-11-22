"""Prepare one reviewable measurement fixture from checked Experiment 23 evidence."""

import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import tarfile


ROOT = Path("hardware/research/inference")
RUNTIME = Path(".agents/runtime/hardware/inference/outputs")
BASELINE = "attention-value-pair-20261119T234247Z-e21df0"
BASELINE_SHA256 = "d853f1eb8d6f3c1af10654601b29d91409178825073df385c9d63000f35f0d49"
ORIGINAL_TIMING = RUNTIME / "attention-clock-v1-original-sta-20261120T003417Z/offline-acceptance.json"
ORIGINAL_TIMING_SHA256 = "6929990fb8d315e0750482de68dc885f81a26add5847ee68df70c02aff966376"
BOARD_IMAGE = "gradiated-tiny-attention-value-pair-v1-50mhz.bit.bin"
BOARD_OVERLAY = "kv260-attention-value-pair-v1-program.dtbo"
LIVE_OVERLAY = "gradiated-tiny-attention-value-pair-v1-program"
REFERENCE_MEMBER = "evidence/p1-candidate/warmup.json"
HERE = Path(__file__).resolve().parent
HELPERS = ("autonomous_comparison.py", "autonomous_mmio.so", "autonomous_runtime.py", "board_resident.py",
           "energy_analysis.py", "energy_validation.py", "candidate_sampler.py", "measurement.py",
           "observer_lifecycle.py", "observer_validation.py", "resident_validation.py")
NEW_FILES = ("clock_boundary.py", "frequency_fixture.py", "score_frequency.py")


def pin(data):
    return {"sha256": sha256(data).hexdigest(), "bytes": len(data)}


def require(ok, detail):
    if not ok:
        raise ValueError(detail)


def checked(path, expected=None):
    require(path.is_file() and not path.is_symlink(), f"Missing regular source: {path}")
    raw = path.read_bytes()
    if expected is not None:
        require(pin(raw) == {k: expected[k] for k in ("bytes", "sha256")}, f"Invalid source digest: {path}")
    return raw


def artifact(repo, result, role):
    row, = (value for value in result["artifacts"] if value["role"] == role)
    return checked(repo / row["path"], row)


def replace(raw, old, new):
    require(raw.count(old) == 1, f"Expected one checked source edit: {old[:100]!r}")
    return raw.replace(old, new)


def retime_host(raw):
    raw = replace(raw, b"earliest, candidate):", b"earliest, candidate, configured_hz=50_000_000):")
    raw = replace(raw, b'cycles["done"] * 20 > data["done_ns"] - timing["inference_begin_ns"]',
                  b'cycles["done"] * 1_000_000_000 > (data["done_ns"] - timing["inference_begin_ns"]) * configured_hz')
    raw = replace(raw, b"max_output=255, deadline_ns=None):", b"max_output=255, deadline_ns=None, configured_hz=50_000_000):")
    raw = replace(raw, b"        self.runtime = runtime\n", b"        self.runtime = runtime\n        self.configured_hz = configured_hz\n")
    return replace(raw, b"self.port.abi == self.runtime.SKIP_ABI)", b"self.port.abi == self.runtime.SKIP_ABI, self.configured_hz)")


def clock_brackets(raw):
    raw = replace(raw, b"remaining, power, analysis, path):", b"remaining, power, analysis, path, *, clock_boundary=None):")
    raw = replace(raw, b"        spi['before'] = capture_spi()\n",
                  b"        if clock_boundary is not None:\n            clock_boundary('active-before')\n        spi['before'] = capture_spi()\n")
    return replace(raw, b"        spi['after'] = capture_spi()\n",
                   b"        spi['after'] = capture_spi()\n        if clock_boundary is not None:\n            clock_boundary('active-after')\n")


def prepare(repo, out, implementation=None):
    current = checked(repo / ROOT / "results" / BASELINE / "run.json")
    require(pin(current)["sha256"] == BASELINE_SHA256, "Experiment 23 physical result pin differs")
    result = json.loads(current)
    require(result["status"] == "passed" and result["conditions"]["original_restored"], "Experiment 23 failed admission")
    archive = repo / RUNTIME / BASELINE
    invocation = json.loads(artifact(repo, result, "invocation"))
    source_review = json.loads(artifact(repo, result, "source_review"))
    baseline_build = json.loads(artifact(repo, result, "build"))
    candidates = {name: checked(archive / "preparation/packet" / name, invocation["sources"][name]) for name in HELPERS}
    protocol = checked(repo / ROOT / "experiments/kv260-clock-frequency-v1.md")
    timing_path = implementation if implementation is not None else repo / ORIGINAL_TIMING
    timing_raw = checked(timing_path)
    if implementation is None:
        require(pin(timing_raw)["sha256"] == ORIGINAL_TIMING_SHA256, "Original-layout rate qualification differs")
    timing = json.loads(timing_raw)
    require(timing["passed"] is True and timing["board_programmed"] is False
            and timing["same_image_for_all_passing_rates"] is True and timing["protocol_sha256"] == pin(protocol)["sha256"],
            "Same-image rate qualification did not pass or differs from the protocol")
    rates = {row["nominal_rate_hz"]: row["upper_qualified_rate_hz"] for row in timing["timing_profiles"].values()
             if row["admitted"] is True and all(row[k] >= 0 for k in ("setup_slack_ns", "hold_slack_ns", "pulse_width_slack_ns"))}
    require(set(rates) == set(timing["qualified_nominal_rates_hz"]) and 50_000_000 in rates,
            "Rate eligibility disagrees with native setup, hold or pulse-width receipts")
    common_identity = result["device"]["configuration"]["comparison_firmware_sha256"]["candidate"]
    if implementation is None:
        image, dtbo, live = BOARD_IMAGE, BOARD_OVERLAY, LIVE_OVERLAY
        for name in (image, dtbo):
            candidates[name] = checked(archive / "preparation/packet" / name, invocation["sources"][name])
        require(pin(candidates[image])["sha256"] == common_identity == baseline_build["implementation"]["sha256"],
                "Prior benchmark, staged and routed image differ")
    else:
        # A separately qualified layout still uses one image for both rates.
        firmware, overlay = (timing[k] for k in ("firmware", "program_overlay"))
        image, dtbo, live = firmware["filename"], overlay["filename"], timing["live_program_overlay"]
        require(all(Path(name).name == name and name not in (".", "..") for name in (image, dtbo, live)), "Invalid staged identities")
        candidates[image] = checked(implementation.parent / "server/offline-package" / image, firmware)
        candidates[dtbo] = checked(implementation.parent / "server" / dtbo, overlay)
        for old, new in ((BOARD_IMAGE, image), (BOARD_OVERLAY, dtbo), (LIVE_OVERLAY, live)):
            if old != new:
                candidates["observer_lifecycle.py"] = replace(candidates["observer_lifecycle.py"], old.encode(), new.encode())
        if image != BOARD_IMAGE:
            candidates["candidate_sampler.py"] = replace(candidates["candidate_sampler.py"], BOARD_IMAGE.encode(), image.encode())
    for kind, name in (("firmware", image), ("program_overlay", dtbo)):
        item = timing[kind]
        require(item["filename"] == name and pin(candidates[name]) == {k: item[k] for k in ("bytes", "sha256")},
                f"Timing qualification asset pin disagrees with staged {name}")
    candidates["timing-acceptance.json"] = timing_raw
    with tarfile.open(fileobj=BytesIO(artifact(repo, result, "archive")), mode="r:gz") as bundle:
        member, = (row for row in bundle.getmembers() if row.name == REFERENCE_MEMBER)
        require(member.isfile(), "Archived replay reference differs")
        reference = bundle.extractfile(member).read()
    require(reference == checked(archive / REFERENCE_MEMBER), "Baseline reply receipt differs from authenticated archive")
    expected = result["conditions"]["exact_fpga_cycle_boundaries"]["candidate"]
    seen = {}
    for row in json.loads(reference)["requests"]:
        case, header = row["case"], row["observed"]["header"]
        require(case not in seen and header["stop_reason"] == "eos", "Baseline request stopping rule differs")
        counts = expected[case]["counts"]
        seen[case] = {"cycles": header["request_cycles"], "counts": {key: header[key] for key in counts}}
    require(seen == expected, "Frozen request work differs from recorded Exp23 replay")
    candidates["score_fixture.py"] = checked(archive / "preparation/runner/score_fixture.py", source_review["files"]["score_fixture.py"])
    candidates.update({name: checked(HERE / name) for name in NEW_FILES})
    candidates["autonomous_comparison.py"] = retime_host(candidates["autonomous_comparison.py"])
    candidates["energy_validation.py"] = clock_brackets(candidates["energy_validation.py"])
    for name, raw in candidates.items():
        if name.endswith(".py"):
            compile(raw, name, "exec")
    out.mkdir(mode=0o700)
    for name, raw in candidates.items():
        (out / name).write_bytes(raw)
    local_reference = out / "reference"
    (local_reference / "p1-candidate").mkdir(parents=True, mode=0o700)
    (local_reference / "p1-candidate" / "warmup.json").write_bytes(reference)
    plan = {"boot": invocation["boot"], "image": {"name": image, "sha256": pin(candidates[image])["sha256"]},
            "overlay": {"name": dtbo, "live": live}, "pins": {name: pin(raw) for name, raw in candidates.items()},
            "replay": {"control": expected, "candidate": expected}, "baseline_run": BASELINE,
            "baseline_run_sha256": BASELINE_SHA256, "baseline_clock_mhz": 50,
            "protocol_sha256": pin(protocol)["sha256"], "reference_pin": pin(reference),
            "qualified_rates_hz": rates,
            "source_pins": {**{name: invocation["sources"][name] for name in HELPERS},
                            "score_fixture.py": source_review["files"]["score_fixture.py"]},
            "implementation_acceptance": pin(timing_raw)}
    (out / "measurement-plan.json").write_text(json.dumps(plan, sort_keys=True, indent=2) + "\n")
    print(json.dumps({"plan": str(out / "measurement-plan.json"), "image": plan["image"], "sources": len(candidates)}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--implementation", type=Path, help="Optional receipt for a separately routed, qualified common image")
    args = parser.parse_args()
    prepare(args.repo, args.output, args.implementation)
