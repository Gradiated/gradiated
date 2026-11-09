from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import logging
import math
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, Sequence

from livetune import controller as control
from livetune import advisor, loadgen, rollout, trace, tune, variants
from livetune.knobs import VARIANT_KEY
from livetune.metrics import window
from livetune.policy import Policy, Slo
from livetune.server import KV_TOLERANCE, Server, UpdateFailed


def _value(raw: str) -> Any:
    if raw == "null":
        return None
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        number = float(raw)
    except ValueError:
        return raw
    return number if math.isfinite(number) else raw


def _corpus(path: str) -> list[int]:
    data = json.loads(Path(path).read_text())
    if isinstance(data, dict) and "prompts" in data:
        return [token for prompt in data["prompts"] for token in prompt]
    return list(data)


# sysexits EX_CONFIG: the controller cannot run with this configuration, so restarting will not help.
CONFIG_ERROR = 78


def _quiet(log: Any, every_s: float, clock: Any = time.monotonic) -> Any:
    """Log every event that did something, and an uneventful window at most every every_s seconds."""
    if every_s <= 0:
        return log
    last = -math.inf

    def write(event: Any) -> None:
        nonlocal last
        eventful = not isinstance(event, dict) or any(key in event for key in ("action", "reconciled", "error"))
        eventful = eventful or any(key.startswith("policy_") for key in event)
        now = clock()
        if eventful or now - last >= every_s:
            last = now if not eventful else last
            log(event)

    return write


def _appender(path: str | None, mode: str = "a"):
    handle = open(path, mode) if path else None

    def write(event: Any) -> None:
        line = event if isinstance(event, str) else json.dumps(event)
        print(line, flush=True)
        if handle:
            handle.write(line + "\n")
            handle.flush()

    return write


