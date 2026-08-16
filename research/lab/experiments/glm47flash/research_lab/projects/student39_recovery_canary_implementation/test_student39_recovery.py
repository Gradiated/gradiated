import json, tempfile, unittest
import student39_recovery as r

class RecoveryContractTests(unittest.TestCase):
    def test_source_binding_and_two_step_resume(self):
        with tempfile.TemporaryDirectory() as d:
            x=r.tiny_run(d)
            self.assertEqual(x["optimizer_steps"],2)
            self.assertTrue(x["checkpoint_reload"])
            self.assertEqual(x["resume_step"],3)
            self.assertTrue(all(m["loss"]>0 for m in x["history"]))

    def test_negative_controls_fail_closed(self):
        for field, value in [("mapping_sha256","drift"),("teacher_revision","drift"),("top64_logits_bf16",[1])]:
            with self.subTest(field=field):
                rec=r.cache_record(); rec[field]=value
                with self.assertRaises(ValueError): r.validate_cache(rec)
        with self.assertRaises(ValueError): r.validate_cache({"optimizer":{"step":9}})

    def test_real_runtime_is_explicitly_not_silent(self):
        try: r.require_runtime()
        except RuntimeError as e: self.assertIn("REAL_RUNTIME_UNAVAILABLE",str(e))
        else: self.fail("host unexpectedly has production runtime; test should be updated")

if __name__=="__main__": unittest.main()
