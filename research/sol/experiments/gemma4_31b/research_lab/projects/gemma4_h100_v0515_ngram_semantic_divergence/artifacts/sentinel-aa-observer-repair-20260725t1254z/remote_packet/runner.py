import concurrent.futures,json,os,time,urllib.request,hashlib,pathlib
out=pathlib.Path("/work/out"); out.mkdir(exist_ok=True); arms=json.load(open("/work/packet/arms.json"))["arms"]
def post(b):
 p={"input_ids":b["prompt"],"sampling_params":{"temperature":0,"min_new_tokens":358,"max_new_tokens":358,"ignore_eos":True}}; q=urllib.request.Request("http://127.0.0.1:30000/generate",json.dumps(p,separators=(",",":")).encode(),{"Content-Type":"application/json"}); t=time.monotonic(); r=json.loads(urllib.request.urlopen(q,timeout=1200).read()); m=r.get("meta_info") or {}; return {"rid":b["request_id"],"latency_s":time.monotonic()-t,"output_ids":r.get("output_ids") or m.get("output_ids") or m.get("completion_token_ids"),"usage":{"prompt_tokens":m.get("prompt_tokens",len(b["prompt"])),"completion_tokens":m.get("completion_tokens",358)},"raw_sha256":hashlib.sha256(json.dumps(r,sort_keys=True).encode()).hexdigest()}
for arm in arms:
 with concurrent.futures.ThreadPoolExecutor(max_workers=len(arm["bodies"])) as e: rows=[f.result() for f in [e.submit(post,b) for b in arm["bodies"]]]
 (out/(arm["name"]+".json")).write_text(json.dumps(rows,indent=2,sort_keys=True)+"\n")
print("SENTINEL_RUNNER_DONE")