def _differences(expected: dict[str, Any], actual: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in sorted(set(expected) | set(actual)):
        a, b = expected.get(key), actual.get(key)
        if isinstance(a, dict) and isinstance(b, dict):
            out.update(_differences(a, b, f"{prefix}{key}."))
        elif a != b:
            out[prefix + key] = (a, b)
    return out


def load_policy(path: str, server: Server, allow_scope_mismatch: bool, variants_dir: str | None = None) -> Policy:
    policy = Policy.load(path)
    expected, actual = policy.provenance.get("scope"), server.fingerprint()
    if expected is None and not allow_scope_mismatch:
        raise SystemExit(f"{path} records no tuning scope; rebuild it with `livetune policy`, or pass --allow-scope-mismatch")
    if expected is not None and not allow_scope_mismatch:
        differs = _scope_differences(expected, actual)
        if differs:
            raise SystemExit(f"{path} was tuned for a different server (policy, live): {differs}; pass --allow-scope-mismatch to override")
    install_variants(policy, server, variants_dir)
    return policy


def install_variants(policy: Policy, server: Server, variants_dir: str | None) -> None:
    """Register the variants a policy carries where the server resolves them, before a rule asks for one.

    A policy's variants are code that runs inside the server: publish policies only through the path
    that reviews them.
    """
    if not policy.variants:
        return
    if not variants_dir:
        raise SystemExit("the policy carries forward variants; give --variants-dir, the server's LIVETUNE_VARIANTS_DIR")
    if policy.used_variants() and not all(state.get("live_variants") for state in server.livetune_states()):
        raise SystemExit("the policy switches forward variants live; the server needs LIVETUNE_LIVE_VARIANTS=1")
    for entry in policy.variants.values():
        variants.register(variants_dir, entry["name"], entry["code"])


def _carried(results: Sequence[dict[str, Any]], start: dict[str, Any], variants_dir: str | None) -> dict[str, dict[str, str]]:
    """The code of every variant the tuned settings switch to, for the policy to carry."""
    ids = {r["settings"].get(VARIANT_KEY) for r in results} - {None, variants.STOCK, start.get(VARIANT_KEY, variants.STOCK)}
    if ids and not variants_dir:
        raise SystemExit("the tuned settings switch forward variants; give --variants-dir to carry their code in the policy")
    return {str(i): variants.embedded(variants.resolve(i, variants_dir)) for i in sorted(ids)}


def replay(args: argparse.Namespace, server: Server) -> None:
    import threading

    policy = load_policy(args.policy, server, args.allow_scope_mismatch, args.variants_dir)
    write = _appender(args.out)
    startup = server.livetune_state()["startup"]
    server.apply(startup)
    # Built (and any trace prewarm run) before a controller starts watching the server.
    prompts = loadgen.PromptSource(_corpus(args.corpus))
    segments = _segments(args, prompts, server, None if args.static else policy)
    stop = threading.Event()
    events: list[dict[str, Any]] = []
    failures: list[BaseException] = []
    step_lock = threading.Lock()
    thread = None
    if not args.static:
        # Seeded from readback, so the first rule changes only what differs and starts no variant cooldown.
        controller = control.Controller(policy, startup=startup,
                                        applied={k: v for k, v in server.livetune_state()["settings"].items() if k != "policy_version"})

        def log(event: dict[str, Any]) -> None:
            events.append(event)
            write({"controller": event})

        def run_controller() -> None:
            try:
                control.run(controller, server.scrape, server.apply, window, interval_s=args.interval, log=log, stop=stop.is_set,
                            sleep=stop.wait, step_lock=step_lock)
            except BaseException as exc:
                failures.append(exc)
                raise

        thread = threading.Thread(target=run_controller, daemon=True)
        thread.start()

    def stop_controller() -> None:
        stop.set()
        if thread is not None:
            thread.join()

    try:
        for index, run_segment in enumerate(segments):
            started = time.time()
            summary = run_segment()
            if index == len(segments) - 1:
                # Join first, so a failure while the last phase ran cannot slip past this check.
                stop_controller()
            # Waits out a window still applying, so every event that started in this phase is counted.
            with step_lock:
                if failures:
                    raise RuntimeError("the controller stopped during the replay; its results are not controlled") from failures[0]
                write(phase_report(summary, events, started, time.time() - started, policy, "static" if args.static else "controlled"))
    finally:
        stop_controller()
        server.apply(startup)


def _server_stops(server: Server) -> bool:
    """Whether every scheduler finishes a replayed early stop itself, at its recorded length."""
    try:
        states = server.livetune_states()
    except Exception:
        return False
    return bool(states) and all(state.get("replay_stops") for state in states)


def _refuse_chunked_early_stops(server: Server, arrivals: Sequence[trace.Arrival], policy: Policy | None = None) -> None:
    """A trace replay that would decode past early stops measures every candidate on more work than
    production did, so it is refused rather than measured. A server with replay stops ends each one
    exactly; otherwise the client cuts the stream, which overruns when a chunk carries several
    tokens: a stream interval above 1, or speculative decoding accepting a run."""
    if _server_stops(server):
        return
    intervals = [int(state.get("settings", {}).get("stream_interval") or 1) for state in server.livetune_states()]
    # A controller replaying the trace may switch to any rule's interval mid-run.
    intervals += [int(rule.settings["stream_interval"]) for rule in (policy.rules if policy else ()) if "stream_interval" in rule.settings]
    info = getattr(server, "info", None)
    speculative = bool(info and (info() or {}).get("speculative_algorithm"))
    chunked = trace.chunked_early_stops(arrivals, max(intervals, default=1), speculative)
    if chunked:
        raise SystemExit(f"{chunked} streaming requests stopped early and would arrive in chunks of more than one token; "
                         "replay would decode past their recorded output. Replay on a server with LIVETUNE_REPLAY_STOPS=1.")


def _segments(args: argparse.Namespace, prompts: loadgen.PromptSource, server: Server, policy: Policy | None = None) -> list[Any]:
    """What a replay plays: scripted closed-loop phases, or recorded traffic arriving open loop.

    A trace's cache prewarm runs here, before the caller starts a controller, so the controller never
    sees the synthetic warmups as traffic.
    """
    import asyncio

    if args.trace:
        try:
            arrivals = trace.arrivals(list(trace.read([args.trace])), speed=args.speed)
        except ValueError as exc:
            raise SystemExit(f"{args.trace}: {exc}") from exc
        if not arrivals:
            raise SystemExit(f"no records in {args.trace}")
        _refuse_chunked_early_stops(server, arrivals, policy)
        ids = loadgen.trace_prompts(arrivals, prompts)
        # From an empty cache, then the recorded initial state: a previous replay's prefixes must not linger.
        server.flush_cache()
        loadgen.prewarm(args.url, arrivals, ids)
        stops = _server_stops(server)
        return [lambda: asyncio.run(loadgen.run_arrivals(args.url, arrivals, ids, warm=False, server_stops=stops)).summary()]
    phases = [loadgen.Phase(**p) for p in json.loads(Path(args.phases).read_text())]
    return [lambda phase=phase, index=index: asyncio_phase(args.url, phase, prompts, index) for index, phase in enumerate(phases)]


def _replay_measured(server: Server, arrivals: list[trace.Arrival], ids: list[list[int]], name: str) -> dict[str, Any]:
    """Replay a trace once and summarise it, judging the SLO on every request it sent."""
    import asyncio

    _refuse_chunked_early_stops(server, arrivals)
    loadgen.prewarm(server.url, arrivals, ids)
    unstreamed = any(not getattr(a, "stream", True) for a in arrivals)
    before = server.scrape() if unstreamed else None
    summary = asyncio.run(loadgen.run_arrivals(server.url, arrivals, ids, name=name, warm=False,
                                               server_stops=_server_stops(server))).summary()
    if summary.get("untimed"):
        # Non-streaming responses came back without the server's per-request timings (no
        # --enable-metrics). The server's histograms cover every request, warm-ups included, so
        # with warm-ups in the replay they cannot judge only the window.
        if any(getattr(a, "warmup", False) for a in arrivals):
            return {**summary, "tps_per_user_p50": None, "ttft_p90": None, "slo_from": "unmeasurable: untimed responses beside warm-ups"}
        served = window(before, server.scrape())
        summary = {**summary, "tps_per_user_p50": served.tps_per_user, "ttft_p90": served.ttft_p90, "slo_from": "server"}
    return summary


def tune_policy(
    server: Server,
    slo: Slo,
    prompts: loadgen.PromptSource,
    grid: dict[str, list[Any]],
    profiles: list[dict[str, Any]] | None,
    arrivals: list[trace.Arrival] | None,
    seconds: float,
    warmup: float,
    record: Any,
    variants_dir: str | None = None,
) -> Policy:
    """Measure each grid value against the startup settings, per profile or against recorded traffic."""
    start = dict(server.livetune_state()["startup"])
    scope = server.fingerprint()
    # Every candidate and confirmation run sends the same token ids; content changes MoE routing.
    trace_ids = loadgen.trace_prompts(arrivals, prompts) if arrivals is not None else None
    if arrivals is not None:
        _refuse_chunked_early_stops(server, arrivals)
    if arrivals is not None and "stream_interval" in grid and not _server_stops(server) and any((a.max_new_tokens or 0) > a.output_tokens for a in arrivals):
        # An early-stopped request is cut off at a chunk boundary, so larger chunks overrun its recorded
        # output by up to stream_interval - 1 tokens and would be measured on more work.
        logging.getLogger(__name__).warning("dropping stream_interval from the grid: the trace has early-stopped requests")
        grid = {knob: values for knob, values in grid.items() if knob != "stream_interval"}

    def measure(profile: tune.Profile, settings: dict[str, Any]) -> dict[str, Any]:
        server.apply(settings)
        # Every measurement starts from the same cold prefix cache; a cache warmed by the previous
        # trial would favour whichever candidate ran later.
        server.flush_cache()
        if arrivals is not None:
            # Every candidate meets the same recorded traffic, arriving at its recorded times.
            summary = _replay_measured(server, arrivals, trace_ids, profile.name)
        else:
            if warmup:
                loadgen.run(server.url, [profile.phase(warmup)], prompts, log=lambda _: None)
            summary = loadgen.run(server.url, [profile.phase(seconds)], prompts, log=lambda _: None)[0]
        # The workload mode decides which caps can bind when `policy` rebuilds from these trials.
        record({"profile": profile.name, "open_loop": profile.open_loop, "settings": settings, "summary": summary, "scope": scope})
        return summary

    profiles = profiles if profiles is not None else [tune.trace_profile(arrivals or [])]
    tune.check_distinguishable(profiles)
    try:
        results = [tune.tune_profile(tune.Profile(**p), start, grid, slo, measure) for p in profiles]
    finally:
        server.apply(start)
    return tune.build_policy(results, slo, {"tuned_at": time.time(), "url": server.url, "scope": scope}, start,
                             _carried(results, start, variants_dir))


def variant_eval(args: argparse.Namespace, server: Server) -> dict[str, Any]:
    """Try one forward variant live on a canary: gate it against stock, measure it, and switch back.

    The variant is registered under its content hash, so every revision gets its own pinned id.
    The canary must run with LIVETUNE_LIVE_VARIANTS=1 and share LIVETUNE_VARIANTS_DIR with this host.
    """
    code = Path(args.variant).read_text()
    name = args.name
    variant_id = variants.register(args.variants_dir, name, code)
    prompts = _gate_prompts(args.corpus, args.prompts, args.prompt_tokens, args.seed)
    # Baselines are always stock, whatever the canary was running; that is restored at the end.
    incumbent = server.livetune_state()["settings"].get(VARIANT_KEY, variants.STOCK)
    stock_id = variants.STOCK
    report: dict[str, Any] = {"variant": name, "id": variant_id, "sha256": hashlib.sha256(code.encode()).hexdigest(), "incumbent": incumbent}
    try:
        server.apply({VARIANT_KEY: stock_id})
        stock = (server.greedy(prompts, args.tokens), server.greedy(prompts, args.tokens))
        verdict, report["switch_s"] = _gate_variant(server, variant_id, prompts, args.tokens, stock)
        report["gate"] = dataclasses.asdict(verdict)
        if verdict.passed and args.trace:
            arrivals = trace.arrivals(list(trace.read([args.trace])), speed=args.speed)
            ids = loadgen.trace_prompts(arrivals, loadgen.PromptSource(_corpus(args.corpus), seed=args.seed))
            runs: dict[str, list[dict[str, Any]]] = {"variant": [], "stock": []}
            # Interleaved, and every run starts from a flushed cache, so order and warmth cancel out.
            for label in ("variant", "stock", "variant", "stock"):
                server.apply({VARIANT_KEY: variant_id if label == "variant" else stock_id})
                server.flush_cache()
                runs[label].append(_replay_measured(server, arrivals, ids, label))
            merged = {label: tune.merged(summaries) for label, summaries in runs.items()}
            report["performance"] = merged
            if args.slo_tps is not None and args.slo_ttft is not None:
                report["faster"] = tune._wins(merged["variant"], merged["stock"], Slo(args.slo_tps, args.slo_ttft), 0.02)
        report["decision"] = "keep" if verdict.passed and report.get("faster", True) else "reject"
    finally:
        server.apply({VARIANT_KEY: incumbent})
    return report


def _gate_prompts(corpus: str, count: int, prompt_tokens: int, seed: int) -> list[list[int]]:
    source = loadgen.PromptSource(_corpus(corpus), seed=seed)
    return [source.family_prompt(prompt_tokens, 0, None) for _ in range(count)]


def _gate_variant(server: Server, variant_id: int, prompts: list[list[int]], tokens: int, stock: tuple[Any, Any]) -> tuple[Any, float]:
    """Switch to a variant and judge its greedy output against stock's two runs; returns the verdict
    and how long the switch took. The caller switches back."""
    from livetune import gate

    started = time.monotonic()
    server.apply({VARIANT_KEY: variant_id})
    switch_s = round(time.monotonic() - started, 1)
    return gate.judge(stock[0], stock[1], server.greedy(prompts, tokens)), switch_s


def _variant_candidates(args: argparse.Namespace, canary: Server, ledger_path: Path) -> list[dict[str, Any]]:
    """Gate every new variant file in --candidates on the canary; return the ledger.

    A variant is judged once per revision, by its code's hash. One that fails the gate is rejected for
    good; one that passes stays a tuning candidate until it has lost --variant-tries cycles. The agent
    loop that writes variants reads code-targets.json and adds files here.
    """
    ledger: dict[str, dict[str, Any]] = json.loads(ledger_path.read_text()) if ledger_path.is_file() else {}
    fresh = []
    for path in sorted(Path(args.candidates).glob("*.py")):
        code = path.read_text()
        sha256 = hashlib.sha256(code.encode()).hexdigest()
        if sha256 in ledger:
            continue
        try:
            variant_id = variants.register(args.variants_dir, path.stem, code)
        except variants.VariantError as exc:
            ledger[sha256] = {"name": path.stem, "status": "invalid", "reason": str(exc), "t": time.time()}
            continue
        fresh.append((path.stem, sha256, variant_id))
    if fresh:
        prompts = _gate_prompts(args.corpus, args.gate_prompts, args.gate_prompt_tokens, 7)
        incumbent = canary.livetune_state()["settings"].get(VARIANT_KEY, variants.STOCK)
        try:
            canary.apply({VARIANT_KEY: variants.STOCK})
            stock = (canary.greedy(prompts, args.gate_tokens), canary.greedy(prompts, args.gate_tokens))
            for name, sha256, variant_id in fresh:
                entry: dict[str, Any] = {"name": name, "id": variant_id, "t": time.time(), "losses": 0}
                try:
                    verdict, entry["switch_s"] = _gate_variant(canary, variant_id, prompts, args.gate_tokens, stock)
                    entry["gate"] = dataclasses.asdict(verdict)
                    entry["status"] = "candidate" if verdict.passed else "rejected"
                except UpdateFailed as exc:
                    # The server refused or failed the switch: the install raised, or building its state did.
                    # Anything else (an unreachable canary) fails the cycle, and the variant is gated next time.
                    entry.update(status="rejected", reason=f"{type(exc).__name__}: {exc}")
                ledger[sha256] = entry
                canary.apply({VARIANT_KEY: variants.STOCK})
        finally:
            canary.apply({VARIANT_KEY: incumbent})
    _write_json(ledger_path, ledger)
    return list(ledger.values())


def _write_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=1))
    temporary.replace(path)


