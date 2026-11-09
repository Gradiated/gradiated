from __future__ import annotations

import asyncio
import dataclasses
import json
import math
import random
import statistics
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Sequence

# Longest a response may go silent before the client gives up: past any supported request deadline
# (the GLM runtime allows 900 s), so a non-streaming request that production let run is measured.
READ_TIMEOUT_S = 1800


@dataclass(frozen=True)
class Phase:
    users: int
    prompt_tokens: int
    output_tokens: int
    seconds: float
    shared_prefix: float = 0.0
    name: str = ""


@dataclass
class RequestRecord:
    start: float
    ttft: float | None = None
    tokens: int = 0
    decode_tps: float | None = None
    error: str | None = None
    cut: bool = False
    warmup: bool = False  # loads the server as production was loaded; never measured
    untimed: bool = False  # a non-streaming response without the server's per-request timings
    end: float | None = None  # when the response finished, on the same clock as start


@dataclass
class PhaseResult:
    phase: Phase
    requests: list[RequestRecord] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        measured = [r for r in self.requests if not r.warmup]
        done = [r for r in measured if r.error is None and r.tokens and not r.cut]
        ttfts = sorted(r.ttft for r in done if r.ttft is not None)
        # A response that arrived in one chunk completed, but has no measurable decode rate.
        rates = sorted(r.decode_tps for r in done if r.decode_tps)
        tokens = sum(r.tokens for r in measured)

        def pct(values: list[float], q: float) -> float | None:
            # Nearest-rank percentile: the smallest value with at least q of the samples at or below it.
            return values[max(math.ceil(q * len(values)) - 1, 0)] if values else None

        return {
            "phase": asdict(self.phase),
            "completed": len(done),
            "errors": sum(r.error is not None for r in measured),
            "untimed": sum(r.untimed for r in done),
            "tps_per_user_p50": statistics.median(rates) if rates else None,
            "tps_per_user_p10": pct(rates, 0.1),
            "ttft_p50": pct(ttfts, 0.5),
            "ttft_p90": pct(ttfts, 0.9),
            "output_tps": tokens / self.phase.seconds if self.phase.seconds else 0.0,
        }


class PromptSource:
    def __init__(self, corpus: Sequence[int], seed: int = 0) -> None:
        if len(corpus) < 1024:
            raise ValueError("corpus is too small")
        self.corpus = list(corpus)
        self.rng = random.Random(seed)

    def prompt(self, length: int, shared: float, shared_seed: int) -> list[int]:
        if not 0.0 <= shared <= 1.0:
            raise ValueError(f"shared_prefix must be in [0, 1], got {shared}")
        shared_len = int(length * shared)
        if shared_len >= len(self.corpus):
            raise ValueError(f"shared prefix of {shared_len} tokens needs a corpus longer than {len(self.corpus)} tokens")
        prefix_start = random.Random(shared_seed).randrange(len(self.corpus) - shared_len) if shared_len else 0
        prefix = self.corpus[prefix_start : prefix_start + shared_len]
        tail = []
        while len(tail) < length - shared_len:
            start = self.rng.randrange(len(self.corpus) - 256)
            tail.extend(self.corpus[start : start + 256])
        return prefix + tail[: length - shared_len]

    def family_prompt(self, length: int, shared_len: int, family: str | None, ancestors: Sequence[tuple[int, str]] = ()) -> list[int]:
        """A prompt whose first shared_len tokens follow its prefix families, at any length.

        ``ancestors`` are (depth, key) pairs for every shared family depth, shallowest first. Tokens up
        to each depth come from that depth's key, so requests that share only a shallower ancestor
        still share those tokens; the rest of the shared prefix comes from ``family``.
        """
        shared_len = min(shared_len, length) if family else 0
        prefix: list[int] = []
        for depth, key in [*ancestors, (shared_len, family)]:
            end = min(depth, shared_len)
            if end > len(prefix):
                # Read the corpus cyclically from a point fixed by the key, so a segment is the same
                # for every request that has the key, however long the request is.
                start = random.Random(key).randrange(len(self.corpus))
                prefix += [self.corpus[(start + i) % len(self.corpus)] for i in range(len(prefix), end)]
        tail: list[int] = []
        while len(tail) < length - shared_len:
            begin = self.rng.randrange(len(self.corpus) - 256)
            tail.extend(self.corpus[begin : begin + 256])
        return prefix + tail[: length - shared_len]


