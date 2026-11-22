"""Keep the sealed conditioned KV260 model loaded across independent requests."""

from contextlib import contextmanager
import hashlib
from pathlib import Path
import struct
import time
from types import SimpleNamespace

PACKAGE_SHA256 = "b0394ba256d877fb62d6eb6e74942d5ff0c649cf751d53481e827c8bae5e9167"
SEALED_RUNNER_SHA256 = "0e32bdf32ea073911ae2cfb81706aa990d71e6788dc43c87da56abca293efe64"
MODEL_PROFILE = "conditioned-hex-balanced-v1"
MODEL_WORDS = 29281
CONTEXT = 256
VOCAB = 320
BOS = 256
EOS = 257


def read_pinned(path, expected):
    data = path.read_bytes()
    if path.is_symlink() or hashlib.sha256(data).hexdigest() != expected:
        raise ValueError(f"Sealed input differs: {path.name}")
    return data


def sealed_runner(bundle):
    read_pinned(bundle / "package.json", PACKAGE_SHA256)
    path = bundle / "board_bos.py"
    data = read_pinned(path, SEALED_RUNNER_SHA256)
    source = {"__name__": "_kv260_sealed", "__file__": str(path)}
    exec(compile(data, str(path), "exec"), source)
    if source["CONDITIONED_PROFILE"] != MODEL_PROFILE:
        raise ValueError("Wrong sealed model profile")
    return source


class CountedBegin:
    """Observe the existing ctypes function without altering its ABI."""

    def __init__(self, native, audit):
        self.native = native
        self.audit = audit

    @property
    def argtypes(self):
        return self.native.argtypes

    @argtypes.setter
    def argtypes(self, value):
        self.native.argtypes = value

    @property
    def restype(self):
        return self.native.restype

    @restype.setter
    def restype(self, value):
        self.native.restype = value

    def __call__(self, *args):
        if self.audit["calls"]:
            raise RuntimeError("Unexpected second native session begin")
        self.audit["calls"] += 1
        result = self.native(*args)
        self.audit["counters"] = list(args[-1])
        return result


def observe_begin(source):
    binding = source["ctypes"]
    audit = {"calls": 0, "counters": None}

    def open_library(*args):
        library = binding.CDLL(*args)
        library.board_session_begin = CountedBegin(library.board_session_begin, audit)
        return library

    # Only this private instance of the sealed runner sees the wrapped library.
    source["ctypes"] = SimpleNamespace(**(vars(binding) | {"CDLL": open_library}))
    return audit


@contextmanager
def open_resident(bundle, *, now=time.perf_counter_ns):
    """Open one native session. Closing releases userspace resources."""
    bundle = Path(bundle)
    source = sealed_runner(bundle)
    audit = observe_begin(source)
    begin = now()
    with source["NativeSession"](bundle) as session:
        ready = now()
        if session.context_count != 0 or audit != {"calls": 1, "counters": [0, MODEL_WORDS, 0, 0, 0]}:
            raise RuntimeError("Native begin count, loaded words or initial context differ")
        yield ResidentRunner(session, source["completion_prefix"], now, begin, ready, audit)