def _rotated_away(trace_dir: str, pid: str, since: float) -> bool:
    """Whether a writer's files from before since are gone. A writer's first file still being there
    proves nothing rotated away; otherwise its oldest file must have been opened before since."""
    files = sorted(Path(trace_dir).glob(f"trace-*-{pid}-*.jsonl"))
    if not files:
        return True
    oldest = files[0].stem.split("-")
    if oldest[3] == "0" * 12:
        return False
    return time.mktime(time.strptime(oldest[1], "%Y%m%dT%H%M%S")) > since


def _await_written(server: Server, timeout_s: float = 120.0, interval_s: float = 1.0) -> bool:
    """Wait until every request that finished before now is on disk. The writer thread is FIFO, so
    once it has processed as many snapshots as were queued at the start, those have been written."""
    queued = [int((state.get("telemetry") or {}).get("enqueued") or 0) for state in server.livetune_states()]
    deadline = time.monotonic() + timeout_s
    while True:
        done = [int((state.get("telemetry") or {}).get("processed") or 0) for state in server.livetune_states()]
        if len(done) == len(queued) and all(d >= q for d, q in zip(done, queued)):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(interval_s)


def _await_finished(server: Server, until: float, timeout_s: float, interval_s: float = 5.0) -> bool:
    """Wait until no request that started before until is still running, so all of them have records."""
    deadline = time.monotonic() + timeout_s
    while True:
        oldest = [state.get("oldest_unfinished") for state in server.livetune_states()]
        if all(t is None or t >= until for t in oldest):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(interval_s)


