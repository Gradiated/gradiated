"""Bound request-local verified-trunk overlay for the resident NGRAM worker."""
from __future__ import annotations
import atexit, hashlib, json, os, threading, time
from pathlib import Path
import numpy as np

ROOT = Path(os.environ.get("REQUEST_LOCAL_ROOT", "/work"))
OUT = Path(os.environ.get("REQUEST_LOCAL_OUT", str(ROOT / "out")))
OUT.mkdir(parents=True, exist_ok=True)
TRACE = OUT / "request-local-ngram.jsonl"
LOCK = threading.Lock()

def atomic(name, row):
    p=OUT/name; q=p.with_suffix(p.suffix+".part"); q.write_text(json.dumps(row,sort_keys=True,indent=2)+"\n"); q.replace(p)
def emit(row):
    with LOCK:
        with TRACE.open("a") as f: f.write(json.dumps(row,sort_keys=True)+"\n")
def digest(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

from sglang.srt.speculative.ngram_worker import NGRAMWorker
from sglang.srt.speculative.cpp_ngram.ngram_corpus import NgramCorpus
ORIG_INIT=NGRAMWorker.__init__
ORIG_PREPARE=NGRAMWorker._prepare_draft_tokens
ORIG_UPDATE=NGRAMWorker._update_ngram_corpus
ORIG_FORWARD=NGRAMWorker.forward_batch_generation

def paths(tokens, mask, n):
    rows=np.asarray(mask).reshape(n,n)
    toks=np.asarray(tokens).reshape(n).tolist()
    sets=[]; leaf_sets=[]; leaf_rows=[]
    for i,row in enumerate(rows): sets.append((i,set(np.flatnonzero(row).tolist())))
    for i,current in reversed(sets):
        if any(current <= kept for kept in leaf_sets): continue
        leaf_sets.append(current); leaf_rows.append(i)
    leaf_rows.reverse()
    return [[toks[j] for j in range(n) if rows[i,j]] for i in leaf_rows]

def merge(local_toks, local_mask, global_toks, global_mask, n):
    """Reserve the longest local verified path, then append global BFS leaves."""
    lp=paths(local_toks,local_mask,n)
    trunk=max(lp,key=len,default=[])
    if len(trunk)<=1:
        return np.asarray(global_toks,dtype=np.int32),np.asarray(global_mask,dtype=np.uint8),0
    trunk=trunk[:n]
    order=list(trunk)
    mask=np.zeros((n,n),dtype=np.uint8)
    for i in range(len(trunk)): mask[i,:i+1]=1
    global_tokens=np.asarray(global_toks).reshape(n)
    global_rows=np.asarray(global_mask).reshape(n,n)
    remaining=n-len(trunk)
    for source in range(remaining):
        target=len(trunk)+source
        order.append(int(global_tokens[source]))
        for ancestor in np.flatnonzero(global_rows[source]):
            if ancestor<remaining: mask[target,len(trunk)+ancestor]=1
    return np.asarray(order,dtype=np.int32),mask.reshape(-1),len(trunk)

def patched_init(self,*a,**kw):
    ORIG_INIT(self,*a,**kw)
    server_args=a[0] if a else kw["server_args"]
    self._request_local={}
    self._request_local_has_verified=set()
    self._request_local_args={"min_bfs_breadth":server_args.speculative_ngram_min_bfs_breadth,"max_bfs_breadth":server_args.speculative_ngram_max_bfs_breadth,"match_type":server_args.speculative_ngram_match_type,"capacity":server_args.speculative_ngram_capacity,"max_trie_depth":server_args.speculative_ngram_max_trie_depth,"draft_token_num":server_args.speculative_num_draft_tokens,"external_sam_budget":0,"external_corpus_max_tokens":0}
    self._request_local_stats={"prepare_calls":0,"update_calls":0,"target_verify_forwards":0,"target_verify_rows":0,"local_trunk_lengths":{},"seen":set()}
    self._request_local_last_prepare={}
    target=self.target_worker.forward_batch_generation
    def timed(*aa,**kk):
        result=target(*aa,**kk)
        if kk.get("is_verify",False):
            self._request_local_stats["target_verify_forwards"]+=1
            self._request_local_stats["target_verify_rows"]+=len(aa[0].reqs) * self.draft_token_num
        return result
    self.target_worker.forward_batch_generation=timed
    emit({"event":"worker_initialized","overlay_sha256":digest(__file__),"draft_token_num":self.draft_token_num,"max_depth":self.max_trie_depth})

def local_for(self,rid):
    c=self._request_local.get(rid)
    if c is None:
        a=self._request_local_args
        c=NgramCorpus(**a); self._request_local[rid]=c
    return c

def patched_prepare(self,batch):
    self.ngram_corpus.synchronize()
    ids=[]; tails=[]; lens=[]
    for req in batch.reqs:
        ids.append(req.rid); tails.append(self._efficient_concat_last_n(req.origin_input_ids,req.output_ids,self.max_trie_depth)); lens.append(len(req.origin_input_ids)+len(req.output_ids))
    gt,gm=self.ngram_corpus.batch_get(ids,tails,lens)
    n=self.draft_token_num; out_t=[]; out_m=[]; trunks={}
    for i,(rid,tail,total) in enumerate(zip(ids,tails,lens)):
        c=local_for(self,rid); c.synchronize(); lt,lm=c.batch_get([rid],[tail],[total])
        if rid in self._request_local_has_verified:
            mt,mm,depth=merge(lt,lm,gt[i*n:(i+1)*n],gm[i*n*n:(i+1)*n*n],n)
        else:
            mt=np.asarray(gt[i*n:(i+1)*n],dtype=np.int32)
            mm=np.asarray(gm[i*n*n:(i+1)*n*n],dtype=np.uint8)
            depth=0
        out_t.append(mt); out_m.append(mm); trunks[str(rid)]=depth
        if 200790 in batch.reqs[i].origin_input_ids:
            self._request_local_last_prepare[rid]={
                "rid":rid,
                "output_len":len(batch.reqs[i].output_ids),
                "output_tail":list(batch.reqs[i].output_ids[-24:]),
                "local_tokens":np.asarray(lt).tolist(),
                "local_mask":np.asarray(lm).reshape(n,n).astype(int).tolist(),
                "global_tokens":np.asarray(gt[i*n:(i+1)*n]).tolist(),
                "global_mask":np.asarray(gm[i*n*n:(i+1)*n*n]).reshape(n,n).astype(int).tolist(),
                "merged_tokens":mt.tolist(),
                "merged_mask":mm.reshape(n,n).astype(int).tolist(),
                "local_trunk_length":depth,
            }
    s=self._request_local_stats; s["prepare_calls"]+=1; s["local_trunk_lengths"].update(trunks); s["seen"].update(map(str,ids))
    emit({"event":"prepare","requests":len(ids),"trunks":trunks,"target_verify_forwards":s["target_verify_forwards"],"target_verify_rows":s["target_verify_rows"]})
    return np.concatenate(out_t),np.concatenate(out_m)

def patched_update(self,batch):
    global_tokens=[]
    for req in batch.reqs:
        tokens=self._efficient_concat_last_n(req.origin_input_ids,req.output_ids,self.max_trie_depth)
        global_tokens.append(tokens)
        # This method runs only after NgramVerifyInput.verify: output_ids are target-verified.
        local_for(self,req.rid).batch_put([tokens])
        self._request_local_has_verified.add(req.rid)
        if 200790 in req.origin_input_ids:
            emit({"event":"request_790_corpus_update","rid":req.rid,"tokens":list(tokens),"output_len":len(req.output_ids)})
    self.ngram_corpus.batch_put(global_tokens)
    self._request_local_stats["update_calls"]+=1

def patched_forward(self,*a,**kw):
    batch=a[0]
    target_rids=[req.rid for req in batch.reqs if 200790 in req.origin_input_ids]
    try:
        result=ORIG_FORWARD(self,*a,**kw)
        for rid in target_rids:
            row=self._request_local_last_prepare.pop(rid,{})
            spec=getattr(batch,"spec_info",None)
            index=next((i for i,req in enumerate(batch.reqs) if req.rid==rid),None)
            row.update({
                "event":"request_790_target_verify",
                "request_ownership":[req.rid for req in batch.reqs],
                "batch_index":index,
                "accepted_drafts":result.num_correct_drafts_per_req_cpu[index] if index is not None and result.num_correct_drafts_per_req_cpu else None,
                "accepted_tokens_with_bonus":int(spec.num_accept_tokens[index]) if index is not None and getattr(spec,"num_accept_tokens",None) is not None else None,
                "retrieve_indexes":spec.retrieve_index[index].detach().cpu().tolist() if index is not None and spec is not None else None,
                "output_len_after":len(batch.reqs[index].output_ids) if index is not None else None,
                "output_tail_after":list(batch.reqs[index].output_ids[-24:]) if index is not None else None,
            })
            emit(row)
        return result
    finally:
        for req in batch.reqs:
            if req.finished() or req.is_retracted:
                removed=self._request_local.pop(req.rid,None) is not None
                self._request_local_has_verified.discard(req.rid)
                if 200790 in req.origin_input_ids:
                    emit({"event":"request_790_cleanup","rid":req.rid,"finished":req.finished(),"retracted":req.is_retracted,"removed":removed})
        s=getattr(self,"_request_local_stats",None)
        if s: emit({"event":"forward","target_verify_forwards":s["target_verify_forwards"],"target_verify_rows":s["target_verify_rows"],"active_local_tries":len(self._request_local)})

def patched_erase(self, req_ids):
    for rid in req_ids: self._request_local.pop(rid,None)
    return self.ngram_corpus.erase_match_state(req_ids)

# Preserve original cleanup call by wrapping corpus cleanup after every forward.
NGRAMWorker.__init__=patched_init
NGRAMWorker._prepare_draft_tokens=patched_prepare
NGRAMWorker._update_ngram_corpus=patched_update
NGRAMWorker.forward_batch_generation=patched_forward
atomic("OVERLAY_STATE.json",{"overlay":"request_local_verified_trunk","overlay_sha256":digest(__file__),"source":"target_verified_tokens_only","global_fallback":"unchanged_BFS_recency","depth":12})
