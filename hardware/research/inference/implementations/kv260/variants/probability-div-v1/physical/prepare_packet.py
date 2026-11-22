"""Seal Experiment 18 board assets and prove every reused byte against source evidence."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

from measurement import CASES, CONTROL_REPLAY, COUNT_KEYS, MODES


ROOT = Path("hardware/research/inference")
RUNTIME = Path(".agents/runtime/hardware/inference/outputs")
RESTORATION = "logits-ddr4-prefetch-20261119T151537Z-9eeb65"
REUSE = "logits-ddr4-burst-20261119T121954Z-31256a"
CONTROL_RUN = "attention-exp-pair-v2-20261117T232821Z-e72da4"
CONTROL_BUILD = "attention-exp-pair-v2-build-20261117T225852Z"
PROTOCOL = ROOT / "experiments/kv260-probability-div-v1.md"
PROTOCOL_SHA = "7a8025206f7ae6d9748849fa0b18a21ce700ccc03fc8d13aa38c5936807d8496"
STOCK = "gradiated-tiny-50mhz.bit.bin"
CONTROL = "gradiated-tiny-attention-exp-pair-v2-50mhz.bit.bin"
CANDIDATE = "gradiated-tiny-probability-div-v1-50mhz.bit.bin"
CONTROL_DTBO = "kv260-attention-exp-pair-v2-program.dtbo"
CANDIDATE_DTBO = "kv260-probability-div-program.dtbo"
CONTROL_OVERLAY = "gradiated-tiny-attention-exp-pair-v2-program"
CANDIDATE_OVERLAY = "gradiated-tiny-probability-div-v1-program"
CONTROL_SHA = "a44cc30cad8db1844459470b63d2325b544dcef34709db88366bbc201409930d"
CONTROL_DTBO_SHA = "c53292a9fed6f2305200bb55602eb69f12ae8f24e42cae1e64a280d929d996fc"
REFERENCE_FILE = "p1-candidate/warmup.json"
COMMON_FILES = (
    "autonomous_comparison.py", "autonomous_mmio.so", "autonomous_runtime.py",
    "benchmark_validation.py", "board_resident.py", "board_resident_benchmark.py",
    "energy_analysis.py", "energy_validation.py", "kv260_accept.py", "kv260_speed_inventory.py",
    "observer_validation.py", "power_sampler.py", "resident_validation.py", "stock_sampler.py",
    "wrapper_validation.py",
)
DIVISIONS_PER_POSITION = 2
SAVED_CLOCKS_PER_DIVISION = 24


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def pin(data):
    return {"bytes": len(data), "sha256": sha256(data).hexdigest()}


def checked(path, expected=None):
    require(path.is_file() and not path.is_symlink(), f"Missing regular input: {path}")
    data = path.read_bytes()
    if expected is not None:
        actual = pin(data)
        if isinstance(expected, dict):
            expected = {key: expected[key] for key in actual}
        else:
            actual = actual["sha256"]
        require(actual == expected, f"Pin differs: {path}")
    return data


def record(repo, run_id):
    result = json.loads(checked(repo / ROOT / "results" / run_id / "run.json"))
    require(result["id"] == run_id and result["status"] == "passed", f"Run {run_id} did not pass")
    return result


def artifact(result, repo, role):
    match = [item for item in result["artifacts"] if item["role"] == role]
    require(len(match) == 1, f"Missing uniquely pinned artifact: {role}")
    return checked(repo / match[0]["path"], match[0])


def derivative(data, old, new):
    old, new = old.encode(), new.encode()
    require(data.count(old) == 1, f"Expected one identity substitution: {old!r}")
    return data.replace(old, new)


def arm_helper(original):
    replacements = {
        "CONTROL_FILE = 'gradiated-tiny-attention-exp-div-v1-50mhz.bit.bin'": f"CONTROL_FILE = '{CONTROL}'",
        "CONTROL_OVERLAY = 'gradiated-tiny-attention-exp-div-v1-program'": f"CONTROL_OVERLAY = '{CONTROL_OVERLAY}'",
        "CONTROL_DTBO = 'kv260-attention-exp-div-program.dtbo'": f"CONTROL_DTBO = '{CONTROL_DTBO}'",
        "OBSERVER_FILE = 'gradiated-tiny-attention-exp-pair-v2-50mhz.bit.bin'": f"OBSERVER_FILE = '{CANDIDATE}'",
        "OBSERVER_OVERLAY = 'gradiated-tiny-attention-exp-pair-v2-program'": f"OBSERVER_OVERLAY = '{CANDIDATE_OVERLAY}'",
        "OBS_DTBO = 'kv260-attention-exp-pair-v2-program.dtbo'": f"OBS_DTBO = '{CANDIDATE_DTBO}'",
    }
    for old, new in replacements.items():
        original = derivative(original, old, new)
    return original


def verified_replay(raw, reference):
    matched = json.loads(raw)
    replay = {mode: {} for mode in MODES}
    for case in CASES:
        values = matched[case + "-cap255"]
        baseline = reference[case]
        require(values["outputs"] == len(baseline["output_ids"]) and values["stop_reason"] == 1 and
                baseline["stop_reason"] == "eos", f"{case}: exercised output or stopping rule differs")
        for mode in MODES:
            final = values[mode]["done"]
            replay[mode][case] = {
                "cycles": {key: final[key] for key in ("first", "last", "done")},
                "counts": {"context_count": final["positions"], "scores_consumed": values["scored_values"],
                           "skipped_positions": values["skipped_positions"]},
            }
        left, right = (replay[mode][case] for mode in MODES)
        count = left["counts"]["context_count"]
        require(left["cycles"] == CONTROL_REPLAY[case] and
                left["counts"] == right["counts"] == {key: baseline[key] for key in COUNT_KEYS},
                "Control or compared work differs from replay")
        # EOS is selected after all context positions have completed. Do not add an EOS position.
        context_sum = count * (count + 1) // 2
        saving = DIVISIONS_PER_POSITION * SAVED_CLOCKS_PER_DIVISION * context_sum
        require(left["cycles"]["done"] - right["cycles"]["done"] == values["saved_clocks"] == saving and
                0 < right["cycles"]["first"] < right["cycles"]["last"] < right["cycles"]["done"],
                f"{case}: terminal clocks disagree with the exact per-position derivation")
    return replay


def make(repo, release, acceptance_sha, rtl_id, replay_path, readiness_path, out):
    protocol = checked(repo / PROTOCOL, PROTOCOL_SHA)
    previous = record(repo, RESTORATION)
    reuse = record(repo, REUSE)
    control = record(repo, CONTROL_BUILD)
    historical = record(repo, CONTROL_RUN)
    rtl = record(repo, rtl_id)
    build = record(repo, release.name)
    require(rtl["protocol"]["sha256"] == build["protocol"]["sha256"] == PROTOCOL_SHA,
            "Candidate qualification protocol differs")
    receipt_bytes = checked(release / "offline-acceptance.json", acceptance_sha)
    receipt = json.loads(receipt_bytes)
    require(receipt["passed"] is True and receipt["board_programmed"] is False and
            receipt["bitstream_conversion_equal"] is True and
            receipt["control_firmware_sha256"] == CONTROL_SHA and receipt["control_overlay_sha256"] == CONTROL_DTBO_SHA and
            receipt["changed_neural_sources"] == ["attention.sv"] and
            receipt["candidate_rtl"]["implementation/rtl/attention.sv"] == rtl["conditions"]["candidate_attention_sha256"],
            "Offline qualification, exact retained control or exact candidate RTL identity differs")
    for key in ("metrics", "control_metrics"):
        timing = receipt[key]
        require(timing["clock"] == "clk_pl_0 period_ns 20.000" and str(timing["fully_routed"]) == "1" and
                float(timing["setup_slack_ns"]) >= 0 and float(timing["hold_slack_ns"]) >= 0,
                f"Route or 50 MHz timing does not close for {key}")
    require(any(a["sha256"] == acceptance_sha for a in build["artifacts"]),
            "Routed build does not pin the acceptance report")
    data = {}
    candidate_bit = checked(release / "server/offline-package" / CANDIDATE, receipt["firmware"])
    candidate_overlay = checked(release / "server" / CANDIDATE_DTBO, receipt["program_overlay"])
    require(build["implementation"]["sha256"] == pin(candidate_bit)["sha256"],
            "Candidate routed record does not pin firmware")
    data[CANDIDATE] = candidate_bit
    data[CANDIDATE_DTBO] = candidate_overlay
    data[CONTROL] = artifact(control, repo, "Verified firmware image")
    data[CONTROL_DTBO] = artifact(control, repo, "Verified firmware-name overlay")
    require(pin(data[CONTROL])["sha256"] == CONTROL_SHA ==
            historical["device"]["configuration"]["comparison_firmware"]["candidate"]
            and pin(data[CONTROL_DTBO])["sha256"] == CONTROL_DTBO_SHA and
            len(data[CONTROL]) == len(candidate_bit) == 7797692 and data[CONTROL] != candidate_bit,
            "Experiment 13 historical board image, overlay or candidate bitstream differs")
    previous_invocation = json.loads(artifact(previous, repo, "invocation"))
    reuse_invocation = json.loads(artifact(reuse, repo, "invocation"))
    for name in COMMON_FILES:
        data[name] = checked(repo / RUNTIME / RESTORATION / "preparation/packet" / name,
                             previous_invocation["sources"][name])
    prior_helper = checked(repo / RUNTIME / RESTORATION / "preparation/packet/observer_lifecycle.py",
                           previous_invocation["sources"]["observer_lifecycle.py"])
    data["observer_lifecycle.py"] = arm_helper(prior_helper)
    data["control_sampler.py"] = derivative(data["stock_sampler.py"], STOCK, CONTROL)
    data["candidate_sampler.py"] = derivative(data["stock_sampler.py"], STOCK, CANDIDATE)
    data["prior-restored.json"] = artifact(previous, repo, "restored")
    data["prior-outcome.json"] = artifact(previous, repo, "outcome")
    readiness = json.loads(checked(readiness_path))
    restored = json.loads(data["prior-restored.json"])
    require(json.loads(data["prior-outcome.json"]) == {"experiment_passed": True, "restored": True} and
            readiness["boot"] == previous_invocation["boot"] == reuse_invocation["boot"] == restored["boot_id"] and
            readiness["taint"] == restored["taint"] == "12288" and readiness["firmware"] == STOCK and
            dict.fromkeys(readiness["overlays"], "applied") == restored["overlays"] and
            not readiness["module"] and not readiness["dma"],
            "Board no longer matches Experiment 17 restored state")
    local = Path(__file__).resolve().parent
    for name in ("lifecycle.py", "measurement.py", "bench_fixture.py"):
        data[name] = checked(local / name)
    raw = checked(replay_path)
    replay_sha = pin(raw)["sha256"]
    require(any(a["sha256"] == replay_sha and a["bytes"] == len(raw) for a in rtl["artifacts"]),
            "Exact replay is outside qualified RTL artifact set")
    archive = repo / RUNTIME / CONTROL_RUN
    control_invocation = json.loads(artifact(historical, repo, "invocation.json"))
    inventory = json.loads(artifact(historical, repo, "Full recovered raw capture inventory"))["files"]
    reference_raw = checked(archive / REFERENCE_FILE, inventory[REFERENCE_FILE])
    references = {r["case"]: r["observed"]["header"] for r in json.loads(reference_raw)["requests"]}
    require(control_invocation["sources"]["autonomous_comparison.py"] == pin(data["autonomous_comparison.py"])["sha256"],
            "Exact historically matched compact host implementation differs")
    replay = verified_replay(raw, references)
    pins = {name: pin(value) for name, value in sorted(data.items())}
    expected_reuse = {name for name, value in pins.items() if reuse_invocation["sources"].get(name) == value}
    require({CONTROL, CONTROL_DTBO} <= expected_reuse <= set(readiness["reusable"]),
            "Same-boot board files do not prove all reusable members")
    config = {
        "arm_kind": "on-chip",
        "boot": readiness["boot"],
        "qualification": {"build": release.name, "rtl": rtl_id, "protocol_sha256": pin(protocol)["sha256"],
                          "build_acceptance_sha256": acceptance_sha, "replay_sha256": replay_sha,
                          "control_reference_sha256": pin(reference_raw)["sha256"],
                          "control_build": CONTROL_BUILD, "control_run": CONTROL_RUN,
                          "previous_board_run": RESTORATION},
        "restoration_anchor": {"state": "prior-restored.json", "outcome": "prior-outcome.json"},
        "replay": replay,
        "pins": pins,
    }
    out.mkdir(mode=0o700)
    for name, value in data.items():
        (out / name).write_bytes(value)
    (out / "config.json").write_text(json.dumps(config, indent=2, sort_keys=True) + "\n")
    return config


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("repo", "release", "replay", "readiness", "out"):
        parser.add_argument("--" + arg, type=Path, required=True)
    for arg in ("acceptance-sha", "rtl-id"):
        parser.add_argument("--" + arg, required=True)
    args = parser.parse_args()
    make(args.repo, args.release, args.acceptance_sha, args.rtl_id, args.replay,
         args.readiness, args.out)
