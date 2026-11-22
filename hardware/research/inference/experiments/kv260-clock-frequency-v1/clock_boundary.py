"""Record and verify configured Linux clock readback outside the energy window."""

import json
from math import prod
from pathlib import Path
import time

from measurement import CASES, MODES


FIRMWARE_FIELDS = {"name", "sha256"}
CLOCK_FIELDS = {"configured_hz", "parent", "parent_hz", "dividers", "enabled"}


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def read_json(path):
    return json.loads(Path(path).read_bytes())


def write_json(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")


def clock_product(clock):
    require(set(clock) == CLOCK_FIELDS and clock["enabled"] is True
            and isinstance(clock["parent"], str) and clock["parent"]
            and isinstance(clock["dividers"], dict) and clock["dividers"]
            and all(isinstance(k, str) and k and type(v) is int and v > 0 for k, v in clock["dividers"].items())
            and all(type(clock[k]) is int and clock[k] > 0 for k in ("configured_hz", "parent_hz")),
            "Missing configured PL0 rate, enabled state, parent or divider chain")
    divider = prod(clock["dividers"].values())
    require(abs(clock["configured_hz"] * divider - clock["parent_hz"]) <= divider,
            "Configured Linux rate cannot be reconciled with the divider chain")
    return divider


def validate_config(config):
    pin = config["image"]
    require(set(pin) == FIRMWARE_FIELDS and config["pins"][pin["name"]]["sha256"] == pin["sha256"],
            "Same-firmware asset pin differs")
    replay = config["replay"]
    require(set(replay) == set(MODES) and replay["control"] == replay["candidate"]
            and set(replay["control"]) == set(CASES), "Both rates must use the same exact reference")
    clock = config["clock_contract"]
    require(set(clock["pl0"]) == set(MODES) and isinstance(clock["unrelated_clocks"], dict)
            and clock["unrelated_clocks"], "Both PL0 configurations and unrelated clock fingerprints are required")
    a, b = (clock["pl0"][mode] for mode in MODES)
    require(clock_product(a) == 20 and clock_product(b) in (16, 19) and a["configured_hz"] == 50_000_000
            and b["configured_hz"] > a["configured_hz"]
            and (a["parent"], a["parent_hz"], set(a["dividers"])) ==
            (b["parent"], b["parent_hz"], set(b["dividers"])),
            "Only the registered PL0 divider values may differ")
    qualified = config["qualified_rates_hz"]
    require(all(str(row["configured_hz"]) in qualified
                and row["configured_hz"] <= qualified[str(row["configured_hz"])] for row in (a, b)),
            "This programming image lacks admitted timing at the configured PL0 rate")


def verify_snapshot(config, mode, observed):
    contract = config["clock_contract"]
    require(observed.get("boot") == config["boot"], "Boundary readback boot differs")
    require(observed.get("image") == config["image"], "Boundary readback firmware identity differs")
    require(observed.get("pl0") == contract["pl0"][mode], "Boundary configured PL0 clock differs")
    require(observed.get("unrelated_clocks") == contract["unrelated_clocks"], "Boundary unrelated clock fingerprint differs")


def capture(output, edge, config, mode, readback, now=time.monotonic_ns):
    path = output / f"clock-{edge}.json"
    begin = now()
    try:
        state = readback()
    except Exception as exc:
        write_json(path, {"begin_ns": begin, "end_ns": now(), "error": f"{type(exc).__name__}: {exc}"})
        raise
    write_json(path, {"begin_ns": begin, "end_ns": now(), "readback": state})
    verify_snapshot(config, mode, state)


def audit(output, config, mode, *, smoke=False):
    edges = ("before", "after") if smoke else ("before", "active-before", "active-after", "after")
    receipts = {edge: read_json(output / f"clock-{edge}.json") for edge in edges}
    for row in receipts.values():
        require(type(row["begin_ns"]) is int and type(row["end_ns"]) is int
                and 0 < row["begin_ns"] <= row["end_ns"], "Invalid configured-clock receipt chronology")
        verify_snapshot(config, mode, row["readback"])

    before, after = (receipts[edge] for edge in ("before", "after"))
    block = read_json(output / ("smoke.json" if smoke else "block.json"))
    if smoke:
        require(before["end_ns"] <= block["begin_ns"] < block["end_ns"] <= after["begin_ns"],
                "Smoke timing is outside the verified clock brackets")
    else:
        warm = read_json(output / "warmup.json")
        arm = read_json(output / "arm.json")
        active_before, active_after = (receipts[edge] for edge in ("active-before", "active-after"))
        require(before["end_ns"] <= warm["begin_ns"] < warm["end_ns"] <= arm["phases"]["idle_before"][0]
                < arm["phases"]["idle_before"][1] <= active_before["begin_ns"] <= active_before["end_ns"]
                <= block["begin_ns"] < block["end_ns"] <= active_after["begin_ns"] <= active_after["end_ns"]
                < arm["phases"]["idle_after"][0] < arm["phases"]["idle_after"][1] <= after["begin_ns"],
                "Power and request windows are outside the verified clock brackets")
    configured_hz = config["clock_contract"]["pl0"][mode]["configured_hz"]
    for receipt in (block,) if smoke else (warm, block):
        for row in receipt["requests"]:
            header = row["observed"]["header"]
            inference_elapsed_ns = header["done_ns"] - header["timing"]["inference_begin_ns"]
            require(header["request_cycles"]["done"] * 1_000_000_000 <= inference_elapsed_ns * configured_hz,
                    "Request wall time is shorter than its FPGA cycles at configured PL0 rate")
    return receipts
