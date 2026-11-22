"""Validate Experiment 14 counters at the end of an autonomous request."""

# Experiment 13 physical record, candidate arm. Values were identical in all
# repetitions and matched the independent full-model RTL replay.
CONTROL_CLOCKS = {
    "encoded-hello": {"first": 416191, "last": 5078839, "done": 5142970},
    "encoded-fu2p2q": {"first": 494945, "last": 7402040, "done": 7475095},
    "encoded-max48": {"first": 4745325, "last": 12626576, "done": 12716857},
}


def verify_counters(case, header, counters, use_ddr):
    context = header["context_count"]
    if not 1 <= context <= 256:
        raise ValueError("Invalid number of completed positions")
    reads = context * 1024 if use_ddr else 0
    expected = {
        "projections": context,
        "useful_bytes": reads * 2,
        "reads": reads,
        "beats": reads,
        "faults": 0,
    }
    for key, value in expected.items():
        if counters[key] != value:
            raise ValueError(f"{key}: expected {value}, observed {counters[key]}")
    if not 0 < counters["projection_clocks"] <= header["request_cycles"]["done"]:
        raise ValueError("Projection clocks outside complete-request interval")
    extra = counters["extra_clocks"]
    if extra != 2 * reads + counters["ar_stalls"] + counters["response_waits"]:
        raise ValueError("Address and response waits do not explain the extra READ clocks")
    if counters["projection_clocks"] != 2112 * context + extra:
        raise ValueError("Projection work or read stalls differ from the dense RTL schedule")
    control = CONTROL_CLOCKS[case]
    cycles = header["request_cycles"]
    if use_ddr:
        if cycles["done"] != control["done"] + extra:
            raise ValueError("Extra request clocks differ from observed weight wait clocks")
        if not control["first"] < cycles["first"] or not control["last"] < cycles["last"]:
            raise ValueError("Inconsistent first or last token clocks in DDR mode")
    elif extra or cycles != control:
        raise ValueError("BRAM mode differs from the adopted Experiment 13 circuit")


class CountedDelivery:
    """Use the existing timing path and read stable counters before the next clear."""

    def __init__(self, delivery, snapshot, use_ddr, request_budget_ns, arm_deadline_ns):
        self.delivery = delivery
        self.snapshot = snapshot
        self.use_ddr = use_ddr
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
                counters = self.snapshot()
                row["ddr_counters"] = counters
                verify_counters(case, row["observed"]["header"], counters, self.use_ddr)
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
