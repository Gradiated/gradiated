"""Audit Experiment 17 receipts and score matched timing and VCC_SOM blocks."""

import argparse
from collections import defaultdict
import importlib.util
import json
from pathlib import Path
from statistics import median

from measurement import (
    ON_CHIP_CLOCKS, HOMOGENEOUS_REPLIES, MODES, SESSIONS, scored_positions, transport_clocks, verify_counters,
)


MAGIC = 0x44445233
CONTRASTS = (("sequential", "prefetch"),)
ORDER = tuple((round_id, mode) for _, mode, rounds, _, _, _ in SESSIONS for round_id in rounds)
HOMOGENEOUS_ORDER = tuple((series, prompt, mode) for _, mode, _, series, prompts, _ in SESSIONS
                          for prompt in prompts)
IDENTITY_KEYS = ("prefix_ids", "output_ids", "stop_reason", "context_count", "scores_consumed",
                 "skipped_positions")
MATRIX = "7a77c0b9cd6f66e1f68d6905c5f2962bf58d92543fbb5e5dbb18980ee9f4a787"


def load(path):
    return json.loads(path.read_bytes())


def need(condition, message):
    if not condition:
        raise ValueError(message)


def module_at(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def rows_by_case(rows):
    return {row["case"]: row["observed"]["header"] for row in rows}


def audit_request(row, reference, mode):
    case = row["case"]
    header = row["observed"]["header"]
    need(not row["observed"]["frames"], f"{case}: unexpected compact receipt frames")
    for key in IDENTITY_KEYS:
        need(header[key] == reference[key], f"{case}: reference mismatch in {key}")
    output_times = header["output_ns"]
    need(len(output_times) == len(header["output_ids"]) >= 2,
         f"{case}: broken timing/output correspondence")
    start = header["admitted_ns"]
    done = header["done_ns"]
    need(0 < done - start <= 5_000_000_000, "Request missed the shared five-second limit")
    need(start < output_times[0] < output_times[-1] <= done <= row["verified_ns"]
         and all(a < b for a, b in zip(output_times, output_times[1:])),
         f"{case}: invalid request chronology")
    counters = row["ddr_counters"]
    need(counters["magic"] == MAGIC and counters["mode"] == "ddr"
         and not any(counters[key] for key in ("fault", "transport_busy", "counter_saturated", "safe_release")),
         f"{case}: invalid fixture state at completion")
    verify_counters(case, header, counters, mode)
    cycles = header["request_cycles"]
    need(0 < cycles["first"] <= cycles["last"] <= cycles["done"],
         f"{case}: missing or invalid FPGA event timestamps")
    need(row["verified_ns"] <= row["ddr_counters_checked_ns"], "Counter check preceded verification")
    return {
        "input_tokens": len(header["prefix_ids"]),
        "output_tokens": len(output_times),
        "context_count": header["context_count"],
        "stop_reason": header["stop_reason"],
        "ttft_ms": (output_times[0] - start) / 1e6,
        "decode_tps": (len(output_times) - 1) * 1e9 / (output_times[-1] - output_times[0]),
        "decode_intervals": len(output_times) - 1,
        "decode_ns": output_times[-1] - output_times[0],
        "completion_ms": (done - start) / 1e6,
        "verified_ms": (row["verified_ns"] - start) / 1e6,
        "first_clocks": cycles["first"],
        "last_clocks": cycles["last"],
        "request_clocks": cycles["done"],
        "scored_positions": scored_positions(header),
        "post_verify_check_ns": row["ddr_counters_checked_ns"] - row["verified_ns"],
        "axibytes": counters["beats"] * 8,
        "hp0_projection_mb_s": counters["beats"] * 8 * 50 / counters["projection_clocks"],
        "transport_clocks": transport_clocks(counters),
        "hidden_clocks": transport_clocks(counters) - counters["extra_clocks"],
        **{key: counters[key] for key in
           ("useful_bytes", "reads", "beats", "faults", "extra_clocks", "ar_stalls",
            "response_waits", "projections", "projection_clocks")},
    }


def audit_block(block, expected, reference, mode):
    rows = block["requests"]
    need([row["case"] for row in rows] == expected, "Unexpected prompt order")
    need(block["begin_ns"] == rows[0]["observed"]["header"]["admitted_ns"]
         and block["end_ns"] == rows[-1]["verified_ns"],
         "Invalid block boundary")
    for left, right in zip(rows, rows[1:]):
        need(left["ddr_counters_checked_ns"] <= right["observed"]["header"]["admitted_ns"],
             "Counter readback overlaps following request")
    return [{"case": row["case"], **audit_request(row, reference[row["case"]], mode)} for row in rows]


def audit_arm(path, warm_order, block_order, reference, mode, energy, spi):
    warm = load(path / "warmup.json")
    block = load(path / "block.json")
    arm = load(path / "arm.json")
    duration_ns = block["end_ns"] - block["begin_ns"]
    warm_data = audit_block(warm, warm_order, reference, mode)
    data = audit_block(block, block_order, reference, mode)
    need(warm["end_ns"] <= block["begin_ns"]
         and arm["phases"]["active"] == [block["begin_ns"], block["end_ns"]], "Bad active window")
    need(arm["idle_context"] == warm_data[-1]["context_count"] == data[-1]["context_count"],
         "Pre- and post-block idle contexts differ")
    need(load(path / "sampler-process.json")["exit"] == 0 and not (path / "sampler.stderr").stat().st_size,
         "Sampler process reported failure")
    version, raw = (path / "sampler.stdout").read_bytes().split(b"\n", 1)
    need(version == b"READY", "Sampler was never ready")
    trace = json.loads(raw)
    rows = energy.check_power(trace, arm["schedule_start_ns"], arm["before"], arm["after"])
    count = sum(r["output_tokens"] for r in data)
    rail = energy.rail(rows, arm["phases"], len(data), count)
    need(rail["admitted"], f"Power trace rejected: {rail.get('reason')}")
    midpoint = rail["alignment_scenarios"]["midpoint"]
    setup = load(path / "load.json")
    load_data = {"model_setup_ns": setup["timing"]["ready_ns"] - setup["timing"]["setup_begin_ns"]}
    need(load_data["model_setup_ns"] > 0, "Unverified model setup")
    spi_raw = load(path / "spi-boundary.json")
    need(spi_raw == arm["spi"], "SPI receipt differs from arm manifest")
    mapping = setup["matrix_upload"]
    base = int(mapping["dma_base"], 16)
    need(mapping["matrix_sha256"] == MATRIX and mapping["dma_bytes"] == 20480
         and mapping["dma_base"] == mapping["hardware_base"]
         and 0 < base <= 0x7fffb000 and base % 64 == 0
         and setup["matrix_setup_ns"] > 0, "Unverified matrix upload or DMA aperture")
    selected = setup["selected_status"]
    need(selected["magic"] == MAGIC and selected["mode"] == "ddr"
         and selected["dma_base"] == mapping["dma_base"]
         and selected["hardware_base"] == mapping["dma_base"] and not selected["safe_release"],
         "Selected mode or DMA mapping differs")
    end_state = load(path / "quiesced.json")
    need(end_state["magic"] == MAGIC and end_state["mode"] == "bram" and end_state["safe_release"]
         and not end_state["transport_busy"] and end_state["dma_bytes"] == 0
         and int(end_state["hardware_base"], 16) == 0, "DMA teardown did not verify")
    for row in (*warm["requests"], *block["requests"]):
        observed = row["ddr_counters"]
        need(observed["dma_base"] == observed["hardware_base"] == mapping["dma_base"]
             and observed["dma_bytes"] == 20480, "DMA mapping changed during scored work")
    load_data.update(matrix_setup_ns=setup["matrix_setup_ns"], dma_base=mapping["dma_base"])
    return {
        "warmups": warm_data, "requests": data, "length_ns": duration_ns,
        "start_ns": block["begin_ns"], "end_ns": block["end_ns"],
        "output_tokens": count, "idle_context": arm["idle_context"],
        "active_power_w": midpoint["gross_j"] * 1e9 / duration_ns,
        "idle_power_w": midpoint["idle_w"],
        "energy_per_answer_j": midpoint["gross_j_per_completion"],
        "energy_per_token_j": midpoint["gross_j_per_output_byte"],
        "tokens_per_joule": count / midpoint["gross_j"],
        "gross_j": midpoint["gross_j"],
        "spi": spi.check_spi_window(spi_raw, block["begin_ns"], block["end_ns"]),
        "power_trace": {"samples": len(rows), "missed_slots": len(trace["missed"])},
        "rail": rail,
        "counter_check_ns": sum(r["post_verify_check_ns"] for r in data[:-1]),
        **load_data,
    }


def relative(a, b):
    return 100 * (b / a - 1) if a else None


def matched_energy(arms):
    counts = {(arm["output_tokens"], arm["idle_context"]) for arm in arms.values()}
    need(len(counts) == 1, "Compared arms completed unequal work or ready-idle cache state")
    result = {}
    for control, candidate in CONTRASTS:
        baseline, tested = arms[control], arms[candidate]
        left = baseline["rail"]["alignment_scenarios"]
        right = tested["rail"]["alignment_scenarios"]
        result[f"{candidate}_vs_{control}"] = {
            **{key: relative(baseline[key], tested[key]) for key in
               ("active_power_w", "energy_per_answer_j", "energy_per_token_j", "tokens_per_joule")},
            "energy_per_answer_by_alignment": {
                k: relative(left[k]["gross_j_per_completion"], right[k]["gross_j_per_completion"])
                for k in left
            },
        }
    return result


def summarize(arms):
    fields = ("ttft_ms", "decode_tps", "completion_ms", "verified_ms", "first_clocks", "last_clocks",
              "request_clocks", "axibytes", "hp0_projection_mb_s", "useful_bytes", "reads", "beats", "faults", "extra_clocks",
              "ar_stalls", "response_waits", "projections", "projection_clocks", "scored_positions",
              "hidden_clocks", "transport_clocks",
              "post_verify_check_ns")
    pooled = {mode: defaultdict(lambda: defaultdict(list)) for mode in MODES}
    timing_pairs, energy_pairs = {}, {}
    for round_id in range(1, 5):
        matched = {mode: arms[f"p{round_id}-{mode}"] for mode in MODES}
        energy_pairs[str(round_id)] = matched_energy(matched)
        grouped = {mode: defaultdict(lambda: defaultdict(list)) for mode in MODES}
        for mode, arm in matched.items():
            for row in arm["requests"]:
                for field in fields:
                    if field in row:
                        grouped[mode][row["case"]][field].append(row[field])
                        pooled[mode][row["case"]][field].append(row[field])
        timing_pairs[str(round_id)] = {
            case: {
                f"{b}_vs_{a}": {
                    field: relative(median(grouped[a][case][field]), median(grouped[b][case][field]))
                    for field in ("ttft_ms", "decode_tps", "completion_ms", "request_clocks")
                }
                for a, b in CONTRASTS
            }
            for case in ON_CHIP_CLOCKS
        }
    return {"timing": pooled, "timing_pairs_pct": timing_pairs, "energy_pairs_pct": energy_pairs}


def historical_order(historic, round_id, file):
    pair = (round_id - 1) % 3 + 1
    rows = load(historic / f"p{pair}-candidate" / file)["requests"]
    return [row["case"] for row in rows]


def chronological(arms, description):
    sequence = list(arms.values())
    need(all(a["end_ns"] < b["start_ns"] for a, b in zip(sequence, sequence[1:])),
         f"Board chronology did not follow the frozen order for {description}")


def score(packet, historic, energy_dir=None):
    watchdog = load(packet / "watchdog.json")
    need(watchdog["request_timeout_ns"] == 5_000_000_000, "Board watchdog differs")
    analysis = energy_dir or historic
    energy = module_at("energy", analysis / "energy_analysis.py")
    spi = module_at("spi", analysis / "energy_validation.py")
    reference = rows_by_case(load(historic / "p1-candidate" / "warmup.json")["requests"])
    smokes, arms, homogeneous_arms, observed_order = {}, {}, {}, {}
    for session, mode, rounds, series, prompts, smoke in SESSIONS:
        if smoke:
            label = f"smoke-{session}-{mode}"
            block = load(packet / label / "smoke.json")
            smokes[label] = audit_block(block, list(ON_CHIP_CLOCKS), reference, mode)
            observed_order[label] = {"start_ns": block["begin_ns"], "end_ns": block["end_ns"]}
            need(all(0 < row["completion_ms"] <= 5000 / 3 for row in smokes[label]),
                 "Smoke reply exceeds the frozen margin")
        for round_id in rounds:
            label = f"p{round_id}-{mode}"
            arms[label] = audit_arm(packet / label, historical_order(historic, round_id, "warmup.json"),
                                    historical_order(historic, round_id, "block.json"),
                                    reference, mode, energy, spi)
            observed_order[label] = arms[label]
        for case in prompts:
            label = f"homogeneous-p{series}-{case}-{mode}"
            homogeneous_arms[label] = audit_arm(packet / label, [case],
                                                [case] * HOMOGENEOUS_REPLIES[case],
                                                reference, mode, energy, spi)
            observed_order[label] = homogeneous_arms[label]
    chronological(observed_order, "the ABBA session sequence")
    energy_pairs = {
        case: {
            str(series): matched_energy({
                mode: homogeneous_arms[f"homogeneous-p{series}-{case}-{mode}"] for mode in MODES
            })
            for series in (1, 2)
        }
        for case in HOMOGENEOUS_REPLIES
    }
    validate_matched_requests(arms, homogeneous_arms)
    return {"smokes": smokes, "arms": arms, **summarize(arms),
            "homogeneous_arms": homogeneous_arms, "homogeneous_energy_pairs_pct": energy_pairs}


def validate_matched_requests(arms, homogeneous_arms):
    blocks = {**arms, **homogeneous_arms}
    for label, control in blocks.items():
        if not label.endswith("-sequential"):
            continue
        candidate = blocks[label.removesuffix("-sequential") + "-prefetch"]
        for left, right in zip(control["requests"], candidate["requests"], strict=True):
            invariant = ("case", "scored_positions", "reads", "beats", "useful_bytes", "output_tokens")
            need(all(left[key] == right[key] for key in invariant), "Matched traffic or outputs differ")
            request_delta = right["request_clocks"] - left["request_clocks"]
            stage_delta = right["projection_clocks"] - left["projection_clocks"]
            service_delta = right["transport_clocks"] - left["transport_clocks"]
            hidden_delta = right["hidden_clocks"] - left["hidden_clocks"]
            need(request_delta == stage_delta == service_delta - hidden_delta,
                 "Matched complete-request clocks are inconsistent with exposed reader service")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet", type=Path)
    parser.add_argument("historic", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--energy-dir", type=Path,
                        help="Exact offline helpers used in the run, if revised from Experiment 13.")
    args = parser.parse_args()
    report = score(args.packet, args.historic, args.energy_dir)
    with args.out.open("x") as file:
        json.dump(report, file, indent=2, sort_keys=True)
        file.write("\n")
