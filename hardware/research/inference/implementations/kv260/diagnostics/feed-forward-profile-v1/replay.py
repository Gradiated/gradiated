"""Replay the unchanged exact adopted KV260 RTL with a simulation-only monitor."""

import argparse
from hashlib import file_digest
import json
from pathlib import Path
import runpy
import sys
import tarfile
import time

from analyse import summarise


HERE = Path(__file__).resolve().parent
BASELINE = "logits-eight-rtl-20261116T190922Z"
KV260_PATH = "hardware/research/inference/implementations/kv260"
BASE_PINS = {
    "simulation.tar.gz": "370be77ea6b898728f3d4b08982fd9ef2a995638042b20e95f31bcea7ca86351",
    "source-closure.json": "f3a995d3743320a60c9010c200a827afa409a9939f9dd046f7c60348e52536fe",
    "model-results.json": "f17783bf33787972479a07ebc2fd08c56e96d8bf6466a60a0608be8d35ce3256",
}
RUN_PIN = "358c641be65be64c23e890dbc12dcd590c6aeb92a7b733594e4871752b943df0"
HELPERS = {
    "variants/scalar-mul-v1/test_model.py": "2081ea5cd7d18fdc611f194085dbf5ef99e400f2c2c4f9bad4410677af635c4c",
    "variants/scalar-mul-v1/materialise.py": "1d73a8acb7158002c8ddb7e92b4ea67c4a8624e756bb91a9ed08559ffac44193",
    "rtl/toolchain.json": "b6a35af5636cca4a2f9bb82135a716873c8bb1abf6926504f2e425ea600df693",
}
CORE_PIN = "dc5851764926a6b5e3638aea760eb025d86da844241497a175e125c6210d0e2d"
BENCH_PIN = "e60966fcfac916cc6bfcfc0ffd70052fb16a8b7f6dd89b419cea56f03b90bfe4"
CASE_NAMES = (
    "encoded-hello-cap255", "encoded-fu2p2q-cap255", "encoded-max48-cap255",
    "encoded-hello-cap0", "encoded-hello-cap1", "bos-only-cap0", "full-context-cap0",
)
EXACT_OUTPUTS = ("bus.events", "bos.csv", "cache.kv", "phases.txt")


def pin(path, expected):
    with path.open("rb") as stream:
        received = file_digest(stream, "sha256").hexdigest()
    if received != expected:
        raise ValueError(f"Pinned artifact changed: {path}")


def load_helper(kv260):
    for relative, expected in HELPERS.items():
        pin(kv260 / relative, expected)
    source = kv260 / "variants/scalar-mul-v1/test_model.py"
    sys.path.insert(0, str(source.parent))
    try:
        return runpy.run_path(str(source))
    finally:
        sys.path.pop(0)


def extract_inputs(archived, unpack, closure):
    members = closure["members"]
    rtl = closure["generated_rtl"]["8"]
    if len(rtl) != 11 or rtl["transformer"] != CORE_PIN:
        raise ValueError("Unexpected adopted RTL closure")
    simulation_paths = {"autonomous_core_tb.sv", "fixtures/model/reference/model.hex", "fixtures/model/reference/bos.hex"}
    simulation_paths.update(f"rtl/{name}.sv" for name in rtl)
    for label in CASE_NAMES:
        simulation_paths.update(f"fixtures/model/reference/{label}/{file}.hex" for file in ("input", "output", "scores"))
        simulation_paths.update(f"{label}/{filename}" for filename in EXACT_OUTPUTS)
    with tarfile.open(archived) as archive:
        for path in sorted(simulation_paths):
            archive_path = f"lanes-8/{path}"
            member = archive.getmember(archive_path)
            meta = members[archive_path]
            if not member.isfile() or member.size != meta["bytes"]:
                raise ValueError(f"Wrong archive member: {archive_path}")
            target = unpack / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.extractfile(member).read())
            pin(target, meta["sha256"])
    for name, expected in rtl.items():
        pin(unpack / "rtl" / (name + ".sv"), expected)
    pin(unpack / "autonomous_core_tb.sv", BENCH_PIN)
    return sorted(rtl)