async def _one(session: Any, url: str, ids: list[int], output_tokens: int, record: RequestRecord, temperature: float = 0.7,
               priority: int | None = None, seed: int | None = None, sampling: dict[str, float] | None = None, logprobs: int = -1,
               stream: bool = True, logprob_start: int = -1, max_new_tokens: int | None = None, hidden_states: bool = False,
               server_stop: bool = False) -> None:
    # Declared limit as production sent it (admission and KV headroom use it). An early stop is
    # reproduced at the observed output_tokens: by the server where it supports replay stops,
    # exactly; otherwise by cutting the stream, which a non-streaming request cannot do, so it asks
    # for exactly what it produced.
    declared = max(max_new_tokens or output_tokens, output_tokens)
    budget = declared if stream or server_stop else output_tokens
    body: dict[str, Any] = {
        "input_ids": ids,
        "sampling_params": {"max_new_tokens": budget, "temperature": temperature, "ignore_eos": True},
        "stream": stream,
    }
    if server_stop and budget > output_tokens:
        body["sampling_params"]["custom_params"] = {"livetune_stop_after": output_tokens}
    if hidden_states:
        body["return_hidden_states"] = True
    if priority is not None:
        body["priority"] = priority  # recorded admission priority, so priority scheduling is replayed too
    if seed is not None:
        body["sampling_params"]["sampling_seed"] = seed
    for key, value in (sampling or {}).items():
        body["sampling_params"][key] = int(value) if key in ("top_k", "min_new_tokens", "stream_interval", "sampling_seed") else value
    if logprobs >= 0:
        body["return_logprob"] = True
        body["top_logprobs_num"] = logprobs
        if logprob_start >= 0:
            body["logprob_start_len"] = logprob_start  # prompt logprobs from here, as recorded
    first = last = None
    first_tokens = 0
    try:
        async with session.post(f"{url}/generate", json=body) as response:
            if response.status != 200:
                record.error = f"http {response.status}: {(await response.text())[:200]}"
                return
            if not stream:
                # One response at the end. With --enable-metrics SGLang reports its own first-token
                # latency and decode rate for the request, so it is judged like a streamed one.
                payload = await response.json()
                meta = payload.get("meta_info", {})
                record.tokens = int(meta.get("completion_tokens", 0))
                record.ttft = meta.get("first_token_latency")
                record.decode_tps = meta.get("decode_throughput")
                record.untimed = record.ttft is None
                return
            async for raw in response.content:
                line = raw.decode().strip()
                if not line.startswith("data:") or line == "data: [DONE]":
                    continue
                payload = json.loads(line[5:])
                if "error" in payload:
                    record.error = f"stream error: {str(payload['error'])[:200]}"
                    return
                now = time.perf_counter()
                tokens = payload.get("meta_info", {}).get("completion_tokens", record.tokens + 1)
                if tokens > record.tokens:
                    if first is None:
                        first = now
                        record.ttft = now - record.start
                        # A chunk can carry several tokens (stream_interval, speculative decoding);
                        # only tokens after the first chunk have a measured decode time.
                        first_tokens = tokens
                    last, record.tokens = now, tokens
                    if budget > output_tokens and tokens >= output_tokens and not server_stop:
                        break  # closing the stream aborts the request, as the recorded stop did
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # network errors are data, not crashes
        record.error = f"{type(exc).__name__}: {exc}"
    finally:
        record.end = last if last is not None else time.perf_counter()
        if first is not None and record.tokens > first_tokens and last > first:
            record.decode_tps = (record.tokens - first_tokens) / (last - first)


