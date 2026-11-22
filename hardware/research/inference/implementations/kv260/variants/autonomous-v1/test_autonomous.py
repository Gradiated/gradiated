"""Bounded autonomous real-core checks against pinned prior scores and software outputs."""
import argparse,hashlib,json,os,signal,struct,subprocess,sys,time
from pathlib import Path
from materialise import materialise
HERE=Path(__file__).resolve().parent
SHA=lambda b:hashlib.sha256(b).hexdigest()
FRESH={
 "encoded-fu2p2q":("timed-01-1/runner.stdout","9b23c8df5cb52633fe05bc02871d246e5538cb94a301aff756f37bfc7aa458ba"),
 "encoded-hello":("timed-01-2/runner.stdout","e92f9d9d8ec33a6ccbfc715e42148a6aea441f017f89a931c08cad3a84197686"),
 "encoded-max48":("timed-01-3/runner.stdout","1edfbd04efc45975a02cfec629601de65d430491313f93984a56a4f232ddb8a1")}
def pinned(path,pin):
 b=path.read_bytes()
 if SHA(b)!=pin:raise ValueError(f'Pin differs: {path}')
 return b
def run(cmd,cwd,env,log,limit):
 start=time.monotonic()
 with log.open('x') as out:
  p=subprocess.Popen(cmd,cwd=cwd,env=env,stdout=out,stderr=subprocess.STDOUT,start_new_session=True)
  try:rc=p.wait(limit)
  except subprocess.TimeoutExpired:
   os.killpg(p.pid,signal.SIGTERM)
   try:p.wait(5)
   except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
   raise
 if rc:raise RuntimeError(f'Failed {rc}: {log}')
 return time.monotonic()-start
def main(a):
 out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 baseline=HERE.parents[1]/'rtl';tool=a.verilator.resolve()
 pin=json.loads((baseline/'toolchain.json').read_text())
 files={str(f.relative_to(tool)):SHA(f.read_bytes()) for f in sorted(tool.rglob('*')) if f.is_file()}
 if len(files)!=pin['tree_files'] or SHA(json.dumps(files,sort_keys=True,separators=(',',':')).encode())!=pin['tree_sha256']:raise ValueError('Simulator differs')
 manifest=json.loads(pinned(a.bundle/'package.json','b0394ba256d877fb62d6eb6e74942d5ff0c649cf751d53481e827c8bae5e9167'))
 weights=pinned(a.bundle/'model-words.bin',manifest['files']['model-words.bin']['sha256'])
 bos=json.loads(pinned(a.bundle/'bos-logits.json',manifest['files']['bos-logits.json']['sha256']))['logits']
 refs=json.loads(pinned(a.references,'33d290aed332af9e8b100a708222796d53f82529bb9c55d5d9ed13606cb0d367'))['cases']
 def hexfile(name,values):
  path=out/name;path.write_text(''.join(f'{x&0xffffffff:08x}\n' for x in values));return path
 model=hexfile('model.hex',struct.unpack('<29281I',weights));scores=hexfile('bos.hex',bos)
 names=materialise(baseline,out/'rtl')
 env=dict(os.environ,VERILATOR_ROOT=str(tool/'share/verilator'),PATH='/Library/Developer/CommandLineTools/usr/bin:/usr/bin:/bin:/usr/sbin:/sbin',SDKROOT='/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk')
 edge=out/'edge';edge.mkdir()
 edge_build=run([str(tool/'bin/verilator'),'--binary','--timing','--assert','-Wall','-Wno-fatal','--top-module','autonomous_edge_tb','-j','2','--Mdir',str(edge/'obj'),'-o','simulation',str(out/'rtl/axi_transformer.sv'),str(HERE/'tests/autonomous_edge_tb.sv')],out,env,edge/'compile.log',150)
 edge_run=run([str(edge/'obj/simulation')],out,env,edge/'simulation.log',150)
 print((edge/'simulation.log').read_text().splitlines()[0],flush=True)
 build_s=run([str(tool/'bin/verilator'),'--binary','--timing','--assert','-Wall','-Wno-fatal','--top-module','autonomous_core_tb','-j','2','--Mdir',str(out/'obj'),'-o','simulation',*[str(out/'rtl'/(n+'.sv')) for n in names],str(HERE/'tests/autonomous_core_tb.sv')],out,env,out/'compile.log',150)
 results=[]
 for name,cap in [('encoded-hello',255),('encoded-fu2p2q',255),('encoded-max48',255),('encoded-hello',1),('encoded-hello',0)]:
  relative,pin=FRESH[name];trace=json.loads(pinned(a.traces/relative,pin))['completion'];ref=refs[name]
  for key in ['prefix_tokens','generated_tokens','stop_reason']:
   if trace[key]!=ref[key]:raise ValueError(f'Prior trace does not match software reference: {name} {key}')
  prefix=len(ref['prefix_tokens']);n=len(trace['input_tokens']) if cap==255 else prefix
  expected=ref['generated_tokens'] if cap==255 else ref['generated_tokens'][:cap]
  reason=1 if cap==255 else 4
  case=out/(name+'-cap'+str(cap));case.mkdir()
  inp=hexfile(str(case.relative_to(out)/'input.hex'),trace['input_tokens'][:n])
  output=hexfile(str(case.relative_to(out)/'output.hex'),expected or [0])
  flat=hexfile(str(case.relative_to(out)/'scores.hex'),[x for f in trace['frames'][:n] for x in f['logits']])
  elapsed=run([str(out/'obj/simulation'),f'+MODEL={model}',f'+SCORES={scores}',f'+CSV={case}/events.csv',f'+RETURNS={case}/bos-returns.csv',f'+INPUT={inp}',f'+OUTPUT={output}',f'+ALLSCORES={flat}',f'+PREFIX={prefix}',f'+OUTPUTS={len(expected)}',f'+POSITIONS={n}',f'+CAP={cap}',f'+REASON={reason}'],out,env,case/'simulation.log',600)
  line=next(x for x in (case/'simulation.log').read_text().splitlines() if x.startswith('PASS '))
  entry={'case':name,'max_output':cap,'positions':n,'scores':n*320,'outputs':len(expected),'elapsed_s':elapsed,'result':line,'prior_score_trace_sha256':pin}
  results.append(entry);(out/'progress.json').write_text(json.dumps(results,indent=2)+'\n');print(json.dumps(entry),flush=True)
 result={'passed':True,'evidence_type':'rtl-simulation','compile_s':build_s,'cases':results,'limits':'Synthetic edges are separate. Scores compared against pinned previously accepted physical traces, outputs against pinned Mac integer software references. No new board measurement.'}
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser()
 for name in ['verilator','bundle','references','traces','output']:p.add_argument('--'+name,type=Path,required=True)
 main(p.parse_args())
