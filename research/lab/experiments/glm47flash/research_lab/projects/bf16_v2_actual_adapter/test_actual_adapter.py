#!/usr/bin/env python3
import json
import os
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import actual_adapter as a


def fixture(root: Path, phase: int = 1, *, missing=None, revision=a.MODEL_REVISION) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    vals = {n: {} for n in a.REQUIRED if n != missing}
    vals["identity-manifest.json"] = {"model_revision": revision}
    for name, value in vals.items(): (root / name).write_text(json.dumps(value) + "\n")
    return root


class Backend:
    def __init__(self, root, *, failure=None, cleanup=True): self.root=root; self.failure=failure; self.cleanup_ok=cleanup; self.created=False
    def create(self, name, disk, cloud): self.created=True; return "instance-1"
    def address(self, instance): return "203.0.113.10"
    def bootstrap(self, ip): pass
    def transfer(self, ip, model): pass
    def capture(self, ip, phase, deadline, script):
        if self.failure == "remote" and phase == 2: raise a.AdapterError("authorization=SECRET should redact")
        return self.root / f"remote-{phase}"
    def retrieve(self, remote, destination):
        phase=int(remote.name.split("-")[-1]); fixture(destination, phase, missing="capture-result.json" if self.failure == "missing" and phase == 2 else None, revision="wrong" if self.failure == "identity" and phase == 2 else a.MODEL_REVISION)
    def delete(self, instance, disk): return {"pass": self.cleanup_ok, "direct_absent": self.cleanup_ok, "inventory_absent": self.cleanup_ok}


