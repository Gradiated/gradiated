"""Write the Experiment 15 physical run record from the verified Mac capture."""

import argparse
from collections import defaultdict
from datetime import datetime
import hashlib
import json
from pathlib import Path
import tarfile
from statistics import mean, median

from measurement import HOMOGENEOUS_REPLIES
from score_fixture import HOMOGENEOUS_ORDER, MATRIX, MODES, ORDER
from score_fixture import load, module_at, need, relative, score


EXPERIMENT = "kv260-output-projection-ddr4-burst-v1"
LABELS = {
    "encoded-hello": "Hello", "encoded-fu2p2q": "Six-byte prompt", "encoded-max48": "48-byte prompt",
}
DISPLAY = {"bram": "BRAM", "scalar": "DDR scalar", "beat": "DDR beat", "row": "DDR row"}
UNITS = {
    "ttft_ms": "ms", "decode_tps": "tokens/s", "completion_ms": "ms", "verified_ms": "ms",
    "first_clocks": "cycles", "last_clocks": "cycles", "request_clocks": "cycles",
    "axibytes": "bytes", "useful_bytes": "bytes", "reads": "reads", "beats": "beats",
    "faults": "faults", "extra_clocks": "cycles", "ar_stalls": "cycles", "response_waits": "cycles",
    "projections": "invocations", "projection_clocks": "cycles",
    "active_power_w": "W", "idle_power_w": "W",
    "energy_per_answer_j": "J/answer", "energy_per_token_j": "J/token", "tokens_per_joule": "tokens/J",
    "gross_j": "J", "matrix_setup_ms": "ms",
}
METHODS = {
    "ttft_ms": "Board CPU admission before encoding and context clear to first useful byte.",
    "decode_tps": "Useful byte intervals divided by first-to-last elapsed time on the board.",
    "completion_ms": "Board CPU admission to observed stop and drain, before output verification.",
    "verified_ms": "Board CPU admission to exact output verification.",
    "first_clocks": "FPGA clock count at first useful byte.",
    "last_clocks": "FPGA clock count at last useful byte.",
    "request_clocks": "FPGA clock count at final completion.",
    "axibytes": "Eight bytes per accepted 64-bit read response.",
    "useful_bytes": "External 16-bit coefficients used by the arithmetic, in bytes.",
    "reads": "Accepted AXI read addresses.",
    "beats": "Accepted AXI read response beats.",
    "faults": "DDR reader fault events.",
    "extra_clocks": "Additional output-projection clocks beyond the BRAM operand schedule.",
    "ar_stalls": "Clocks with ARVALID asserted and ARREADY low.",
    "response_waits": "Clocks with RREADY asserted and RVALID low.",
    "projections": "Output projection invocations.",
    "projection_clocks": "Total busy clocks in the output projection.",
    "active_power_w": "Sample-midpoint gross VCC_SOM integral over block time.",
    "idle_power_w": "Two equal-duration settled VCC_SOM idle brackets with the same live context.",
    "energy_per_answer_j": "Sample-midpoint gross VCC_SOM integral divided by verified block replies.",
    "energy_per_token_j": "Sample-midpoint gross VCC_SOM integral divided by useful block output bytes.",
    "tokens_per_joule": "Useful block output bytes divided by sample-midpoint gross VCC_SOM joules.",
    "gross_j": "Sample-midpoint trapezoidal VCC_SOM integral over the verified block.",
    "matrix_setup_ms": "DMA page allocation, upload, mode selection and readback before warm-up.",
}
ENERGY = ("active_power_w", "idle_power_w", "energy_per_answer_j", "energy_per_token_j",
          "tokens_per_joule", "gross_j")
