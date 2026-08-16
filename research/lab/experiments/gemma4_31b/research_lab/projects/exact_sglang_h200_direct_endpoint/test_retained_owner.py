#!/usr/bin/env python3
import unittest
from pathlib import Path
P=Path(__file__).resolve().parent
class Contract(unittest.TestCase):
 def test_corrected_user_owner_and_sglang_contract(self):
  s=(P/'sglang_h200_owner.py').read_text();r=(P/'sglang_endpoint_runner.py').read_text()
  for token in ('VerifiedRetainedOwner','retained_development_window(out,events,a.deadline_epoch,600)','unit_manager=\'user\'','--kv-cache-dtype fp8_e5m2','--entrypoint bash','diagnostics(ip,out,events','scp_from') : self.assertIn(token,s)
  for token in ('threading.Barrier(32)','prompt_tokens','completion_tokens','c32_completed_requests_per_second','separate_10k_stream'): self.assertIn(token,r)
if __name__=='__main__':unittest.main()
