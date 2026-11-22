"""Write the Experiment 17 physical run record from the verified Mac capture."""

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


EXPERIMENT = "kv260-logits-ddr4-prefetch-v1"
CONTROL = "logits-ddr4-burst-20261119T121954Z-31256a"
LABELS = {
    "encoded-hello": "Hello", "encoded-fu2p2q": "Six-byte prompt", "encoded-max48": "48-byte prompt",
}
DISPLAY = {"sequential": "Sequential", "prefetch": "Prefetch"}
UNITS = {
    "ttft_ms": "ms", "decode_tps": "tokens/s", "completion_ms": "ms", "verified_ms": "ms",
    "first_clocks": "cycles", "last_clocks": "cycles", "request_clocks": "cycles",
    "hp0_projection_mb_s": "MB/s", "axibytes": "bytes", "useful_bytes": "bytes", "reads": "reads", "beats": "beats",
    "hidden_clocks": "cycles", "transport_clocks": "cycles",
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
    "extra_clocks": "Exposed score-stage operand wait beyond the identical 1,680-clock per-position arithmetic schedule.",
    "hidden_clocks": "Accepted AR plus accepted R plus AR stalls plus R waits, minus exposed operand wait.",
    "transport_clocks": "Accepted AR plus accepted R plus AR stalls plus R waits.",
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
           "post_verify_check_ns", "counter_check_ms", "scored_positions", "hidden_clocks", "transport_clocks", *ENERGY}


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
                   "reason": "Both arms retain on-chip input embeddings, use the same 20 KiB DMA mapping and fetch 512-byte groups."},
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
    prior = load(project / "results" / CONTROL / "run.json")
    records = module_at("records", project / "tools/records.py")
    evidence = args.packet / "evidence"
    outcome = load(evidence / "outcome.json")
    invocation = load(args.packet / "invocation.json")
    plan = load(evidence / "intent.json")
    allowed = plan["configuration"]
    build = load(args.build)
    need(allowed["pins"] == invocation["sources"] and allowed["qualification"] == invocation["qualification"],
         "Board configuration differed from its invocation")
    firmware = allowed["arms"]["prefetch"]["firmware"]
    control_firmware = allowed["arms"]["sequential"]["firmware"]
    firmware_hash = allowed["pins"][firmware]["sha256"]
    control_hash = allowed["pins"][control_firmware]["sha256"]
    need(build["passed"] and build["firmware_assets"][firmware] == firmware_hash
         and build["control_firmware_assets"][control_firmware] == control_hash == prior["implementation"]["sha256"]
         and refs["build"]["sha256"] == allowed["qualification"]["release_sha256"]
         and refs["protocol"]["sha256"] == allowed["qualification"]["protocol_sha256"],
         "Live fixtures differ from the admitted routed images or protocol")
    need(outcome == {"experiment_passed": True, "restored": True}, "Supervisor did not complete and restore")
    status = load(args.completed)
    need(status["outcome"] == outcome and not status["running"] and
         load(args.packet / "supervisor-pid.json")["pid"] == status["pid"], "Supervisor outcome differs from live receipt")
    recovered = load(args.recovery_state)
    need(recovered["boot"] == plan["boot"] and recovered["firmware"] == "gradiated-tiny-50mhz.bit.bin"
         and recovered["overlays"] == ["gradiated-tiny-clock", "gradiated-tiny-interface", "gradiated-tiny-program"]
         and recovered["taint"] == "12288" and not any((recovered["module"], recovered["dma"])),
         "Fresh serial stock-state probe differs")
    supervisor = (args.packet / "supervisor.txt").read_text().splitlines()
    labels = set(report["arms"]) | set(report["homogeneous_arms"]) | set(report["smokes"])
    need(labels == {line.removesuffix(" passed") for line in supervisor if line.endswith(" passed")},
         "Supervisor log does not confirm the complete arm set")
    initial, final = (load(evidence / f"{name}.state.json") for name in ("admission", "restored"))
    need(initial["boot_id"] == final["boot_id"] == invocation["boot"] == plan["boot"],
         "Unexpected boot transition")
    need(all(initial[key] == final[key] for key in ("firmware_name", "overlays", "taint", "uio", "bindings")),
         "Restored firmware or board state differs")
    before, after = (load(evidence / f"original-{edge}.stdout") for edge in ("before", "after"))
    need(len(before["logits"]) == 320 and before["logits"] == after["logits"]
         and all(item["accepted"] and not item["mismatch_indices"] for item in (before, after)),
         "Original BOS verification failed")
    need(load(evidence / "hp0-baseline.json") == load(evidence / "hp0-exit.stdout") == recovered["hp0"],
         "Original HP0, FPD, or SMMU words did not restore")
    need(load(evidence / "original-direct-dma-dt.json") == load(evidence / "restored-direct-dma-dt.json"),
         "Original direct DMA device tree changed")
    config = dict(model=initial["model"], kernel=initial["kernel"], boot_id=initial["boot_id"],
                  configured_pl0_hz=50_000_000, fixture_firmware_sha256=firmware_hash, control_firmware_sha256=control_hash,
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
        "control_run": CONTROL,
        "supervisor_completion_observed_at": status["utc"],
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
        workload={"id": "kv260-ddr4-prefetch-abba-v1", "sha256": refs["workload"]["sha256"]},
        device=dict(id=prior["device"]["id"], configuration=config,
                    configuration_sha256=records.configuration_digest(config)),
        protocol=dict(prior["protocol"], id=EXPERIMENT, sha256=refs["protocol"]["sha256"],
                      warmup="Three mixed warm-ups or one single-prompt warm-up per ordered arm.",
                      quality_gate="Exact outputs, stop reasons and contexts. Verified AXI and FPGA cycle accounting.",
                      measurement_boundary="Board CPU admission through useful byte and completion observations. Gross VCC_SOM block integral includes request gaps and verification."),
        correctness=dict(passed=True, evidence="Exact reference outputs and validated FPGA counters on 200 timed replies, 36 warm-ups and 9 smoke replies. All 320 original BOS scores verified."),
        quality=dict(passed=True, evidence="Frozen W16A16 arithmetic, weights, workload and stopping rules."),
        conditions=conditions, started_at=load(args.packet / "dispatch.json")["utc"],
        completed_at=status["utc"],
        metrics=metrics, artifacts=list(refs.values()), supersedes=None,
        limitations=[
            "One board and boot, three fixed prompts and an ABBA experiment with four mixed and two homogeneous pairs per prompt.",
            "Gross VCC_SOM energy includes inter-request verification and identical counter reads. Independent calibration and off-module power were unavailable.",
            "Accepted HP0 bytes may differ from physical DDR controller traffic. Hidden service is derived from interface and projection counters.",
            "SPI1/TPM probes bracket each active window with a finite read delay.",
            "The first complete live status receipt places an upper bound on completion time.",
            "Kernel taint from the temporary unsigned out-of-tree module persists until reboot.",
        ],
    )


