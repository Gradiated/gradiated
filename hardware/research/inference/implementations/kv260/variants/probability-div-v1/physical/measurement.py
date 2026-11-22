"""Frozen on-chip comparison schedule and FPGA cycle acceptance."""

CASES = ("encoded-hello", "encoded-fu2p2q", "encoded-max48")
MODES = ("control", "candidate")
HOMOGENEOUS_REPLIES = dict(zip(CASES, (18, 12, 8), strict=True))
SESSIONS = (
    ("A1", "control", (1, 2), 1, CASES, True),
    ("B1", "candidate", (1, 2), 1, CASES, True),
    ("B2", "candidate", (3, 4), 2, CASES[::-1], False),
    ("A2", "control", (3, 4), 2, CASES[::-1], True),
)
REQUEST_NS = 5_000_000_000
MEASUREMENT_SECONDS = 1800
RESTORE_SECONDS = 180
CONTROL_REPLAY = {
    "encoded-hello": {"first": 416191, "last": 5078839, "done": 5142970},
    "encoded-fu2p2q": {"first": 494945, "last": 7402040, "done": 7475095},
    "encoded-max48": {"first": 4745325, "last": 12626576, "done": 12716857},
}
COUNT_KEYS = ("context_count", "scores_consumed", "skipped_positions")


def mixed_order(round_id):
    if round_id not in (1, 2, 3, 4):
        raise ValueError("Invalid mixed round")
    first, second, last = CASES if round_id < 3 else CASES[::-1]
    return (first, second, last), (first, second, last, second, first, last)


def verify_counts(case, header, reference):
    expected = reference[case]
    actual = {key: header[key] for key in COUNT_KEYS}
    if header["request_cycles"] != expected["cycles"] or actual != expected["counts"]:
        raise ValueError(f"{case}: FPGA clocks or work counts differ from exact RTL replay")
    if header["scores_consumed"] != 320 * (header["context_count"] - header["skipped_positions"]):
        raise ValueError(f"{case}: scored positions disagree with context and skip counts")


class CheckedDelivery:
    """Apply the watchdog and exact cycle gate to each compact reply."""

    def __init__(self, delivery, reference, deadline_ns):
        self.delivery = delivery
        self.reference = reference
        self.deadline_ns = deadline_ns
        self.BlockFailure = delivery.BlockFailure

    def run_block(self, runner, cases, references, admit):
        rows = []
        try:
            for case, timed in cases:
                self.delivery.deadline_ns = min(self.deadline_ns, runner.now() + REQUEST_NS)
                block, _ = self.delivery.run_block(runner, [(case, timed)], references, admit)
                row, = block["requests"]
                rows.append(row)
                verify_counts(case, row["observed"]["header"], self.reference)
                row["verified_ns"] = runner.now()
        except self.BlockFailure as err:
            raise self.BlockFailure(err, rows + err.completed) from err
        except Exception as err:
            raise self.BlockFailure(err, rows) from err
        return {
            "begin_ns": rows[0]["observed"]["header"]["admitted_ns"],
            "end_ns": rows[-1]["verified_ns"],
            "requests": rows,
        }, {}
