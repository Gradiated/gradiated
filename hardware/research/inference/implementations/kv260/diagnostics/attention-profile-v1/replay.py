"""Replay the adopted KV260 circuit with an elaboration-only attention monitor."""

import argparse
from hashlib import file_digest
import json
from pathlib import Path
import runpy
import sys
import tarfile
import time

HERE = Path(__file__).resolve().parent
BASELINE = "ff-down-rtl-20261117T000318Z"
BASE_PINS = {
    "simulation.tar.gz": "882fc1239f926fa48ac0a5e15b87811f18e8e7b42c34bb9b73aba6e324430af9",
    "source-closure.json": "65678472903e1562145c95dceaf8509deb859da74e471a9d18de2615a9d02076",
    "model-results.json": "021d1c66c22445d4edf6ab50801718974c26516f16d455483ece01a4380dd84a",
}
RUN_PIN = "bd5e5ee84b7fd4c957c14c3d8b73ad0d22f2b5f5d23b2cc76130b0ca32e9669c"
HELPER_PIN = "2081ea5cd7d18fdc611f194085dbf5ef99e400f2c2c4f9bad4410677af635c4c"
TOOL_PIN = "b6a35af5636cca4a2f9bb82135a716873c8bb1abf6926504f2e425ea600df693"
CASE_NAMES = (
    "encoded-hello-cap255", "encoded-fu2p2q-cap255", "encoded-max48-cap255",
    "encoded-hello-cap0", "encoded-hello-cap1", "bos-only-cap0", "full-context-cap0",
)
EXACT_OUTPUTS = ("bus.events", "bos.csv", "cache.kv", "phases.txt")
STATES = (
    "idle", "score_req", "score_data", "score_mac", "score_send", "score_wait",
    "exp_read", "exp_send", "exp_wait", "prob_read", "prob_send", "prob_wait",
    "value_req", "value_data", "value_mac", "value_send", "value_wait", "output",
)
COUNTERS = (
    "score_request_stalls", "score_response_stalls", "value_request_stalls",
    "value_response_stalls", "exp_cutoffs", "exp_divide_cycles", "zero_probabilities",
    "prob_divide_cycles", "zero_prob_divide_cycles", "scalar_send_stalls", "output_stalls",
)
PHASES = {
    "key_traversal": STATES[1:4], "key_rounding": STATES[4:6], "exponential": STATES[6:9],
    "probability": STATES[9:12], "value_traversal": STATES[12:15],
    "value_rounding": STATES[15:17], "attention_output": STATES[17:], "other": STATES[:1],
}
LENGTHS = (1, 16, 64, 128, 256)


def sha(path):
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def require_pin(path, expected):
    if sha(path) != expected:
        raise ValueError(f"Pinned diagnostic input differs: {path}")


def helper(kv260):
    path = kv260 / "variants/scalar-mul-v1/test_model.py"
    require_pin(path, HELPER_PIN)
    require_pin(kv260 / "rtl/toolchain.json", TOOL_PIN)
    sys.path.insert(0, str(path.parent))
    try:
        return runpy.run_path(str(path))
    finally:
        sys.path.pop(0)


def extract(raw, workspace):
    closure = json.loads((raw / "source-closure.json").read_bytes())
    rtl = closure["generated_rtl"]["candidate"]
    if len(rtl) != 11:
        raise ValueError("Wrong adopted source geometry")
    paths = {f"candidate/rtl/{name}.sv": f"rtl/{name}.sv" for name in rtl}
    paths.update({f"oracle/{name}": f"oracle/{name}" for name in ("autonomous_core_tb.sv", "model.hex", "bos.hex")})
    for case in CASE_NAMES:
        for filename in ("input.hex", "output.hex", "scores.hex"):
            paths[f"oracle/{case}/{filename}"] = f"oracle/{case}/{filename}"
        for filename in EXACT_OUTPUTS:
            paths[f"candidate/{case}/{filename}"] = f"expected/{case}/{filename}"
    with tarfile.open(raw / "simulation.tar.gz") as archive:
        for name, relative in paths.items():
            member = archive.getmember(name)
            info = closure["members"][name]
            if not member.isfile() or member.size != info["bytes"]:
                raise ValueError(f"Invalid adopted member: {name}")
            out = workspace / relative
            out.parent.mkdir(parents=True, exist_ok=True)
            with out.open("xb") as stream:
                stream.write(archive.extractfile(member).read())
            require_pin(out, info["sha256"])
    for name, pin in rtl.items():
        require_pin(workspace / "rtl" / (name + ".sv"), pin)
    return sorted(rtl)


def compile_replay(args, workspace, names, run, env, deadline):
    original = (workspace / "oracle/autonomous_core_tb.sv").read_bytes()
    prefix, terminator, suffix = original.rpartition(b"endmodule")
    if not terminator or suffix not in (b"", b"\n"):
        raise ValueError("Unexpected adopted bench boundary")
    bench = workspace / "autonomous_core_tb.sv"
    bench.write_bytes(prefix + b'\n`include "monitor.svh"\n' + terminator + suffix)
    binary = workspace / "obj/simulation"
    run([str(args.verilator / "bin/verilator"), "--binary", "--timing", "--assert", "-Wno-fatal",
         "--top-module", "autonomous_core_tb", "-j", "2", "--Mdir", str(binary.parent), "-o", "simulation",
         "-I" + str(HERE), *[str(workspace / "rtl" / (name + ".sv")) for name in names], str(bench)],
        workspace, env, workspace / "compile.log", 150, deadline)
    return binary


