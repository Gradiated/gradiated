"""Validate Experiment 16 counters at the end of an autonomous request."""

# Experiment 13 physical record, candidate arm. Values were identical in all
# repetitions and matched the independent full-model RTL replay.
CONTROL_CLOCKS = {
    "encoded-hello": {"first": 416191, "last": 5078839, "done": 5142970},
    "encoded-fu2p2q": {"first": 494945, "last": 7402040, "done": 7475095},
    "encoded-max48": {"first": 4745325, "last": 12626576, "done": 12716857},
}


MODES = ("bram", "ddr")
HOMOGENEOUS_REPLIES = {"encoded-hello": 18, "encoded-fu2p2q": 12, "encoded-max48": 8}
SESSIONS = (
    ("A1", "bram", (1, 2), 1, tuple(HOMOGENEOUS_REPLIES), True),
    ("B1", "ddr", (1, 2), 1, tuple(HOMOGENEOUS_REPLIES), True),
    ("B2", "ddr", (3, 4), 2, tuple(reversed(HOMOGENEOUS_REPLIES)), False),
    ("A2", "bram", (3, 4), 2, tuple(reversed(HOMOGENEOUS_REPLIES)), True),
)
POSITION_SCORE_COUNT = 320
BYTES_PER_PROJECTION = 20480
READS_PER_PROJECTION = 320
BEATS_PER_PROJECTION = 2560
BASE_CYCLES_PER_PROJECTION = 1680
STAGING_CYCLES_PER_PROJECTION = 2880


def scored_positions(header):
    scores = header["scores_consumed"]
    scored, partial = divmod(scores, POSITION_SCORE_COUNT)
    if partial or scored <= 0 or scored != header["context_count"] - header["skipped_positions"]:
        raise ValueError("Fully scored positions disagree with context and skipped work")
    return scored


def verify_counters(case, header, counters, mode):
    scored = scored_positions(header)
    control = CONTROL_CLOCKS[case]
    cycles = header["request_cycles"]
    if mode == "bram":
        if counters is not None or cycles != control:
            raise ValueError("BRAM control differs from the selected Experiment 13 circuit")
        return
    expected = {
        "projections": scored,
        "useful_bytes": BYTES_PER_PROJECTION * scored,
        "reads": READS_PER_PROJECTION * scored,
        "beats": BEATS_PER_PROJECTION * scored,
        "faults": 0,
    }
    for key, value in expected.items():
        if counters[key] != value:
            raise ValueError(f"{key}: expected {value}, observed {counters[key]}")
    if counters["mode"] != "ddr" or counters["transport_busy"] or counters["fault"]:
        raise ValueError("Wrong weight source or active/faulted logits reader at completion")
    extra = counters["extra_clocks"]
    if extra != STAGING_CYCLES_PER_PROJECTION * scored + counters["ar_stalls"] + counters["response_waits"]:
        raise ValueError("DDR stalls and buffer staging do not explain the extra logits clocks")
    if counters["projection_clocks"] != BASE_CYCLES_PER_PROJECTION * scored + extra:
        raise ValueError("Projection busy cycles differ from arithmetic and DDR waits")
    if not 0 < counters["projection_clocks"] <= cycles["done"]:
        raise ValueError("Logits projection clocks outside complete-request interval")
    first_extra = cycles["first"] - control["first"]
    last_extra = cycles["last"] - control["last"]
    if cycles["done"] != control["done"] + extra or not 0 < first_extra <= last_extra <= extra:
        raise ValueError("Extra request and token clocks disagree with the weight fetch")
    if first_extra < STAGING_CYCLES_PER_PROJECTION:
        raise ValueError("First emitted token lacks a complete logits fetch")


class CountedDelivery:
    """Use the existing timing path and read stable counters before the next clear."""

    def __init__(self, delivery, snapshot, mode, request_budget_ns, arm_deadline_ns):
        self.delivery = delivery
        self.snapshot = snapshot
        self.mode = mode
        self.request_budget_ns = request_budget_ns
        self.arm_deadline_ns = arm_deadline_ns
        self.BlockFailure = delivery.BlockFailure

    def run_block(self, runner, cases, references, admit):
        rows = []
        try:
            for case, timed in cases:
                self.delivery.deadline_ns = min(self.arm_deadline_ns, runner.now() + self.request_budget_ns)
                block, _ = self.delivery.run_block(runner, [(case, timed)], references, admit)
                row, = block["requests"]
                rows.append(row)
                counters = self.snapshot() if self.snapshot is not None else None
                row["ddr_counters"] = counters
                verify_counters(case, row["observed"]["header"], counters, self.mode)
                row["ddr_counters_checked_ns"] = runner.now()
        except self.BlockFailure as err:
            raise self.BlockFailure(err, rows + err.completed) from err
        except Exception as err:
            raise self.BlockFailure(err, rows) from err
        return {
            "begin_ns": rows[0]["observed"]["header"]["admitted_ns"],
            "end_ns": rows[-1]["verified_ns"],
            "requests": rows,
        }, {}
