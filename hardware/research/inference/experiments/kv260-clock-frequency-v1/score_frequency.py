"""Audit sealed Exp24 work and clock receipts and summarise physical observations."""

import argparse
from collections import defaultdict
from hashlib import sha256
from pathlib import Path
from statistics import mean, median

import clock_boundary as clock
from measurement import CASES, MODES, SESSIONS
from score_fixture import score as score_work


LABELS = dict(zip(CASES, ("Hello", "Six-byte prompt", "48-byte prompt"), strict=True))
ALIGNMENTS = ("midpoint", "midpoint_minus_50ms", "midpoint_plus_50ms", "read_start", "read_end")
HERE = Path(__file__).resolve().parent


def audit_inputs(config, packet):
    for name, expected in config["pins"].items():
        clock.require(Path(name).name == name, f"Unexpected fixture asset name: {name}")
        path = packet / name
        clock.require(path.is_file() and not path.is_symlink(), f"Missing checked fixture file: {name}")
        data = path.read_bytes()
        clock.require({"sha256": sha256(data).hexdigest(), "bytes": len(data)} == expected, f"Changed fixture file: {name}")
    reference = (packet / "reference/p1-candidate/warmup.json").read_bytes()
    clock.require({"sha256": sha256(reference).hexdigest(), "bytes": len(reference)} == config["reference_pin"],
                  "Frozen workload digest differs")


def pooled(blocks):
    joules = sum(row["gross_j"] for row in blocks)
    duration = sum(row["length_ns"] for row in blocks) / 1e9
    outputs = sum(row["output_tokens"] for row in blocks)
    replies = sum(len(row["requests"]) for row in blocks)
    return {"replies": replies, "useful_tokens": outputs, "active_w": joules / duration,
            "idle_w": mean(w for row in blocks for w in row["idle_power_w"]), "gross_j_answer": joules / replies,
            "gross_j_token": joules / outputs, "tokens_per_joule": outputs / joules}


def thermal_brackets(path, window):
    out = {}
    for edge in ("before", "after"):
        data = clock.read_json(path / f"temperatures-{edge}.json")
        clock.require(0 < data["begin_ns"] <= data["end_ns"] and
                      (data["end_ns"] <= window["start_ns"] if edge == "before" else data["begin_ns"] >= window["end_ns"]),
                      "Temperature observation overlaps the active request block")
        out[edge] = {r["label"]: r["value"] / 1000 for r in data["sensors"] if "value" in r}
    return out


def audit(evidence, packet, config):
    clock.validate_config(config)
    audit_inputs(config, packet)
    report = score_work(evidence, packet / "reference", packet, config)
    arm_clock, temperatures = {}, {}
    physical = {**report["arms"], **report["homogeneous_arms"]}
    chronological = []
    for session, mode, rounds, series, cases, smoke in SESSIONS:
        if smoke:
            label = f"smoke-{session}-{mode}"
            arm_clock[label] = clock.audit(evidence / label, config, mode, smoke=True)
            chronological.append(arm_clock[label])
        for label in [*(f"p{i}-{mode}" for i in rounds), *(f"homogeneous-p{series}-{case}-{mode}" for case in cases)]:
            arm_clock[label] = clock.audit(evidence / label, config, mode)
            temperatures[label] = thermal_brackets(evidence / label, physical[label])
            chronological.append(arm_clock[label])
    clock.require(all(a["after"]["end_ns"] < b["before"]["begin_ns"] for a, b in zip(chronological, chronological[1:])),
                  "Clock brackets overlap or violate A1/B1/B2/A2 order")
    names = {"mixed": {mode: [report["arms"][f"p{i}-{mode}"] for i in range(1, 5)] for mode in MODES}}
    for case in CASES:
        names[case] = {mode: [report["homogeneous_arms"][f"homogeneous-p{i}-{case}-{mode}"] for i in (1, 2)] for mode in MODES}
    rate = {mode: config["clock_contract"]["pl0"][mode]["configured_hz"] for mode in MODES}
    derived = {"configured_hz": rate, "device_time_ratio": rate["control"] / rate["candidate"],
               "device_time_ms_for_exact_completion_cycles": {
                   case: {mode: config["replay"][mode][case]["cycles"]["done"] * 1000 / rate[mode] for mode in MODES}
                   for case in CASES}}
    return {**report, "clock_readbacks": arm_clock, "temperature_c": temperatures,
            "pooled_energy": {name: {mode: pooled(blocks) for mode, blocks in sides.items()} for name, sides in names.items()},
            "same_firmware": config["image"], "configured_rate_prediction": derived,
            "exact_work": config["replay"]["control"]}


def span(values):
    return f"{min(values):+.2f}% to {max(values):+.2f}%"


