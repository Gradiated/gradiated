"""Deterministic scheduler, oracle-receipt and clock tests with synthetic data."""

from hashlib import sha256
from pathlib import Path
from threading import Event, enumerate as threads
from time import perf_counter_ns
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import kv260_milestones as bench

HERE = Path(__file__).resolve().parent


def plan(kind):
    return bench.read_plan(HERE/f"kv260-{kind}-v1.json")


class Clock:
    def __init__(self):
        self.value = 0

    def now(self):
        return self.value

    def wait(self, deadline):
        self.value = max(deadline,self.value)

    def serve(self, case, deadline):
        start = self.value
        self.value += 250*bench.MS
        return dict(output_ns=[start+10*bench.MS,start+20*bench.MS],
                    done_ns=start+40*bench.MS,verified_ns=self.value,
                    verification={"case":case})


class PromptCases(unittest.TestCase):
    def test_public_octets_and_encoded_geometry(self):
        natural, probes = bench.prompt_cases(plan("prompt-context"))
        lengths = sorted(len(bytes.fromhex(row["utf8_hex"])) for row in natural)
        self.assertEqual(lengths,[0,4,4,12,12,12,24,24,48,48])
        for row in natural:
            data = bytes.fromhex(row["utf8_hex"])
            self.assertEqual(row["text"].encode(),data)
            self.assertEqual(len(row["input_ids"]),1+2*len(data))
        self.assertEqual(bench.hex_prefix(b"a"),[256,278,289])
        self.assertEqual(sorted(len(p["input_ids"]) for p in probes),
                         sorted([17,65,129,193,256]*2))
        self.assertTrue(all(p["input_ids"][0] == 256 for p in probes))

    def test_rejects_overlength_and_multibyte_miscount(self):
        config = plan("prompt-context")
        config["natural"]["byte_lengths"].append(49)
        with self.assertRaises(ValueError):
            bench.prompt_cases(config)
        config = plan("prompt-context")
        config["natural"]["unicode_prompt_bytes"] -= 1
        with self.assertRaises(ValueError):
            bench.prompt_cases(config)


