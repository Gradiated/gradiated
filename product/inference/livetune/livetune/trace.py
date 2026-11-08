"""Per-request traffic records: what the server saw, without what users wrote.

A record holds lengths, cache hits, timings, sampling features and keyed hashes of prompt
prefixes. It never holds text or token ids. Prefix keys are BLAKE2b digests keyed by
``LIVETUNE_TRACE_KEY`` (hex), or a random key kept in the trace directory, so a key groups requests that
share a prefix without revealing the prefix and without linking across deployments that
use different keys.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import statistics
import time
from array import array
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

# Prefix depths, in tokens, that name a request's prefix family: the system prompt, then deeper shared context.
FAMILY_DEPTHS = (256, 2048, 16384)


@dataclass(frozen=True)
class Record:
    t: float  # wall-clock completion time
    prompt_tokens: int
    cached_tokens: int
    output_tokens: int
    queue_s: float | None  # time in the waiting queue, summed over re-entries
    ttft_s: float | None  # scheduler arrival to first token
    decode_s: float | None  # first token to completion
    finish: str  # "length", "stop", "abort", ...
    retractions: int = 0
    spec_accept: float | None = None  # mean accepted tokens per verify step
    temperature: float | None = None
    max_new_tokens: int | None = None
    constrained: bool = False  # json schema, regex or grammar
    priority: int | None = None
    lora: bool = False
    session: bool = False
    families: tuple[str, ...] = ()  # keyed prefix hashes at FAMILY_DEPTHS that the prompt reaches
    cached_family: str | None = None  # keyed hash of the cached prefix
    cached_family_tokens: int = 0  # how many tokens that hash covers: the cached prefix rounded down to whole pages
    sampling: dict[str, float] = field(default_factory=dict)  # sampling parameters that differ from SGLang's defaults
    logprobs: int = -1  # -1 none; otherwise logprobs were requested, with this many top alternatives

    @property
    def decode_tps(self) -> float | None:
        return (self.output_tokens - 1) / self.decode_s if self.decode_s and self.output_tokens > 1 else None

    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"))

    @classmethod
    def from_json(cls, line: str) -> "Record":
        data = json.loads(line)
        data["families"] = tuple(data.get("families", ()))
        return cls(**{key: value for key, value in data.items() if key in cls.__dataclass_fields__})


class PrefixKeys:
    def __init__(self, key: bytes | None = None, directory: str | Path | None = None) -> None:
        env = os.environ.get("LIVETUNE_TRACE_KEY")
        self.key = key or (bytes.fromhex(env) if env else (_directory_key(Path(directory)) if directory else os.urandom(32)))

    def digest(self, ids: Sequence[int], length: int) -> str:
        head = ids[:length]
        data = head.tobytes() if isinstance(head, array) and head.typecode == "q" else array("q", head).tobytes()
        return hashlib.blake2b(data, key=self.key[:64], digest_size=8).hexdigest()

    def families(self, ids: Sequence[int]) -> tuple[str, ...]:
        return tuple(self.digest(ids, depth) for depth in FAMILY_DEPTHS if len(ids) >= depth)


def _directory_key(directory: Path) -> bytes:
    """One key per trace directory: schedulers that share it hash prefixes alike, other deployments differ.

    The first process to arrive creates it exclusively; the rest read it. It is as sensitive as the
    traces it keys, so it is readable by the owner only.
    """
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / ".trace-key"
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        for _ in range(50):  # the creator may not have written it yet
            key = bytes.fromhex(path.read_text().strip() or "00")
            if len(key) == 32:
                return key
            time.sleep(0.05)
        raise ValueError(f"{path} does not hold a 32-byte hex key")
    key = os.urandom(32)
    with os.fdopen(fd, "w") as handle:
        handle.write(key.hex())
    return key


class Writer:
    """Appends records as JSON lines, rotating files so a busy server keeps a bounded tail."""

    def __init__(self, directory: str | Path, max_bytes: int = 64 << 20, keep: int = 8, flush_s: float = 1.0) -> None:
        self.directory = Path(directory)
        # Records are Confidential usage data: the directory and files are for the owner only.
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.max_bytes, self.keep, self.flush_s = max_bytes, keep, flush_s
        self.written = 0
        self._open()

    def _open(self) -> None:
        # Names sort in write order, which retention and readers rely on.
        self.path = self.directory / f"trace-{time.strftime('%Y%m%dT%H%M%S')}-{os.getpid()}-{self.written:012d}.jsonl"
        self.handle = os.fdopen(os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600), "a", buffering=1 << 16)
        self.bytes, self.last_flush = 0, time.monotonic()

    def write(self, record: Record) -> None:
        line = record.to_json() + "\n"
        self.handle.write(line)
        self.bytes += len(line)
        self.written += 1
        if time.monotonic() - self.last_flush >= self.flush_s:
            self.handle.flush()
            self.last_flush = time.monotonic()
        if self.bytes >= self.max_bytes:
            self.handle.close()
            self._prune()
            self._open()

    def _prune(self) -> None:
        # Several schedulers can share the directory (data parallelism) and restarted ones leave files
        # behind. Keep this writer's newest files, and the newest files of writers that have exited;
        # never touch a live writer's files, which it may still be appending to.
        mine, exited = [], []
        for path in sorted(self.directory.glob("trace-*.jsonl")):
            pid = _writer_pid(path)
            if pid == os.getpid():
                mine.append(path)
            elif pid is not None and not _alive(pid):
                exited.append(path)
        for old in mine[: -self.keep + 1 or None] + exited[: -self.keep or None]:
            old.unlink(missing_ok=True)

    def close(self) -> None:
        self.handle.close()


def _writer_pid(path: Path) -> int | None:
    parts = path.stem.split("-")
    return int(parts[2]) if len(parts) == 4 and parts[2].isdigit() else None


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def read(paths: Iterable[str | Path], since: float = 0.0) -> Iterator[Record]:
    for path in paths:
        path = Path(path)
        files = sorted(path.glob("trace-*.jsonl")) if path.is_dir() else [path]
        for file in files:
            with file.open() as handle:
                for line in handle:
                    if line.strip():
                        record = Record.from_json(line)
                        if record.t >= since:
                            yield record


def _pct(values: Sequence[float], q: float) -> float | None:
    ordered = sorted(values)
    return ordered[max(math.ceil(q * len(ordered)) - 1, 0)] if ordered else None


def _band(prompt_tokens: int) -> str:
    for edge, name in ((1024, "<1k"), (4096, "1-4k"), (16384, "4-16k"), (65536, "16-64k")):
        if prompt_tokens < edge:
            return name
    return ">=64k"


def shared_families(records: Sequence[Record]) -> list[tuple[str, int] | None]:
    """Each record's family: the deepest fixed-depth prefix hash it shares with another record, and that depth.

    Requests of different lengths reach different depths, so a long and a short prompt that share
    their first 2,048 tokens are grouped at 2,048 rather than split at the long one's deepest hash.
    """
    counts = Counter(key for r in records for key in r.families)
    out: list[tuple[str, int] | None] = []
    for r in records:
        shared = [(key, FAMILY_DEPTHS[i]) for i, key in enumerate(r.families) if counts[key] > 1]
        out.append(shared[-1] if shared else None)
    return out


def summarize(records: Sequence[Record]) -> dict[str, Any]:
    """The traffic mix: what to tune for and what to propose."""
    if not records:
        return {"requests": 0}
    span = max(r.t for r in records) - min(r.t for r in records)
    prompt = [r.prompt_tokens for r in records]
    output = [r.output_tokens for r in records]
    prompt_total = sum(prompt)
    by_band: dict[str, list[Record]] = defaultdict(list)
    for r in records:
        by_band[_band(r.prompt_tokens)].append(r)
    family_counts = Counter(found[0] for found in shared_families(records) if found is not None)
    shared = sum(family_counts.values())
    rates = [r.decode_tps for r in records if r.decode_tps]
    return {
        "requests": len(records),
        "seconds": round(span, 1),
        "arrival_rps": round(len(records) / span, 3) if span > 0 else None,
        "prompt_tokens": {"p50": _pct(prompt, 0.5), "p90": _pct(prompt, 0.9), "max": max(prompt)},
        "output_tokens": {"p50": _pct(output, 0.5), "p90": _pct(output, 0.9), "max": max(output)},
        "cache_hit": round(sum(r.cached_tokens for r in records) / prompt_total, 3) if prompt_total else None,
        "uncached_tokens_per_s": round((prompt_total - sum(r.cached_tokens for r in records)) / span, 1) if span > 0 else None,
        "bands": {
            band: {
                "share": round(len(rs) / len(records), 3),
                "cache_hit": round(sum(r.cached_tokens for r in rs) / max(sum(r.prompt_tokens for r in rs), 1), 3),
                "output_p50": _pct([r.output_tokens for r in rs], 0.5),
                "ttft_p90": _pct([r.ttft_s for r in rs if r.ttft_s is not None], 0.9),
                "decode_tps_p50": _pct([r.decode_tps for r in rs if r.decode_tps], 0.5),
            }
            for band, rs in sorted(by_band.items())
        },
        "families": {
            "distinct": len(family_counts),
            "requests_sharing": round(shared / len(records), 3),
            "top_shares": [round(count / len(records), 3) for _, count in family_counts.most_common(5)],
        },
        "queue_s_p90": _pct([r.queue_s for r in records if r.queue_s is not None], 0.9),
        "ttft_s_p90": _pct([r.ttft_s for r in records if r.ttft_s is not None], 0.9),
        "decode_tps_p50": statistics.median(rates) if rates else None,
        "finish": dict(Counter(r.finish for r in records)),
        "retracted_share": round(sum(r.retractions > 0 for r in records) / len(records), 4),
        "constrained_share": round(sum(r.constrained for r in records) / len(records), 3),
        "lora_share": round(sum(r.lora for r in records) / len(records), 3),
        "greedy_share": round(sum(r.temperature == 0 for r in records) / len(records), 3),
        "spec_accept_p50": _pct([r.spec_accept for r in records if r.spec_accept], 0.5),
    }


@dataclass(frozen=True)
class Arrival:
    """One request to replay: when it arrives and its shape, with prefix sharing kept by family."""

    at: float
    prompt_tokens: int
    output_tokens: int
    shared_tokens: int
    family: str | None
    temperature: float | None
    seconds: float = 0.0  # recorded server time, first scheduling to completion
    cached_tokens: int = 0  # what production actually hit, for the cache-hit guard of a tuned rule
    priority: int | None = None
    ancestors: tuple[tuple[int, str], ...] = ()
    sampling: dict[str, float] = field(default_factory=dict)
    logprobs: int = -1  # (depth, key) of every shared family depth, shallowest first


def replay_gaps(records: Sequence[Record]) -> dict[str, int]:
    """Request modes replay cannot reproduce, with their counts: synthetic requests carry no grammar,
    adapter or session, and those change what a request costs."""
    gaps = {
        "constrained": sum(r.constrained for r in records),
        "lora": sum(r.lora for r in records),
        "session": sum(r.session for r in records),
    }
    return {mode: count for mode, count in gaps.items() if count}


def observed_cache_hit(schedule: Sequence[Arrival]) -> float:
    prompt = sum(a.prompt_tokens for a in schedule)
    return round(sum(a.cached_tokens for a in schedule) / prompt, 3) if prompt else 0.0


def concurrency(schedule: Sequence[Arrival], q: float = 0.9) -> int:
    """The q-quantile over time of requests in flight, as a gauge sampled at random moments would see it.

    Each level counts for as long as it lasted, so a brief burst does not outweigh a long quiet span.
    """
    events = sorted([(a.at, 1) for a in schedule] + [(a.at + a.seconds, -1) for a in schedule])
    level, held = 0, Counter()
    for (t, step), following in zip(events, events[1:] + [events[-1]] if events else []):
        level += step
        held[level] += following[0] - t
    total = sum(held.values())
    if total <= 0:
        return 1
    seen = 0.0
    for value in sorted(held):
        seen += held[value]
        if seen >= q * total:
            return max(value, 1)
    return max(max(held), 1)


def arrivals(records: Sequence[Record], speed: float = 1.0) -> list[Arrival]:
    """An open-loop replay schedule; arrival time is completion minus the request's server time.

    A family is the deepest fixed-depth prefix hash that several requests share, so every member,
    including the cold first one, carries the same prefix. Its length is only what is proven common:
    that depth, or a longer cached prefix whose hash two or more members share. A single member's
    cache hit may come from a request outside the trace, so it proves nothing about the others.
    """
    if not records:
        return []
    unreproducible = replay_gaps(records)
    if unreproducible:
        raise ValueError(f"trace replay cannot reproduce these request modes: {unreproducible}")

    def started(r: Record) -> float:
        return r.t - sum(x or 0.0 for x in (r.ttft_s, r.decode_s))

    # A request aborted before its first token never ran on the GPU; one aborted later did, for the
    # tokens it produced, which replay reproduces by generating exactly that many.
    records = [r for r in records if not (r.finish == "abort" and r.output_tokens == 0)]
    if not records:
        return []
    families = shared_families(records)
    cached_counts = Counter(r.cached_family for r in records if r.cached_family)
    proven_cached: dict[str, int] = {}
    for r in records:
        if r.cached_family and cached_counts[r.cached_family] > 1:
            # Only the hashed pages are proven common; the remainder of a partial page is not.
            hashed = r.cached_family_tokens or r.cached_tokens
            proven_cached[r.cached_family] = min(proven_cached.get(r.cached_family, hashed), hashed)
    counts = Counter(key for r in records for key in r.families)

    def prefix(r: Record, found: tuple[str, int] | None) -> tuple[int, str | None]:
        # The fixed-depth family is shared by all its members; a deeper cached prefix only by the
        # subgroup whose cached hash matches, so it extends theirs alone.
        depth, key = (found[1], found[0]) if found else (0, None)
        proven = proven_cached.get(r.cached_family, 0) if r.cached_family else 0
        return (proven, r.cached_family) if proven > depth else (depth, key)

    t0 = min(started(r) for r in records)
    out = []
    for r, found in zip(records, families):
        ancestors = tuple((FAMILY_DEPTHS[i], key) for i, key in enumerate(r.families) if counts[key] > 1)
        shared, family = prefix(r, found)
        out.append(
            Arrival(
                at=(started(r) - t0) / speed,
                prompt_tokens=r.prompt_tokens,
                output_tokens=max(r.output_tokens, 1),
                shared_tokens=min(shared, r.prompt_tokens),
                family=family,
                temperature=r.temperature,
                # Only arrivals are compressed: requests still take their recorded time on the server.
                seconds=sum(x or 0.0 for x in (r.ttft_s, r.decode_s)),
                cached_tokens=r.cached_tokens,
                priority=r.priority,
                ancestors=ancestors,
                sampling=dict(r.sampling),
                logprobs=r.logprobs,
            )
        )
    return sorted(out, key=lambda a: a.at)


@dataclass
class BatchStats:
    """Cumulative per-forward-batch counters, read as deltas over a window like Prometheus counters."""

    counts: dict[str, float] = field(default_factory=lambda: defaultdict(float))

    def add(self, mode: str, requests: int, tokens: int, graph: bool, seconds: float | None) -> None:
        c = self.counts
        c[f"{mode}_batches"] += 1
        c[f"{mode}_requests"] += requests
        c[f"{mode}_tokens"] += tokens
        if graph:
            c[f"{mode}_graph_batches"] += 1
        if seconds is not None and seconds >= 0:
            c[f"{mode}_seconds"] += seconds

    def snapshot(self) -> dict[str, float]:
        return {key: round(value, 6) for key, value in sorted(self.counts.items())}


def batch_deltas(earlier: Mapping[str, float], later: Mapping[str, float]) -> dict[str, float]:
    return {key: later[key] - earlier.get(key, 0.0) for key in later}
