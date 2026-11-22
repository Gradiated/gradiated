"""Run the selected 27K transformer or simulate its projection and positional-rotation circuits."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import random
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import model
import runtime

P, R, DATA = runtime.PROJECT, runtime.RUNTIME, runtime.MODEL
RECIPE = {'name': 'prefix32', 'temperature': .8, 'sample_bytes': 32}
TRAINING = {'seed': 47, 'passes': 2000, 'batch_size': 8, 'learning_rate': .001,
            'weight_decay': .01, 'grad_clip': 1., 'supervised_tokens_per_pass': 4535}


def inputs():
    meta = runtime.read(DATA / 'selection.json')
    if (meta['schema'] != 1 or meta['configuration'] != model.config()
            or meta['parameters'] != 26720 or meta['recipe'] != RECIPE or meta['training'] != TRAINING):
        raise ValueError('Unreviewed model, training or decoding configuration.')
    expected = {'jokes.json', 'expected.jsonl', 'trace.json', 'trace.txt'}
    if set(meta['files_sha256']) != expected:
        raise ValueError('Unexpected model input manifest.')
    for name, digest in meta['files_sha256'].items():
        if Path(name).name != name or runtime.sha(DATA / name) != digest:
            raise ValueError('Frozen model input changed: ' + name)
    rows = runtime.read(DATA / 'jokes.json')
    if ([r['id'] for r in rows] != [f'J{i:02d}' for i in range(1,49)]
            or len({r['text'] for r in rows}) != 48
            or sum(len(model.sequence(r))-1 for r in rows) != 4535
            or max(len(model.sequence(r)) for r in rows) > 256):
        raise ValueError('Changed, duplicated or truncated training corpus.')
    return meta, rows


def load_selected(meta, mode='q8'):
    info = meta['weights'][mode]
    if info['path'] != 'models/tiny/' + mode or set(info['files']) != {'model.safetensors', 'config.json'}:
        raise ValueError('Invalid selected-model location.')
    path = R / info['path']
    for name, pin in info['files'].items():
        if Path(name).name != name or (path/name).stat().st_size != pin['bytes'] or runtime.sha(path/name) != pin['sha256']:
            raise ValueError('Missing or modified selected payload: ' + name)
    if runtime.read(path / 'config.json') != model.config():
        raise ValueError('Selected payload configuration differs.')
    return model.loaded(path, quantized=mode=='q8')


def source_identity():
    paths = ['generative.sh', 'uv.lock', 'pyproject.toml', 'tools/generative.py',
             'tools/model.py', 'tools/runtime.py', 'tools/llama_numpy_reference.py',
             'model/selection.json', 'model/jokes.json', 'model/expected.jsonl',
             'tools/fixed.py', 'hardware.md', 'model/fixed.json', 'tools/rtl.py',
             'rtl/mac32.sv', 'rtl/mac32_tb.sv', 'rtl/toolchain.json', 'rtl/viewer.html',
             'rtl/qk_rope.sv', 'rtl/qk_rope_tb.sv', 'rtl/rope_viewer.html',
             'rtl/kv_cache.sv', 'rtl/kv_cache_tb.sv', 'rtl/cache_viewer.html',
             'model/conditioned.json', 'model/conditioned.md']
    return {name: runtime.sha(P/name) for name in paths}


def text_seed(text):
    return int.from_bytes(hashlib.sha256(text.encode()).digest()[:4], 'little') & 0x7fffffff


def verify(meta, rows, report, folder):
    """Regression against the actual pre-cleanup outputs, including the failure."""
    import mlx.core as mx
    import mlx.optimizers as optim
    net = load_selected(meta)
    expected = [json.loads(line) for line in (DATA/'expected.jsonl').read_text().splitlines()]
    if [v['seed'] for v in expected] != list(range(10001,10129)):
        raise ValueError('Expected exactly the original 128 confirmation seeds.')
    generation = model.grade(model.sample(net, [v['seed'] for v in expected], RECIPE), rows)
    for actual, reference in zip(generation['results'], expected):
        for key in ('seed','tokens','eos','text','valid_utf8_bytes','matched_joke'):
            if actual[key] != reference[key]:
                raise ValueError(f'Pre-cleanup output changed: seed {reference["seed"]}, {key}')
    if not model.qualifies(generation, final=True):
        raise ValueError('Original finite-joke gate failed.')
    report['confirmation'] = generation
    report['q8_numerics'] = model.numerical(net, rows)
    report['singletons'] = []
    for seed in (10001,10007,10031,10125,10128):
        one = model.sample(net,[seed],RECIPE)
        if one['results'][0]['tokens'] != expected[seed-10001]['tokens']:
            raise ValueError('Singleton/batch replay changed.')
        report['singletons'].append(one)
    trace = model.sample(net,[47],RECIPE,trace=True)
    old_trace = runtime.read(DATA/'trace.json')['results'][0]
    if trace['results'][0]['tokens'] != old_trace['tokens']:
        raise ValueError('Recorded seed-47 sampling trace changed.')
    report['sampling_trace'] = trace
    del net
    net = load_selected(meta,'fp32')
    count = sum(v.size for v in model.tensors(net).values())
    if count != 26720:
        raise ValueError('Parameter census changed.')
    report['parameters'] = count
    report['fp32_numerics'] = model.numerical(net,rows)
    del net
    # One real optimizer update validates the retained training path without retraining a selected model.
    mx.random.seed(47)
    fresh = model.new_model()
    x,y,mask = model.batch(rows[:8])
    if int(mask.sum().item()) != 851 or not mx.all(mask[:,0]==1).item() or mx.any(x>=258).item():
        raise ValueError('First-byte/EOS supervision or no-ID protocol changed.')
    opt = optim.AdamW(learning_rate=.001,weight_decay=.01)
    loss,norm = model.updater(fresh,opt)(x,y,mask)
    mx.eval(fresh.parameters(),opt.state,loss,norm)
    model.finite(fresh)
    if not math.isfinite(float(loss.item())+float(norm.item())):
        raise FloatingPointError('Training smoke is nonfinite.')
    report['training_smoke'] = {'loss':float(loss.item()), 'mask_tokens':851,
                                'first_byte_supervised':True, 'selected_weights_unchanged':True}
    import fixed
    report['fixed_numerics'] = fixed.verify_selected(meta,rows,RECIPE)
    report['accepted'] = True
    print('Verified: 128/128 pre-cleanup token sequences unchanged; 127 exact jokes, 41 distinct; known failure retained.',flush=True)
    print('FP32/q8 NumPy, cache, packing, parameter census and real training-step checks passed.',flush=True)
    print('Fixed-point: all 128 frozen token hashes and the real Q-row integer oracle passed.',flush=True)


def train(meta,rows,report,folder):
    """Explicit opt-in reproduction recipe; exports cannot overwrite selected weights."""
    import mlx.core as mx
    import mlx.nn as nn
    import mlx.optimizers as optim
    mx.random.seed(TRAINING['seed'])
    rng = random.Random(TRAINING['seed'])
    net = model.new_model()
    mx.eval(net.parameters())
    opt = optim.AdamW(learning_rate=.001,weight_decay=.01)
    update = model.updater(net,opt)
    started = time.perf_counter()
    report['training'] = dict(TRAINING)
    report['metrics'] = []
    for epoch in range(1,2001):
        net.train()
        order = list(range(48));rng.shuffle(order)
        total = 0.
        for k in range(0,48,8):
            loss,norm = update(*model.batch([rows[i] for i in order[k:k+8]]))
            mx.eval(net.parameters(),opt.state,loss,norm)
            value,gradient = float(loss.item()),float(norm.item())
            if not math.isfinite(value+gradient):
                raise FloatingPointError('Nonfinite training loss or gradient.')
            total += value
        if epoch%100==0:
            metric = {'pass':epoch,'mean_batch_loss':total/6}
            report['metrics'].append(metric)
            print(json.dumps(metric),flush=True)
            runtime.save(folder/'results.json',report)
    net.eval();model.finite(net)
    report['training_seconds'] = time.perf_counter()-started
    report['fp32'] = model.export(net,folder/'fp32')
    report['fp32_numerics'] = model.numerical(net,rows)
    nn.quantize(net,group_size=32,bits=8,mode='affine');mx.eval(net.parameters())
    report['q8'] = model.export(net,folder/'q8')
    report['q8_numerics'] = model.numerical(net,rows)
    report['generation'] = model.grade(model.sample(net,list(range(64)),RECIPE),rows)
    print('Training finished. New exports are in '+str(folder)+'. Selected weights are unchanged.',flush=True)


def chat(args,meta,report,folder):
    if args.format=='fixed':
        import fixed
        net,manifest = fixed.selected(meta)
        sampler = fixed.sample
        print(f'Fixed-point software on Mac CPU: 16-bit weights, {manifest["activation_bits"]}-bit working values; not FPGA execution.',flush=True)
    else:
        net = load_selected(meta)
        sampler = model.sample
    report['numeric_format'] = args.format
    report['attempts'] = []
    print('Generative intern: BOS only; no joke IDs. Enter=random seed, text=reproducible sampling seed, q=quit. Repeats are possible.',flush=True)
    index = 0
    while True:
        try:
            action = input('\nNext: ').strip()
        except (EOFError,KeyboardInterrupt):
            break
        if action=='q':
            break
        seed = text_seed(action) if action else ((args.seed+index)&0x7fffffff if args.seed is not None else int.from_bytes(os.urandom(4),'little')&0x7fffffff)
        index += 1
        result = sampler(net,[seed],RECIPE)
        report['attempts'].append(result)
        if args.format=='fixed':report['cumulative_fixed_ranges'] = {k:dict(v) for k,v in net.stats.items()}
        runtime.save(folder/'results.json',report)
        item = result['results'][0]
        print('Intern: '+model.terminal(item['text']),flush=True)
        if not item['eos']:
            print('[Generation reached its length limit.]',flush=True)



def experiment_path(path):
    path=path.resolve()
    path.relative_to((R/'outputs/tiny').resolve())
    return path


def candidate_load(path,optimizer=False):
    import mlx.core as mx
    from mlx.utils import tree_unflatten
    path=experiment_path(path)
    record=runtime.read(path/'candidate.json')
    if record['configuration']!=model.config():raise ValueError('Candidate geometry changed.')
    for name,info in record['files'].items():
        if Path(name).name!=name:raise ValueError('Invalid candidate path.')
        file=path/'checkpoint'/name
        if file.stat().st_size!=info['bytes'] or runtime.sha(file)!=info['sha256']:raise ValueError('Candidate hash mismatch: '+name)
    net=model.loaded(path/'checkpoint')
    state=tree_unflatten(list(mx.load(str(path/'checkpoint/optimizer.safetensors')).items())) if optimizer else None
    return net,record,state


def candidate_save(net,opt,folder,record):
    import mlx.core as mx
    from mlx.utils import tree_flatten
    target=folder/'checkpoint';target.mkdir()
    mx.save_safetensors(str(target/'model.safetensors'),model.tensors(net))
    mx.save_safetensors(str(target/'optimizer.safetensors'),dict(tree_flatten(opt.state)))
    runtime.save(target/'config.json',model.config())
    record['files']={n:dict(bytes=(target/n).stat().st_size,sha256=runtime.sha(target/n))
                     for n in ('model.safetensors','optimizer.safetensors','config.json')}
    record['configuration']=model.config()
    runtime.save(folder/'candidate.json',record)
    loaded,_,_=candidate_load(folder)
    if any(not mx.array_equal(v,model.tensors(loaded)[n]).item() for n,v in model.tensors(net).items()):
        raise ValueError('Candidate exact reload failed.')


def conditioned_pin(info,manifest):
    path=experiment_path(R/info['runtime_path'])
    if (path/manifest).stat().st_size!=info['bytes'] or runtime.sha(path/manifest)!=info['sha256']:raise ValueError('Conditioned selection manifest hash differs.')
    return path


def conditioned_fixed_load(path,candidate):
    import fixed as fx
    import numpy as np
    import mlx.core as mx
    path=experiment_path(path);record=runtime.read(path/'converted.json')
    source=experiment_path(candidate)/'candidate.json'
    if runtime.read(source)!=record['candidate']:raise ValueError('Converted candidate protocol differs.')
    if runtime.sha(source)!=record['source_candidate_sha256']:
        raise ValueError('Integer source candidate differs.')
    if runtime.sha(path/'arithmetic.json')!=record['arithmetic_sha256']:raise ValueError('Integer arithmetic manifest changed.')
    manifest=runtime.read(path/'arithmetic.json')
    if manifest['implementation_sha256']!=fx.implementation_sha256():raise ValueError('Integer implementation changed.')
    info=manifest['images'];image=path/'fixed-tensors.safetensors'
    if info['file']!=image.name or image.stat().st_size!=info['bytes'] or runtime.sha(image)!=info['sha256']:
        raise ValueError('Converted integer image changed.')
    fx.dependencies();saved=mx.load(str(image));expected=info['arrays']
    if set(saved)!=set(expected):raise ValueError('Integer tensor keys differ.')
    net=fx.Fixed.__new__(fx.Fixed);net.we=manifest['weight_exponents'];net.e=manifest['activation_exponents']
    net.activation_bits=manifest['activation_bits'];net.q={};net.stats={}
    for name,info in expected.items():
        a=np.array(saved[name])
        if list(a.shape)!=info['shape'] or a.dtype.str!=info['dtype'] or a.nbytes!=info['bytes']:
            raise ValueError('Integer tensor metadata differs.')
        a=a.astype(np.int64)
        if name in fx.NAMES:net.q[name]=a
        elif name in ('rope','exp_table','rsqrt_table'):setattr(net,name,a)
        else:raise ValueError('Unexpected integer tensor.')
    for key,value in net.manifest().items():
        if manifest[key]!=value:raise ValueError('Integer contract differs: '+key)
    return net,record['candidate']


def conditioned_convert(native,record,args,corpus,rows,report,folder):
    import numpy as np
    import fixed as fx
    fx.dependencies()
    original,_=model.numpy_weights(native)
    weights={short:original[full] for short,full in fx.NAMES.items()}
    protocol=dict(answer_marker=record.get('answer_marker',True),encoding=record.get('encoding','bytes'))
    # Calibration is limited to training teachers and development generations.
    teachers=[model.conditioned_prefix(r['input'],**protocol)+list(r['suffix_target'].encode())
              for r in corpus['train'][:96]]
    dev=model.conditioned_decode(native,[r['input'] for r in corpus['development']],**protocol)
    paths=teachers+[r['input_tokens']+r['tokens'] for r in dev['results'] if all(t<320 for t in r['tokens'])]
    ranges=dict.fromkeys(fx.ACTIVATIONS,0.)
    for ids in paths:
        _,states,_=fx.float_forward(weights,np.asarray([ids],dtype=np.int64))
        for name in ranges:ranges[name]=max(ranges[name],float(np.abs(states[name]).max()))
    net=fx.Fixed(weights,ranges,activation_bits=16)
    report['calibration']=dict(training_paths=len(teachers),development_paths=len(dev['results']),activation_maxima=ranges,headroom=2,final_used=False)
    report['primitives']=fx.primitive_checks()
    checks=[]
    base=teachers[0]
    probes=[teachers[i] for i in (0,1,47)]+[[256],(base*((256+len(base)-1)//len(base)))[:256]]
    for ids in probes:
        x=np.asarray([ids],dtype=np.int64)
        full,states,cache=fx.integer_call(net,x)
        incremental=None;all_logits=[]
        for position,t in enumerate(ids):
            logits,part,incremental=fx.integer_call(net,np.asarray([[t]],dtype=np.int64),incremental)
            all_logits.append(logits[0,0])
            for name in states:
                expected=states[name][:,position:position+1]
                if name in ('scores','prob'):expected=states[name][:,:,position:position+1,:position+1]
                np.testing.assert_array_equal(expected,part[name])
        np.testing.assert_array_equal(full[0],np.asarray(all_logits))
        for a,b in zip(cache,incremental):np.testing.assert_array_equal(a,b)
        floating,_,_=fx.float_forward(weights,x)
        decoded=full.astype(np.float64)*2.**net.e['logits'];error=decoded-floating
        relative=np.sqrt(np.mean(error**2,axis=-1))/np.maximum(1,np.sqrt(np.mean(floating.astype(np.float64)**2,axis=-1)))
        checks.append(dict(positions=len(ids),all_states_and_cache_exact=True,max_logit_error=float(np.abs(error).max()),normalized_rmse=float(relative.max())))
    report['checks']=checks;report['saturation']=net.stats
    if any(v['saturated'] for v in net.stats.values()):raise ValueError('Integer conversion probes saturated.')
    if any(c['normalized_rmse']>.01 for c in checks):raise ValueError('Integer normalized error gate failed.')
    report['fixed']=net.freeze(folder)
    converted=dict(candidate=record,source_candidate_sha256=runtime.sha(args.candidate/'candidate.json'),arithmetic_sha256=runtime.sha(folder/'arithmetic.json'))
    runtime.save(folder/'converted.json',converted)
    reloaded,_=conditioned_fixed_load(folder,args.candidate)
    for name in net.q:np.testing.assert_array_equal(net.q[name],reloaded.q[name])
    report['accepted']=True
    print(json.dumps(dict(checks=checks,exponents=net.e,weight_exponents=net.we,saturations=0)),flush=True)


def conditioned_check(net,record,args,corpus,report,folder):
    import mlx.core as mx
    import mlx.optimizers as optim
    protocol=dict(answer_marker=record.get('answer_marker',True),encoding=record.get('encoding','bytes'))
    texts=[r['input'] for r in corpus['development'][:4]]+['fu2p2q','Hi!','fu2p2q']
    batch=model.conditioned_decode(net,texts,**protocol)['results']
    for text,row in zip(texts,batch):
        one=model.conditioned_decode(net,[text],**protocol)['results'][0]
        if one!=row:raise ValueError('Singleton or repeat differs.')
    # Four updates uninterrupted versus two, save/reload including Adam, then two.
    examples=[dict(input=r['input'],target=r['suffix_target']) for r in corpus['train'][:16]]
    x,y,m=model.conditioned_batch(examples,8.,**protocol)
    uninterrupted,_,_=candidate_load(args.candidate)
    opt=optim.AdamW(learning_rate=.0003,weight_decay=.01)
    update=model.updater(uninterrupted,opt)
    for _ in range(4):
        loss,norm=update(x,y,m);mx.eval(uninterrupted.parameters(),opt.state,loss,norm)
    interrupted,_,_=candidate_load(args.candidate)
    other=optim.AdamW(learning_rate=.0003,weight_decay=.01);update=model.updater(interrupted,other)
    for _ in range(2):
        loss,norm=update(x,y,m);mx.eval(interrupted.parameters(),other.state,loss,norm)
    resume=folder/'resume-check';resume.mkdir();candidate_save(interrupted,other,resume,dict(record))
    restored,_,state=candidate_load(resume,optimizer=True)
    resumed=optim.AdamW(learning_rate=.0003,weight_decay=.01);resumed.state=state;resumed.learning_rate=.0003
    update=model.updater(restored,resumed)
    for _ in range(2):
        loss,norm=update(x,y,m);mx.eval(restored.parameters(),resumed.state,loss,norm)
    import numpy as np
    differences={}
    for name,value in model.tensors(uninterrupted).items():
        a=np.array(value);b=np.array(model.tensors(restored)[name])
        differences[name]=float(np.abs(a-b).max())
        np.testing.assert_allclose(a,b,atol=1e-6,rtol=1e-6)
    from mlx.utils import tree_flatten
    a=dict(tree_flatten(opt.state));b=dict(tree_flatten(resumed.state))
    optimizer_difference=0.
    for key in a:
        aa=np.array(a[key]);bb=np.array(b[key])
        optimizer_difference=max(optimizer_difference,float(np.abs(aa-bb).max()))
        np.testing.assert_allclose(aa,bb,atol=1e-6,rtol=1e-6)
    ordinary=['hi','hello','hey','how are you','what do you do','tell me a joke','tell me another joke',
              'chips','chocolate chips','fish and chips','salt and vinegar','three weeks','what is tape-out?',
              'why','no','yes','a','b','x','1','42','12345','test','testing','random','asdf','qwerty','fu2p2q',
              'Who is your boss?','Are you an intern?','What company do you work for?',
              'Why is Nvidia better than you?','My dog ate the chip design.','Can you help me?',
              'I do not believe you.','That was terrible.','Good morning!','It is raining today.',
              'Explain quantum mechanics.','What is the meaning of life?','Please stop talking about chips.',
              'Do you have any cheese and onion?', 'hello world','HELLO','Hello','Hello!',
              ' x ','   hello   ','1 + 1 =','foo@example.com']
    _,targets=inputs()
    report['supplemental_user_like']=model.grade(model.conditioned_decode(net,ordinary,**protocol),targets)
    report.update(accepted=True,singletons_and_repeats=len(texts),optimizer_resume=dict(max_parameter_abs=max(differences.values()),max_optimizer_abs=optimizer_difference,atol=1e-6,rtol=1e-6))
    print(json.dumps(dict(singletons_and_repeats=len(texts),optimizer_resume=report['optimizer_resume'],supplemental={k:v for k,v in report['supplemental_user_like'].items() if k!='results'})),flush=True)


def conditioned(args,meta,rows,report,folder):
    import mlx.core as mx
    import mlx.optimizers as optim
    if args.stage=='conditioned-prepare':
        corpus=model.conditioned_corpus(rows,args.encoding)
        runtime.save(folder/'corpus.json',corpus)
        report['corpus']=dict(path=str(folder/'corpus.json'),sha256=runtime.sha(folder/'corpus.json'),
                             counts={n:len(corpus[n]) for n in ('train','development','final')})
        print(json.dumps(report['corpus']),flush=True);return
    if args.stage=='conditioned-chat':
        if args.format=='fixed':net,record=conditioned_fixed_load(args.fixed_candidate,args.candidate)
        else:net,record,_=candidate_load(args.candidate)
        text=json.loads(args.text_json)
        result=model.conditioned_decode(net,[text],fixed=args.format=='fixed',
            answer_marker=record.get('answer_marker',True),encoding=record.get('encoding','bytes'))
        report['generation']=result
        if args.format=='fixed':report['saturation']=net.stats
        row=result['results'][0]
        print('Intern: '+model.terminal(row['text']),flush=True)
        if not row['eos']:print('['+row['stop']+']',flush=True)
        return
    corpus_path=experiment_path(args.corpus);corpus=runtime.read(corpus_path)
    identity=runtime.sha(corpus_path)
    report.update(corpus_sha256=identity,corpus_path=str(corpus_path))
    if args.candidate:
        net,record,state=candidate_load(args.candidate,optimizer=args.stage=='conditioned-train')
        if record['corpus_sha256']!=identity:raise ValueError('Resuming with different corpus.')
    else:
        net=load_selected(meta,'fp32');state=None
        record=dict(step=0,corpus_sha256=identity,pairing=args.pairing,answer_marker=not args.no_answer_marker,encoding=args.encoding,
                    original_fp32_sha256=meta['weights']['fp32']['files']['model.safetensors']['sha256'])
    if args.stage=='conditioned-convert':
        conditioned_convert(net,record,args,corpus,rows,report,folder);return
    if args.stage=='conditioned-check':
        conditioned_check(net,record,args,corpus,report,folder);return
    if args.stage=='conditioned-probe':
        import numpy as np
        import llama_numpy_reference as ref
        from mlx_lm.models.cache import make_prompt_cache
        weights,_=model.numpy_weights(net)
        class Weights:
            def shape(self,n):return weights[n].shape
            def get(self,n,rows=None):return weights[n] if rows is None else weights[n][rows]
        checks=[]
        for entry in corpus['development'][:6]:
            prefix=model.conditioned_prefix(entry['input'],record.get('answer_marker',True),record.get('encoding','bytes'))
            target=rows[entry['input'].encode()[-1]%48]['text'] if record['pairing']=='suffix' else rows[0]['text']
            ids=prefix+list(target.encode())
            full=np.array(net(mx.array([ids]))[0],dtype=np.float32)
            cache=make_prompt_cache(net);incremental=[]
            for token in ids:incremental.append(np.array(net(mx.array([[token]]),cache=cache)[0,-1],dtype=np.float32))
            inc=np.array(incremental)
            expected=ref.forward(Weights(),model.config(),ids)
            np.testing.assert_allclose(full,inc,atol=.002,rtol=.0002)
            np.testing.assert_allclose(full[-1],expected,atol=.002,rtol=.0002)
            targets=np.array(ids[len(prefix):]+[257]);pred=full[len(prefix)-1:]
            z=pred-pred.max(axis=-1,keepdims=True);nll=-z[np.arange(len(targets)),targets]+np.log(np.exp(z).sum(axis=-1))
            checks.append(dict(input=entry['input'],length=len(ids),cache_max_abs=float(np.abs(full-inc).max()),
                               oracle_max_abs=float(np.abs(full[-1]-expected).max()),
                               first_16_nll=nll[:16].tolist(),teacher_errors=int(np.count_nonzero(pred.argmax(axis=-1)!=targets))))
        report['checks']=checks;report['accepted']=True
        print(json.dumps(checks),flush=True);return
    if args.stage=='conditioned-eval':
        texts=[r['input'] for r in corpus[args.split]]
        texts=texts[args.offset:args.offset+args.limit if args.limit else None]
        if args.format=='fixed':net,record=conditioned_fixed_load(args.fixed_candidate,args.candidate)
        start=time.monotonic()
        result=model.grade(model.conditioned_decode(net,texts,fixed=args.format=='fixed',answer_marker=record.get('answer_marker',True),encoding=record.get('encoding','bytes')),rows)
        report.update(candidate=record,split=args.split,offset=args.offset,generation=result,evaluation_seconds=time.monotonic()-start,numeric_format='fixed' if args.format=='fixed' else 'fp32')
        if args.format=='fixed':report['saturation']=net.stats
        summary={k:v for k,v in result.items() if k!='results'}
        print(json.dumps(summary),flush=True)
        for row in result['results'][:8]:print(json.dumps({k:row[k] for k in ('input','text','eos','matched_joke')},ensure_ascii=False),flush=True)
        return
    opt=optim.AdamW(learning_rate=args.learning_rate,weight_decay=.01)
    if state is not None:
        if record['pairing']!=args.pairing:raise ValueError('Pairing changed during resume.')
        opt.state=state
    opt.learning_rate=args.learning_rate
    if abs(float(opt.learning_rate.item())-args.learning_rate)>1e-10:raise ValueError('Optimizer rate differs.')
    update=model.updater(net,opt);net.train();start=time.monotonic()
    metrics=[];examples=corpus['train'];initial_step=record['step'];supervised=0
    forbidden={r['input'] for name in ('development','final') for r in corpus[name]}
    alphabet='abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*()_+-=[]{};:,.?/ '
    if record.get('fresh_prefixes',args.fresh_prefixes)!=args.fresh_prefixes:raise ValueError('Fresh-prefix regime changed on resume.')
    for step in range(initial_step+1,initial_step+args.steps+1):
        rng=random.Random(1979+step)
        selected=[examples[i] for i in rng.sample(range(len(examples)),16)]
        training=[]
        for r in selected:
            text=r['input']
            if args.fresh_prefixes and r['family']!='authored-edge':
                # Keep the suffix for this arm's training target; every earlier
                # character is fresh. This code is never called at inference.
                while True:
                    text=''.join(rng.choice(alphabet) for _ in range(len(text)-1))+r['input'][-1]
                    if text not in forbidden:break
            training.append(dict(input=text,target=r[args.pairing+'_target']))
        x,y,mask=model.conditioned_batch(training,args.start_weight,record.get('answer_marker',True),record.get('encoding','bytes'))
        loss,norm=update(x,y,mask);mx.eval(net.parameters(),opt.state,loss,norm)
        value,grad=float(loss.item()),float(norm.item())
        if not math.isfinite(value+grad):raise FloatingPointError('Nonfinite conditional training.')
        supervised+=int((mask>0).sum().item())
        if step%100==0:
            metric=dict(step=step,loss=value,gradient_norm=grad,elapsed_seconds=time.monotonic()-start)
            metrics.append(metric);print(json.dumps(metric),flush=True)
        if step%50==0 and time.monotonic()-start>125:break
    net.eval();model.finite(net)
    record.update(step=step,learning_rate=args.learning_rate,parent=str(args.candidate) if args.candidate else None,
                  supervised_tokens=record.get('supervised_tokens',0)+supervised,decoding='argmax-all-320',
                  training_pairing_only=True,fresh_prefixes=args.fresh_prefixes,start_weight=args.start_weight)
    candidate_save(net,opt,folder,record)
    report.update(candidate=record,metrics=metrics,training_seconds=time.monotonic()-start)
    print('Candidate saved: '+str(folder),flush=True)


def worker(args,meta,rows):
    import mlx.core as mx
    if os.environ.get('MLX_ENABLE_TF32')!='0':
        raise ValueError('Explicit full FP32 setting required.')
    folder = args.output.resolve()
    if folder.parent != (R/'outputs/tiny').resolve() or not folder.is_dir():
        raise ValueError('Worker output must be its pre-created runtime job directory.')
    mx.set_default_device(mx.gpu);mx.set_memory_limit(2*1024**3)
    source = source_identity()
    for name in source:
        destination = folder/'source'/name
        destination.parent.mkdir(parents=True,exist_ok=True)
        destination.write_bytes((P/name).read_bytes())
    report = {'state':'incomplete','stage':args.stage,'started_at':runtime.now(),
              'source_sha256':source,'packages':model.packages()}
    try:
        if args.stage.startswith('conditioned-'):conditioned(args,meta,rows,report,folder)
        elif args.stage=='chat':chat(args,meta,report,folder)
        elif args.stage=='verify':verify(meta,rows,report,folder)
        elif args.stage=='fixed':
            import fixed
            fixed.study(meta,rows,report,folder,load_selected,RECIPE,args.activation_bits,args.acceptance)
        elif args.stage=='rtl':
            import rtl
            rtl.run(folder,report,meta,rows,args.rtl_rows)
        elif args.stage=='rtl-rope':
            import rtl
            rtl.run_rope(folder,report,meta,rows)
        elif args.stage=='rtl-cache':
            import rtl
            rtl.run_cache(folder,report,meta,rows)
        elif args.stage=='fixed-smoke':
            import fixed
            report['fixed_primitives'] = fixed.primitive_checks()
            report['accepted'] = True
            print(json.dumps(report['fixed_primitives']),flush=True)
        else:train(meta,rows,report,folder)
        if source_identity()!=source:
            raise ValueError('Source changed during execution.')
        report.update(state='complete',completed_at=runtime.now(),peak_mlx_bytes=mx.get_peak_memory())
    except BaseException as error:
        report['error'] = {'type':type(error).__name__,'message':str(error)}
        raise
    finally:
        runtime.save(folder/'results.json',report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',choices=('chat','verify','train','validate','fixed','fixed-smoke','rtl','rtl-rope','rtl-cache','rtl-setup','conditioned-prepare','conditioned-train','conditioned-eval','conditioned-chat','conditioned-probe','conditioned-convert','conditioned-check'))
    parser.add_argument('--corpus',type=Path)
    parser.add_argument('--candidate',type=Path)
    parser.add_argument('--fixed-candidate',type=Path)
    parser.add_argument('--text-json',help='One actual text input encoded as a JSON string')
    parser.add_argument('--offset',type=int,default=0)
    parser.add_argument('--pairing',choices=('independent','suffix'),default='independent')
    parser.add_argument('--encoding',choices=('bytes','role48','hex'),default='bytes')
    parser.add_argument('--no-answer-marker',action='store_true')
    parser.add_argument('--start-weight',type=float,default=1.)
    parser.add_argument('--fresh-prefixes',action='store_true')
    parser.add_argument('--steps',type=int,default=800)
    parser.add_argument('--learning-rate',type=float,default=.0003)
    parser.add_argument('--split',choices=('development','final'),default='development')
    parser.add_argument('--limit',type=int)
    parser.add_argument('--seed',type=int)
    parser.add_argument('--format',choices=('q8','fixed'),default='q8',help='fixed uses integer arithmetic; ordinary chat defaults to q8, conditioned chat/eval to FP32')
    parser.add_argument('--activation-bits',type=int,choices=(16,18),help='fixed study only; default 16')
    parser.add_argument('--acceptance',choices=('strict','teaching'),help='fixed study only; default strict; teaching reports the absolute-error miss separately')
    parser.add_argument('--rtl-rows',type=int,choices=(1,32,96),help='RTL simulation only; default 96 (Q/K/V); 32 is Q-only, 1 is scalar')
    parser.add_argument('--inside',action='store_true',help=argparse.SUPPRESS)
    parser.add_argument('--output',type=Path,help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.seed is not None and not 0<=args.seed<2**31:
        parser.error('Seed must fit 31 nonnegative bits.')
    if args.format!='q8' and args.stage not in ('chat','conditioned-chat','conditioned-eval'):parser.error('--format applies to chat/conditioned evaluation only')
    if args.stage!='fixed' and (args.activation_bits is not None or args.acceptance is not None):
        parser.error('--activation-bits and --acceptance apply to fixed study only')
    if args.stage=='fixed':
        args.activation_bits = 16 if args.activation_bits is None else args.activation_bits
        args.acceptance = args.acceptance or 'strict'
    if args.rtl_rows is not None and args.stage!='rtl':parser.error('--rtl-rows applies to RTL simulation only')
    if args.stage=='rtl':args.rtl_rows = 96 if args.rtl_rows is None else args.rtl_rows
    if args.stage.startswith('conditioned-'):
        if args.seed is not None:parser.error('Conditioned generation has no seed or sampler.')
        if args.stage in ('conditioned-train','conditioned-eval','conditioned-probe','conditioned-convert','conditioned-check') and args.corpus is None:parser.error('--corpus required')
        if args.stage=='conditioned-chat' and args.candidate is None:
            selection=runtime.read(DATA/'conditioned.json')
            args.candidate=conditioned_pin(selection['fp32'],'candidate.json')
            if args.format=='fixed' and args.fixed_candidate is None:
                args.fixed_candidate=conditioned_pin(selection['fixed'],'converted.json')
        if args.format=='fixed' and args.fixed_candidate is None:parser.error('--fixed-candidate required')
        if args.text_json is not None:
            if args.stage!='conditioned-chat':parser.error('--text-json applies to conditioned-chat only')
            try:
                value=json.loads(args.text_json)
                if not isinstance(value,str):raise ValueError('Text must be a JSON string')
            except (ValueError,TypeError) as error:parser.error(str(error))
        if not 0<=args.offset<1000:parser.error('Invalid evaluation offset')
        if not 1<=args.start_weight<=32:parser.error('Invalid answer-start weight')
        if not 1<=args.steps<=4000:parser.error('--steps must be 1..4000 per bounded worker')
        if not 0<args.learning_rate<=.003:parser.error('Learning rate outside experiment range')
        if args.limit is not None and not 1<=args.limit<=1000:parser.error('Invalid evaluation limit')
    meta,rows = inputs()
    if args.stage=='rtl-setup':
        if args.inside or args.output is not None:parser.error('Tool setup is not a simulation worker')
        import rtl
        rtl.setup()
        return
    if args.stage=='validate':
        print('Validated the selected 26,720-parameter BOS-only model, frozen corpus and output fixtures.')
        return
    if args.inside:
        if args.output is None:parser.error('Worker output is required.')
        worker(args,meta,rows)
        return
    if args.output is not None:parser.error('--output is internal.')
    argv = [args.stage]+(['--seed',str(args.seed)] if args.seed is not None else [])
    if args.format!='q8':argv += ['--format',args.format]
    if args.stage=='fixed':argv += ['--activation-bits',str(args.activation_bits),'--acceptance',args.acceptance]
    if args.stage=='rtl':argv += ['--rtl-rows',str(args.rtl_rows)]
    if args.stage.startswith('conditioned-'):
        if args.corpus:argv += ['--corpus',str(args.corpus)]
        if args.candidate:argv += ['--candidate',str(args.candidate)]
        argv += ['--pairing',args.pairing,'--steps',str(args.steps),'--learning-rate',str(args.learning_rate),'--split',args.split]
        if args.limit:argv += ['--limit',str(args.limit)]
        if args.offset:argv += ['--offset',str(args.offset)]
        if args.fixed_candidate:argv += ['--fixed-candidate',str(args.fixed_candidate)]
        if args.text_json is not None:argv += ['--text-json',args.text_json]
        if args.fresh_prefixes:argv += ['--fresh-prefixes']
        if args.no_answer_marker:argv += ['--no-answer-marker']
        argv += ['--start-weight',str(args.start_weight),'--encoding',args.encoding]
        if args.stage=='conditioned-chat' and args.text_json is None:
            record=runtime.read(experiment_path(args.candidate)/'candidate.json')
            cap=48 if record.get('encoding') in ('role48','hex') else 96
            print(f'Text-conditioned transformer on Mac ({"W16A16 integer" if args.format=="fixed" else "FP32"}). Up to {cap} UTF-8 bytes; Ctrl-D quits. Same input repeats. Each input starts a fresh completion.',flush=True)
            while True:
                try:text=input('\nYou: ')
                except (EOFError,KeyboardInterrupt):break
                try:model.conditioned_prefix(text,record.get('answer_marker',True),record.get('encoding','bytes'))
                except ValueError as error:print(str(error),flush=True);continue
                code=runtime.supervise([*argv,'--text-json',json.dumps(text,ensure_ascii=True)],180)
                if code:raise SystemExit(code)
            return
        raise SystemExit(runtime.supervise(argv,180))
    timeout = {'verify':180,'fixed':1200,'fixed-smoke':120,'rtl':180,'rtl-rope':180,'rtl-cache':180}.get(args.stage,600)
    raise SystemExit(runtime.supervise(argv,timeout))


if __name__=='__main__':
    main()