COVERAGE_KEYS = {
    "ttft_ms": "ttft", "decode_tps": "decode_tps", "completion_ms": "completion_time",
    "verified_ms": "completion_time", "active_power_w": "active_power", "idle_power_w": "idle_power",
    "energy_per_answer_j": "energy_per_answer", "energy_per_token_j": "energy_per_answer",
    "gross_j": "energy_per_answer", "tokens_per_joule": "tokens_per_joule", "matrix_setup_ms": "startup",
    "reads": "memory_bandwidth", "beats": "memory_bandwidth", "useful_bytes": "memory_bandwidth",
    "axibytes": "memory_bandwidth",
}
DERIVED = {"ttft_ms", "decode_tps", "completion_ms", "verified_ms", "axibytes", "matrix_setup_ms", *ENERGY}


def digest(stream):
    result = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b""):
        result.update(block)
    return result.hexdigest()


def sha(path):
    with path.open("rb") as file:
        return digest(file)


def pin(path, repo, role):
    return dict(path=str(path.relative_to(repo)), sha256=sha(path), bytes=path.stat().st_size, role=role)


def write_json(path, value):
    encoded = json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if path.exists():
        need(path.read_text() == encoded, f"Existing record differs: {path}")
    else:
        with path.open("x") as file:
            file.write(encoded)


def verify_recovered(packet):
    archive = packet / "board-evidence.tar.gz"
    receipt = load(packet / "recovered.json")
    need(archive.stat().st_size == receipt["bytes"] and sha(archive) == receipt["sha256"],
         "Recovered board archive digest mismatch")
    names = set()
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar:
            name = Path(member.name)
            need(member.isfile() and name not in names and not name.is_absolute() and ".." not in name.parts,
                 f"Invalid archive member: {name}")
            names.add(name)
            path = packet / name
            need(path.is_file() and not path.is_symlink(), f"Missing receipt: {path}")
            with tar.extractfile(member) as stream:
                need(digest(stream) == sha(path), f"Extracted receipt differs from archive: {name}")


def mode_arms(report, mode, case=None):
    if case is None:
        return [report["arms"][f"p{i}-{mode}"] for i in range(1, 5)]
    return [report["homogeneous_arms"][f"homogeneous-p{i}-{case}-{mode}"] for i in (1, 2)]


def arm_totals(arms):
    joules = sum(a["gross_j"] for a in arms)
    seconds = sum(a["length_ns"] for a in arms) / 1e9
    outputs = sum(a["output_tokens"] for a in arms)
    replies = sum(len(a["requests"]) for a in arms)
    return {
        "j_answer": joules / replies, "j_token": joules / outputs, "tpj": outputs / joules,
        "power": joules / seconds, "idle": mean(w for arm in arms for w in arm["idle_power_w"]),
        "seconds": seconds, "outputs": outputs, "replies": replies,
    }


def measurements(report):
    result = []

    def add(prefix, field, samples):
        result.append(dict(name=f"{prefix}.{field}", unit=UNITS[field], method=METHODS[field],
                           kind="derived" if field in DERIVED else "observed", samples=samples))

    for mode in MODES:
        for case, values in report["timing"][mode].items():
            for field, samples in values.items():
                add(f"{mode}.{case}", field, samples)
        for case in (None, *LABELS):
            prefix = f"{mode}.mixed" if case is None else f"{mode}.homogeneous.{case}"
            arms = mode_arms(report, mode, case)
            for field in ENERGY:
                add(prefix, field, [value for arm in arms for value in
                                  (arm[field] if field == "idle_power_w" else [arm[field]])])
            add(prefix, "matrix_setup_ms", [arm["matrix_setup_ns"] / 1e6 for arm in arms])
    return result


