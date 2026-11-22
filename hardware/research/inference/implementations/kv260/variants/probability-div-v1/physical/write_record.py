"""Write the Experiment 18 physical run record from the verified Mac capture."""

import argparse
from collections import defaultdict
from datetime import datetime
import hashlib
import json
from pathlib import Path
import tarfile
from statistics import mean, median

from measurement import CASES, HOMOGENEOUS_REPLIES, MODES, SESSIONS, mixed_order
from score_fixture import HOMOGENEOUS_ORDER, ORDER
from score_fixture import load, module_at, need, relative, score


from prepare_packet import CANDIDATE, CONTROL as CONTROL_FIRMWARE, CONTROL_BUILD, CONTROL_RUN, REFERENCE_FILE, RESTORATION

EXPERIMENT = "kv260-probability-div-v1"
LABELS = {
    "encoded-hello": "Hello", "encoded-fu2p2q": "Six-byte prompt", "encoded-max48": "48-byte prompt",
}
DISPLAY = {"control": "Experiment 13", "candidate": "Probability divider"}
REQUEST_METRICS = {
    "ttft_ms": ("ms", "Board CPU admission before encoding and context clear to first useful byte.", "ttft"),
    "decode_tps": ("tokens/s", "Useful byte intervals divided by board CPU first-to-last elapsed time.", "decode_tps"),
    "completion_ms": ("ms", "Board CPU admission to observed stop and drain before verification.", "completion_time"),
    "verified_ms": ("ms", "Board CPU admission to exact output verification.", "completion_time"),
    "verification_ns": ("ns", "CPU interval between observed completion and exact verification.", "completion_time"),
    "first_clocks": ("cycles", "FPGA clock count at first useful byte.", "stage_cycles"),
    "last_clocks": ("cycles", "FPGA clock count at last useful byte.", "stage_cycles"),
    "request_clocks": ("cycles", "FPGA clock count at final completion.", "stage_cycles"),
    "scored_positions": ("positions", "Accepted scores divided by 320.", "output_counts"),
    "skipped_positions": ("positions", "FPGA count of prefill positions without scores.", "output_counts"),
}
BLOCK_METRICS = {
    "active_power_w": ("W", "Sample-midpoint gross VCC_SOM integral divided by block time.", "active_power"),
    "idle_power_w": ("W", "Two equal-duration settled VCC_SOM idle brackets at matched context.", "idle_power"),
    "energy_per_answer_j": ("J/answer", "Sample-midpoint gross VCC_SOM integral divided by verified block replies.", "energy_per_answer"),
    "energy_per_token_j": ("J/token", "Sample-midpoint gross VCC_SOM integral divided by useful block output bytes.", "energy_per_answer"),
    "tokens_per_joule": ("tokens/J", "Useful block output bytes divided by sample-midpoint gross VCC_SOM integral.", "tokens_per_joule"),
    "gross_j": ("J", "Sample-midpoint trapezoidal VCC_SOM integral over the verified active block.", "energy_per_answer"),
    "model_setup_ns": ("ns", "Native setup begin through weights loaded and ready, outside the block.", "startup"),
}
OBSERVED = {"first_clocks", "last_clocks", "request_clocks", "skipped_positions"}


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
    coverage = {}

    def add(prefix, field, values, definitions):
        unit, method, family = definitions[field]
        kind = "observed" if field in OBSERVED else "derived"
        name = f"{prefix}.{field}"
        result.append(dict(name=name, unit=unit, method=method, kind=kind, samples=values))
        state = "measured" if kind == "observed" else "derived"
        coverage.setdefault(family, {"state": state, "metrics": []})["metrics"].append(name)

    for mode in MODES:
        for case, values in report["timing"][mode].items():
            for field, samples in values.items():
                add(f"{mode}.{case}", field, samples, REQUEST_METRICS)
        for case in (None, *CASES):
            prefix = f"{mode}.mixed" if case is None else f"{mode}.homogeneous.{case}"
            arms = mode_arms(report, mode, case)
            for field in BLOCK_METRICS:
                samples = [value for arm in arms for value in
                           (arm[field] if field == "idle_power_w" else [arm[field]])]
                add(prefix, field, samples, BLOCK_METRICS)
    return result, coverage


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


