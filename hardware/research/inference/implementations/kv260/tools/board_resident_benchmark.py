"""Balanced resident benchmark blocks with exact score checks and compact receipts."""

from itertools import chain

A, B, C = CASES = "encoded-fu2p2q", "encoded-hello", "encoded-max48"
FORWARD = ((A, B, C), (B, C, A), (C, A, B))
REVERSE = ((A, C, B), (B, A, C), (C, B, A))
LONG_ORDER = (FORWARD[0], REVERSE[0], FORWARD[1], REVERSE[1], FORWARD[2], REVERSE[2])
CLEAR_COUNTERS = [0, 29281, 0, 0, 0]


def schedule(session):
    if not 0 <= session < 3:
        raise ValueError("Expected process session index 0–2")
    current, following = session, (session + 1) % 3
    warmup = tuple(chain(FORWARD[current], REVERSE[current]))
    short = tuple(chain(FORWARD[current], REVERSE[current], FORWARD[following], REVERSE[following]))
    modes = (False, True) if session % 2 == 0 else (True, False)
    yield "warmup", [(case, False) for case in warmup]
    yield "observer", [(B, mode) for mode in modes]
    yield "short", [(case, True) for case in short]
    if session == 2:
        long = tuple(chain.from_iterable(LONG_ORDER * 2 + LONG_ORDER[:4]))
        yield "long", [(case, True) for case in long]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def compact(completion):
    return {
        "header": {name: value for name, value in completion.items() if name != "frames"},
        "frames": [[frame["logits_sha256"], frame["counters"]] for frame in completion["frames"]],
    }


class Mismatch(ValueError):
    def __init__(self, message, detail):
        super().__init__(message)
        self.detail = detail


class BlockFailure(RuntimeError):
    def __init__(self, cause, completed, examples):
        super().__init__(str(cause))
        self.detail = getattr(cause, "detail", None)
        self.completed = completed
        self.examples = examples


def check_actual(actual, expected):
    """Compare every raw signed score before admitting another request."""
    frames, wanted = actual["frames"], expected["frames"]
    for position, (frame, reference) in enumerate(zip(frames, wanted)):
        if frame != reference:
            raise Mismatch("Resident frame differs", {"position": position, "actual": frame, "expected": reference})
    if len(frames) != len(wanted):
        position = min(len(frames), len(wanted))
        raise Mismatch("Frame count differs", {"position": position, "actual_count": len(frames),
                       "expected_count": len(wanted), "actual": frames[position] if position < len(frames) else None,
                       "expected": wanted[position] if position < len(wanted) else None})
    result = compact(actual)
    reference = {name: value for name, value in expected.items() if name != "frames"}
    if result["header"] != reference:
        raise Mismatch("Resident completion differs", {"actual": result["header"], "expected": reference})
    return result


def context(receipt):
    return receipt["observed"]["header"]["context_count"]


def check_request(result, case, detailed, expected_index, previous, earliest, expected):
    require(result["case"] == case and result["detailed"] is detailed and result["observed"] == expected,
            "Request identity, counters, decisions or score digests differ")
    return check_timing(result, detailed, expected_index, previous, earliest)


def check_timing(result, detailed, expected_index, previous, earliest):
    timing = result["timing"]
    require(timing["index"] == expected_index and timing["previous_context_count"] == previous,
            "Resident request index or previous context differs")
    admitted = result["admitted_ns"]
    returned = result["returned_ns"]
    verified = result["verified_ns"]
    begin, end = timing["inference_begin_ns"], timing["inference_end_ns"]
    first, eos = timing["first_byte_ns"], timing["eos_ns"]
    clear = timing["clear"]
    points = [earliest, admitted]
    if expected_index:
        require(clear is not None and clear["context_count"] == 0 and clear["counters"] == CLEAR_COUNTERS,
                "Missing or invalid native clear")
        points.extend((clear["begin_ns"], clear["end_ns"]))
    else:
        require(clear is None and previous == 0, "Initial resident context differs")
    points.extend((begin, first))
    if detailed:
        emissions = timing["emitted_byte_ns"]
        require(type(emissions) is list and len(emissions) == len(result["observed"]["header"]["generated_tokens"])
                and emissions[0] == first and emissions[-1] < eos, "Emitted-byte timestamps differ")
        points.extend(emissions[1:])
    else:
        require("emitted_byte_ns" not in timing, "Observer control recorded optional timestamps")
    points.extend((eos, end, returned, verified))
    require(all(type(point) is int for point in points) and points == sorted(points)
            and admitted < verified and first < eos,
            "Request, clear, inference or verification timestamps are out of order")
    return context(result)


def validate_block(block, cases, expected, index, previous, earliest):
    requests = block["requests"]
    require(len(requests) == len(cases) and len(requests) > 0, "Block schedule length differs")
    require(block["begin_ns"] == requests[0]["admitted_ns"]
            and block["end_ns"] == requests[-1]["verified_ns"], "Block timing omits work or gaps")
    for result, (case, detailed) in zip(requests, cases, strict=True):
        previous = check_request(result, case, detailed, index, previous, earliest, expected[case])
        earliest = result["verified_ns"]
        index += 1
    return index, previous, earliest


def run_block(runner, cases, references, admit, *, capture_examples=False):
    """Verify requests synchronously. Hardware state remains resident throughout."""
    require(0 < len(cases) <= 48, "Request block is outside the declared bound")
    completed, examples = [], {}
    now = runner.now
    index = runner.requests
    previous = runner.session.context_count
    earliest = runner.setup["ready_ns"]
    try:
        for case, detailed in cases:
            admit()
            prompt = references[case]["prefix_text"]
            admitted = now()
            result = runner.complete(prompt, time_each_byte=detailed)
            returned = now()
            actual = result["completion"]
            observed = check_actual(actual, references[case])
            if capture_examples and case not in examples:
                examples[case] = actual
            receipt = {"case": case, "detailed": detailed, "timing": result["timing"],
                       "observed": observed, "admitted_ns": admitted, "returned_ns": returned,
                       "verified_ns": now()}
            # Check timestamps before starting another hardware request.
            previous = check_timing(receipt, detailed, index, previous, earliest)
            receipt["verified_ns"] = now()
            completed.append(receipt)
            earliest = receipt["verified_ns"]
            index += 1
            del result, actual
    except Exception as error:
        raise BlockFailure(error, completed, examples) from error
    return {"begin_ns": completed[0]["admitted_ns"], "end_ns": completed[-1]["verified_ns"],
            "requests": completed}, examples
