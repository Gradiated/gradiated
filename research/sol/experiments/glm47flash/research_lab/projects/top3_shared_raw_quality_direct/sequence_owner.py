#!/usr/bin/env python3
"""One retained owner for the direct top-3/top-2 raw-quality decision."""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path("/root/workspace/research/sol/experiments/glm47flash")
NEBIUS = ROOT / "campaign_100/nebius"
PROJECT = Path(__file__).resolve().parent
sys.path.insert(0, str(NEBIUS))
import vllm_smoke_control as smoke
import vllm_recover_existing as recover
from placement_control import VerifiedRetainedOwner

MODEL = Path("/root/.cache/glm47flash-awq-ab31d120")
KEY = Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
PUB = KEY.with_suffix(".pub")
TOP3 = ROOT / "research_lab/projects/full47_top3_shared_c32_direct/artifacts/l40s_top3_shared_c32_20260716_r1/configs/top3_shared_config.json"
TOP2 = ROOT / "research_lab/projects/full47_top2_shared_c32_direct_corrected/artifacts/l40s_top2_shared_c32_20260716_r2/configs/top2_shared_config.json"

def sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()

def shadow(root: Path, config: Path) -> Path:
    target = root / "model-top3"
    target.mkdir()
    for source in MODEL.iterdir():
        if not source.is_file() or source.name in {"config.json", "model-files.sha256", "model-files-manifest.json", ".campaign-integrity-v1"}: continue
        os.link(source, target / source.name)
    data = config.read_bytes(); (target / "config.json").write_bytes(data)
    manifest = json.loads((MODEL / "model-files-manifest.json").read_text())
    digest = sha(target / "config.json")
    for row in manifest["files"]:
        if row["path"] == "config.json": row.update(bytes=len(data), sha256=digest)
    (target / "model-files-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    lines = (MODEL / "model-files.sha256").read_text().splitlines()
    (target / "model-files.sha256").write_text("\n".join(f"{digest}  config.json" if row.endswith("  config.json") else row for row in lines) + "\n")
    return target

def valid(summary: Path) -> bool:
    try:
        value = json.loads(summary.read_text()); result = value["allocation_result"]
        quality = result.get("quality", {})
        return value["retained_for_next_experiment"] is True and value["background_pass"] is True and result.get("full_load_pass") is True and quality.get("pass") is True
    except (OSError, ValueError, KeyError, TypeError): return False

def recovery_args(out: Path, name: str, instance_id: str, deadline: float, spec: str):
    value = type("Args", (), {})()
    value.output_dir=out; value.name=name; value.instance_id=instance_id; value.control_summary=None; value.parent_experiment_id="top3_shared_raw_quality_direct"; value.session_deadline_epoch=deadline
    value.ssh_key=KEY; value.local_model_dir=MODEL; value.reference_tokenizer_dir=MODEL; value.repair_spec_sha256=spec; value.config_override=TOP2; value.config_override_sha256=sha(TOP2)
    value.reuse_staged_runtime=True; value.reuse_staged_runtime_and_checkpoint=True; value.keep_instance_after_result=False; value.dtype="bfloat16"; value.max_num_batched_tokens=65536; value.max_num_seqs=32; value.frontier_concurrencies="32"; value.decode_block_n=32; value.decode_num_stages=2; value.num_kv_splits=4; value.kv_cache_dtype="auto"; value.repair_window_seconds=0; value.background_arm_envelope_seconds=300; value.allow_deferred_absolute_quality_failure=False; value.head_shared_w4=False; value.selective_w4_scope="combined"
    return value

def main() -> int:
    if not os.environ.get("INVOCATION_ID") or os.environ.get("SYSTEMD_EXEC_PID") != str(os.getpid()): raise SystemExit("durable systemd main required")
    started=time.time(); deadline=started+2800; name="glm47-top3-raw-quality-20260716-r2"; out=PROJECT/"artifacts"/("l40s_top3_raw_quality_"+time.strftime("%Y%m%d_r2", time.gmtime())); out.mkdir(parents=True)
    model=shadow(out, TOP3); packet={"top3_config_sha256":sha(TOP3),"top2_config_sha256":sha(TOP2),"deadline_epoch":deadline,"sequence":["top3","conditional_top2"]}; (out/"LAUNCH_PACKET.json").write_text(json.dumps(packet,indent=2,sort_keys=True)+"\n"); spec=sha(out/"LAUNCH_PACKET.json")
    with VerifiedRetainedOwner(name, out/"owner-cleanup.json") as owner:
        smoke.run(out/"top3_shared_c32",name,KEY,PUB,model,model,spec,True,4,32,(32,),2800,300,"auto","awq","l40s-awq",False,False,False,False,False,"combined",0,False)
        summary=out/"top3_shared_c32/summary.json"
        if not valid(summary): owner.complete("TOP3_RAW_QUALITY_SIGNAL_FAIL"); return 1
        instance=json.loads(summary.read_text())["instance_id"]; owner.bind_instance(instance)
        if time.time()+800>deadline: owner.complete("TOP3_RAW_QUALITY_SIGNAL_PLAUSIBLE"); return 0
        recover.run(recovery_args(out/"top2_shared_c32",name,instance,deadline,spec))
        top2=json.loads((out/"top2_shared_c32/summary.json").read_text())
        owner.complete("TOP2_RAW_QUALITY_SIGNAL_PLAUSIBLE" if top2.get("background_pass") else "TOP2_RAW_QUALITY_SIGNAL_FAIL_PRESERVE_TOP3")
        return 0

if __name__ == "__main__": raise SystemExit(main())
