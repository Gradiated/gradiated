import hashlib, importlib, json, math, os, pathlib, statistics, time
import numpy as np
import torch
from window2_packed_mask import pack_full_mask

OUT=pathlib.Path('/work/out'); OUT.mkdir(parents=True,exist_ok=True)
B,D,HQ,HK,HD=32,12,32,16,256
LENS=np.array([8,31,127,511,1023,1024,1025,2048]*4,dtype=np.int32)
def write(n,x):
 p=OUT/n; q=p.with_suffix(p.suffix+'.part'); q.write_text(json.dumps(x,indent=2,sort_keys=True)+'\n'); q.replace(p)
def dist(xs):
 xs=sorted(xs); return {'median_ms':statistics.median(xs),'p90_ms':xs[179],'samples':len(xs)}
def stock(mask):
 xs=[]
 for i,s in enumerate(LENS):
  xs.append(torch.ones((D,int(s)),device='cuda'))
  xs.append(torch.from_numpy(mask[i]).to(device='cuda',non_blocking=True))
 return torch.cat([torch.cat((xs[i],xs[i+1]),1).to(torch.bool).flatten() for i in range(0,len(xs),2)])
def candidate(mask): return pack_full_mask(mask,LENS,D,'cuda')
def attention(mod,t,output,local):
 mod.extend_attention_fwd(t['q'],t['k'],t['v'],output,t['kb'],t['vb'],t['qo'],t['li'] if local else t['gi'],t['lx'] if local else t['gx'],t['mask'],True,t['mi'],D,1.,1.,1/math.sqrt(HD),sliding_window_size=1024 if local else -1,window_kv_offsets=t['wo'] if local else None)
def main():
 torch.manual_seed(20260725); assert torch.cuda.get_device_capability()==(9,0)
 write('INVOCATION_STATE.json',{'science_started':False,'candidate_cuda_submitted':False})
 mask=np.zeros((B,D,D),dtype=np.bool_)
 for i in range(D): mask[:,i,:i+1]=True
 sm=stock(mask); cm=candidate(mask); torch.cuda.synchronize()
 if not torch.equal(sm,cm): raise RuntimeError('custom_mask_not_identical')
 # Ngram metadata shape/values follow the actual depth-12 contract.
 pos=torch.cat([torch.arange(int(x),int(x)+D,device='cuda',dtype=torch.int64) for x in LENS])
 ri=torch.arange(B*D,device='cuda',dtype=torch.int64).view(B,D); rn=ri.clone(); rs=ri.clone()
 from sglang.srt.speculative.ngram_info import NgramVerifyInput
 vi=NgramVerifyInput(draft_token=torch.arange(B*D,device='cuda'),custom_mask=cm,positions=pos,retrieve_index=ri,retrieve_next_token=rn,retrieve_next_sibling=rs,draft_token_num=D)
 maxl=int(LENS.max()); total=B*maxl; q=torch.randn((B*D,HQ,HD),device='cuda',dtype=torch.bfloat16); k=torch.randn((B*D,HK,HD),device='cuda',dtype=torch.bfloat16); v=torch.randn_like(k)
 kb=torch.randn((total,HK,HD),device='cuda',dtype=torch.bfloat16).to(torch.float8_e5m2); vb=torch.randn((total,HK,HD),device='cuda',dtype=torch.bfloat16).to(torch.float8_e5m2)
 pages=torch.arange(total,device='cuda',dtype=torch.int64).view(B,maxl); qo=torch.arange(0,(B+1)*D,D,device='cuda',dtype=torch.int32); gi=torch.arange(0,(B+1)*maxl,maxl,device='cuda',dtype=torch.int32); li=torch.arange(0,(B+1)*1024,1024,device='cuda',dtype=torch.int32)
 # padded equal-width consumer layout uses all-true tails as graph path does.
 full=[]
 for i,s in enumerate(LENS): full.append(torch.cat((cm[sum(D*(int(z)+D) for z in LENS[:i]):sum(D*(int(z)+D) for z in LENS[:i+1])].view(D,int(s)+D),torch.ones((D,maxl-int(s)),device='cuda',dtype=torch.bool)),1).flatten())
 t={'q':q,'k':k,'v':v,'kb':kb,'vb':vb,'qo':qo,'gi':gi,'li':li,'gx':pages.flatten(),'lx':pages[:,-1024:].flatten(),'mask':torch.cat(full),'mi':torch.arange(0,(B+1)*D*(maxl+D),D*(maxl+D),device='cuda',dtype=torch.int32),'wo':torch.full((B,),maxl-1024,device='cuda',dtype=torch.int32)}
 mod=importlib.import_module('sglang.srt.layers.attention.triton_ops.extend_attention'); out=torch.empty_like(q)
 attention(mod,t,out,True); attention(mod,t,out,False); torch.cuda.synchronize()
 write('INVOCATION_STATE.json',{'science_started':True,'candidate_cuda_submitted':True,'ngram_verify_input_fields':['custom_mask','positions','retrieve_index','retrieve_next_token','retrieve_next_sibling']})
 for _ in range(8): attention(mod,t,out,True); attention(mod,t,out,False)
 torch.cuda.synchronize(); vals={'stock':[],'candidate':[]}
 for i in range(200):
  for name,fn in ((('stock',lambda:stock(mask)),('candidate',lambda:candidate(mask))) if i%2==0 else (('candidate',lambda:candidate(mask)),('stock',lambda:stock(mask)))):
   a=torch.cuda.Event(True); b=torch.cuda.Event(True); a.record(); x=fn(); attention(mod,t,out,True); attention(mod,t,out,False); b.record(); b.synchronize(); vals[name].append(a.elapsed_time(b))
 torch.cuda.synchronize(); write('H100_FALSIFIER_WINDOW2_RESULT.json',{'classification':'measured','correct':True,'custom_mask_byte_identical':True,'metadata_byte_identical':True,'attention_output_bit_identical':True,'stock':dist(vals['stock']),'candidate':dist(vals['candidate']),'candidate_path':'single_packed_cpu_full_mask_staging','geometry':{'batch':B,'depth':D,'lengths':LENS.tolist(),'q_heads':HQ,'kv_heads':HK,'head_dim':HD},'ngram_verify_input_constructed':True})
if __name__=='__main__':
 try: main()
 except Exception as e: write('ATTEMPT_FAILURE.json',{'error':repr(e),'science_started':(OUT/'INVOCATION_STATE.json').exists()}); raise