def measurement_coverage(prior, metrics, refs, temperatures):
    result = {}
    for metric in metrics:
        label = metric["name"].rsplit(".", 1)[-1]
        key = COVERAGE_KEYS.get(label, "stage_cycles")
        coverage = result.setdefault(key, {"state": "measured" if key == "stage_cycles" else "derived",
                                           "metrics": []})
        coverage["metrics"].append(metric["name"])
    result["memory_bandwidth"]["reason"] = "Eight bytes per accepted beat at HP0. DDR controller traffic was unavailable."
    result.update({
        "correctness": {"state": "measured", "sources": [refs["score"], refs["rtl"]]},
        "output_counts": {"state": "measured", "sources": [refs["score"]]},
        "repeatability": {"state": "measured", "sources": [refs["score"]]},
        "resources": {"state": "reused", "sources": [refs["build"]]},
        "implementation_timing": {"state": "reused", "sources": [refs["build"]]},
        "memory": {"state": "reused", "sources": [refs["build"], refs["memory"], refs["score"]],
                   "reason": "All modes share the fixture. Distinct storage includes the on-chip copy, four-lane beat and 32-weight row buffers, and the mapped host page."},
        "operating_conditions": {"state": "measured", "sources": [refs["archive"]],
                                 "reason": "Linux clock readback and temperature brackets." if temperatures
                                 else "Linux clock readback. No temperature samples were available."},
        "recovery": {"state": "measured", "sources": [refs["outcome"], refs["after_bos"]]},
        "workload_coverage": {"state": "measured", "sources": [refs["score"], refs["protocol"]]},
        "cache_capacity": {"state": "reused", "sources": [refs["memory"]]},
        "token_gaps": {"state": "measured", "sources": [refs["archive"]]},
        "idle_subtracted_energy": {"state": "derived", "sources": [refs["score"]],
                                   "reason": "Stored in sensitivity results. Primary comparisons are gross."},
        "prefill": {"state": "not_measured", "reason": "No separate prefill timer. TTFT and internal counters are available."},
        "sustained_throughput": {"state": "not_measured", "reason": "Only bounded single-request comparison blocks."},
        "power_validation": {"state": "not_measured", "reason": "Module sensor was used without independent calibration."},
    })
    for key in prior["conditions"]["measurement_coverage"]:
        result.setdefault(key, {"state": "not_applicable", "reason": "Outside the fixed one-board circuit comparison."})
    return result


def temperatures(evidence):
    grouped = defaultdict(list)
    labels = [f"p{r}-{m}" for r, m in ORDER]
    labels += [f"homogeneous-p{r}-{case}-{m}" for r, case, m in HOMOGENEOUS_ORDER]
    for label in labels:
        for edge in ("before", "after"):
            path = evidence / f"{label}-{edge}.temperatures.json"
            if path.is_file():
                for reading in load(path)["sensors"]:
                    if "value" in reading:
                        grouped[reading["label"]].append(reading["value"] / 1000)
    return {name: {"first": v[0], "last": v[-1], "maximum": max(v), "samples": len(v)}
            for name, v in grouped.items()}


