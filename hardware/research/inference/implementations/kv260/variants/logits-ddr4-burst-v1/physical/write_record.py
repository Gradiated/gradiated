"""Write the Experiment 16 physical run record from the verified Mac capture."""

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


EXPERIMENT = "kv260-logits-ddr4-burst-v1"
LABELS = {
    "encoded-hello": "Hello", "encoded-fu2p2q": "Six-byte prompt", "encoded-max48": "48-byte prompt",
}
DISPLAY = {"bram": "On-chip", "ddr": "DDR4"}
UNITS = {
    "ttft_ms": "ms", "decode_tps": "tokens/s", "completion_ms": "ms", "verified_ms": "ms",
    "first_clocks": "cycles", "last_clocks": "cycles", "request_clocks": "cycles",
    "hp0_projection_mb_s": "MB/s", "axibytes": "bytes", "useful_bytes": "bytes", "reads": "reads", "beats": "beats",
    "faults": "faults", "extra_clocks": "cycles", "ar_stalls": "cycles", "response_waits": "cycles",
    "projections": "invocations", "projection_clocks": "cycles",
    "active_power_w": "W", "idle_power_w": "W",
    "energy_per_answer_j": "J/answer", "energy_per_token_j": "J/token", "tokens_per_joule": "tokens/J",
    "gross_j": "J", "matrix_setup_ms": "ms", "model_setup_ms": "ms",
    "post_verify_check_ns": "ns", "counter_check_ms": "ms", "scored_positions": "positions",
}
METHODS = {
    "ttft_ms": "Board CPU admission before encoding and context clear to first useful byte.",
    "decode_tps": "Useful byte intervals divided by first-to-last elapsed time on the board.",
    "completion_ms": "Board CPU admission to observed stop and drain, before output verification.",
    "verified_ms": "Board CPU admission to exact output verification.",
    "first_clocks": "FPGA clock count at first useful byte.",
    "last_clocks": "FPGA clock count at last useful byte.",
    "request_clocks": "FPGA clock count at final completion.",
    "hp0_projection_mb_s": "Accepted HP0 bytes divided by projection busy time at 50 MHz.",
    "axibytes": "Eight bytes per accepted 64-bit read response.",
    "useful_bytes": "External 16-bit coefficients used by the arithmetic, in bytes.",
    "reads": "Accepted AXI read addresses.",
    "beats": "Accepted AXI read response beats.",
    "faults": "DDR reader fault events.",
    "extra_clocks": "Additional final-logits clocks beyond the on-chip operand schedule.",
    "ar_stalls": "Clocks with ARVALID asserted and ARREADY low.",
    "response_waits": "Clocks with RREADY asserted and RVALID low.",
    "projections": "Output projection invocations.",
    "projection_clocks": "Total busy clocks in the final-logits projection.",
    "active_power_w": "Sample-midpoint gross VCC_SOM integral over block time.",
    "idle_power_w": "Two equal-duration settled VCC_SOM idle brackets with the same live context.",
    "energy_per_answer_j": "Sample-midpoint gross VCC_SOM integral divided by verified block replies.",
    "energy_per_token_j": "Sample-midpoint gross VCC_SOM integral divided by useful block output bytes.",
    "tokens_per_joule": "Useful block output bytes divided by sample-midpoint gross VCC_SOM joules.",
    "gross_j": "Sample-midpoint trapezoidal VCC_SOM integral over the verified block.",
    "matrix_setup_ms": "DMA page allocation, upload, mode selection and readback before warm-up.",
    "model_setup_ms": "Native setup begin through ready state before the weight-source setup.",
    "post_verify_check_ns": "Board stopwatch interval after exact reply verification through timing/counter guard.",
    "counter_check_ms": "Sum of post-verification timings contained within the active block, excluding final reply.",
    "scored_positions": "Accepted scores divided by the 320-token vocabulary.",
}
ENERGY = ("active_power_w", "idle_power_w", "energy_per_answer_j", "energy_per_token_j",
          "tokens_per_joule", "gross_j")
