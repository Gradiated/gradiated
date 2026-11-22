"""Matched, resident KV260 comparison using exact completion verification."""

from itertools import chain
from statistics import median


class BlockFailure(RuntimeError):
    def __init__(self, error, completed):
        super().__init__(str(error))
        self.detail = getattr(error, "partial", None)
        self.completed = completed


def schedule(base, pair):
    warmup = base.FORWARD[pair]
    follow = base.REVERSE[pair]
    turn = follow.index(warmup[-1]) + 1
    return [(case, False) for case in warmup], [(case, True) for case in warmup + follow[turn:] + follow[:turn]]


def verify_row(runtime, row, expected, index, previous, earliest, candidate):
    data = row["observed"]["header"]
    if row["observed"]["frames"]:
        raise ValueError("A compact timed receipt cannot claim full-score frames")
    runtime.compare_reference(data, expected)
    timing = data["timing"]
    ordered = [earliest, data["admitted_ns"]]
    if index:
        clear = timing["clear"]
        if (not clear or clear["context_count"] != 0 or clear["counters"] != [0, 29281, 0, 0, 0]):
            raise ValueError("Resident request did not clear the previous context")
        ordered.extend((clear["begin_ns"], clear["end_ns"]))
    elif timing["clear"] is not None or previous != 0:
        raise ValueError("Unexpected initial resident context")
    ordered.extend([timing["inference_begin_ns"], *data["output_ns"], data["done_ns"],
                    timing["inference_end_ns"], data["returned_ns"], row["verified_ns"]])
    if (timing["index"] != index or timing["previous_context_count"] != previous or
            not all(type(value) is int for value in ordered) or ordered != sorted(ordered) or
            any(a >= b for a, b in zip(data["output_ns"], data["output_ns"][1:])) or
            data["admitted_ns"] >= data["done_ns"]):
        raise ValueError("Resident timing or chronology differs")
    context = data["context_count"]
    if candidate:
        cycles = data["request_cycles"]
        if (data["scores_consumed"] != runtime.VOCAB * context or not 0 < cycles["done"] or
                cycles["done"] * 20 > data["done_ns"] - timing["inference_begin_ns"] or
                bool(data["output_ns"]) != ("first" in cycles and "last" in cycles) or
                data["output_ns"] and not 0 < cycles["first"] <= cycles["last"] <= cycles["done"]):
            raise ValueError("Autonomous work or output cycles disagree with the timed request")
    elif "scores_consumed" in data or "request_cycles" in data:
        raise ValueError("Control cannot claim autonomous counters")
    return context


class DeliveryBenchmark:
    """Adapter for the existing matched power/idle instrumentation."""

    BlockFailure = BlockFailure

    def __init__(self, runtime, port=None, max_output=255, deadline_ns=None):
        self.runtime = runtime
        self.port = port
        self.max_output = max_output
        self.deadline_ns = deadline_ns

    def run_block(self, runner, cases, references, admit):
        completed = []
        index = runner.requests
        previous = runner.session.context_count
        earliest = runner.setup["ready_ns"]
        try:
            for case, _ in cases:
                admit()
                expected = references[case]
                result = self.runtime.complete(runner, expected["prefix_text"], self.port,
                                               max_output=self.max_output, deadline_ns=self.deadline_ns)
                # These checks are outside each inference timing window. The
                # repeated-block rail integral intentionally includes these gaps.
                row = {"case": case, "observed": {"header": result, "frames": []},
                       "verified_ns": runner.now()}
                previous = verify_row(self.runtime, row, expected, index, previous, earliest,
                                      self.port is not None)
                row["verified_ns"] = runner.now()
                completed.append(row)
                index += 1
                earliest = row["verified_ns"]
        except Exception as error:
            raise BlockFailure(error, completed) from error
        if not completed:
            raise ValueError("Empty delivery block")
        return {"begin_ns": completed[0]["observed"]["header"]["admitted_ns"],
                "end_ns": completed[-1]["verified_ns"], "requests": completed}, {}


def check_block(runtime, block, cases, references, candidate, index, previous, earliest):
    rows = block["requests"]
    if (len(rows) != len(cases) or not rows or
            block["begin_ns"] != rows[0]["observed"]["header"]["admitted_ns"] or
            block["end_ns"] != rows[-1]["verified_ns"]):
        raise ValueError("Delivery block boundary or row count differs")
    for row, (case, _) in zip(rows, cases, strict=True):
        if row["case"] != case:
            raise ValueError("Recorded delivery case order differs")
        previous = verify_row(runtime, row, references[case], index, previous, earliest, candidate)
        index += 1
        earliest = row["verified_ns"]
    return index, previous, earliest


def timings(block):
    cases = {}
    for row in block["requests"]:
        data = row["observed"]["header"]
        values = cases.setdefault(row["case"], {"ttft_ms": [], "decode_bytes_per_second": [],
                                               "completion_ms": [], "verified_ms": []})
        start = data["admitted_ns"]
        times = data["output_ns"]
        if times:
            values["ttft_ms"].append((times[0] - start) / 1e6)
        if len(times) >= 2 and times[-1] > times[0]:
            values["decode_bytes_per_second"].append((len(times) - 1) * 1e9 / (times[-1] - times[0]))
        values["completion_ms"].append((data["done_ns"] - start) / 1e6)
        values["verified_ms"].append((row["verified_ns"] - start) / 1e6)
    return cases


def comparison(gates):
    pairs = []
    for pair in range(1, 4):
        arms = [gates[f"p{pair}-{mode}"]["checked"] for mode in ("stock", "candidate")]
        timing = {}
        for case, metrics in arms[0]["timing"].items():
            timing[case] = {}
            for key, control_values in metrics.items():
                variant_values = arms[1]["timing"][case][key]
                left, right = ([*values] for values in (control_values, variant_values))
                if left and right:
                    baseline, candidate = median(left), median(right)
                    timing[case][key] = {"stock_median": baseline, "candidate_median": candidate,
                                         "relative_change": candidate / baseline - 1 if baseline else None}
        pairs.append({"pair": pair, "timing": timing, "rail": [arm["rail"] for arm in arms]})
    return pairs


def block_summary(block, examples):
    return {"requests": len(block["requests"]), "begin_ns": block["begin_ns"], "end_ns": block["end_ns"],
            "output_bytes": sum(len(row["observed"]["header"]["output_ns"]) for row in block["requests"]),
            "frames": 0, "examples": sorted(examples)}


def capped_reference(reference, cap):
    if cap not in (0, 1) or not reference["generated_tokens"] or reference["generated_tokens"][0] >= 256:
        raise ValueError("Expected a zero/one-token cap and frozen useful first byte")
    prefix = reference["prefix_tokens"]
    logits = reference["frames"][len(prefix) - 1]["logits"]
    selected = max(range(320), key=logits.__getitem__)
    if selected != reference["generated_tokens"][0]:
        raise ValueError("Frozen reference does not agree with score selection")
    ids = [selected] if cap else []
    return {**reference, "generated_tokens": ids, "stop_reason": "output_limit",
            "context_count": len(prefix), "byte_prefix_hex": bytes(ids).hex()}
