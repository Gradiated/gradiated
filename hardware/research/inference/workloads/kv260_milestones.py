"""Prepare milestone inputs and time one serial service supplied by an owner.

This module has no board or model entry point. An admitted supervisor supplies
one callback that runs and verifies a request before returning its receipt.
"""

from bisect import bisect_right
from collections import Counter, deque
from itertools import groupby
from pathlib import Path
import json
from statistics import median
from threading import Condition, Event, Thread
from unittest.mock import patch

NS = 1_000_000_000
MS = 1_000_000
CONTEXT = 256
BOS = 256
HEX_LIMIT = 48
OUTCOMES = ("completed", "rejected", "timed_out", "failed", "aborted", "not_offered")


def read_plan(path):
    plan = json.loads(Path(path).read_text())
    if (plan["schema_version"] != 1 or plan["implementation"] != "scalar-div-v1"
            or plan["model"] != "chip-joke-text-20261109"):
        raise ValueError("Unexpected milestone geometry or selected baseline")
    return plan


def hex_prefix(data):
    """The frozen model's two nibble IDs per byte, with their distinct bases."""
    return [BOS, *[token for byte in data for token in (272 + (byte >> 4), 288 + (byte & 15))]]


def prompt_cases(plan):
    natural, fixed = plan["natural"], plan["teacher_forced"]
    if plan["context_limit"] != CONTEXT or not 1 <= natural["max_output_tokens"] < CONTEXT:
        raise ValueError("Unexpected context or output cap")
    lengths = natural["byte_lengths"]
    contexts = fixed["context_lengths"]
    if (lengths != sorted(set(lengths)) or not all(0 < length <= HEX_LIMIT for length in lengths)
            or contexts != sorted(set(contexts))
            or not all(fixed["final_step_window"] <= length <= CONTEXT for length in contexts)):
        raise ValueError("Invalid prompt or diagnostic work length")

    def natural_case(name, text):
        data = text.encode("utf-8")
        if len(data) > HEX_LIMIT:
            raise ValueError(f"Natural prompt exceeds the sealed interface: {name}")
        return {"id": name, "text": text, "utf8_hex": data.hex(), "input_ids": hex_prefix(data),
                "max_output_tokens": natural["max_output_tokens"]}

    cases, probes = [], []
    if natural["include_bos_only"]:
        cases.append(natural_case("bos-only", ""))
    for family, text in natural["families"].items():
        if not text.isascii() or len(text) < max(lengths):
            raise ValueError("Length ladders require complete ASCII source prefixes")
        for length in lengths:
            cases.append(natural_case(f"{family}-{length}b", text[:length]))
        prefix = hex_prefix(text.encode("ascii") * CONTEXT)
        for length in contexts:
            probes.append({"id": f"{family}-{length}ids", "input_ids": prefix[:length],
                           "final_step_window": fixed["final_step_window"]})
    unicode = natural_case("utf8-multibyte", natural["unicode_prompt"])
    if len(bytes.fromhex(unicode["utf8_hex"])) != natural["unicode_prompt_bytes"]:
        raise ValueError("Expected exact multibyte prompt length")
    cases.append(unicode)
    payloads = (cases, probes)
    for rows, key in zip(payloads, ("utf8_hex", "input_ids"), strict=True):
        if len({tuple(row[key]) for row in rows}) != len(rows):
            raise ValueError("Repeated input within one workload")
    return cases, probes