def record(args, project, report, refs):
    prior = load(project / "results/attention-exp-pair-v2-20261117T232821Z-e72da4/run.json")
    records = module_at("records", project / "tools/records.py")
    evidence = args.packet / "evidence"
    outcome = load(evidence / "outcome.json")
    invocation = load(args.packet / "invocation.json")
    plan = load(evidence / "intent.json")
    allowed = plan["configuration"]
    build = load(args.build)
    firmware = allowed["firmware"]
    firmware_hash = allowed["pins"][firmware]["sha256"]
    need(build["passed"] and build["firmware_assets"][firmware] == firmware_hash,
         "Live fixture differs from the admitted routed image")
    need(outcome["experiment_passed"] and outcome["restored"] and load(args.packet / "exit.json")["status"] == 0,
         "Supervisor did not complete and restore")
    initial, final = (load(evidence / f"{name}.state.json") for name in ("admission", "restored"))
    need(initial["boot_id"] == final["boot_id"] == invocation["boot"] == plan["boot"],
         "Unexpected boot transition")
    before, after = (load(evidence / f"original-{edge}.stdout") for edge in ("before", "after"))
    need(len(before["logits"]) == 320 and before["logits"] == after["logits"]
         and all(item["accepted"] and not item["mismatch_indices"] for item in (before, after)),
         "Original BOS verification failed")
    config = dict(model=initial["model"], kernel=initial["kernel"], boot_id=initial["boot_id"],
                  configured_pl0_hz=50_000_000, fixture_firmware_sha256=firmware_hash,
                  initial_taint=initial["taint"], restored_taint=final["taint"],
                  original_state_sha256=refs["initial"]["sha256"], restored_state_sha256=refs["restored"]["sha256"])
    metrics = measurements(report)
    thermal = temperatures(evidence)
    all_arms = {**report["arms"], **report["homogeneous_arms"]}
    conditions = {
        "measurement_standard": "inference-measurements-v2",
        "measurement_coverage": measurement_coverage(prior, metrics, refs, thermal),
        "mixed_timed_replies": sum(len(a["requests"]) for a in report["arms"].values()),
        "homogeneous_timed_replies": sum(len(a["requests"]) for a in report["homogeneous_arms"].values()),
        "warmups": sum(len(a["warmups"]) for a in all_arms.values()),
        "smoke_replies": sum(len(a) for a in report["smokes"].values()),
        "failures": 0, "timeouts": 0, "matrix_sha256": MATRIX, "matrix_bytes": 2048,
        "mixed_mode_order": ORDER, "homogeneous_order": HOMOGENEOUS_ORDER,
        "mixed_timing_pairs_pct": report["timing_pairs_pct"],
        "mixed_energy_pairs_pct": report["energy_pairs_pct"],
        "homogeneous_energy_pairs_pct": report["homogeneous_energy_pairs_pct"],
        "temperature_brackets_c": thermal, "routed_timing": build["timing"],
        "fixture_resources": build["resources"], "original_restored": True,
        "arms": {name: {k: a[k] for k in ("output_tokens", "idle_context", "spi", "power_trace", "dma_base",
                                         "matrix_setup_ns")} for name, a in all_arms.items()},
        "development_effort": {"engineering_attention_minutes": None, "ai_usage_cost": None},
    }
    need(tuple(conditions[k] for k in ("mixed_timed_replies", "homogeneous_timed_replies", "warmups",
                                       "smoke_replies")) == (96, 304, 72, 12),
         "Fixed request count differs")
    return dict(
        schema_version=1, id=invocation["attempt"], experiment_id=EXPERIMENT, evidence_type="physical-measurement",
        status="passed", source=dict(commit=args.revision, patch_sha256=refs["patch"]["sha256"]),
        model=prior["model"], implementation={"id": EXPERIMENT, "sha256": firmware_hash},
        workload={"id": "kv260-ddr4-four-mode-fixed-v1", "sha256": refs["workload"]["sha256"]},
        device=dict(id=prior["device"]["id"], configuration=config,
                    configuration_sha256=records.configuration_digest(config)),
        protocol=dict(prior["protocol"], id=EXPERIMENT, sha256=refs["protocol"]["sha256"],
                      warmup="Three mixed warm-ups or one single-prompt warm-up per ordered arm.",
                      quality_gate="Exact outputs, stop reasons and contexts. Verified AXI and FPGA cycle accounting.",
                      measurement_boundary="Board CPU admission through useful byte and completion observations. Gross VCC_SOM block integral includes request gaps and verification."),
        correctness=dict(passed=True, evidence="Exact reference outputs and validated FPGA counters on 400 timed replies, 72 warm-ups and 12 smoke replies. All 320 original BOS scores verified."),
        quality=dict(passed=True, evidence="Frozen W16A16 arithmetic, weights, workload and stopping rules."),
        conditions=conditions, started_at=load(args.packet / "dispatch.json")["utc"],
        completed_at=args.completed_at,
        metrics=metrics, artifacts=list(refs.values()), supersedes=None,
        limitations=[
            "One board and boot, three fixed prompts and the four-mode fixture.",
            "Gross VCC_SOM measurements include request gaps and verification. Independent calibration and off-module power were unavailable.",
            "AXI interface bytes count accepted beats. DDR controller traffic was unavailable.",
            "The route contains all storage paths. Its resource report measures the comparison fixture.",
            "Kernel taint from the temporary unsigned out-of-tree module persists until reboot.",
        ],
    )