class OpenLoop(unittest.TestCase):
    def test_deterministic_rates_and_burst_geometry(self):
        config = plan("request-load")
        total = 0
        for index, order in enumerate(config["scenario_orders"]):
            for label, wanted in zip(("steady-1","steady-3","steady-5","burst-3"),(60,180,300,180)):
                self.assertIn(label,order)
                arrivals = bench.open_loop_arrivals(config,index,label)
                self.assertEqual(len(arrivals),wanted)
                self.assertEqual(arrivals[0]["offset_ns"],0)
                self.assertLess(arrivals[-1]["offset_ns"],60*bench.NS)
                self.assertEqual({row["case"] for row in arrivals},set(config["cases"]))
                total += wanted
        self.assertEqual(total,2_160)
        burst = bench.open_loop_arrivals(config,0,"burst-3")
        self.assertEqual([r["offset_ns"] for r in burst[:8]],[0]*4+[4*bench.NS//3]*4)

    def test_queue_full_is_not_admitted_queue_expiry_and_abort_are(self):
        arrivals = [{"index":i,"case":"fake","offset_ns":i*10} for i in range(6)]
        queue = bench.LoadQueue(arrivals,100,1,40)
        queue.offer(0,100)
        self.assertEqual(queue.take(105)["index"],0)
        queue.offer(1,110)
        queue.offer(2,120)
        queue.expire(151)
        queue.offer(3,151)
        queue.abort(152)
        self.assertEqual([r["outcome"] for r in queue.rows],
                         ["running","timed_out","rejected","aborted","not_offered","not_offered"])
        self.assertEqual(queue.rows[1]["reason"],"queue_expired")
        self.assertNotIn("admitted_ns",queue.rows[2])
        with self.assertRaises(ValueError):
            queue.offer(4,130)

    def test_request_gap_and_slo_denominator_includes_rejects(self):
        config = plan("request-load")
        m=bench.MS
        rows=[
            dict(outcome="completed",planned_ns=0,offered_ns=2*m,admitted_ns=2*m,
                 queue_depth_at_offer=0,started_ns=22*m,output_ns=[50*m,60*m,70*m],
                 verified_ns=500*m,terminal_ns=500*m),
            dict(outcome="rejected",planned_ns=960*m,offered_ns=975*m,
                 queue_depth_at_offer=4,terminal_ns=975*m),
            dict(outcome="completed",planned_ns=980*m,offered_ns=990*m,admitted_ns=990*m,
                 queue_depth_at_offer=0,started_ns=1_051*m,output_ns=[1_401*m,1_431*m],
                 verified_ns=1_801*m,terminal_ns=1_801*m),
        ]
        output = bench.summarise_load(rows,config,0,1_000*m,2_000*m)
        self.assertEqual((output["offered"],output["admitted"],output["slo_passes"]),(3,2,1))
        self.assertEqual(output["slo_pass_fraction_of_offered"],1/3)
        self.assertEqual(output["slo_goodput_per_offered_second"],1)
        self.assertEqual(output["waiting_at_offer_end"],1)
        self.assertEqual(output["active_at_offer_end"],0)
        self.assertEqual(output["unfinished_at_offer_end"],1)
        self.assertEqual(output["completed_requests_per_observed_second"],1)
        self.assertEqual(output["pooled_decode_tokens_s"],60)
        self.assertEqual(rows[0]["queue_ns"],20*m)
        self.assertEqual(rows[0]["service_first_byte_ns"],28*m)
        self.assertFalse(rows[2]["slo_pass"])

    def test_incomplete_or_late_offer_cannot_produce_capacity_goodput(self):
        config=plan("request-load")
        rows=[{"outcome":"not_offered","planned_ns":0},
              {"outcome":"rejected","planned_ns":100,"offered_ns":100*bench.MS,
               "terminal_ns":101*bench.MS,"queue_depth_at_offer":0}]
        summary=bench.summarise_load(rows,config,0,bench.NS,500*bench.MS,"producer_failed")
        self.assertFalse(summary["valid_offer_window"])
        self.assertIsNone(summary["slo_goodput_per_offered_second"])
        self.assertEqual(summary["full_observation_ns"],500*bench.MS)

    def test_threaded_producer_offers_while_serial_service_waits(self):
        config = plan("request-load")
        config.update(window_s=1,drain_s=1,queue_capacity_waiting=1,max_offer_slip_ms=500)
        rejected_while_busy = Event()
        served = []

        class SignalQueue(bench.LoadQueue):
            def offer(self,index,now_ns):
                super().offer(index,now_ns)
                if self.rows[index]["outcome"] == "rejected":
                    rejected_while_busy.set()

        def serve(case,deadline):
            if not served and not rejected_while_busy.wait(2):
                raise TimeoutError("No independent queue offer while worker was blocked")
            served.append(case)
            stamp = perf_counter_ns()
            return {"output_ns":[stamp],"done_ns":stamp,"verified_ns":stamp}

        with patch.object(bench,"LoadQueue",SignalQueue):
            result=bench.run_open_loop(config,0,"steady-5",serve,deadline_ns=perf_counter_ns()+5*bench.NS,
                                       now=perf_counter_ns)
        summary=result["summary"]
        self.assertIsNone(result["stop"])
        self.assertTrue(rejected_while_busy.is_set())
        self.assertEqual(summary["offered"],5)
        self.assertEqual(summary["admitted"],len(served))
        self.assertEqual(summary["outcomes"]["completed"]+summary["outcomes"]["rejected"],5)
        self.assertFalse(any(t.name=="kv260-open-loop-offers" for t in threads()))

    def test_failed_and_timeout_receipts_stop_service(self):
        now=Clock()
        row={"started_ns":0,"case":"fixture"}
        self.assertFalse(bench.run_service(row,now.serve,now.now,100*bench.MS))
        self.assertEqual(row["outcome"],"timed_out")
        now=Clock()
        row={"started_ns":0,"case":"fixture"}
        self.assertFalse(bench.run_service(row,lambda *_: {},now.now,bench.NS))
        self.assertEqual(row["outcome"],"failed")


class RepeatabilityAndPower(unittest.TestCase):
    def test_complete_window_segments_and_drain(self):
        config=plan("repeatability")
        config.update(duration_s=2,segment_s=1)
        clock=Clock()
        results=bench.run_repeatability(config,1,clock.serve,deadline_ns=8*bench.NS,now=clock.now)
        self.assertEqual(results["stop"],"window_end")
        self.assertEqual(len(results["requests"]),8)
        distribution=bench.repeatability_segments(results,1)
        self.assertEqual([r["completed"] for r in distribution["segments"]],[3,4])
        self.assertEqual(distribution["drained_completed"],1)
        self.assertEqual(bench.repeat_order(["a","b","c"],2),["c","a","b","b","a","c"])

    def test_early_request_cap_is_not_complete(self):
        config=plan("repeatability")
        config.update(duration_s=2,max_requests=2)
        clock=Clock()
        results=bench.run_repeatability(config,0,clock.serve,deadline_ns=8*bench.NS,now=clock.now)
        self.assertEqual(results["stop"],"request_cap")

    def test_full_long_sampler_is_bounded_on_a_synthetic_clock(self):
        config=plan("repeatability")
        clock=Clock()
        report={}
        bench.collect_power_slots(config,bench.NS,612*bench.NS,lambda:"300",clock.wait,clock.now,report)
        self.assertEqual(report["slots"],12_200)
        self.assertEqual(len(report["samples"]),12_200)
        self.assertEqual(report["end_ns"],611*bench.NS)
        self.assertFalse(report["missed"])

    def test_variable_power_envelope_integrates_all_alignment_cases(self):
        config=plan("repeatability")
        config["power"]["window_s"]=8
        clock=Clock()
        report={}
        bench.collect_power_slots(config,bench.NS,10*bench.NS,lambda:"300",clock.wait,clock.now,report)
        phases={"idle_before":(2*bench.NS,4*bench.NS),"active":(4_500*bench.MS,6*bench.NS),
                "idle_after":(6_500*bench.MS,8_500*bench.MS)}
        result=bench.summarise_power(config,report,phases,3,12)
        self.assertEqual(len(result["alignments"]),5)
        for alignment in result["alignments"].values():
            self.assertAlmostEqual(alignment["gross_j"],4.5)
            self.assertAlmostEqual(alignment["j_per_verified_completion"],1.5)
            self.assertAlmostEqual(alignment["idle_adjusted_j"],0)
        removed=report["samples"].pop(85)
        report["missed"].append({"slot":removed["slot"],"observed_ns":removed["begin_ns"]+30*bench.MS})
        with self.assertRaisesRegex(ValueError,"gap"):
            bench.summarise_power(config,report,phases,3,12)

    def test_power_integration_interpolates_inside_a_sample_interval(self):
        points=[(0,0.0),(100*bench.MS,10.0)]
        self.assertAlmostEqual(bench.integrate_power_window(points,25*bench.MS,75*bench.MS,110*bench.MS),0.25)

    def test_late_sample_and_partial_failure_are_visible(self):
        config=plan("repeatability")
        config["power"]["window_s"]=1
        clock=Clock()
        report={}
        def late(deadline):
            clock.wait(deadline+30*bench.MS if deadline==bench.NS+50*bench.MS else deadline)
        bench.collect_power_slots(config,bench.NS,3*bench.NS,lambda:"300",late,clock.now,report)
        self.assertEqual([s["slot"] for s in report["missed"]],[1])
        clock=Clock()
        bad={}
        with self.assertRaises(ValueError):
            bench.collect_power_slots(config,bench.NS,3*bench.NS,lambda:"65536",clock.wait,clock.now,bad)
        self.assertEqual(bad["samples"][0]["error"],"ValueError")


class InjectedAdapters(unittest.TestCase):
    def test_resident_uses_same_block_check_and_pins_case(self):
        calls=[]
        class Benchmark:
            def __init__(self,deadline):
                calls.append(deadline)
            def run_block(self,runner,cases,references,admit):
                admit()
                calls.append(cases)
                self_ref=references["case"]
                return {"requests":[{"case": "case","verified_ns":12,
                       "observed":{"header":{"output_ns":[5],"done_ns":10,"reference":self_ref}}}]}, {}
        serve=bench.resident_service(object(),{"case":"pinned"},Benchmark,lambda: calls.append("admit"))
        self.assertEqual(serve("case",14),{"output_ns":[5],"done_ns":10,"verified_ns":12,
                                         "verification":{"done_ns":10,"reference":"pinned"}})
        self.assertEqual(calls,[14,"admit",[("case",True)]])

    def test_teacher_probe_verifies_every_frame_and_restores_session_method(self):
        clock=Clock()
        def score_hash(token):
            return sha256(str(token).encode()).hexdigest()
        def original(token):
            clock.wait(clock.now()+3)
            return {"input_token":token,"logits_sha256":score_hash(token)}
        session=SimpleNamespace(step=original,clear=lambda: None)
        def score(tokens):
            return {"frames":[session.step(token) for token in tokens],"context_count":len(tokens),"timing":{}}
        runner=SimpleNamespace(session=session,now=clock.now,score_sequence=score)
        probe={"input_ids":[256,272,289],"final_step_window":2}
        reference=[score_hash(x) for x in probe["input_ids"]]
        result=bench.teacher_probe(runner,probe,reference,lambda fn,now,deadline,*a: fn(*a),100)
        self.assertEqual(result["step_durations_ns"],[3,3,3])
        self.assertEqual(result["final_step_median_ns"],3)
        self.assertIs(session.step,original)
        with self.assertRaises(ValueError):
            bench.teacher_probe(runner,probe,[reference[0]]*3,lambda fn,now,deadline,*a: fn(*a),100)


if __name__ == "__main__":
    unittest.main()