def findings(report):
    derived = report["configured_rate_prediction"]
    rate = derived["configured_hz"]
    a, b = (rate[m] for m in MODES)
    change = 100 * (derived["device_time_ratio"] - 1)
    lines = ["# Matching the same image at two PL0 rates", "",
             f"Linux configured PL0 at {a:,} Hz and {b:,} Hz. Both rates used the same image, model and workload. "
             f"All 200 timed replies, 36 warm-ups and nine smokes matched the reference output, EOS, work and exact device counters.", "",
             f"The configured rate ratio predicts a {change:+.2f}% change in device time for fixed clock counts. "
             "The host-inference elapsed time was at least the device-cycle time at each configured rate. "
             "That consistency check uses independent CPU timestamps and the configured rate. It provides no external clock-frequency reading.", "",
             "## Request timing", "",
             "| Prompt | TTFT, ms | Decode, tokens/s | Completion, ms | Paired completion change | Calculated device completion, ms |",
             "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for case in CASES:
        timing = [report["timing"][mode][case] for mode in MODES]
        pairs = [p[case]["candidate_vs_control"]["completion_ms"] for p in report["timing_pairs_pct"].values()]
        values = [" → ".join(f"{median(row[field]):.3f}" for row in timing) for field in ("ttft_ms", "decode_tps", "completion_ms")]
        predicted = " → ".join(f"{derived['device_time_ms_for_exact_completion_cycles'][case][mode]:.3f}" for mode in MODES)
        lines.append("| " + " | ".join((LABELS[case], *values, span(pairs), predicted)) + " |")
    lines += ["", "First, last and completion counters stayed identical at both rates.", "",
              "| Prompt | Positions | Scores consumed | Skipped positions | First clocks | Last clocks | Completion clocks |",
              "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for case in CASES:
        work = report["exact_work"][case]
        counts, cycles = work["counts"], work["cycles"]
        values = [counts[k] for k in ("context_count", "scores_consumed", "skipped_positions")]
        values += [cycles[k] for k in ("first", "last", "done")]
        lines.append("| " + " | ".join((LABELS[case], *(f"{v:,}" for v in values))) + " |")
    lines += ["", "## Gross VCC_SOM module energy", "",
              "| Scope | Active W | Idle W | Gross J/answer | Gross J/token | Tokens/J |",
              "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for case in ("mixed", *CASES):
        by_rate = report["pooled_energy"][case]
        keys = ("active_w", "idle_w", "gross_j_answer", "gross_j_token", "tokens_per_joule")
        cells = [" → ".join(f"{by_rate[m][key]:.6g}" for m in MODES) for key in keys]
        lines.append("| " + " | ".join((LABELS.get(case, "Mixed"), *cells)) + " |")
    lines += ["", "The active integral spans first admission through final verification. The 20 Hz INA260 trace uses a 75 ms contributing-gap limit. "
              "Configured-clock probes bracket the active interval. The shifted alignments may include power samples influenced by those probes. "
              "The five alignments below show paired gross J/answer changes.", "",
              "| Scope | Midpoint | Midpoint −50 ms | Midpoint +50 ms | Read start | Read end |",
              "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for case in ("mixed", *CASES):
        group = report["energy_pairs_pct"] if case == "mixed" else report["homogeneous_energy_pairs_pct"][case]
        values = [p["candidate_vs_control"]["energy_per_answer_by_alignment"] for p in group.values()]
        lines.append("| " + " | ".join((LABELS.get(case, "Mixed"), *(span([p[k] for p in values]) for k in ALIGNMENTS))) + " |")
    blocks = {**report["arms"], **report["homogeneous_arms"]}
    missed = sum(row["power_trace"]["missed_slots"] for row in blocks.values())
    spi_changed = [f"`{label}` {r['spi']['active_ms_delta']:+} ms SPI1 and {r['spi']['transfers_delta']:+} TPM transfers"
                   for label, r in blocks.items() if r["spi"]["active_ms_delta"] or r["spi"]["transfers_delta"]]
    lines += ["", f"The sampler missed {missed} scheduled slots. All 20 powered blocks passed the gap check."]
    if spi_changed:
        lines += ["", "Peripheral counters changed in " + ", ".join(spi_changed) + ". The brackets do not locate activity inside the active integral."]
    by_sensor = defaultdict(list)
    for row in report["temperature_c"].values():
        for readings in row.values():
            for key, value in readings.items():
                by_sensor[key].append(value)
    if by_sensor:
        lines += ["", "Temperature brackets ranged " + ", ".join(f"{sensor} {min(v):.1f}–{max(v):.1f} °C" for sensor, v in sorted(by_sensor.items())) + "."]
    else:
        lines += ["", "Temperature sensors supplied no usable readings in the captured brackets."]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for value in ("evidence", "config", "output"):
        parser.add_argument(value, type=Path)
    parser.add_argument("--packet", type=Path, default=HERE)
    args = parser.parse_args()
    report = audit(args.evidence, args.packet, clock.read_json(args.config))
    args.output.mkdir(mode=0o700)
    clock.write_json(args.output / "score.json", report)
    (args.output / "measurement-findings.md").write_text(findings(report))
