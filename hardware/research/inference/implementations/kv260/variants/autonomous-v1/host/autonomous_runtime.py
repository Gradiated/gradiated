"""Host side of the KV260 AU01 request interface and its matched control."""

import ctypes
from unittest.mock import patch

CONTEXT = 256
BOS = 256
EOS = 257
VOCAB = 320
MAX_OUTPUT = 255
ABI = 0x41553031
DEADLINE_NS = 30_000_000_000
STOP_CODES = {1: "eos", 2: "context_limit", 3: "non_byte_token", 4: "output_limit"}
STATUS_FAULT = 4
STATUS_DONE = 2
STATUS_ACTIVE = 1
STATUS_OUTPUT = 8
STATUS_FIRST_TIME = 16
STATUS_LAST_TIME = 32
STATUS_OVERFLOW = 64


class RequestFailure(RuntimeError):
    def __init__(self, message, *, partial=None):
        super().__init__(message)
        self.partial = partial


class NativeEvent(ctypes.Structure):
    _fields_ = [("observed_ns", ctypes.c_uint64),
                ("status", ctypes.c_uint32),
                ("token", ctypes.c_uint32)]


class Port:
    """Access the extension through the live, exclusively owned native session."""

    def __init__(self, session, library):
        self.session = session
        self.library = ctypes.CDLL(str(library))
        u32 = ctypes.c_uint32
        u64 = ctypes.c_uint64
        bindings = {
            "autonomous_read": [ctypes.c_void_p, u32, ctypes.POINTER(u32)],
            "autonomous_start": [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint16),
                                 ctypes.c_size_t, u32, u64],
            "autonomous_wait": [ctypes.c_void_p, u64, ctypes.POINTER(NativeEvent)],
        }
        for name, signature in bindings.items():
            fn = getattr(self.library, name)
            fn.argtypes = signature
            fn.restype = ctypes.c_int
        if self.read(0x24) != ABI:
            raise RequestFailure("The owned mapping does not report the pinned AU01 ABI")

    @property
    def address(self):
        return ctypes.addressof(self.session.anchor)

    def read(self, offset):
        value = ctypes.c_uint32()
        if self.library.autonomous_read(self.address, offset, ctypes.byref(value)):
            raise RequestFailure(f"AU01 rejected host read of register 0x{offset:02x}")
        return value.value

    def start(self, prefix, max_output, deadline_ns):
        words = (ctypes.c_uint16 * len(prefix))(*prefix)
        code = self.library.autonomous_start(self.address, words, len(prefix), max_output, deadline_ns)
        if code:
            raise RequestFailure(f"AU01 did not admit the request ({code})")

    def wait(self, deadline_ns):
        event = NativeEvent()
        code = self.library.autonomous_wait(self.address, deadline_ns, ctypes.byref(event))
        if code not in (0, 1):
            raise RequestFailure(f"AU01 read failed ({code}, status 0x{event.status:x})")
        return event.token if code else None, event.observed_ns, event.status


def check_input(prefix, max_output):
    if not 1 <= len(prefix) <= CONTEXT or prefix[0] != BOS:
        raise ValueError("Expected a bounded prompt beginning with BOS")
    if any(type(token) is not int or not 0 <= token < VOCAB for token in prefix):
        raise ValueError("Invalid input token ID")
    if type(max_output) is not int or not 0 <= max_output <= MAX_OUTPUT:
        raise ValueError("Invalid maximum output count")


def call_before(method, now, deadline_ns, *args):
    remaining = deadline_ns - now()
    if remaining <= 0:
        raise RequestFailure("Native operation reached the request deadline")
    # The verified, privately loaded NativeSession passes this value to C.
    # Both stock and slice steps use the same private globals. No other
    # request runs concurrently while this one owns the UIO mapping.
    scope = method.__func__.__globals__
    if "CALL_BUDGET_NS" not in scope:
        return method(*args)
    original = scope["CALL_BUDGET_NS"]
    scope["CALL_BUDGET_NS"] = min(original, remaining)
    try:
        return method(*args)
    finally:
        scope["CALL_BUDGET_NS"] = original


def control_request(session, prefix, max_output, now, deadline_ns):
    """Use the existing score-returning step, with no score capture in the timed path."""
    for token in prefix:
        last = call_before(session.step, now, deadline_ns, token)
    room = CONTEXT - len(prefix)
    limit = min(room, max_output)
    stop = "context_limit" if room <= max_output else "output_limit"
    output, times = [], []
    for index in range(limit):
        if now() >= deadline_ns:
            raise RequestFailure("Host-controlled generation deadline elapsed", partial=output[:])
        chosen = max(range(VOCAB), key=last["logits"].__getitem__)
        if chosen == EOS:
            stop = "eos"
            break
        observed = now()
        output.append(chosen)
        if chosen >= BOS:
            stop = "non_byte_token"
            break
        times.append(observed)
        if index + 1 < limit:
            last = call_before(session.step, now, deadline_ns, chosen)
    done = now()
    if done >= deadline_ns:
        raise RequestFailure("Host-controlled completion exceeded deadline", partial=output)
    return {"output_ids": output, "output_ns": times, "stop_reason": stop,
            "done_ns": done, "context_count": session.context_count}


