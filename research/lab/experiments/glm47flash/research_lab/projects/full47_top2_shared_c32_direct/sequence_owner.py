#!/usr/bin/env python3
"""One durable owner for the preregistered top4/top2/top4 retained session."""
import hashlib
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path('/root/workspace/research/lab/experiments/glm47flash')
NEBIUS = ROOT / 'campaign_100/nebius'
PROJECT = Path(__file__).resolve().parent
sys.path.insert(0, str(NEBIUS))
import vllm_smoke_control as smoke
import vllm_recover_existing as recover

MODEL = Path('/root/.cache/glm47flash-awq-ab31d120')
KEY = Path('/root/.config/nebius/glm-campaign/ssh_ed25519')
PUB = Path('/root/.config/nebius/glm-campaign/ssh_ed25519.pub')
OUT = PROJECT / 'artifacts/l40s_top2_shared_c32_20260716_r1'

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    if not os.environ.get('INVOCATION_ID') or os.environ.get('SYSTEMD_EXEC_PID') != str(os.getpid()):
        raise SystemExit('durable systemd main required')
    deadline = time.time() + 2400
    configs = OUT / 'configs'; configs.mkdir(parents=True, exist_ok=False)
    stock = json.loads((MODEL/'config.json').read_text())
    binding = {}
    for label, topk in (('top4',4),('top2',2),('top3',3)):
        path=configs/f'{label}_shared_config.json'
        if label == 'top4':
            path.write_bytes((MODEL / 'config.json').read_bytes())
            value = stock
        else:
            value=dict(stock); value['num_experts_per_tok']=topk
            path.write_text(json.dumps(value, sort_keys=True, indent=2)+'\n')
        binding[label]={'path':str(path),'sha256':sha(path),'num_experts_per_tok':topk,'n_shared_experts':value['n_shared_experts']}
    if binding['top4']['sha256'] != sha(MODEL/'config.json'):
        raise RuntimeError('stock config copy differs')
    packet={'configs':binding,'checkpoint':str(MODEL),'checkpoint_config_sha256':sha(MODEL/'config.json'),'sequence':['top4_shared_c32_pre','top2_shared_c32','top4_shared_c32_post'],'deadline_epoch':deadline}
    (OUT/'LAUNCH_PACKET.json').write_text(json.dumps(packet,sort_keys=True,indent=2)+'\n')
    spec=sha(OUT/'LAUNCH_PACKET.json')
    args=dict(key=KEY, public_key=PUB, model_dir=MODEL, tokenizer_dir=MODEL, spec_hash=spec, keep_instance_after_result=True, num_kv_splits=4, max_num_seqs=32, frontier_concurrencies=(32,), absolute_timeout_seconds=2400, background_arm_envelope_seconds=300, kv_cache_dtype='auto', scientific_mode='awq', profile='l40s-awq')
    rc=smoke.run(OUT/'top4_shared_c32_pre','glm47-top2-shared-c32-20260716-r1',**args)
    if rc: raise SystemExit(rc)
    summary=OUT/'top4_shared_c32_pre/summary.json'
    ident=json.loads(summary.read_text())['instance_id']
    for label, keep in (('top2_shared_c32',True),('top4_shared_c32_post',False)):
        cfg='top2' if label.startswith('top2') else 'top4'
        ns=type('Args',(),{})()
        ns.output_dir=OUT/label; ns.name='glm47-top2-shared-c32-20260716-r1'; ns.instance_id=ident; ns.control_summary=None; ns.parent_experiment_id='full47_top2_shared_c32_direct'; ns.session_deadline_epoch=deadline; ns.ssh_key=KEY; ns.local_model_dir=MODEL; ns.reference_tokenizer_dir=MODEL; ns.repair_spec_sha256=spec; ns.config_override=Path(binding[cfg]['path']); ns.config_override_sha256=binding[cfg]['sha256']; ns.reuse_staged_runtime=True; ns.reuse_staged_runtime_and_checkpoint=True; ns.keep_instance_after_result=keep; ns.dtype='bfloat16'; ns.max_num_batched_tokens=65536; ns.max_num_seqs=32; ns.frontier_concurrencies='32'; ns.decode_block_n=32; ns.decode_num_stages=2; ns.num_kv_splits=4; ns.kv_cache_dtype='auto'; ns.repair_window_seconds=0
        rc=recover.run(ns)
        if rc: raise SystemExit(rc)
    return 0
if __name__ == '__main__': raise SystemExit(main())
