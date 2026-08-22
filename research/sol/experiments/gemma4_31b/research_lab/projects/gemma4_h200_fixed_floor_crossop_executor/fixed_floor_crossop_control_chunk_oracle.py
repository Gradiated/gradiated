#!/usr/bin/env python3
"""Build a byte-preserving oracle from the already-frozen control SSE files."""
import argparse, hashlib, json, pathlib

def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p, v):
    q=p.with_suffix(p.suffix+'.part'); q.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n'); q.replace(p)
def events(p):
    chunks=[]; finish=[]; usage=[]; count=0
    for line in p.read_bytes().splitlines():
        if not line.startswith(b'data: ') or line == b'data: [DONE]': continue
        count+=1; item=json.loads(line[6:]); choice=(item.get('choices') or [{}])[0]
        if choice.get('text'):
            chunks.append(choice['text'])
        if choice.get('finish_reason') is not None: finish.append(choice.get('finish_reason'))
        if item.get('usage') is not None: usage.append(item['usage'])
    return {'sha256':digest(p),'sse_events':count,'chunks':chunks,'finish_reason':finish,'usage':usage}
def main():
    a=argparse.ArgumentParser(); a.add_argument('--control-root',type=pathlib.Path,required=True); a.add_argument('--terminal-sha256',required=True); a.add_argument('--output',type=pathlib.Path,required=True); z=a.parse_args()
    terminal=z.control_root/'TERMINAL.json'
    if digest(terminal)!=z.terminal_sha256: raise SystemExit('control_terminal_hash_mismatch')
    rows=[]
    for i in range(32):
        p=z.control_root/f'response-{i:02d}.sse'; r=events(p)
        if len(r['chunks'])!=358 or r['sse_events']!=359 or len(r['usage'])!=1 or r['usage'][0] != {'prompt_tokens':4214,'completion_tokens':358,'total_tokens':4572,'reasoning_tokens':0}: raise SystemExit('control_shape_or_accounting_mismatch')
        rows.append(r)
    put(z.output,{'schema_version':1,'classification':'exact_ordered_emitted_chunk_sequence','control_terminal_sha256':z.terminal_sha256,'rows':rows,'no_decode_reencode_or_normalization':True})
if __name__=='__main__': main()