COVERAGE_KEYS = {
    "ttft_ms": "ttft", "decode_tps": "decode_tps", "completion_ms": "completion_time",
    "verified_ms": "completion_time", "active_power_w": "active_power", "idle_power_w": "idle_power",
    "energy_per_answer_j": "energy_per_answer", "energy_per_token_j": "energy_per_answer",
    "gross_j": "energy_per_answer", "tokens_per_joule": "tokens_per_joule", "matrix_setup_ms": "startup",
    "reads": "memory_bandwidth", "beats": "memory_bandwidth", "useful_bytes": "memory_bandwidth",
    "axibytes": "memory_bandwidth", "hp0_projection_mb_s": "memory_bandwidth",
}
DERIVED = {"ttft_ms", "decode_tps", "completion_ms", "verified_ms", "axibytes", "hp0_projection_mb_s", "matrix_setup_ms", "model_setup_ms",
           "post_verify_check_ns", "counter_check_ms", "scored_positions", *ENERGY}


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
            add(prefix, "model_setup_ms", [arm["model_setup_ns"] / 1e6 for arm in arms])
            add(prefix, "counter_check_ms", [arm["counter_check_ns"] / 1e6 for arm in arms])
            if mode == "ddr":
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
                   "reason": "Separate routed circuits. Candidate retains on-chip input embedding and stages 512 bytes per eight-row group from a 20 KiB DMA mapping."},
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