def findings(result, report, build_id, rtl_id):
    time = report["timing"]
    timing_rows = []
    comparisons = []
    transport_rows = []
    for mode in MODES:
        rows = [r for a in mode_arms(report, mode) for r in a["requests"]]
        totals = {
            key: median(r[key] / r["projections"] for r in rows)
            for key in ("ar_stalls", "response_waits", "extra_clocks")
        }
        nonfinal = median((r["beats"] - r["reads"]) / r["projections"] for r in rows)
        transport_rows.append(f"| {DISPLAY[mode]} | {totals['ar_stalls']:,.2f} | "
                              f"{totals['response_waits']:,.2f} | {nonfinal:,.2f} | "
                              f"{totals['extra_clocks']:,.2f} |")
    for case, label in LABELS.items():
        for mode in MODES:
            numbers = time[mode][case]
            fields = ("ttft_ms", "decode_tps", "completion_ms", "request_clocks", "extra_clocks")
            ttft, decode, completion, cycles, extra = (median(numbers[field]) for field in fields)
            timing_rows.append(
                f"| {label} | {DISPLAY[mode]} | {ttft:.3f} | {decode:.1f} | "
                f"{completion:.3f} | {cycles:,.0f} | {extra:,.0f} |")
        pairs = [p[case] for p in report["timing_pairs_pct"].values()]
        comparisons.append(
            f"| {label} | " + " | ".join(
                span(p[name]["completion_ms"] for p in pairs)
                for name in ("beat_vs_scalar", "row_vs_beat", "row_vs_scalar", "row_vs_bram"))
            + f" | {median(time['row'][case]['extra_clocks']) / 50_000:.3f} | "
            + f"{median(time['row'][case]['completion_ms']) - median(time['bram'][case]['completion_ms']):+.3f} |")
    energy_rows = []
    for mode in MODES:
        total = arm_totals(mode_arms(report, mode))
        energy_rows.append(f"| {DISPLAY[mode]} | {total['power']:.4f} | {total['idle']:.4f} | "
                           f"{total['j_answer']:.6f} | {total['j_token']:.8f} | {total['tpj']:.2f} |")
    scalar = arm_totals(mode_arms(report, "scalar"))
    row = arm_totals(mode_arms(report, "row"))
    bram = arm_totals(mode_arms(report, "bram"))
    per_case = []
    for case, label in LABELS.items():
        for mode in MODES:
            a = arm_totals(mode_arms(report, mode, case))
            per_case.append(f"| {label} | {DISPLAY[mode]} | {HOMOGENEOUS_REPLIES[case]} | "
                            f"{a['j_answer']:.6f} | {a['j_token']:.8f} | {a['tpj']:.2f} |")
    pair_rows = []
    for scope, pairs in (("Mixed", report["energy_pairs_pct"]),
                         *((LABELS[c], d) for c, d in report["homogeneous_energy_pairs_pct"].items())):
        comparisons_in_scope = [
            span(r[contrast]["energy_per_answer_j"] for r in pairs.values())
            for contrast in ("beat_vs_scalar", "row_vs_beat", "row_vs_scalar", "row_vs_bram")
        ]
        alignment = span(v for p in pairs.values()
                         for v in p["row_vs_scalar"]["energy_per_answer_by_alignment"].values())
        pair_rows.append(f"| {scope} | " + " | ".join(comparisons_in_scope) + f" | {alignment} |")
    peripheral = []
    for name, arm in {**report["arms"], **report["homogeneous_arms"]}.items():
        status = arm["spi"]
        if status["active_ms_delta"] or status["transfers_delta"]:
            peripheral.append(f"{name} (SPI1 {status['active_ms_delta']:+,} ms, TPM "
                              f"{status['transfers_delta']:+,} transfers)")
    if peripheral:
        spi_note = ("Recorded SPI1 or TPM changes occurred in these brackets. "
                    + ", ".join(peripheral) + ". The bracket does not isolate peripheral energy.")
    else:
        spi_note = "All 40 SPI1 active-time and TPM transfer brackets remained steady."
    config = result["device"]["configuration"]
    build = result["conditions"]["fixture_resources"]
    timing = result["conditions"]["routed_timing"]
    return f"""# Reading attention output weights in beats and row bursts

Row bursts changed gross mixed-block energy per answer by {relative(scalar['j_answer'], row['j_answer']):+.2f}% against one read per weight and by {relative(bram['j_answer'], row['j_answer']):+.2f}% against BRAM. The four modes matched all 400 timed replies, 72 warm-ups and 12 smoke replies. Both the added whole-request FPGA clocks and the added output-projection clocks reconciled to the measured transport waits.

All modes shared the routed 50 MHz fixture, arithmetic and workload. One projection applies a 32-by-32 matrix of signed 16-bit weights. Beat reuse supplies four operands from each 64-bit response. Row reuse serves 32 operands from one eight-beat AXI burst. [Routed fixture](../{build_id}/findings.md) · [Exact RTL replay](../{rtl_id}/findings.md)

| Mode | AR transactions per projection | R beats per projection | AXI bytes | Useful DDR bytes |
| --- | ---: | ---: | ---: | ---: |
| BRAM | 0 | 0 | 0 | 0 |
| DDR scalar | 1,024 | 1,024 | 8,192 | 2,048 |
| DDR beat | 256 | 256 | 2,048 | 2,048 |
| DDR row | 32 | 256 | 2,048 | 2,048 |

AXI bytes describe the HP0 interface. The experiment used no DDR-controller traffic counter. Added clocks equal twice the number of accepted addresses plus address stalls, response waits and accepted nonfinal beats. The BRAM projection itself takes 2,112 clocks per invocation.

| Mode | Median address stalls | Median response waits | Nonfinal beats | Median added clocks |
| --- | ---: | ---: | ---: | ---: |
{chr(10).join(transport_rows)}

Each entry is per projection invocation, calculated on each mixed reply and then summarized over replies.

## Mixed timing and FPGA clocks

Eight timed observations per prompt and mode. Values are medians. The board CPU observed the first byte, useful-byte stream and completion. The hardware autonomously recorded its own clocks.

| Prompt | Mode | First byte, ms | Decode, tokens/s | Completion, ms | Request clocks | Added projection clocks |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(timing_rows)}

| Prompt | Beat vs scalar completion | Row vs beat | Row vs scalar | Row vs BRAM | Row added FPGA ms | Row added wall ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(comparisons)}

Each range spans the four within-round changes in median completion time. Comparing row and beat isolates the change in address issue and burst response schedule with the same AXI payload bytes.

## Gross module energy

The INA260 measured the VCC_SOM rail. Active power divides pooled energy by pooled active block time. Gross energy per answer and per token divide summed joules by the corresponding completed work, including context clear, request gaps and verification. Idle power averages the equal-duration ready-idle windows. Mixed and single-prompt blocks use separate pools.

| Mode | Active W | Ready-idle W | Gross J/answer | J/output token | Tokens/J |
| --- | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(energy_rows)}

Relative to scalar mode, row mode changed total mixed-block duration by {relative(scalar['seconds'], row['seconds']):+.2f}% and active power by {relative(scalar['power'], row['power']):+.2f}%. Both changes enter the gross block energy.

| Prompt | Mode | Replies per block | Gross J/answer | J/output token | Tokens/J |
| --- | --- | ---: | ---: | ---: | ---: |
{chr(10).join(per_case)}

| Scope | Beat vs scalar J/answer | Row vs beat | Row vs scalar | Row vs BRAM | Row vs scalar five-alignment range |
| --- | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(pair_rows)}

{spi_note} The archived run retains every bracket and power sample, including the five sample-alignment scenarios.

## Routed resources and restoration

The shared fixture used {build['lut']:,.0f} LUTs, {build['register']:,.0f} registers, {build['dsp']:,.0f} DSPs and {build['bram_tile']:g} block RAM tiles. The worst setup and hold slacks were {float(timing['setup_slack_ns']):.3f} ns and {float(timing['hold_slack_ns']):.3f} ns. The fixture retains the BRAM storage and supports both forms of reuse. Its resource counts describe the fixture.

The original image and weights were restored after the final verified DMA release. All 320 original BOS scores matched. Final kernel taint was {config['restored_taint']}. Evidence covers this board and boot. Experiment 13 remains the selected circuit comparison baseline.

[Run record](run.json) · [Protocol](../../experiments/{EXPERIMENT}.md)
"""


