#!/usr/bin/env python3
"""Exact-token W4 endpoint consumer that needs only the staged tokenizer config."""
from __future__ import annotations
import argparse, concurrent.futures, json, threading, time, urllib.request
from pathlib import Path

MODEL="google/gemma-4-31B-it"; PROMPT=4214; OUTPUT=358
def atomic(p:Path,v:object)->None:
 t=p.with_suffix(p.suffix+".part");t.write_text(json.dumps(v,indent=2,sort_keys=True)+"\n");t.replace(p)
def ids(vocab:int,n:int)->list[int]: return [32+((n*7919+i)%(vocab-64)) for i in range(PROMPT)]
def one(base:str,body:dict,out:Path,stem:str,barrier:threading.Barrier)->dict:
 barrier.wait(timeout=120);raw=out/"raw"/f"{stem}.sse";data=json.dumps(body,sort_keys=True,separators=(",",":")).encode();(out/"requests"/f"{stem}.json").write_bytes(data);started=time.monotonic();first=None;ended=None;tokens=[];text=[];usage=None;request=urllib.request.Request(base+"/v1/completions",data=data,headers={"Content-Type":"application/json"})
 with urllib.request.urlopen(request,timeout=1800) as response,raw.open("wb") as handle:
  for line in response:
   handle.write(line);line=line.strip()
   if not line.startswith(b"data:"):continue
   payload=line[5:].strip()
   if payload==b"[DONE]":ended=time.monotonic();break
   event=json.loads(payload);usage=event.get("usage") if isinstance(event.get("usage"),dict) else usage
   for choice in event.get("choices") or []:tokens.extend(choice.get("token_ids") or []);fragment=choice.get("text") or "";text.append(fragment);first=first or (time.monotonic() if fragment or choice.get("token_ids") else None)
 passed=bool(first and ended and usage and int(usage.get("prompt_tokens",-1))==PROMPT and int(usage.get("completion_tokens",-1))==OUTPUT and len(tokens)==OUTPUT and raw.stat().st_size and "".join(text).strip())
 return {"pass":passed,"wall_seconds":(ended or time.monotonic())-started,"ttft_ms":None if first is None else (first-started)*1000,"usage":usage,"output_tokens":len(tokens),"raw_sse_bytes":raw.stat().st_size,"text_bytes":len("".join(text).encode())}
def arm(base:str,root:Path,c:int,vocab:int)->dict:
 out=root/f"c{c}";out.mkdir();(out/"raw").mkdir();(out/"requests").mkdir();(out/"metrics-before.prom").write_bytes(urllib.request.urlopen(base+"/metrics",timeout=30).read());barrier=threading.Barrier(c);bodies=[{"model":MODEL,"prompt":ids(vocab,i),"add_special_tokens":False,"max_tokens":OUTPUT,"temperature":0,"ignore_eos":True,"stream":True,"stream_options":{"include_usage":True},"return_token_ids":True} for i in range(c)];started=time.monotonic()
 with concurrent.futures.ThreadPoolExecutor(max_workers=c) as pool:rows=list(pool.map(lambda x:one(base,x[1],out,f"request-{x[0]:03d}",barrier),enumerate(bodies)))
 wall=time.monotonic()-started;(out/"metrics-after.prom").write_bytes(urllib.request.urlopen(base+"/metrics",timeout=30).read());r={"concurrency":c,"complete_count":sum(x["pass"] for x in rows),"failure_count":sum(not x["pass"] for x in rows),"wall_seconds":wall,"completed_requests_per_second":c/wall,"service_seconds_per_request":wall/c,"nonempty_outputs":all(x["text_bytes"]>0 for x in rows),"rows":rows};r["pass"]=r["complete_count"]==c and not r["failure_count"] and r["nonempty_outputs"];atomic(out/"TERMINAL.json",r);return r
def main()->int:
 p=argparse.ArgumentParser();p.add_argument("--base",default="http://127.0.0.1:8000");p.add_argument("--tokenizer",type=Path,required=True);p.add_argument("--output",type=Path,required=True);p.add_argument("--concurrencies",default="96,128");a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);result={"schema_version":1,"model":MODEL,"workload":{"prompt_tokens":PROMPT,"output_tokens":OUTPUT,"cache_read_fraction_target":.127},"arms":[],"pass":False}
 try:
  (a.output/"server-models.json").write_bytes(urllib.request.urlopen(a.base+"/v1/models",timeout=30).read());config=json.loads((a.tokenizer/"config.json").read_text());vocab=int(config.get("vocab_size") or config["text_config"]["vocab_size"])
  for c in map(int,a.concurrencies.split(",")):
   value=arm(a.base,a.output,c,vocab);result["arms"].append(value)
   if not value["pass"]:break
  result["pass"]=len(result["arms"])==len(a.concurrencies.split(",")) and all(x["pass"] for x in result["arms"])
 except Exception as e:result["error"]={"type":type(e).__name__,"message":str(e)[:4000]}
 atomic(a.output/"TERMINAL.json",result);return 0 if result["pass"] else 1
if __name__=="__main__":raise SystemExit(main())
