import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from gdecide.ensemble import combine_answer, ensemble, read_run

ROOT = Path(__file__).resolve().parents[1]


def choice(probs):
    return {"type": "choice", "choice": max(probs, key=probs.get), "probabilities": probs}


def ok(rid, answers, ms=10.0):
    return {"run_id": rid, "dataset": "D", "track": "T", "proxy_tokens": 5, "engine": "x", "status": "ok",
            "response": {"model": "x", "answers": answers}, "total_wall_ms": ms}


class CombineAnswer(unittest.TestCase):
    def test_reax_equal_average(self):
        a = combine_answer([choice({"a": .6, "b": .3, "c": .1}), choice({"a": .2, "b": .3, "c": .5})], [1, 1])
        for k, v in {"a": .4, "b": .3, "c": .3}.items():
            self.assertAlmostEqual(a["probabilities"][k], v)
        self.assertEqual(a["choice"], "a")
        self.assertAlmostEqual(math.fsum(a["probabilities"].values()), 1, places=15)

    def test_reax_noul_and_score(self):
        n = combine_answer([{"type": "noul", "noul": .2}, {"type": "noul", "noul": .8}], [.5, .5])
        self.assertEqual(n, {"type": "noul", "noul": .5})
        s = combine_answer([{"type": "score", "probabilities": {"0": .3, "1": .7}},
                            {"type": "score", "probabilities": {"0": .7, "1": .3}}], [1, 1])
        self.assertEqual(s["score"], .5)
        self.assertEqual(s["probabilities"], {"0": .5, "1": .5})

    def test_weights(self):
        a = combine_answer([choice({"a": 1.0, "b": 0.0}), choice({"a": 0.0, "b": 1.0})], [3, 1])
        self.assertAlmostEqual(a["probabilities"]["a"], .75)
        n = combine_answer([{"type": "noul", "noul": 1.0}, {"type": "noul", "noul": 0.0}], [1, 3])
        self.assertAlmostEqual(n["noul"], .25)

    def test_tie_goes_to_first_sorted_key(self):
        a = combine_answer([choice({"b": .6, "a": .4}), choice({"b": .4, "a": .6})], [1, 1])
        self.assertEqual(a["choice"], "a")

    def test_log_pool(self):
        a = combine_answer([choice({"a": .8, "b": .2}), choice({"a": .2, "b": .8})], [1, 1], "log")
        self.assertAlmostEqual(a["probabilities"]["a"], .5)
        a = combine_answer([choice({"a": .9, "b": .1}), choice({"a": .5, "b": .5})], [1, 1], "log")
        expected = math.sqrt(.45) / (math.sqrt(.45) + math.sqrt(.05))
        self.assertAlmostEqual(a["probabilities"]["a"], expected)
        n = combine_answer([{"type": "noul", "noul": .9}, {"type": "noul", "noul": .5}], [1, 1], "log")
        self.assertAlmostEqual(n["noul"], expected)
        z = combine_answer([choice({"a": 1.0, "b": 0.0}), choice({"a": .5, "b": .5})], [1, 1], "log")
        self.assertGreater(z["probabilities"]["a"], .999)

    def test_rejects_mismatch_and_invalid(self):
        with self.assertRaises(ValueError):
            combine_answer([choice({"a": .5, "b": .5}), choice({"a": .5, "c": .5})], [1, 1])
        with self.assertRaises(ValueError):
            combine_answer([choice({"a": .5, "b": .5}), {"type": "noul", "noul": .5}], [1, 1])
        with self.assertRaises(ValueError):
            combine_answer([choice({"a": .1, "b": .1}), choice({"a": .5, "b": .5})], [1, 1])
        with self.assertRaises(ValueError):
            combine_answer([choice({"a": float("nan"), "b": .5}), choice({"a": .5, "b": .5})], [1, 1])


class Ensemble(unittest.TestCase):
    def runs(self):
        a = {"r1": ok("r1", {"q": choice({"x": .9, "y": .1})}, 5),
             "r2": ok("r2", {"q": {"type": "noul", "noul": .2}}),
             "r3": {"run_id": "r3", "status": "unsupported", "error": "too long"},
             "r4": {"run_id": "r4", "status": "error", "error": "boom"}}
        b = {"r1": ok("r1", {"q": choice({"x": .1, "y": .9})}, 7),
             "r2": {"run_id": "r2", "status": "unsupported", "error": "too long"},
             "r3": ok("r3", {"q": choice({"x": .3, "y": .7}), "p": {"type": "noul", "noul": .6}}),
             "r4": {"run_id": "r4", "status": "unsupported", "error": "too long"},
             "r5": ok("r5", {"q": {"type": "noul", "noul": .4}})}
        return a, b

    def test_fallback_and_union(self):
        records, stats = ensemble(list(self.runs()), [.5, .5])
        by = {r["run_id"]: r for r in records}
        self.assertEqual(list(by), ["r1", "r2", "r3", "r4", "r5"])
        self.assertAlmostEqual(by["r1"]["response"]["answers"]["q"]["probabilities"]["x"], .5)
        self.assertEqual(by["r1"]["total_wall_ms"], 7)
        self.assertEqual(by["r1"]["dataset"], "D")
        self.assertAlmostEqual(by["r2"]["response"]["answers"]["q"]["noul"], .2)
        self.assertEqual(by["r3"]["response"]["answers"]["p"]["noul"], .6)
        self.assertEqual(by["r4"]["status"], "error")
        self.assertEqual(by["r5"]["status"], "ok")
        self.assertEqual(stats, {"rows": 5, "all": 1, "partial_rows": 3, "partial_questions": 0, "none": 1, "by_member": [2, 3]})

    def test_partial_question(self):
        a = {"r": ok("r", {"q": choice({"x": .9, "y": .1})})}
        b = {"r": ok("r", {"q": choice({"x": .5, "y": .5}), "p": {"type": "noul", "noul": .3}})}
        records, stats = ensemble([a, b], [1, 3])
        answers = records[0]["response"]["answers"]
        self.assertAlmostEqual(answers["q"]["probabilities"]["x"], .6)
        self.assertEqual(answers["p"]["noul"], .3)
        self.assertEqual(stats["partial_questions"], 1)

    def test_bad_weights(self):
        with self.assertRaises(ValueError):
            ensemble(list(self.runs()), [1])
        with self.assertRaises(ValueError):
            ensemble(list(self.runs()), [0, 0])

    def test_cli_writes_scoreable_run(self):
        a, b = self.runs()
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "a").mkdir()
            (tmp / "a" / "results-0.jsonl").write_text("".join(json.dumps(r) + "\n" for r in list(a.values())[:2]))
            (tmp / "a" / "results-1.jsonl").write_text("".join(json.dumps(r) + "\n" for r in list(a.values())[2:]) + "{trunc")
            (tmp / "b.jsonl").write_text("".join(json.dumps(r) + "\n" for r in b.values()))
            subprocess.run([sys.executable, "-m", "gdecide.ensemble", "--runs", str(tmp / "a"), str(tmp / "b.jsonl"),
                            "--out", str(tmp / "e"), "--weights", "1", "1"], check=True, cwd=ROOT, capture_output=True)
            self.assertEqual(len(read_run(tmp / "a")), 4)
            merged = read_run(tmp / "e")
            self.assertEqual(len(merged), 5)
            self.assertEqual((tmp / "e" / "results.jsonl").read_text(), (tmp / "e" / "results-0.jsonl").read_text())
            self.assertEqual(json.loads((tmp / "e" / "ensemble.json").read_text())["weights"], [1.0, 1.0])


if __name__ == "__main__":
    unittest.main()