def stock_state(data, boot):
    return (data["boot"] == boot and data["firmware"] == "gradiated-tiny-50mhz.bit.bin" and
            data["overlays"] == ["gradiated-tiny-clock", "gradiated-tiny-interface", "gradiated-tiny-program"] and
            data["taint"] == "12288" and not any((data["module"], data["dma"])))


def record(args, project, report, refs):
    prior = load(project / "results" / CONTROL_RUN / "run.json")
    record_tools = module_at("records", project / "tools/records.py")
    evidence = args.packet / "evidence"
    invocation = load(args.packet / "invocation.json")
    intent = load(evidence / "intent.json")
    allowed = intent["configuration"]
    policy = allowed["qualification"]
    need(allowed["pins"] == invocation["sources"] and policy == invocation["qualification"] and
         policy["build_acceptance_sha256"] == refs["build_acceptance"]["sha256"] and
         policy["protocol_sha256"] == refs["protocol"]["sha256"] and
         policy["replay_sha256"] == refs["rtl_boundaries"]["sha256"], "Board intent or qualification pin differs")
    status = load(args.packet / "completed.json")
    outcome = load(evidence / "outcome.json")
    need(status["outcome"] == outcome and not status["running"] and
         load(args.packet / "supervisor-pid.json")["pid"] == status["pid"], "Live completion evidence differs")
    initial, final = (load(evidence / f"{name}.state.json") for name in ("admission", "restored"))
    boot = invocation["boot"]
    need(initial["boot_id"] == final["boot_id"] == allowed["boot"] == boot, "Unexpected boot transition")
    need(stock_state(load(args.packet / "preparation/board-restored.json"), boot), "Fresh UART stock check differs")
    need(all(initial[key] == final[key] for key in
             ("firmware_name", "taint", "overlays", "uio", "bindings", "kernel", "model", "manager", "dfx")),
         "Restored firmware or state differs")
    before, after = (load(evidence / f"original-{edge}.stdout") for edge in ("before", "after"))
    need(len(before["logits"]) == 320 and before["logits"] == after["logits"] and
         all(item["accepted"] and not item["mismatch_indices"] for item in (before, after)),
         "Original BOS scores differ or fail reference checks")
    log = (args.packet / "supervisor.txt").read_text().splitlines()
    labels = set(report["arms"]) | set(report["homogeneous_arms"]) | set(report["smokes"])
    need(labels == {line.removesuffix(" passed") for line in log if line.endswith(" passed")},
         "Supervisor log does not confirm the full arm set")
    need(outcome == {"experiment_passed": True, "restored": True}, "Board outcome did not pass")
    firmware = {mode: allowed["pins"][name]["sha256"] for mode, name in
                zip(MODES, (CONTROL_FIRMWARE, CANDIDATE), strict=True)}
    build = load(args.build / "run.json")
    control = load(project / "results" / CONTROL_BUILD / "run.json")
    need(firmware["candidate"] == build["implementation"]["sha256"] and
         firmware["control"] == control["implementation"]["sha256"], "Admitted routed firmware pins differ")
    routed = {
        mode: {"resources": source["conditions"]["resources"], "timing": source["conditions"]["timing"]}
        for mode, source in zip(MODES, (control, build), strict=True)
    }
    metrics, coverage = measurements(report)
    all_arms = {**report["arms"], **report["homogeneous_arms"]}
    thermal, thermal_by_arm = temperatures(evidence, all_arms)
    coverage.update({
        "correctness": {"state": "measured", "sources": [refs["score"], refs["rtl_boundaries"]]},
        "output_counts": {**coverage["output_counts"], "state": "measured", "sources": [refs["score"]]},
        "repeatability": {"state": "measured", "sources": [refs["score"]]},
        "resources": {"state": "reused", "sources": [refs["build"], refs["control_build"]]},
        "implementation_timing": {"state": "reused", "sources": [refs["build"], refs["control_build"]]},
        "memory": {"state": "reused", "sources": [refs["memory"], refs["build"], refs["control_build"]],
                   "reason": "Unchanged logical allocations and recorded physical resource use on both circuits."},
        "cache_capacity": {"state": "reused", "sources": [refs["memory"]]},
        "operating_conditions": {"state": "measured", "sources": [refs["archive"]],
                                 "reason": "Linux-reported 50 MHz setting and sampled temperature brackets."},
        "recovery": {"state": "measured", "sources": [refs["outcome"], refs["after_bos"], refs["uart_restored"]]},
        "token_gaps": {"state": "measured", "sources": [refs["archive"]]},
        "idle_subtracted_energy": {"state": "derived", "sources": [refs["score"]]},
        "power_validation": {"state": "not_measured", "reason": "No external calibration or off-module meter."},
        "prefill": {"state": "not_measured", "reason": "Exact first/last/done timers with no independent prefill timer."},
        "sustained_throughput": {"state": "not_measured", "reason": "Short paired blocks at concurrency one."},
        "memory_bandwidth": {"state": "not_applicable", "reason": "Both fixtures retain the tested on-chip weights."},
    })
    end = datetime.fromisoformat(status["utc"])
    start = datetime.fromisoformat(load(args.packet / "dispatch.json")["utc"])
    config = dict(model=initial["model"], kernel=initial["kernel"], boot_id=boot,
                  physical_unit="KV260 USB bridge XFL1RXOM0IWQ",
                  configured_pl0_hz=50_000_000, comparison_firmware_sha256=firmware,
                  initial_taint=initial["taint"], restored_taint=final["taint"],
                  original_state_sha256=refs["entry"]["sha256"], restored_state_sha256=refs["restored"]["sha256"])
    conditions = {
        "measurement_standard": "inference-measurements-v2", "measurement_coverage": coverage,
        "control_run": CONTROL_RUN, "previous_board_run": RESTORATION, "routed": routed,
        "routed_attention_hierarchy": build["conditions"]["hierarchy"],
        "schedule": intent["sessions"], "mixed_rounds": intent["mixed_rounds"],
        "counts": report["counts"], "failures": 0, "timeouts": 0, "incomplete_requests": 0,
        "exact_fpga_cycle_boundaries": allowed["replay"],
        "mixed_timing_pairs_pct": report["timing_pairs_pct"], "mixed_energy_pairs_pct": report["energy_pairs_pct"],
        "homogeneous_energy_pairs_pct": report["homogeneous_energy_pairs_pct"],
        "temperature_brackets_c": thermal, "arm_temperature_brackets_c": thermal_by_arm, "original_restored": True,
        "arms": {name: {k: a[k] for k in ("output_tokens", "idle_context", "spi", "power_trace", "model_setup_ns")}
                 for name, a in all_arms.items()},
        "power_supply_boundary": "INA260 VCC_SOM module rail, 20 Hz. Linear trapezoidal interpolation and 75 ms maximum covered sample gap.",
        "development_effort": {"engineering_attention_minutes": None, "ai_usage_cost": None,
                               "dispatch_to_first_complete_receipt_seconds": (end - start).total_seconds()},
    }
    value = dict(
        schema_version=1, id=invocation["attempt"], experiment_id=EXPERIMENT,
        evidence_type="physical-measurement", status="passed",
        source=dict(commit=args.revision, patch_sha256=refs["patch"]["sha256"]),
        model=prior["model"], implementation={"id": EXPERIMENT, "sha256": firmware["candidate"]},
        workload={"id": "kv260-probability-div-abba-v1", "sha256": refs["workload"]["sha256"]},
        device=dict(id=prior["device"]["id"], configuration=config,
                    configuration_sha256=record_tools.configuration_digest(config)),
        protocol=dict(prior["protocol"], id=EXPERIMENT, sha256=refs["protocol"]["sha256"],
                      warmup="Three mixed or one homogeneous warm-up per powered block.",
                      quality_gate="Exact frozen outputs, stop reasons, counts and first/last/done FPGA clocks.",
                      measurement_boundary="Board CPU admission through useful output and completion. Gross VCC_SOM block integral includes inter-reply verification and gaps."),
        correctness=dict(passed=True, evidence="200 timed, 36 warm-up and nine smoke replies passed output, stopping and all three FPGA cycle checks. All 320 original BOS scores passed restoration."),
        quality=dict(passed=True, evidence="Frozen W16A16 arithmetic, model, outputs and stopping rules, plus qualified exact model replay."),
        conditions=conditions, started_at=start.isoformat(), completed_at=end.isoformat(),
        metrics=metrics, artifacts=list(refs.values()), supersedes=None,
        limitations=[
            "One board and boot, three fixed prompts, four mixed pairs and two homogeneous pairs per prompt.",
            "Only VCC_SOM is measured. Gross active energy includes inter-request verification and gaps.",
            "The board clock source is the Linux clock framework. Runtime frequency was not independently instrumented.",
            "The SPI1/TPM counters bracket each active window with finite delays. They cannot isolate peripheral power.",
            "The first complete live status receipt places an upper bound on board completion time.",
            "Taint 12288 reflects previously loaded and unloaded DDR fixture code in the inherited boot.",
        ],
    )
    record_tools.validate(value)
    return value


