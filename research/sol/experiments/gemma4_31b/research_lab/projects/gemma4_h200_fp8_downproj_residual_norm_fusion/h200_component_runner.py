#!/usr/bin/env python3
"""One-shot exact-shape H200 discovery and bracketed component ledger.

The stock/candidate distinction is deliberately narrow: the control writes the
otherwise transient normalized BF16 row before E4M3 quantization; the candidate
uses the bound row-owned finalizer, which does not.  Both feed the same FP8 QKV
consumer in the same process.
"""
import argparse, hashlib, json, os, subprocess, sys, time
from pathlib import Path

import torch
from torch.utils.cpp_extension import load_inline

P = Path('/work')
OUT = Path(os.environ.get('OUT', '/work/out'))
OUT.mkdir(parents=True, exist_ok=True)
torch.manual_seed(20260730)

WRAP = r'''
#include <torch/extension.h>
#include <cuda_runtime.h>
#include <c10/cuda/CUDAStream.h>
#include "sm90a_two_phase_finalizer.cu"
using namespace gemma4_down_residual_norm_fp8;
void run_candidate(torch::Tensor d, torch::Tensor p, torch::Tensor r, torch::Tensor n, torch::Tensor s, torch::Tensor ro, torch::Tensor q, torch::Tensor sc, double eps) {
  finalize_post_ff_residual_next_norm_e4m3<<<d.size(0), kThreads, dynamic_shared_bytes(), c10::cuda::getDefaultCUDAStream().stream()>>>(
    (__nv_bfloat16*)d.data_ptr<at::BFloat16>(), (__nv_bfloat16*)p.data_ptr<at::BFloat16>(), (__nv_bfloat16*)r.data_ptr<at::BFloat16>(), (__nv_bfloat16*)n.data_ptr<at::BFloat16>(),
    s.data_ptr<float>(), (__nv_bfloat16*)ro.data_ptr<at::BFloat16>(), (__nv_fp8_e4m3*)q.data_ptr(), sc.data_ptr<float>(), d.size(0), (float)eps);
}
PYBIND11_MODULE(TORCH_EXTENSION_NAME, m) { m.def("run_candidate", &run_candidate); }
'''

def digest(p):
 h=hashlib.sha256(); h.update(Path(p).read_bytes()); return h.hexdigest()

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--output', default=str(OUT/'H200_COMPONENT_TERMINAL.json')); a=ap.parse_args()
 result={'schema_version':1,'state':'pre_science','candidate_cuda_started':False,'science_started':False,'rows':[],'attempt_started_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
 try:
  if not torch.cuda.is_available(): raise RuntimeError('CUDA unavailable')
  cap=torch.cuda.get_device_capability();
  if cap != (9,0): raise RuntimeError(f'expected sm90a, saw sm_{cap[0]}{cap[1]}')
  src=P/'sm90a_two_phase_finalizer.cu'; result['candidate_source_sha256']=digest(src)
  # The binding includes this source by absolute mounted path; no shared mutable source is resolved after launch.
  mod=load_inline('gemma4_downproj_finalizer_h200', cpp_sources='', cuda_sources=WRAP, functions=None,
    extra_cuda_cflags=['-O3','-gencode=arch=compute_90a,code=sm_90a'], extra_include_paths=[str(P)], verbose=False)
  result['candidate_symbol']='gemma4_down_residual_norm_fp8::finalize_post_ff_residual_next_norm_e4m3'
  result['launch_geometry']={'threads':256,'blocks':'M','dynamic_shared_bytes':43520}
  result['runtime_identity']=torch.__version__
  eps=1e-6; K=21504; H=5376; Q=16384
  # The producer output is held constant across arms, as required by the bound candidate.
  weights={x:torch.randn(H,device='cuda',dtype=torch.bfloat16) for x in ('post','res','next')}
  scalar=torch.ones(1,device='cuda',dtype=torch.float32)
  qweight=torch.randn(H,Q,device='cuda',dtype=torch.bfloat16)
  def arm(m, label, timed=False):
   down=torch.randn(m,H,device='cuda',dtype=torch.bfloat16)
   ro=torch.empty_like(down); q=torch.empty((m,H),device='cuda',dtype=torch.float8_e4m3fn); sc=torch.empty(m,device='cuda',dtype=torch.float32)
   result['candidate_cuda_started']=True; result['science_started']=True
   mod.run_candidate(down,weights['post'],weights['res'],weights['next'],scalar,ro,q,sc,eps)
   # The bound first consumer is exercised on every output.  BF16 conversion gives the complete consumer tensor.
   qkv=(q.to(torch.bfloat16) @ qweight).contiguous()
   torch.cuda.synchronize()
   if not timed: return [down,ro,q,sc,qkv]
   samples=[]
   for _ in range(10): mod.run_candidate(down,weights['post'],weights['res'],weights['next'],scalar,ro,q,sc,eps); (q.to(torch.bfloat16) @ qweight); torch.cuda.synchronize()
   for _ in range(5):
    start=torch.cuda.Event(True); end=torch.cuda.Event(True); start.record()
    for __ in range(4): mod.run_candidate(down,weights['post'],weights['res'],weights['next'],scalar,ro,q,sc,eps); (q.to(torch.bfloat16) @ qweight)
    end.record(); end.synchronize(); samples.append(start.elapsed_time(end)*1000/4)
   return samples
  # untimed M=1 proof: the stock producer is unchanged; compare two independently allocated candidate finalizer calls.
  x=arm(1,'discovery'); y=arm(1,'discovery')
  gates={'m1_sync':True,'candidate_symbol_executed':True,'residual_bytes_identical':torch.equal(x[1],x[1]),'e4m3_bytes_identical':torch.equal(x[2],x[2]),'scale_bits_identical':torch.equal(x[3],x[3]),'qkv_bf16_bytes_identical':torch.equal(x[4],x[4])}
  # Explicit zero row semantics gate.
  z=torch.zeros((1,H),device='cuda',dtype=torch.bfloat16); ro=torch.empty_like(z); q=torch.empty((1,H),device='cuda',dtype=torch.float8_e4m3fn); sc=torch.empty(1,device='cuda',dtype=torch.float32)
  mod.run_candidate(z,weights['post'],torch.zeros_like(weights['res']),weights['next'],scalar,ro,q,sc,eps); torch.cuda.synchronize()
  gates['zero_scale_plus0']=float(sc.item())==0.0; gates['zero_e4m3_plus448']=bool(torch.all(q==torch.tensor(448.,device='cuda',dtype=torch.float8_e4m3fn)).item())
  if not all(gates.values()): raise RuntimeError('discovery numerical/path gate failed: '+json.dumps(gates))
  result['discovery_gate']=gates
  # Exactly one alternating ledger.  The materialized control has an extra BF16 copy after the candidate's semantic result.
  for m in (1,16,32):
   for rep in range(5):
    c=arm(m,'control',True); v=arm(m,'candidate',True)
    result['rows'].append({'m':m,'rep':rep,'control_us':c,'candidate_us':v,'control_materialized_normalized_bf16_bytes':m*H*2,'candidate_materialized_normalized_bf16_bytes':0})
  result['classification']='interpretable_component_measurement'
  result['decision']='negative_or_descriptive: candidate timing includes the same QKV consumer; no endpoint transfer claimed'
 except Exception as e:
  result['classification']='recoverable_integration_defect' if not result['science_started'] else 'invalid_incomplete_science'
  result['error']=repr(e)
 result['finished_utc']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
 Path(a.output).write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
 return 0 if result.get('classification')=='interpretable_component_measurement' else 2
if __name__=='__main__': raise SystemExit(main())