def temperatures(evidence, arms):
    grouped = defaultdict(list)
    brackets = {}
    for label, arm in sorted(arms.items(), key=lambda item: item[1]["start_ns"]):
        brackets[label] = {}
        for edge in ("before", "after"):
            trace = load(evidence / f"{label}-{edge}.temperatures.json")
            need(trace["begin_ns"] <= trace["end_ns"], f"Invalid temperature interval: {label}/{edge}")
            boundary_verified = (trace["end_ns"] <= arm["start_ns"] if edge == "before"
                                 else trace["begin_ns"] >= arm["end_ns"])
            need(boundary_verified, f"Temperature reading overlaps active block: {label}/{edge}")
            readings = {r["label"]: r["value"] / 1000 for r in trace["sensors"] if "value" in r}
            brackets[label][edge] = readings
            for sensor, value in readings.items():
                grouped[sensor].append(value)
    summary = {name: {"first": v[0], "last": v[-1], "maximum": max(v), "samples": len(v)}
               for name, v in grouped.items()}
    return summary, brackets


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
    need(outcome == {"experiment_passed": True, "restored": True},
         "Supervisor did not complete and restore")
    exit_receipt = args.packet / "exit.json"
    if exit_receipt.is_file():
        need(load(exit_receipt)["status"] == 0, "Supervisor exit status is nonzero")
    else:
        need(args.recovery_state is not None, "Missing Mac supervisor exit receipt")
        recovered = load(args.recovery_state)
        need(recovered["boot"] == plan["boot"] and recovered["firmware"] == "gradiated-tiny-50mhz.bit.bin"
             and recovered["overlays"] == ["gradiated-tiny-clock", "gradiated-tiny-interface", "gradiated-tiny-program"]
             and recovered["taint"] == "12288", "Resumed serial stock-state probe differs")
        supervisor = (args.packet / "supervisor.txt").read_text().splitlines()
        labels = set(report["arms"]) | set(report["homogeneous_arms"]) | set(report["smokes"])
        need(labels <= {line.removesuffix(" passed") for line in supervisor if line.endswith(" passed")},
             "Recovered supervisor log does not confirm every measurement arm")
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
    all_arms = {**report["arms"], **report["homogeneous_arms"]}
    thermal, thermal_by_arm = temperatures(evidence, all_arms)
    conditions = {
        "measurement_standard": "inference-measurements-v2",
        "measurement_coverage": measurement_coverage(prior, metrics, refs, thermal),
        "mixed_timed_replies": sum(len(a["requests"]) for a in report["arms"].values()),
        "homogeneous_timed_replies": sum(len(a["requests"]) for a in report["homogeneous_arms"].values()),
        "warmups": sum(len(a["warmups"]) for a in all_arms.values()),
        "smoke_replies": sum(len(a) for a in report["smokes"].values()),
        "failures": 0, "timeouts": 0, "matrix_sha256": MATRIX, "matrix_bytes": 20480,
        "mixed_mode_order": ORDER, "homogeneous_order": HOMOGENEOUS_ORDER,
        "control_resources": build["control_resources"],
        "resource_accounting": build["resource_accounting"],
        "mixed_timing_pairs_pct": report["timing_pairs_pct"],
        "mixed_energy_pairs_pct": report["energy_pairs_pct"],
        "homogeneous_energy_pairs_pct": report["homogeneous_energy_pairs_pct"],
        "temperature_brackets_c": thermal, "arm_temperature_brackets_c": thermal_by_arm,
        "routed_timing": build["timing"],
        "fixture_resources": build["resources"], "original_restored": True,
        "mac_exit_receipt_available": exit_receipt.is_file(),
        "arms": {name: {k: a[k] for k in ("output_tokens", "idle_context", "spi", "power_trace", "dma_base",
                                         "matrix_setup_ns", "model_setup_ns", "counter_check_ns") if k in a}
                 for name, a in all_arms.items()},
        "development_effort": {"engineering_attention_minutes": None, "ai_usage_cost": None},
    }
    need(tuple(conditions[k] for k in ("mixed_timed_replies", "homogeneous_timed_replies", "warmups",
                                       "smoke_replies")) == (48, 152, 36, 9),
         "Fixed request count differs")
    return dict(
        schema_version=1, id=invocation["attempt"], experiment_id=EXPERIMENT, evidence_type="physical-measurement",
        status="passed", source=dict(commit=args.revision, patch_sha256=refs["patch"]["sha256"]),
        model=prior["model"], implementation={"id": EXPERIMENT, "sha256": firmware_hash},
        workload={"id": "kv260-ddr4-logits-abba-v1", "sha256": refs["workload"]["sha256"]},
        device=dict(id=prior["device"]["id"], configuration=config,
                    configuration_sha256=records.configuration_digest(config)),
        protocol=dict(prior["protocol"], id=EXPERIMENT, sha256=refs["protocol"]["sha256"],
                      warmup="Three mixed warm-ups or one single-prompt warm-up per ordered arm.",
                      quality_gate="Exact outputs, stop reasons and contexts. Verified AXI and FPGA cycle accounting.",
                      measurement_boundary="Board CPU admission through useful byte and completion observations. Gross VCC_SOM block integral includes request gaps and verification."),
        correctness=dict(passed=True, evidence="Exact reference outputs and validated FPGA counters on 200 timed replies, 36 warm-ups and 9 smoke replies. All 320 original BOS scores verified."),
        quality=dict(passed=True, evidence="Frozen W16A16 arithmetic, weights, workload and stopping rules."),
        conditions=conditions, started_at=load(args.packet / "dispatch.json")["utc"],
        completed_at=args.completed_at,
        metrics=metrics, artifacts=list(refs.values()), supersedes=None,
        limitations=[
            "One board and boot, three fixed prompts and an ABBA experiment with two logical pairs.",
            "Gross VCC_SOM measurements include request gaps and verification. Independent calibration and off-module power were unavailable.",
            "AXI interface bytes count accepted beats. DDR controller traffic was unavailable.",
            "Only the candidate exposes the DDR counters. Its between-request counter checks are included in gross workload energy.",
            "The separately routed candidate exposes storage savings and the added DDR interface and buffering.",
            "Kernel taint from the temporary unsigned out-of-tree module persists until reboot.",
        ],
    )


