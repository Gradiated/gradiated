"""Summarise disjoint parent cycles and separate, possibly overlapping child activity."""

import json
from pathlib import Path
import sys


PARENT = (
    "idle", "pair", "exp_send", "exp_wait", "sigmoid_send", "sigmoid_wait",
    "gate_multiply_send", "gate_multiply_wait", "silu_shift_send", "silu_shift_wait",
    "hidden_multiply_send", "hidden_multiply_wait", "hidden_shift_send", "hidden_shift_wait",
    "store", "down_start", "down_run",
)
COMMANDS = ("exp", "sigmoid_divide", "gate_multiply", "silu_shift", "hidden_multiply", "hidden_shift")
SCALAR = (
    "idle", "output", "div_step", "mul_step", "simple_done", "exp_power", "exp_index",
    "exp_load", "exp_mul", "exp_interp", "exp_done", "rsq_index", "rsq_load", "rsq_yy",
    "rsq_my", "rsq_factor", "rsq_update", "div_finish",
)
FIELDS = (
    ("POSITION", 3), ("PREPARE", 6), ("PARENT", 17), ("ACTIVITY", 17 * 16),
    ("DENSE", 3 * 5), ("DENSE_IO", 3 * 2), ("COMMAND_IO", 6 * 4), ("SCALAR", 6 * 18),
    ("EXP_DIV", 3 * 3), ("ARGS_MIN", 6 * 3), ("ARGS_MAX", 6 * 3),
)
DENSE = ("gate", "up", "down")
DIVISIONS = ("range_reduction", "table_address", "interpolation")


def matrix(values, columns):
    return [values[i:i + columns] for i in range(0, len(values), columns)]


def need(condition, message):
    if not condition:
        raise ValueError(message)


def read_positions(path):
    lines = path.read_text().splitlines()
    width = len(FIELDS)
    need(len(lines) % width == 0, "Incomplete per-position profile")
    for start in range(0, len(lines), width):
        fields = {}
        for line, (field, size) in zip(lines[start:start + width], FIELDS, strict=True):
            name, *tokens = line.split()
            need(name == field and len(tokens) == size, f"Wrong shape for {field}")
            values = [int(value) for value in tokens]
            if not field.startswith("ARGS"):
                need(all(value >= 0 for value in values), f"Negative count in {field}")
            fields[field] = values
        yield fields


def validate_position(fields, position):
    need(fields["POSITION"] == [position, 32, 0], f"Bad position, result count or state: {position}")
    setup = fields["PREPARE"]
    need(setup[1] == 32 and setup[4] == 1 and setup[4] + setup[5] == setup[3], "Input or launch geometry")
    parent = fields["PARENT"]
    cycles = sum(parent)
    need(parent[0] == 0 and cycles == 34306, f"FF_WAIT clocks differ in position {position}")
    masks = matrix(fields["ACTIVITY"], 16)
    need(list(map(sum, masks)) == parent, "Overlap mask partition differs from parent")

    for i, (counts, io) in enumerate(zip(matrix(fields["DENSE"], 5), matrix(fields["DENSE_IO"], 2), strict=True)):
        need(sum(counts) == cycles and sum(io) == counts[4], "Dense occupancy or handshake counter mismatch")
        need(io[0] == (32 if i == 2 else 128), "Missing dense row results")
        # Mask bit i corresponds to READ, MAC and ROUND activity of this dense engine.
        from_masks = sum(row[mask] for row in masks for mask in range(16) if mask & (1 << i))
        need(from_masks == sum(counts[1:4]), "Dense arithmetic occupancy does not reconcile")

    command = matrix(fields["COMMAND_IO"], 4)
    scalar = matrix(fields["SCALAR"], 18)
    ranges = zip(fields["ARGS_MIN"], fields["ARGS_MAX"], strict=True)
    need(all(low <= high for low, high in ranges), "Unordered captured scalar operand ranges")
    for i, (io, ticks) in enumerate(zip(command, scalar, strict=True)):
        need(io[0] == io[2] == 128, "Missing accepted/completed scalar commands")
        need(parent[2 + 2*i] == io[0] + io[1] and parent[3 + 2*i] == sum(ticks), "Scalar parent wait/send attribution differs")
        need(ticks[1] == io[2] + io[3], "Scalar result handshakes differ from output occupancy")
    scalar_active = sum(row[mask] for row in masks for mask in range(8, 16))
    need(scalar_active == sum(sum(ticks[2:]) for ticks in scalar), "Scalar arithmetic occupancy does not reconcile")
    exp = matrix(fields["EXP_DIV"], 3)
    need(sum(row[0] for row in exp) == scalar[0][2] and sum(row[1] for row in exp) == scalar[0][17],
         "Nested exponential division cycles differ from parent command's divider occupancy")
    need(all(row[1] == row[2] for row in exp), "Nested exponential division entry/finish counts differ")


def totals(rows, field):
    return [sum(column) for column in zip(*(row[field] for row in rows), strict=True)]


def summarise(path, exact_case):
    rows = list(read_positions(path))
    expected = exact_case["done"]
    need(rows and len(rows) == expected["positions"], "Missing or extra feed-forward positions")
    for position, fields in enumerate(rows, 1):
        validate_position(fields, position)
    phase_ticks = expected["phases"]
    parent = totals(rows, "PARENT")
    preparation = totals(rows, "PREPARE")
    need(sum(parent) == phase_ticks[14] and preparation[0] == phase_ticks[12] and preparation[3] == phase_ticks[13],
         "Profile does not match the adopted model phase counters")
    # Begin/end are independent archived request boundaries. The final prefix
    # position has already run feed-forward when LOGIT_START is first sampled.
    prefix_positions = exact_case["prefix"]["positions"]
    need(sum(totals(rows[:prefix_positions], "PARENT")) == exact_case["prefix"]["phases"][14],
         "Feed-forward prefix does not match the archived phase counter")
    return {
        "positions": len(rows),
        "prefix_positions": prefix_positions,
        "whole_request_cycles": expected["done"],
        "preparation": dict(zip(
            ("norm2_wait_ticks", "accepted_inputs", "blocked_input_ticks", "ff_start_ticks", "launches", "blocked_launch_ticks"),
            preparation, strict=True
        )),
        "ff_wait_ticks": sum(parent),
        "parent_state_ticks": dict(zip(PARENT, parent, strict=True)),
        "active_child_masks_by_parent_state": dict(zip(PARENT, matrix(totals(rows, "ACTIVITY"), 16), strict=True)),
        "dense_state_ticks": dict(zip(DENSE, matrix(totals(rows, "DENSE"), 5), strict=True)),
        "dense_output_counts": dict(zip(DENSE, matrix(totals(rows, "DENSE_IO"), 2), strict=True)),
        "scalar_command_counts": dict(zip(COMMANDS, matrix(totals(rows, "COMMAND_IO"), 4), strict=True)),
        "scalar_substate_ticks_by_command": {
            command: dict(zip(SCALAR, ticks, strict=True))
            for command, ticks in zip(COMMANDS, matrix(totals(rows, "SCALAR"), 18), strict=True)
        },
        "exp_nested_division_ticks": dict(zip(DIVISIONS, matrix(totals(rows, "EXP_DIV"), 3), strict=True)),
        "per_position": rows,
    }