def span(values):
    values = list(values)
    return f"{min(values):+.2f}% to {max(values):+.2f}%"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("repo", "packet", "historic", "build", "rtl", "protocol", "patch", "output"):
        parser.add_argument(name, type=Path)
    parser.add_argument("revision")
    parser.add_argument("--completed-at", required=True,
                        help="Timezone-aware Mac UTC receipt time when the board supervisor returned.")
    parser.add_argument("--energy-dir", type=Path, help="Directory with the exact two energy helper scripts.")
    args = parser.parse_args()
    need(datetime.fromisoformat(args.completed_at).tzinfo is not None, "Completion time needs timezone")
    project = args.repo / "hardware/research/inference"
    evidence = args.packet / "evidence"
    verify_recovered(args.packet)
    analysis = args.energy_dir or args.historic
    pins = load(evidence / "intent.json")["configuration"]["pins"]
    for file in ("energy_analysis.py", "energy_validation.py"):
        need(sha(analysis / file) == pins[file]["sha256"], f"Offline analysis helper differs: {file}")
    report = score(evidence, args.historic, analysis)
    score_path = args.packet / "score.json"
    workload = args.packet / "scored-workload.json"
    write_json(score_path, report)
    write_json(workload, {
        "mixed_order": ORDER, "homogeneous_order": HOMOGENEOUS_ORDER,
        "homogeneous_replies_per_block": HOMOGENEOUS_REPLIES,
        "historical_workload_sha256": sha(args.historic / "workload.json"),
    })
    files = {
        "initial": evidence / "admission.state.json", "restored": evidence / "restored.state.json",
        "before_bos": evidence / "original-before.stdout", "after_bos": evidence / "original-after.stdout",
        "outcome": evidence / "outcome.json", "archive": args.packet / "board-evidence.tar.gz",
        "receipt": args.packet / "recovered.json", "invocation": args.packet / "invocation.json",
        "protocol": args.protocol, "patch": args.patch, "rtl": args.rtl, "build": args.build,
        "score": score_path, "workload": workload,
        "memory": project / "implementations/kv260/resource-memory-baseline.json",
        "energy_analysis": analysis / "energy_analysis.py", "energy_validation": analysis / "energy_validation.py",
    }
    for helper in ("score_fixture.py", "measurement.py", "write_record.py"):
        files[helper] = Path(__file__).resolve().parent / helper
    refs = {key: pin(path, args.repo, key) for key, path in files.items()}
    value = record(args, project, report, refs)
    records = module_at("records", project / "tools/records.py")
    records.validate(value)
    text = findings(value, report, args.build.parent.name, args.rtl.parent.name)
    args.output.mkdir()
    write_json(args.output / "run.json", value)
    with (args.output / "findings.md").open("x") as file:
        file.write(text)


if __name__ == "__main__":
    main()
