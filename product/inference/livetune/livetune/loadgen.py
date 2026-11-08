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


@dataclass
class PhaseResult:
    phase: Phase
    requests: list[RequestRecord] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        done = [r for r in self.requests if r.error is None and r.tokens and not r.cut]
        ttfts = sorted(r.ttft for r in done if r.ttft is not None)
        # A response that arrived in one chunk completed, but has no measurable decode rate.
        rates = sorted(r.decode_tps for r in done if r.decode_tps)
        tokens = sum(r.tokens for r in self.requests)

        def pct(values: list[float], q: float) -> float | None:
            # Nearest-rank percentile: the smallest value with at least q of the samples at or below it.
            return values[max(math.ceil(q * len(values)) - 1, 0)] if values else None

        return {
            "phase": asdict(self.phase),
            "completed": len(done),
            "errors": sum(r.error is not None for r in self.requests),
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

    def family_prompt(self, length: int, shared_len: int, family: str | None) -> list[int]:
        """A prompt whose first shared_len tokens are the same for every request of the family, at any length."""
        shared_len = min(shared_len, length) if family else 0
        start = random.Random(family).randrange(len(self.corpus)) if shared_len else 0
        # Read the corpus cyclically so a family's prefix does not depend on how long it is.
        prefix = [self.corpus[(start + i) % len(self.corpus)] for i in range(shared_len)]
        tail: list[int] = []
        while len(tail) < length - shared_len:
            begin = self.rng.randrange(len(self.corpus) - 256)
            tail.extend(self.corpus[begin : begin + 256])
        return prefix + tail[: length - shared_len]


async def _one(session: Any, url: str, ids: list[int], output_tokens: int, record: RequestRecord, temperature: float = 0.7, priority: int | None = None) -> None:
    body: dict[str, Any] = {
        "input_ids": ids,
        "sampling_params": {"max_new_tokens": output_tokens, "temperature": temperature, "ignore_eos": True},
        "stream": True,
    }
    if priority is not None:
        body["priority"] = priority  # recorded admission priority, so priority scheduling is replayed too
    first = last = None
    first_tokens = 0
    try:
        async with session.post(f"{url}/generate", json=body) as response:
            if response.status != 200:
                record.error = f"http {response.status}: {(await response.text())[:200]}"
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
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # network errors are data, not crashes
        record.error = f"{type(exc).__name__}: {exc}"
    finally:
        if first is not None and record.tokens > first_tokens and last > first:
            record.decode_tps = (record.tokens - first_tokens) / (last - first)


async def run_phase(url: str, phase: Phase, prompts: PromptSource, phase_index: int = 0) -> PhaseResult:
    import aiohttp

    result = PhaseResult(phase)
    deadline = time.perf_counter() + phase.seconds
    timeout = aiohttp.ClientTimeout(total=None, sock_read=600)
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


def trace_prompts(arrivals: Sequence[Any], prompts: PromptSource) -> list[list[int]]:
    """The token ids for each arrival, built once so every replay of a trace sends the same content."""
    return [prompts.family_prompt(a.prompt_tokens, a.shared_tokens, a.family) for a in arrivals]


async def run_arrivals(url: str, arrivals: Sequence[Any], prompts: PromptSource | Sequence[list[int]], name: str = "trace") -> PhaseResult:
    """Open loop: each recorded request arrives at its own time, whatever the server is doing."""
    import aiohttp

    from livetune.trace import concurrency, observed_cache_hit

    span = max((a.at for a in arrivals), default=0.0)
    phase = Phase(
        # Open loop has no user count; the demand the trace produced stands in for it.
        users=concurrency(arrivals) if arrivals else 0,
        prompt_tokens=int(statistics.median(a.prompt_tokens for a in arrivals)) if arrivals else 0,
        output_tokens=int(statistics.median(a.output_tokens for a in arrivals)) if arrivals else 0,
        seconds=span,
        # Recorded so `policy --trials` rebuilds the same profile, and the same cache-hit guard.
        shared_prefix=observed_cache_hit(arrivals) if arrivals else 0.0,
        name=name,
    )
    result = PhaseResult(phase)
    timeout = aiohttp.ClientTimeout(total=None, sock_read=600)
    ids_for = trace_prompts(arrivals, prompts) if isinstance(prompts, PromptSource) else list(prompts)
    async with aiohttp.ClientSession(timeout=timeout, connector=aiohttp.TCPConnector(limit=0)) as session:
        started = time.perf_counter()

        async def send(arrival: Any, ids: list[int]) -> None:
            await asyncio.sleep(max(arrival.at - (time.perf_counter() - started), 0.0))
            record = RequestRecord(time.perf_counter())
            result.requests.append(record)
            temperature = 0.7 if arrival.temperature is None else arrival.temperature
            await _one(session, url, ids, arrival.output_tokens, record, temperature, getattr(arrival, "priority", None))

        await asyncio.gather(*(send(a, ids) for a, ids in zip(arrivals, ids_for)))
    # Every request runs to completion, so the phase lasts until the last one finishes.
    result.phase = dataclasses.replace(phase, seconds=time.perf_counter() - started)
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
