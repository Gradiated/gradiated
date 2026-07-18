#!/usr/bin/env python3
import argparse, hashlib, json, os, statistics, time
from pathlib import Path
import torch

SHAPES=(('sliding_qkv',5376,16384,50),('global_qkv',5376,20480,10),('sliding_output',8192,5376,50),('global_output',16384,5376,10),('gate_up',5376,43008,60),('down',21504,5376,60))
DECODE=(8,16,32); PREFILL=3679; STEPS=358; CEILING=0.5479752315195353
def atomic(p,v):
 t=p.with_suffix(p.suffix+'.tmp'); t.write_text(json.dumps(v,indent=2,sort_keys=True)+'\\n'); os.replace(t,p)
def pct(v,q): return sorted(v)[int((len(v)-1)*q)]
def one(a,w,reps):
 cuda=[]; wall=[]; checksum=0.
 for _ in range(reps):
  s,e=torch.cuda.Event(True),torch.cuda.Event(True); torch.cuda.synchronize(); t=time.perf_counter(); s.record(); y=torch.matmul(a,w.t()); e.record(); e.synchronize(); cuda.append(s.elapsed_time(e)); wall.append((time.perf_counter()-t)*1000); maximum=float(y.float().abs().max()); checksum+=float(y.float().sum())
  if not bool(torch.isfinite(y).all()) or maximum == 0.: raise RuntimeError('timed BF16 matmul violated finite nonzero varied-sign oracle')
 return cuda,wall,checksum
def main():
 p=argparse.ArgumentParser();p.add_argument('--stage',required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--seed',type=int,required=True);a=p.parse_args()
 r={'schema_version':1,'type':'gemma4_h100_stock_bf16_exact_linears','stage':a.stage,'pass':False,'all_actual_consumers_pass':False,'geometry':{'shapes':[{'name':n,'k':k,'n':n2,'multiplicity':z}for n,k,n2,z in SHAPES],'decode_m':list(DECODE),'prefill_m':PREFILL,'decode_steps':STEPS},'rows':[]}; start=time.perf_counter()
 try:
  torch.manual_seed(a.seed); torch.cuda.manual_seed_all(a.seed); props=torch.cuda.get_device_properties(0); name=torch.cuda.get_device_name()
  if name!='NVIDIA H100 80GB HBM3' or tuple(torch.cuda.get_device_capability())!=(9,0) or props.total_memory<80*1024**3: raise RuntimeError(f'expected full H100 80GB capability 9.0, got {name} {props.total_memory} {torch.cuda.get_device_capability()}')
  r['runtime']={'gpu_name':name,'gpu_capability':list(torch.cuda.get_device_capability()),'gpu_total_memory_bytes':props.total_memory,'torch':torch.__version__,'cuda':torch.version.cuda,'consumer':'torch.matmul','consumer_source_sha256':hashlib.sha256(b'torch.matmul(activations,weight.transpose(0,1))').hexdigest(),'seed':a.seed}
  cases=[SHAPES[0]] if a.stage=='sentinel' else SHAPES; ms=[8] if a.stage=='sentinel' else [*DECODE,PREFILL]
  for shape,k,n,multi in cases:
   w=torch.randn((n,k),device='cuda',dtype=torch.bfloat16)/8
   for m in ms:
    x=torch.randn((m,k),device='cuda',dtype=torch.bfloat16)
    for _ in range(3):
     warm=torch.matmul(x,w.t())
     if not bool(torch.isfinite(warm).all()) or float(warm.float().abs().max())==0.: raise RuntimeError('warmup oracle failed')
    torch.cuda.synchronize();torch.cuda.reset_peak_memory_stats(); cuda,wall,checksum=one(x,w,7 if m==PREFILL else 15)
    r['rows'].append({'shape':shape,'m':m,'multiplicity':multi,'activation_shape':[m,k],'weight_shape':[n,k],'output_shape':[m,n],'dtype':'torch.bfloat16','finite_nonzero_varied_sign_oracle':True,'consumed_checksum':checksum,'pass':checksum!=0.,'cuda_event_ms':{'p50':statistics.median(cuda),'p95':pct(cuda,.95),'raw':cuda},'wall_ms':{'p50':statistics.median(wall),'p95':pct(wall,.95),'raw':wall},'peak_allocated_bytes':torch.cuda.max_memory_allocated(),'peak_reserved_bytes':torch.cuda.max_memory_reserved()})
    del x,warm
   del w;torch.cuda.empty_cache()
  r['all_actual_consumers_pass']=all(x['pass'] for x in r['rows']) and len(r['rows'])==len(cases)*len(ms)
  if a.stage=='sentinel': r['sentinel']={'shape':'sliding_qkv','m':8,'pass':r['all_actual_consumers_pass'] and len(r['rows'])==1}
  else:
   by={m:[x for x in r['rows'] if x['m']==m] for m in [*DECODE,PREFILL]}; prefill=sum(x['cuda_event_ms']['p50']*x['multiplicity'] for x in by[PREFILL])/1000; floors=[]
   for m in DECODE:
    decode=sum(x['cuda_event_ms']['p50']*x['multiplicity'] for x in by[m])*STEPS/m/1000; total=prefill+decode; floors.append({'m':m,'prefill_once_seconds':prefill,'decode_358_steps_seconds':decode,'linear_component_floor_seconds_per_request':total,'ceiling_seconds_per_request':CEILING,'survives_ceiling':total<=CEILING})
   r['economic_floor']=floors; r['sweep']={'required_row_count':24,'pass':r['all_actual_consumers_pass'] and len(r['rows'])==24,'surviving_concurrencies':[x['m'] for x in floors if x['survives_ceiling']]}
  r['pass']=r['all_actual_consumers_pass']
 except Exception as e: r['error']={'type':type(e).__name__,'message':str(e)[:2000]}
 r['useful_gpu_seconds']=time.perf_counter()-start;atomic(a.output,r);return 0 if r['pass'] else 1
if __name__=='__main__': raise SystemExit(main())
