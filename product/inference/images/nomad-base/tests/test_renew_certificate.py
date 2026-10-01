import importlib.util
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import tempfile
import time
import unittest
from unittest.mock import Mock

spec = importlib.util.spec_from_file_location("renew", Path(__file__).parents[1] / "renew-certificate.py")
renew = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renew)


class RenewalTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.tls = self.root / "tls"
        self.tls.mkdir(mode=0o700)
        renew.openssl("req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256", "-nodes", "-days", "3650", "-subj", "/CN=test-ca", "-addext", "basicConstraints=critical,CA:TRUE", "-addext", "keyUsage=critical,keyCertSign,cRLSign", "-keyout", self.root / "ca.key", "-out", self.tls / "ca.pem")
        self.extensions = self.root / "extensions"
        self.extensions.write_text("subjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid,issuer\nbasicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature\nextendedKeyUsage=clientAuth,serverAuth\nsubjectAltName=DNS:client.global.nomad,DNS:localhost,IP:127.0.0.1\n")
        key = self.tls / "client-key.pem"
        renew.openssl("genpkey", "-algorithm", "EC", "-pkeyopt", "ec_paramgen_curve:P-256", "-out", key)
        public = renew.openssl("pkey", "-in", key, "-pubout").decode()
        (self.tls / "client.pem").write_text(self.sign(public, 365))
        self.config = self.root / "config.json"
        self.config.write_text(json.dumps({"instance_id": "019d5a4a-0000-7000-8000-000000000001", "nomad_node_id": "3f1e5a52-8d4b-4c1e-9a55-111111111111", "token": "t" * 43}))
        self.pid = self.root / "pid"
        self.reload = Mock()
        self.issued = 0

    def tearDown(self):
        self.temporary.cleanup()

    def sign(self, public, days=30):
        with tempfile.TemporaryDirectory(dir=self.root) as temporary:
            key = Path(temporary) / "public.pem"
            key.write_text(public)
            return renew.openssl("x509", "-new", "-force_pubkey", key, "-subj", "/CN=client.global.nomad", "-CA", self.tls / "ca.pem", "-CAkey", self.root / "ca.key", "-set_serial", str(time.time_ns()), "-days", str(days), "-extfile", self.extensions).decode()

    def issue(self, config, public_key=None, certificate=None):
        self.assertNotIn("private_key", config)
        self.assertIsNotNone(certificate)
        if public_key is None:
            return None
        self.issued += 1
        return self.sign(public_key)

    def run_once(self, issue=None, reload=None, ready=None):
        return renew.renew_once(self.tls, self.config, self.pid, issue=issue or self.issue, reload=reload or self.reload, ready=ready or Mock())

    def test_migrates_legacy_certificate_and_rotates_key_then_waits_until_day_twenty(self):
        old_key = (self.tls / "client-key.pem").read_bytes()
        self.assertTrue(self.run_once())
        self.assertNotEqual(old_key, (self.tls / "client-key.pem").read_bytes())
        renew.validate_pair(self.tls / "client.pem", self.tls / "client-key.pem", self.tls / "ca.pem")
        self.assertEqual(os.stat(self.tls / "client-key.pem").st_mode & 0o777, 0o600)
        start, end = renew.dates(self.tls / "client.pem")
        self.assertFalse(renew.needs_renewal(self.tls / "client.pem", now=start + 19 * 86400))
        self.assertTrue(renew.needs_renewal(self.tls / "client.pem", now=start + 21 * 86400))
        self.assertFalse(self.run_once())
        self.assertEqual(self.issued, 1)
        self.assertEqual(self.reload.call_count, 1)

    def test_issuer_outage_preserves_existing_key_and_certificate(self):
        key = (self.tls / "client-key.pem").read_bytes()
        certificate = (self.tls / "client.pem").read_bytes()
        with self.assertRaises(OSError):
            self.run_once(issue=Mock(side_effect=OSError("unavailable")))
        self.assertEqual(key, (self.tls / "client-key.pem").read_bytes())
        self.assertEqual(certificate, (self.tls / "client.pem").read_bytes())
        self.reload.assert_not_called()

    def test_invalid_or_wrong_key_certificates_never_replace_the_current_pair(self):
        current = (self.tls / "client.pem").read_bytes()
        for wrong in ("invalid", current.decode()):
            with self.assertRaises(Exception):
                self.run_once(issue=lambda *args, **kwargs: wrong)
            self.assertEqual(current, (self.tls / "client.pem").read_bytes())
        self.reload.assert_not_called()

    def test_reload_failure_is_retried_after_process_restart_without_reissuance(self):
        with self.assertRaises(OSError):
            self.run_once(reload=Mock(side_effect=OSError("not ready")))
        self.assertTrue((self.tls / "renewal/reload-pending").exists())
        self.assertFalse(self.run_once())
        self.assertEqual(self.issued, 1)
        self.assertFalse((self.tls / "renewal/reload-pending").exists())
        self.reload.assert_called_once()

    def test_refuses_redirects_and_unrelated_process_ids(self):
        with self.assertRaises(RuntimeError):
            renew.NoRedirect().redirect_request(None, None, 302, "", {}, "https://attacker.invalid")
        self.pid.write_text(str(os.getpid()))
        with self.assertRaises(RuntimeError):
            renew.reload_agent(self.tls, self.pid)

    def test_interrupted_path_migration_and_write_are_retryable(self):
        (self.tls / ".link-client.pem").symlink_to("missing")
        directory = self.tls / "renewal/initial"
        directory.mkdir(parents=True)
        (directory / ".write-interrupted").write_text("partial")
        self.assertTrue(self.run_once())
        renew.validate_pair(self.tls / "client.pem", self.tls / "client-key.pem", self.tls / "ca.pem")

    def test_agent_startup_failure_does_not_change_tls_files(self):
        certificate = (self.tls / "client.pem").read_bytes()
        self.pid.write_text(str(os.getpid()))
        issue = Mock()
        with self.assertRaises(RuntimeError):
            renew.renew_once(self.tls, self.config, self.pid, issue=issue)
        self.assertEqual(certificate, (self.tls / "client.pem").read_bytes())
        self.assertFalse((self.tls / "renewal").exists())
        issue.assert_not_called()

    def test_supervisor_restarts_exited_child_and_exits_on_duplicate_lock(self):
        script = (Path(__file__).parents[1] / "run-renewer.sh").read_text()
        child = self.root / "child.py"
        counter = self.root / "counter"
        child.write_text(f"from pathlib import Path\np=Path({str(counter)!r})\nif p.exists(): raise SystemExit(75)\np.write_text('started')\nraise SystemExit(1)\n")
        supervisor = self.root / "supervisor.sh"
        supervisor.write_text(script.replace("/opt/gradiated/bin/renew-certificate", str(child)).replace("sleep 60", "sleep 0.01"))
        result = subprocess.run(["bash", str(supervisor)], capture_output=True, timeout=3)
        self.assertEqual(result.returncode, 0)
        self.assertIn(b'"exit_code":1', result.stdout)

    @unittest.skipUnless(os.environ.get("NOMAD_BINARY"), "NOMAD_BINARY required for actual Nomad reload")
    def test_real_nomad_reloads_certificate_without_restarting_agent_or_other_process(self):
        config = self.root / "agent.hcl"
        config.write_text(f'''data_dir = "{self.root}/data"
bind_addr = "127.0.0.1"
advertise {{
  http = "127.0.0.1"
  rpc = "127.0.0.1"
  serf = "127.0.0.1"
}}
server {{
  enabled = true
  bootstrap_expect = 1
}}
client {{ enabled = false }}
tls {{
  http = true
  rpc = true
  ca_file = "{self.tls}/ca.pem"
  cert_file = "{self.tls}/client.pem"
  key_file = "{self.tls}/client-key.pem"
  verify_https_client = true
}}
''')
        workload = subprocess.Popen(["sleep", "120"])
        log = open(self.root / "agent.log", "wb")
        agent = subprocess.Popen([os.environ["NOMAD_BINARY"], "agent", "-config=" + str(config)], stdout=log, stderr=log)
        self.pid.write_text(str(agent.pid))
        try:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if agent.poll() is not None:
                    log.flush()
                    self.fail((self.root / "agent.log").read_text())
                try:
                    with socket.create_connection(("127.0.0.1", 4646), timeout=1):
                        break
                except OSError:
                    time.sleep(0.1)
            try:
                self.assertTrue(self.run_once(reload=renew.reload_agent, ready=renew.agent_ready))
            except Exception:
                log.flush()
                print((self.root / "agent.log").read_text()[-6000:])
                raise
            self.assertIsNone(agent.poll())
            self.assertIsNone(workload.poll())
        finally:
            agent.send_signal(signal.SIGTERM)
            workload.terminate()
            agent.wait(timeout=10)
            workload.wait(timeout=10)
            log.close()


if __name__ == "__main__":
    unittest.main()