def span(values):
    return f"{min(values):+.2f}% to {max(values):+.2f}%"


def findings(value, report, build_id, rtl_id):
    header = [
        "# Shortening exact attention probability division",
        "",
    ]
    completion_delta = []
    timing_rows = []
    cycle_rows = []
    for case, label in LABELS.items():
        left, right = (report["timing"][mode][case] for mode in MODES)
        cells = []
        for key, precision in (("ttft_ms", 3), ("decode_tps", 1), ("completion_ms", 3)):
            a, b = median(left[key]), median(right[key])
            cells.append(f"{a:.{precision}f} → {b:.{precision}f} ({relative(a,b):+.2f}%)")
        completion_delta.append(relative(median(left["completion_ms"]), median(right["completion_ms"])))
        paired = [pair[case]["candidate_vs_control"]["completion_ms"] for pair in report["timing_pairs_pct"].values()]
        timing_rows.append(f"| {label} | {' | '.join(cells)} | {span(paired)} |")
        cycles = [f"{left[key][0]:,} → {right[key][0]:,}" for key in ("first_clocks", "last_clocks", "request_clocks")]
        delta = left["request_clocks"][0] - right["request_clocks"][0]
        row = mode_arms(report, "control", case)[0]["requests"][0]
        cycle_rows.append(f"| {label} | {row['input_tokens']} | {row['output_tokens']} | {row['context_count']} | "
                          f"{row['scored_positions']} | {' | '.join(cycles)} | {delta:,} |")
    energy_rows = []
    alignment_rows = []
    for case in (None, *CASES):
        scope = LABELS.get(case, "Mixed")
        for mode in MODES:
            totals = arm_totals(mode_arms(report, mode, case))
            energy_rows.append(f"| {scope} | {DISPLAY[mode]} | {totals['power']:.4f} | {totals['idle']:.4f} | "
                               f"{totals['j_answer']:.6f} | {totals['j_token']:.8f} | {totals['tpj']:.2f} |")
        pairs = report["energy_pairs_pct"] if case is None else report["homogeneous_energy_pairs_pct"][case]
        distributions = [p["candidate_vs_control"]["energy_per_answer_by_alignment"] for p in pairs.values()]
        cells = [span([p[k] for p in distributions]) for k in
                 ("midpoint", "midpoint_minus_50ms", "midpoint_plus_50ms", "read_end", "read_start")]
        alignment_rows.append(f"| {scope} | {' | '.join(cells)} |")
    mixed = [arm_totals(mode_arms(report, mode)) for mode in MODES]
    energy_pct = relative(*(stats["j_answer"] for stats in mixed))
    low, high = min(-d for d in completion_delta), max(-d for d in completion_delta)
    header.append(
        f"The exact shortened divider completed all 200 timed replies on one KV260 at 50 MHz. Median completion "
        f"took {low:.2f}–{high:.2f}% less time across the three fixed prompts. Pooled mixed-block gross VCC_SOM "
        f"joules per verified answer changed {energy_pct:+.2f}%. The routed blocks and both arms' replay pins are "
        f"available in the [routed build](../{build_id}/findings.md) and [exact RTL qualification](../{rtl_id}/findings.md)."
    )
    routed = value["conditions"]["routed"]
    resource_rows = []
    resource_columns = (("LUTs", "lut", 117120), ("Registers", "register", 234240), ("DSPs", "dsp", 1248),
                        ("Block RAM tiles", "bram_tile", 144))
    for label, key, capacity in resource_columns:
        a, b = (routed[mode]["resources"][key] for mode in MODES)
        resource_rows.append(f"| {label} | {a:,.0f} ({a/capacity:.2%}) | {b:,.0f} ({b/capacity:.2%}) | {b-a:+,.0f} |")
    for label, key in (("Setup slack, ns", "setup_slack_ns"), ("Hold slack, ns", "hold_slack_ns")):
        a, b = (float(routed[mode]["timing"][key]) for mode in MODES)
        resource_rows.append(f"| {label} | {a:.3f} | {b:.3f} | {b-a:+.3f} |")
    hierarchy = value["conditions"].get("routed_attention_hierarchy", {})
    hierarchy_rows = []
    for scope, label in (("att", "Attention"), ("scalar", "Primary scalar"), ("second_exp", "Second exponent")):
        if not hierarchy:
            break
        a, b = (hierarchy[mode][scope] for mode in MODES)
        hierarchy_rows.append(f"| {label} | {a['total_lut']:,} → {b['total_lut']:,} | "
                              f"{a['ff']:,} → {b['ff']:,} | {a['dsp']} → {b['dsp']} | "
                              f"{a['ramb36'] + a['ramb18']/2:g} → {b['ramb36'] + b['ramb18']/2:g} |")
    hierarchy_table = ["", "| Routed hierarchy | LUTs | Registers | DSPs | Block RAM tiles |",
                       "| --- | ---: | ---: | ---: | ---: |", *hierarchy_rows] if hierarchy_rows else []
    changed = [(name, row["spi"]) for name, row in value["conditions"]["arms"].items()
               if row["spi"]["active_ms_delta"] or row["spi"]["transfers_delta"]]
    spi = "SPI1 active time and TPM transfer counts were steady in all active-window brackets."
    if changed:
        observed = ", ".join(f"`{name}` +{data['active_ms_delta']} ms SPI1, +{data['transfers_delta']} TPM transfers"
                             for name, data in changed)
        spi = f"SPI1 or TPM counters changed in {observed}. The brackets cannot resolve activity inside the integration window."
    thermal = value["conditions"]["temperature_brackets_c"]
    temperatures = ", ".join(f"{key} {r['first']:.1f} → {r['last']:.1f} °C (peak {r['maximum']:.1f} °C)"
                             for key, r in sorted(thermal.items()))
    missed = sum(row["power_trace"]["missed_slots"] for row in value["conditions"]["arms"].values())
    lines = [
        *header, "", "## Request timing", "",
        "The board CPU starts timing before request encoding and context clear. Decode rate uses the intervals between useful bytes. Completion includes stopping and drain. Each arm contributed eight mixed-block observations per prompt. The range is the min/max of four round-paired median changes.",
        "", "| Prompt | First useful byte, ms | Decode, tokens/s | Completion, ms | Paired completion change |",
        "| --- | ---: | ---: | ---: | ---: |", *timing_rows, "", "## Exact work and FPGA clocks", "",
        "The three natural prompts reached EOS with the same output bytes in both arms. Every timed reply, warm-up and smoke independently checked against its own replay first, last and completion clocks.",
        "", "| Prompt | Encoded input tokens | Useful output tokens | Positions | Scored positions | First | Last | Done | Done clocks saved |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |", *cycle_rows,
        "", "Each occupied depth contributes two probability divisions and each division saves 24 clocks. At depth `d`, the cumulative saving is `24d(d+1)` clocks. The paired terminal counters reconciled exactly to that prediction. The RTL audit checked all 256 occupied depths and seven complete-request forecasts. [Pre-run cache-depth analysis](../../experiments/kv260-attention-context-cost-v1/findings.md)",
        "", "## Gross VCC_SOM energy", "",
        "The INA260 trace integrates the active block from first admission through final exact verification, including gaps between replies. Idle power averages equal settled brackets with the same loaded weights and context count. Gross ratios pool joules and their matching work totals.",
        "", "| Scope | Arm | Active W | Idle W | Gross J/answer | Gross J/token | Tokens/J |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |", *energy_rows,
        "", "Each alignment cell reports the range of paired gross J/answer changes. Mixed has four pairs, and each fixed-prompt block has two.",
        "", "| Scope | Midpoint | Midpoint −50 ms | Midpoint +50 ms | Read end | Read start |",
        "| --- | ---: | ---: | ---: | ---: | ---: |", *alignment_rows,
        "", f"The 20 Hz sampler skipped {missed} scheduled slots. Every integration used the same 75 ms limit on the gap between contributing samples. {spi}",
        "", f"Active-block temperature brackets showed {temperatures}." if temperatures else "",
        "", "## Routing and restoration", "",
        "| Routed resource | Experiment 13 | Probability divider | Change |",
        "| --- | ---: | ---: | ---: |", *resource_rows, *hierarchy_table,
        "", "Both images use on-chip weights and the same model upload of 117,124 bytes. The allocated KV cache is 32,768 bytes. Valid KV contents reached 12,928, 17,280 and 25,728 bytes respectively. [Logical storage accounting](../../implementations/kv260/resource-memory-baseline.md)",
        "", "The board ran ABBA across three comparison image loads. Nine smoke replies and 36 warm-ups passed. The original image, original weights and all 320 original BOS scores passed restoration on the same boot. Original UIO permissions, clock, firmware and overlay identities were verified.",
        "", f"[Run record](run.json) · [Protocol](../../experiments/{EXPERIMENT}.md)", "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("repo", "packet", "historic", "build", "rtl", "rtl-boundaries", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()
    project = args.repo / "hardware/research/inference"
    evidence = args.packet / "evidence"
    prepare = args.packet / "preparation"
    analysis = prepare / "packet"
    verify_recovered(args.packet)
    invocation = load(args.packet / "invocation.json")
    config = load(analysis / "config.json")
    need(config == load(evidence / "intent.json")["configuration"] and
         sha(analysis / "config.json") == invocation["config_sha256"], "Frozen packet config differs")
    for helper in ("energy_analysis.py", "energy_validation.py"):
        need(sha(analysis / helper) == config["pins"][helper]["sha256"], f"Analysis helper differs: {helper}")
    historic_reference = args.historic / REFERENCE_FILE
    need(sha(historic_reference) == config["qualification"]["control_reference_sha256"],
         "Historical independent compact output reference differs")
    report = score(evidence, args.historic, analysis, config)
    score_path = args.packet / "score.json"
    workload = args.packet / "scored-workload.json"
    write_json(score_path, report)
    write_json(workload, {
        "sessions": SESSIONS, "mixed_order": ORDER, "mixed_rounds": {index: mixed_order(index) for index in range(1, 5)},
        "homogeneous_order": HOMOGENEOUS_ORDER, "homogeneous_replies_per_block": HOMOGENEOUS_REPLIES,
        "historical_workload_sha256": sha(args.historic / "workload.json"), "model_reference": CONTROL_RUN,
    })
    build_id = args.build.name
    build_acceptance = args.repo / ".agents/runtime/hardware/inference/outputs" / build_id / "offline-acceptance.json"
    files = {
        "entry": evidence / "admission.state.json", "restored": evidence / "restored.state.json",
        "before_bos": evidence / "original-before.stdout", "after_bos": evidence / "original-after.stdout",
        "outcome": evidence / "outcome.json", "archive": args.packet / "board-evidence.tar.gz",
        "receipt": args.packet / "recovered.json", "invocation": args.packet / "invocation.json",
        "protocol": prepare / "protocol.md", "patch": prepare / "source.patch",
        "rtl": args.rtl, "rtl_boundaries": args.rtl_boundaries, "score": score_path, "workload": workload,
        "build": args.build / "run.json", "build_acceptance": build_acceptance,
        "control_build": project / "results" / CONTROL_BUILD / "run.json",
        "control_reference": historic_reference,
        "memory": project / "implementations/kv260/resource-memory-baseline.json",
        "completion": args.packet / "completed.json", "dispatch": args.packet / "dispatch.json",
        "uart_restored": prepare / "board-restored.json", "packet_qa": args.packet / "packet-qa.json",
        "supervisor": args.packet / "supervisor.txt",
    }
    refs = {key: pin(path, args.repo, key) for key, path in files.items()}
    value = record(args, project, report, refs)
    text = findings(value, report, build_id, args.rtl.parent.name)
    args.output.mkdir()
    write_json(args.output / "run.json", value)
    (args.output / "findings.md").write_text(text)


if __name__ == "__main__":
    main()