def span(values, precision=2):
    return f"{min(values):+.{precision}f}% to {max(values):+.{precision}f}%"


def findings(result, report, build_id, rtl_id):
    timing_rows, transport_rows, energy_rows, sensitivity_rows, rates, completion_changes = [], [], [], [], [], []
    for case, label in LABELS.items():
        a, b = (report["timing"][mode][case] for mode in MODES)
        values = []
        for key, digits in (("ttft_ms", 3), ("decode_tps", 1), ("completion_ms", 3)):
            x, y = median(a[key]), median(b[key])
            values.append(f"{x:.{digits}f} → {y:.{digits}f} ({relative(x, y):+.2f}%)")
        completion_changes.append(relative(median(a["completion_ms"]), median(b["completion_ms"])))
        paired = [p[case]["prefetch_vs_sequential"]["completion_ms"] for p in report["timing_pairs_pct"].values()]
        timing_rows.append(f"| {label} | " + " | ".join(values) + f" | {span(paired)} |")
        rates.append(f"{median(a['hp0_projection_mb_s']):.1f} → "
                     f"{median(b['hp0_projection_mb_s']):.1f} MB/s for {label}")
        scores = a["scored_positions"][0]
        stage = lambda key: f"{median(a[key])/scores:,.1f} → {median(b[key])/scores:,.1f}"
        left, right = (median(x["request_clocks"]) for x in (a,b))
        transport_rows.append(f"| {label} | {scores} | {a['axibytes'][0]:,} | {stage('transport_clocks')} | "
                              f"{stage('response_waits')} | {stage('ar_stalls')} | {stage('extra_clocks')} | "
                              f"{stage('hidden_clocks')} | {stage('projection_clocks')} | {(right-left)/50_000:+.3f} |")

    for case, label in [(None, "Mixed"), *LABELS.items()]:
        for mode in MODES:
            x = arm_totals(mode_arms(report, mode, case))
            energy_rows.append(f"| {label} | {DISPLAY[mode]} | {x['power']:.4f} | {x['idle']:.4f} | "
                               f"{x['j_answer']:.6f} | {x['j_token']:.8f} | {x['tpj']:.2f} |")
        series = report["energy_pairs_pct"] if case is None else report["homogeneous_energy_pairs_pct"][case]
        contrasts = [v["prefetch_vs_sequential"] for v in series.values()]
        alignments = ("midpoint", "midpoint_minus_50ms", "midpoint_plus_50ms", "read_end", "read_start")
        cols = [span([q["energy_per_answer_by_alignment"][a] for q in contrasts]) for a in alignments]
        sensitivity_rows.append(f"| {label} | " + " | ".join(cols) + " |")
    left, right = (arm_totals(mode_arms(report, mode)) for mode in MODES)
    mixed_change = relative(left["j_answer"], right["j_answer"])
    pairs = result["conditions"]["arms"]
    mapped_pairs = [(a["dma_base"], pairs[label.removesuffix("-sequential") + "-prefetch"]["dma_base"])
                    for label, a in pairs.items() if label.endswith("-sequential")]
    different_pages = sum(left != right for left, right in mapped_pairs)
    mappings = (f"DMA bases differed in {different_pages} of the {len(mapped_pairs)} paired blocks. "
                "The run record lists each allocation." if different_pages
                else "Both arms used the same DMA base within every paired block.")
    spi = [f"{label} logged +{a['spi']['active_ms_delta']:,} ms of SPI1 active time and "
           f"+{a['spi']['transfers_delta']:,} TPM transfers."
           for label,a in pairs.items() if a["spi"]["active_ms_delta"] or a["spi"]["transfers_delta"]]
    mixed_peripherals_steady = all(not (a["spi"]["active_ms_delta"] or a["spi"]["transfers_delta"])
                                   for a in report["arms"].values())
    peripheral = "SPI1 and TPM counters were steady in all mixed-block brackets. " if mixed_peripherals_steady else ""
    peripheral += (" ".join(spi) + " The timing relative to the active window is unresolved."
                   if spi else "All single-prompt brackets also had steady peripheral counters.")
    temps = result["conditions"]["temperature_brackets_c"]
    thermal = " ".join(f"{k} was {v['first']:.1f} °C at entry, {v['last']:.1f} °C at exit, and "
                       f"peaked at {v['maximum']:.1f} °C in the measured brackets." for k,v in temps.items())
    resources = result["conditions"]["resource_accounting"]["hierarchy"]
    a, b = (resources["fpga"][mode] for mode in ("control", "candidate"))
    tiles = lambda x: x["ramb36"] + x["ramb18"] / 2
    gains = [f"| {title} | {a[key]:,} | {b[key]:,} | {b[key]-a[key]:+,} |"
             for key,title in (("lut","LUTs"),("register","Registers"),("dsp","DSPs"))]
    gains.append(f"| Block RAM tiles | {tiles(a):g} | {tiles(b):g} | {tiles(b)-tiles(a):+g} |")
    reader = resources.get("reader")
    if reader is not None:
        left_reader, right_reader = (reader[mode] for mode in ("control", "candidate"))
        gains.append(f"| Reader LUTRAM | {left_reader['lutram']:,} | {right_reader['lutram']:,} | "
                     f"{right_reader['lutram'] - left_reader['lutram']:+,} |")
    arm_checks = (median(x["counter_check_ns"] for x in mode_arms(report, mode))/1e6 for mode in MODES)
    check_a, check_b = arm_checks
    scope_disagreement = []
    for case, label in [(None, "Mixed"), *LABELS.items()]:
        series = report["energy_pairs_pct"] if case is None else report["homogeneous_energy_pairs_pct"][case]
        vals = [v["prefetch_vs_sequential"]["energy_per_answer_j"] for v in series.values()]
        if min(vals) < 0 < max(vals):
            scope_disagreement.append(label)
    disagreement = (" The midpoint pairs varied in sign for " + ", ".join(scope_disagreement) + "."
                    if scope_disagreement else "")
    completion_summary = (f"Median completion took {abs(max(completion_changes)):.2f}–"
                          f"{abs(min(completion_changes)):.2f}% less time across the three prompts."
                          if max(completion_changes) < 0 else
                          f"Median completion changed {span(completion_changes)} across the three prompts.")
    return f"""# Overlapping final-score weight reads with scoring

The sequential and prefetch circuits returned exact outputs in all 200 timed replies on one KV260 at 50 MHz. {completion_summary} The prefetch circuit used {tiles(b):g} block RAM tiles, compared with {tiles(a):g} for the sequential DDR4 circuit and 39 for the historical on-chip circuit. Pooled mixed-block gross module energy per verified answer changed {mixed_change:+.2f}%. [Routed build](../{build_id}/findings.md) · [Exact RTL replay](../{rtl_id}/findings.md)

## Request timing

Each arm supplied eight mixed-block observations per prompt. Timing begins at board CPU admission. Decode rate counts useful byte intervals from the first useful byte to the last. Completion ends before verification.

| Prompt | First useful byte, ms | Decode, tokens/s | Completion, ms | Paired completion change |
| --- | ---: | ---: | ---: | ---: |
{chr(10).join(timing_rows)}

## Memory service and overlap

Both arms issued 320 read addresses and received 2,560 beats carrying 20,480 matrix bytes per scored position. The FPGA counter reports exposed wait. Subtracting exposed wait from measured address, beat and stall cycles gives inferred overlap. The projection-busy counter equals 1,680 clocks of arithmetic and control per scored position plus exposed wait. The change in request clocks matched the change in projection-busy clocks on every paired reply. Bus-service clocks sum accepted addresses, accepted beats, address stalls and response waits. Launch and capture cancel in this counter identity. Service varied slightly between the two arms and also contributed to the measured savings. In RTL replay, direct event traces counted 1,599 overlapping clocks per scored position, including 663 clocks with an accepted AXI address or response. The physical run derives overlap from request counters.

| Prompt | Scored positions | HP0 bytes per reply | Service clocks per position | R wait per position | AR stall per position | Exposed clocks per position | Inferred hidden clocks per position | Projection clocks per position | Completion change in FPGA time, ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(transport_rows)}

Accepted HP0 bytes divided by projection busy time gave {", ".join(rates)}. This phase-specific rate includes scoring time. {mappings}

## Gross VCC_SOM energy

Energy is the gross trace integral across the active block, including inter-reply verification and matched DDR counter reads. Active watts divide joules by block duration. Mixed-block active power averaged {left['power']:.4f} W sequential and {right['power']:.4f} W prefetch. Idle watts average the settled brackets at equal context. Median in-block post-verification counter-check totals were {check_a:.3f} ms sequential and {check_b:.3f} ms prefetch in mixed blocks.

| Scope | Mode | Active W | Idle W | Gross J/answer | Gross J/token | Tokens/J |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(energy_rows)}

Each column gives the minimum and maximum paired J/answer change across the matching blocks. Mixed has four pairs and each single prompt has two.{disagreement}

| Scope | Midpoint | Midpoint −50 ms | Midpoint +50 ms | Read end | Read start |
| --- | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(sensitivity_rows)}

{peripheral} {thermal}

## Routing and restoration

| Resource | Sequential | Prefetch | Change |
| --- | ---: | ---: | ---: |
{chr(10).join(gains)}

The nine smoke replies and 36 warm-ups passed. The board ran ABBA across three image loads. The temporary DMA mapping was released before each switch. The original image, HP0/FPD/SMMU words, weights and all 320 original BOS scores passed restoration. Completion time in the record is the first observed complete supervisor receipt.

[Run record](run.json) · [Protocol](../../experiments/{EXPERIMENT}.md)
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("repo", "packet", "historic", "build", "rtl", "protocol", "patch", "output"):
        parser.add_argument(name, type=Path)
    parser.add_argument("revision")
    parser.add_argument("--completed", type=Path, required=True, help="Authenticated completed board receipt.")
    parser.add_argument("--recovery-state", type=Path, required=True, help="Fresh board state and HP0 verification.")
    parser.add_argument("--energy-dir", type=Path, help="Directory with the exact two energy helper scripts.")
    args = parser.parse_args()
    need(datetime.fromisoformat(load(args.completed)["utc"]).tzinfo is not None, "Completion time needs timezone")
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
    files.update(completed=args.completed, recovery_state=args.recovery_state,
                 entry_hp0=evidence / "hp0-baseline.json", restored_hp0=evidence / "hp0-exit.stdout",
                 supervisor=args.packet / "supervisor.txt", dispatch=args.packet / "dispatch.json")
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
