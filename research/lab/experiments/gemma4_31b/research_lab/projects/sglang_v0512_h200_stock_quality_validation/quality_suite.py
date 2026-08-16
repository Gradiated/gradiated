#!/usr/bin/env python3
"""Gemma-owned paired capture, executable scoring, and reference sentinel."""
import argparse, ast, hashlib, json, math, subprocess, sys, urllib.error, urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parent
SUITE=ROOT/'suite'
def canon(x): return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def sha(x): return hashlib.sha256(x).hexdigest()
def write(p,x): p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(canon(x)+b'\n')
def read(p): return json.loads(Path(p).read_text())

def cases():
    pads=' '.join(['the']*4100)
    nll=' '.join(['Gemma quality sentinel token sequence.']*40)
    rows=[
      ('tool_json','Return exactly JSON, no markdown: {"operation":"sum","arguments":{"a":19,"b":23}}.',{'kind':'json','expected':{'operation':'sum','arguments':{'a':19,'b':23}}}),
      ('python','Return only Python code defining `def median(xs):` for a nonempty integer list; it must return its middle value after sorting. No imports.',{'kind':'python','tests':['assert median([3,1,2])==2','assert median([9,1,5,3,7])==5']}),
      ('math','What is 17 * 19? Reply only with the decimal integer.',{'kind':'exact','expected':'323'}),
      ('long_key',pads+'\n\nThe verification key is: MINT-ORCHID-47. What is the verification key? Reply only with it.',{'kind':'exact','expected':'MINT-ORCHID-47'}),
      ('unicode_stop','Reply only with this exact Unicode text: café 東京 ✓',{'kind':'exact','expected':'café 東京 ✓','stream':True}),
      ('chat_template','You are continuing a conversation. Earlier user: My preferred fruit is pear. Earlier assistant: I will remember. Now reply only with the preferred fruit.',{'kind':'exact','expected':'pear','history':[{'role':'user','content':'My preferred fruit is pear.'},{'role':'assistant','content':'I will remember.'}]}),
      ('teacher_nll',nll,{'kind':'nll','minimum':128}),
    ]
    return [{'case_id':a,'prompt':b,'scorer':c,'critical':True,'content_sha256':sha(canon({'case_id':a,'prompt':b,'scorer':c,'critical':True}))} for a,b,c in rows]

def build():
    SUITE.mkdir(exist_ok=True)
    policy={'model':'google/gemma-4-31B-it','revision':'b9ea41a2887d8607f594846523f94c6cc75ac8a4','temperature':0.0,'top_p':1.0,'max_tokens':128,'repetitions':2,'max_nll_delta':0.03,'minimum_scored_tokens':128,'default_non_reasoning':True}
    write(SUITE/'policy.json',policy); (SUITE/'cases.jsonl').write_bytes(b''.join(canon(x)+b'\n' for x in cases()))
    files={p.name:sha(p.read_bytes()) for p in (SUITE/'policy.json',SUITE/'cases.jsonl')}; write(SUITE/'MANIFEST.json',{'files':files,'suite_sha256':sha(canon(files))})
    print(read(SUITE/'MANIFEST.json')['suite_sha256'])

def load():
    man=read(SUITE/'MANIFEST.json');
    if {p.name:sha(p.read_bytes()) for p in (SUITE/'policy.json',SUITE/'cases.jsonl')}!=man['files']: raise ValueError('suite hash mismatch')
    return read(SUITE/'policy.json'),[json.loads(x) for x in (SUITE/'cases.jsonl').read_text().splitlines()],man
def post(url,payload):
    raw=canon(payload); req=urllib.request.Request(url,data=raw,headers={'Content-Type':'application/json'},method='POST')
    try:
      with urllib.request.urlopen(req,timeout=240) as r: out=r.read()
    except urllib.error.HTTPError as e:
      raise ValueError(f'HTTP {e.code}: {e.read().decode("utf-8", "replace")[:2000]}') from e
    return json.loads(out),{'request_sha256':sha(raw),'response_sha256':sha(out),'request_bytes':raw.decode('utf-8'),'response_bytes':out.decode('utf-8','replace')}