def open_loop_arrivals(plan, repetition, scenario):
    order = plan["scenario_orders"]
    if not 0 <= repetition < len(order) or scenario not in order[repetition]:
        raise ValueError("Unexpected scenario or repetition")
    spec = plan["scenarios"][scenario]
    rate, simultaneous = spec["rate_per_s"], spec["simultaneous"]
    if type(rate) is not int or rate <= 0 or type(simultaneous) is not int or simultaneous <= 0:
        raise ValueError("Expected a positive integral arrival schedule")
    cases = plan["cases"]
    if not cases or len(set(cases)) != len(cases):
        raise ValueError("Expected distinct load cases")
    if plan["worker_count"] != 1 or not 1 <= plan["queue_capacity_waiting"] <= 16:
        raise ValueError("This load harness supports one bounded serial service")
    count = plan["window_s"] * rate
    if not 1 <= count <= 1_000 or count % simultaneous:
        raise ValueError("Scope exceeds the arrival budget or cuts a burst")
    return [{"index": i, "case": cases[(i+repetition) % len(cases)],
             "offset_ns": (i//simultaneous)*simultaneous*NS//rate} for i in range(count)]


class LoadQueue:
    """Record waiting slots separately from the single active request."""

    def __init__(self, arrivals, start_ns, capacity, expiry_ns):
        self.rows = [dict(row, planned_ns=start_ns+row["offset_ns"], outcome="not_offered")
                     for row in arrivals]
        self.pending = deque()
        self.capacity = capacity
        self.expiry_ns = expiry_ns

    def expire(self, now_ns):
        while self.pending and self.pending[0]["queue_deadline_ns"] <= now_ns:
            row = self.pending.popleft()
            row.update(outcome="timed_out", reason="queue_expired", terminal_ns=now_ns)

    def offer(self, index, now_ns):
        row = self.rows[index]
        if row["outcome"] != "not_offered" or now_ns < row["planned_ns"]:
            raise ValueError("Offer chronology differs from the frozen schedule")
        self.expire(now_ns)
        row.update(offered_ns=now_ns, queue_depth_at_offer=len(self.pending),
                   queue_deadline_ns=row["planned_ns"]+self.expiry_ns)
        if now_ns >= row["queue_deadline_ns"] or len(self.pending) >= self.capacity:
            reason = "producer_late" if now_ns >= row["queue_deadline_ns"] else "queue_full"
            row.update(outcome="rejected", reason=reason, terminal_ns=now_ns)
        else:
            row.update(outcome="waiting", admitted_ns=now_ns)
            self.pending.append(row)

    def take(self, now_ns):
        self.expire(now_ns)
        if not self.pending:
            return None
        row = self.pending.popleft()
        row.update(outcome="running", started_ns=now_ns)
        return row

    def abort(self, now_ns):
        self.expire(now_ns)
        while self.pending:
            self.pending.popleft().update(outcome="aborted", reason="session_stopped", terminal_ns=now_ns)


def verified_receipt(receipt, start, deadline, now_ns):
    output_times = receipt["output_ns"]
    verified = receipt["verified_ns"]
    stamps = [start, *output_times, receipt["done_ns"], verified, now_ns]
    if not all(type(value) is int for value in stamps) or stamps != sorted(stamps):
        raise ValueError("Service timestamps do not share a monotonic clock")
    if verified >= deadline:
        raise TimeoutError("Verified service exceeded its deadline")
    if any(a >= b for a, b in zip(output_times, output_times[1:])):
        raise ValueError("Output arrival timestamps must increase")
    trace = {"output_ns": list(output_times), "done_ns": receipt["done_ns"],
             "verified_ns": verified, "useful_output_tokens": len(output_times)}
    if "verification" in receipt:
        trace["verification"] = receipt["verification"]
    return trace


def run_service(row, serve, now, deadline):
    try:
        trace = verified_receipt(serve(row["case"], deadline), row["started_ns"], deadline, now())
    except (TimeoutError, OSError, RuntimeError, ValueError, TypeError, KeyError) as error:
        timed_out = isinstance(error, TimeoutError) or now() >= deadline
        row.update(outcome="timed_out" if timed_out else "failed", terminal_ns=now(),
                   reason=f"service_{type(error).__name__}", error=str(error))
        return False
    row.update(trace, outcome="completed", terminal_ns=trace["verified_ns"])
    return True


def run_open_loop(plan, repetition, scenario, serve, *, deadline_ns, now):
    """Drive a local, bounded queue. Only the caller invokes the service.

    `serve(case, deadline_ns)` returns an exact-verified receipt. Its native
    deadlines and the outer process watchdog must also be enforced by the
    board supervisor. Pass the same `runner.now` callable used by delivery.
    The producer never invokes the service.
    """
    if not (0 < plan["window_s"] <= 60 and 0 < plan["drain_s"] <= 10
            and 0 < plan["service_timeout_ms"] <= 3000 and 0 < plan["queue_expiry_ms"] <= 2000):
        raise ValueError("Load window, drain or request deadline exceeds the prepared envelope")
    arrivals = open_loop_arrivals(plan, repetition, scenario)
    started_ns = now() + 100*MS
    end_ns = started_ns + plan["window_s"]*NS
    wall_end = end_ns + plan["drain_s"]*NS
    if wall_end > deadline_ns:
        raise ValueError("Insufficient absolute deadline for the offer window and drain")
    queue = LoadQueue(arrivals, started_ns, plan["queue_capacity_waiting"], plan["queue_expiry_ms"]*MS)
    condition = Condition()
    stop = Event()
    producer_done = False
    producer_errors = []

    def producer():
        nonlocal producer_done
        try:
            for due, same_time in groupby(queue.rows, key=lambda row: row["planned_ns"]):
                while (remaining := due-now()) > 0 and not stop.is_set():
                    stop.wait(remaining/NS)
                with condition:
                    offered = now()
                    if stop.is_set() or offered >= end_ns:
                        break
                    for row in same_time:
                        queue.offer(row["index"], offered)
                    condition.notify()
        except Exception as error:
            producer_errors.append(error)
            stop.set()
        finally:
            with condition:
                producer_done = True
                condition.notify()

    thread = Thread(target=producer, name="kv260-open-loop-offers", daemon=True)
    thread.start()
    stopped = None
    try:
        while True:
            with condition:
                current = now()
                if current >= wall_end:
                    stopped = "drain_deadline"
                    break
                if stop.is_set():
                    stopped = "producer_failed"
                    break
                row = queue.take(current)
                if row is None:
                    if producer_done:
                        break
                    condition.wait((wall_end-current)/NS)
                    continue
            limit = min(wall_end, row["started_ns"]+plan["service_timeout_ms"]*MS)
            if not run_service(row, serve, now, limit):
                stopped = "service_failed"
                break
    finally:
        stop.set()
        thread.join(timeout=max(0, (wall_end-now())/NS))
        with condition:
            queue.abort(now())
    if thread.is_alive() or producer_errors:
        stopped = "producer_failed"
    if stopped is None and (remaining := end_ns-now()) > 0:
        Event().wait(remaining/NS)
    finished_ns = now()
    return {"rows": queue.rows, "stop": stopped,
            "summary": summarise_load(queue.rows, plan, started_ns, end_ns, finished_ns, stopped)}


def summarise_load(rows, plan, started_ns, end_ns, finished_ns, stopped=None):
    counts = Counter(row["outcome"] for row in rows)
    if set(counts)-set(OUTCOMES) or started_ns >= end_ns:
        raise ValueError("Load evidence must contain terminal outcomes and a finite offer window")
    offered = sum("offered_ns" in row for row in rows)
    admitted = sum("admitted_ns" in row for row in rows)
    if (offered != len(rows)-counts["not_offered"] or
            admitted != offered-counts["rejected"]):
        raise ValueError("Offer/admission counts cannot be reconciled")
    good = output = decode_count = decode_ns = waiting_at_end = active_at_end = 0
    lags, early_waiting, late_waiting = [], [], []
    quarter = (end_ns-started_ns)//4
    limits = plan["slo"]
    for row in rows:
        if "offered_ns" in row:
            lags.append(row["offered_ns"]-row["planned_ns"])
            if row["planned_ns"] < started_ns+quarter:
                early_waiting.append(row["queue_depth_at_offer"])
            elif row["planned_ns"] >= end_ns-quarter:
                late_waiting.append(row["queue_depth_at_offer"])
        if "admitted_ns" in row and row["admitted_ns"] < end_ns <= row["terminal_ns"]:
            if row.get("started_ns",end_ns) >= end_ns:
                waiting_at_end += 1
            else:
                active_at_end += 1
        if "started_ns" in row:
            row["queue_ns"] = row["started_ns"]-row["offered_ns"]
        if row["outcome"] != "completed":
            continue
        times = row["output_ns"]
        output += len(times)
        row["verified_service_ns"] = row["verified_ns"]-row["started_ns"]
        row["planned_to_verified_ns"] = row["verified_ns"]-row["planned_ns"]
        row["offer_to_verified_ns"] = row["verified_ns"]-row["offered_ns"]
        row["service_first_byte_ns"] = times[0]-row["started_ns"] if times else None
        row["planned_first_byte_ns"] = times[0]-row["planned_ns"] if times else None
        row["offer_first_byte_ns"] = times[0]-row["offered_ns"] if times else None
        row["decode_tokens_s"] = (len(times)-1)*NS/(times[-1]-times[0]) if len(times)>1 else None
        if len(times)>1:
            decode_count += len(times)-1
            decode_ns += times[-1]-times[0]
        ok = bool(times and row["planned_first_byte_ns"] <= limits["first_byte_ms"]*MS
                  and row["planned_to_verified_ns"] <= limits["verified_completion_ms"]*MS)
        row["slo_pass"] = ok
        good += ok
    valid = (stopped is None and offered > 0 and offered == len(rows) and finished_ns >= end_ns
             and max(lags) <= plan["max_offer_slip_ms"]*MS)
    waiting_growth = (sum(late_waiting)/len(late_waiting)-sum(early_waiting)/len(early_waiting)
                      if early_waiting and late_waiting else None)
    observed_ns = max(0, finished_ns-started_ns)
    return {"planned": len(rows), "offered": offered, "admitted": admitted,
            "submitted": offered, "outcomes": {name: counts[name] for name in OUTCOMES},
            "max_offer_slip_ns": max(lags,default=None), "waiting_at_offer_end": waiting_at_end,
            "active_at_offer_end": active_at_end, "unfinished_at_offer_end": waiting_at_end+active_at_end,
            "late_minus_early_mean_waiting": waiting_growth,
            "offered_window_ns": end_ns-started_ns, "full_observation_ns": observed_ns,
            "slo_passes": good, "slo_pass_fraction_of_offered": good/offered if offered else None,
            "slo_goodput_per_offered_second": good*NS/(end_ns-started_ns) if valid else None,
            "completed_requests_per_observed_second": counts["completed"]*NS/observed_ns if observed_ns else None,
            "useful_output_tokens": output, "useful_output_per_observed_second": output*NS/observed_ns if observed_ns else None,
            "pooled_decode_tokens_s": decode_count*NS/decode_ns if decode_ns else None,
            "valid_offer_window": valid,
            "passes_initial_slo_screen": valid and good/offered >= limits["min_fraction_of_offered"]
                                        and waiting_at_end <= limits["max_waiting_at_offer_end"]
                                        and waiting_growth is not None
                                        and waiting_growth <= limits["max_late_minus_early_mean_waiting"]}


def repeat_order(cases, session):
    """Each case appears twice per cycle, in rotating and reverse positions."""
    at = session % len(cases)
    forward = cases[at:] + cases[:at]
    return forward + list(reversed(forward))


def run_repeatability(plan, session, serve, *, deadline_ns, now):
    if not (0 <= session < plan["sessions"] <= 3 and plan["cases"]
            and 0 < plan["duration_s"] <= 600 and 0 < plan["service_timeout_ms"] <= 3000
            and 0 < plan["max_requests"] <= 3600):
        raise ValueError("Repeatability session exceeds the prepared envelope")
    began = now()
    end = began + plan["duration_s"]*NS
    if deadline_ns < end + plan["service_timeout_ms"]*MS:
        raise ValueError("Absolute deadline cannot accommodate the window and bounded drain")
    pattern = repeat_order(plan["cases"],session)
    requests = []
    reason = "request_cap"
    for index in range(plan["max_requests"]):
        began_request = now()
        if began_request >= end:
            reason = "window_end"
            break
        row = {"case": pattern[index%len(pattern)], "index": index, "started_ns": began_request}
        requests.append(row)
        until = min(deadline_ns,began_request+plan["service_timeout_ms"]*MS)
        if not run_service(row,serve,now,until):
            reason = "service_failed"
            break
    finished = now()
    if reason == "request_cap" and finished >= end:
        reason = "window_end"
    return {"began_ns": began, "admission_end_ns": end, "finished_ns": finished,
            "stop": reason, "requests": requests}


def repeatability_segments(record, segment_s):
    start, end = record["began_ns"], record["admission_end_ns"]
    width = segment_s*NS
    if width <= 0 or end <= start or (end-start)%width:
        raise ValueError("Expected complete fixed-duration segment boundaries")
    segments = [[] for _ in range((end-start)//width)]
    drained = []
    for row in record["requests"]:
        if row["outcome"] != "completed":
            continue
        finish = row["verified_ns"]
        if not start <= finish <= record["finished_ns"]:
            raise ValueError("Completion outside the recorded session")
        if finish >= end:
            drained.append(row)
        else:
            segments[(finish-start)//width].append(row)
    return {"segments": [{"completed":len(rows),
                          "output_tokens":sum(row["useful_output_tokens"] for row in rows),
                          "median_verified_service_ns":median(row["verified_ns"]-row["started_ns"] for row in rows)
                                                          if rows else None}
                         for rows in segments], "drained_completed":len(drained)}


def resident_service(runner, references, make_benchmark, admit):
    """Reuse the admitted DeliveryBenchmark path, including exact checking."""
    def serve(case, deadline_ns):
        benchmark = make_benchmark(deadline_ns)
        block, _ = benchmark.run_block(runner, [(case, True)], references, admit)
        row, = block["requests"]
        if row["case"] != case:
            raise ValueError("Exact service returned the wrong workload case")
        header = row["observed"]["header"]
        return {"output_ns": header["output_ns"], "done_ns": header["done_ns"],
                "verified_ns": row["verified_ns"],
                "verification": {key: value for key,value in header.items() if key != "output_ns"}}

    return serve


def teacher_probe(runner, probe, expected_hashes, call_before, deadline_ns):
    """Time legacy token steps and verify every signed-score frame by hash."""
    tokens = probe["input_ids"]
    if not 1 <= probe["final_step_window"] <= len(tokens) <= CONTEXT:
        raise ValueError("Invalid fixed score-step window")
    if len(expected_hashes) != len(tokens) or any(
        len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest) for digest in expected_hashes
    ):
        raise ValueError("Exactly one SHA-256 reference digest per step is required")
    original_step, original_clear = runner.session.step, runner.session.clear
    durations = []

    def step(token_id):
        began = runner.now()
        result = call_before(original_step, runner.now, deadline_ns, token_id)
        durations.append(runner.now()-began)
        return result

    with (patch.object(runner.session, "step", step),
          patch.object(runner.session, "clear",
                       lambda: call_before(original_clear,runner.now,deadline_ns))):
        result = runner.score_sequence(tokens)
    if runner.now() >= deadline_ns:
        raise TimeoutError("Legacy probe reached its verification deadline")
    if (result["context_count"] != len(tokens) or len(durations) != len(tokens)
            or [f["input_token"] for f in result["frames"]] != tokens
            or [f["logits_sha256"] for f in result["frames"]] != list(expected_hashes)):
        raise ValueError("Legacy score-step probe differs from its pinned reference")
    return {"step_durations_ns":durations,"context_count":result["context_count"],"timing":result["timing"],
            "final_step_median_ns":median(durations[-probe["final_step_window"]:])}


def collect_power_slots(plan, start_ns, deadline_ns, read_raw, wait_until, now, report):
    """Collect bounded prospective 20 Hz slots with injected, qualified I/O.

    The enclosing unprivileged sampler owns sensor identity checks and the
    external watchdog. The caller retains this report even after an I/O error.
    """
    power = plan["power"]
    period = power["period_ms"]*MS
    if period != 50*MS or type(power["window_s"]) is not int or not 1 <= power["window_s"] <= 610:
        raise ValueError("Invalid fixed 20 Hz sampling envelope")
    slots = power["window_s"]*NS//period
    end_ns = start_ns+slots*period
    if end_ns > deadline_ns or now() >= start_ns:
        raise ValueError("Unbounded or already started power sample schedule")
    if report:
        raise ValueError("Expected a fresh power report")
    report.update(start_ns=start_ns,end_ns=None,period_ns=period,slots=slots,samples=[],missed=[])
    try:
        for slot in range(slots):
            planned = start_ns+slot*period
            wait_until(planned)
            before = now()
            if before < planned or before >= deadline_ns:
                raise TimeoutError("Power collector clock or deadline failed")
            if before-planned >= period//2:
                report["missed"].append({"slot":slot,"observed_ns":before})
                continue
            row = {"slot":slot,"begin_ns":before}
            report["samples"].append(row)
            try:
                value = read_raw()
                after = now()
                if (not isinstance(value,str) or not 1 <= len(value) <= 5
                        or not value.isascii() or not value.isdecimal() or int(value)>65_535):
                    raise ValueError("Invalid INA260 raw-count reading")
                if not before <= after < deadline_ns:
                    raise TimeoutError("Power read exceeded its deadline")
                row.update(end_ns=after,raw=value)
            except Exception as error:
                row.update(end_ns=now(),error=type(error).__name__)
                raise
        wait_until(end_ns)
        if not end_ns <= now() <= deadline_ns:
            raise TimeoutError("Unbounded or incomplete power interval")
    finally:
        report["end_ns"] = now()


def admitted_power_samples(plan, report):
    """Verify the variable-length slot trace before using any electrical data."""
    period = plan["power"]["period_ms"]*MS
    start, end = report["start_ns"], report["end_ns"]
    slots = plan["power"]["window_s"]*NS//period
    if period != 50*MS or not 1 <= slots <= 12_200 or report["period_ns"] != period or report["slots"] != slots:
        raise ValueError("Power trace schedule differs from its plan")
    if type(end) is not int or end < start+slots*period:
        raise ValueError("Incomplete power trace")
    samples, missed = report["samples"], report["missed"]
    if sorted(row["slot"] for row in samples+missed) != list(range(slots)):
        raise ValueError("Power slots are missing or repeated")
    last = start
    for row in samples:
        due = start+row["slot"]*period
        value = row.get("raw", "")
        begin, finish = row["begin_ns"], row["end_ns"]
        if ("error" in row or not last <= begin <= finish <= end or not 0 <= begin-due < period//2
                or not isinstance(value,str) or not 1 <= len(value) <= 5
                or not value.isascii() or not value.isdecimal() or int(value)>65_535):
            raise ValueError("Invalid sampled power slot")
        last = finish
    for row in missed:
        due = start+row["slot"]*period
        if not due+period//2 <= row["observed_ns"] <= end:
            raise ValueError("Invalid missed power slot")
    return samples


def integrate_power_window(points, begin_ns, end_ns, max_gap_ns):
    """Integrate interpolated watts over bracketed monotonic nanoseconds."""
    times = [time for time,_ in points]
    i, j = bisect_right(times,begin_ns)-1, bisect_right(times,end_ns-1)
    if begin_ns >= end_ns or i < 0 or j >= len(times):
        raise ValueError("Power samples do not bracket the measurement")
    joules = 0.0
    for k in range(i,j):
        t0,p0 = points[k]
        t1,p1 = points[k+1]
        if not 0 < t1-t0 <= max_gap_ns:
            raise ValueError("Power sample gap exceeds the admitted limit")
        a,b = max(begin_ns,t0),min(end_ns,t1)
        if a < b:
            p_a = p0+(p1-p0)*(a-t0)/(t1-t0)
            p_b = p0+(p1-p0)*(b-t0)/(t1-t0)
            joules += (p_a+p_b)*(b-a)/(2*NS)
    return joules


def summarise_power(plan, trace, phases, completions, output_tokens):
    """Analyse VCC_SOM with the same five alignment checks as the paired runs."""
    before, active, after = (phases[key] for key in ("idle_before","active","idle_after"))
    if (before[1]-before[0] != 2*NS or after[1]-after[0] != 2*NS
            or before[1]+500*MS > active[0] or active[0] >= active[1]
            or active[1]+500*MS > after[0] or completions < 0 or output_tokens < 0):
        raise ValueError("Incorrect power windows or denominators")
    samples = admitted_power_samples(plan,trace)
    gap = plan["power"]["max_gap_ms"]*MS
    if not 0 < gap <= 75*MS:
        raise ValueError("Power gap allowance exceeds the qualified method")
    summary = {}
    seconds = (active[1]-active[0])/NS
    for name,start_weight,offset in (
        ("midpoint",1,0),("read_start",2,0),("read_end",0,0),
        ("midpoint_minus_50ms",1,-50*MS),("midpoint_plus_50ms",1,50*MS)
    ):
        points = [((row["begin_ns"]*start_weight+row["end_ns"]*(2-start_weight))//2+offset,
                   int(row["raw"])/100) for row in samples]
        if any(a[0] >= b[0] for a,b in zip(points,points[1:])):
            raise ValueError("Non-monotonic power sample alignment")
        idle0,gross,idle1 = [integrate_power_window(points,*interval,gap) for interval in (before,active,after)]
        idle_w = [idle0/2,idle1/2]
        summary[name] = {"gross_j":gross,"active_w":gross/seconds,"idle_w":idle_w,
                         "idle_adjusted_j":gross-sum(idle_w)/2*seconds,
                         "j_per_verified_completion":gross/completions if completions else None,
                         "j_per_output_token":gross/output_tokens if output_tokens else None,
                         "output_tokens_per_joule":output_tokens/gross if gross else None}
    return {"boundary":"VCC_SOM","alignments":summary,"active_ns":active[1]-active[0]}
