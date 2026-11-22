"""Seal the matched Experiment 17 board bundle after routed build and RTL acceptance."""
import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
import tarfile

PRIOR = "logits-ddr4-burst-20261119T121954Z-31256a"
SEQUENTIAL = "gradiated-tiny-logits-ddr4-burst-v1-50mhz.bit.bin"
PREFETCH = "gradiated-tiny-logits-ddr4-prefetch-v1-50mhz.bit.bin"
SEQ_PROGRAM = "kv260-logits-ddr4-burst-program.dtbo"
PREF_PROGRAM = "kv260-logits-ddr4-prefetch-program.dtbo"
BUILD_PREFIX = "logits-ddr4-prefetch-build-"
RTL_PREFIX = "logits-ddr4-prefetch-rtl-"
DRIVER_SHA = "b4ec24defa36f20248f09f913f30326db467f691d8aa4b098b092e944f57b3d4"
MATRIX_SHA = "7a77c0b9cd6f66e1f68d6905c5f2962bf58d92543fbb5e5dbb18980ee9f4a787"


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def pin(data):
    return {"sha256": sha256(data).hexdigest(), "bytes": len(data)}


def checked(path, expected=None):
    require(path.is_file() and not path.is_symlink(), f"Missing regular input file: {path}")
    data = path.read_bytes()
    if expected is not None:
        present = pin(data)
        require(present == expected if isinstance(expected, dict) else present["sha256"] == expected,
                f"Pin differs: {path}")
    return data


def file_sha(path):
    require(path.is_file() and not path.is_symlink(), f"Missing regular input file: {path}")
    sha = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(block)
    return sha.hexdigest()


def run_artifact(run, repo, role):
    candidates = [row for row in run["artifacts"] if row.get("role") == role]
    require(len(candidates) == 1, f"Missing uniquely pinned artifact: {role}")
    row = candidates[0]
    return checked(repo / row["path"], {key: row[key] for key in ("bytes", "sha256")})


