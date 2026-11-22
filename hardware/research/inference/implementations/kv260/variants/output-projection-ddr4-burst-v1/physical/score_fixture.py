"""Audit Experiment 15 receipts and score matched timing and VCC_SOM blocks."""

import argparse
from collections import defaultdict
from itertools import combinations
import importlib.util
import json
from pathlib import Path
from statistics import median

from measurement import (
    CONTROL_CLOCKS, HOMOGENEOUS_ORDERS, HOMOGENEOUS_REPLIES, MIXED_ORDERS,
    TRANSFER_COUNTS, verify_counters,
)


MODES = tuple(TRANSFER_COUNTS)
MAGIC = 0x44445232
CONTRASTS = tuple(combinations(MODES, 2))
ORDER = tuple((round_id, mode) for round_id, modes in enumerate(MIXED_ORDERS, 1) for mode in modes)
HOMOGENEOUS_ORDER = tuple((round_id, prompt, mode)
                          for round_id, prompt, modes in HOMOGENEOUS_ORDERS for mode in modes)
IDENTITY_KEYS = ("prefix_ids", "output_ids", "stop_reason", "context_count", "scores_consumed",
                 "skipped_positions")
MATRIX = "a470ed9570d1ebf01a5431fda805d02e0e11b88dcb0e06785e324bdd37c57e89"


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
    need(start < output_times[0] < output_times[-1] <= done <= row["verified_ns"]
         and all(a < b for a, b in zip(output_times, output_times[1:])),
         f"{case}: invalid request chronology")
    counters = row["ddr_counters"]
    need(counters["magic"] == MAGIC and counters["mode"] == mode
         and not any(counters[key] for key in ("fault", "transport_busy", "counter_saturated")),
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
        "axibytes": counters["beats"] * 8,
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
    mapping = setup["matrix_upload"]
    base = int(mapping["dma_base"], 16)
    need(mapping["matrix_sha256"] == MATRIX and mapping["dma_bytes"] == 2048
         and mapping["dma_base"] == mapping["hardware_base"]
         and 0 < base <= 0x7ffff800 and base % 64 == 0
         and setup["matrix_setup_ns"] > 0, "Unverified matrix upload or DMA aperture")
    selected = setup["selected_status"]
    need(selected["magic"] == MAGIC and selected["mode"] == mode and selected["dma_base"] == mapping["dma_base"]
         and selected["hardware_base"] == mapping["dma_base"], "Selected mode or DMA mapping differs")
    spi_raw = load(path / "spi-boundary.json")
    need(spi_raw == arm["spi"], "SPI receipt differs from arm manifest")
    end_state = load(path / "quiesced.json")
    need(end_state["magic"] == MAGIC and end_state["mode"] == "bram" and end_state["safe_release"]
         and not end_state["transport_busy"] and end_state["dma_bytes"] == 0
         and int(end_state["hardware_base"], 16) == 0, "DMA teardown did not verify")
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
        "matrix_setup_ns": setup["matrix_setup_ns"],
        "dma_base": mapping["dma_base"],
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
              "request_clocks", "axibytes", "useful_bytes", "reads", "beats", "faults", "extra_clocks",
              "ar_stalls", "response_waits", "projections", "projection_clocks")
    pooled = {mode: defaultdict(lambda: defaultdict(list)) for mode in MODES}
    timing_pairs, energy_pairs = {}, {}
    for round_id in range(1, len(MIXED_ORDERS) + 1):
        matched = {mode: arms[f"p{round_id}-{mode}"] for mode in MODES}
        energy_pairs[str(round_id)] = matched_energy(matched)
        grouped = {mode: defaultdict(lambda: defaultdict(list)) for mode in MODES}
        for mode, arm in matched.items():
            for row in arm["requests"]:
                for field in fields:
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
            for case in CONTROL_CLOCKS
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
    analysis = energy_dir or historic
    energy = module_at("energy", analysis / "energy_analysis.py")
    spi = module_at("spi", analysis / "energy_validation.py")
    reference = rows_by_case(load(historic / "p1-candidate" / "warmup.json")["requests"])
    smokes = {}
    for mode in MODES:
        arm_path = packet / f"smoke-{mode}"
        block = load(arm_path / "smoke.json")
        smokes[mode] = audit_block(block, list(CONTROL_CLOCKS), reference, mode)
    arms = {
        f"p{round_id}-{mode}": audit_arm(packet / f"p{round_id}-{mode}",
                                       historical_order(historic, round_id, "warmup.json"),
                                       historical_order(historic, round_id, "block.json"),
                                       reference, mode, energy, spi)
        for round_id, mode in ORDER
    }
    chronological(arms, "mixed blocks")
    homogeneous_arms = {}
    for series, case, mode in HOMOGENEOUS_ORDER:
        label = f"homogeneous-p{series}-{case}-{mode}"
        homogeneous_arms[label] = audit_arm(packet / label, [case],
                                            [case] * HOMOGENEOUS_REPLIES[case],
                                            reference, mode, energy, spi)
    chronological({**arms, **homogeneous_arms}, "all timed blocks")
    energy_pairs = {
        case: {
            str(series): matched_energy({
                mode: homogeneous_arms[f"homogeneous-p{series}-{case}-{mode}"] for mode in MODES
            })
            for series in (1, 2)
        }
        for case in HOMOGENEOUS_REPLIES
    }
    return {"smokes": smokes, "arms": arms, **summarize(arms),
            "homogeneous_arms": homogeneous_arms, "homogeneous_energy_pairs_pct": energy_pairs}


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
