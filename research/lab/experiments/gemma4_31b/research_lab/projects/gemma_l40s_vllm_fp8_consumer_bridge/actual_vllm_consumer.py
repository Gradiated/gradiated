#!/usr/bin/env python3
import argparse, importlib, inspect, json, time
from pathlib import Path
import torch

SHAPES=(("sliding_qkv",5376,16384),("global_qkv",5376,20480),("sliding_output",8192,5376),("global_output",16384,5376),("merged_gate_up",5376,43008),("down",21504,5376))
def main():
 p=argparse.ArgumentParser(); p.add_argument('--stage',required=True); p.add_argument('--output',type=Path,required=True); a=p.parse_args()
 out={"stage":a.stage,"pass":False,"all_actual_consumers_pass":False,"economic_both_envelopes_falsified":False,"rows":[],"vllm":None}
 try:
  fp8=importlib.import_module('vllm.model_executor.layers.quantization.fp8'); out['vllm']={"fp8_module":fp8.__file__,"classes":sorted(x for x in dir(fp8) if 'Fp8' in x or 'FP8' in x)}
  if a.stage=='conditional':
   lm=importlib.import_module('vllm.model_executor.layers.logits_processor'); cls=getattr(lm,'ParallelLMHead'); out['parallel_lm_head']={"class":str(cls),"signature":str(inspect.signature(cls))}; raise RuntimeError('ParallelLMHead construction requires pinned runtime tensor-parallel initialization')
  method=getattr(fp8,'Fp8LinearMethod'); config=getattr(fp8,'Fp8Config'); out['method']={"class":str(method),"apply_signature":str(inspect.signature(method.apply)),"create_weights_signature":str(inspect.signature(method.create_weights)),"config_signature":str(inspect.signature(config))}
  cfg=config(is_checkpoint_fp8_serialized=True, activation_scheme='dynamic')
  actual=method(cfg); out['method']['instance_class']=str(type(actual))
  raise RuntimeError('actual Fp8LinearMethod was constructed but its pinned weight-loader contract must be satisfied before apply; no generic fallback is permitted')
 except Exception as e: out['error']={"type":type(e).__name__,"message":str(e)[:1000]}
 a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n'); return 0
if __name__=='__main__': raise SystemExit(main())
