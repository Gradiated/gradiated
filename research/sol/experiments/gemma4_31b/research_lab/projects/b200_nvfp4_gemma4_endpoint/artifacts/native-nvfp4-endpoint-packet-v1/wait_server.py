#!/usr/bin/env python3
import argparse,json,os,time,urllib.request
p=argparse.ArgumentParser();p.add_argument("--pid",type=int,required=True);p.add_argument("--url",required=True);p.add_argument("--output",required=True);a=p.parse_args();end=time.monotonic()+1800
while time.monotonic()<end:
 if os.waitpid(a.pid,os.WNOHANG)[0]: raise SystemExit("server_exited_before_ready")
 try:
  with urllib.request.urlopen(a.url,timeout=5) as r: open(a.output,"w").write(json.dumps({"ready":True,"models":json.loads(r.read())}));raise SystemExit(0)
 except Exception: time.sleep(2)
raise SystemExit("server_readiness_timeout")