class ResidentRunner:
    """Run requests sequentially through one open, synchronously used session."""

    def __init__(self, session, prefix, now, setup_begin, ready, audit=None):
        self.session = session
        self.prefix = prefix
        self.now = now
        self.setup = {"setup_begin_ns": setup_begin, "ready_ns": ready}
        self.begin = audit
        self.requests = 0
        self.failed = False

    def _run(self, operation):
        if self.failed:
            raise RuntimeError("Resident session has failed")
        try:
            previous = self.session.context_count
            clear = None
            if self.requests:
                if not 0 < previous <= CONTEXT:
                    raise RuntimeError("Unexpected previous context length")
                begin = self.now()
                receipt = self.session.clear()
                end = self.now()
                if receipt != {"context_count": 0, "counters": [0, MODEL_WORDS, 0, 0, 0]}:
                    raise RuntimeError("Native clear counters differ")
                clear = {"begin_ns": begin, "end_ns": end, **receipt}
            if self.session.context_count != 0:
                raise RuntimeError("Request did not start at position zero")
            begin = self.now()
            value = operation()
            end = self.now()
            timing = {"index": self.requests, "previous_context_count": previous,
                      "clear": clear, "inference_begin_ns": begin, "inference_end_ns": end}
            self.requests += 1
            return value, timing
        except BaseException:
            self.failed = True
            raise

    def complete(self, prompt, *, time_each_byte=False):
        encoded, prefix = self.prefix(prompt, CONTEXT - 1, encoding="hex")
        byte_times = [] if time_each_byte else None

        def infer():
            frames, decisions, generated = [], [], []
            limit = CONTEXT - len(prefix)
            stopped = "context_limit"
            first = eos = None

            def step(token, phase):
                frame = self.session.step(token)
                frame.update(frame_index=len(frames), input_token=token, phase=phase)
                frames.append(frame)
                return frame

            for token in prefix:
                last = step(token, "prefix")
            for index in range(limit):
                chosen = max(range(VOCAB), key=last["logits"].__getitem__)
                if chosen == EOS:
                    eos = self.now()
                elif chosen < BOS and (first is None or byte_times is not None):
                    selected = self.now()
                    if first is None:
                        first = selected
                    if byte_times is not None:
                        byte_times.append(selected)
                decisions.append({"frame_index": last["frame_index"], "token": chosen})
                if chosen == EOS:
                    stopped = "eos"
                    break
                generated.append(chosen)
                if chosen > 255:
                    stopped = "non_byte_token"
                    break
                if index + 1 < limit:
                    last = step(chosen, "generation")
            return frames, decisions, generated, stopped, first, eos

        (frames, decisions, generated, stopped, first, eos), timing = self._run(infer)
        timing.update(first_byte_ns=first, eos_ns=eos)
        if byte_times is not None:
            timing["emitted_byte_ns"] = byte_times
        hash_frames(frames)
        byte_ids = generated[:-1] if stopped == "non_byte_token" else generated
        raw = bytes(byte_ids)
        text = None
        if len(byte_ids) == len(generated):
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                pass
        return {"timing": timing, "completion": {
            "hardware_accepted": True, "model_profile": MODEL_PROFILE,
            "input_encoding": "hex", "answer_marker": False, "sampling_performed": False,
            "max_new_tokens": CONTEXT - 1, "context_limit": CONTEXT, "context_count": self.session.context_count,
            "prefix_text": prompt, "prefix_utf8_hex": encoded.hex(), "prefix_tokens": prefix,
            "input_tokens": [frame["input_token"] for frame in frames], "generated_tokens": generated,
            "continuation_text": text, "valid_utf8_bytes": text is not None,
            "continuation_bytes_hex": raw.hex() if len(byte_ids) == len(generated) else None,
            "byte_prefix_hex": raw.hex(), "eos": stopped == "eos", "stop_reason": stopped,
            "frames": frames, "decisions": decisions,
        }}

    def score_sequence(self, tokens):
        """Feed a fixed token sequence through the same request boundary."""
        if (not 1 <= len(tokens) <= CONTEXT or tokens[0] != BOS
                or any(type(token) is not int or not 0 <= token < VOCAB for token in tokens)):
            raise ValueError("Expected 1–256 valid token IDs beginning with BOS")
        frames, timing = self._run(lambda: [self.session.step(token) for token in tokens])
        for token, frame in zip(tokens, frames, strict=True):
            frame["input_token"] = token
        hash_frames(frames)
        return {"timing": timing, "frames": frames, "context_count": self.session.context_count}


def hash_frames(frames):
    for frame in frames:
        frame["logits_sha256"] = hashlib.sha256(struct.pack("<320i", *frame["logits"])).hexdigest()