def findings(result, report, build_id, rtl_id):
    rows, energy, pairs, transport = [], [], [], []
    for case, label in LABELS.items():
        values = [report["timing"][mode][case] for mode in MODES]
        a, b = values
        cols = []
        for key, digits in (("ttft_ms",3), ("decode_tps",1), ("completion_ms",3)):
            x, y = median(a[key]), median(b[key])
            cols.append(f"{x:.{digits}f} → {y:.{digits}f} ({relative(x,y):+.2f}%)")
        paired = [p[case]["ddr_vs_bram"]["completion_ms"] for p in report["timing_pairs_pct"].values()]
        rows.append(f"| {label} | " + " | ".join(cols) + f" | {span(paired)} |")
        n = b["scored_positions"][0]
        extra = median(b["extra_clocks"])
        traffic = b["axibytes"][0]
        wait = median(b["response_waits"])
        stalls = median(b["ar_stalls"])
        transport.append(f"| {label} | {n} | {b['reads'][0]:,} | {b['beats'][0]:,} | {traffic:,} | "
                         f"{wait:,.0f} | {stalls:,.0f} | {extra:,.0f} | {extra/50_000:.3f} | {median(b['hp0_projection_mb_s']):.2f} |")
    for scope in (None, *LABELS):
        totals = {mode: arm_totals(mode_arms(report, mode, scope)) for mode in MODES}
        for mode in MODES:
            q = totals[mode]
            energy.append(f"| {LABELS[scope] if scope else 'Mixed'} | {DISPLAY[mode]} | {q['power']:.4f} | "
                          f"{q['idle']:.4f} | {q['j_answer']:.6f} | {q['j_token']:.8f} | {q['tpj']:.2f} |")
        series = report["energy_pairs_pct"] if scope is None else report["homogeneous_energy_pairs_pct"][scope]
        q = [v["ddr_vs_bram"] for v in series.values()]
        pairs.append(f"| {LABELS[scope] if scope else 'Mixed'} | "
                     f"{span(v['energy_per_answer_j'] for v in q)} | "
                     f"{span(x for v in q for x in v['energy_per_answer_by_alignment'].values())} |")
    original = result["conditions"]["control_resources"]
    candidate = result["conditions"]["fixture_resources"]
    res_rows = [
        f"| {label} | {original[key]:,g} | {candidate[key]:,g} | {candidate[key]-original[key]:+,g} |"
        for key,label in (("lut","LUTs"),("register","Registers"),("dsp","DSPs"),("bram_tile","Block RAM tiles"))
    ]
    mixed = [arm_totals(mode_arms(report, mode)) for mode in MODES]
    checks = {
        mode: median(x["counter_check_ns"] / 1e6 for x in mode_arms(report, mode))
        for mode in MODES
    }
    scope = {**report["arms"], **report["homogeneous_arms"]}
    spi = []
    for name, a in scope.items():
        q = a["spi"]
        if q["active_ms_delta"] or q["transfers_delta"]:
            spi.append(f"{name} logged {q['active_ms_delta']:+,} ms of SPI1 active time "
                       f"and {q['transfers_delta']:+,} TPM transfers.")
    spi_note = " ".join(spi) if spi else "All 20 SPI1 and TPM brackets stayed steady."
    thermal = result["conditions"]["temperature_brackets_c"]
    temp_note = " ".join(f"{sensor} first/last/max {x['first']:.1f}/{x['last']:.1f}/{x['maximum']:.1f} °C."
                         for sensor, x in thermal.items()) or "No temperature sample was available."
    setup = [a["matrix_setup_ns"]/1e6 for a in scope.values() if "matrix_setup_ns" in a]
    model_setup = {
        mode: median(a["model_setup_ns"]/1e6 for name,a in scope.items() if name.endswith("-"+mode))
        for mode in MODES
    }
    taint = result["device"]["configuration"]["restored_taint"]
    energy_change = relative(mixed[0]["j_answer"], mixed[1]["j_answer"])
    recovery_note = (" The Mac serial connection paused during the run. Completion and restoration were verified "
                     "from the checksummed board outcome, supervisor log and a fresh stock-state readback. The record "
                     "uses the first resumed stock-state readback time as an upper bound on completion."
                     if not result["conditions"]["mac_exit_receipt_available"] else "")
    return f"""# Moving the final-score weight matrix to DDR4

The DDR4 candidate matched all 200 timed replies and restored the original research image and its 320 BOS scores. The routed design changed block RAM use from {original['bram_tile']:g} to {candidate['bram_tile']:g} tiles. Gross mixed-block module energy per verified answer changed {energy_change:+.2f}%. The input embedding table stayed on-chip.{recovery_note} [Routed build and hierarchy census](../{build_id}/findings.md) · [Exact RTL replay](../{rtl_id}/findings.md)

## Mixed timings and the scored positions

Eight observations per mode and prompt. Each entry shows the median from on-chip to DDR4. First-byte and completion times are measured by the board CPU. Decode counts useful output byte intervals.

| Prompt | First useful byte, ms | Decode, tokens/s | Completion, ms | Paired completion change |
| --- | ---: | ---: | ---: | ---: |
{chr(10).join(rows)}

| Prompt | Fully scored positions | Accepted AR | Accepted R beats | HP0 bytes | Median R waits | Median AR stalls | Median added FPGA clocks | FPGA time added, ms | HP0 MB/s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(transport)}

Each complete scoring projection uses 40 groups of eight rows. It issues 320 burst addresses, accepts 2,560 beats and consumes 20,480 useful bytes. Prompt-only steps that skip final scores neither issue reads nor consume matrix bytes. The candidate adds 2,880 launch and staging clocks per fully scored position, plus measured address stalls and response waits. That sum matched the entire added request time in FPGA clocks on every reply. The on-chip control reproduced the selected circuit's exact first, last and complete request counters. HP0 throughput divides accepted bytes by projection busy time at 50 MHz.

## Gross VCC_SOM energy

The 20 powered blocks used matched ready-idle brackets. Mixed blocks and single-prompt blocks are pooled separately. Active watts divide integrated joules by block time and idle watts average the settled brackets. The same gross block joules are divided by verified answers and by useful tokens. The sequential calculation uses no independent DDR-only power sensor.

| Scope | Mode | Active W | Idle W | Gross J/answer | Gross J/token | Tokens/J |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(energy)}

| Scope | Paired change in gross J/answer | Five-alignment range |
| --- | ---: | ---: |
{chr(10).join(pairs)}

A contiguous energy block includes inter-reply verification and counter-check gaps. The median sum of the in-block post-verification check times in the mixed blocks was {checks['bram']:.3f} ms on-chip and {checks['ddr']:.3f} ms on DDR4. Only the candidate reads the DDR-specific counters. The per-reply completion times end earlier. {spi_note}

## Resources and operating conditions

| Resource | On-chip | DDR4 | Change |
| --- | ---: | ---: | ---: |
{chr(10).join(res_rows)}

The candidate retains the on-chip input embedding and adds a 512-byte staging buffer for each group. Exact hierarchy counts and timing slacks are in the routed build. Median native model setup was {model_setup['bram']:.1f} ms on-chip and {model_setup['ddr']:.1f} ms on DDR4. The separate DMA page allocation, upload and mode setup took {min(setup):.3f}–{max(setup):.3f} ms. Neither setup enters the timed arms. {temp_note}

Nine smoke replies and 36 warm-ups passed. The four logical sessions ran in ABBA order with three comparison image loads on one boot. After the last checked DMA release, the original FPGA image, HP0 state, weights and all 320 original BOS scores passed restoration. Kernel taint remained {taint}, the same value admitted after Experiment 15. Experiment 13 remains selected.

[Run record](run.json) · [Executed protocol](../../experiments/{EXPERIMENT}.md)
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
    parser.add_argument("--recovery-state", type=Path, help="Fresh verified stock receipt when Mac lost the exit line.")
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
    if args.recovery_state is not None:
        files["recovery_state"] = args.recovery_state
    for helper in ("score_fixture.py", "measurement.py", "write_record.py", "lifecycle.py"):
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