def messages(c): return c['scorer'].get('history',[])+[{'role':'user','content':c['prompt']}]
def capture(base,out):
    pol,rows,man=load(); out=Path(out); out.mkdir(parents=True,exist_ok=True); captures=[]
    for c in rows:
      kind=c['scorer']['kind']; payload={'model':pol['model'],'messages':messages(c),'temperature':0.0,'top_p':1.0,'max_tokens':pol['max_tokens'],'stream':False}
      if kind=='nll':
        value,meta=post(base.rstrip('/')+'/generate',{'text':c['prompt'],'sampling_params':{'temperature':0.0,'max_new_tokens':1},'return_logprob':True,'logprob_start_len':0,'top_logprobs_num':0})
        vals=(value.get('meta_info') or {}).get('input_token_logprobs') or []
        norm=[{'logprob':float(x[0] if isinstance(x,list) else x['logprob']),'token_id':int(x[1] if isinstance(x,list) else x['token_id'])} for x in vals if (x[0] if isinstance(x,list) else x.get('logprob')) is not None]
        if len(norm)<c['scorer']['minimum'] or any(not math.isfinite(x['logprob']) or x['logprob']>0 for x in norm): raise ValueError('invalid runtime input logprobs')
        captures.append({'case_id':c['case_id'],'output':{'input_token_logprobs':norm},'raw':[meta]}); continue
      replies=[]; raw=[]
      for _ in range(pol['repetitions']):
        value,meta=post(base.rstrip('/')+'/v1/chat/completions',payload); choice=value.get('choices',[{}])[0]; msg=choice.get('message') or {}; content=msg.get('content')
        if not isinstance(content,str) or choice.get('finish_reason')=='length': raise ValueError('invalid chat response')
        usage=value.get('usage') or {}; 
        if not isinstance(usage.get('prompt_tokens'),int) or not isinstance(usage.get('completion_tokens'),int): raise ValueError('usage missing')
        replies.append(content); raw.append(meta|{'usage':usage})
      if len(set(replies))!=1:
        write(out/'CAPTURE_FAILURE.json',{'classification':'deterministic_repetition_mismatch','case_id':c['case_id'],'server_identity':{'base_url':base.rstrip('/'),'model':pol['model'],'revision':pol['revision'],'kv_cache_arm':out.name},'responses':[{'content':reply,'raw':meta} for reply,meta in zip(replies,raw)]})
        raise ValueError('deterministic repetition mismatch; raw evidence persisted')
      record={'case_id':c['case_id'],'output':replies[0],'raw':raw}
      if c['scorer'].get('stream'):
        stream_payload=payload|{'stream':True}; req=urllib.request.Request(base.rstrip('/')+'/v1/chat/completions',data=canon(stream_payload),headers={'Content-Type':'application/json'},method='POST')
        with urllib.request.urlopen(req,timeout=240) as r: blob=r.read().decode('utf-8')
        assembled=''.join(json.loads(line[6:])['choices'][0].get('delta',{}).get('content','') for line in blob.splitlines() if line.startswith('data: {'))
        if assembled!=replies[0]: raise ValueError('stream assembly mismatch')
        record['stream_assembled']=assembled
      captures.append(record)
    (out/'captures.jsonl').write_bytes(b''.join(canon(x)+b'\n' for x in captures)); write(out/'CAPTURE_TERMINAL.json',{'pass':True,'suite_sha256':man['suite_sha256'],'capture_sha256':sha((out/'captures.jsonl').read_bytes()),'cases':len(captures)})
def score(control,candidate,out):
    pol,rows,man=load(); a={x['case_id']:x for x in map(json.loads,Path(control).read_text().splitlines())}; b={x['case_id']:x for x in map(json.loads,Path(candidate).read_text().splitlines())}; results=[]
    for c in rows:
      x,y=a[c['case_id']]['output'],b[c['case_id']]['output']; k=c['scorer']['kind']
      def val(z):
       if k=='exact': return str(z).strip()==c['scorer']['expected']
       if k=='json':
        try:return json.loads(z)==c['scorer']['expected']
        except:return False
       if k=='python':
        try: ast.parse(z); r=subprocess.run([sys.executable,'-I','-c',z+'\n'+'\n'.join(c['scorer']['tests'])],timeout=2,capture_output=True); return r.returncode==0
        except:return False
       if k=='nll': return True
      results.append({'case_id':c['case_id'],'control_pass':val(x),'candidate_pass':val(y)})
    nll=lambda z:-sum(v['logprob'] for v in z['input_token_logprobs'])/len(z['input_token_logprobs'])
    cn=nll(a['teacher_nll']['output']); fn=nll(b['teacher_nll']['output']); passed=all(x['control_pass'] and x['candidate_pass'] for x in results) and fn-cn<=pol['max_nll_delta']
    write(Path(out),{'classification':'paired_quality_score','pass':passed,'suite_sha256':man['suite_sha256'],'cases':results,'control_nll':cn,'candidate_nll':fn,'nll_delta':fn-cn})
def main():
 p=argparse.ArgumentParser(); p.add_argument('mode',choices=['build','validate','capture','score']); p.add_argument('--base');p.add_argument('--output');p.add_argument('--control');p.add_argument('--candidate');a=p.parse_args()
 if a.mode=='build':build()
 elif a.mode=='validate':print(load()[2]['suite_sha256'])
 elif a.mode=='capture':capture(a.base,a.output)
 else:score(a.control,a.candidate,a.output)
if __name__=='__main__':main()