class AdapterTests(unittest.TestCase):
    def test_dry_run_mutation_spy(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); model=root/"model"; model.mkdir()
            (model/"model-files-manifest.json").write_text(json.dumps({"revision":a.MODEL_REVISION,"shard_count":a.SHARDS,"weight_bytes":a.WEIGHT_BYTES})+"\n")
            spec=root/"spec"; spec.write_text(json.dumps({"runtime_identity":{"model_revision":a.MODEL_REVISION},"captures":{"count":3,"absolute_session_timeout_seconds":3600}})+"\n")
            suite=root/"suite"; suite.write_text(json.dumps({"case_count":36})+"\n"); script=root/"remote.sh"; script.write_text("true\n")
            spy=Backend(root/"spy")
            result=a.run(spy, output=root/"out", name="n", model_dir=model, spec=spec, suite_manifest=suite, remote_script=script, dry_run=True)
            self.assertTrue(result["pass"]); self.assertFalse(spy.created)

    def test_all_failure_fixtures_and_success(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); model=root/"model"; model.mkdir()
            (model/"model-files-manifest.json").write_text(json.dumps({"revision":a.MODEL_REVISION,"shard_count":a.SHARDS,"weight_bytes":a.WEIGHT_BYTES})+"\n")
            spec=root/"spec"; spec.write_text(json.dumps({"runtime_identity":{"model_revision":a.MODEL_REVISION},"captures":{"count":3,"absolute_session_timeout_seconds":3600}})+"\n")
            suite=root/"suite"; suite.write_text(json.dumps({"case_count":36})+"\n")
            script=root/"remote.sh"; script.write_text("true\n")
            for label, expected in [("ok",True),("missing",False),("identity",False),("remote",False)]:
                result=a.run(Backend(root/label, failure=None if label=="ok" else label), output=root/("out-"+label), name="n", model_dir=model, spec=spec, suite_manifest=suite, remote_script=script)
                self.assertEqual(result["pass"], expected)
            result=a.run(Backend(root/"cleanup", cleanup=False), output=root/"out-cleanup", name="n", model_dir=model, spec=spec, suite_manifest=suite, remote_script=script)
            self.assertFalse(result["pass"])

    def test_no_mutation_systemd_boundary(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); out=root/"precreate"; model=root/"model"; model.mkdir()
            (model/"model-files-manifest.json").write_text(json.dumps({"revision":a.MODEL_REVISION,"shard_count":a.SHARDS,"weight_bytes":a.WEIGHT_BYTES})+"\n")
            spec=root/"spec"; spec.write_text(json.dumps({"runtime_identity":{"model_revision":a.MODEL_REVISION},"captures":{"count":3,"absolute_session_timeout_seconds":3600}})+"\n")
            suite=root/"suite"; suite.write_text(json.dumps({"case_count":36})+"\n")
            script=root/"remote.sh"; script.write_text("true\n")
            key=root/"key"; key.write_text("not-a-real-key\n"); pub=root/"key.pub"; pub.write_text("ssh-ed25519 AAAA test\n")
            cmd=a.build_systemd_command(Path(a.__file__), out, unit="bf16-v2-test", controller_args=[
                "--output", str(out), "--name", "dry-run", "--model-dir", str(model), "--spec", str(spec),
                "--suite-manifest", str(suite), "--remote-script", str(script), "--ssh-key", str(key),
                "--ssh-public-key", str(pub)])
            result=__import__("subprocess").run(cmd, capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            terminal=json.loads((out/"precreate-terminal.json").read_text())
            self.assertTrue(terminal["pass"]); self.assertFalse(terminal["mutation"])

    def test_redaction(self):
        self.assertNotIn("SECRET", a.redacted("authorization=SECRET"))

    def test_actual_backend_construction_and_disk_cleanup_views(self):
        backend=a.NebiusBackend(Path("/tmp/no-provider-key")); calls=[]; state={"instance":True,"disk":True}
        backend._delete_instance=lambda instance: calls.append(("instance",instance))
        backend._wait_absent=lambda instance, deadline: True
        backend._delete_disk=lambda disk: (calls.append(("disk",disk)), state.__setitem__("disk",False))
        backend._list_items=lambda kind: ([{"name":"dry"}] if kind == "instance" and state["instance"] else ([{"name":"dry-boot","id":"disk-1"}] if state["disk"] else []))
        backend._metadata_name=lambda row: row["name"]
        backend._metadata_id=lambda row: row.get("id")
        backend._delete_instance=lambda instance: (calls.append(("instance",instance)), state.__setitem__("instance",False))
        result=backend.delete("instance-1", "dry-boot")
        self.assertTrue(result["pass"]); self.assertEqual(calls, [("instance","instance-1"),("disk","disk-1")])

    def test_actual_backend_address_passes_key_and_deadline_to_wait_ssh(self):
        backend=a.NebiusBackend(Path("/tmp/paired-key")); seen=[]
        backend._get_instance=lambda instance: {"ready": True}
        backend._extract_public_ipv4=lambda payload: "203.0.113.10"
        backend._wait_ssh=lambda ip, key, deadline: seen.extend([ip,key,deadline])
        self.assertEqual(backend.address("instance-1"), "203.0.113.10")
        self.assertEqual(seen[:2], ["203.0.113.10", Path("/tmp/paired-key")])
        self.assertGreater(seen[2], __import__("time").time())

    def test_remote_archive_validation(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); source=fixture(root/"capture"); archive=root/"capture.tar.gz"
            with tarfile.open(archive,"w:gz") as tar: tar.add(source, arcname="capture-1")
            result=a.validate_archive(archive, root/"unpacked", a.MODEL_REVISION)
            self.assertTrue(result["artifact_complete"])

    def test_host_without_sglang_routes_to_pinned_container(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); bindir=root/"bin"; bindir.mkdir(); captured=root/"docker-argv"
            sudo=bindir/"sudo"
            sudo.write_text("#!/bin/sh\nprintf '%s\\n' \"$*\" > \"$CAPTURE\"\n")
            sudo.chmod(0o755)
            env={"PATH":str(bindir)+":/usr/bin", "CAPTURE":str(captured), "V2_IN_CONTAINER":"0"}
            result=subprocess.run(["bash", "remote_v2_capture.sh", "1", "9999999999"], env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            argv=captured.read_text()
            self.assertIn("docker run --rm --gpus all --ipc=host --shm-size=32g --cap-add SYS_NICE", argv)
            self.assertIn("lmsysorg/sglang:v0.5.15-cu130@sha256:655d004115e384b56b73ad6869bb04b29cce7ba3e597ce8f92eeeb49e2acb0af", argv)
            self.assertIn("/workspace/model-bf16", argv); self.assertIn("/input/development.jsonl", argv)

    def test_deadline_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); model=root/"model"; model.mkdir()
            (model/"model-files-manifest.json").write_text(json.dumps({"revision":a.MODEL_REVISION,"shard_count":a.SHARDS,"weight_bytes":a.WEIGHT_BYTES})+"\n")
            spec=root/"spec"; spec.write_text(json.dumps({"runtime_identity":{"model_revision":a.MODEL_REVISION},"captures":{"count":3,"absolute_session_timeout_seconds":3600}})+"\n")
            suite=root/"suite"; suite.write_text(json.dumps({"case_count":36})+"\n")
            script=root/"remote.sh"; script.write_text("true\n")
            with patch.object(a.time, "time", side_effect=[1000, 5000]):
                result=a.run(Backend(root/"deadline"), output=root/"out-deadline", name="n", model_dir=model, spec=spec, suite_manifest=suite, remote_script=script)
            self.assertFalse(result["pass"])


if __name__ == "__main__": unittest.main()
