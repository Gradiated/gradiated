#!/usr/bin/env python3
import hashlib, json, shutil
from pathlib import Path

P=Path(__file__).resolve().parent
def h(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 b=json.loads((P/'DIRECTOR_STOCK_MULTIPLEX_BINDING.json').read_text())
 if h(P/'DIRECTOR_STOCK_MULTIPLEX_BINDING.json') != '82c91cf2ae5c3993ecac31a37fddc59684a8df83fef2b84fa322912d5bde9e70': raise RuntimeError('binding_sha')
 for row in b['evidence'].values():
  q=(P/row['path']).resolve()
  if h(q)!=row['sha256']: raise RuntimeError('bound_evidence:'+row['path'])
 root=P/'stock_packet'; shutil.rmtree(root,ignore_errors=True); (root/'inputs').mkdir(parents=True)
 for name in ('TRACE_PACKET.json','exact_semantic_rows.jsonl','requests.jsonl'):
  shutil.copy2(P/'packet/inputs'/name,root/'inputs'/name)
 shutil.copy2(P/'packet/geometry.jsonl',root/'geometry.jsonl'); shutil.copy2(P/'stock_multiplex_runner.py',root/'stock_multiplex_runner.py'); shutil.copy2(P/'multiplex_runner.py',root/'multiplex_runner.py')
 args=json.loads((P/'packet/inputs/ngram-launch.json').read_text())['args']; args=args[:args.index('--speculative-algorithm')]
 if any('ngram' in x.lower() or 'speculative' in x.lower() for x in args): raise RuntimeError('forbidden_stock_flag')
 (root/'STOCK_LAUNCH.json').write_text(json.dumps({'args':args,'forbidden_flags_absent':True},sort_keys=True,indent=2)+'\n')
 files=[]
 for x in sorted(p for p in root.rglob('*') if p.is_file()): files.append({'path':str(x.relative_to(root)),'bytes':x.stat().st_size,'sha256':h(x)})
 (root/'PACKET_MANIFEST.json').write_text(json.dumps({'schema_version':1,'files':files,'binding_sha256':h(P/'DIRECTOR_STOCK_MULTIPLEX_BINDING.json'),'stock_no_speculation':True},sort_keys=True,indent=2)+'\n')
 (root/'PACKET_ID.json').write_text(json.dumps({'content_address':'sha256:'+h(root/'PACKET_MANIFEST.json'),'manifest':'PACKET_MANIFEST.json'},sort_keys=True,indent=2)+'\n')
 print(json.dumps({'packet':str(root),'packet_sha256':h(root/'PACKET_MANIFEST.json'),'files':len(files)}))
if __name__=='__main__': main()