def _trace_gap(server: Server, trace_dir: str, since: float, history: dict[tuple[str, float], list[tuple[float, int]]]) -> str | None:
    """Why the production trace may be missing requests that started at or after since, or None.

    A window replayed with requests missing is a lighter workload than production served. Records
    are lost when the scheduler was not recording, restarted, dropped records, failed to write them,
    or rotated the files away. history holds this process's earlier readings of each writer's drop
    count, so a writer that dropped records once can still vouch for a later window.
    """
    now = time.time()
    for state in server.livetune_states():
        telemetry = state.get("telemetry") or {}
        path, started, dropped = telemetry.get("trace_path"), telemetry.get("since"), int(telemetry.get("dropped") or 0)
        if not path or started is None:
            return "a scheduler is not recording traffic"
        if telemetry.get("error"):
            return f"a scheduler's trace writer failed: {telemetry['error']}"
        if started > since:
            return "a scheduler started recording during the window"
        pid = Path(path).stem.split("-")[2]
        if _rotated_away(trace_dir, pid, since):
            return "the window's oldest trace file was rotated away"
        readings = history.setdefault((pid, started), [])
        readings.append((now, dropped))
        if dropped and not any(t <= since and d == dropped for t, d in readings):
            return f"a scheduler dropped {dropped} records, and none of them can be ruled out of the window"
    return None