async def run_phase(url: str, phase: Phase, prompts: PromptSource, phase_index: int = 0) -> PhaseResult:
    import aiohttp

    result = PhaseResult(phase)
    deadline = time.perf_counter() + phase.seconds
    timeout = aiohttp.ClientTimeout(total=None, sock_read=READ_TIMEOUT_S)
    connector = aiohttp.TCPConnector(limit=0)
    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:

        async def user(index: int) -> None:
            while time.perf_counter() < deadline:
                ids = prompts.prompt(phase.prompt_tokens, phase.shared_prefix, shared_seed=phase_index)
                record = RequestRecord(time.perf_counter())
                result.requests.append(record)
                try:
                    # Requests still running at the deadline are cut off; their tokens so far count.
                    await asyncio.wait_for(_one(session, url, ids, phase.output_tokens, record), deadline - time.perf_counter())
                except TimeoutError:
                    record.cut = True
                    return
                if record.error:
                    await asyncio.sleep(1.0)

        await asyncio.gather(*(user(i) for i in range(phase.users)))
    return result


def warm_prefixes(arrivals: Sequence[Any], ids_for: Sequence[list[int]]) -> list[list[int]]:
    """Prefixes production already had cached when the window began.

    A request whose recorded hit no request in the window explains hit something cached before it;
    prewarming exactly that prefix reproduces the hit from a flushed cache. Another request explains
    a hit only if, in production, its prefill finished before this one looked up the cache: arriving
    earlier is not enough while it is still queued.
    """
    def keys(arrival: Any) -> list[tuple[int, str]]:
        own = [(arrival.shared_tokens, arrival.family)] if arrival.family else []
        return [(depth, key) for depth, key in getattr(arrival, "ancestors", ())] + own

    def scheduled(arrival: Any) -> float:
        value = getattr(arrival, "scheduled_s", None)
        return arrival.at if value is None else value

    def prefilled(arrival: Any) -> float:
        value = getattr(arrival, "prefilled_s", None)
        return arrival.at if value is None else value

    order = sorted(range(len(arrivals)), key=lambda i: scheduled(arrivals[i]))
    ready = sorted(range(len(arrivals)), key=lambda i: prefilled(arrivals[i]))
    covered: dict[str, int] = {}
    warm = []
    done = 0
    for i in order:
        arrival, ids = arrivals[i], ids_for[i]
        # Every prefix a request shares, ancestors included, is cached once its prefill finishes.
        while done < len(ready) and prefilled(arrivals[ready[done]]) <= scheduled(arrival) and ready[done] != i:
            other = arrivals[ready[done]]
            for depth, key in keys(other):
                covered[key] = max(covered.get(key, 0), min(depth, other.shared_tokens))
            done += 1
        cached = min(getattr(arrival, "cached_tokens", 0), len(ids))
        if cached and not any(covered.get(key, 0) >= cached for _, key in keys(arrival)):
            warm.append(ids[:cached])
    return warm


async def _prewarm(session: Any, url: str, arrivals: Sequence[Any], ids_for: Sequence[list[int]], parallel: int = 8) -> None:
    """Every candidate must start from the same cache, so a warmup that fails is retried alone and then fatal."""
    gate = asyncio.Semaphore(parallel)

    async def one(ids: list[int]) -> bool:
        async with gate:
            body = {"input_ids": ids, "sampling_params": {"max_new_tokens": 1, "temperature": 0}}
            async with session.post(f"{url}/generate", json=body) as response:
                await response.read()
                return response.status == 200

    prefixes = warm_prefixes(arrivals, ids_for)
    results = await asyncio.gather(*(one(ids) for ids in prefixes))
    gate = asyncio.Semaphore(1)  # a low queue limit under test can reject concurrent warmups
    for ids, ok in zip(prefixes, results):
        if not ok and not await one(ids):
            raise RuntimeError(f"could not prewarm a {len(ids)}-token prefix; the candidates would start from different caches")