def phase_totals(row):
    return {phase: sum(row[state] for state in states) for phase, states in PHASES.items()}


def parse_profile(path, expected):
    rows = []
    for line in path.read_text().splitlines():
        values = [int(item) for item in line.split()]
        position, length, *samples = values
        if position != len(rows) + 1 or length != position or min(samples) < 0:
            raise ValueError("Unexpected invocation or occupied context")
        row = dict(zip(STATES + COUNTERS, samples, strict=True))
        expected_terms = 32 * length
        for stage in ("score", "value"):
            if (row[f"{stage}_req"] - row[f"{stage}_request_stalls"] != expected_terms or
                    row[f"{stage}_data"] - row[f"{stage}_response_stalls"] != expected_terms or
                    row[f"{stage}_mac"] != expected_terms):
                raise ValueError("Cache handshake partition differs")
        if not (row["exp_read"] == row["prob_read"] == 2 * length and
                row["exp_divide_cycles"] == 96 * (2 * length - row["exp_cutoffs"]) and
                row["prob_divide_cycles"] == 64 * length and
                row["zero_prob_divide_cycles"] == 32 * row["zero_probabilities"] and
                row["output"] - row["output_stalls"] == 32):
            raise ValueError("Scalar or output accounting differs")
        row.update(position=position, context_length=length, total=sum(row[name] for name in STATES))
        row.update(phase_totals(row))
        rows.append(row)
    for boundary in ("prefix", "done"):
        position = expected[boundary]["positions"]
        if boundary == "done" and len(rows) != position:
            raise ValueError("Unexpected number of completed attention invocations")
        if sum(row["total"] for row in rows[:position]) != expected[boundary]["phases"][8]:
            raise ValueError(f"Attention cycles and parent {boundary} window do not match")
    return rows


def replay(case, expected, workspace, binary, run, env, deadline):
    output = workspace / "cases" / case
    output.mkdir(parents=True)
    cap = int(case.rsplit("-cap", 1)[1])
    oracle = workspace / "oracle"
    args = dict(MODEL=oracle / "model.hex", SCORES=oracle / "bos.hex",
                CSV=output / "bus.events", RETURNS=output / "bos.csv", INPUT=oracle / case / "input.hex",
                OUTPUT=oracle / case / "output.hex", ALLSCORES=oracle / case / "scores.hex",
                PREFIX=expected["prefix"]["positions"], OUTPUTS=expected["outputs"],
                POSITIONS=expected["done"]["positions"], CAP=cap, SKIP=1,
                REASON=1 if cap == 255 else 2 if case.startswith("full-context") else 4,
                CACHE=output / "cache.kv", PHASE=output / "phases.txt")
    run([str(binary), *[f"+{key}={value}" for key, value in args.items()]],
        output, env, output / "simulation.log", 120, deadline)
    for name in EXACT_OUTPUTS:
        require_pin(output / name, sha(workspace / "expected" / case / name))
    rows = parse_profile(output / "attention-profile.txt", expected)
    print(case, len(rows), sum(item["total"] for item in rows), flush=True)
    return rows


def save(path, data):
    with path.open("x", encoding="utf-8") as out:
        json.dump(data, out, sort_keys=True, indent=2)
        out.write("\n")


def summarise(data, archived):
    results = {}
    for case, rows in data.items():
        keys = STATES + COUNTERS + tuple(PHASES) + ("total",)
        total = {key: sum(row[key] for row in rows) for key in keys}
        positions = sum(row["context_length"] for row in rows)
        total.update(
            invocations=len(rows), complete_request_cycles=archived[case]["done"]["done"],
            accepted_kv_pairs=64 * positions, useful_operand_bytes=128 * positions,
            returned_kv_bytes=256 * positions,
            ready_cache_overlap_predicted_cycles=sum(62 * row["context_length"] - 32 for row in rows),
            parity=list(EXACT_OUTPUTS),
        )
        results[case] = total
    return {
        "cases": results,
        "fixed_context_samples": [data["full-context-cap0"][length - 1] for length in LENGTHS],
    }


def main(args):
    deadline = time.monotonic() + min(1100, args.deadline_epoch - time.time())
    top = args.repo / "hardware/research/inference"
    require_pin(top / "results" / BASELINE / "run.json", RUN_PIN)
    raw = args.repo / ".agents/runtime/hardware/inference/outputs" / BASELINE
    for filename, pin in BASE_PINS.items():
        require_pin(raw / filename, pin)
    reference = json.loads((raw / "model-results.json").read_bytes())["candidate"]
    if set(reference) != set(CASE_NAMES):
        raise ValueError("Standard diagnostics differ")
    kv260 = top / "implementations/kv260"
    tools = helper(kv260)
    env = tools["simulator"](args.verilator, kv260)
    args.output.mkdir()
    names = extract(raw, args.output)
    binary = compile_replay(args, args.output, names, tools["run"], env, deadline)
    rows = {case: replay(case, reference[case], args.output, binary, tools["run"], env, deadline) for case in CASE_NAMES}
    save(args.output / "profile.json", summarise(rows, reference))
    print("Seven exact model replays and every attention partition passed.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("repo", "verilator", "output"):
        parser.add_argument("--" + name, type=lambda value: Path(value).resolve(), required=True)
    parser.add_argument("--deadline-epoch", type=float, required=True)
    main(parser.parse_args())