def improve(args: argparse.Namespace, server: Server) -> None:
    """Keep improving: advise from production, measure the proposals on a canary against the
    production traffic just recorded, and publish a policy only when something beat startup."""
    canary = Server(args.canary)
    out = Path(args.work_dir)
    # Snapshots copy Confidential trace records, so the work directory is the owner's only.
    out.mkdir(mode=0o700, parents=True, exist_ok=True)
    out.chmod(0o700)
    write = _appender(str(out / "improve.jsonl"))
    # Each production writer's drop count as read in earlier cycles, to vouch for later windows.
    history: dict[tuple[str, float], list[tuple[float, int]]] = {}
    while True:
        started = time.time()
        report = advise(argparse.Namespace(seconds=args.advise_seconds, interval=args.interval, trace_dir=args.trace_dir, close_s=args.close_s), server)
        entry: dict[str, Any] = {"t": started, "proposals": report["proposals"], "grid": report["grid"]}
        differs = _scope_differences(server.fingerprint(), canary.fingerprint())
        grid = dict(report["grid"])
        code_targets = [p for p in report["proposals"] if p["tier"] == "code"]
        if args.candidates and not differs:
            if not canary.livetune_state().get("live_variants"):
                entry["variants_skipped"] = "the canary runs without LIVETUNE_LIVE_VARIANTS=1"
            else:
                ledger = _variant_candidates(args, canary, out / "variants.json")
                entry["variants"] = [{k: v.get(k) for k in ("name", "id", "status")} for v in ledger if v.get("t", 0) >= started]
                kept = [v["id"] for v in ledger if v["status"] == "candidate"]
                if kept:
                    grid[VARIANT_KEY] = kept
        # A record is written when its request finishes, so a window that ended just now would miss its
        # long requests. Replay one that closed --close-s ago, whose requests have had time to finish.
        until = time.time() - args.close_s
        since = until - args.window
        # A request that started in the window and still runs (the longest outlive --close-s) has no
        # record yet; records still queued for the writer would be missing from a read made now.
        finished = _await_finished(server, until, args.close_s)
        written = finished and _await_written(server)
        # Requests running when the window began loaded the server too; they replay unmeasured.
        records = list(trace.read([args.trace_dir], since=since, until=until, overlapping=True))
        if differs:
            # A canary that differs from production would measure another intervention.
            entry["skipped"] = {"canary_scope_differs": sorted(differs)}
        elif not report.get("traffic_complete", True):
            # The proposals were drawn from a traffic mix that was still missing requests.
            entry["skipped"] = {"incomplete_trace": "the advisor's traffic was still being recorded"}
        elif not grid or not records:
            entry["skipped"] = "nothing to test" if not grid else "no recorded traffic"
        elif gap := ("requests from the window are still running" if not finished else "records were still being written" if not written
                     else _trace_gap(server, args.trace_dir, since, history)):
            # Tuning on a partial trace measures a lighter workload than production served.
            entry["skipped"] = {"incomplete_trace": gap}
        elif gaps := trace.replay_gaps(records):
            # Replay would send these as plain requests and tune for a different workload.
            entry["skipped"] = {"unreproducible_modes": gaps}
        else:
            snapshot = out / f"trace-{int(started)}.jsonl"
            with os.fdopen(os.open(snapshot, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as handle:
                handle.write("".join(r.to_json() + "\n" for r in records))
            if code_targets:
                # The shapes worth a kernel, and the traffic it must win on, for the agent loop that writes variants.
                _write_json(out / "code-targets.json", {"t": started, "targets": code_targets, "trace": str(snapshot),
                                                        "candidates": args.candidates})
            policy = tune_policy(canary, Slo(args.slo_tps, args.slo_ttft), loadgen.PromptSource(_corpus(args.corpus)), grid,
                                 None, trace.arrivals(records, speed=args.speed, measured_from=since), 0, 0, _appender(str(out / f"trials-{int(started)}.jsonl")),
                                 args.variants_dir)
            winner = policy.rule("trace").settings
            entry["winner"] = winner
            if VARIANT_KEY in grid:
                _score_candidates(out / "variants.json", grid[VARIANT_KEY], winner.get(VARIANT_KEY), args.variant_tries)
            if winner != policy.rule("unmeasured").settings:
                staged_before = Path(args.stage_policy).read_text() if args.stage_url else None
                verdict = stage(args, server, policy) if args.stage_url else None
                if verdict is not None:
                    entry["stage"] = dataclasses.asdict(verdict)
                if verdict is None or verdict.decision == "promote":
                    entry["published"] = args.policy_out
                    try:
                        guard = promote(args, server, policy, staged_ok=verdict is not None and verdict.decision == "promote")
                    except BaseException:
                        if staged_before is not None:
                            _publish(args.stage_policy, staged_before)  # an unfinished promotion promoted nothing
                        raise
                    if guard is not None:
                        entry["guard"] = dataclasses.asdict(guard)
                        if guard.decision == "revert" and staged_before is not None:
                            # The staged replica still runs the candidate the fleet just rejected.
                            _publish(args.stage_policy, staged_before)
        write(entry)
        if args.once:
            return
        time.sleep(max(args.every - (time.time() - started), 0))


def _score_candidates(ledger_path: Path, measured: Sequence[int], chosen: int | None, tries: int) -> None:
    """Count a cycle each measured candidate lost; retire one that has lost tries cycles."""
    ledger = json.loads(ledger_path.read_text())
    for entry in ledger.values():
        if entry.get("status") == "candidate" and entry.get("id") in measured:
            entry["losses"] = 0 if entry["id"] == chosen else entry.get("losses", 0) + 1
            if entry["losses"] >= tries:
                entry["status"] = "retired"
    _write_json(ledger_path, ledger)


def _scope_differences(expected: dict[str, Any], actual: dict[str, Any]) -> dict[str, Any]:
    differs = _differences(expected, actual)
    # Free memory varies a little between starts; a policy holds within a few percent of its KV capacity.
    kv = differs.get("kv_tokens")
    if kv and all(kv) and abs(kv[1] - kv[0]) <= KV_TOLERANCE * kv[0]:
        del differs["kv_tokens"]
    return differs


def _publish(path: str, text: str) -> None:
    tmp = Path(path + ".tmp")
    tmp.write_text(text)
    tmp.replace(path)  # controllers reload a complete file, never a partial one


def _watch(servers: list[Server], seconds: float, interval: float,
           running: Sequence[Callable[[Server], bool] | None] | None = None) -> list[list[Any]]:
    """Metric windows from several servers over the same span.

    A server with a running check keeps only the windows it passed at both ends: a staged replica
    whose traffic moved to the policy's startup rule mid-watch was not running the candidate then.
    """
    checks = list(running) if running is not None else [None] * len(servers)
    windows: list[list[Any]] = [[] for _ in servers]

    def read(i: int) -> Any:
        # An unreadable replica, or one not running what is being judged, loses the window.
        try:
            current = servers[i].scrape()
            return current if checks[i] is None or checks[i](servers[i]) else None
        except Exception:
            return None

    previous = [read(i) for i in range(len(servers))]
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        time.sleep(interval)
        for i in range(len(servers)):
            current = read(i)
            if previous[i] is not None and current is not None:
                windows[i].append(window(previous[i], current))
            previous[i] = current
    return windows


def _runs_candidate(server: Server, policy: Policy) -> bool:
    """Whether every data-parallel scheduler has this policy loaded and is applying one of its tuned rules."""
    startup = policy.rules[-1].settings
    candidates = [rule.settings for rule in policy.rules if rule.settings != startup]

    def runs(live: dict[str, Any]) -> bool:
        return live.get("policy_version") == policy.version and any(all(live.get(k) == v for k, v in c.items()) for c in candidates)

    states = server.livetune_states()
    return bool(states) and all(runs(state.get("settings", {})) for state in states)


def _verified_on(server: Server, policy: Policy) -> bool:
    """_runs_candidate, with a state that cannot be read counting as not running the candidate."""
    try:
        return _runs_candidate(server, policy)
    except Exception:
        return False


def _wait_applied(server: Server, policy: Policy, timeout_s: float, interval_s: float) -> bool:
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            if _runs_candidate(server, policy):
                return True
        except Exception:
            pass
        if time.monotonic() >= deadline:
            return False
        time.sleep(interval_s)


def promote(args: argparse.Namespace, production: Server, policy: Policy, staged_ok: bool = False) -> rollout.Verdict | None:
    """Publish to the fleet, then guard it: compare the fleet after against just before, and restore
    the previous policy if it regressed. A big shift in traffic makes the comparison inconclusive, and
    the change stays, since it has already passed replay and the stage."""
    scope = production.fingerprint()
    # The staged replica already runs the candidate, so its windows cannot serve as the previous policy's
    # baseline; it was judged against its peers during the stage.
    staged = getattr(args, "stage_url", None)
    members = [m for m in [production] + [Server(url) for url in _replica_urls(args.fleet, excluding=getattr(production, "url", None))] if not _same_url(m.url, staged)]
    # Replicas outside production's scope refuse the policy, so their unchanged windows would dilute the comparison.
    fleet = [m for m in members if not _scope_differences(scope, m.fingerprint())]
    slo = Slo(args.slo_tps, args.slo_ttft)
    if not fleet:
        # Nothing left to guard (the staged replica was the only one): publishing would be unmeasured.
        return rollout.Verdict("revert", "no fleet replica to guard the publication; nothing published", rollout.Side.of([], slo), rollout.Side.of([], slo))
    # The first publication still needs a restore point: a policy that holds the startup settings.
    previous = Path(args.policy_out).read_text() if Path(args.policy_out).exists() else _startup_policy(production, policy, slo).to_json()
    before = _watch(fleet, args.guard_seconds, args.interval) if args.guard_seconds else None
    _publish(args.policy_out, policy.to_json())
    if before is None:
        return None
    try:
        verdict = _guard(args, fleet, policy, before, slo)
    except Exception as exc:
        # A guard that cannot finish has not shown the candidate is safe.
        verdict = rollout.Verdict("revert", f"the guard could not finish: {type(exc).__name__}: {exc}", rollout.Side.of([], slo), rollout.Side.of([], slo))
    if verdict.decision == "inconclusive" and not staged_ok:
        # With no stage either, nothing live has shown the candidate is safe.
        verdict = rollout.Verdict("revert", f"the guard was inconclusive and there was no stage: {verdict.reason}", verdict.stage, verdict.peers)
    if verdict.decision == "revert":
        _publish(args.policy_out, previous)
    return verdict


def _startup_policy(production: Server, candidate: Policy, slo: Slo) -> Policy:
    import math

    from livetune.policy import Rule

    startup = candidate.rules[-1].settings
    return Policy(slo, (Rule("unmeasured", math.inf, math.inf, dict(startup)),), {"scope": candidate.provenance.get("scope") or production.fingerprint(),
                                                                              "startup_only": True})


def _guard(args: argparse.Namespace, fleet: list[Server], policy: Policy, before: list[list[Any]], slo: Slo) -> rollout.Verdict:
    # Judge only the replicas that took the candidate up, from the moment they did.
    from concurrent.futures import ThreadPoolExecutor

    # All replicas get the same apply window, measured from publishing, not one after another.
    with ThreadPoolExecutor(max_workers=max(len(fleet), 1)) as pool:
        ready = list(pool.map(lambda m: _wait_applied(m, policy, args.stage_apply_s, args.interval), fleet))
    applied = [i for i, ok in enumerate(ready) if ok]
    missed = [fleet[i].url for i, ok in enumerate(ready) if not ok]
    if missed:
        # A replica that misses the window would load the policy later, after the guard, unmeasured on its
        # traffic; the fleet takes a candidate together or not at all.
        return rollout.Verdict("revert", f"replicas did not apply the published policy in time: {missed}", rollout.Side.of([], slo), rollout.Side.of([], slo))
    on_candidate = lambda server: _verified_on(server, policy)
    after = _watch([fleet[i] for i in applied], args.guard_seconds, args.interval, [on_candidate] * len(applied))

    left = [fleet[i].url for i in applied if not _verified_on(fleet[i], policy)]
    if left:
        # A replica that dropped the candidate mid-guard (local probation rollback, say), or whose state
        # cannot be read, was not shown running it; a guard prefers the known-good policy.
        return rollout.Verdict("revert", f"replicas not verified on the candidate at the end of the guard: {left}", rollout.Side.of([], slo), rollout.Side.of([], slo))
    return rollout.judge([w for side in after for w in side], [w for i in applied for w in before[i]], slo)


def _same_url(a: str | None, b: str | None) -> bool:
    return a is not None and b is not None and a.rstrip("/") == b.rstrip("/")


def _replica_urls(text: str | None, excluding: str | None = None) -> list[str]:
    """A comma-separated replica list, each once, without the excluded replica."""
    urls: list[str] = []
    for url in (text or "").split(","):
        url = url.strip()
        if url and not _same_url(url, excluding) and not any(_same_url(url, seen) for seen in urls):
            urls.append(url)
    return urls


def stage(args: argparse.Namespace, production: Server, policy: Policy) -> rollout.Verdict:
    """Run a candidate on one production replica beside its peers; restore the replica's policy unless it is promoted."""
    replica = Server(args.stage_url)
    # The staged replica runs the candidate, so listed among its own peers it would vouch for itself.
    peers = [Server(url) for url in _replica_urls(args.peers, excluding=args.stage_url)]
    slo = Slo(args.slo_tps, args.slo_ttft)
    scope = production.fingerprint()
    # Evidence counts only from replicas running the intervention production runs.
    outside = [s.url for s in (replica, *peers) if _scope_differences(scope, s.fingerprint())]
    if outside or not peers:
        reason = f"replicas outside production's scope: {outside}" if outside else "no peers besides the staged replica to compare against"
        return rollout.Verdict("inconclusive", reason, rollout.Side.of([], slo), rollout.Side.of([], slo))
    previous = Path(args.stage_policy).read_text()
    _publish(args.stage_policy, policy.to_json())
    verdict = None
    try:
        # The scope ignores live settings, so an unchanged replica would match its peers: measure
        # only once the replica reports a candidate rule live, and only if it still does at the end.
        if not _wait_applied(replica, policy, args.stage_apply_s, args.interval):
            verdict = rollout.Verdict("inconclusive", "the staged replica did not apply the candidate", rollout.Side.of([], slo), rollout.Side.of([], slo))
            return verdict
        watched = _watch([replica, *peers], args.stage_seconds, args.interval,
                         [lambda server: _verified_on(server, policy)] + [None] * len(peers))
        verdict = rollout.judge(watched[0], [w for side in watched[1:] for w in side], slo)
        if verdict.decision == "promote" and not _verified_on(replica, policy):
            verdict = rollout.Verdict("inconclusive", "the staged replica is not verified on the candidate at the end of the stage", verdict.stage, verdict.peers)
        return verdict
    except BaseException:
        verdict = None  # a stage that did not finish has promoted nothing
        raise
    finally:
        if verdict is None or verdict.decision != "promote":
            _publish(args.stage_policy, previous)


def _batch_counters(server: Server) -> dict[str, float]:
    """Batch counters summed over every data-parallel scheduler, so they cover what the metrics and trace cover."""
    total: dict[str, float] = {}
    for state in server.livetune_states():
        for key, value in ((state.get("telemetry") or {}).get("batches") or {}).items():
            total[key] = total.get(key, 0.0) + value
    return total


def advise(args: argparse.Namespace, server: Server) -> dict[str, Any]:
    """Watch the server for a while, then propose experiments from what it saw."""
    before = _batch_counters(server)
    started_wall = time.time()
    windows, previous = [], server.scrape()
    deadline = time.monotonic() + args.seconds
    while time.monotonic() < deadline:
        time.sleep(args.interval)
        current = server.scrape()
        windows.append(window(previous, current))
        previous = current
    after_state = server.livetune_state()
    after = _batch_counters(server)
    ended_wall = time.time()
    # The traffic mix is the requests that started while the metrics were watched, so utilization
    # and shape describe one workload. A record is written when its request finishes, so wait close_s
    # for the long ones to finish before reading.
    close_s = getattr(args, "close_s", 600.0)
    complete = True
    if args.trace_dir:
        # Wait for every request that started while watching to finish and reach the trace (the
        # longest outlive any fixed delay), within close_s; past that the mix is marked incomplete.
        complete = _await_finished(server, ended_wall, close_s) and _await_written(server)
    records = list(trace.read([args.trace_dir], since=started_wall, until=ended_wall)) if args.trace_dir else []
    batches = trace.batch_deltas(before, after)
    evidence = advisor.Evidence(
        windows=windows,
        traffic=trace.summarize(records),
        batches=batches,
        settings=after_state.get("settings", {}),
        startup=after_state.get("startup", {}),
        kv_capacity=int(server.info().get("max_total_num_tokens") or 0),
        page_size=int(after_state.get("page_size") or 1),
    )
    proposals = advisor.advise(evidence)
    utilization = {
        "forward_share": round(evidence.mean("forward_share"), 3),
        "eviction_share": round(evidence.mean("eviction_share"), 3),
        "kv_free_share": round(evidence.mean("kv_free_share"), 4),
        "output_tps": round(evidence.mean("output_tps"), 1),
    }
    return {"utilization": utilization, "traffic": evidence.traffic, "traffic_complete": complete, "batches": batches,
            "proposals": advisor.to_json(proposals), "grid": advisor.as_grid(proposals)}


def phase_report(summary: dict[str, Any], events: list[dict[str, Any]], started: float, seconds: float, policy: Policy, mode: str) -> dict[str, Any]:
    during = [e for e in events if started <= e["wall"] <= started + seconds]
    switches = [e for e in during if "action" in e]
    apply_errors = sum("error" in e["action"] for e in switches)
    return {
        **summary,
        "mode": mode,
        # A rejected apply leaves traffic on settings the controller did not choose; such a phase is not controlled evidence.
        "apply_errors": apply_errors,
        "valid": apply_errors == 0,
        # Both halves of the SLO must be measured for a phase to pass or fail it.
        "slo_met": None if None in (summary["tps_per_user_p50"], summary["ttft_p90"]) else policy.slo.met(summary["tps_per_user_p50"], summary["ttft_p90"]),
        "rules": sorted({e["rule"] for e in during if e.get("rule")}),
        "first_switch_s": round(switches[0]["wall"] - started, 1) if switches else None,
    }


def asyncio_phase(url: str, phase: loadgen.Phase, prompts: loadgen.PromptSource, index: int) -> dict[str, Any]:
    import asyncio

    return asyncio.run(loadgen.run_phase(url, phase, prompts, index)).summary()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="livetune")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("status", "set", "load", "tune", "control", "replay", "policy", "traffic", "advise", "improve", "variant-eval"):
        p = sub.add_parser(name)
        p.add_argument("--url", default="http://127.0.0.1:30000")
    sub.choices["set"].add_argument("pairs", nargs="+")
    for name in ("load", "tune", "replay"):
        sub.choices[name].add_argument("--corpus", required=True)
        sub.choices[name].add_argument("--out", required=name == "tune")
    sub.choices["load"].add_argument("--phases", required=True)
    r = sub.choices["replay"]
    source = r.add_mutually_exclusive_group(required=True)
    source.add_argument("--phases", help="closed-loop phases (JSON list)")
    source.add_argument("--trace", help="recorded traffic (trace directory or file), replayed open loop")
    r.add_argument("--speed", type=float, default=1.0, help="trace time compression: 2 replays twice as fast")
    r.add_argument("--policy", required=True)
    r.add_argument("--static", action="store_true", help="hold the startup settings instead of running the controller")
    r.add_argument("--interval", type=float, default=5.0)
    for name in ("control", "replay"):
        sub.choices[name].add_argument("--allow-scope-mismatch", action="store_true", help="use a policy tuned on a different model, layout or GPU")
    for name in ("control", "replay", "tune", "policy", "improve"):
        sub.choices[name].add_argument("--variants-dir", default=os.environ.get("LIVETUNE_VARIANTS_DIR"),
                                       help="the server's LIVETUNE_VARIANTS_DIR, where policies' variants are registered and read")
    t = sub.choices["tune"]
    workload = t.add_mutually_exclusive_group(required=True)
    workload.add_argument("--profiles", help="closed-loop profiles (JSON list)")
    workload.add_argument("--trace", help="recorded traffic to measure every candidate against, open loop")
    t.add_argument("--speed", type=float, default=1.0, help="trace time compression")
    t.add_argument("--grid", required=True)
    t.add_argument("--slo-tps", type=float, required=True)
    t.add_argument("--slo-ttft", type=float, required=True)
    t.add_argument("--seconds", type=float, default=40)
    t.add_argument("--warmup", type=float, default=10)
    pol = sub.choices["policy"]
    pol.add_argument("--trials", required=True)
    pol.add_argument("--slo-tps", type=float, required=True)
    pol.add_argument("--slo-ttft", type=float, required=True)
    pol.add_argument("--out", required=True)
    tr = sub.choices["traffic"]
    tr.add_argument("--trace-dir", required=True)
    tr.add_argument("--since", type=float, default=0.0, help="wall-clock seconds; 0 reads everything")
    a = sub.choices["advise"]
    a.add_argument("--seconds", type=float, default=300)
    a.add_argument("--interval", type=float, default=5.0)
    a.add_argument("--trace-dir", help="the server's LIVETUNE_TRACE_DIR, for the traffic mix")
    a.add_argument("--out", help="write the report here as well")
    a.add_argument("--close-s", type=float, default=600, help="the traffic mix is the requests that started while watching, read this long after, once they have finished")
    ve = sub.choices["variant-eval"]
    ve.add_argument("--variant", required=True, help="a Python file defining install(model, patch, ctx)")
    ve.add_argument("--name", required=True)
    ve.add_argument("--variants-dir", default=os.environ.get("LIVETUNE_VARIANTS_DIR"), required=not os.environ.get("LIVETUNE_VARIANTS_DIR"))
    ve.add_argument("--corpus", required=True)
    ve.add_argument("--prompts", type=int, default=8)
    ve.add_argument("--prompt-tokens", type=int, default=1024)
    ve.add_argument("--tokens", type=int, default=64)
    ve.add_argument("--seed", type=int, default=7)
    ve.add_argument("--trace", help="recorded traffic to measure the variant against stock, interleaved")
    ve.add_argument("--speed", type=float, default=1.0)
    ve.add_argument("--slo-tps", type=float)
    ve.add_argument("--slo-ttft", type=float)
    im = sub.choices["improve"]
    im.add_argument("--canary", required=True, help="a server with the production scope that only replayed traffic reaches")
    im.add_argument("--trace-dir", required=True)
    im.add_argument("--corpus", required=True)
    im.add_argument("--slo-tps", type=float, required=True)
    im.add_argument("--slo-ttft", type=float, required=True)
    im.add_argument("--policy-out", required=True, help="where controllers read their policy")
    im.add_argument("--work-dir", required=True)
    im.add_argument("--every", type=float, default=3600)
    im.add_argument("--window", type=float, default=600, help="seconds of recorded traffic to replay")
    im.add_argument("--close-s", type=float, default=600, help="how long before now the replayed window ends, so its requests have finished")
    im.add_argument("--advise-seconds", type=float, default=300)
    im.add_argument("--interval", type=float, default=5.0)
    im.add_argument("--speed", type=float, default=1.0)
    im.add_argument("--once", action="store_true")
    im.add_argument("--stage-url", help="a production replica that runs each winner first, beside its peers")
    im.add_argument("--stage-policy", help="the policy file the staged replica's controller reads")
    im.add_argument("--peers", default="", help="comma-separated production replicas to compare against")
    im.add_argument("--stage-seconds", type=float, default=1800)
    im.add_argument("--stage-apply-s", type=float, default=180, help="how long the staged controller may take to apply the candidate")
    im.add_argument("--fleet", default="", help="comma-separated production replicas the guard watches with --url")
    im.add_argument("--guard-seconds", type=float, default=1800, help="fleet time before and after publishing to compare; 0 disables")
    im.add_argument("--candidates", help="a directory of forward variant files (install(model, patch, ctx)) to gate and tune on the canary")
    im.add_argument("--variant-tries", type=int, default=3, help="cycles a gated variant may lose before it is retired")
    im.add_argument("--gate-prompts", type=int, default=8)
    im.add_argument("--gate-prompt-tokens", type=int, default=1024)
    im.add_argument("--gate-tokens", type=int, default=64)
    c = sub.choices["control"]
    c.add_argument("--policy", required=True)
    c.add_argument("--interval", type=float, default=5.0)
    c.add_argument("--log")
    c.add_argument("--mode", choices=("act", "observe"), default="act", help="observe logs decisions without applying them")
    c.add_argument("--log-every", type=float, default=0.0,
                   help="seconds between logged windows that changed nothing; 0 logs every window")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    server = Server(args.url)

    if args.command == "traffic":
        print(json.dumps(trace.summarize(list(trace.read([args.trace_dir], since=args.since))), indent=1))
        return 0
    if args.command == "advise":
        report = advise(args, server)
        if args.out:
            Path(args.out).write_text(json.dumps(report, indent=1))
        print(json.dumps(report, indent=1))
        return 0
    if args.command == "variant-eval":
        if args.trace and (args.slo_tps is None or args.slo_ttft is None):
            raise SystemExit("--trace needs --slo-tps and --slo-ttft, so a slower variant cannot be kept on correctness alone")
        print(json.dumps(variant_eval(args, server), indent=1))
        return 0
    if args.command == "improve":
        if args.stage_url and not (args.stage_policy and args.peers):
            raise SystemExit("--stage-url needs --stage-policy and --peers")
        if args.candidates and not args.variants_dir:
            raise SystemExit("--candidates needs --variants-dir, the canary's LIVETUNE_VARIANTS_DIR")
        improve(args, server)
        return 0
    if args.command == "status":
        print(json.dumps(server.livetune_state(), indent=1))
    elif args.command == "set":
        settings = dict((k, _value(v)) for k, v in (pair.split("=", 1) for pair in args.pairs))
        started = time.perf_counter()
        server.apply(settings)
        print(json.dumps({"applied": settings, "seconds": round(time.perf_counter() - started, 3)}))
    elif args.command == "load":
        phases = [loadgen.Phase(**p) for p in json.loads(Path(args.phases).read_text())]
        loadgen.run(args.url, phases, loadgen.PromptSource(_corpus(args.corpus)), log=_appender(args.out))
    elif args.command == "tune":
        grid = json.loads(Path(args.grid).read_text())
        # An `advise` report carries its live proposals as a grid.
        grid = grid["grid"] if "proposals" in grid else grid
        try:
            arrivals = trace.arrivals(list(trace.read([args.trace])), speed=args.speed) if args.trace else None
        except ValueError as exc:
            raise SystemExit(f"{args.trace}: {exc}") from exc
        profiles = json.loads(Path(args.profiles).read_text()) if args.profiles else None
        policy = tune_policy(server, Slo(args.slo_tps, args.slo_ttft), loadgen.PromptSource(_corpus(args.corpus)), grid,
                             profiles, arrivals, args.seconds, args.warmup, _appender(args.out + ".trials.jsonl", mode="w"), args.variants_dir)
        Path(args.out).write_text(policy.to_json())
        print(policy.to_json())
    elif args.command == "policy":
        slo = Slo(args.slo_tps, args.slo_ttft)
        trials = [json.loads(line) for line in Path(args.trials).read_text().splitlines() if line.strip()]
        scopes = {json.dumps(t.get("scope"), sort_keys=True) for t in trials}
        if len(scopes) != 1 or "null" in scopes:
            raise SystemExit("trials must all record the same tuning scope; rerun tune for older or mixed trial files")
        scope = trials[0]["scope"]
        start = scope["startup"]
        results = tune.best_from_trials(trials, slo, start)
        policy = tune.build_policy(results, slo, {"trials": args.trials, "scope": scope}, start, _carried(results, start, args.variants_dir))
        Path(args.out).write_text(policy.to_json())
        print(policy.to_json())
    elif args.command == "replay":
        replay(args, server)
    elif args.command == "control":
        # A missing, invalid or out-of-scope policy stays that way until a new one is released, so a
        # supervisor should not restart into the same refusal. A server that does not answer yet is
        # transient: that raises, and the supervisor retries.
        try:
            Policy.load(args.policy)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            print(f"livetune control: {args.policy}: {exc}", file=sys.stderr)
            return CONFIG_ERROR
        try:
            policy = load_policy(args.policy, server, args.allow_scope_mismatch, args.variants_dir)
        except (SystemExit, ValueError) as exc:
            print(f"livetune control: {exc}", file=sys.stderr)
            return CONFIG_ERROR
        acting = args.mode == "act"
        live = server.livetune_state()
        # policy_version is announced, never reconciled: a value left by a previous controller must not be restored.
        applied = {key: value for key, value in live["settings"].items() if key != "policy_version"}
        controller = control.Controller(policy, startup=live["startup"], applied=applied, judge_changes=acting)
        apply = server.apply if acting else (lambda settings: None)
        if acting:
            server.apply({"policy_version": policy.version})  # announce which policy this replica runs
        log = _quiet(_appender(args.log), args.log_every)
        seen = Path(args.policy).stat().st_mtime

        def scrape() -> Any:
            # A republished policy takes effect at the next window; one that fails its scope check is ignored.
            nonlocal seen
            mtime = Path(args.policy).stat().st_mtime
            if mtime != seen:
                try:
                    reloaded = load_policy(args.policy, server, args.allow_scope_mismatch, args.variants_dir)
                    # Announce the version before adopting the rules, so a replica never runs a policy
                    # under another policy's version; if this fails, nothing has changed yet.
                    if acting:
                        server.apply({"policy_version": reloaded.version})
                    controller.replace_policy(reloaded)
                    seen = mtime
                    log({"t": time.time(), "policy_reloaded": args.policy, "version": reloaded.version})
                except (SystemExit, ValueError) as exc:
                    seen = mtime  # an invalid or out-of-scope file stays invalid until it is republished
                    log({"t": time.time(), "policy_rejected": str(exc)})
                except OSError as exc:
                    log({"t": time.time(), "policy_reload_retry": str(exc)})  # transient: try again next window
            return server.scrape()

        control.run(controller, scrape, apply, window, interval_s=args.interval, log=log)
    return 0


if __name__ == "__main__":
    sys.exit(main())