def make(repo, release, receipt_sha, board, out, protocol_sha):
    source = Path(__file__).resolve().parent
    project = repo / "hardware/research/inference"
    prior = json.loads((project / "results" / PRIOR / "run.json").read_text())
    require(prior["status"] == "passed" and prior["conditions"]["original_restored"], "Historical arm was not qualified")
    invocation = json.loads(run_artifact(prior, repo, "invocation"))
    previous = repo / ".agents/runtime/hardware/inference/outputs" / PRIOR / "preparation/packet"
    config = json.loads(checked(previous / "config.json", invocation["config_sha256"]))
    require(invocation["sources"] == config["pins"], "Historical board configuration differs from its invocation")
    restored = run_artifact(prior, repo, "restored")
    outcome = run_artifact(prior, repo, "outcome")
    with tarfile.open(fileobj=BytesIO(run_artifact(prior, repo, "archive")), mode="r:gz") as archive:
        exit_words = archive.getmember("evidence/hp0-exit.stdout")
        require(exit_words.isfile(), "Previous HP0 readback is not a regular artifact")
        hp0 = archive.extractfile(exit_words).read()
    require(json.loads(hp0) == board["hp0"], "Current HP0 differs from the archived Experiment 16 exit")
    require(json.loads(outcome) == {"experiment_passed": True, "restored": True}, "Prior restoration did not pass")
    require(re.fullmatch(BUILD_PREFIX + r"[0-9TZ]+", release.name), "Unexpected release identity")
    acceptance_data = checked(release / "offline-acceptance.json", receipt_sha)
    acceptance = json.loads(acceptance_data)
    rtl = acceptance["rtl_replay"]
    require(acceptance["passed"] is True and acceptance["board_programmed"] is False
            and acceptance["generated_psu_matches_control"] is True and acceptance["archive_members"] > 0
            and acceptance["routed_hp0"]["arlen"] == 7
            and re.fullmatch(RTL_PREFIX + r"[0-9TZ]+", rtl["run"])
            and re.fullmatch(r"[0-9a-f]{64}", rtl["rtl_source_manifest_sha256"]),
            "Release lacks a passing exact RTL match and routed HP0 qualification")
    archive = release / "server.tar.gz"
    receipt = json.loads(checked(release / "server.receipt.json"))
    require(receipt["passed"] is True and receipt["bytes"] == archive.stat().st_size
            and receipt["files"] == acceptance["archive_members"]
            and receipt["sha256"] == acceptance["archive_sha256"] == file_sha(archive),
            "Recovered route archive differs from its release and checksum receipt")
    rtl_result = json.loads(checked(project / "results" / rtl["run"] / "run.json"))
    require(rtl_result["status"] == "passed"
            and rtl_result["implementation"]["sha256"] == rtl["rtl_source_manifest_sha256"]
            and rtl_result["protocol"]["sha256"] == protocol_sha,
            "Archived exact RTL source closure differs from routing or protocol")
    for role in ("timing", "control_timing"):
        timing = acceptance[role]
        require(timing["clock"] == "clk_pl_0 period_ns 20.000"
                and float(timing["setup_slack_ns"]) >= 0 and float(timing["hold_slack_ns"]) >= 0,
                f"Routed 50 MHz slack failed for {role}")
    require(board["boot"] == config["boot"] == json.loads(restored)["boot_id"]
            and board["taint"] == str(config["fixture_taint"])
            and not any((board["module"], board["dma"])), "Physical board admission differs from the prior run")
    common = {key: config[key] for key in ("interface_overlay", "dma_overlay", "afi_restore_overlay",
                                          "driver", "allow_module_load", "fixture_taint", "project_state", "boot")}
    skip = {"bram_sampler.py", "ddr_sampler.py", "prior-outcome.json", "prior-restored.json", "kv260-interface.dtbo",
            "gradiated-tiny-attention-exp-pair-v2-50mhz.bit.bin", "kv260-attention-exp-pair-v2-program.dtbo",
            "lifecycle.py", "bench_fixture.py", "measurement.py"}
    data = {name: checked(previous / name, expected)
            for name, expected in config["pins"].items() if name not in skip}
    require(pin(data[common["driver"]])["sha256"] == DRIVER_SHA
            and pin(data["matrix.bin"]) == {"sha256": MATRIX_SHA, "bytes": 20480},
            "The stock Experiment 16 driver or packed matrix differs")
    control = acceptance["control_firmware_assets"]
    candidate = acceptance["firmware_assets"]
    for key in ("interface_overlay", "dma_overlay", "afi_restore_overlay"):
        name = common[key]
        expected = pin(data[name])["sha256"]
        require(expected == control[name] == candidate[name], f"Shared control and candidate {key} differ")
        checked(release / "server" / name, expected)
    for name in (SEQUENTIAL, SEQ_PROGRAM):
        require(pin(data[name])["sha256"] == control[name], f"Wrong control asset: {name}")
    data[PREFETCH] = checked(release / "server/offline-package" / PREFETCH, candidate[PREFETCH])
    data[PREF_PROGRAM] = checked(release / "server" / PREF_PROGRAM, candidate[PREF_PROGRAM])
    require(len(data[PREFETCH]) == len(data[SEQUENTIAL]) == 7797692
            and data[PREFETCH] != data[SEQUENTIAL], "Distinct full firmware images required")
    sampler = checked(previous / "ddr_sampler.py", config["pins"]["ddr_sampler.py"])
    require(sampler.count(SEQUENTIAL.encode()) == 1, "Unexpected power sampler firmware identity")
    data["sequential_sampler.py"] = sampler
    data["prefetch_sampler.py"] = sampler.replace(SEQUENTIAL.encode(), PREFETCH.encode())
    data["prior-restored.json"] = restored
    data["prior-outcome.json"] = outcome
    data["prior-hp0.json"] = hp0
    for name in ("bench_fixture.py", "measurement.py", "lifecycle.py"):
        data[name] = checked(source / name)
    protocol = checked(project / "experiments/kv260-logits-ddr4-prefetch-v1.md", protocol_sha)
    new_config = {
        **common,
        "arms": {
            "sequential": {"firmware": SEQUENTIAL, "program_overlay": SEQ_PROGRAM,
                           "interface_overlay": common["interface_overlay"]},
            "prefetch": {"firmware": PREFETCH, "program_overlay": PREF_PROGRAM,
                         "interface_overlay": common["interface_overlay"]},
        },
        "qualification": {"control_run": PRIOR, "build": release.name, "release_sha256": receipt_sha,
                          "rtl": rtl["run"], "protocol_sha256": pin(protocol)["sha256"]},
        "restoration_anchor": {"state": "prior-restored.json", "outcome": "prior-outcome.json", "hp0": "prior-hp0.json"},
        "pins": {name: pin(value) for name, value in sorted(data.items())},
    }
    out.mkdir(mode=0o700)
    for name, value in data.items():
        with (out / name).open("xb") as stream:
            stream.write(value)
    with (out / "config.json").open("x") as stream:
        json.dump(new_config, stream, sort_keys=True, indent=2)
        stream.write("\n")
    return new_config


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("repo", "release", "board", "out"):
        parser.add_argument("--" + arg, type=Path, required=True)
    parser.add_argument("--receipt-sha", required=True)
    parser.add_argument("--protocol-sha", required=True)
    args = parser.parse_args()
    make(args.repo, args.release, args.receipt_sha, json.loads(args.board.read_text()), args.out, args.protocol_sha)
