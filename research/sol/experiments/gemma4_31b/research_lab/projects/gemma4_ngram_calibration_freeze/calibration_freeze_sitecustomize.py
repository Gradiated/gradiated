"""Stock NGRAM calibration for requests 0--31, then fail-closed global writes."""
import hashlib, itertools, json, os, threading
from pathlib import Path

ROOT = Path(os.environ.get("CALIBRATION_FREEZE_ROOT", "/work"))
OUT = Path(os.environ.get("CALIBRATION_FREEZE_OUT", str(ROOT / "out"))); OUT.mkdir(parents=True, exist_ok=True)
TRACE = OUT / "calibration-freeze-ngram.jsonl"; LOCK = threading.Lock(); WORKERS = []

def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def emit(row):
    with LOCK:
        with TRACE.open("a") as f: f.write(json.dumps(row, sort_keys=True) + "\n")
def atomic(name, value):
    p=OUT/name; q=p.with_suffix(p.suffix+".part"); q.write_text(json.dumps(value,sort_keys=True,indent=2)+"\n"); q.replace(p)

from sglang.srt.speculative.ngram_worker import NGRAMWorker
ORIGINAL_INIT, ORIGINAL_UPDATE, ORIGINAL_FORWARD = NGRAMWorker.__init__, NGRAMWorker._update_ngram_corpus, NGRAMWorker.forward_batch_generation

def index(req):
    ids=getattr(req,"origin_input_ids",[])
    return ids[535]-200000 if len(ids)>535 and 200000<=ids[535]<=201035 else None

def patched_init(self,*a,**k):
    ORIGINAL_INIT(self,*a,**k); self._cf_completed=set(); self._cf_frozen=False; self._cf_writes_after_freeze=0; WORKERS.append(self)
    emit({"event":"worker_initialized","overlay_sha256":digest(__file__),"max_trie_depth":self.max_trie_depth,"draft_token_num":self.draft_token_num})

def patched_update(self,batch):
    if self._cf_frozen:
        self._cf_writes_after_freeze += 1
        atomic("ACTIVATION_STATE.json",{"overlay":"calibration_freeze_global_ngram","overlay_sha256":digest(__file__),"calibration_indices":sorted(self._cf_completed),"calibration_complete":True,"writes_after_freeze":self._cf_writes_after_freeze,"transition":"stock_update_completed_then_all_later_update_calls_noop","read_path":"unchanged_stock_global_bfs_depth_12"})
        emit({"event":"write_suppressed","update_call_after_freeze":self._cf_writes_after_freeze,"requests":len(batch.reqs)})
        return
    ORIGINAL_UPDATE(self,batch)
    newly=[]
    for req in batch.reqs:
        i=index(req)
        if i is not None and 0<=i<=31 and req.finished() and i not in self._cf_completed:
            self._cf_completed.add(i); newly.append(i)
    if newly: emit({"event":"calibration_completion","newly_completed":newly,"completed":sorted(self._cf_completed)})
    if len(self._cf_completed)==32:
        self._cf_frozen=True
        state={"overlay":"calibration_freeze_global_ngram","overlay_sha256":digest(__file__),"calibration_indices":sorted(self._cf_completed),"calibration_complete":True,"writes_after_freeze":0,"transition":"stock_update_completed_then_all_later_update_calls_noop","read_path":"unchanged_stock_global_bfs_depth_12"}
        atomic("ACTIVATION_STATE.json",state); emit({"event":"freeze_activated",**state})

def patched_forward(self,*a,**k):
    batch=a[0]; result=ORIGINAL_FORWARD(self,*a,**k); accepted=result.num_correct_drafts_per_req_cpu
    if accepted is not None:
        emit({"event":"target_verify","freeze_active":self._cf_frozen,"rows":[{"request_index":index(req),"accepted_drafts":int(value),"output_len":len(req.output_ids)} for req,value in zip(batch.reqs,accepted)]})
    return result

NGRAMWorker.__init__=patched_init; NGRAMWorker._update_ngram_corpus=patched_update; NGRAMWorker.forward_batch_generation=patched_forward
atomic("OVERLAY_STATE.json",{"overlay":"calibration_freeze_global_ngram","overlay_sha256":digest(__file__),"read_path":"unchanged_stock_global_bfs_depth_12","write_path":"stock_requests_0_31_then_fail_closed_noop"})