def finish_candidate(port, output, times, reason, observed, status):
    if status & (STATUS_FAULT | STATUS_OVERFLOW | STATUS_ACTIVE | STATUS_OUTPUT) or not status & STATUS_DONE:
        raise RequestFailure("Unexpected AU01 terminal status", partial=output)
    clocks_valid = status & (STATUS_FIRST_TIME | STATUS_LAST_TIME)
    expected_clocks = STATUS_FIRST_TIME | STATUS_LAST_TIME if times else 0
    if clocks_valid != expected_clocks or port.read(0x3c) != len(output) or port.read(0x44) != 0:
        raise RequestFailure("Invalid AU01 timing or output queue status", partial=output)
    count, scores = port.read(0x54), port.read(0x58)
    if not 1 <= count <= CONTEXT or port.read(0x20) != count or scores != VOCAB * count:
        raise RequestFailure("AU01 processed-position or score count differs", partial=output)
    legacy_status = port.read(0x00)
    if not legacy_status & 1 or legacy_status & 0x1e:
        raise RequestFailure("Core was not configured, idle and healthy at completion", partial=output)
    internal = {"done": port.read(0x50)}
    if times:
        internal.update(first=port.read(0x48), last=port.read(0x4c))
        if not 0 < internal["first"] <= internal["last"] <= internal["done"]:
            raise RequestFailure("Invalid AU01 internal cycle ordering", partial=output)
    if internal["done"] <= 0:
        raise RequestFailure("Missing AU01 completion cycle count", partial=output)
    return {"output_ids": output, "output_ns": times, "stop_reason": reason,
            "done_ns": observed, "context_count": count, "scores_consumed": scores,
            "request_cycles": internal}


def compact_request(port, prefix, max_output, deadline_ns):
    port.start(prefix, max_output, deadline_ns)
    output, times = [], []
    try:
        while True:
            token, observed, status = port.wait(deadline_ns)
            if token is None:
                break
            if len(output) >= max_output or output and output[-1] >= BOS:
                raise RequestFailure("Extra output from compact path")
            output.append(token)
            if token < BOS:
                times.append(observed)
    except RequestFailure as error:
        raise RequestFailure(str(error), partial=output) from error
    reason = STOP_CODES.get((status >> 8) & 15)
    if reason is None:
        raise RequestFailure("Missing or unknown AU01 stop reason", partial=output)
    required_nonbyte = reason == "non_byte_token"
    if bool(output and output[-1] >= BOS) != required_nonbyte:
        raise RequestFailure("AU01 non-byte terminal output disagrees with its reason", partial=output)
    return finish_candidate(port, output, times, reason, observed, status)


def complete(runner, prompt, port=None, *, max_output=MAX_OUTPUT, deadline_ns=None):
    """Compare board-CPU-observed byte delivery through a common request boundary."""
    admitted = runner.now()
    limit_ns = min(deadline_ns or admitted + DEADLINE_NS, admitted + DEADLINE_NS)
    encoded, prefix = runner.prefix(prompt, CONTEXT - 1, encoding="hex")
    check_input(prefix, max_output)

    def infer():
        if port is None:
            return control_request(runner.session, prefix, max_output, runner.now, limit_ns)
        result = compact_request(port, prefix, max_output, limit_ns)
        # The sealed native driver has not stepped this request. Its idle clear
        # reads the live context and resets its own state. The wrapper still
        # needs this observed count for resident request bookkeeping.
        runner.session.context_count = result["context_count"]
        return result

    native_clear = runner.session.clear
    with patch.object(runner.session, "clear", lambda: call_before(native_clear, runner.now, limit_ns)):
        data, timing = runner._run(infer)
    returned = runner.now()
    if returned >= limit_ns:
        raise RequestFailure("Host did not finish diagnostics within its request deadline", partial=data)
    timestamps = [admitted, timing["inference_begin_ns"], *data["output_ns"], data["done_ns"],
                  timing["inference_end_ns"], returned]
    if timestamps != sorted(timestamps) or any(a >= b for a, b in zip(data["output_ns"], data["output_ns"][1:])):
        raise RequestFailure("Request timestamps are out of order", partial=data)
    return {"prompt_hex": encoded.hex(), "prefix_ids": list(prefix), "admitted_ns": admitted,
            "returned_ns": returned, "timing": timing, **data}


def compare_reference(observed, expected):
    """Only work common to both arms after the timed delivery window."""
    wanted = {"prompt_hex": expected["prefix_utf8_hex"], "prefix_ids": expected["prefix_tokens"],
              "output_ids": expected["generated_tokens"], "stop_reason": expected["stop_reason"],
              "context_count": expected["context_count"]}
    actual = {field: observed[field] for field in wanted}
    if actual != wanted:
        raise RequestFailure("Completion differs from the exact software reference",
                             partial={"observed": actual, "expected": wanted})
    bytes_out = bytes(token for token in actual["output_ids"] if token < BOS)
    if (bytes_out.hex() != expected["byte_prefix_hex"] or len(bytes_out) != len(observed["output_ns"])):
        raise RequestFailure("Output bytes or delivery timestamps differ from the reference", partial=actual)
    return bytes_out