def compile_monitor(arguments, workspace, unpack, helper, env, names, deadline):
    source = (unpack / "autonomous_core_tb.sv").read_bytes()
    body, separator, rest = source.rpartition(b"endmodule")
    if not separator or rest not in (b"", b"\n"):
        raise ValueError("Unexpected close of the pinned testbench")
    monitor_path = workspace / "monitor.svh"
    monitor_path.write_bytes((HERE / "monitor.svh").read_bytes())
    bench = workspace / "autonomous_core_tb.sv"
    bench.write_bytes(body + b'`include "monitor.svh"\nendmodule' + rest)
    binary = workspace / "obj/simulation"
    helper["run"](
        [str(arguments.verilator / "bin/verilator"), "--binary", "--timing", "--assert",
         "-Wno-fatal", "--top-module", "autonomous_core_tb", "-j", "2", "--Mdir", str(binary.parent),
         "-o", "simulation", "-I" + str(workspace),
         *[str(unpack / "rtl" / (name + ".sv")) for name in names], str(bench)],
        workspace, env, workspace / "compile.log", 150, deadline,
    )
    return binary


def replay_case(case, archived, reference, output, binary, helper, env, deadline):
    output.mkdir()
    case_type, cap_text = case.rsplit("-cap", 1)
    cap = int(cap_text)
    old = archived[case]
    oracle = reference / "fixtures/model/reference"
    profile = output / "position-ticks.txt"
    params = {
        "MODEL": oracle / "model.hex", "SCORES": oracle / "bos.hex",
        "CSV": output / "bus.events", "RETURNS": output / "bos.csv",
        "INPUT": oracle / case / "input.hex", "OUTPUT": oracle / case / "output.hex",
        "ALLSCORES": oracle / case / "scores.hex", "PREFIX": old["prefix"]["positions"],
        "OUTPUTS": old["outputs"], "POSITIONS": old["done"]["positions"], "CAP": cap,
        "REASON": 1 if cap == 255 else 2 if case_type == "full-context" else 4,
        "SKIP": 1, "CACHE": output / "cache.kv", "PHASE": output / "phases.txt", "FF_PROFILE": profile,
    }
    helper["run"]([str(binary), *[f"+{key}={value}" for key, value in params.items()]],
                  output, env, output / "simulation.log", 120, deadline)
    for name in EXACT_OUTPUTS:
        if (output / name).read_bytes() != (reference / case / name).read_bytes():
            raise ValueError(f"Baseline output parity failed: {case}/{name}")
    summary = summarise(profile, old)
    summary["parity"] = list(EXACT_OUTPUTS)
    return summary


def main(args):
    deadline = time.monotonic() + min(900, args.deadline_epoch - time.time())
    pinned_run = args.repo / "hardware/research/inference/results" / BASELINE / "run.json"
    pin(pinned_run, RUN_PIN)
    raw = args.repo / ".agents/runtime/hardware/inference/outputs" / BASELINE
    for filename, expected in BASE_PINS.items():
        pin(raw / filename, expected)
    archived = json.loads((raw / "model-results.json").read_bytes())["8"]
    if set(archived) != set(CASE_NAMES):
        raise ValueError("Pinned workload shape changed")
    helper = load_helper(args.repo / KV260_PATH)
    env = helper["simulator"](args.verilator, args.repo / KV260_PATH)
    args.output.mkdir()
    unpack = args.output / "pinned"
    names = extract_inputs(raw / "simulation.tar.gz", unpack, json.loads((raw / "source-closure.json").read_bytes()))
    binary = compile_monitor(args, args.output, unpack, helper, env, names, deadline)
    summaries = {}
    for case in CASE_NAMES:
        summaries[case] = replay_case(case, archived, unpack, args.output / case, binary, helper, env, deadline)
        print(case, summaries[case]["positions"], summaries[case]["ff_wait_ticks"], "exact FF_WAIT clocks", flush=True)
    full = {case: item.pop("per_position") for case, item in summaries.items()}
    for filename, data in (("case-summary.json", summaries), ("per-position.json", full)):
        (args.output / filename).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    print("Seven exact replays and all feed-forward accounting checks passed.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("repo", "verilator", "output"):
        parser.add_argument("--" + name, type=lambda value: Path(value).resolve(), required=True)
    parser.add_argument("--deadline-epoch", type=float, required=True)
    main(parser.parse_args())
