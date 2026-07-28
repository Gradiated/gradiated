#!/usr/bin/env python3
import argparse, concurrent.futures, hashlib, json, math, pathlib, threading, time, urllib.request
def canonical(x): return json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
def one(i, body, base, out, barrier):
    (out/f"request-{i:02}.json").write_bytes(canonical(body)); barrier.wait(); start=time.monotonic(); raw=[]; ids=[]; text=""; usage={}; error=None
    try:
      req=urllib.request.Request(base+"/v1/completions",canonical(body),{"Content-Type":"application/json"})
      with urllib.request.urlopen(req,timeout=1800) as r:
       for line in r:
        raw.append(line)
        if line.startswith(b"data: ") and line.strip()!=b"data: [DONE]":
         x=json.loads(line[6:]); c=(x.get("choices") or [{}])[0]; ids.extend(c.get("token_ids") or []); text+=c.get("text") or ""; usage=x.get("usage") or usage
    except Exception as e: error=repr(e)
    elapsed=time.monotonic()-start; (out/f"response-{i:02}.sse").write_bytes(b"".join(raw))
    return {"index":i,"error":error,"seconds":elapsed,"prompt_tokens":usage.get("prompt_tokens"),"completion_tokens":usage.get("completion_tokens"),"returned_token_ids":len(ids),"nonempty":bool(text),"request_sha256":hashlib.sha256(canonical(body)).hexdigest()}
def main():
 p=argparse.ArgumentParser();p.add_argument("--host",required=True);p.add_argument("--port",type=int,required=True);p.add_argument("--output",type=pathlib.Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True);base=f"http://{a.host}:{a.port}"
 vocab=262144; prefix=[1000+((j*7919+17)%48000) for j in range(535)]; bodies=[]
 for i in range(32):
  suffix=[60000+i]+[1000+((i*4214+j*1543)%48000) for j in range(3678)]
  bodies.append({"model":"google/gemma-4-31B-it","prompt":prefix+suffix,"max_tokens":358,"min_tokens":358,"ignore_eos":True,"temperature":0,"seed":20260728+i,"stream":True,"stream_options":{"include_usage":True},"return_token_ids":True,"add_special_tokens":False})
 b=threading.Barrier(32); start=time.monotonic()
 with concurrent.futures.ThreadPoolExecutor(max_workers=32) as ex: rows=list(ex.map(lambda z:one(z[0],z[1],base,a.output,b),enumerate(bodies)))
 batch=time.monotonic()-start; ok=all(r["error"] is None and r["prompt_tokens"]==4214 and r["completion_tokens"]==358 and r["returned_token_ids"]==358 and r["nonempty"] and math.isfinite(r["seconds"]) for r in rows)
 (a.output/"TERMINAL.json").write_text(json.dumps({"classification":"endpoint_measurement" if ok else "endpoint_invalid","complete_requests":sum(r["error"] is None for r in rows),"service_seconds_per_request":batch/32,"batch_seconds":batch,"rows":rows,"identity":{"workload":"c32/4214/358/text-only/non-reasoning","candidate_requires":"compressed-tensors symmetric float4 tensor-group size16 W4A4"}},sort_keys=True,indent=2))
if __name__=="__main__": main()