def trace_prompts(arrivals: Sequence[Any], prompts: PromptSource) -> list[list[int]]:
    """The token ids for each arrival, built once so every replay of a trace sends the same content."""
    return [prompts.family_prompt(a.prompt_tokens, a.shared_tokens, a.family, getattr(a, "ancestors", ())) for a in arrivals]


def prewarm(url: str, arrivals: Sequence[Any], ids_for: Sequence[list[int]]) -> None:
    """Load the prefixes production had cached before the window, ahead of a replay that skips its own prewarm."""
    if not warm_prefixes(arrivals, ids_for):
        return
    import aiohttp

    async def go() -> None:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=None, sock_read=READ_TIMEOUT_S)) as session:
            await _prewarm(session, url, arrivals, ids_for)

    asyncio.run(go())


async def run_arrivals(url: str, arrivals: Sequence[Any], prompts: PromptSource | Sequence[list[int]], name: str = "trace",
                       warm: bool = True, server_stops: bool = False) -> PhaseResult:
    """Open loop: each recorded request arrives at its own time, whatever the server is doing.

    With server_stops, early-stopped requests are finished by the server at their recorded length.
    """
    import aiohttp

    from livetune.trace import concurrency, observed_cache_hit

    span = max((a.at for a in arrivals), default=0.0)
    measured = [a for a in arrivals if not getattr(a, "warmup", False)]
    phase = Phase(
        # Open loop has no user count; the demand the trace produced stands in for it.
        users=concurrency(arrivals) if arrivals else 0,
        prompt_tokens=int(statistics.median(a.prompt_tokens for a in measured)) if measured else 0,
        output_tokens=int(statistics.median(a.output_tokens for a in measured)) if measured else 0,
        seconds=span,
        # Recorded so `policy --trials` rebuilds the same profile, and the same cache-hit guard.
        shared_prefix=observed_cache_hit(arrivals) if arrivals else 0.0,
        name=name,
    )
    result = PhaseResult(phase)
    timeout = aiohttp.ClientTimeout(total=None, sock_read=READ_TIMEOUT_S)
    ids_for = trace_prompts(arrivals, prompts) if isinstance(prompts, PromptSource) else list(prompts)
    async with aiohttp.ClientSession(timeout=timeout, connector=aiohttp.TCPConnector(limit=0)) as session:
        if warm:
            await _prewarm(session, url, arrivals, ids_for)
        started = time.perf_counter()

        async def send(arrival: Any, ids: list[int]) -> None:
            await asyncio.sleep(max(arrival.at - (time.perf_counter() - started), 0.0))
            record = RequestRecord(time.perf_counter(), warmup=getattr(arrival, "warmup", False))
            result.requests.append(record)
            temperature = 0.7 if arrival.temperature is None else arrival.temperature
            # Only the seed production sent: on some runtimes a seed changes the decoding path (Kimi's
            # DFLASH turns off), so an unseeded request stays unseeded, at the cost of sampling noise.
            await _one(session, url, ids, arrival.output_tokens, record, temperature, getattr(arrival, "priority", None), None,
                       getattr(arrival, "sampling", None), getattr(arrival, "logprobs", -1),
                       getattr(arrival, "stream", True), getattr(arrival, "logprob_start", -1), getattr(arrival, "max_new_tokens", None),
                       getattr(arrival, "hidden_states", False), server_stops)

        await asyncio.gather(*(send(a, ids) for a, ids in zip(arrivals, ids_for)))
    # Every request runs to completion, so the phase lasts until the last measured one finishes; a
    # warm-up still decoding after that is awaited but does not stretch the measured time.
    ends = [r.end for r in result.requests if not r.warmup and r.end is not None]
    finished = max(ends) if ends else time.perf_counter()
    result.phase = dataclasses.replace(phase, seconds=finished - started)
    return result


def run(url: str, phases: Sequence[Phase], prompts: PromptSource, log: Any = print) -> list[dict[str, Any]]:
    out = []
    for index, phase in enumerate(phases):
        started = time.time()
        summary = asyncio.run(run_phase(url, phase, prompts, index)).summary()
        summary["started"] = started
        log(json.dumps(summary))
        out.append(summary)
    return out
