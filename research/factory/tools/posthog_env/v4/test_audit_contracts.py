"""Synthetic audit admission regressions; no database or model calls."""

import copy
import unittest

import audit_contracts as AC


class AuditAdmission(unittest.TestCase):
    def setUp(self):
        self.base = {"twin_id": "synthetic", "team_id": 7, "loaded_now_utc": "2026-11-01", "shift_days": 5}
        self.rec = {"verdict": "CLEAN", "defects": [], "queries_run": [{"result": "[[12]]"}],
                    "snapshot": AC.snapshot(self.base), "cache_key": AC.cache_key(self.base, "author")}

    def test_complete_audit_is_reusable_and_admissible(self):
        self.assertTrue(AC.reusable(self.rec, self.base, "author"))
        self.assertTrue(AC.admissible(self.rec, self.base))

    def test_failures_and_unqueried_verdicts_are_retried(self):
        for update in ({"error": "429"}, {"verdict": None}, {"queries_run": []},
                       {"queries_run": [{"result": "ERROR timeout"}]}, {"queries_run": [{"result": "REJECTED"}]},
                       {"defects": None}):
            rec = {**self.rec, **update}
            self.assertFalse(AC.reusable(rec, self.base, "author"), update)
            self.assertFalse(AC.admissible(rec, self.base), update)

    def test_reloaded_reanchored_and_different_model_caches_expire(self):
        for key, value in (("team_id", 8), ("loaded_now_utc", "2026-11-02"), ("shift_days", 6)):
            base = {**self.base, key: value}
            self.assertFalse(AC.reusable(self.rec, base, "author"))
            self.assertFalse(AC.admissible(self.rec, base))
        self.assertFalse(AC.reusable(self.rec, self.base, "new-author"))

    def test_clean_label_cannot_hide_material_defects(self):
        rec = copy.deepcopy(self.rec)
        rec["defects"] = [{"severity": "material", "what": "shared identities", "evidence": "query -> 12"}]
        self.assertFalse(AC.completed(rec))
        rec["verdict"] = "MATERIAL"
        self.assertTrue(AC.completed(rec))
        self.assertFalse(AC.admissible(rec, self.base))

    def test_minor_defects_need_evidence_and_consistent_label(self):
        rec = {**self.rec, "verdict": "MINOR", "defects": [{"severity": "minor", "what": "rare gap"}]}
        self.assertFalse(AC.completed(rec))
        rec["defects"][0]["evidence"] = "query -> 1"
        self.assertTrue(AC.admissible(rec, self.base))

    def test_legacy_verdict_only_cache_cannot_admit_twin(self):
        self.assertFalse(AC.admissible({"verdict": "CLEAN", "defects": []}, self.base))


if __name__ == "__main__":
    unittest.main()
