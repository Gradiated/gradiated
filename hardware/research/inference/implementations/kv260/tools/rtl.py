"""Pinned local RTL simulator, independent fixtures and a trace-based teaching view."""
import csv
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import random
import signal
import subprocess
import tarfile
import time
import urllib.request

import runtime

RTL = runtime.PROJECT/'rtl'
PIN_SHA256 = 'b6a35af5636cca4a2f9bb82135a716873c8bb1abf6926504f2e425ea600df693'


def tool_pin():
    path = RTL/'toolchain.json'
    if runtime.sha(path)!=PIN_SHA256:raise ValueError('RTL toolchain pin changed')
    pin = runtime.read(path)
    if pin['runtime_root']!='toolchains/verilator-5.052/verilator/5.052':
        raise ValueError('Unreviewed RTL toolchain location')
    return pin


def tool_root(pin):
    root = runtime.RUNTIME/pin['runtime_root']
    files = {str(p.relative_to(root)):runtime.sha(p) for p in sorted(root.rglob('*')) if p.is_file()}
    digest = hashlib.sha256(json.dumps(files,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if len(files)!=pin['tree_files'] or digest!=pin['tree_sha256']:
        raise ValueError('Missing or modified simulator; run generative.sh rtl-setup')
    return root


def setup():
    """Explicit network-capable provisioning only; simulation workers remain offline."""
    pin = tool_pin()
    signal.signal(signal.SIGALRM,lambda *_: (_ for _ in ()).throw(TimeoutError('Tool setup exceeded 180 seconds')))
    signal.alarm(180)
    try:
        try:
            root = tool_root(pin)
            print('Pinned simulator already verified: '+str(root))
            return
        except ValueError:
            root = runtime.RUNTIME/pin['runtime_root']
            if root.exists():raise ValueError('Existing tool tree differs; refusing to overwrite it')
        base = runtime.RUNTIME/'toolchains';base.mkdir(parents=True,exist_ok=True)
        archive = base/'verilator-5.052-arm64-tahoe.tar.gz'
        if not archive.exists():
            with urllib.request.urlopen('https://ghcr.io/token?service=ghcr.io&scope=repository:homebrew/core/verilator:pull',timeout=30) as response:
                token = json.load(response)['token']
            request = urllib.request.Request(pin['bottle_url'])
            request.add_unredirected_header('Authorization','Bearer '+token)
            with urllib.request.urlopen(request,timeout=60) as response:data = response.read(pin['bottle_bytes']+1)
            if len(data)!=pin['bottle_bytes'] or hashlib.sha256(data).hexdigest()!=pin['bottle_sha256']:
                raise ValueError('Downloaded simulator bottle differs')
            archive.write_bytes(data)
        if archive.stat().st_size!=pin['bottle_bytes'] or runtime.sha(archive)!=pin['bottle_sha256']:
            raise ValueError('Simulator archive differs')
        destination = (base/'verilator-5.052').resolve()
        destination.mkdir(exist_ok=True)
        with tarfile.open(archive) as source:
            members = source.getmembers()
            if len(members)>2000 or sum(m.size for m in members)>150_000_000:
                raise ValueError('Unexpected archive size')
            for member in members:
                if (not (destination/member.name).resolve().is_relative_to(destination)
                        or member.issym() or member.islnk() or not (member.isfile() or member.isdir())):
                    raise ValueError('Unsafe simulator archive entry')
            source.extractall(destination)
        root = tool_root(pin)
        print('Installed verified simulator locally: '+str(root))
    finally:signal.alarm(0)


def oracle(x,w):
    """Unbounded integer products and Fraction/ties-even, independent of RTL/fixed.py."""
    if len(x)!=32 or len(w)!=32 or any(not -32768<=v<=32767 for v in [*x,*w]):
        raise ValueError('Exactly 32 signed 16-bit operand pairs required')
    products = [a*b for a,b in zip(x,w)]
    partials = [];total = 0
    for value in products:total += value;partials.append(total)
    rounded = round(Fraction(total,32768))
    return dict(products=products,partial_sums=partials,sum=total,rounded=rounded,
                result=min(32767,max(-32768,rounded)),saturated=int(not -32768<=rounded<=32767))


def scalar_synthetic_fixtures():
    """Original directed/random arithmetic cases, with no model payload dependency."""
    cases = []
    def add(name,x,w):cases.append(dict(name=name,x=x,w=w,expected=oracle(x,w)))
    add('Zero',[0]*32,[0]*32)
    add('Unit operands',[1]*32,[1]*32)
    for a,b in ((32767,32767),(-32768,-32768),(-32768,32767),(32767,-32768)):
        add(f'Extrema {a} x {b}',[a]*32,[b]*32)
    add('Exact cancellation',[-32767,32767]*16,[32767]*32)
    for a in (-5,-3,-1,1,3,5):add(f'Tie {a}/2',[a]+[0]*31,[16384]+[0]*31)
    for b in (-16385,-16383,16383,16385):add(f'Adjacent to half {b}',[1]+[0]*31,[b]+[0]*31)
    add('Positive output limit',[32767,32767]+[0]*30,[32767,1]+[0]*30)
    add('Negative output limit',[-32768,-32768]+[0]*30,[32767,1]+[0]*30)
    add('Positive clipping',[-32768]+[0]*31,[-32768]+[0]*31)
    add('Negative clipping',[-32768,-32768]+[0]*30,[32767,2]+[0]*30)
    rng = random.Random(20261102)
    for i in range(128):
        limit = 2048 if i<96 else 32768
        add(f'Random {i:03d}',[rng.randrange(-limit,limit) for _ in range(32)],
            [rng.randrange(-limit,limit) for _ in range(32)])
    return cases


def fixtures():
    import fixed
    path = runtime.MODEL/'fixed.json'
    if runtime.sha(path)!=fixed.SELECTED_SHA256:raise ValueError('Fixed model manifest changed')
    manifest = runtime.read(path);trace = manifest['teaching_projection']
    if (manifest['activation_bits']!=16 or trace['activation_bits']!=16 or trace['weight_bits']!=16
            or trace['accumulator_exponent']!=-26 or trace['output_exponent']!=-11):
        raise ValueError('Projection is not the selected 16-bit/shift-15 format')
    image = runtime.RUNTIME/manifest['runtime_path']/manifest['images']['file']
    if runtime.sha(image)!=manifest['images']['sha256']:raise ValueError('Fixed payload changed')
    expected = oracle(trace['input_values'],trace['weight_values'])
    if (expected['products']!=trace['products'] or expected['partial_sums']!=trace['partial_sums']
            or expected['sum']!=trace['accumulator'] or expected['result']!=trace['output']):
        raise ValueError('Pinned teaching trace fails independent oracle')
    return [dict(name='Real BOS / first Q coordinate',x=trace['input_values'],
                 w=trace['weight_values'],expected=expected),*scalar_synthetic_fixtures()]


def matrix_case(name,x,weights):
    if len(weights) not in (1,32,96):raise ValueError('One, 32 or 96 output rows required')
    return dict(name=name,x=list(x),weights=[list(w) for w in weights],
                expected=[oracle(x,w) for w in weights])


def projection_layout(manifest,output_rows):
    if output_rows not in (1,32,96):raise ValueError('Unsupported projection geometry')
    names = ('Q','K','V') if output_rows==96 else ('Q',)
    descriptions = {'Q':'Query: what information to look for',
                    'K':'Key: labels used to find relevant information',
                    'V':'Value: information to gather'}
    layout = []
    for i,name in enumerate(names):
        source = manifest['activation_exponents']['norm1']+manifest['weight_exponents'][name]
        target = manifest['activation_exponents'][name.lower()]
        if target-source!=15:raise ValueError('Projection rescaling is not the circuit shift of 15')
        layout.append(dict(name=name,start=32*i,count=1 if output_rows==1 else 32,
                           accumulator_exponent=source,output_exponent=target,description=descriptions[name]))
    return layout


def reset_probe_count(output_rows):
    return 8 if output_rows==96 else 6 if output_rows>1 else 5


def matrix_fixtures(meta,targets,output_rows=32):
    """Real Q/K/V projections cross-checked with the pinned full integer model."""
    import fixed
    import model
    net,manifest = fixed.selected(meta)
    layout = projection_layout(manifest,output_rows)
    names = [p['name'] for p in layout]
    np = fixed.np
    weights = [row for name in names for row in net.q[name].tolist()]
    longest = max(targets,key=lambda r:len(model.sequence(r)))
    probes = [(targets[0],1),(targets[0],2),(targets[2],3),(targets[7],7),
              (targets[2],18),(targets[47],63),(longest,128)]
    cases = []
    for target,length in probes:
        tokens = model.sequence(target)[:length]
        if len(tokens)!=length:raise ValueError('Real projection prefix was truncated')
        _,states,_ = fixed.integer_call(net,np.asarray([tokens],dtype=np.int64))
        x = states['norm1'][0,-1].tolist()
        case = matrix_case('Model '+target['id']+' / prefix '+str(length),x,weights)
        outputs = [row['result'] for row in case['expected']]
        references = {name:states[name.lower()][0,-1].tolist() for name in names}
        if outputs!=[v for name in names for v in references[name]] or any(row['saturated'] for row in case['expected']):
            raise ValueError('Independent matrix oracle differs from integer model projections')
        case['model_reference'] = dict(joke_id=target['id'],prefix_length=length,q=references['Q'],vectors=references)
        cases.append(case)
    if cases[0]['expected'][0]['result']!=-115:raise ValueError('Original first Q output changed')
    return cases+matrix_synthetic_fixtures(output_rows)


def matrix_synthetic_fixtures(output_rows):
    """Same matrix arithmetic cases used by the Mac suite, without real-model probes."""
    cases = []
    for case in scalar_synthetic_fixtures()[:21]:
        w = case['w']
        cases.append(matrix_case(case['name'],case['x'],[w[r%32:]+w[:r%32] for r in range(output_rows)]))
    for reverse in (False,True):
        weights = [[(32767,-32768,16384)[r//32] if j==(31-r%32 if reverse else r%32) else 0
                    for j in range(32)] for r in range(output_rows)]
        cases.append(matrix_case('Reversed identity' if reverse else 'Identity',list(range(1,33)),weights))
    rng = random.Random(2026110232)
    for i in range(16):
        limit = 2048 if i<8 else 32768
        cases.append(matrix_case('Random matrix '+str(i),[rng.randrange(-limit,limit) for _ in range(32)],
                                 [[rng.randrange(-limit,limit) for _ in range(32)] for _ in range(output_rows)]))
    return cases


def check_trace(path,cases):
    cases = [c if 'weights' in c else matrix_case(c.get('name','Fixture'),c['x'],[c['w']]) for c in cases]
    output_rows = len(cases[0]['weights'])
    reset_probes = reset_probe_count(output_rows)
    term_checks = 0
    seen_labels = set()
    real = []
    def check_case(label,rows):
        nonlocal term_checks,real
        if label in seen_labels or not 0<=label<len(cases)+reset_probes+1:
            raise ValueError('Duplicate or invalid matrix transaction label')
        seen_labels.add(label)
        if label==0:real = rows
        case = cases[label] if label<len(cases) else cases[0]
        if {r.get('step_row',0) for r in rows if r['step_valid']}!=set(range(output_rows)):
            raise ValueError('Missing or invalid observed step row')
        if {r.get('result_row',0) for r in rows if r['result_valid']}!=set(range(output_rows)):
            raise ValueError('Missing or invalid observed result row')
        for output_row in range(output_rows):
            expected = case['expected'][output_row]
            steps = [r for r in rows if r['step_valid'] and r.get('step_row',0)==output_row]
            if len(steps)!=32:raise ValueError('Not exactly 32 observed terms per row')
            for i,row in enumerate(steps):
                if (row['step_index']!=i or row['operand_x']!=case['x'][i]
                        or row['operand_w']!=case['weights'][output_row][i]
                        or row['step_product']!=expected['products'][i]
                        or row['step_sum']!=expected['partial_sums'][i]
                        or row['accumulator']!=row['step_sum']):
                    raise ValueError('Independent observed product/sum mismatch')
                term_checks += 1
            start = next(r for r in rows if r['phase']==1 and r.get('row',0)==output_row and not r['step_valid'])
            results = [r for r in rows if r['result_valid'] and r.get('result_row',0)==output_row]
            if results[0]['cycle']-start['cycle']!=65:raise ValueError('Observed row latency differs')
            if any(r['result']!=expected['result'] or r['saturated']!=expected['saturated'] for r in results):
                raise ValueError('Independent observed rounding/saturation mismatch')

    # Only retain one request at a time; a 96-output trace need not stay in RAM.
    current = None;rows = []
    with path.open() as source:
        for values in csv.DictReader(source):
            row = {k:int(v) for k,v in values.items()}
            label = row['case']
            if label<0:continue # Interrupted/reset probes are asserted by the testbench.
            if current is not None and label!=current:
                check_case(current,rows);rows = []
            current = label;rows.append(row)
    if current is not None:check_case(current,rows)
    if seen_labels!=set(range(len(cases)+reset_probes+1)):
        raise ValueError('Missing completed matrix request')
    transactions = len(cases)+reset_probes+1
    return dict(full_transactions=transactions,output_rows=output_rows,outputs_checked=transactions*output_rows,
                terms_checked=term_checks,row_latency_edges=65,reset_probes=reset_probes,all_exact=True),real


def simulation_tools(folder,report,section):
    pin = tool_pin();root = tool_root(pin)
    details = report[section]
    env = runtime.clean_environment(runtime.RUNTIME,os.environ)
    env.update(PATH='/Library/Developer/CommandLineTools/usr/bin:/usr/bin:/bin:/usr/sbin:/sbin',
               SDKROOT='/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk',
               VERILATOR_ROOT=str(root/'share/verilator'),
               CLANG_MODULE_CACHE_PATH=str(folder/'clang-cache'))
    deadline = time.monotonic()+150
    commands = details['commands']
    def command(name,argv):
        started = time.monotonic()
        log = folder/(name+'.log')
        with log.open('w') as stream:
            result = subprocess.run(argv,cwd=folder,env=env,stdout=stream,stderr=subprocess.STDOUT,
                                    timeout=max(.1,deadline-time.monotonic()),check=False)
        commands.append(dict(name=name,argv=argv,seconds=time.monotonic()-started,exit_code=result.returncode,log=log.name))
        runtime.save(folder/'results.json',report)
        if result.returncode:
            print(log.read_text()[-6000:],flush=True)
            raise RuntimeError(name+' failed; see '+str(log))
        return log.read_text()
    compiler_path = Path('/Library/Developer/CommandLineTools/usr/bin/clang++')
    sdk = Path('/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk')
    compiler = dict(path=str(compiler_path),sha256=runtime.sha(compiler_path),
                    version=command('compiler-version',[str(compiler_path),'--version']).strip(),
                    sdk=str(sdk),sdk_settings_sha256=runtime.sha(sdk/'SDKSettings.json'))
    version = command('version',[str(root/'bin/verilator'),'--version']).strip()
    if version!=pin['version_stdout']:raise ValueError('Simulator version differs')
    return pin,root,compiler,version,command


def run(folder,report,meta,targets,output_rows=96):
    details = report['rtl'] = dict(state='incomplete',commands=[])
    cases = matrix_fixtures(meta,targets,output_rows) if output_rows>1 else [matrix_case(c['name'],c['x'],[c['w']]) for c in fixtures()]
    runtime.save(folder/'fixtures.json',cases)
    def hexfile(name,values,width):
        path = folder/name
        path.write_text(''.join(f'{v&((1<<width)-1):0{width//4}x}\n' for v in values))
        return path
    paths = {k:hexfile(k+'.hex',values,bits) for k,values,bits in (
        ('inputs',[v for c in cases for v in c['x']],16),
        ('weights',[v for c in cases for row in c['weights'] for v in row],16),
        ('answers',[e['result'] for c in cases for e in c['expected']],16),
        ('clips',[e['saturated'] for c in cases for e in c['expected']],8))}
    pin,root,compiler,version,command = simulation_tools(folder,report,'rtl')
    command('compile',[str(root/'bin/verilator'),'--binary','--timing','--trace','--assert','-Wall',
                       '--top-module','mac32_tb',f'-GROWS={output_rows}','-j','2','--Mdir',str(folder/'obj'),'-o','simulation',
                       '-CFLAGS','-isysroot /Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk',
                       '-LDFLAGS','-isysroot /Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk',
                       str(RTL/'mac32.sv'),str(RTL/'mac32_tb.sv')])
    csvpath = folder/'cycles.csv';vcdpath = folder/'waves.vcd'
    output = command('simulation',[str(folder/'obj/simulation'),f'+CASES={len(cases)}',
                     '+X='+str(paths['inputs']),'+W='+str(paths['weights']),
                     '+ANSWERS='+str(paths['answers']),'+CLIPS='+str(paths['clips']),
                     '+CSV='+str(csvpath),'+VCD='+str(vcdpath)])
    reset_probes = reset_probe_count(output_rows)
    wanted = f'PASS full_transactions={len(cases)+reset_probes+1} output_rows={output_rows} reset_probes={reset_probes} row_latency_edges=65'
    if wanted not in output:raise ValueError('Missing testbench success receipt')
    checked,real = check_trace(csvpath,cases)
    layout = projection_layout(runtime.read(runtime.MODEL/'fixed.json'),output_rows)
    view = dict(projections=layout,cycles=real,expected=cases[0]['expected'],name=cases[0]['name'],
                inputs=cases[0]['x'],weights=cases[0]['weights'],checks=checked,simulator=version)
    template = (RTL/'viewer.html').read_text()
    (folder/'projection.html').write_text(template.replace('__SIMULATION_DATA__',json.dumps(view).replace('</','<\\/')))
    report['rtl'] = dict(state='complete',compiler=compiler,simulator=version,tool_tree_sha256=pin['tree_sha256'],
        projections=layout,fixture_cases=len(cases),oracle='Independent unbounded Python integers and Fraction nearest-even',
        checks=checked,real_projection=cases[0]['expected'],
        full_integer_model_probes=[c['model_reference'] for c in cases if 'model_reference' in c],commands=details['commands'],
        artifacts={name:dict(bytes=(folder/name).stat().st_size,sha256=runtime.sha(folder/name))
                   for name in ('cycles.csv','waves.vcd','projection.html','fixtures.json')},
        limits='RTL simulation of Q/K/V linear projections before RoPE;  input normalization is still prepared in Python. No synthesis, board or full-transformer RTL result')
    report['accepted'] = True
    print(wanted,flush=True)
    print('Independent Python oracle: '+str(checked),flush=True)
    for projection in layout:
        begin = projection['start'];end = begin+projection['count']
        print('Real model '+projection['name']+' outputs: '+str([e['result'] for e in cases[0]['expected'][begin:end]]),flush=True)
    print('Teaching view: '+str(folder/'projection.html'),flush=True)


def rope_layout(manifest):
    """Refuse any arithmetic contract different from this specific teaching circuit."""
    if (manifest['activation_bits']!=16 or manifest['rope_fraction_bits']!=14
            or any(manifest['activation_exponents'][key]!=-11 for key in ('q','k','qrot','krot'))):
        raise ValueError('RoPE circuit requires signed16 Q/K at exponent -11 and Q14 coefficients')
    return dict(heads=2,head_width=16,pairs_per_head=8,positions=256,
                input_exponent=-11,output_exponent=-11,coefficient_exponent=-14)


def rope_case(name,values,coefficients,position):
    """Independent unbounded arithmetic, split-half pairing and Fraction rounding."""
    if (len(values)!=64 or len(coefficients)!=8 or any(len(row)!=2 for row in coefficients)
            or not 0<=position<256
            or any(not -32768<=v<=32767 for v in [*values,*[v for row in coefficients for v in row]])):
        raise ValueError('RoPE needs 64 signed16 values, eight signed16 coefficient pairs and position 0..255')
    expected = [];outputs = [None]*64
    for pair in range(32):
        ia = (pair//16)*32+((pair//8)%2)*16+pair%8;ib = ia+8
        a,b = values[ia],values[ib];c,s = coefficients[pair%8]
        products = [a*c,b*s,b*c,a*s]
        totals = [products[0],products[0]-products[1],products[2],products[2]+products[3]]
        rounded = [round(Fraction(totals[j],16384)) for j in (1,3)]
        result = [min(32767,max(-32768,v)) for v in rounded]
        saturated = sum(int(not -32768<=v<=32767)<<j for j,v in enumerate(rounded))
        expected.append(dict(pair=pair,index_a=ia,index_b=ib,products=products,totals=totals,
                             rounded=rounded,result=result,saturated=saturated))
        outputs[ia],outputs[ib] = result
    return dict(name=name,position=position,x=list(values),coefficients=[list(row) for row in coefficients],
                expected=expected,outputs=outputs)


def rope_synthetic_fixtures():
    patterns = [('Zero',0,0,16384,0),('Identity',123,-456,16384,0),
                ('Quarter turn',123,-456,0,16384),('Half turn',123,-456,-16384,0),
                ('Positive clipping',32767,32767,16384,16384),
                ('Negative clipping',-32768,-32768,16384,16384)]
    patterns += [(f'Tie {a}/2',a,0,8192,0) for a in (-5,-3,-1,1,3,5)]
    patterns += [(f'Near half {c}',1,0,c,0) for c in (-8193,-8191,8191,8193)]
    patterns += [(f'Extrema {a} {b}',a,b,-32768,32767) for a,b in
                 ((32767,32767),(-32768,-32768),(-32768,32767),(32767,-32768))]
    cases = []
    for i,(name,a,b,c,s) in enumerate(patterns):
        values = [v for _ in range(4) for v in ([a]*8+[b]*8)]
        cases.append(rope_case(name,values,[[c,s]]*8,(i*17)%256))
    values = list(range(-32,32))
    cases.append(rope_case('Distinct coordinates identity',values,[[16384,0]]*8,83))
    cases.append(rope_case('Distinct coordinates quarter turn',values,[[0,16384]]*8,127))
    rng = random.Random(2026110301)
    for i in range(128):
        limit = 2048 if i<96 else 32768
        cases.append(rope_case(f'Random RoPE {i:03d}',[rng.randrange(-limit,limit) for _ in range(64)],
                               [[rng.randrange(-32768,32768) for _ in range(2)] for _ in range(8)],rng.randrange(256)))
    return cases


def rope_fixtures(meta,targets):
    import fixed
    import model
    net,manifest = fixed.selected(meta);layout = rope_layout(manifest);np = fixed.np
    cases = []
    def append(name,states,index,position,source):
        values = [int(v) for key in ('q','k') for v in states[key][0,index]]
        case = rope_case(name,values,net.rope[position].tolist(),position)
        reference = [int(v) for key in ('qrot','krot') for v in states[key][0,index]]
        if case['outputs']!=reference or any(e['saturated'] for e in case['expected']):
            raise ValueError('RoPE independent oracle differs from the full integer model or clips')
        case['model_reference'] = dict(source=source,position=position,outputs=reference)
        cases.append(case)
    longest = max(targets,key=lambda r:len(model.sequence(r)))
    probes = [(targets[0],1),(targets[0],2),(targets[2],3),(targets[7],7),
              (targets[2],18),(targets[47],63),(longest,128)]
    for target,length in probes:
        tokens = model.sequence(target)[:length]
        if len(tokens)!=length:raise ValueError('Truncated RoPE prefix')
        _,states,_ = fixed.integer_call(net,np.asarray([tokens],dtype=np.int64))
        append(f"{target['id']} · token position {length-1}",states,-1,length-1,'authored joke prefix')
    # Long context is an explicitly synthetic repeated sequence, not new language evidence.
    tokens = (model.sequence(targets[0])*256)[:256]
    _,states,_ = fixed.integer_call(net,np.asarray([tokens],dtype=np.int64))
    for position in range(256):
        append(f'Synthetic context · token position {position}',states,position,position,'synthetic repeated training sequence')
    cases += rope_synthetic_fixtures()
    return cases,net.rope.tolist(),layout


def check_rope_trace(path,cases):
    seen = set();products = 0;views = {}
    display = {*range(7),262}
    def check(label,rows):
        nonlocal products
        if label in seen or not 0<=label<len(cases)+10:raise ValueError('Duplicate/invalid RoPE transaction')
        seen.add(label);case = cases[label] if label<len(cases) else cases[0]
        if label in display and label<len(cases):
            first_busy = next(i for i,row in enumerate(rows) if row['busy'])
            views[label] = rows[first_busy:]
        if {r['step_pair'] for r in rows if r['step_valid']}!=set(range(32)):
            raise ValueError('Missing or wrong RoPE step pair')
        if {r['pair'] for r in rows if r['result_valid']}!=set(range(32)):
            raise ValueError('Missing or wrong RoPE result pair')
        if any(r['position']!=case['position'] for r in rows if r['busy']):
            raise ValueError('RoPE position was not latched')
        for pair,expected in enumerate(case['expected']):
            steps = [r for r in rows if r['step_valid'] and r['step_pair']==pair]
            if len(steps)!=4:raise ValueError('Expected four RoPE products per pair')
            ia,ib = expected['index_a'],expected['index_b']
            a,b = case['x'][ia],case['x'][ib];c,s = case['coefficients'][pair%8]
            for j,row in enumerate(steps):
                if (row['step_kind']!=j or row['step_input']!=[a,b,b,a][j]
                        or row['step_coefficient']!=[c,s,c,s][j]
                        or row['step_product']!=expected['products'][j] or row['step_total']!=expected['totals'][j]
                        or row['a']!=a or row['b']!=b or row['cosine']!=c or row['sine']!=s
                        or row['combined_a' if j<2 else 'combined_b']!=expected['totals'][j]):
                    raise ValueError('Observed RoPE product/combined value mismatch')
                products += 1
            start = next(r for r in rows if r['pair']==pair and r['phase']==1 and not r['step_valid'])
            results = [r for r in rows if r['result_valid'] and r['pair']==pair]
            if results[0]['cycle']-start['cycle']!=6:raise ValueError('RoPE pair latency changed')
            if any([r['result_a'],r['result_b']]!=expected['result'] or r['saturated']!=expected['saturated']
                   or r['index_a']!=ia or r['index_b']!=ib for r in results):
                raise ValueError('Observed RoPE rounding/clipping/tag mismatch')
    current = None;rows = []
    with path.open() as source:
        for values in csv.DictReader(source):
            row = {k:int(v) for k,v in values.items()};label = row['case']
            if label<0:continue
            if current is not None and current!=label:check(current,rows);rows = []
            current = label;rows.append(row)
    if current is not None:check(current,rows)
    if seen!=set(range(len(cases)+10)):raise ValueError('Missing completed RoPE request')
    count = len(seen)
    return dict(full_transactions=count,pairs_checked=count*32,outputs_checked=count*64,products_checked=products,
                reset_probes=9,pair_latency_edges=6,all_exact=True),views


def run_rope(folder,report,meta,targets):
    report['rope_rtl'] = dict(state='incomplete',commands=[])
    cases,table,layout = rope_fixtures(meta,targets)
    runtime.save(folder/'fixtures.json',cases)
    def hexfile(name,values,width):
        path = folder/(name+'.hex')
        path.write_text(''.join(f'{v&((1<<width)-1):0{width//4}x}\n' for v in values))
        return str(path)
    paths = {key:hexfile(key,values,bits) for key,values,bits in (
        ('X',[v for case in cases for v in case['x']],16),
        ('C',[row[0] for case in cases for row in case['coefficients']],16),
        ('S',[row[1] for case in cases for row in case['coefficients']],16),
        ('ANSWERS',[v for case in cases for v in case['outputs']],16),
        ('CLIPS',[e['saturated'] for case in cases for e in case['expected']],8),
        ('POSITIONS',[case['position'] for case in cases],16),
        ('TC',[row[0] for position in table for row in position],16),
        ('TS',[row[1] for position in table for row in position],16))}
    pin,root,compiler,version,command = simulation_tools(folder,report,'rope_rtl')
    command('compile',[str(root/'bin/verilator'),'--binary','--timing','--trace','--assert','-Wall',
        '--top-module','qk_rope_tb','-j','2','--Mdir',str(folder/'obj'),'-o','simulation',
        '-CFLAGS','-isysroot /Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk',
        '-LDFLAGS','-isysroot /Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk',
        str(RTL/'qk_rope.sv'),str(RTL/'qk_rope_tb.sv')])
    output = command('simulation',[str(folder/'obj/simulation'),f'+CASES={len(cases)}',
        *['+'+key+'='+value for key,value in paths.items()],'+CSV='+str(folder/'cycles.csv'),'+VCD='+str(folder/'waves.vcd')])
    wanted = f'PASS rope_transactions={len(cases)+10} reset_probes=9 pair_latency_edges=6'
    if wanted not in output:raise ValueError('Missing RoPE success receipt')
    checks,traces = check_rope_trace(folder/'cycles.csv',cases)
    view = dict(cases=[dict(fixture=i,**cases[i],cycles=traces[i]) for i in sorted(traces)],
                checks=checks,layout=layout,simulator=version)
    template = (RTL/'rope_viewer.html').read_text()
    (folder/'rope.html').write_text(template.replace('__SIMULATION_DATA__',json.dumps(view).replace('</','<\\/')))
    references = [case['model_reference'] for case in cases if 'model_reference' in case]
    report['rope_rtl'] = dict(state='complete',checks=checks,compiler=compiler,simulator=version,
        tool_tree_sha256=pin['tree_sha256'],fixture_cases=len(cases),layout=layout,
        oracle='Independent unbounded Python integers and Fraction nearest-even',
        full_integer_model_probes=references,commands=report['rope_rtl']['commands'],
        artifacts={name:dict(bytes=(folder/name).stat().st_size,sha256=runtime.sha(folder/name))
                   for name in ('fixtures.json','cycles.csv','waves.vcd','rope.html','TC.hex','TS.hex')},
        limits='Separate RoPE RTL block. Q/K and coefficients prepared in Python; no projection connection, KV cache, attention, synthesis or board execution')
    report['accepted'] = True
    print(wanted,flush=True);print('Independent RoPE oracle: '+str(checks),flush=True)
    print(f'Full integer model: {len(references)} positions / {len(references)*64} Qrot/Krot values, no clipping',flush=True)
    print('Position 1 / first Q pair: '+str(cases[1]['expected'][0]),flush=True)
    print('Teaching view: '+str(folder/'rope.html'),flush=True)


def cache_address(position,coordinate):
    if not (0<=position<256 and 0<=coordinate<32):raise ValueError('Invalid cache address')
    return position*32+coordinate


def cache_layout(manifest):
    if (manifest['activation_bits']!=16 or manifest['activation_exponents']['krot']!=-11
            or manifest['activation_exponents']['v']!=-12 or manifest['kv_bytes']!=32768):
        raise ValueError('Cache requires selected signed16 Krot/V layout')
    return dict(positions=256,coordinates=32,k_exponent=-11,v_exponent=-12,word_bits=16,logical_bytes=32768)


def cache_fixtures(meta,targets):
    import fixed
    import model
    net,manifest=fixed.selected(meta);np=fixed.np;layout=cache_layout(manifest)
    tokens=(model.sequence(targets[0])*256)[:256]
    _,states,cache=fixed.integer_call(net,np.asarray([tokens],dtype=np.int64))
    k,v=states['krot'][0],states['v'][0]
    for observed,expected in zip(cache,(k,v)):
        if not np.array_equal(observed[0].transpose(1,0,2).reshape(256,32),expected):
            raise ValueError('Full integer model cache differs from Krot/V')
    incremental=None
    for token in tokens[:3]:_,_,incremental=fixed.integer_call(net,np.asarray([[token]],dtype=np.int64),incremental)
    for observed,expected in zip(incremental,(k[:3],v[:3])):
        if not np.array_equal(observed[0].transpose(1,0,2).reshape(3,32),expected):
            raise ValueError('Incremental cache differs from full integer model')
    banks=[dict(name='Synthetic 256-position model context',source='Repeated J01 training tokens; not unseen language',k=k.tolist(),v=v.tolist()),
           *cache_synthetic_banks()]
    if any(len(bank[key])!=256 or any(len(row)!=32 or any(not -32768<=x<=32767 for x in row) for row in bank[key])
           for bank in banks for key in ('k','v')):raise ValueError('Invalid cache fixture payload')
    return banks,layout


def cache_synthetic_banks():
    """Original address/extrema and seeded-random payloads; no model values."""
    patterned_k=[[p*32+c-4096 for c in range(32)] for p in range(256)]
    patterned_v=[[32767-3*(p*32+c) for c in range(32)] for p in range(256)]
    patterned_k[0][0],patterned_v[0][0]=-32768,32767
    patterned_k[255][31],patterned_v[255][31]=32767,-32768
    rng=random.Random(2026110302)
    return [dict(name='Distinct addressing and signed extrema',source='Synthetic coordinate patterns',k=patterned_k,v=patterned_v),
           dict(name='Seeded random signed16 values',source='Synthetic seed 2026110302',
                k=[[rng.randrange(-32768,32768) for _ in range(32)] for _ in range(256)],
                v=[[rng.randrange(-32768,32768) for _ in range(32)] for _ in range(256)])]


class CacheReference:
    """Independent clock-by-clock append/visibility/read oracle; RAM survives reset."""
    def __init__(self):
        self.memory={};self.count=0;self.coordinate=0;self.pending=False;self.packet=[0,0,0,0]

    def step(self,row):
        reset=bool(row['reset']);wv=bool(row['write_valid']);rv=bool(row['read_valid'])
        wp,wc=row['write_position'],row['write_coordinate'];rp,rc=row['read_position'],row['read_coordinate']
        wr=not reset and not self.pending and not rv and self.count<256 and wp==self.count and wc==self.coordinate
        rr=not reset and not self.pending and not wv and 0<=rp<self.count and 0<=rc<32
        valid=self.pending and not reset
        wf=wv and wr;rf=rv and rr;of=valid and bool(row['output_ready']);commit=False
        result=dict(pre_write_ready=int(wr),pre_read_ready=int(rr),pre_valid=int(valid),
                    write_fire=int(wf),read_fire=int(rf),reply_fire=int(of))
        if reset:self.count=0;self.coordinate=0;self.pending=False;self.packet=[0,0,0,0]
        else:
            if wf:
                self.memory[cache_address(wp,wc)]=[row['write_k'],row['write_v']]
                self.coordinate+=1
                if self.coordinate==32:self.count+=1;self.coordinate=0;commit=True
            if rf:self.packet=[rp,rc,*self.memory[cache_address(rp,rc)]];self.pending=True
            elif of:self.pending=False
        result.update(token_count=self.count,next_coordinate=self.coordinate,commit_valid=int(commit),
                      pending=int(self.pending),output_valid=int(self.pending and not reset),
                      output_position=self.packet[0],output_coordinate=self.packet[1],output_k=self.packet[2],output_v=self.packet[3])
        return result

    def check(self,row):
        expected=self.step(row)
        if any(row[key]!=value for key,value in expected.items()):
            raise ValueError(f"Cache protocol/value mismatch at clock {row['cycle']}")
        return expected


def check_cache_trace(path,banks):
    reference=CacheReference();counts=dict(cycles_checked=0,writes_accepted=0,reads_checked=0,
        values_checked=0,tokens_committed=0,write_rejections=0,read_rejections=0,reset_edges=0,stalled_response_edges=0)
    seen=[set() for _ in banks];readback=[None]*8192;build=[];full=[];reset_view=[];closed=False;last_cycle=-1
    with path.open() as source:
        for values in csv.DictReader(source):
            row={k:int(v) for k,v in values.items()}
            if row['cycle']<=last_cycle:raise ValueError('Cache trace clock order changed')
            last_cycle=row['cycle'];counts['cycles_checked']+=1
            bank=row['bank']
            if not 0<=bank<len(banks):raise ValueError('Invalid cache fixture bank')
            reference.check(row)
            for key in ('write_fire','read_fire','reply_fire'):
                if row[key] not in (0,1):raise ValueError('Invalid cache handshake')
            counts['reset_edges']+=row['reset']
            counts['write_rejections']+=int(row['write_valid'] and not row['write_fire'] and not row['reset'])
            counts['read_rejections']+=int(row['read_valid'] and not row['read_fire'] and not row['reset'])
            counts['stalled_response_edges']+=int(row['pre_valid'] and not row['output_ready'])
            if row['write_fire']:
                p,c=row['write_position'],row['write_coordinate']
                if [row['write_k'],row['write_v']]!=[banks[bank]['k'][p][c],banks[bank]['v'][p][c]]:
                    raise ValueError('Accepted write differs from pinned cache fixture')
                counts['writes_accepted']+=1
            if row['read_fire']:
                counts['reads_checked']+=1;counts['values_checked']+=2
                if row['section']==10*bank+1:
                    p,c=row['output_position'],row['output_coordinate'];address=cache_address(p,c)
                    if address in seen[bank]:raise ValueError('Duplicate full-cache readback address')
                    seen[bank].add(address)
                    if [row['output_k'],row['output_v']]!=[banks[bank]['k'][p][c],banks[bank]['v'][p][c]]:
                        raise ValueError('Full readback differs from cache fixture')
                    if bank==0:readback[address]=[row['output_k'],row['output_v'],row['cycle']]
            counts['tokens_committed']+=row['commit_valid']
            if row['section']==0 and not closed:
                if row['write_fire'] and row['write_position']>=3:closed=True
                else:build.append(row)
            if row['section']==3:full.append(row)
            if row['section']==4 and len(reset_view)<7:reset_view.append(row)
    if any(addresses!=set(range(8192)) for addresses in seen):raise ValueError('Missing full-cache readback address')
    if (reference.count!=0 or reference.pending or counts['reset_edges']<13
            or not counts['stalled_response_edges'] or not counts['write_rejections'] or not counts['read_rejections']):
        raise ValueError('Missing cache reset/stall/rejection coverage')
    counts.update(all_exact=True,full_readback_values=len(banks)*16384,model_readback_values=16384,
                  address_pairs_per_bank=8192,full_readback_banks=len(banks))
    scenes=[dict(name='Build the first three model tokens',base='empty',cycles=build),
            dict(name='Full cache: read first and last addresses',base='full',cycles=full),
            dict(name='Reset: old RAM bits become invalid',base='full',cycles=reset_view)]
    if any(not s['cycles'] for s in scenes):raise ValueError('Missing cache teaching trace')
    return counts,dict(scenes=scenes,readback=readback)


def run_cache(folder,report,meta,targets):
    report['cache_rtl']=dict(state='incomplete',commands=[])
    banks,layout=cache_fixtures(meta,targets);runtime.save(folder/'fixtures.json',banks)
    paths={}
    for key in ('k','v'):
        path=folder/(key+'.hex')
        path.write_text(''.join(f'{value&65535:04x}\n' for bank in banks for row in bank[key] for value in row))
        paths[key]=path
    pin,root,compiler,version,command=simulation_tools(folder,report,'cache_rtl')
    command('compile',[str(root/'bin/verilator'),'--binary','--timing','--trace','--assert','-Wall',
        '--top-module','kv_cache_tb','-j','2','--Mdir',str(folder/'obj'),'-o','simulation',
        '-CFLAGS','-isysroot /Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk',
        '-LDFLAGS','-isysroot /Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk',
        str(RTL/'kv_cache.sv'),str(RTL/'kv_cache_tb.sv')])
    output=command('simulation',[str(folder/'obj/simulation'),'+K='+str(paths['k']),'+V='+str(paths['v']),
                               '+CSV='+str(folder/'cycles.csv'),'+VCD='+str(folder/'waves.vcd')])
    wanted='PASS kv_cache banks=3 positions=256 coordinates=32'
    if wanted not in output:raise ValueError('Missing cache success receipt')
    checks,view=check_cache_trace(folder/'cycles.csv',banks)
    view.update(checks=checks,layout=layout,simulator=version)
    template=(RTL/'cache_viewer.html').read_text()
    (folder/'cache.html').write_text(template.replace('__SIMULATION_DATA__',json.dumps(view).replace('</','<\\/')))
    report['cache_rtl']=dict(state='complete',checks=checks,layout=layout,compiler=compiler,simulator=version,
        tool_tree_sha256=pin['tree_sha256'],commands=report['cache_rtl']['commands'],
        model_reference='Full 256-position Krot/V equals returned cache; incremental first three tokens equal full prefix',
        oracle='Independent Python clock-by-clock append/commit/visibility/read replay',
        artifacts={name:dict(bytes=(folder/name).stat().st_size,sha256=runtime.sha(folder/name))
                   for name in ('fixtures.json','cycles.csv','waves.vcd','cache.html')},
        limits='Separate KV-cache block; Python supplies Krot/V. No connected projection/RoPE/attention, synthesis or board execution')
    report['accepted']=True
    print(wanted,flush=True);print('Independent cache replay: '+str(checks),flush=True)
    print('Teaching view: '+str(folder/'cache.html'),flush=True)


def vivado_command(folder,name,argv,commands,allow_warnings=False,timeout_seconds=180):
    """Bound each tool and its descendants; retain commands, diagnostics and cleanup."""
    log = folder/(name+'.log');started = time.monotonic()
    env = runtime.clean_environment(runtime.RUNTIME,os.environ)
    env.update(TMPDIR=str(folder/'tmp'),XILINX_LOCAL_USER_DATA='no',
               XILINX_LOCAL_USER_DATA_ANALYTICS='no')
    (folder/'tmp').mkdir(exist_ok=True)
    receipt = dict(name=name,argv=[str(v) for v in argv],timeout_seconds=timeout_seconds,log=str(log))
    commands.append(receipt)
    with log.open('w') as stream:
        child = subprocess.Popen(receipt['argv'],cwd=folder,env=env,stdout=stream,
                                 stderr=subprocess.STDOUT,start_new_session=True)
        receipt.update(pid=child.pid,process_group=child.pid)
        try:
            receipt['exit_code'] = child.wait(timeout=timeout_seconds)
        except (subprocess.TimeoutExpired,KeyboardInterrupt):
            receipt['timed_out_or_interrupted'] = True
            raise
        finally:
            try:os.killpg(child.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            child.wait()
            receipt.update(exit_code=child.returncode,seconds=time.monotonic()-started,child_reaped=True)
            # A killed vendor wrapper may briefly leave descendants awaiting init's
            # reap. Check after a bounded grace period, retaining failure honestly.
            for attempt in range(21):
                try:os.killpg(child.pid,0);receipt['process_group_absent']=False
                except ProcessLookupError:receipt['process_group_absent']=True;break
                if attempt<20:time.sleep(.05)
            receipt['diagnostics']=[line for line in log.read_text().splitlines()
                if any(mark in line.upper() for mark in ('WARNING:','ERROR:','FATAL:'))]
    output = log.read_text()
    # XSim can return zero after an HDL failure; require clean logs AND a PASS receipt.
    diagnostics = [line for line in output.splitlines()
                   if any(mark in line.upper() for mark in ('WARNING:','ERROR:','FATAL:'))]
    receipt['diagnostics'] = diagnostics
    # The installed Ubuntu rdiArgs.sh injects LIBRARY_PATH even into our clean
    # environment. Retain this vendor warning; never suppress HDL diagnostics.
    vendor = [line for line in diagnostics if name=='elaborate' and
              line.startswith('WARNING: [XSIM 43-3431]') and
              output.split(line,1)[1].split('Starting static elaboration',1)[0].strip()=='LIBRARY_PATH']
    receipt['vendor_environment_warnings'] = vendor
    fatal=[line for line in diagnostics if line not in vendor and
           (not allow_warnings or any(mark in line.upper() for mark in ('ERROR:','FATAL:','CRITICAL WARNING:')))]
    if receipt['exit_code'] or fatal or not receipt['process_group_absent']:
        raise RuntimeError(name+' failed; see '+str(log)+'\n'+output[-3000:])
    return output


def vivado_frozen(folder,digest,block,rows):
    """Verify a Mac-supplied manifest before parsing or using any fixture payload."""
    path = folder/'transfer.json'
    if not digest or runtime.sha(path)!=digest:raise ValueError('Frozen transfer manifest hash differs')
    transfer = runtime.read(path)
    import fixed
    if (transfer['schema']!=1 or transfer['block']!=block or transfer['rows']!=rows
            or transfer['fixed_manifest_sha256']!=fixed.SELECTED_SHA256
            or transfer['fixed_payload_sha256']!=runtime.read(runtime.MODEL/'fixed.json')['images']['sha256']):
        raise ValueError('Frozen fixture provenance/geometry differs')
    names = {'fixtures.json','results.json'} | ({'TC.hex','TS.hex'} if block=='qk_rope' else set())
    if set(transfer['files'])!=names:raise ValueError('Unexpected frozen transfer files')
    for name,pin in transfer['files'].items():
        source = folder/name
        if source.stat().st_size!=pin['bytes'] or runtime.sha(source)!=pin['sha256']:
            raise ValueError('Frozen input hash differs: '+name)
    original = runtime.read(folder/'results.json')
    section = {'mac32':'rtl','qk_rope':'rope_rtl','kv_cache':'cache_rtl'}[block]
    if not original.get('accepted') or original[section]['state']!='complete':
        raise ValueError('Original Mac reference run did not pass')
    for name in names-{'results.json'}:
        if original[section]['artifacts'][name]['sha256']!=transfer['files'][name]['sha256']:
            raise ValueError('Transfer differs from original Mac artifact pin: '+name)
    for name in ('model/fixed.json','tools/fixed.py','rtl/'+block+'.sv','rtl/'+block+'_tb.sv'):
        if original['source_sha256'][name]!=runtime.sha(runtime.PROJECT/name):
            raise ValueError('Mac source differs: '+name)
    return runtime.read(folder/'fixtures.json'),transfer


def vivado_inputs(folder,block,cases,table=None):
    def hexfile(name,values,width=16):
        path = folder/(name+'.hex')
        path.write_text(''.join(f'{v&((1<<width)-1):0{width//4}x}\n' for v in values))
        return str(path)
    if block=='mac32':
        # Recompute expectations with the independent oracle, including frozen inputs.
        for case in cases:
            if case['expected']!=matrix_case(case['name'],case['x'],case['weights'])['expected']:
                raise ValueError('Projection fixture oracle differs')
        args = dict(CASES=str(len(cases)),X=hexfile('inputs',(v for c in cases for v in c['x'])),
            W=hexfile('weights',(v for c in cases for row in c['weights'] for v in row)),
            ANSWERS=hexfile('answers',(e['result'] for c in cases for e in c['expected'])),
            CLIPS=hexfile('clips',(e['saturated'] for c in cases for e in c['expected']),8))
    elif block=='qk_rope':
        for case in cases:
            expected = rope_case(case['name'],case['x'],case['coefficients'],case['position'])
            if any(case[key]!=expected[key] for key in ('expected','outputs')):
                raise ValueError('RoPE fixture oracle differs')
        args = dict(CASES=str(len(cases)),X=hexfile('inputs',(v for c in cases for v in c['x'])),
            C=hexfile('cosines',(r[0] for c in cases for r in c['coefficients'])),
            S=hexfile('sines',(r[1] for c in cases for r in c['coefficients'])),
            ANSWERS=hexfile('answers',(v for c in cases for v in c['outputs'])),
            CLIPS=hexfile('clips',(e['saturated'] for c in cases for e in c['expected']),8),
            POSITIONS=hexfile('positions',(c['position'] for c in cases)))
        for key in ('TC','TS'):
            path = folder/(key+'.hex')
            path.write_text((table/key).with_suffix('.hex').read_text() if table else '4000\n'*2048 if key=='TC' else '0000\n'*2048)
            args[key]=str(path)
    else:
        if len(cases)!=3 or any(len(c[key])!=256 or any(len(r)!=32 or any(not -32768<=v<=32767 for v in r)
                for r in c[key]) for c in cases for key in ('k','v')):raise ValueError('Invalid cache banks')
        args = {key.upper():hexfile(key,(v for c in cases for row in c[key] for v in row)) for key in ('k','v')}
    args.update(CSV=str(folder/'cycles.csv'),VCD=str(folder/'waves.vcd'))
    runtime.save(folder/'fixtures.json',cases)
    return args


FROZEN_TRANSFERS = {
    'mac32':'1c55cec3639e4d80a7f2e83174c96b9ccd0ab8419cccd7fe2d34346221de8894',
    'qk_rope':'92d80e22fdf0fbe970e7730db7cea002add4ab0f728909b9078ba0f671ac84a1',
    'kv_cache':'a062b62602d56338df18640c3d11e9aaaabb735eb6060f13d8a1e788756ab1fc'}


def fixed_tensor_values(manifest_path=None,manifest_sha256=None,tensor_path=None):
    """Decode pinned integer SafeTensors bytes, with no ML libraries/model call.

    Explicit imports require all three arguments and exactly the original
    circuit's arithmetic and tensor geometry. Their weights may differ; this
    transport check never selects a candidate or transfers numerical acceptance.
    """
    import struct
    import fixed
    explicit=any(value is not None for value in (manifest_path,manifest_sha256,tensor_path))
    if explicit and not all((manifest_path,manifest_sha256,tensor_path)):
        raise ValueError('Explicit fixed inputs require manifest, trusted SHA256 and tensor path')
    selected_path=runtime.MODEL/'fixed.json'
    if runtime.sha(selected_path)!=fixed.SELECTED_SHA256:raise ValueError('Fixed arithmetic manifest changed')
    selected=runtime.read(selected_path)
    if explicit:
        manifest_path=Path(manifest_path)
        if runtime.sha(manifest_path)!=manifest_sha256:raise ValueError('Imported fixed arithmetic manifest changed')
        manifest=runtime.read(manifest_path)
        annotations={'images','runtime_path','source_q8_sha256','study','teaching_projection'}
        for name in set(selected)-annotations:
            if json.dumps(manifest.get(name),sort_keys=True)!=json.dumps(selected[name],sort_keys=True):
                raise ValueError('Imported arithmetic differs from original circuit: '+name)
        for name in ('file','bytes','arrays'):
            if manifest.get('images',{}).get(name)!=selected['images'][name]:
                raise ValueError('Imported tensor geometry differs from original circuit: '+name)
        path=Path(tensor_path)
    else:
        manifest=selected
        path=runtime.RUNTIME/manifest['runtime_path']/manifest['images']['file']
    if manifest['implementation_sha256']!=fixed.implementation_sha256():
        raise ValueError('Selected integer arithmetic source changed')
    raw=path.read_bytes()
    if len(raw)!=manifest['images']['bytes'] or hashlib.sha256(raw).hexdigest()!=manifest['images']['sha256']:
        raise ValueError('Fixed integer payload changed')
    size=struct.unpack('<Q',raw[:8])[0]
    if not 0<size<=len(raw)-8:raise ValueError('Invalid SafeTensors header size')
    header=json.loads(raw[8:8+size]);payload=raw[8+size:];values={}
    expected=manifest['images']['arrays']
    if set(header)-{'__metadata__'}!=set(expected):raise ValueError('Fixed tensor inventory changed')
    types={'<i2':('I16','h',2),'<u4':('U32','I',4)}
    for name,pin in expected.items():
        entry=header[name];dtype,code,width=types[pin['dtype']];begin,end=entry['data_offsets']
        count=1
        for dimension in pin['shape']:count*=dimension
        if (entry['dtype']!=dtype or entry['shape']!=pin['shape'] or not 0<=begin<=end<=len(payload)
                or end-begin!=pin['bytes'] or count*width!=end-begin):
            raise ValueError('Fixed tensor shape/dtype/offset changed: '+name)
        values[name]=list(struct.unpack('<'+str(count)+code,payload[begin:end]))
    return values,manifest


def frontend_fixtures(kind):
    """Connected pipeline probes; never pass synthetic upstream work off as a model."""
    rng=random.Random(2026110401)
    inputs=[[rng.randrange(-4096,4096) for _ in range(32)] for _ in range(256)]
    inputs[0]=[-32768,32767,0,1,-1,3,-3,5,-5]+list(range(23))
    references={}
    if kind=='frozen':
        base=runtime.RUNTIME/'mac-frozen'
        matrices,mp=vivado_frozen(base/'mac32',FROZEN_TRANSFERS['mac32'],'mac32',96)
        ropes,rp=vivado_frozen(base/'qk_rope',FROZEN_TRANSFERS['qk_rope'],'qk_rope',None)
        weights=matrices[0]['weights']
        for i,case in enumerate(matrices[:7]):
            position=case['model_reference']['prefix_length']-1
            if case['weights']!=weights or ropes[i]['position']!=position:
                raise ValueError('Frozen connected-stage inputs differ')
            projected=[e['result'] for e in case['expected']]
            if ropes[i]['x']!=projected[:64]:raise ValueError('Frozen projection/RoPE boundary differs')
            inputs[position]=case['x'];references[position]=ropes[i]['outputs']
        table=[]
        for key in ('TC','TS'):
            words=[int(v,16) for v in (base/'qk_rope'/(key+'.hex')).read_text().split()]
            if len(words)!=2048 or any(not 0<=v<=65535 for v in words):raise ValueError('Invalid frozen RoPE table')
            table.append([v-65536 if v>=32768 else v for v in words])
        provenance=dict(projection=mp,rope=rp,real_boundary_positions=sorted(references),
                        upstream='Seven frozen norm1 vectors; all other input vectors are explicitly synthetic')
    else:
        weights=[[(32767,-32768,16384)[r//32] if c==r%32 else rng.randrange(-64,64)
                  for c in range(32)] for r in range(96)]
        rotations=((16384,0),(0,16384),(-16384,0),(0,-16384),(11585,11585))
        table=[[rotations[(p+j)%len(rotations)][coordinate] for p in range(256) for j in range(8)]
               for coordinate in range(2)]
        provenance=dict(upstream='All operands and coefficients are synthetic; no model comparison')
    cases=[]
    for position,x in enumerate(inputs):
        dots=[oracle(x,w) for w in weights];qkv=[e['result'] for e in dots]
        coefficients=[[table[0][position*8+j],table[1][position*8+j]] for j in range(8)]
        rotation=rope_case('Connected position '+str(position),qkv[:64],coefficients,position)
        if position in references and rotation['outputs']!=references[position]:
            raise ValueError('Connected arithmetic differs from archived full-model Qrot/Krot')
        cases.append(dict(x=x,qkv=qkv,rotation=rotation,q=rotation['outputs'][:32],
                          k=rotation['outputs'][32:],v=qkv[64:],
                          saturated=int(any(e['saturated'] for e in dots+rotation['expected']))))
    return dict(kind=kind,weights=weights,table=table,cases=cases,provenance=provenance)


def check_frontend_trace(path,fixture):
    """Replay observed arithmetic/order and actual interstage query/cache transfers."""
    cases=fixture['cases'];weights=fixture['weights'];memory={}
    count=0;coordinate=0;mac_count=0;rope_count=0;query_count=0;writes=0;label=None
    checks=dict(projection_products=0,rope_products=0,query_values=0,cache_writes=0,cache_read_values=0,
                reset_edges=0,complete_tokens=0)
    expected_dot=None
    with path.open() as source:
        for values in csv.reader(source):
            kind=values[0];values=[int(v) for v in values[1:]]
            case_id,cycle,a,b,c,d,e,f=values
            case=cases[max(0,case_id)]
            if kind=='Z':
                if any((a,b,c,d,e)):raise ValueError('Connected reset visibility mismatch')
                count=coordinate=mac_count=rope_count=query_count=writes=0;label=None
                checks['reset_edges']+=1
            elif kind=='M':
                if label is None:label=case_id
                if label!=case_id or (a,b)!=divmod(mac_count,32):raise ValueError('Connected projection order mismatch')
                if b==0:expected_dot=oracle(case['x'],weights[a])
                if (c,d,e,f)!=(case['x'][b],weights[a][b],expected_dot['products'][b],expected_dot['partial_sums'][b]):
                    raise ValueError('Connected observed MAC product/sum mismatch')
                mac_count+=1;checks['projection_products']+=1
            elif kind=='R':
                if mac_count!=3072 or (a,b)!=divmod(rope_count,4):raise ValueError('Connected RoPE order mismatch')
                expected=case['rotation']['expected'][a];ia=expected['index_a'];ib=expected['index_b']
                x=case['qkv'];co,si=case['rotation']['coefficients'][a%8]
                if (c,d,e,f)!=([x[ia],x[ib],x[ib],x[ia]][b],[co,si,co,si][b],expected['products'][b],expected['totals'][b]):
                    raise ValueError('Connected observed RoPE product/sum mismatch')
                rope_count+=1;checks['rope_products']+=1
            elif kind=='W':
                if rope_count!=128 or a!=count or b!=coordinate or (c,d)!=(case['k'][b],case['v'][b]):
                    raise ValueError('Connected Krot/V append mismatch')
                memory[a*32+b]=[c,d];coordinate+=1;writes+=1
                if coordinate==32:count+=1;coordinate=0
                if e!=count:raise ValueError('Connected cache commit visibility mismatch')
                checks['cache_writes']+=1
            elif kind=='Q':
                if (mac_count,rope_count,writes)!=(3072,128,32) or coordinate or a!=query_count:
                    raise ValueError('Connected query appeared before complete projection/rotation/commit')
                if (b,c)!=(case['q'][a],case['saturated']):raise ValueError('Connected Qrot/clipping mismatch')
                checks['query_values']+=1;query_count+=1
                if query_count==32:
                    checks['complete_tokens']+=1
                    mac_count=rope_count=query_count=writes=0;label=None
            elif kind=='K':
                if not 0<=a<count or not 0<=b<32 or [c,d]!=memory[a*32+b] or e!=count:
                    raise ValueError('Connected cache readback/visibility mismatch')
                checks['cache_read_values']+=2
            else:raise ValueError('Unknown connected trace record')
    if checks['complete_tokens']!=263 or checks['query_values']!=8416 or checks['cache_read_values']!=17422 or checks['reset_edges']!=16:
        raise ValueError('Missing connected stage/reset/full-context coverage: '+str(checks))
    checks.update(all_exact=True,positions=256,reset_stages=7)
    return checks


def run_frontend_vivado(folder,command,kind):
    work=folder/'frontend';work.mkdir();fixture=frontend_fixtures(kind)
    runtime.save(work/'fixtures.json',fixture)
    def hexfile(name,values,width=16):
        path=work/(name+'.hex');path.write_text(''.join(f'{v&((1<<width)-1):0{width//4}x}\n' for v in values));return str(path)
    args={key:hexfile(key,(v for case in fixture['cases'] for v in case[name])) for key,name in
          (('X','x'),('Q','q'),('K','k'),('V','v'))}
    args.update(W=hexfile('W',(v for row in fixture['weights'] for v in row)),
                C=hexfile('C',fixture['table'][0]),S=hexfile('S',fixture['table'][1]),
                CLIPS=hexfile('CLIPS',(c['saturated'] for c in fixture['cases']),8),
                CSV=str(work/'events.csv'),VCD=str(work/'waves.vcd'))
    sources=[RTL/(name+'.sv') for name in ('mac32','qk_rope','kv_cache','frontend','frontend_tb')]
    command(work,'compile',[Path('/home/admin/amd/2025.2/Vivado/bin/xvlog'),'--sv',*sources])
    command(work,'elaborate',[Path('/home/admin/amd/2025.2/Vivado/bin/xelab'),'work.frontend_tb',
                            '--debug','typical','--mt','2','--snapshot','frontend_sim'])
    output=command(work,'simulation',[Path('/home/admin/amd/2025.2/Vivado/bin/xsim'),'frontend_sim','--runall',
        '--onerror','quit','--onfinish','quit',*[v for k,value in args.items() for v in ('--testplusarg',k+'='+value)]])
    if 'PASS frontend tokens=263 positions=256 reset_stages=7' not in output:raise ValueError('Missing connected frontend success receipt')
    checks=check_frontend_trace(work/'events.csv',fixture)
    print('Connected frontend: '+str(checks),flush=True)
    return dict(state='complete',checks=checks,provenance=fixture['provenance'],
        source_sha256={str(p.relative_to(runtime.PROJECT)):runtime.sha(p) for p in sources},
        artifacts={p.name:dict(bytes=p.stat().st_size,sha256=runtime.sha(p)) for p in work.iterdir() if p.suffix in ('.csv','.vcd','.json','.hex')},
        limits='Connected QKV/RoPE/cache only. Normalized inputs prepared externally; no attention, normalization, full-model logits or board result')


def scalar_shift_reference(value,amount):
    """Independent unbounded/Fraction oracle for the checked scalar shifter."""
    if amount>=0:
        if amount>62 or abs(value)>((2**63-1)>>amount):raise OverflowError('Scalar left shift overflow')
        return value<<amount
    return round(Fraction(value,1<<-amount))


def scalar_multiply_reference(a,b):
    if abs(a)*abs(b)>2**63-1:raise OverflowError('Scalar product overflow')
    return a*b


def scalar_reference(op,a,b,amount,exp_table,rsqrt_table):
    """Independent scalar formulas; never imports a numerical/model runtime."""
    if op==0:return scalar_shift_reference(a,amount),0
    if op==1:
        if not 0<b<=2**62:raise ValueError('Scalar denominator out of range')
        return round(Fraction(a,b)),0
    if op==2:return scalar_multiply_reference(a,b),0
    if op==3:
        if not -2**62<=a<=0:raise ValueError('Scalar exponential input out of range')
        if -a>16*65536:return 0,0
        power,remainder=divmod(-a,45426);index,fraction=divmod(remainder*256,45426)
        mantissa=exp_table[index]+round(Fraction((exp_table[index+1]-exp_table[index])*fraction,45426))
        return round(Fraction(mantissa,1<<power)),0
    if op==4:
        if a<=0:raise ValueError('Scalar reciprocal square root input must be positive')
        k=(a.bit_length()-1-32)//2;m=scalar_shift_reference(a,-2-2*k)
        if m==2**32:m>>=2;k+=1
        index=min(((m-2**30)*256)//(3*2**30),255);y=rsqrt_table[index]
        for _ in range(2):
            y2=scalar_shift_reference(scalar_multiply_reference(y,y),-30)
            my2=scalar_shift_reference(scalar_multiply_reference(m,y2),-30)
            y=scalar_shift_reference(scalar_multiply_reference(y,3*2**30-my2),-31)
        return y,k
    raise ValueError('Unknown scalar opcode')


def scalar_vivado_cases(exp_table,rsqrt_table):
    cases=[]
    def add(op,a,b=0,shift=0):
        try:result,exponent=scalar_reference(op,a,b,shift,exp_table,rsqrt_table);error=0
        except (OverflowError,ValueError):result=exponent=0;error=1
        cases.append(dict(op=op,a=a,b=b,shift=shift,result=result,exponent=exponent,error=error))
    maximum=2**63-1
    values=[-2**63,-maximum,-2**62,-32768,-5,-3,-1,0,1,3,5,32767,2**31,2**62,maximum]
    for a in values:
        for shift in (-128,-65,-64,-63,-62,-31,-1,0,1,31,62,63,127):add(0,a,shift=shift)
        for b in (-1,0,1,2,3,2**31,2**62,2**62+1,maximum):add(1,a,b)
        for b in (-2**63,-maximum,-32768,-1,0,1,32767,2**31,maximum):add(2,a,b)
    for a in (1,-2**62-1,-2**62,-1048577,-1048576,-1048575,0,-1,-2,-3,-45425,-45426,-45427):add(3,a)
    for power in range(24):
        for delta in (-1,0,1):add(3,-min(1048577,max(0,power*45426+delta)))
    for index in range(257):
        for delta in (-1,0,1):add(3,-max(0,(index*45426)//256+delta))
    for a in (-1,0,1,42950,2**30,2**31,2**32,2**62,maximum):add(4,a)
    for bit in range(63):
        for delta in (-1,0,1):
            if 0<=2**bit+delta<=maximum:add(4,2**bit+delta)
    rng=random.Random(20261104)
    for _ in range(128):
        a=rng.randrange(-2**63,2**63)
        add(0,a,shift=rng.randrange(-128,128));add(1,a,rng.randrange(1,2**62+1))
        add(2,rng.randrange(-2**33,2**33),rng.randrange(-2**33,2**33))
        add(3,-rng.randrange(0,1048578));add(4,rng.randrange(1,maximum+1))
    return cases


def scalar_vivado_hexfile(folder,name,values,bits):
    path=folder/(name+'.hex')
    path.write_text(''.join(f'{v&((1<<bits)-1):0{bits//4}x}\n' for v in values))
    return str(path)


def run_scalar_vivado(folder,command):
    work=folder/'scalar';work.mkdir();values,manifest=fixed_tensor_values()
    exp_table,rsqrt_table=values['exp_table'],values['rsqrt_table']
    cases=scalar_vivado_cases(exp_table,rsqrt_table)
    runtime.save(work/'fixtures.json',dict(source='Synthetic operands with selected model tables; not full-model inference',cases=cases,exp_table=exp_table,rsqrt_table=rsqrt_table))
    args={key.upper():scalar_vivado_hexfile(work,key,(c[key] for c in cases),bits) for key,bits in
          (('op',8),('a',64),('b',64),('shift',8),('result',64),('exponent',8),('error',8))}
    args['ANSWER']=args.pop('RESULT')
    args.update(EXP=scalar_vivado_hexfile(work,'exp',exp_table,32),RSQRT=scalar_vivado_hexfile(work,'rsqrt',rsqrt_table,32),
                N=str(len(cases)),CSV=str(work/'cycles.csv'),VCD=str(work/'waves.vcd'))
    base=Path('/home/admin/amd/2025.2/Vivado/bin');sources=[RTL/(name+'.sv') for name in ('fixed_scalar','fixed_scalar_tb')]
    command(work,'compile',[base/'xvlog','--sv',*sources])
    command(work,'elaborate',[base/'xelab','work.fixed_scalar_tb','--debug','typical','--mt','2','--snapshot','scalar_sim'])
    output=command(work,'simulation',[base/'xsim','scalar_sim','--runall','--onerror','quit','--onfinish','quit',
        *[v for key,value in args.items() for v in ('--testplusarg',key+'='+value)]])
    wanted=f'PASS fixed_scalar requests={len(cases)+1} reset_probes=2'
    if wanted not in output:raise ValueError('Missing scalar success receipt')
    with (work/'cycles.csv').open() as source:rows=list(csv.DictReader(source))
    if len(rows)!=len(cases)+1:raise ValueError('Missing scalar response')
    for i,(row,case) in enumerate(zip(rows,[*cases,cases[-1]])):
        if int(row['case'])!=(i if i<len(cases) else len(cases)-1):raise ValueError('Scalar request order changed')
        if any(int(row[key])!=case[key] for key in ('op','a','b','shift','result','exponent','error')):
            raise ValueError('Scalar independent oracle mismatch')
        if not 1<=int(row['edges'])<=650 or not 1<=int(row['stalls'])<=5:raise ValueError('Scalar latency/stall coverage differs')
    checks=dict(all_exact=True,fixture_cases=len(cases),responses_checked=len(rows),reset_probes=2,
                opcodes_checked=5,error_responses=sum(c['error'] for c in cases))
    print('Scalar arithmetic: '+str(checks),flush=True)
    return dict(state='complete',checks=checks,source_sha256={str(p.relative_to(runtime.PROJECT)):runtime.sha(p) for p in sources},
        fixed_manifest_sha256=runtime.sha(runtime.MODEL/'fixed.json'),fixed_payload_sha256=manifest['images']['sha256'],
        table_sha256={name:hashlib.sha256(b''.join(v.to_bytes(4,'little') for v in values[name])).hexdigest() for name in ('exp_table','rsqrt_table')},
        artifacts={p.name:dict(bytes=p.stat().st_size,sha256=runtime.sha(p)) for p in work.iterdir() if p.suffix in ('.csv','.vcd','.json','.hex')},
        limits='Selected tables; synthetic scalar operands only. No full-model forward, connected inference or board result')


def rmsnorm_reference(x,gains,source_exponent,gain_exponent,output_exponent,rsqrt_table):
    if len(x)!=32 or len(gains)!=32 or any(not -32768<=v<=32767 for v in [*x,*gains]):
        raise ValueError('RMSNorm requires32 signed16 inputs and gains')
    squares=sum(v*v for v in x)
    if squares>=2**47:raise OverflowError('RMS square sum exceeds48bits')
    r=scalar_shift_reference(squares,2*source_exponent+27)+42950
    if not 0<r<=2**63-1:raise OverflowError('RMS epsilon addition exceeds scratch')
    y,k=scalar_reference(4,r,0,0,[],rsqrt_table)
    xy=[scalar_multiply_reference(v,y) for v in x]
    products=[scalar_multiply_reference(v,gain) for v,gain in zip(xy,gains)]
    rounded=[scalar_shift_reference(v,source_exponent+gain_exponent-30-k-output_exponent) for v in products]
    return dict(squares=squares,r=r,y=y,k=k,xy=xy,product=products,
                result=[max(-32768,min(32767,v)) for v in rounded],saturated=[int(not -32768<=v<=32767) for v in rounded])


def rmsnorm_vivado_cases(name,source_exponent,gain_exponent,output_exponent,gain_name,values):
    cases=[]
    def add(label,x,gains=None,golden=None):
        gains=values[gain_name] if gains is None else gains
        expected=rmsnorm_reference(x,gains,source_exponent,gain_exponent,output_exponent,values['rsqrt_table'])
        if golden is not None and expected['result']!=golden:raise ValueError('RMSNorm oracle differs from archived real-model input')
        cases.append(dict(name=label,x=x,gain=gains,expected=expected,golden=golden is not None))
    provenance={}
    if name=='norm1':
        matrices,transfer=vivado_frozen(runtime.RUNTIME/'mac-frozen/mac32',FROZEN_TRANSFERS['mac32'],'mac32',96)
        selection=runtime.read(runtime.MODEL/'selection.json');jokes_path=runtime.MODEL/'jokes.json'
        if runtime.sha(jokes_path)!=selection['files_sha256']['jokes.json']:raise ValueError('Frozen joke snapshot changed')
        jokes={r['id']:r['text'] for r in runtime.read(jokes_path)}
        for case in matrices[:7]:
            ref=case['model_reference'];tokens=[256,*jokes[ref['joke_id']].encode('utf-8'),257]
            token=tokens[ref['prefix_length']-1]
            add('Real '+ref['joke_id']+' prefix '+str(ref['prefix_length']),values['E'][token*32:(token+1)*32],golden=case['x'])
        provenance['archived_mac_projection']=transfer
    patterns=[[0]*32,[1]*32,[-1]*32,[32767]*32,[-32768]*32,[-32768,32767]*16,list(range(-16,16)),list(range(1,33))]
    for coordinate in (0,15,16,31):
        x=[0]*32;x[coordinate]=-32768;patterns.append(x)
    for i,x in enumerate(patterns):add('Directed '+str(i),x)
    for value in (-32768,-1,0,32767):add('Synthetic gain '+str(value),list(range(-16,16)),[value]*32)
    rng=random.Random(2026110402)
    for i in range(24):add('Random '+str(i),[rng.randrange(-32768,32768) for _ in range(32)],None if i<12 else [rng.randrange(-32768,32768) for _ in range(32)])
    return cases,provenance


def run_norm_vivado(folder,command):
    values,manifest=fixed_tensor_values();reports={}
    configurations=(('norm1',-14,-14,-11,'gain1'),('norm2',-12,-14,-11,'gain2'),
                    ('normfinal',-10,-13,-10,'gain3'),('clipping-stress',-14,-14,-15,'gain1'))
    for name,se,ge,oe,gain_name in configurations:
        work=folder/name;work.mkdir();cases,provenance=rmsnorm_vivado_cases(name,se,ge,oe,gain_name,values)
        runtime.save(work/'fixtures.json',dict(source='Selected tables/gains; synthetic vectors except seven archived norm1 inputs',exponents=[se,ge,oe],cases=cases))
        args=dict(N=str(len(cases)),X=scalar_vivado_hexfile(work,'inputs',(v for c in cases for v in c['x']),16),
            GAIN=scalar_vivado_hexfile(work,'gains',(v for c in cases for v in c['gain']),16),
            ANSWER=scalar_vivado_hexfile(work,'answers',(v for c in cases for v in c['expected']['result']),16),
            CLIP=scalar_vivado_hexfile(work,'clips',(v for c in cases for v in c['expected']['saturated']),8),
            RSQRT=scalar_vivado_hexfile(work,'rsqrt',values['rsqrt_table'],32),CSV=str(work/'cycles.csv'),VCD=str(work/'waves.vcd'))
        base=Path('/home/admin/amd/2025.2/Vivado/bin');sources=[RTL/(n+'.sv') for n in ('fixed_scalar','rmsnorm','rmsnorm_tb')]
        command(work,'compile',[base/'xvlog','--sv',*sources])
        command(work,'elaborate',[base/'xelab','work.rmsnorm_tb','--debug','typical','--mt','2','--snapshot','norm_sim',
            '--generic_top','SOURCE_EXP='+str(se),'--generic_top','GAIN_EXP='+str(ge),'--generic_top','OUTPUT_EXP='+str(oe)])
        output=command(work,'simulation',[base/'xsim','norm_sim','--runall','--onerror','quit','--onfinish','quit',
            *[v for key,value in args.items() for v in ('--testplusarg',key+'='+value)]])
        wanted=f'PASS rmsnorm requests={len(cases)+3} coordinates=32 reset_probes=3'
        if wanted not in output:raise ValueError('Missing RMSNorm success receipt')
        with (work/'cycles.csv').open() as source:rows=list(csv.DictReader(source))
        if len(rows)!=(len(cases)+3)*32:raise ValueError('Missing RMSNorm output coordinates')
        for i,row in enumerate(rows):
            label,coordinate=divmod(i,32);case=cases[label] if label<len(cases) else cases[0];expected=case['expected']
            if int(row['case'])!=label or int(row['coordinate'])!=coordinate:raise ValueError('RMSNorm output order changed')
            wanted_values=dict(input=case['x'][coordinate],gain=case['gain'][coordinate],result=expected['result'][coordinate],
                saturated=expected['saturated'][coordinate],error=0,squares=expected['squares'],r=expected['r'],y=expected['y'],k=expected['k'],
                xy=expected['xy'][coordinate],product=expected['product'][coordinate])
            if any(int(row[key])!=value for key,value in wanted_values.items()):raise ValueError('RMSNorm independent observed intermediate/result mismatch')
        checks=dict(all_exact=True,requests=len(cases)+3,values_checked=len(rows),unique_golden_values=sum(c['golden'] for c in cases)*32,
                    saturations=sum(int(r['saturated']) for r in rows),reset_probes=3)
        print('RMSNorm '+name+': '+str(checks),flush=True)
        reports[name]=dict(state='complete',checks=checks,exponents=[se,ge,oe],provenance=provenance,
            source_sha256={str(p.relative_to(runtime.PROJECT)):runtime.sha(p) for p in sources},
            artifacts={p.name:dict(bytes=p.stat().st_size,sha256=runtime.sha(p)) for p in work.iterdir() if p.suffix in ('.csv','.vcd','.json','.hex')})
    return dict(state='complete',configurations=reports,fixed_manifest_sha256=runtime.sha(runtime.MODEL/'fixed.json'),
        fixed_payload_sha256=manifest['images']['sha256'],
        limits='Three selected RMSNorm geometries plus synthetic clipping stress. Seven real norm1 vectors; other vectors synthetic. No full transformer or board inference')


def attention_exp_oracle(value,table):
    if value>0 or value<-(1<<62):raise ValueError('Nonpositive checked exponential input required')
    if value < -16*65536:return 0
    power,remainder=divmod(-value,45426)
    index,fraction=divmod(remainder*256,45426)
    mantissa=table[index]+round(Fraction((table[index+1]-table[index])*fraction,45426))
    return round(Fraction(mantissa,1<<power))


def attention_oracle(query,keys,values,table):
    length=len(keys)
    if not 1<=length<=256 or len(values)!=length or len(query)!=32 or any(len(row)!=32 for row in keys+values):
        raise ValueError('Attention geometry changed')
    if any(not -32768<=v<=32767 for row in [query,*keys,*values] for v in row):
        raise ValueError('Attention operands exceed signed16')
    result=[];clips=[];scores=[];exps=[];probs=[];clipped=False
    for head in range(2):
        local=[]
        for row in keys:
            total=sum(query[head*16+c]*row[head*16+c] for c in range(16))
            if not -(1<<47)<=total<(1<<47):raise OverflowError('Attention score accumulator')
            rounded=round(Fraction(total,256))
            clipped=clipped or not -(1<<31)<=rounded<(1<<31)
            local.append(min((1<<31)-1,max(-(1<<31),rounded)))
        scores.append(local)
        maximum=max(local)
        exps.append([attention_exp_oracle(v-maximum,table) for v in local])
        denominator=sum(exps[-1])
        if not 0<denominator<(1<<63):raise OverflowError('Attention exponential sum')
        probs.append([round(Fraction(v*32768,denominator)) for v in exps[-1]])
        if any(not 0<=p<=32768 for p in probs[-1]):raise OverflowError('Attention probability')
        for c in range(16):
            total=sum(probs[-1][p]*values[p][head*16+c] for p in range(length))
            if not -(1<<47)<=total<(1<<47):raise OverflowError('Attention context accumulator')
            rounded=round(Fraction(total,32768))
            clipped=clipped or not -32768<=rounded<=32767
            result.append(min(32767,max(-32768,rounded)));clips.append(int(clipped))
    return dict(scores=scores,exp=exps,prob=probs,result=result,clips=clips)


def attention_cases():
    tensors,manifest=fixed_tensor_values();table=tensors['exp_table'];rng=random.Random(2026110403)
    cases=[]
    def add(name,query,keys,values,source):
        cases.append(dict(name=name,q=query,k=keys,v=values,length=len(keys),source=source,
                          expected=attention_oracle(query,keys,values,table)))
    add('One token / unsigned probability one',[0]*32,[[0]*32],
        [[-32768 if c%2==0 else 32767 for c in range(32)]],'Synthetic signed extrema')
    add('Two-token mean and signed ties',[0]*32,[[0]*32 for _ in range(2)],
        [[c-16+p for c in range(32)] for p in range(2)],'Synthetic RNE means')
    for value in (32767,-32768):
        add('Rounded probability sum / clipping '+str(value),[0]*32,[[0]*32 for _ in range(17)],
            [[value]*32 for _ in range(17)],'Synthetic uniform probabilities; independent rounding intentionally need not sum to32768')
    add('Full-context seeded moderate QK',[rng.randrange(-2048,2048) for _ in range(32)],
        [[rng.randrange(-2048,2048) for _ in range(32)] for _ in range(256)],
        [[rng.randrange(-32768,32768) for _ in range(32)] for _ in range(256)],'Synthetic seed2026110403')
    add('Full-context signed score extrema',[32767 if c%2 else -32768 for c in range(32)],
        [[32767 if (p+c)%3 else -32768 for c in range(32)] for p in range(256)],
        [[rng.randrange(-32768,32768) for _ in range(32)] for _ in range(256)],'Synthetic extrema/cutoff')
    base=runtime.RUNTIME/'mac-frozen'
    rope,rp=vivado_frozen(base/'qk_rope',FROZEN_TRANSFERS['qk_rope'],'qk_rope',None)
    cache,cp=vivado_frozen(base/'kv_cache',FROZEN_TRANSFERS['kv_cache'],'kv_cache',None)
    bank=cache[0]
    for index,length,name in ((262,256,'Full repeated-training context'),(0,1,'J01 position0'),(1,2,'J01 position1')):
        case=rope[index]
        if case['position']!=length-1:raise ValueError('Archived attention position changed')
        if case['outputs'][32:]!=bank['k'][length-1]:raise ValueError('Archived Qrot/Krot and cache boundary differs')
        add(name,case['outputs'][:32],bank['k'][:length],bank['v'][:length],
            'Actual archived Qrot/Krot/V; context answer independently derived, not archived full-forward context golden')
    query=[2048 if c%16==0 else 0 for c in range(32)]
    keys=[[(p-8)*1024 if c%16==0 else 0 for c in range(32)] for p in range(17)]
    values=[[(p-8)*(c-16)*23 for c in range(32)] for p in range(17)]
    add('Distinct ordered scores and value addressing',query,keys,values,'Synthetic head/position/coordinate pattern')
    return cases,table,dict(fixed_payload_sha256=manifest['images']['sha256'],
        fixed_manifest_sha256=runtime.sha(runtime.MODEL/'fixed.json'),rope_transfer=rp,cache_transfer=cp)


def attention_check_trace(path,cases):
    labels=set();current=None;state=None
    checks=dict(requests=0,score_products=0,value_products=0,scores=0,exponentials=0,probabilities=0,context_values=0)
    def finish():
        if current is None:return
        case=cases[current] if current<len(cases) else cases[0];n=case['length']
        expected=dict(D=[16*n]*2,C=[16*n]*2,S=[n]*2,E=[n]*2,P=[n]*2,O=32)
        if state!=expected:raise ValueError('Incomplete attention request '+str((current,state,expected)))
        labels.add(current);checks['requests']+=1
    with path.open() as stream:
        for values in csv.DictReader(stream):
            kind=values.pop('kind');row={k:int(v) for k,v in values.items()};label=row['case']
            if label<0:continue
            if label!=current:
                finish()
                if label in labels:raise ValueError('Duplicate completed attention label')
                current=label;state={k:[0,0] for k in ('D','C','S','E','P')};state['O']=0
            if not 0<=label<len(cases)+4:raise ValueError('Unexpected attention fixture label')
            case=cases[label] if label<len(cases) else cases[0];n=case['length'];h=row['head'];p=row['position'];c=row['coordinate']
            if kind in ('D','C'):
                if h not in (0,1):raise ValueError('Invalid attention head')
                if kind=='D':
                    want_p,want_c=divmod(state['D'][h],16)
                    if (p,c)!=(want_p,want_c):raise ValueError('Attention score product order')
                    a=case['q'][h*16+c];b=case['k'][p][h*16+c]
                    total=sum(case['q'][h*16+j]*case['k'][p][h*16+j] for j in range(c+1))
                    checks['score_products']+=1
                else:
                    want_c,want_p=divmod(state['C'][h],n)
                    if (p,c)!=(want_p,want_c):raise ValueError('Attention value product order')
                    a=case['expected']['prob'][h][p];b=case['v'][p][h*16+c]
                    total=sum(case['expected']['prob'][h][j]*case['v'][j][h*16+c] for j in range(p+1))
                    checks['value_products']+=1
                if (row['a'],row['b'],row['product'],row['total'])!=(a,b,a*b,total):
                    raise ValueError('Independent attention product/partial sum mismatch '+str((label,kind,h,p,c)))
                state[kind][h]+=1
            elif kind in ('S','E','P'):
                if h not in (0,1) or p!=state[kind][h]:raise ValueError('Attention scalar event order')
                key={'S':'scores','E':'exp','P':'prob'}[kind]
                if row['value']!=case['expected'][key][h][p]:raise ValueError('Independent attention '+key+' mismatch')
                state[kind][h]+=1;checks[{'S':'scores','E':'exponentials','P':'probabilities'}[kind]]+=1
            elif kind=='O':
                if c!=state['O'] or row['error'] or (row['value'],row['saturated'])!=(case['expected']['result'][c],case['expected']['clips'][c]):
                    raise ValueError('Independent attention output/clipping mismatch')
                state['O']+=1;checks['context_values']+=1
            else:raise ValueError('Unknown attention event')
    finish()
    if labels!=set(range(len(cases)+4)):raise ValueError('Missing attention request')
    return dict(checks,all_exact=True,reset_probes=4,heads=2,max_length=256,
        real_archived_input_cases=sum('Actual archived' in c['source'] for c in cases),
        limits='Actual pinned table plus synthetic and archived intermediate operands; no archived full-forward context golden or complete transformer proof')


def run_attention_vivado(folder,command):
    work=folder/'attention';work.mkdir();cases,table,provenance=attention_cases()
    runtime.save(work/'fixtures.json',dict(cases=cases,table=table,provenance=provenance))
    def hexfile(name,values,width=16):
        path=work/(name+'.hex');path.write_text(''.join(f'{v&((1<<width)-1):0{width//4}x}\n' for v in values));return str(path)
    args=dict(N=str(len(cases)),Q=hexfile('Q',(v for c in cases for v in c['q'])),
        K=hexfile('K',(v for c in cases for row in [*c['k'],*[[0]*32 for _ in range(256-c['length'])]] for v in row)),
        V=hexfile('V',(v for c in cases for row in [*c['v'],*[[0]*32 for _ in range(256-c['length'])]] for v in row)),
        ANSWERS=hexfile('ANSWERS',(v for c in cases for v in c['expected']['result'])),
        CLIPS=hexfile('CLIPS',(v for c in cases for v in c['expected']['clips']),8),
        LENGTHS=hexfile('LENGTHS',(c['length'] for c in cases)),TABLE=hexfile('TABLE',table,32),
        CSV=str(work/'events.csv'),VCD=str(work/'waves.vcd'))
    sources=[RTL/(n+'.sv') for n in ('fixed_scalar','kv_cache','attention','attention_tb')]
    base=Path('/home/admin/amd/2025.2/Vivado/bin')
    command(work,'compile',[base/'xvlog','--sv',*sources])
    command(work,'elaborate',[base/'xelab','work.attention_tb','--debug','typical','--mt','2','--snapshot','attention_sim'])
    output=command(work,'simulation',[base/'xsim','attention_sim','--runall','--onerror','quit','--onfinish','quit',
        *[v for k,value in args.items() for v in ('--testplusarg',k+'='+value)]])
    if f'PASS attention requests={len(cases)+4} heads=2 coordinates=32 reset_probes=4' not in output:
        raise ValueError('Missing attention success receipt')
    checks=attention_check_trace(work/'events.csv',cases)
    return dict(state='complete',checks=checks,provenance=provenance,
        oracle='Independent unbounded Python ints/Fraction with selected exp table; every score/product/partial/exp/prob/context checked',
        source_sha256={str(p.relative_to(runtime.PROJECT)):runtime.sha(p) for p in sources},
        artifacts={p.name:dict(bytes=p.stat().st_size,sha256=runtime.sha(p)) for p in work.iterdir() if p.suffix in ('.csv','.vcd','.json','.hex')})


def dense_case(name,x,weights,shift,bits):
    """Independent unbounded products/sums and Fraction nearest-even narrowing."""
    if not x or bits not in (16,32) or not 0<=shift<=47 or any(not -32768<=v<=32767 for v in x):
        raise ValueError('Invalid dense operand format')
    expected=[]
    for row in weights:
        if len(row)!=len(x) or any(not -32768<=v<=32767 for v in row):raise ValueError('Invalid dense weight geometry')
        products=[a*b for a,b in zip(x,row)];partials=[];total=0
        for product in products:
            total+=product
            if not -(1<<47)<=total<(1<<47):raise OverflowError('Dense sum exceeds signed48')
            partials.append(total)
        rounded=round(Fraction(total,1<<shift));lo=-(1<<(bits-1));hi=(1<<(bits-1))-1
        expected.append(dict(products=products,partials=partials,rounded=rounded,
                             result=min(hi,max(lo,rounded)),saturated=int(not lo<=rounded<=hi)))
    return dict(name=name,x=x,weights=weights,expected=expected)


def dense_fixtures(inputs,outputs,shift,bits,weights=None):
    rng=random.Random(2026110401);cases=[]
    def add(name,x,w):cases.append(dense_case(name,x,w,shift,bits))
    if weights is not None:
        add('Pinned weights / SYNTHETIC seeded activations',[rng.randrange(-2048,2048) for _ in range(inputs)],weights)
        add('Pinned weights / SYNTHETIC signed extrema',[32767,-32768]*(inputs//2),weights)
        add('Pinned weights / SYNTHETIC coordinate pattern',[(j+1)*(-1 if j%2 else 1) for j in range(inputs)],weights)
        return cases
    weights=[[rng.randrange(-2048,2048) for _ in range(inputs)] for _ in range(outputs)]
    add('Seeded retained weights',[rng.randrange(-2048,2048) for _ in range(inputs)],weights)
    add('Activation-only reload',[rng.randrange(-2048,2048) for _ in range(inputs)],weights)
    def uniform(name,x,w):add(name,x,[w[r%inputs:]+w[:r%inputs] for r in range(outputs)])
    uniform('Zero',[0]*inputs,[0]*inputs);uniform('Unit',[1]*inputs,[1]*inputs)
    for a,b in ((32767,32767),(-32768,-32768),(-32768,32767),(32767,-32768)):
        uniform('Extrema '+str((a,b)),[a]*inputs,[b]*inputs)
    uniform('Cancellation',[-32767,32767]*(inputs//2),[32767]*inputs)
    if shift:
        for a in (-5,-3,-1,1,3,5):
            sign=-1 if shift==16 else 1
            uniform('Tie '+str(a),[sign*a]+[0]*(inputs-1),[-32768 if shift==16 else 1<<(shift-1)]+[0]*(inputs-1))
        for delta in (-1,1):
            for sign in (-1,1):
                if shift==16:
                    uniform('Near half '+str((sign,delta)),[sign,sign]+[0]*(inputs-2),[32767,1+delta]+[0]*(inputs-2))
                else:uniform('Near half '+str((sign,delta)),[sign]+[0]*(inputs-1),[(1<<(shift-1))+delta]+[0]*(inputs-1))
    for reverse in (False,True):
        add('Reversed orientation' if reverse else 'Orientation',list(range(1,inputs+1)),
            [[(32767,-32768,16384)[r%3] if j==(inputs-1-r%inputs if reverse else r%inputs) else 0
              for j in range(inputs)] for r in range(outputs)])
    for i in range(8):
        limit=2048 if i<4 else 32768
        add('Random '+str(i),[rng.randrange(-limit,limit) for _ in range(inputs)],
            [[rng.randrange(-limit,limit) for _ in range(inputs)] for _ in range(outputs)])
    return cases


def dense_check_trace(path,cases,inputs,outputs):
    seen=set();term_count=0;output_count=0;current=None;term=0;next_output=0;starts={};seen_result=set();stall_edges=0;last_clock=-1
    def finish():
        if current is not None:
            if term!=inputs*outputs or next_output!=outputs:raise ValueError('Missing completed dense request '+str(current))
            seen.add(current)
    with path.open() as source:
        for raw in csv.DictReader(source):
            row={k:int(v) for k,v in raw.items()};label=row['case']
            if row['cycle']<=last_clock:raise ValueError('Dense trace clock order changed')
            last_clock=row['cycle']
            if label<0:continue
            if not 0<=label<len(cases)+8:raise ValueError('Invalid dense transaction label')
            if label!=current:
                finish()
                if label in seen:raise ValueError('Duplicate dense transaction label')
                current=label;term=0;next_output=0;starts={};seen_result=set()
            case=cases[label] if label<len(cases) else cases[0] if label<len(cases)+7 else cases[1]
            if row['phase']==1 and not row['step_valid']:starts.setdefault(row['result_row'],row['cycle'])
            if row['step_valid']:
                r,j=divmod(term,inputs)
                if r>=outputs:raise ValueError('Extra dense arithmetic term')
                expected=case['expected'][r]
                if (row['step_row'],row['step_index'],row['step_input'],row['step_weight'],row['step_product'],row['step_sum'])!=(
                        r,j,case['x'][j],case['weights'][r][j],expected['products'][j],expected['partials'][j]):
                    raise ValueError('Independent dense term mismatch '+str((label,r,j)))
                term+=1;term_count+=1
            if row['result_valid']:
                r=row['result_row']
                if not 0<=r<outputs:raise ValueError('Invalid dense result row')
                expected=case['expected'][r]
                if row['result']!=expected['result'] or row['saturated']!=expected['saturated']:
                    raise ValueError('Independent dense rounding/clipping mismatch')
                if r not in seen_result:
                    if r!=next_output or row['cycle']-starts[r]!=2*inputs+1:raise ValueError('Dense row tag/latency mismatch')
                    next_output+=1;seen_result.add(r);output_count+=1
                else:stall_edges+=1
    finish()
    if seen!=set(range(len(cases)+8)):raise ValueError('Dense completed request coverage differs')
    return dict(requests=len(seen),outputs_checked=output_count,products_partial_sums_checked=term_count,
                row_latency_edges=2*inputs+1,reset_probes=7,stall_edges=stall_edges,all_exact=True)


def dense_hexfile(folder,name,values,bits=16):
    path=folder/(name+'.hex')
    path.write_text(''.join(f'{v&((1<<bits)-1):0{bits//4}x}\n' for v in values))
    return str(path)


def run_dense_vivado(folder,command):
    values,manifest=fixed_tensor_values();reports=[]
    geometries=[(32,32,16,16,'O','O','context','o'),(128,32,15,16,'down','down','hidden','down'),
        (32,320,8,32,'logits','E','normfinal','logits'),(32,128,16,16,'gate','gate','norm2','gate'),
        (32,128,15,16,'up','up','norm2','up')]
    for kind in ('synthetic','real-weights'):
        targets=geometries+([(32,320,0,32,'32bit-clipping',None,None,None)] if kind=='synthetic' else [])
        for inputs,outputs,shift,bits,name,weight,source,target in targets:
            if weight and (manifest['activation_exponents'][target]-(manifest['activation_exponents'][source]+
                    manifest['weight_exponents'][weight])!=shift or manifest['images']['arrays'][weight]['shape']!=[outputs,inputs]):
                raise ValueError('Dense shape/binary scale differs from selected model')
            work=folder/('dense-'+name+'-'+kind);work.mkdir()
            weights=None if kind=='synthetic' else [values[weight][r*inputs:(r+1)*inputs] for r in range(outputs)]
            cases=dense_fixtures(inputs,outputs,shift,bits,weights);runtime.save(work/'fixtures.json',cases)
            args=dict(CASES=str(len(cases)),X=dense_hexfile(work,'inputs',(v for c in cases for v in c['x'])),
                W=dense_hexfile(work,'weights',(v for c in cases for row in c['weights'] for v in row)),
                ANSWERS=dense_hexfile(work,'answers',(e['result'] for c in cases for e in c['expected']),bits),
                CLIPS=dense_hexfile(work,'clips',(e['saturated'] for c in cases for e in c['expected']),8),
                CSV=str(work/'cycles.csv'),VCD=str(work/'waves.vcd'))
            tools=Path('/home/admin/amd/2025.2/Vivado/bin')
            command(work,'compile',[tools/'xvlog','--sv',RTL/'dense.sv',RTL/'dense_tb.sv'])
            command(work,'elaborate',[tools/'xelab','work.dense_tb','--debug','typical','--mt','2','--snapshot','dense_sim',
                *[v for k,value in (('INPUTS',inputs),('OUTPUTS',outputs),('SHIFT',shift),('RESULT_BITS',bits)) for v in ('--generic_top',k+'='+str(value))]])
            output=command(work,'simulation',[tools/'xsim','dense_sim','--runall','--onerror','quit','--onfinish','quit',
                *[v for k,value in args.items() for v in ('--testplusarg',k+'='+value)]])
            wanted=f'PASS dense requests={len(cases)+8} inputs={inputs} outputs={outputs} shift={shift} bits={bits} reset_probes=7'
            if wanted not in output:raise ValueError('Missing dense testbench receipt')
            checks=dense_check_trace(work/'cycles.csv',cases,inputs,outputs)
            reports.append(dict(name=name,kind=kind,artifact_directory=work.name,inputs=inputs,outputs=outputs,shift=shift,bits=bits,checks=checks,
                evidence='Synthetic arithmetic/protocol only' if kind=='synthetic' else 'Pinned real weights with SYNTHETIC activations; no full-model reference comparison',
                artifacts={p.name:dict(bytes=p.stat().st_size,sha256=runtime.sha(p)) for p in work.iterdir() if p.suffix in ('.hex','.json','.csv','.vcd')}))
            print('Dense '+name+' '+kind+': '+str(checks),flush=True)
    return dict(state='complete',geometries=reports,fixed_payload_sha256=manifest['images']['sha256'],
                source_sha256={name:runtime.sha(RTL/name) for name in ('dense.sv','dense_tb.sv')})


def ff_exp_negative(value,table):
    if value>0:raise ValueError('Nonpositive exp input required')
    magnitude=min(-value,16*65536);power,remainder=divmod(magnitude,45426)
    index,fraction=divmod(remainder*256,45426)
    mantissa=table[index]+round(Fraction((table[index+1]-table[index])*fraction,45426))
    return 0 if -value>16*65536 else round(Fraction(mantissa,1<<power))


def ff_oracle(x,values):
    """Selected SwiGLU with independent unbounded/Fraction math, supplied weights/table."""
    if len(x)!=32:raise ValueError('SwiGLU input needs32 coordinates')
    weights={k:[values[k][r*n:(r+1)*n] for r in range(rows)]
             for k,n,rows in (('gate',32,128),('up',32,128),('down',128,32))}
    gate=dense_case('Gate',x,weights['gate'],16,16)['expected']
    up=dense_case('Up',x,weights['up'],15,16)['expected']
    def clipped(value):return min(32767,max(-32768,value)),int(not -32768<=value<=32767)
    silu=[];hidden=[];clips=[]
    for g,u in zip(gate,up):
        a,b=g['result'],u['result'];decay=ff_exp_negative(-abs(a<<6),values['exp_table'])
        sigmoid=round(Fraction((1<<62) if a>=0 else decay<<31,(1<<31)+decay))
        s,cs=clipped(round(Fraction(a*sigmoid,1<<30)));h,ch=clipped(round(Fraction(s*b,1<<13)))
        silu.append(s);hidden.append(h);clips.append(g['saturated']|(u['saturated']<<1)|(cs<<2)|(ch<<3))
    output=dense_case('Down',hidden,weights['down'],15,16)['expected']
    return dict(x=x,gate=[e['result'] for e in gate],up=[e['result'] for e in up],silu=silu,hidden=hidden,
                element_clips=clips,outputs=[e['result'] for e in output],output_clips=[e['saturated'] for e in output])


def ff_fixtures():
    values,manifest=fixed_tensor_values();rng=random.Random(2026110403)
    inputs=[[rng.randrange(-2048,2048) for _ in range(32)],[0]*32,[32767,-32768]*16,list(range(-16,16))]
    cases=[dict(name='SYNTHETIC norm2 input '+str(i),**ff_oracle(x,values)) for i,x in enumerate(inputs)]
    return cases,values,manifest


def ff_check_trace(path,cases):
    seen={};elements=0;outputs=0;clipped_elements=0;last_clock=-1
    with path.open() as source:
        for raw in csv.DictReader(source):
            row={k:int(v) for k,v in raw.items()};label=row['case']
            if row['cycle']<=last_clock:raise ValueError('Feed-forward clock order changed')
            last_clock=row['cycle']
            if label<0:continue
            if row['error']:raise ValueError('Unexpected feed-forward scalar fault')
            case=cases[label] if label<len(cases) else cases[0]
            counts=seen.setdefault(label,[0,set()])
            if row['element_valid']:
                j=counts[0]
                if j>=128 or row['element_index']!=j or [row[k] for k in ('gate','up','silu','hidden','element_clips')]!=[
                        case[k][j] for k in ('gate','up','silu','hidden','element_clips')]:raise ValueError('Independent feed-forward element mismatch')
                counts[0]+=1;elements+=1;clipped_elements+=int(bool(row['element_clips']))
            if row['result_valid']:
                j=row['result_row']
                if not 0<=j<32 or row['result']!=case['outputs'][j] or row['saturated']!=case['output_clips'][j]:
                    raise ValueError('Independent feed-forward final result mismatch')
                if j not in counts[1]:counts[1].add(j);outputs+=1
    if set(seen)!=set(range(len(cases)+4)) or any(n!=128 or r!=set(range(32)) for n,r in seen.values()):
        raise ValueError('Missing completed feed-forward request')
    return dict(requests=len(seen),element_intermediates_checked=elements*4,elements_checked=elements,
                outputs_checked=outputs,reset_probes=4,fault_probes=1,clipped_element_observations=clipped_elements,all_exact=True)


def run_feedforward_vivado(folder,command):
    cases,values,manifest=ff_fixtures();work=folder/'feedforward';work.mkdir();runtime.save(work/'fixtures.json',cases)
    args=dict(CASES=str(len(cases)),X=dense_hexfile(work,'inputs',(v for c in cases for v in c['x'])),
        GATE=dense_hexfile(work,'gate',values['gate']),UP=dense_hexfile(work,'up',values['up']),
        DOWN=dense_hexfile(work,'down',values['down']),EXP=dense_hexfile(work,'exp',values['exp_table'],32),
        EGATE=dense_hexfile(work,'expected-gate',(v for c in cases for v in c['gate'])),
        EUP=dense_hexfile(work,'expected-up',(v for c in cases for v in c['up'])),
        ESILU=dense_hexfile(work,'expected-silu',(v for c in cases for v in c['silu'])),
        EHIDDEN=dense_hexfile(work,'expected-hidden',(v for c in cases for v in c['hidden'])),
        ECLIPS=dense_hexfile(work,'expected-element-clips',(v for c in cases for v in c['element_clips']),8),
        ANSWERS=dense_hexfile(work,'answers',(v for c in cases for v in c['outputs'])),
        CLIPS=dense_hexfile(work,'clips',(v for c in cases for v in c['output_clips']),8),
        CSV=str(work/'cycles.csv'),VCD=str(work/'waves.vcd'))
    tools=Path('/home/admin/amd/2025.2/Vivado/bin');names=('dense.sv','fixed_scalar.sv','feedforward.sv','feedforward_tb.sv')
    command(work,'compile',[tools/'xvlog','--sv',*[RTL/name for name in names]])
    command(work,'elaborate',[tools/'xelab','work.feedforward_tb','--debug','typical','--mt','2','--snapshot','feedforward_sim'])
    output=command(work,'simulation',[tools/'xsim','feedforward_sim','--runall','--onerror','quit','--onfinish','quit',
        *[v for k,value in args.items() for v in ('--testplusarg',k+'='+value)]])
    wanted=f'PASS feedforward requests={len(cases)+4} elements={(len(cases)+4)*128} outputs={(len(cases)+4)*32} reset_probes=4 fault_probes=1'
    if wanted not in output:raise ValueError('Missing feed-forward testbench receipt')
    checks=ff_check_trace(work/'cycles.csv',cases);print('Feed-forward: '+str(checks),flush=True)
    return dict(state='complete',checks=checks,fixed_payload_sha256=manifest['images']['sha256'],
        evidence='Pinned real weights/tables with SYNTHETIC norm2 inputs; no full-model reference comparison',
        source_sha256={name:runtime.sha(RTL/name) for name in names},
        artifacts={p.name:dict(bytes=p.stat().st_size,sha256=runtime.sha(p)) for p in work.iterdir() if p.suffix in ('.hex','.json','.vcd','.csv')},
        limits='Feed-forward sublayer only: external norm2 input, no residual, complete transformer, bitstream or board result')


def transformer_model_words(values):
    """Ordered32-bit loader words: signed16 tensor payloads occupy the low16bits."""
    names=('E','Q','K','V','O','gate','up','down','gain1','gain2','gain3')
    words=[v&65535 for name in names for v in values[name]]
    rope=values['rope']
    if len(rope)!=4096:raise ValueError('Expected original256x8 RoPE pairs')
    words += [(rope[i]&65535)|((rope[i+1]&65535)<<16) for i in range(0,len(rope),2)]
    words += values['exp_table']+values['rsqrt_table']
    if len(words)!=29281 or any(not 0<=v<(1<<32) for v in words):raise ValueError('Full-core model word format differs')
    return words


def transformer_bos_reference(values):
    """Archived Mac boundaries plus analytically exact one-position attention invariants."""
    matrices,mp=vivado_frozen(runtime.RUNTIME/'mac-frozen/mac32',FROZEN_TRANSFERS['mac32'],'mac32',96)
    ropes,rp=vivado_frozen(runtime.RUNTIME/'mac-frozen/qk_rope',FROZEN_TRANSFERS['qk_rope'],'qk_rope',None)
    case=matrices[0];rope=ropes[0]
    if case['model_reference']['prefix_length']!=1 or rope['position']!=0 or rope['x']!=[e['result'] for e in case['expected'][:64]]:
        raise ValueError('Archived BOS boundaries differ')
    expected=dict(embed=values['E'][256*32:257*32],norm1=case['x'],
        q=[e['result'] for e in case['expected'][:32]],k=[e['result'] for e in case['expected'][32:64]],
        v=[e['result'] for e in case['expected'][64:96]],qrot=rope['outputs'][:32],krot=rope['outputs'][32:])
    expected['cache_k']=expected['krot'];expected['cache_v']=expected['v']
    scores=[round(Fraction(sum(a*b for a,b in zip(expected['qrot'][h*16:(h+1)*16],expected['krot'][h*16:(h+1)*16])),256)) for h in range(2)]
    derived=dict(scores={0:scores[0],256:scores[1]},exp={0:1<<31,256:1<<31},prob={0:32768,256:32768},context=expected['v'])
    return expected,derived,dict(projection=mp,rope=rp)


def transformer_check_trace(path,tokens,bos,derived,full_golden=None):
    """Check observed stage coverage and original references; no invented logit targets."""
    lengths={k:32 for k in ('embed','norm1','q','k','v','qrot','krot','context','o','res1','norm2','down','res2','normfinal')}
    lengths.update(gate=128,up=128,silu=128,hidden=128,ff_clips=128,logits=320)
    observed={};last_cycle=-1;logits=0
    with path.open() as source:
        for raw in csv.DictReader(source):
            row={k:int(v) if k!='stage' else v for k,v in raw.items()};step=row['step'];stage=row['stage'];index=row['index']
            if row['cycle']<last_cycle:raise ValueError('Full-core trace clock order changed')
            last_cycle=row['cycle']
            if not 0<=step<=len(tokens):raise ValueError('Invalid full-core request label')
            stages=observed.setdefault(step,{})
            coordinates=stages.setdefault(stage,{})
            if index in coordinates:raise ValueError('Duplicate full-core stage coordinate '+str((step,stage,index)))
            coordinates[index]=row['value']
            if stage=='logits':
                if index!=len(coordinates)-1:raise ValueError('Logit order changed')
                logits+=1
    if set(observed)!=set(range(len(tokens)+1)):raise ValueError('Missing completed decoder request')
    archived_checks=0;derived_checks=0;golden_checks=0
    for step,stages in observed.items():
        position=step if step<len(tokens) else 0
        wanted=dict(lengths,cache_k=32,cache_v=32,scores=2*(position+1),exp=2*(position+1),prob=2*(position+1))
        if set(stages)!=set(wanted):raise ValueError('Missing/extra observed decoder stage '+str(set(wanted)^set(stages)))
        for stage,count in wanted.items():
            expected_indices=({h*256+p for h in range(2) for p in range(position+1)} if stage in ('scores','exp','prob') else
                              set(range(position*32,(position+1)*32)) if stage in ('cache_k','cache_v') else set(range(count)))
            if set(stages[stage])!=expected_indices:raise ValueError('Incomplete decoder stage '+str((step,stage)))
        if step in (0,len(tokens)):
            for stage,values in bos.items():
                if [stages[stage][i] for i in range(len(values))]!=values:raise ValueError('Archived BOS boundary mismatch: '+stage)
                archived_checks+=len(values)
            for stage,values in derived.items():
                wanted_values=values if isinstance(values,dict) else dict(enumerate(values))
                if stages[stage]!=wanted_values:raise ValueError('Derived BOS attention invariant differs: '+stage)
                derived_checks+=len(wanted_values)
        if full_golden is not None:
            expected=full_golden[step] if step<len(tokens) else full_golden[0]
            for stage,values in expected.items():
                wanted_values=values if isinstance(values,dict) else dict(enumerate(values))
                if stages.get(stage)!=wanted_values:raise ValueError('Original full-model golden mismatch: '+str((step,stage)))
                golden_checks+=len(wanted_values)
    return dict(requests=len(observed),ordered_logits=logits,archived_bos_boundary_values_checked=archived_checks,
                derived_bos_attention_values_checked=derived_checks,full_model_golden_values_checked=golden_checks,
                full_model_comparison='pending' if full_golden is None else 'provided original Mac golden arrays',
                clear_context_replays=1,all_available_checks_exact=True),observed


def mac_case_golden(case):
    """Decode original integer arrays into causal RTL coordinates, never a forward.

    The caller must verify the Mac transfer manifest and original export receipt
    before passing a case. Attention excludes future columns; cache coordinates
    are position*32+head*16+coordinate. No states or logits may be omitted.
    """
    tokens=case['tokens'];length=len(tokens)
    if (not 1<=length<=256 or tokens[0]!=256 or
        any(type(t) is not int or not 0<=t<320 for t in tokens) or
        case.get('incremental_matches_full') is not True):
        raise ValueError('Original Mac case tokens/incremental proof differs')
    widths={name:32 for name in ('embed','norm1','q','k','v','qrot','krot','context',
            'o','res1','norm2','down','res2','normfinal')}
    widths.update(gate=128,up=128,silu=128,hidden=128,logits=320)
    if set(case['states'])!=set(widths)|{'scores','prob'}:
        raise ValueError('Original Mac state inventory differs')
    def tensor(item,shape,low,high):
        if item.get('shape')!=shape or item.get('dtype') not in ('int64','<i8'):
            raise ValueError('Original Mac integer tensor shape/dtype differs')
        def check(values,axes):
            if not axes:
                if type(values) is not int or not low<=values<=high:
                    raise ValueError('Original Mac integer tensor value/range differs')
            else:
                if not isinstance(values,list) or len(values)!=axes[0]:
                    raise ValueError('Original Mac integer tensor nested shape differs')
                for value in values:check(value,axes[1:])
        check(item['values'],shape)
        return item['values']
    arrays={name:tensor(case['states'][name],[1,length,width],-(1<<(31 if name=='logits' else 15)),
                        (1<<(31 if name=='logits' else 15))-1) for name,width in widths.items()}
    arrays['scores']=tensor(case['states']['scores'],[1,2,length,length],-(1<<31),(1<<31)-1)
    arrays['prob']=tensor(case['states']['prob'],[1,2,length,length],0,65535)
    if set(case['cache'])!={'k','v'}:raise ValueError('Original Mac cache inventory differs')
    caches={name:tensor(case['cache'][name],[1,2,length,16],-32768,32767) for name in ('k','v')}
    golden=[]
    for position in range(length):
        row={name:arrays[name][0][position] for name in widths}
        for name in ('scores','prob'):
            row[name]={head*256+p:arrays[name][0][head][position][p]
                       for head in range(2) for p in range(position+1)}
        for name,stage in (('k','krot'),('v','v')):
            values=[value for head in range(2) for value in caches[name][0][head][position]]
            if values!=row[stage]:raise ValueError('Original Mac final cache differs from returned states')
            row['cache_'+name]={position*32+i:value for i,value in enumerate(values)}
        golden.append(row)
    return tokens,golden


def mac_whole_model_reference(folder,digest):
    """Verify the sealed original Mac export before decoding any reference arrays."""
    import fixed
    import re
    folder=folder.resolve();transfer_path=folder/'transfer.json'
    if not digest or runtime.sha(transfer_path)!=digest:raise ValueError('Whole-model transfer manifest hash differs')
    transfer=runtime.read(transfer_path)
    names=('BOS','J01-first16','authored128','repeated-J01-256')
    expected={'goldens.json','export-results.json'}|{
        'provenance/'+name+'/'+file for name in names for file in ('export-results.json','watchdog.json','launch.json')}
    _,selected=fixed_tensor_values()
    pins=dict(fixed_manifest=fixed.SELECTED_SHA256,payload=selected['images']['sha256'],
              selection_manifest=runtime.sha(runtime.MODEL/'selection.json'))
    if (transfer['schema']!=1 or transfer['kind']!='fresh-selected-fixed-whole-model-reference' or
        transfer['case_names']!=list(names) or transfer['case_lengths']!=[1,16,128,256] or
        set(transfer['files'])!=expected or transfer['fixed_manifest_sha256']!=pins['fixed_manifest'] or
        transfer['fixed_payload_sha256']!=pins['payload']):
        raise ValueError('Whole-model transfer identity/inventory differs')
    for name,pin in transfer['files'].items():
        path=(folder/name).resolve()
        if (not path.is_relative_to(folder) or path.stat().st_size!=pin['bytes'] or runtime.sha(path)!=pin['sha256']):
            raise ValueError('Whole-model transfer input bytes/hash differ: '+name)
    report=runtime.read(folder/'export-results.json')
    flags=('accepted','all_full_incremental_states_logits_prefix_and_final_caches_exact',
           'all_json_roundtrips_exact','source_and_selected_weights_unchanged')
    if (report['schema']!=1 or report['state']!='complete' or any(report.get(k) is not True for k in flags) or
        report['arithmetic_sha256']!=fixed.implementation_sha256() or report['model_pins']!=pins or
        report['case_names']!=list(names) or report['source_sha256']!=transfer['source_sha256'] or
        report['worker_sha256']!=transfer['worker_sha256'] or report['git_commit']!=transfer['source_commit'] or
        report['goldens']!=transfer['files']['goldens.json']):
        raise ValueError('Original whole-model export receipt/provenance differs')
    # The Linux harness/docs/runtime can differ; all computational reference and
    # selected model source identities must remain the same as the original Mac.
    for name in ('tools/fixed.py','tools/model.py','tools/generative.py','tools/llama_numpy_reference.py',
                 'uv.lock','pyproject.toml','model/fixed.json','model/selection.json','model/jokes.json'):
        if runtime.sha(runtime.PROJECT/name)!=transfer['source_sha256'][name]:
            raise ValueError('Original whole-model computational source differs: '+name)
    versions={}
    for section in (runtime.PROJECT/'uv.lock').read_text().split('[[package]]')[1:]:
        name=re.search(r'^name = "([^"]+)"$',section,re.M);version=re.search(r'^version = "([^"]+)"$',section,re.M)
        if name and version and name[1] in ('mlx','mlx-lm','numpy','transformers'):versions[name[1]]=version[1]
    if len(versions)!=4 or report['packages']!=versions:raise ValueError('Whole-model Mac package versions differ from pinned lock')
    for name,pin in report['selected_weight_pins'].items():
        path=(runtime.RUNTIME/name).resolve()
        if (not path.is_relative_to(runtime.RUNTIME.resolve()) or path.stat().st_size!=pin['bytes'] or
            runtime.sha(path)!=pin['sha256']):raise ValueError('Original selected weight pin differs: '+name)
    payload=runtime.read(folder/'goldens.json')
    if payload['schema']!=1 or [c['name'] for c in payload['cases']]!=list(names):
        raise ValueError('Whole-model case inventory differs')
    profile='(version 1)(allow default)(deny network*)(deny file-write*)'
    profile+='(allow file-write* (literal "/dev/null")'+''.join(
        ' (subpath (param "'+n+'"))' for n in ('TINY_TMP','TINY_CACHE','TINY_OUTPUTS'))+')'
    golden={};saturations=0;worker_reports=report['case_reports']
    if len(worker_reports)!=4:raise ValueError('Whole-model worker receipt count differs')
    for case,original in zip(payload['cases'],worker_reports):
        name=case['name'];base=folder/'provenance'/name
        worker=runtime.read(base/'export-results.json');watchdog=runtime.read(base/'watchdog.json');launch=runtime.read(base/'launch.json')
        if (worker!=original or worker['case']!=name or worker['tokens']!=case['tokens'] or
            worker['state']!='complete' or any(worker.get(k) is not True for k in
                ('accepted','all_states_integer','source_unchanged','selected_pins_unchanged','json_roundtrip_exact','incremental_matches_full')) or
            worker['model_pins']!=pins or worker['arithmetic_sha256']!=report['arithmetic_sha256'] or
            worker['source_sha256']!=transfer['source_sha256'] or worker['worker_sha256']!=transfer['worker_sha256'] or
            worker['packages']!=report['packages'] or worker['mlx_memory_limit_bytes']!=2147483648 or
            worker['timeout_seconds']!=180 or case['counters']!={'full':worker['full_counters'],'incremental':worker['incremental_counters']}):
            raise ValueError('Whole-model per-case reference receipt differs: '+name)
        linked=report['case_results'][name]
        if (linked['export_results_sha256']!=transfer['files']['provenance/'+name+'/export-results.json']['sha256'] or
            worker['goldens']!=linked['goldens']):
            raise ValueError('Whole-model case aggregation identity differs: '+name)
        if (watchdog!=report['case_results'][name]['watchdog'] or watchdog['timeout_seconds']!=180 or
            watchdog['exit_code']!=0 or any(watchdog.get(k) is not True for k in ('child_reaped','child_absent','process_group_absent')) or
            not 0<=watchdog['elapsed_seconds']<=180):
            raise ValueError('Whole-model worker watchdog/cleanup differs: '+name)
        cmd=launch['command'];env=launch['clean_environment']
        if (launch.get('same_launch_arguments_except_worker_path') is not True or
            launch['worker_timeout_seconds']!=180 or launch['worker_sha256']!=transfer['worker_sha256'] or
            launch['parent_sha256']!=report['supervisor_sha256'] or len(cmd)!=18 or
            cmd[0]!='/usr/bin/sandbox-exec' or cmd[1:7:2]!=['-D']*3 or cmd[7:9]!=['-p',profile] or
            cmd[10:12]!=['-I','-B'] or cmd[13:17]!=['--case',name,'--inside','--output'] or
            env.get('MLX_ENABLE_TF32')!='0' or env.get('PYTHONDONTWRITEBYTECODE')!='1' or
            set(env)-{'PATH','HOME','USER','LOGNAME','LANG','LC_ALL','LC_CTYPE','TERM',
                      'PYTHONDONTWRITEBYTECODE','TMPDIR','MLX_ENABLE_TF32'}):
            raise ValueError('Whole-model original sandbox/launch differs: '+name)
        mapping=dict(item.split('=',1) for item in cmd[2:7:2]);mac_root=Path(mapping['TINY_TMP']).parent
        if (mapping!={k:str(mac_root/v) for k,v in (('TINY_TMP','tmp'),('TINY_CACHE','cache'),('TINY_OUTPUTS','outputs'))} or
            cmd[9]!=str(mac_root/'venv/bin/python') or not Path(cmd[12]).is_relative_to(mac_root/'tmp') or
            not Path(cmd[17]).is_relative_to(mac_root/'outputs') or env['TMPDIR']!=mapping['TINY_TMP']):
            raise ValueError('Whole-model original sandbox mapping differs: '+name)
        tokens,arrays=mac_case_golden(case)
        prefix={'BOS':'bos','J01-first16':'j01-16','authored128':'authored128','repeated-J01-256':'repeated-j01-256'}[name]
        if tokens!=transformer_prefix_tokens(prefix):raise ValueError('Whole-model frozen input tokens differ: '+name)
        saturations+=sum(stat['saturated'] for counters in case['counters'].values() for stat in counters.values())
        golden[name]=dict(tokens=tokens,arrays=arrays,counters=case['counters'])
    if saturations or report['full_and_incremental_saturations']!=saturations:
        raise ValueError('Whole-model reference saturation requires additional hardware flag verification')
    return golden,dict(directory=str(folder),transfer_sha256=digest,files=transfer['files'],
        original_commit=transfer['source_commit'],worker_sha256=transfer['worker_sha256'],model_pins=pins,
        arithmetic_sha256=report['arithmetic_sha256'],reference_checks=report['checks'],saturations=saturations,
        original_environment='Original pinned offline Mac export; no model environment or forward recreated on Linux',
        provenance_scope='Transfer/data/receipt hashes and declarations locally verified. Worker/supervisor source hashes and execution controls are Mac-attested; script bytes were not transferred')


CONDITIONED_TRANSFER_SHA256 = 'c0d3b73943ab580199cc7a4ceb0807c9a215e250d58c169fab016b019598a4fc'
CONDITIONED_CASES = (('BOS',1),('J01-first16',16),('authored128',128),('repeated-J01-256',256),
                     ('encoded-fu2p2q',13),('encoded-hello',11),('encoded-max48',97))


def mac_conditioned_reference(folder,digest,model_inputs):
    """Verify the separate balanced candidate and all seven fresh Mac exports.

    Decode exported arrays only. Original computational sources are bound to
    the earlier verified source import; never replace server source or run MLX.
    """
    import fixed
    import board_bos
    folder=folder.resolve()
    if digest!=CONDITIONED_TRANSFER_SHA256 or runtime.sha(folder/'transfer.json')!=digest:
        raise ValueError('Conditioned transfer manifest hash differs')
    transfer=runtime.read(folder/'transfer.json')
    expected={'fixed/'+name for name in ('arithmetic.json','converted.json','fixed-tensors.safetensors','results.json','final-comparison.json')}
    expected|={'goldens/'+name+'/'+file for name,_ in CONDITIONED_CASES for file in ('goldens.json','export-results.json','watchdog.json')}
    expected|={'provenance/conditioned-balanced-'+stage+'-20261109/'+file
               for stage in ('scale','export') for file in ('worker.py','supervisor.py')}
    if transfer['schema']!=1 or set(transfer['files'])!=expected:
        raise ValueError('Conditioned transfer inventory differs')
    for name,pin in transfer['files'].items():
        path=(folder/name).resolve()
        if not path.is_relative_to(folder) or path.stat().st_size!=pin['bytes'] or runtime.sha(path)!=pin['sha256']:
            raise ValueError('Conditioned transfer payload differs: '+name)
    manifest_path,manifest_sha,tensor_path=model_inputs
    if (Path(manifest_path).resolve()!=folder/'fixed/arithmetic.json' or
            Path(tensor_path).resolve()!=folder/'fixed/fixed-tensors.safetensors' or
            manifest_sha!=transfer['files']['fixed/arithmetic.json']['sha256']):
        raise ValueError('Conditioned explicit tensor inputs differ from transfer')
    _,manifest=fixed_tensor_values(*model_inputs)
    initial=folder.parent/'conditioned-import-20261109'
    if runtime.sha(initial/'transfer.json')!='f11899a8bc5f8b96080cc22b4c344568d1a2e91fd11050f0fc4fea78cb3b236d':
        raise ValueError('Original conditioned source import differs')
    initial_transfer=runtime.read(initial/'transfer.json')
    source_names=('tools/fixed.py','tools/model.py','tools/generative.py','tools/runtime.py',
                  'tools/llama_numpy_reference.py','uv.lock','pyproject.toml',
                  'model/selection.json','model/jokes.json','model/fixed.json')
    source_pins={}
    for name in source_names:
        pin=initial_transfer['files']['source/'+name];path=initial/'source'/name
        if path.stat().st_size!=pin['bytes'] or runtime.sha(path)!=pin['sha256']:
            raise ValueError('Original conditioned source bytes differ: '+name)
        source_pins[name]=pin['sha256']
    if (len(transfer['git_commit'])!=40 or not transfer['git_commit'].startswith(initial_transfer['source_commit']) or
            transfer['source_candidate_sha256']!=initial_transfer['files']['fp32/candidate.json']['sha256']):
        raise ValueError('Conditioned source candidate identity differs')
    numerical=runtime.read(folder/'fixed/results.json');final=runtime.read(folder/'fixed/final-comparison.json')
    if (numerical.get('state')!='complete' or numerical.get('accepted') is not True or
            numerical.get('source_unchanged') is not True or numerical.get('all_scales_match_original') is not True or
            numerical['arithmetic_sha256']!=manifest_sha or numerical['weights_sha256']!=manifest['images']['sha256'] or
            len(numerical['checks'])!=5 or any(c.get('all_states_and_every_prefix_cache_exact') is not True or
                not 0<=c['normalized_rmse']<=.01 for c in numerical['checks']) or
            any(v['saturated'] for v in numerical['saturation'].values()) or
            any(v['clipped'] for v in numerical['ranges'].values()) or
            final['summary']!={'samples':1000,'exact':991,'unique':40,'largest':85,'completed':1000,
                              'same_as_unbalanced':1000,'same_as_fp32':999,'saturations':0} or
            len(final['results'])!=1000):
        raise ValueError('Balanced candidate numerical/output gate differs')
    pins=dict(fixed_manifest=fixed.SELECTED_SHA256,selection_manifest=source_pins['model/selection.json'],
        conditioned_arithmetic=manifest_sha,conditioned_record=transfer['files']['fixed/converted.json']['sha256'],
        payload=manifest['images']['sha256'])
    versions={'mlx':'0.32.4','mlx-lm':'0.32.2','numpy':'2.5.4','transformers':'5.22.1'}
    worker_sha=transfer['files']['provenance/conditioned-balanced-export-20261109/worker.py']['sha256']
    cases={};reference_checks={};saturations=0
    if [(c['name'],c['positions']) for c in transfer['cases']]!=list(CONDITIONED_CASES):
        raise ValueError('Conditioned case order/lengths differ')
    for item,(name,length) in zip(transfer['cases'],CONDITIONED_CASES):
        base=folder/'goldens'/name;worker=runtime.read(base/'export-results.json');watchdog=runtime.read(base/'watchdog.json')
        payload=runtime.read(base/'goldens.json')
        if payload.get('schema')!=1 or len(payload['cases'])!=1:raise ValueError('Conditioned golden case inventory differs')
        case=payload['cases'][0]
        if (case['name']!=name or len(case['tokens'])!=length or worker['case']!=name or worker['length']!=length or
                worker['tokens']!=case['tokens'] or worker['model_pins']!=pins or worker['worker_sha256']!=worker_sha or
                worker['arithmetic_sha256']!=fixed.implementation_sha256() or worker['packages']!=versions or
                worker['git_commit']!=transfer['git_commit'] or worker['mlx_memory_limit_bytes']!=2147483648 or
                worker['timeout_seconds']!=180 or worker.get('state')!='complete' or any(worker.get(k) is not True for k in
                    ('accepted','source_unchanged','selected_pins_unchanged','all_states_integer','json_roundtrip_exact','incremental_matches_full')) or
                any(worker['source_sha256'].get(k)!=v for k,v in source_pins.items()) or
                worker['goldens']!=transfer['files']['goldens/'+name+'/goldens.json'] or worker['goldens']!=item['goldens'] or
                case['counters']!={'full':worker['full_counters'],'incremental':worker['incremental_counters']}):
            raise ValueError('Conditioned original export receipt differs: '+name)
        if (watchdog['timeout_seconds']!=180 or watchdog['exit_code']!=0 or
                not 0<=watchdog['elapsed_seconds']<=180 or any(watchdog.get(k) is not True for k in
                    ('child_reaped','child_absent','process_group_absent'))):
            raise ValueError('Conditioned worker watchdog/cleanup differs: '+name)
        prefix={'BOS':'bos','J01-first16':'j01-16','authored128':'authored128','repeated-J01-256':'repeated-j01-256'}
        texts={'encoded-fu2p2q':'fu2p2q','encoded-hello':'hello','encoded-max48':'0123456789abcdef'*3}
        expected_tokens=(transformer_prefix_tokens(prefix[name]) if name in prefix else
                         board_bos.completion_prefix(texts[name],255,encoding='hex')[1])
        tokens,arrays=mac_case_golden(case)
        if tokens!=expected_tokens:raise ValueError('Conditioned explicit input tokens differ: '+name)
        saturations+=sum(stat['saturated'] for counters in case['counters'].values() for stat in counters.values())
        cases[name]=dict(tokens=tokens,arrays=arrays,counters=case['counters']);reference_checks[name]=worker['checks']
    if saturations:raise ValueError('Conditioned reference has saturated activations')
    return cases,dict(directory=str(folder),transfer_sha256=digest,files=transfer['files'],model_pins=pins,
        arithmetic_sha256=manifest['implementation_sha256'],reference_checks=reference_checks,saturations=0,
        source_import_sha256=runtime.sha(initial/'transfer.json'),worker_sha256=worker_sha,
        numerical_gate=dict(max_normalized_rmse=max(c['normalized_rmse'] for c in numerical['checks']),
                            final_format_regression=final['summary']),
        original_environment='Verified original pinned Mac source snapshots and restricted export/supervisor sources; successful 180-second watchdog receipts; no model forward recreated on Linux',
        provenance_scope='Data/source/receipt hashes checked locally. Actual launch/environment controls and original execution are Mac-attested; per-case launch receipts were not included')


def verified_transformer_trace(path,digest,words):
    """Accept only a sealed current-RTL simulation trace with its actual inputs."""
    path=path.resolve()
    if not path.is_relative_to(runtime.RUNTIME.resolve()) or not digest or runtime.sha(path)!=digest:
        raise ValueError('RTL trace report location/hash differs')
    report=runtime.read(path);block=report.get('blocks',{}).get('transformer',{})
    if report.get('state')!='complete' or report.get('mode')!='transformer' or block.get('state')!='complete':
        raise ValueError('Expected a complete actual transformer simulation report')
    names=('fixed_scalar','mac32','qk_rope','kv_cache','frontend','attention','dense','rmsnorm','feedforward','transformer','transformer_tb')
    if set(block.get('source_sha256',{}))!=set(names):raise ValueError('RTL trace source inventory differs')
    for name,sha in block['source_sha256'].items():
        if runtime.sha(RTL/(name+'.sv'))!=sha:raise ValueError('RTL trace source is not current: '+name)
    if any(sum(c['name']==name for c in report['commands'])!=1 for name in ('compile','elaborate','simulation')) or any(
           c.get('exit_code')!=0 or c.get('child_reaped') is not True or c.get('process_group_absent') is not True or
           (c['name']=='simulation' and c['timeout_seconds']!=180) for c in report['commands']):
        raise ValueError('RTL trace simulation/cleanup receipt differs')
    work=path.parent/'transformer'
    for name in ('stages.csv','input-tokens.json','model-words.hex','tokens.hex'):
        pin=block['artifacts'][name];source=work/name
        if source.stat().st_size!=pin['bytes'] or runtime.sha(source)!=pin['sha256']:
            raise ValueError('RTL trace input/artifact hash differs: '+name)
    tokens=runtime.read(work/'input-tokens.json')
    if ([int(v,16) for v in (work/'tokens.hex').read_text().splitlines()]!=tokens or
        [int(v,16) for v in (work/'model-words.hex').read_text().splitlines()]!=words):
        raise ValueError('RTL trace actual token/model words differ')
    return tokens,work,dict(report=str(path),report_sha256=digest,source_sha256=block['source_sha256'],
                           trace=block['artifacts']['stages.csv'],inputs=block['artifacts']['input-tokens.json'])


def run_model_comparison(folder,command,fixture_dir,digest,trace_reports,vivado_bin,*,model_inputs=None):
    source_pins={p.name:runtime.sha(p) for p in RTL.glob('*.sv')}
    cases,provenance=(mac_whole_model_reference(fixture_dir,digest) if model_inputs is None else
                      mac_conditioned_reference(fixture_dir,digest,model_inputs))
    values,_=fixed_tensor_values(*(model_inputs or ()));words=transformer_model_words(values)
    if model_inputs is None:bos,derived,_=transformer_bos_reference(values)
    else:bos,derived={},{}
    available=[]
    for path,sha in trace_reports:
        available.append(verified_transformer_trace(Path(path),sha,words))
    checks={};used=set()
    for name,case in cases.items():
        matches=[i for i,(tokens,_,_) in enumerate(available) if tokens==case['tokens']]
        if len(matches)>1:raise ValueError('Duplicate saved RTL input case: '+name)
        if matches:
            index=matches[0];used.add(index);_,work,identity=available[index]
            result,_=transformer_check_trace(work/'stages.csv',case['tokens'],bos,derived,case['arrays'])
            checks[name]=dict(checks=result,saved_trace=identity)
        else:
            work=folder/name;work.mkdir()
            checks[name]=run_transformer_vivado(work,command,tokens=case['tokens'],golden=case['arrays'],
                                               waveform=False,vivado_bin=vivado_bin,model_inputs=model_inputs)
        print('Original Mac whole-model comparison exact: '+name,flush=True)
    if used!=set(range(len(available))):raise ValueError('Saved RTL trace did not match an exported case')
    counts=dict(cases=len(cases),input_positions=sum(len(c['tokens']) for c in cases.values()),
        original_state_and_cache_values_checked=sum(c['checks']['full_model_golden_values_checked'] for c in checks.values()),
        logits_including_clear_replays=sum(c['checks']['ordered_logits'] for c in checks.values()),
        original_input_logits=sum(len(c['tokens'])*320 for c in cases.values()),clear_replays=len(cases),
        all_exact=True,original_mac_model_comparison=True)
    if any(runtime.sha(RTL/name)!=sha for name,sha in source_pins.items()):
        raise ValueError('RTL source changed during original model comparison')
    print('Original Mac full-model comparison: '+str(counts),flush=True)
    return dict(state='complete',checks=counts,cases=checks,reference=provenance,source_sha256=source_pins,
        limits='Explicit teacher-forced integer reference cases plus clear-context replays. Not sampled generation, new language quality, complete board routing or physical FPGA execution')



def check_transformer_arithmetic(observed,tokens,values):
    """Independent local checks at OBSERVED inputs, never a replacement forward.

    observed is transformer_check_trace's integer-keyed step/stage/coordinate map.
    Every local oracle reads recorded RTL inputs; its calculated outputs are
    compared, never fed into a later neural stage. Cache history consists of
    observed accepted cache writes. The final step is the fresh-BOS clear replay.
    Caller must verify the selected tensor image before supplying values.
    """
    if not tokens or tokens[0]!=256 or len(tokens)>256 or any(not 0<=v<320 for v in tokens):
        raise ValueError('Invalid arithmetic-crosscheck token sequence')
    if set(observed)!=set(range(len(tokens)+1)):raise ValueError('Missing arithmetic-crosscheck request')
    shapes={'E':10240,'Q':1024,'K':1024,'V':1024,'O':1024,'gate':4096,'up':4096,'down':4096,
            'gain1':32,'gain2':32,'gain3':32,'rope':4096,'exp_table':257,'rsqrt_table':256}
    if any(name not in values or len(values[name])!=length for name,length in shapes.items()):
        raise ValueError('Arithmetic-crosscheck tensor geometry differs')
    matrix={name:[values[name][j*width:(j+1)*width] for j in range(rows)]
            for name,width,rows in (('E',32,320),('Q',32,32),('K',32,32),('V',32,32),('O',32,32))}
    counts=dict(requests=0,stage_values_checked=0,dense_dot_terms_checked=0,attention_dot_terms_checked=0,
                residual_values_checked=0,cache_transfer_values_checked=0,logit_values_checked=0,
                stage_value_counts={})
    keys=[];cache_values=[]
    lengths={name:32 for name in ('embed','norm1','q','k','v','qrot','krot','context','o','res1','norm2','down','res2','normfinal')}
    lengths.update(gate=128,up=128,silu=128,hidden=128,ff_clips=128,logits=320)
    def clip16(value):return min(32767,max(-32768,value))
    for step in range(len(tokens)+1):
        replay=step==len(tokens);position=0 if replay else step;token=256 if replay else tokens[step]
        if replay:keys=[];cache_values=[]
        stages=observed[step]
        wanted=set(lengths)|{'cache_k','cache_v','scores','exp','prob'}
        if set(stages)!=wanted:raise ValueError('Missing/extra arithmetic stage at request '+str(step))
        def vector(stage):
            count=lengths[stage]
            if set(stages[stage])!=set(range(count)):raise ValueError('Arithmetic stage coordinate coverage differs: '+stage)
            return [stages[stage][i] for i in range(count)]
        def checked(stage,expected,indices=None):
            indices=range(len(expected)) if indices is None else indices
            target=dict(zip(indices,expected))
            if stages[stage]!=target:
                bad=next((i for i,v in target.items() if stages[stage].get(i)!=v),None)
                raise ValueError('Observed stage arithmetic mismatch '+str((step,stage,bad)))
            counts['stage_values_checked']+=len(expected)
            counts['stage_value_counts'][stage]=counts['stage_value_counts'].get(stage,0)+len(expected)
        def dense_checked(stage,input_stage,name,shift,bits):
            # The input vector is the actual accepted RTL output from that stage.
            expected=dense_case('Observed '+stage,vector(input_stage),matrix[name],shift,bits)['expected']
            checked(stage,[row['result'] for row in expected])
            counts['dense_dot_terms_checked']+=len(matrix[name])*len(vector(input_stage))
        checked('embed',values['E'][token*32:(token+1)*32])
        norm1=rmsnorm_reference(vector('embed'),values['gain1'],-14,-14,-11,values['rsqrt_table'])
        checked('norm1',norm1['result'])
        for stage,name in (('q','Q'),('k','K'),('v','V')):dense_checked(stage,'norm1',name,15,16)
        coefficients=[[values['rope'][(position*8+j)*2],values['rope'][(position*8+j)*2+1]] for j in range(8)]
        rotation=rope_case('Observed RoPE',vector('q')+vector('k'),coefficients,position)
        checked('qrot',rotation['outputs'][:32]);checked('krot',rotation['outputs'][32:])
        cache_indices=range(position*32,(position+1)*32)
        checked('cache_k',vector('krot'),cache_indices);checked('cache_v',vector('v'),cache_indices)
        counts['cache_transfer_values_checked']+=64
        if len(keys)!=position or len(cache_values)!=position:raise ValueError('Observed cache sequence changed')
        keys.append([stages['cache_k'][position*32+j] for j in range(32)])
        cache_values.append([stages['cache_v'][position*32+j] for j in range(32)])
        attention=attention_oracle(vector('qrot'),keys,cache_values,values['exp_table'])
        for stage,key in (('scores','scores'),('exp','exp'),('prob','prob')):
            flat=[v for row in attention[key] for v in row]
            checked(stage,flat,[head*256+p for head in range(2) for p in range(position+1)])
        checked('context',attention['result'])
        counts['attention_dot_terms_checked']+=64*(position+1)
        dense_checked('o','context','O',16,16)
        residual1=[clip16(round(Fraction(a+4*b,4))) for a,b in zip(vector('embed'),vector('o'))]
        checked('res1',residual1);counts['residual_values_checked']+=32
        norm2=rmsnorm_reference(vector('res1'),values['gain2'],-12,-14,-11,values['rsqrt_table'])
        checked('norm2',norm2['result'])
        # FF is independently checked as a block using the recorded norm2 input.
        ff=ff_oracle(vector('norm2'),values)
        for stage,key in (('gate','gate'),('up','up'),('silu','silu'),('hidden','hidden'),('ff_clips','element_clips'),('down','outputs')):
            checked(stage,ff[key])
        counts['dense_dot_terms_checked']+=128*32*2+32*128
        residual2=[clip16(round(Fraction(a+4*b,4))) for a,b in zip(vector('res1'),vector('down'))]
        checked('res2',residual2);counts['residual_values_checked']+=32
        normfinal=rmsnorm_reference(vector('res2'),values['gain3'],-10,-13,-10,values['rsqrt_table'])
        checked('normfinal',normfinal['result'])
        dense_checked('logits','normfinal','E',8,32);counts['logit_values_checked']+=320
        counts['requests']+=1
    counts.update(all_exact=True,clear_context_replays=1,
        evidence='Independent per-stage integer/Fraction arithmetic at observed RTL inputs, using verified selected weights/tables',
        original_mac_full_model_comparison='pending; this is not a replacement full-model forward or a new model fixture')
    return counts


def run_transformer_vivado(folder,command,tokens=None,golden=None,waveform=True,vivado_bin=Path('/home/admin/amd/2025.2/Vivado/bin'),*,model_inputs=None):
    """BOS structural smoke by default; golden arrays must come from original Mac export.

    tokens: explicit teacher-forced input token list, beginning256, maximum256.
    golden: optional list of dictionaries stage->flat integer values per step.
    Scores/exp/prob use sparse integer keys head*256+position (rather than padding
    or masking), all other stages use coordinate-order lists. Only pass arrays
    whose original export/provenance/hash was verified by the caller.
    """
    tokens=[256] if tokens is None else tokens
    if not tokens or tokens[0]!=256 or len(tokens)>256 or any(not 0<=t<320 for t in tokens):raise ValueError('Invalid decoder input tokens')
    if golden is not None and (len(golden)!=len(tokens) or any(len(g['logits'])!=320 for g in golden)):
        raise ValueError('Original golden logits geometry differs')
    if model_inputs is not None:
        if golden is None:
            raise ValueError('Imported model simulation requires fresh full-model goldens')
        values,manifest=fixed_tensor_values(*model_inputs)
        bos,derived={},{}
        provenance=dict(reference='Fresh full-model goldens for explicitly pinned tensor inputs',
            fixed_manifest_sha256=runtime.sha(Path(model_inputs[0])),
            fixed_payload_sha256=manifest['images']['sha256'],
            arithmetic_sha256=manifest['implementation_sha256'])
    else:
        values,manifest=fixed_tensor_values();bos,derived,provenance=transformer_bos_reference(values)
    work=folder/'transformer';work.mkdir();runtime.save(work/'input-tokens.json',tokens)
    def hexfile(name,values,width=32):
        path=work/(name+'.hex');path.write_text(''.join(f'{v&((1<<width)-1):0{width//4}x}\n' for v in values));return str(path)
    args=dict(STEPS=str(len(tokens)),MODEL=hexfile('model-words',transformer_model_words(values)),
              TOKENS=hexfile('tokens',tokens,16),CSV=str(work/'stages.csv'))
    if waveform:args['VCD']=str(work/'waves.vcd')
    if golden is not None:args['ANSWERS']=hexfile('original-golden-logits',(v for g in golden for v in g['logits']))
    names=('fixed_scalar','mac32','qk_rope','kv_cache','frontend','attention','dense','rmsnorm','feedforward','transformer','transformer_tb')
    tools=vivado_bin
    command(work,'compile',[tools/'xvlog','--sv',*[RTL/(name+'.sv') for name in names]])
    command(work,'elaborate',[tools/'xelab','work.transformer_tb','--debug','typical','--mt','2','--snapshot','transformer_sim'])
    output=command(work,'simulation',[tools/'xsim','transformer_sim','--runall','--onerror','quit','--onfinish','quit',
        *[v for k,value in args.items() for v in ('--testplusarg',k+'='+value)]])
    wanted=f'PASS transformer requests={len(tokens)+1} logits={(len(tokens)+1)*320} golden_logits={int(golden is not None)} clear_replays=1'
    if wanted not in output:raise ValueError('Missing full-core testbench receipt')
    checks,observed=transformer_check_trace(work/'stages.csv',tokens,bos,derived,golden)
    checks['independent_arithmetic']=check_transformer_arithmetic(observed,tokens,values)
    runtime.save(work/'observed-stages.json',{str(step):stages for step,stages in observed.items()})
    print('Full decoder: '+str(checks),flush=True)
    return dict(state='complete',checks=checks,provenance=provenance,
        evidence=('Explicitly pinned imported weights and complete fresh full-model goldens; independent observed-stage arithmetic checked'
                  if model_inputs is not None else
                  'Pinned real weights/tables and BOS plus explicit teacher-forced tokens; archived boundaries checked; fresh full-model golden comparison '+('pending' if golden is None else 'provided')),
        source_sha256={name:runtime.sha(RTL/(name+'.sv')) for name in names},
        artifacts={p.name:dict(bytes=p.stat().st_size,sha256=runtime.sha(p)) for p in work.iterdir() if p.suffix in ('.hex','.json','.csv','.vcd')},
        limits='Complete one-token RTL datapath simulation; host sampling remains external. No physical fit, bitstream, FPGA execution, speed or energy claim')


def transformer_prefix_tokens(name):
    if name=='bos':return [256]
    selection=runtime.read(runtime.MODEL/'selection.json');path=runtime.MODEL/'jokes.json'
    if runtime.sha(path)!=selection['files_sha256']['jokes.json']:raise ValueError('Frozen target snapshot changed')
    rows=runtime.read(path);target=rows[0]
    if target['id']!='J01':raise ValueError('Frozen prefix target differs')
    tokens=[256,*target['text'].encode('utf-8'),257]
    if name=='repeated-j01-256':return (tokens*256)[:256]
    if name=='authored128':
        tokens=max(([256,*row['text'].encode('utf-8'),257] for row in rows),key=len)
        if len(tokens)<128:raise ValueError('Longest frozen authored sequence is shorter than128 tokens')
        return tokens[:128]
    return tokens[:3 if name=='j01-3' else 16]


def pack_model_words(folder,*,model_inputs=None):
    """Offline transport package only; the source tensor image is verified first."""
    import struct
    values,manifest=fixed_tensor_values(*(model_inputs or ()));words=transformer_model_words(values)
    data=struct.pack('<'+str(len(words))+'I',*words)
    path=folder/'model-words.bin';path.write_bytes(data)
    pin=dict(bytes=len(data),sha256=runtime.sha(path),words=len(words),word_format='little-endian unsigned32')
    banks=[dict(bank=i,name=name,words=count) for i,name,count in
           ((0,'E',10240),(1,'Q',1024),(2,'K',1024),(3,'V',1024),(4,'O',1024),
            (5,'gate',4096),(6,'up',4096),(7,'down',4096),(8,'gain1',32),(9,'gain2',32),
            (10,'gain3',32),(11,'rope_cosine_low16_sine_high16',2048),(13,'exp_table',257),(14,'rsqrt_table',256))]
    package=dict(schema=1,packed_image=pin,banks=banks,parameter_count=26720,
        fixed_manifest_sha256=runtime.sha(Path(model_inputs[0]) if model_inputs else runtime.MODEL/'fixed.json'),
        fixed_tensor_image_sha256=manifest['images']['sha256'],
        arithmetic_implementation_sha256=manifest['implementation_sha256'],
        limits='Verified model bytes for later offline host loading; no board access or model inference')
    runtime.save(folder/'model-package.json',package)
    print('Packed model image: '+str(path)+' '+str(pin),flush=True)
    return dict(state='complete',package=package)



def axi_check_trace(path):
    """Independent AXI pairing/backpressure scoreboard and synthetic-stub action checks."""
    aw=None;wd=None;ar=None;active_b=None;active_r=None;bank=0;address=0;last_token=None
    expected=dict(core_weights=0,core_tokens=0,core_reads=0,core_clears=0,core_resets=0)
    counts=dict(cycles_checked=0,write_responses=0,read_responses=0,write_errors=0,read_errors=0,
                aw_first=0,w_first=0,simultaneous_aw_w=0,read_stall_edges=0,write_stall_edges=0,
                model_words_accepted=0,tokens_accepted=0,logits_consumed=0,context_clears=0)
    prev=None;prev_consume=False;prev_soft=False;prev_b_accept=False;prev_r_accept=False;last_clock=-1
    with path.open() as source:
        for raw in csv.DictReader(source):
            if any('x' in value.lower() or 'z' in value.lower() for value in raw.values()) and raw['resetn']!='0':
                raise ValueError('Unknown AXI value outside reset')
            row={key:(0 if 'x' in value.lower() or 'z' in value.lower() else int(value)) for key,value in raw.items()}
            if row['cycle']<=last_clock:raise ValueError('AXI clock order changed')
            last_clock=row['cycle'];counts['cycles_checked']+=1
            if prev_consume:expected['core_reads']+=1;counts['logits_consumed']+=1
            if prev is not None and (not prev['resetn'] or prev_soft):expected['core_resets']+=1;last_token=None
            if prev_b_accept:active_b=None
            if prev_r_accept:active_r=None
            soft=False;consume=False;b_accept=False;r_accept=False
            if not row['resetn']:
                aw=None;wd=None;ar=None;active_b=None;active_r=None;bank=0;address=0
            else:
                if prev is not None and prev['resetn']:
                    if prev['bvalid'] and not prev['bready'] and (not row['bvalid'] or row['bresp']!=prev['bresp']):
                        raise ValueError('AXI B response changed under backpressure')
                    if prev['rvalid'] and not prev['rready'] and (not row['rvalid'] or (row['rresp'],row['rdata'])!=(prev['rresp'],prev['rdata'])):
                        raise ValueError('AXI R response changed under backpressure')
                if row['bvalid'] and active_b is None:
                    if aw is None or wd is None:raise ValueError('AXI write response lacked independently captured AW/W')
                    register=aw;data,strobe=wd;aw=None;wd=None;response=row['bresp'];active_b=(register,data,strobe,response)
                    static_bad=(register&3)!=0 or strobe!=15 or register not in (4,8,12,16,28)
                    static_bad |= register==4 and (data>>4!=0 or (data&15) in (12,15))
                    static_bad |= register==8 and data>>16!=0
                    static_bad |= register==16 and (data>>9!=0 or (data&511)>=320)
                    static_bad |= register==28 and data not in (0,1,2)
                    if response not in (0,2) or (static_bad and response!=2):raise ValueError('AXI invalid write did not return SLVERR')
                    if response==0:
                        if register==4:bank=data
                        elif register==8:address=data
                        elif register==12:
                            address=(address+1)&65535;expected['core_weights']+=1;counts['model_words_accepted']+=1
                        elif register==16:
                            last_token=data;expected['core_tokens']+=1;counts['tokens_accepted']+=1
                        elif register==28 and data==1:expected['core_clears']+=1;counts['context_clears']+=1
                        elif register==28 and data==2:soft=True;bank=0;address=0
                    elif not static_bad and register in (4,8):raise ValueError('AXI valid register write was refused')
                if row['rvalid'] and active_r is None:
                    if ar is None:raise ValueError('AXI read response lacked captured AR')
                    register,snapshot=ar;ar=None;response=row['rresp'];data=row['rdata'];active_r=(register,response,data)
                    if response not in (0,2):raise ValueError('Invalid AXI read response code')
                    static_bad=(register&3)!=0 or register not in (0,4,8,20,24,32)
                    if static_bad or (register==24 and snapshot['error']):
                        if response!=2 or data!=0:raise ValueError('Invalid/faulted AXI read exposed data')
                    elif register!=24:
                        if response!=0:raise ValueError('Valid AXI register read refused')
                        if register==0:
                            if data!=snapshot['value']:raise ValueError('AXI status/capacity snapshot differs')
                        elif register==32:
                            if data!=snapshot['value'] or data>256:raise ValueError('Invalid AXI context count snapshot')
                        elif data!=snapshot['value']:raise ValueError('AXI register/peek snapshot differs')
                    elif response==0:
                        if snapshot['token'] is None:raise ValueError('AXI logit read preceded token')
                        wanted=(snapshot['token']*65536+snapshot['index']-1000)&0xffffffff
                        if data!=wanted:raise ValueError('Synthetic AXI logit snapshot differs')
                    elif data!=0:raise ValueError('Failed AXI data read returned nonzero data')
                if row['awready'] and (aw is not None or row['bvalid']):raise ValueError('AXI accepted second outstanding AW')
                if row['wready'] and (wd is not None or row['bvalid']):raise ValueError('AXI accepted second outstanding W')
                if row['arready'] and (ar is not None or row['rvalid']):raise ValueError('AXI accepted second outstanding AR')
                aw_fire=bool(row['awvalid'] and row['awready']);w_fire=bool(row['wvalid'] and row['wready'])
                if aw_fire and w_fire:counts['simultaneous_aw_w']+=1
                elif aw_fire and wd is None:counts['aw_first']+=1
                elif w_fire and aw is None:counts['w_first']+=1
                if aw_fire:aw=row['awaddr']
                if w_fire:wd=(row['wdata'],row['wstrb'])
                if row['arvalid'] and row['arready']:
                    register=row['araddr'];snapshot=dict(error=row['core_error'],index=row['core_index'],token=last_token)
                    if register in (4,8,20):snapshot['value']={4:bank,8:address,20:row['core_index']}[register]
                    elif register==32:snapshot['value']=row['core_context']
                    elif register==0:
                        capacity=int(bool(row['core_configured'] and not row['core_busy'] and not row['core_error'] and row['core_context']<256 and not row['soft_reset']))
                        load_capacity=int(not row['core_configured'] and not row['core_busy'] and not row['soft_reset'])
                        snapshot['value']=row['core_configured']|(row['core_busy']<<1)|(row['core_error']<<2)|(row['core_saturated']<<3)|(row['core_logit_valid']<<4)|(capacity<<5)|(load_capacity<<6)
                    ar=(register,snapshot)
                if row['bvalid']:
                    counts['write_stall_edges']+=int(not row['bready'])
                    if row['bready']:
                        b_accept=True;counts['write_responses']+=1;counts['write_errors']+=int(row['bresp']==2)
                if row['rvalid']:
                    counts['read_stall_edges']+=int(not row['rready'])
                    if row['rready']:
                        r_accept=True;counts['read_responses']+=1;counts['read_errors']+=int(row['rresp']==2)
                        consume=active_r[0]==24 and row['rresp']==0
            if any(row[key]!=value for key,value in expected.items()):
                raise ValueError('AXI command/data consumption count mismatch at clock '+str(row['cycle']))
            prev=row;prev_soft=soft;prev_consume=consume;prev_b_accept=b_accept;prev_r_accept=r_accept
    if aw is not None or wd is not None or ar is not None or (active_b is not None and not prev_b_accept) or (active_r is not None and not prev_r_accept):
        raise ValueError('Missing accepted AXI response')
    if not counts['aw_first'] or not counts['w_first'] or not counts['simultaneous_aw_w'] or counts['logits_consumed']!=1280:
        raise ValueError('Missing AXI order/logit-consumption coverage')
    counts.update(protocol_only=True,all_exact=True)
    return counts


def run_axi_vivado(folder,command):
    """Fast protocol test uses a SYNTHETIC stub; real neural wrapper is elaborated separately."""
    tools=Path('/home/admin/amd/2025.2/Vivado/bin');work=folder/'axi-protocol';work.mkdir()
    command(work,'compile',[tools/'xvlog','--sv',RTL/'axi_transformer.sv',RTL/'axi_transformer_tb.sv'])
    command(work,'elaborate',[tools/'xelab','work.axi_transformer_tb','--debug','typical','--mt','2','--snapshot','axi_sim'])
    output=command(work,'simulation',[tools/'xsim','axi_sim','--runall','--onerror','quit','--onfinish','quit',
        '--testplusarg','CSV='+str(work/'cycles.csv'),'--testplusarg','VCD='+str(work/'waves.vcd')])
    if 'PASS axi protocol_only=1' not in output:raise ValueError('Missing synthetic AXI protocol receipt')
    checks=axi_check_trace(work/'cycles.csv')
    actual=folder/'axi-real-core';actual.mkdir()
    names=('fixed_scalar','mac32','qk_rope','kv_cache','frontend','attention','dense','rmsnorm','feedforward','transformer','axi_transformer')
    command(actual,'compile',[tools/'xvlog','--sv',*[RTL/(name+'.sv') for name in names]])
    command(actual,'elaborate',[tools/'xelab','work.axi_transformer','--debug','typical','--mt','2','--snapshot','axi_real_core'])
    report=dict(state='complete',checks=checks,evidence='Synthetic bus protocol only; separately compiled/elaborated real neural core wrapper',
        real_core_compiled_and_elaborated=True,
        source_sha256={name:runtime.sha(RTL/(name+'.sv')) for name in (*names,'axi_transformer_tb')},
        artifacts={p.name:dict(bytes=p.stat().st_size,sha256=runtime.sha(p)) for p in work.iterdir() if p.suffix in ('.csv','.vcd')},
        limits='No physical AXI interconnect/Arm CPU/board image test, no neural comparison through this bus test, no synthesis/bitstream')
    print('AXI protocol: '+str(checks),flush=True);print('Real-core AXI wrapper elaboration passed',flush=True)
    return report



def axi_core_check_events(path,words,expected_scores):
    """Verify accepted real-bus transactions, selected parameter order and returned score bits."""
    lengths={0:10240,1:1024,2:1024,3:1024,4:1024,5:4096,6:4096,7:4096,8:32,9:32,10:32,11:2048,13:257,14:256}
    expected_locations=[(bank,address) for bank,count in lengths.items() for address in range(count)]
    aw=None;wd=None;ar=None;bank=0;address=0;loaded=0;context=0;busy=False;last_cycle=-1
    counts=dict(events_checked=0,model_words_checked=0,write_responses=0,read_responses=0,status_reads=0,
                successful_tokens=0,rejected_commands=0,context_clears=0,logits_checked=0)
    returned=[];seen={0:0,1:0}
    with path.open() as source:
        for raw in csv.DictReader(source):
            row={k:int(v) if k!='kind' else v for k,v in raw.items()};kind=row['kind'];request=row['request']
            if row['cycle']<last_cycle:raise ValueError('Real AXI event clock order changed')
            last_cycle=row['cycle'];counts['events_checked']+=1
            if kind=='AW':
                if aw is not None:raise ValueError('Multiple real AXI AW outstanding')
                aw=row['address']
            elif kind=='W':
                if wd is not None:raise ValueError('Multiple real AXI W outstanding')
                wd=(row['data'],row['response']) # response field marks partial write strobe in W events.
            elif kind=='B':
                if aw is None or wd is None:raise ValueError('Real AXI B lacked AW/W pairing')
                register=aw;data,partial=wd;aw=None;wd=None;counts['write_responses']+=1
                if row['response']==2:
                    counts['rejected_commands']+=1
                    if not (register==16 and data==0 or register==12 and (partial or address==1 and loaded==0)):
                        raise ValueError('Unexpected real AXI rejected command')
                    continue
                if row['response']!=0 or partial:raise ValueError('Invalid real AXI successful B response')
                if register==4:bank=data
                elif register==8:address=data
                elif register==12:
                    if loaded>=len(words) or (bank,address)!=expected_locations[loaded] or data!=words[loaded]:
                        raise ValueError('Selected model word/order changed in actual AXI transport')
                    loaded+=1;address+=1;counts['model_words_checked']+=1
                elif register==16:
                    if data!=256 or busy or loaded!=len(words) or context!=0:raise ValueError('Invalid real AXI BOS acceptance')
                    busy=True;context=1;counts['successful_tokens']+=1
                elif register==28:
                    if data!=1 or busy:raise ValueError('Invalid real AXI context clear')
                    context=0;counts['context_clears']+=1
                else:raise ValueError('Unexpected successful real AXI write register')
            elif kind=='AR':
                if ar is not None:raise ValueError('Multiple real AXI AR outstanding')
                register=row['address'];snapshot=dict(bank=bank,address=address,context=context,busy=busy,configured=int(loaded==len(words)))
                ar=(register,request,snapshot)
            elif kind=='R':
                if ar is None:raise ValueError('Real AXI R lacked AR pairing')
                register,owner,snapshot=ar;ar=None;counts['read_responses']+=1
                if owner!=request:raise ValueError('Real AXI read owner changed during response')
                if row['response']==2:
                    if register!=24 or busy or row['data']!=0:raise ValueError('Unexpected real AXI failed read')
                    continue
                if row['response']!=0:raise ValueError('Invalid real AXI read response')
                data=row['data']
                if register==0:
                    counts['status_reads']+=1
                    fixed=snapshot['configured']|(int(snapshot['busy'])<<1)
                    fixed|=int(snapshot['configured'] and not snapshot['busy'] and snapshot['context']<256)<<5
                    fixed|=int(not snapshot['configured'] and not snapshot['busy'])<<6
                    if (data&~16)!=fixed or (not snapshot['busy'] and data&16):raise ValueError('Actual neural AXI status/capacity differs')
                elif register==8:
                    if data!=snapshot['address']:raise ValueError('Actual neural AXI auto-increment address differs')
                elif register==32:
                    if data!=snapshot['context']:raise ValueError('Actual neural AXI context count differs')
                elif register==20:
                    if request not in seen or data!=seen[request]:raise ValueError('Actual neural AXI index peek changed order')
                elif register==24:
                    if request not in seen or not busy or seen[request]>=320:raise ValueError('Unexpected actual neural logit consumption')
                    index=seen[request];value=data-(1<<32) if data&(1<<31) else data
                    if value!=expected_scores[index]:raise ValueError('Actual AXI score differs from prior actual-RTL baseline')
                    returned.append((request,index,value));seen[request]+=1;counts['logits_checked']+=1
                    if seen[request]==320:busy=False
                else:raise ValueError('Unexpected real AXI read register')
            else:raise ValueError('Invalid actual AXI event kind')
    if aw is not None or wd is not None or ar is not None or loaded!=29281 or seen!={0:320,1:320} or counts['context_clears']!=1:
        raise ValueError('Incomplete selected-model actual AXI transaction coverage')
    counts.update(requests=2,transport_consistency_exact=True,original_mac_full_model_golden_comparison=False)
    return counts,returned


def axi_core_check_returns(path,expected_scores,bus_returned):
    with path.open() as source:rows=[tuple(int(row[k]) for k in ('request','index','score')) for row in csv.DictReader(source)]
    expected=[(request,index,value) for request in range(2) for index,value in enumerate(expected_scores)]
    if rows!=expected or rows!=bus_returned:raise ValueError('Actual AXI returned score trace differs')
    return len(rows)


def run_axi_core_vivado(folder,command):
    """Real neural core through real AXI, compared with a preceding direct actual-RTL run."""
    baseline_folder=folder/'axi-core-baseline';baseline_folder.mkdir()
    baseline=run_transformer_vivado(baseline_folder,command,tokens=[256])
    baseline_path=baseline_folder/'transformer/observed-stages.json'
    if runtime.sha(baseline_path)!=baseline['artifacts']['observed-stages.json']['sha256']:
        raise ValueError('Actual RTL baseline trace hash changed')
    observed=runtime.read(baseline_path);scores=[observed['0']['logits'][str(i)] for i in range(320)]
    values,manifest=fixed_tensor_values();words=transformer_model_words(values)
    work=folder/'axi-real-neural-core';work.mkdir()
    def hexfile(name,values,width=32):
        path=work/(name+'.hex');path.write_text(''.join(f'{v&((1<<width)-1):0{width//4}x}\n' for v in values));return str(path)
    args=dict(MODEL=hexfile('selected-model-words',words),SCORES=hexfile('prior-actual-rtl-bos-scores',scores),
        CSV=str(work/'bus-events.csv'),RETURNS=str(work/'returned-scores.csv'),VCD=str(work/'waves.vcd'))
    names=('fixed_scalar','mac32','qk_rope','kv_cache','frontend','attention','dense','rmsnorm','feedforward','transformer','axi_transformer','axi_transformer_core_tb')
    tools=Path('/home/admin/amd/2025.2/Vivado/bin')
    command(work,'compile',[tools/'xvlog','--sv',*[RTL/(name+'.sv') for name in names]])
    command(work,'elaborate',[tools/'xelab','work.axi_transformer_core_tb','--debug','typical','--mt','2','--snapshot','axi_neural_sim'])
    output=command(work,'simulation',[tools/'xsim','axi_neural_sim','--runall','--onerror','quit','--onfinish','quit',
        *[v for k,value in args.items() for v in ('--testplusarg',k+'='+value)]])
    if 'PASS axi_real_core requests=2 model_words=29281 logits=640' not in output:
        raise ValueError('Missing actual neural AXI success receipt')
    checks,returned=axi_core_check_events(work/'bus-events.csv',words,scores)
    checks['returned_trace_values_checked']=axi_core_check_returns(work/'returned-scores.csv',scores,returned)
    print('Real neural AXI: '+str(checks),flush=True)
    return dict(state='complete',checks=checks,direct_actual_rtl_baseline=baseline,
        evidence='Pinned real model weights/tables and real BOS neural calculations through real AXI; scores match preceding direct actual RTL trace',
        fixed_payload_sha256=manifest['images']['sha256'],
        source_sha256={name:runtime.sha(RTL/(name+'.sv')) for name in names},
        artifacts={p.name:dict(bytes=p.stat().st_size,sha256=runtime.sha(p)) for p in work.iterdir() if p.suffix in ('.hex','.json','.csv','.vcd')},
        limits='Transport consistency across two actual RTL paths; not independent original Mac full-model golden proof. No C driver, Arm CPU, physical AXI interconnect, board image, bitstream or hardware performance result')


def synthesis_utilization(path):
    names={'CLB LUTs*':'luts','CLB LUTs':'luts','CLB Registers':'registers','Block RAM Tile':'bram_tiles',
           'RAMB36/FIFO*':'ramb36','RAMB18':'ramb18','DSPs':'dsps','URAM':'uram'}
    result={}
    for line in path.read_text().splitlines():
        fields=[field.strip() for field in line.split('|')]
        if len(fields)>6 and fields[1] in names:
            result[names[fields[1]]]=dict(used=float(fields[2]),available=int(fields[5]),percent=float(fields[6]))
    if set(result)!=set(names.values()):raise ValueError('Incomplete synthesis utilization report')
    return result


def run_host_validation(folder,command):
    """Portable transport API tests with a synthetic MMIO device, never a board."""
    sources=[runtime.PROJECT/'tools'/name for name in ('host.c','host.h','host_tb.c')]
    compiler=Path('/usr/bin/cc')
    command(folder,'host-compiler-version',[compiler,'--version'])
    flags=['-std=c11','-Wall','-Wextra','-Werror','-pedantic','-O2']
    wanted='PASS host mock suites=6 model_words=29281 vocabulary=320 context_limit=256'
    for name,extra in (('normal',[]),('sanitized',['-fsanitize=address,undefined','-fno-omit-frame-pointer','-g'])):
        binary=folder/('host-tests-'+name)
        command(folder,'host-compile-'+name,[compiler,*flags,*extra,sources[0],sources[2],'-o',binary])
        output=command(folder,'host-tests-'+name,[binary])
        if wanted not in output:raise ValueError('Missing host MMIO mock success receipt')
    checks=dict(mock_suites=6,all_exact=True,context_frames=256,logit_values=81920,
                compiler_warnings_fatal=True,address_sanitizer=True,undefined_behavior_sanitizer=True)
    print('Host transport API: '+str(checks),flush=True)
    return dict(state='complete',checks=checks,source_sha256={str(p.relative_to(runtime.PROJECT)):runtime.sha(p) for p in sources},
                compiler_sha256=runtime.sha(compiler.resolve()),
                limits='Synthetic MMIO callback tests only. No physical mapping, board access, sampling or neural inference')


def run_synthesis_vivado(folder,command,top,vivado_bin=Path('/home/admin/amd/2025.2/Vivado/bin')):
    """Component/full-core OOC mapping only; no place/route or programming file."""
    dependencies={
        'fixed_scalar':['fixed_scalar'],
        'rmsnorm':['fixed_scalar','rmsnorm'],
        'dense':['dense'],
        'attention':['fixed_scalar','attention'],
        'frontend':['mac32','qk_rope','kv_cache','frontend'],
        'feedforward':['fixed_scalar','dense','feedforward'],
        'transformer':['fixed_scalar','rmsnorm','mac32','qk_rope','kv_cache','frontend','attention','dense','feedforward','transformer']}
    sources=[RTL/(name+'.sv') for name in dependencies[top]]
    source_pins={str(p.relative_to(runtime.PROJECT)):runtime.sha(p) for p in sources}
    work=folder/top;work.mkdir();script=work/'synth.tcl'
    lines=['set_param general.maxThreads 2']
    lines+=['read_verilog -sv {'+str(path)+'}' for path in sources]
    generic=' -generic {INPUTS=32 OUTPUTS=320 SHIFT=8 RESULT_BITS=32}' if top=='dense' else ''
    hierarchy=' -flatten_hierarchy none' if top=='transformer' else ''
    lines+=['synth_design -top '+top+' -part xck26-sfvc784-2LV-c -mode out_of_context'+generic+hierarchy,
            'report_utilization -file utilization.rpt',
            'report_utilization -hierarchical -file utilization-hierarchical.rpt',
            'set bb [get_cells -hier -quiet -filter {IS_BLACKBOX == 1}]',
            'set lt [get_cells -hier -quiet -filter {REF_NAME =~ LD*}]',
            'puts "BLACKBOX_COUNT [llength $bb]"','puts "LATCH_COUNT [llength $lt]"',
            'if {[llength $bb] || [llength $lt]} {error {Unexpected black box or latch}}',
            'write_checkpoint -force synthesized.dcp','puts {PASS SYNTHESIS '+top+'}','exit']
    script.write_text('\n'.join(lines)+'\n')
    output=command(work,'synthesis',[vivado_bin/'vivado','-mode','batch','-notrace','-source',script])
    if 'PASS SYNTHESIS '+top not in output:raise ValueError('Missing synthesis receipt')
    if 'BLACKBOX_COUNT 0' not in output or 'LATCH_COUNT 0' not in output:raise ValueError('Synthesis left an unsupported cell')
    warnings=[line for line in output.splitlines() if line.startswith('WARNING:')]
    timing=work/'timing.tcl'
    timing.write_text('set_param general.maxThreads 2\nopen_checkpoint {synthesized.dcp}\n'
                      'create_clock -name clk -period 10 [get_ports clk]\n'
                      'report_timing_summary -file timing.rpt\nputs {PASS UNPLACED TIMING REPORT}\nexit\n')
    timing_output=command(work,'synthesis-timing',[vivado_bin/'vivado',
                          '-mode','batch','-notrace','-source',timing])
    if 'PASS UNPLACED TIMING REPORT' not in timing_output:raise ValueError('Missing unplaced timing receipt')
    warnings += [line for line in timing_output.splitlines() if line.startswith('WARNING:')]
    if any(runtime.sha(runtime.PROJECT/name)!=sha for name,sha in source_pins.items()):
        raise ValueError('RTL source changed during synthesis; refusing checkpoint provenance')
    return dict(state='complete',top=top,target='xck26-sfvc784-2LV-c',warnings=warnings,
        utilization=synthesis_utilization(work/'utilization.rpt'),
        source_sha256=source_pins,
        artifacts={p.name:dict(bytes=p.stat().st_size,sha256=runtime.sha(p)) for p in work.iterdir()
                   if p.suffix in ('.rpt','.tcl','.dcp')},
        limits='Out-of-context synthesis only. No place/route, routed timing, programming file or board measurement')


def implementation_checkpoint(path,digest):
    """Accept only a sealed successful full-core synthesis of the current RTL."""
    path=path.resolve()
    if not path.is_relative_to(runtime.RUNTIME.resolve()) or not digest or runtime.sha(path)!=digest:
        raise ValueError('Implementation synthesis report location/hash differs')
    report=runtime.read(path)
    block=report.get('blocks',{}).get('transformer',{})
    if (report.get('state')!='complete' or report.get('mode')!='synthesis' or
        block.get('state')!='complete' or block.get('top')!='transformer' or
        block.get('target')!='xck26-sfvc784-2LV-c'):
        raise ValueError('Implementation requires successful matching full-core synthesis')
    expected={'rtl/'+name+'.sv' for name in ('fixed_scalar','rmsnorm','mac32','qk_rope',
              'kv_cache','frontend','attention','dense','feedforward','transformer')}
    if set(block.get('source_sha256',{}))!=expected:
        raise ValueError('Implementation source inventory differs')
    for name,sha in block['source_sha256'].items():
        if runtime.sha(runtime.PROJECT/name)!=sha:
            raise ValueError('Implementation RTL differs from synthesized source: '+name)
    checkpoint=path.parent/'transformer/synthesized.dcp'
    pin=block['artifacts']['synthesized.dcp']
    if checkpoint.stat().st_size!=pin['bytes'] or runtime.sha(checkpoint)!=pin['sha256']:
        raise ValueError('Implementation checkpoint bytes/hash differ')
    return checkpoint,dict(report=str(path),report_sha256=digest,checkpoint_sha256=pin['sha256'],
                           source_sha256=block['source_sha256'],vendor_wrapper_sha256=report['vendor_wrapper_sha256'])


def run_board_prep_vivado(folder,command,vivado_bin,clock_mhz=100):
    """Validate a proposed PS/AXI shell without generating or loading an image."""
    script=runtime.PROJECT/'tools/kv260-shell.tcl'
    sources=[script,*[RTL/(name+'.sv') for name in ('fixed_scalar','mac32','qk_rope','kv_cache',
                'frontend','attention','dense','rmsnorm','feedforward','transformer','axi_transformer')]]
    source_pins={str(p.relative_to(runtime.PROJECT)):runtime.sha(p) for p in sources}
    output=command(folder,'board-prep',[vivado_bin/'vivado','-mode','batch','-notrace','-source',script,
                   '-nojournal','-log',folder/'vivado.log','-tclargs',folder,str(clock_mhz)])
    if 'PASS LOGICAL_PS_AXI_CANDIDATE_ONLY' not in output or 'NOT_A_BOARD_IMAGE_OR_BITSTREAM' not in output:
        raise ValueError('Missing logical-only board candidate receipt')
    if any(runtime.sha(runtime.PROJECT/name)!=sha for name,sha in source_pins.items()):
        raise ValueError('Board candidate source changed during validation')
    properties={};pins=[]
    for line in output.splitlines():
        if line.startswith('CANDIDATE_PIN='):
            sha,path=line.split('=',1)[1].split(' ',1);pins.append(dict(path=path,sha256=sha))
        elif line.startswith('CANDIDATE_'):
            name,value=line.split('=',1)
            if name in properties:raise ValueError('Duplicate board candidate property')
            properties[name]=value
    expected=dict(CANDIDATE_BOARD_PART='xilinx.com:kv260_som:part0:1.4',
        CANDIDATE_PART='xck26-sfvc784-2LV-c',CANDIDATE_PROPOSED_CLOCK_MHZ=str(clock_mhz),
        CANDIDATE_PROPOSED_MMIO_BASE='0xA0000000',CANDIDATE_PROPOSED_MMIO_RANGE='0x100')
    if (len(pins)!=2 or any(properties.get(name)!=value for name,value in expected.items()) or
        not clock_mhz*990000<int(properties['CANDIDATE_DERIVED_CLOCK_HZ'])<=clock_mhz*1000000):
        raise ValueError('Logical board candidate identity/clock/address differs')
    artifacts=[p for p in folder.rglob('*') if p.is_file() and
               (p.suffix in ('.bd','.xpr') or p.name in ('candidate-properties.txt',
                'validated-candidate-ps-axi.tcl','kv260_axi_bridge.v'))]
    print('Logical board candidate only: '+str(properties),flush=True)
    return dict(state='complete',logical_design_validated=True,properties=properties,installed_pins=pins,
        source_sha256=source_pins,
        warnings=[line for line in output.splitlines() if line.startswith('WARNING:')],
        artifacts={str(p.relative_to(folder)):dict(bytes=p.stat().st_size,sha256=runtime.sha(p)) for p in artifacts},
        limits='Candidate PS/AXI block design only; actual board firmware/OS/device-tree/MMIO compatibility, clock measurement, Arm adapter, synthesis/route, image generation and board execution remain unverified')


def verified_model_gate(path,digest):
    path=path.resolve()
    if not path.is_relative_to(runtime.RUNTIME.resolve()) or not digest or runtime.sha(path)!=digest:
        raise ValueError('Numerical gate report location/hash differs')
    report=runtime.read(path);block=report.get('blocks',{}).get('model-compare',{})
    if (report.get('state')!='complete' or report.get('accepted') is not True or report.get('mode')!='model-compare' or
        block.get('state')!='complete' or block.get('checks',{}).get('original_mac_model_comparison') is not True or
        block['checks'].get('all_exact') is not True or block['checks'].get('cases')!=4):
        raise ValueError('Full candidate build requires an accepted original Mac numerical comparison')
    for name in ('fixed_scalar','mac32','qk_rope','kv_cache','frontend','attention','dense','rmsnorm','feedforward','transformer','axi_transformer'):
        if runtime.sha(RTL/(name+'.sv'))!=block['source_sha256'].get(name+'.sv'):
            raise ValueError('Candidate RTL differs from numerical gate: '+name)
    import fixed
    pins=block['reference']['model_pins']
    if (pins['fixed_manifest']!=fixed.SELECTED_SHA256 or pins['payload']!=runtime.read(runtime.MODEL/'fixed.json')['images']['sha256'] or
        block['reference']['arithmetic_sha256']!=fixed.implementation_sha256()):
        raise ValueError('Candidate arithmetic/model differs from numerical gate')
    return dict(report=str(path),report_sha256=digest,checks=block['checks'],reference=block['reference'])


def board_predecessor(path,digest,phase,input_path,input_sha,gate,depth=0):
    """Bind each candidate input to a sealed successful predecessor, not raw bytes."""
    import re
    path=path.resolve()
    if depth>8 or not path.is_relative_to(runtime.RUNTIME.resolve()) or runtime.sha(path)!=digest:
        raise ValueError('Full candidate predecessor report location/hash differs')
    report=runtime.read(path)
    if report.get('state')!='complete':raise ValueError('Full candidate predecessor did not complete')
    allowed={'generate':{'board-prep'},'synth':{'generate'},'opt':{'synth'},'place':{'opt'},
             'route':{'place'},'reports':{'synth','opt','place','route'},'source-audit':{'generate'},'bitstream':{'reports'}}
    # The first independently audited session build preceded this CLI schema.
    # Its exact receipt/DCP pins are admitted as a single recorded seed; other
    # raw checkpoints cannot bypass typed predecessor and numerical-gate links.
    seed='11a4c62a00cf3d218775b4b64091b5e9c8bd0ef0f251410fe6a864ea5d2d9fac'
    if digest==seed:
        if phase not in ('opt','reports') or report.get('phase')!='synth' or report.get('source_recheck') is not True:
            raise ValueError('Audited candidate seed is not valid for this phase')
        pin=report['checkpoint']
        if (Path(pin['path']).resolve()!=input_path or pin['sha256']!=input_sha or
            input_sha!='fc9bfff6a7cd89946eb8a5fc8edf7b338a045bb093afe96907eda4642972d0d1' or input_path.stat().st_size!=pin['bytes']):
            raise ValueError('Audited full candidate checkpoint differs')
        for name,sha in report['source_sha256'].items():
            if Path(name)!=runtime.PROJECT/'tools/kv260-build.tcl' and runtime.sha(Path(name))!=sha:
                raise ValueError('Audited full candidate source closure changed: '+name)
        generation=Path(report['generation_report']);generation_sha=report['generation_report_sha256']
        if runtime.sha(generation)!=generation_sha or generation_sha!='9dff6332af61f2635ae52f257edbc838e8f60ff493987b262e52f65e1dd8797f':
            raise ValueError('Audited full candidate generation link differs')
        generated=runtime.read(generation);candidate=Path(generated['candidate_report'])
        if (generated.get('state')!='complete' or generated.get('source_recheck') is not True or
            runtime.sha(candidate)!=generated['candidate_report_sha256']):
            raise ValueError('Audited full candidate board-preset link differs')
        if runtime.read(candidate)['blocks']['board-prep']['properties']['CANDIDATE_PROPOSED_CLOCK_MHZ']!='50':
            raise ValueError('Audited full candidate is not the selected 50 MHz prototype')
        commands=report['commands']
        if len(commands)!=1 or commands[0]['exit_code']!=0 or not all(commands[0].get(k) is True for k in ('child_reaped','process_group_absent')):
            raise ValueError('Audited full candidate synthesis/cleanup differs')
        output=Path(commands[0]['log']).read_text()
        names=('fixed_scalar','mac32','qk_rope','kv_cache','frontend','attention','dense','rmsnorm','feedforward','transformer','axi_transformer')
        for name in names:
            source=RTL/(name+'.sv')
            if (report['source_sha256'].get(str(source))!=runtime.sha(source) or
                not re.search(r"synthesizing module '[^']+' \["+re.escape(str(source))+r':\d+\]',output)):
                raise ValueError('Audited candidate did not compile current neural source: '+name)
        return dict(report=str(path),report_sha256=digest,phase='synth',audited_session_seed=True,
            generation_report=str(generation),generation_report_sha256=generation_sha,
            board_report=str(candidate),board_report_sha256=generated['candidate_report_sha256'],
            historically_pinned_inputs=len(report['source_sha256']),historical_source_closure_complete=False,
            historical_closure_limit='Four generated vendor headers were omitted from the original145 input manifest; later175-file audit/current canonical AMD matches do not retrospectively pin them',
            compiler_log_sha256=runtime.sha(Path(commands[0]['log'])))
    if report.get('mode')=='board-prep':
        block=report['blocks']['board-prep'];previous='board-prep'
        if block.get('logical_design_validated') is not True:raise ValueError('Candidate board preparation is unvalidated')
    elif report.get('mode')=='board-build':
        block=report['blocks']['board-build'];previous=block['phase']
        if block['numerical_gate']['report_sha256']!=gate['report_sha256']:
            raise ValueError('Candidate predecessor uses a different numerical gate')
        prior=block['predecessor']
        board_predecessor(Path(prior['report']),prior['report_sha256'],previous,
                          Path(block['input']['path']).resolve(),block['input']['sha256'],gate,depth+1)
    else:raise ValueError('Expected a sealed candidate-board predecessor')
    if previous not in allowed[phase] or block.get('state')!='complete':
        raise ValueError('Full candidate predecessor phase/order differs')
    for name in ('fixed_scalar','mac32','qk_rope','kv_cache','frontend','attention','dense','rmsnorm','feedforward','transformer','axi_transformer'):
        if block['source_sha256'].get('rtl/'+name+'.sv')!=runtime.sha(RTL/(name+'.sv')):
            raise ValueError('Candidate predecessor source differs: '+name)
    for name,pin in block['artifacts'].items():
        artifact=(path.parent/name).resolve()
        if (not artifact.is_relative_to(path.parent) or artifact.stat().st_size!=pin['bytes'] or runtime.sha(artifact)!=pin['sha256']):
            raise ValueError('Candidate predecessor artifact/closure changed: '+name)
        if artifact.name=='synthesis-source-closure.tsv':
            for line in artifact.read_text().splitlines():
                sha,source=line.split('\t',1)
                if runtime.sha(Path(source))!=sha:raise ValueError('Candidate compiled-source closure changed: '+source)
    if phase=='bitstream':
        if (report.get('accepted') is not True or block.get('diagnostic_passed') is not True or
            Path(block['input']['path']).resolve()!=input_path or block['input']['sha256']!=input_sha):
            raise ValueError('Candidate bitstream requires accepted final reports for this exact routed input')
        return dict(report=str(path),report_sha256=digest,phase=previous,accepted_final_diagnostics=True)
    try:relative=str(input_path.relative_to(path.parent))
    except ValueError:raise ValueError('Candidate input is outside predecessor artifacts') from None
    if block['artifacts'].get(relative,{}).get('sha256')!=input_sha:
        raise ValueError('Candidate input is not a sealed predecessor artifact')
    return dict(report=str(path),report_sha256=digest,phase=previous)


def board_clock_audit(folder,metrics,clocks,checks):
    """Check functional coverage without inventing clocks for unused PS outputs."""
    rows=[line.split('\t') for line in (folder/'clock-domain.tsv').read_text().splitlines()]
    domain={row[0]:row[1] for row in rows if row[0]!='neural_clock_pin'}
    neural=[row[1] for row in rows if row[0]=='neural_clock_pin']
    if (domain['design_top']!='tiny_ps_axi_wrapper' or domain['clock_domain']!='clk_pl_0' or
        float(domain['clock_period_ns'])!=20 or domain['sealed_expected_derived_clock_hz']!='49999500' or
        domain['source_pin']!=domain['ps8']+'/PLCLK[0]' or domain['buffer_input']!=domain['buffer']+'/I' or
        domain['buffer_output']!=domain['buffer']+'/O' or domain['neural_aclk']!='tiny_ps_axi_i/neural/aclk' or
        int(domain['clock_gap_nets'])<0 or clocks!=[dict(name='clk_pl_0',period_ns=20.0)] or
        not neural or len(neural)!=len(set(neural)) or len(neural)!=int(domain['neural_clock_pins']) or
        any(not pin.startswith('tiny_ps_axi_i/neural/') for pin in neural)):
        raise ValueError('Full candidate PS/buffer/neural clock topology or 20 ns target differs')
    coverage={};outputs=[]
    for line in (folder/'clock-coverage.tsv').read_text().splitlines():
        row=line.split('\t')
        if row[0]=='ps_clock_output':outputs.append(row[1:])
        elif row[0]=='unclocked_active_pin':raise ValueError('Full candidate has an active unclocked pin')
        else:coverage[row[0]]=row[1]
    unused={'EMIOENET0MDIOMDC','EMIOENET1MDIOMDC','EMIOENET2MDIOMDC','EMIOENET3MDIOMDC',
            'EMIOSDIO0CLKOUT','EMIOSDIO1CLKOUT','EMIOSPI0SCLKO','EMIOSPI1SCLKO'}
    if (coverage['native_no_clock']!=metrics['native_no_clock'] or int(coverage['native_no_clock'])!=checks['no_clock'] or
        len(outputs)!=int(coverage['native_no_clock']) or len(outputs)!=len({row[0] for row in outputs}) or
        coverage['unused_ps_clock_outputs']!=coverage['native_no_clock'] or coverage['unused_ps_clock_outputs']!=metrics['unused_ps_clock_outputs'] or
        coverage['unclocked_active_pins']!='0' or metrics['unclocked_active_pins']!='0' or
        coverage['unconstrained_internal_endpoints']!='0' or metrics['unconstrained_internal_endpoints']!='0' or
        checks['unconstrained_internal_endpoints']!=0 or
        any(name not in {domain['ps8']+'/'+n for n in unused} or direction!='OUT' or sinks!='0' for name,direction,sinks in outputs)):
        raise ValueError('Full candidate clock coverage is incomplete or inactive outputs have loads')
    constraints={}
    for name in ('constraints-before.txt','constraints-after.txt'):
        state=dict(line.split() for line in (folder/name).read_text().splitlines())
        if (int(state['default_rules'])<=0 or any(state[k]!='0' for k in
            ('changed_rules','waiver_objects','loop_allow_nets','clock_route_overrides'))):
            raise ValueError('Full candidate DRC defaults or clock/loop waiver audit differs')
        constraints[name]=state
    return dict(clock_domain='clk_pl_0',period_ns=20,derived_candidate_clock_hz=49999500,
        ps8=domain['ps8'],source_pin=domain['source_pin'],buffer=domain['buffer'],neural_clock_pins=len(neural),
        clock_gap_nets=int(domain['clock_gap_nets']),native_no_clock=checks['no_clock'],unused_ps_outputs=[row[0] for row in outputs],active_unclocked_pins=0,
        unconstrained_internal_endpoints=0,constraint_audits=constraints,
        coverage_scope='Native no_clock outputs remain visible; only exact unused hard-PS peripheral OUT pins with zero sinks are classified inactive. No clock or timing exception was added')


def run_board_build_vivado(folder,command,phase,input_path,input_sha,model_report,model_sha,predecessor,predecessor_sha,vivado_bin):
    """Build only an offline full PS/AXI candidate after original numerical proof."""
    import re
    gate=verified_model_gate(model_report,model_sha);input_path=input_path.resolve()
    if (not input_path.is_relative_to(runtime.RUNTIME.resolve()) or not input_sha or runtime.sha(input_path)!=input_sha):
        raise ValueError('Full candidate input location/hash differs')
    parent=board_predecessor(predecessor,predecessor_sha,phase,input_path,input_sha,gate)
    script=runtime.PROJECT/'tools/kv260-build.tcl'
    source_pins={str(p.relative_to(runtime.PROJECT)):runtime.sha(p) for p in
                 [script,*[RTL/(n+'.sv') for n in ('fixed_scalar','mac32','qk_rope','kv_cache','frontend',
                           'attention','dense','rmsnorm','feedforward','transformer','axi_transformer')]]}
    output=command(folder,'board-build-'+phase,[vivado_bin/'vivado','-mode','batch','-notrace','-source',script,
        '-nojournal','-log',folder/'vivado.log','-tclargs',phase,input_path,folder])
    markers=('CANDIDATE_BITSTREAM_ONLY','NOT_DEPLOYED') if phase=='bitstream' else ('NOT_A_BOARD_IMAGE_OR_BITSTREAM',)
    if 'PASS CANDIDATE_BUILD '+phase not in output or any(marker not in output for marker in markers):
        raise ValueError('Missing full candidate phase receipt')
    if runtime.sha(input_path)!=input_sha or any(runtime.sha(runtime.PROJECT/n)!=sha for n,sha in source_pins.items()):
        raise ValueError('Full candidate input/source changed during phase')
    before=(folder/'inputs-before.tsv').read_text();after=(folder/'inputs-after.tsv').read_text()
    if not before or before!=after:raise ValueError('Full candidate transitive source pins changed')
    info=dict(state='complete',phase=phase,numerical_gate=gate,predecessor=parent,input=dict(path=str(input_path),sha256=input_sha),
        source_sha256=source_pins,warnings=[line for line in output.splitlines() if line.startswith('WARNING:')],
        limits='Offline candidate full PS/AXI/neural build only; no actual board firmware/OS/device-tree compatibility, bitstream/XSA, programming or physical measurement')
    if phase not in ('generate','source-audit'):
        structure=dict(line.split() for line in (folder/'structure.txt').read_text().splitlines())
        if structure['blackboxes']!='0' or structure['latches']!='0' or structure['processing_system_primitives']!='1':
            raise ValueError('Full candidate is not a complete latch-free PS/AXI/neural design')
        info['structure']=structure
    if phase=='reports':
        metrics={};clocks=[]
        for line in (folder/'metrics.txt').read_text().splitlines():
            fields=line.split()
            if fields[0]=='clock':clocks.append(dict(name=fields[1],period_ns=float(fields[3])))
            else:metrics[fields[0]]=fields[1]
        timing=(folder/'timing.rpt').read_text()
        checks={name:int(count) for name,count in re.findall(r'checking ([a-z_]+) \((\d+)\)',timing)}
        if not clocks or not {'no_clock','unconstrained_internal_endpoints'}<=set(checks):
            raise ValueError('Full candidate clock/timing coverage is missing')
        clock_audit=board_clock_audit(folder,metrics,clocks,checks)
        timing_met='All user specified timing constraints are met.' in timing
        passed=(timing_met and float(metrics['setup_slack_ns'])>=0 and float(metrics['hold_slack_ns'])>=0 and
            all(metrics[k]=='0' for k in ('drc_errors_or_critical_warnings','routing_errors','unrouted_nets','partially_routed_nets','routing_gap_nets')) and
            metrics['fully_placed']=='1' and metrics['fully_routed']=='1' and
            clock_audit['clock_gap_nets']==0 and clock_audit['active_unclocked_pins']==0 and checks['unconstrained_internal_endpoints']==0)
        info.update(metrics=metrics,clocks=clocks,timing_coverage=checks,all_reported_timing_constraints_met=timing_met,
                    clock_audit=clock_audit,diagnostic_passed=passed,outcome='passed' if passed else 'failed',
                    utilization=synthesis_utilization(folder/'utilization.rpt'))
    if phase=='bitstream':
        bitstream=folder/'offline-candidate.bit'
        if not bitstream.is_file() or bitstream.stat().st_size<1024:raise ValueError('Candidate programming file missing/empty')
        info.update(candidate_only=True,programming_file_generated=True,board_compatibility_verified=False,
            programming_file=dict(path=str(bitstream),bytes=bitstream.stat().st_size,sha256=runtime.sha(bitstream)),
            required_runtime_configuration=dict(part='xck26-sfvc784-2LV-c',PS_PL0_clock_max_hz=50000000,
                candidate_PS_clock_hz=49999500,register_base='0xA0000000',register_bytes=256,
                PS_AXI_port='M_AXI_HPM0_FPD',reset='active-low synchronized PL reset'),
            limits='Offline candidate .bit only. It does not initialize the PS clock/AXI/boot software, contain model weights, establish board power/OS compatibility, or load/flash a board')
    info['artifacts']={str(p.relative_to(folder)):dict(bytes=p.stat().st_size,sha256=runtime.sha(p)) for p in folder.rglob('*')
        if p.is_file() and '.Xil' not in p.parts and p.suffix in
           ('.bit','.dcp','.rpt','.txt','.tsv','.xpr','.bd','.v','.sv','.svh','.vh','.vhd','.xdc','.xci','.xml','.mem','.coe','.dat')}
    print('Full candidate phase complete: '+phase,flush=True)
    if phase=='reports':print('Full candidate diagnostics: '+str(info['metrics']),flush=True)
    return info


def implementation_report_script(checkpoint,period_ns):
    """Report the same routed netlist under an explicit diagnostic clock."""
    if any(c in str(checkpoint) for c in '{}\n\r') or period_ns not in (10,20):
        raise ValueError('Invalid routed-timing checkpoint/period')
    return '\n'.join(['set_param general.maxThreads 2','open_checkpoint {'+str(checkpoint)+'}',
        'create_clock -name clk -period '+str(period_ns)+' [get_ports clk]',
        'report_route_status -file route-status.rpt',
        'report_timing_summary -delay_type min_max -report_unconstrained -file timing.rpt',
        'report_utilization -file utilization.rpt','report_drc -file drc.rpt',
        'set maximum [get_timing_paths -quiet -delay_type max -max_paths 1]',
        'set minimum [get_timing_paths -quiet -delay_type min -max_paths 1]',
        'if {[llength $maximum] != 1 || [llength $minimum] != 1} {error {Missing clocked timing paths}}',
        'set errors [get_drc_violations -quiet -filter {SEVERITY == "Error" || SEVERITY == "Critical Warning"}]',
        'set fp [open metrics.txt w]',
        'puts $fp "setup_slack_ns [get_property SLACK $maximum]"',
        'puts $fp "hold_slack_ns [get_property SLACK $minimum]"',
        'puts $fp "drc_errors_or_critical_warnings [llength $errors]"',
        'puts $fp "fully_placed [report_route_status -boolean_check PLACED_FULLY]"',
        'puts $fp "fully_routed [report_route_status -boolean_check ROUTED_FULLY]"',
        'puts $fp "routing_errors [report_route_status -boolean_check ERRORS_IN_ROUTES]"',
        'puts $fp "unrouted_nets [llength [report_route_status -return_nets -route_type UNROUTED]]"',
        'puts $fp "partially_routed_nets [llength [report_route_status -return_nets -route_type PARTIAL]]"',
        'set gaps [report_route_status -return_nets -route_type GAPS]',
        'puts $fp "routing_gap_nets [llength $gaps]"',
        'puts $fp "clock_period_ns [get_property PERIOD [get_clocks clk]]"',
        'puts $fp "clock_source [get_property HD.CLK_SRC [get_ports clk]]"',
        'close $fp','set fp [open routing-gaps.txt w]',
        'foreach net $gaps {puts $fp [report_property -all -return_string $net]}',
        'close $fp','puts {PASS IMPLEMENTATION REPORTS}','exit'])+'\n'


def implementation_report_result(work,output,period_ns,clock_source):
    if 'PASS IMPLEMENTATION REPORTS' not in output:raise ValueError('Missing implementation reports receipt')
    metrics=dict(line.split() for line in (work/'metrics.txt').read_text().splitlines())
    if float(metrics['clock_period_ns'])!=period_ns or metrics['clock_source']!=clock_source:
        raise ValueError('Implementation clock assumptions changed')
    timing_met='All user specified timing constraints are met.' in (work/'timing.rpt').read_text()
    internal_met=float(metrics['setup_slack_ns'])>=0 and float(metrics['hold_slack_ns'])>=0
    passed=(timing_met and internal_met and metrics['drc_errors_or_critical_warnings']=='0' and
            metrics['fully_placed']=='1' and metrics['fully_routed']=='1' and metrics['routing_errors']=='0' and
            metrics['unrouted_nets']=='0' and metrics['partially_routed_nets']=='0')
    return dict(state='complete',metrics=metrics,utilization=synthesis_utilization(work/'utilization.rpt'),
        all_reported_timing_constraints_met=timing_met,internal_setup_and_hold_met=internal_met,
        drc_errors_or_critical_warnings=int(metrics['drc_errors_or_critical_warnings']),
        report_warnings=[line for line in output.splitlines() if line.startswith('WARNING:')],
        diagnostic_passed=passed,outcome='passed' if passed else 'failed')


def run_routed_timing_vivado(folder,command,path,digest,period_ns,vivado_bin):
    """Recheck a sealed completed route, retaining the original failed-clock arm."""
    path=path.resolve()
    if not path.is_relative_to(runtime.RUNTIME.resolve()) or not digest or runtime.sha(path)!=digest:
        raise ValueError('Routed-timing progress report location/hash differs')
    progress=runtime.read(path)
    if (progress['target']!='xck26-sfvc784-2LV-c' or
        progress.get('stages',{}).get('route',{}).get('state')!='complete'):
        raise ValueError('Routed timing requires a completed route checkpoint')
    _,provenance=implementation_checkpoint(Path(progress['input']['report']),progress['input']['report_sha256'])
    if runtime.sha(vivado_bin/'rdiArgs.sh')!=provenance['vendor_wrapper_sha256']:
        raise ValueError('Routed-timing vendor wrapper differs from synthesis')
    if progress['input']['source_sha256']!=provenance['source_sha256']:
        raise ValueError('Routed-timing source provenance differs')
    checkpoint=path.parent/'route.dcp';pin=progress['stages']['route']['checkpoint_sha256']
    if runtime.sha(checkpoint)!=pin:raise ValueError('Routed-timing checkpoint hash differs')
    script=folder/'reports.tcl';script.write_text(implementation_report_script(checkpoint,period_ns))
    output=command(folder,'implementation-reports',[vivado_bin/'vivado','-mode','batch','-notrace','-source',script])
    info=implementation_report_result(folder,output,period_ns,progress['assumptions']['external_clock_buffer_site'])
    if runtime.sha(checkpoint)!=pin or any(runtime.sha(runtime.PROJECT/name)!=sha for name,sha in provenance['source_sha256'].items()):
        raise ValueError('Routed-timing checkpoint/source changed during reporting')
    info.update(input=dict(progress=str(path),progress_sha256=digest,route_checkpoint_sha256=pin,
                           synthesis=provenance),clock_period_ns=period_ns,
        limits='Same existing core-only physical route, reanalyzed at explicitly selected clock. No rerouting, PS/AXI shell, board timing closure, programming file or physical clock measurement',
        artifacts={p.name:dict(bytes=p.stat().st_size,sha256=runtime.sha(p)) for p in folder.iterdir()
                   if p.suffix in ('.rpt','.tcl','.txt')})
    print('Routed core timing at '+str(period_ns)+' ns: '+str(info['metrics']),flush=True)
    return info


def run_implementation_vivado(folder,command,checkpoint_report,digest,info,vivado_bin=Path('/home/admin/amd/2025.2/Vivado/bin')):
    """Bounded core-only layout diagnostic, with no board shell or bitstream."""
    checkpoint,provenance=implementation_checkpoint(checkpoint_report,digest)
    if runtime.sha(vivado_bin/'rdiArgs.sh')!=provenance['vendor_wrapper_sha256']:
        raise ValueError('Implementation vendor wrapper differs from synthesis')
    work=folder/'transformer';work.mkdir()
    info.update(state='incomplete',target='xck26-sfvc784-2LV-c',input=provenance,
        assumptions=dict(clock_period_ns=10,external_clock_buffer='HD.CLK_SRC from target BUFGCE inventory',
            boundary='Unconstrained core data ports; no PS, AXI wrapper, board I/O or physical board clock',
            floorplan='Unrestricted diagnostic placement; not a reusable locked OOC partition'),
        limits='Core-only OOC layout diagnostic. No board timing closure, original Mac whole-model proof, programming file or board measurement',
        stages={})
    binary=vivado_bin/'vivado'
    # Each process opens a checkpoint, so a timeout preserves earlier completed stages.
    # HD.CLK_SRC models a hypothetical external buffer; it does not choose a PS clock.
    for stage,previous,operations in (
        ('opt',checkpoint,['create_clock -name clk -period 10 [get_ports clk]',
            'set candidates [lsort -dictionary [get_sites -quiet -filter {SITE_TYPE == BUFGCE}]]',
            'if {![llength $candidates]} {error {No target BUFGCE sites}}',
            'set clock_source [lindex $candidates [expr {[llength $candidates] / 2}]]',
            'set_property HD.CLK_SRC $clock_source [get_ports clk]',
            'puts "DIAGNOSTIC_CLOCK_SOURCE $clock_source"','opt_design']),
        ('place',work/'opt.dcp',['place_design']),
        ('route',work/'place.dcp',['route_design'])):
        script=work/(stage+'.tcl')
        if any(c in str(previous) for c in '{}\n\r'):raise ValueError('Unsafe Tcl checkpoint path')
        lines=['set_param general.maxThreads 2','open_checkpoint {'+str(previous)+'}',
               'if {[get_property PART [current_design]] ne "xck26-sfvc784-2LV-c"} {error {Checkpoint part differs}}',
               *operations,'write_checkpoint -force '+stage+'.dcp']
        if stage=='opt':
            lines+=['report_drc -checks [get_drc_checks LUTLP-1] -file combinational-loops.rpt',
                    'if {[llength [get_drc_violations -quiet]]} {error {Combinational loop in optimized netlist}}']
        lines+=['puts {PASS IMPLEMENTATION '+stage+'}','exit']
        script.write_text('\n'.join(lines)+'\n')
        output=command(work,'implementation-'+stage,[binary,'-mode','batch','-notrace','-source',script])
        if 'PASS IMPLEMENTATION '+stage not in output:raise ValueError('Missing implementation '+stage+' receipt')
        info['stages'][stage]=dict(state='complete',checkpoint_sha256=runtime.sha(work/(stage+'.dcp')),
            warnings=[line for line in output.splitlines() if line.startswith('WARNING:')])
        if stage=='opt':
            sources=[line.split()[-1] for line in output.splitlines() if line.startswith('DIAGNOSTIC_CLOCK_SOURCE ')]
            if len(sources)!=1:raise ValueError('Missing diagnostic clock-source identity')
            info['assumptions']['external_clock_buffer_site']=sources[0]
        runtime.save(work/'progress.json',info)
        print('Core-only implementation '+stage+' complete',flush=True)
    script=work/'reports.tcl'
    script.write_text(implementation_report_script(work/'route.dcp',10))
    output=command(work,'implementation-reports',[binary,'-mode','batch','-notrace','-source',script])
    info.update(implementation_report_result(work,output,10,info['assumptions']['external_clock_buffer_site']))
    if any(runtime.sha(runtime.PROJECT/name)!=sha for name,sha in provenance['source_sha256'].items()):
        raise ValueError('RTL source changed during implementation')
    info['artifacts']={p.name:dict(bytes=p.stat().st_size,sha256=runtime.sha(p)) for p in work.iterdir()
                       if p.suffix in ('.dcp','.rpt','.tcl','.txt')}
    print('Core-only implementation metrics: '+str(info['metrics']),flush=True)
    return info


def vivado_main():
    """Linux-only preparation/replay; never invokes the Mac model worker or setup."""
    import argparse
    import sys
    import tempfile
    parser = argparse.ArgumentParser(description='Vivado RTL verification; standard library only, no ML runtime or training')
    parser.add_argument('--vivado',choices=('compile','synthetic','frozen','frontend','scalar','norm','dense','feedforward','attention','transformer','axi','axi-core','host','pack','synthesis','implementation','board-prep','routed-timing','model-compare','board-build'),required=True)
    parser.add_argument('--block',choices=('all','mac32','qk_rope','kv_cache'),default='all')
    parser.add_argument('--rows',type=int,choices=(1,32,96),default=96)
    parser.add_argument('--vivado-bin',type=Path,default=Path('/home/admin/amd/2025.2/Vivado/bin'))
    parser.add_argument('--fixture-dir',type=Path)
    parser.add_argument('--manifest-sha256')
    parser.add_argument('--fixed-inputs',nargs=3,metavar=('ARITHMETIC_JSON','SHA256','TENSORS'),
                        help='Pack/model-compare only: pinned tensor bytes with unchanged original circuit arithmetic')
    parser.add_argument('--trace-report',nargs=2,action='append',default=[],metavar=('RESULTS_JSON','SHA256'),
                        help='Model-compare only: reuse a sealed current-source transformer trace; simulate missing cases')
    parser.add_argument('--fixture-kind',choices=('synthetic','frozen'),default='synthetic')
    parser.add_argument('--synthesis-top',choices=('fixed_scalar','rmsnorm','dense','attention','frontend','feedforward','transformer'),default='frontend')
    parser.add_argument('--prefix',choices=('bos','j01-3','j01-16','authored128','repeated-j01-256'),default='bos',help='Explicit frozen teacher-forced inputs for transformer simulation')
    parser.add_argument('--no-waveform',action='store_true',help='Transformer only: retain all accepted-value CSV events, omit internal VCD')
    parser.add_argument('--synthesis-timeout',type=int,choices=(180,600),default=180,
                        help='Separate full-core synthesis watchdog; simulator invocations always remain180 seconds')
    parser.add_argument('--checkpoint-report',type=Path,help='Sealed synthesis results.json or completed-route progress.json in ignored runtime')
    parser.add_argument('--checkpoint-report-sha256',help='Trusted SHA256 of the checkpoint report')
    parser.add_argument('--timing-period-ns',type=int,choices=(10,20),default=10,
                        help='Routed-timing only: explicit nominal clock for the same existing physical route')
    parser.add_argument('--board-clock-mhz',type=int,choices=(50,100),default=100,
                        help='Board-prep only: candidate PS clock request, pending physical board checks')
    parser.add_argument('--build-phase',choices=('generate','source-audit','synth','opt','place','route','reports','bitstream'))
    parser.add_argument('--build-input',type=Path)
    parser.add_argument('--build-input-sha256')
    parser.add_argument('--build-receipt',type=Path)
    parser.add_argument('--build-receipt-sha256')
    parser.add_argument('--model-report',type=Path)
    parser.add_argument('--model-report-sha256')
    parser.add_argument('--board-build-timeout',type=int,choices=(180,600),default=180,
                        help='Full-board candidate only: synth/opt/place/route watchdog; generate/reports stay180 seconds')
    parser.add_argument('--implementation-timeout',type=int,choices=(180,600),default=180,
                        help='Separate per-stage core-only opt/place/route watchdog; reports remain180 seconds')
    args = parser.parse_args()
    if args.fixed_inputs and args.vivado not in ('pack','model-compare'):
        parser.error('Explicit fixed inputs apply only to pack transport and model-compare')
    if args.synthesis_timeout!=180 and (args.vivado!='synthesis' or args.synthesis_top!='transformer'):
        parser.error('The 600-second synthesis budget is only for the complete transformer netlist')
    if args.implementation_timeout!=180 and args.vivado!='implementation':
        parser.error('The implementation budget is only for core-only opt/place/route')
    if args.no_waveform and args.vivado!='transformer':
        parser.error('--no-waveform only applies to the transformer trace test')
    if args.timing_period_ns!=10 and args.vivado!='routed-timing':
        parser.error('Alternate timing period only applies to the routed-timing diagnostic')
    if args.board_clock_mhz!=100 and args.vivado!='board-prep':
        parser.error('Candidate board clock only applies to board-prep')
    if args.trace_report and args.vivado!='model-compare':
        parser.error('Saved trace reports only apply to model-compare')
    if args.vivado=='model-compare' and (not args.fixture_dir or not args.manifest_sha256):
        parser.error('Model-compare requires --fixture-dir and its trusted --manifest-sha256')
    if args.board_build_timeout!=180 and (args.vivado!='board-build' or args.build_phase not in ('synth','opt','place','route')):
        parser.error('The full-board600-second budget only applies to synth/opt/place/route')
    if sys.platform!='linux':parser.error('This entry point is for the authorised Linux simulator host')
    if args.vivado=='board-build' and not all((args.build_phase,args.build_input,args.build_input_sha256,args.model_report,args.model_report_sha256,args.build_receipt,args.build_receipt_sha256)):
        parser.error('Board-build requires phase, sealed input and accepted sealed model report')
    if args.vivado!='board-build' and any((args.build_phase,args.build_input,args.build_input_sha256,args.model_report,args.model_report_sha256,args.build_receipt,args.build_receipt_sha256)):
        parser.error('Full-board input/gate arguments only apply to board-build')
    if args.vivado in ('implementation','routed-timing') and (not args.checkpoint_report or not args.checkpoint_report_sha256):
        parser.error('Layout/timing requires --checkpoint-report and its trusted --checkpoint-report-sha256')
    if args.vivado=='frozen' and (args.block=='all' or not args.fixture_dir or not args.manifest_sha256):
        parser.error('Frozen mode requires one block, --fixture-dir and trusted --manifest-sha256')
    root = runtime.RUNTIME/'vivado-prep';root.mkdir(exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix=args.vivado+'-',dir=root))
    report = dict(state='incomplete',mode=args.vivado,started_at=runtime.now(),commands=[],blocks={},
        limits='Scope is defined by the selected mode and block receipts. No board execution or measured FPGA speed/energy',
        required_real_model_comparison='pending' if args.vivado!='frozen' else 'incomplete')
    report['vendor_wrapper_sha256']=runtime.sha(args.vivado_bin/'rdiArgs.sh')
    report['source_sha256']={name:runtime.sha(runtime.PROJECT/name) for name in
        ('tools/rtl.py','tools/runtime.py','tools/fixed.py','model/fixed.json',
         'rtl/mac32.sv','rtl/mac32_tb.sv','rtl/qk_rope.sv','rtl/qk_rope_tb.sv','rtl/kv_cache.sv','rtl/kv_cache_tb.sv')}
    print('Vivado artifacts: '+str(folder),flush=True)
    command = lambda directory,name,argv: vivado_command(directory,name,argv,report['commands'],
        allow_warnings=name.startswith(('synthesis','implementation-','board-build-')) or name=='board-prep',
        timeout_seconds=(args.synthesis_timeout if name=='synthesis' else args.implementation_timeout
                         if name in ('implementation-opt','implementation-place','implementation-route') else args.board_build_timeout
                         if name in ('board-build-synth','board-build-opt','board-build-place','board-build-route') else 180))
    try:
        import fixed
        if runtime.sha(runtime.MODEL/'fixed.json')!=fixed.SELECTED_SHA256:
            raise ValueError('Selected arithmetic manifest changed')
        manifest=runtime.read(runtime.MODEL/'fixed.json')
        if args.vivado=='pack':
            report['blocks']['model_package']=pack_model_words(folder,model_inputs=args.fixed_inputs)
            report['state']='complete'
            report['required_real_model_comparison']='Byte transport only; no inference performed'
            return
        if args.vivado=='host':
            report['blocks']['host']=run_host_validation(folder,command)
            report['state']='complete'
            report['required_real_model_comparison']='Host callback mocks only; no inference performed'
            return
        if args.vivado=='board-prep':
            report['blocks']['board-prep']=run_board_prep_vivado(folder,command,args.vivado_bin,args.board_clock_mhz)
            report['state']='complete'
            report['required_real_model_comparison']='Logical board shell only; no inference performed'
            return
        if args.vivado=='board-build':
            output=command(folder,'board-build-version',[args.vivado_bin/'vivado','-version'])
            if '2025.2' not in output:raise ValueError('Expected installed Vivado 2025.2')
            info=run_board_build_vivado(folder,command,args.build_phase,args.build_input,args.build_input_sha256,
                args.model_report,args.model_report_sha256,args.build_receipt,args.build_receipt_sha256,args.vivado_bin)
            report['blocks']['board-build']=info
            report['state']='complete'
            report['accepted']=info.get('diagnostic_passed',False)
            report['required_real_model_comparison']='Accepted original Mac numerical gate reverified against candidate RTL'
            return
        if args.vivado=='routed-timing':
            output=command(folder,'implementation-version',[args.vivado_bin/'vivado','-version'])
            if '2025.2' not in output:raise ValueError('Expected installed Vivado 2025.2')
            report['blocks']['routed-timing']=run_routed_timing_vivado(folder,command,args.checkpoint_report,
                args.checkpoint_report_sha256,args.timing_period_ns,args.vivado_bin)
            report['state']='complete'
            report['accepted']=report['blocks']['routed-timing']['diagnostic_passed']
            report['required_real_model_comparison']='Timing reanalysis only; no inference performed'
            return
        if args.vivado=='implementation':
            output=command(folder,'implementation-version',[args.vivado_bin/'vivado','-version'])
            if '2025.2' not in output:raise ValueError('Expected installed Vivado 2025.2')
            report['blocks']['implementation']={}
            run_implementation_vivado(folder,command,args.checkpoint_report,args.checkpoint_report_sha256,
                                      report['blocks']['implementation'],args.vivado_bin)
            report['state']='complete'
            report['accepted']=report['blocks']['implementation']['diagnostic_passed']
            report['required_real_model_comparison']='Core layout diagnostic only; original Mac whole-model validation remains pending'
            return
        for name in ('xvlog','xelab','xsim'):
            output = command(folder,name+'-version',[args.vivado_bin/name,'--version'])
            if '2025.2' not in output:raise ValueError('Expected installed Vivado 2025.2')
        if args.vivado=='model-compare':
            report['blocks']['model-compare']=run_model_comparison(folder,command,args.fixture_dir,
                args.manifest_sha256,args.trace_report,args.vivado_bin,model_inputs=args.fixed_inputs)
            report.update(state='complete',accepted=True,
                required_real_model_comparison='Passed explicit original Mac integer reference cases and clear-context replays')
            return
        if args.vivado=='synthesis':
            report['blocks'][args.synthesis_top]=run_synthesis_vivado(folder,command,args.synthesis_top,args.vivado_bin)
            report['state']='complete'
            report['required_real_model_comparison']='Synthesis is not model-reference validation'
            return
        if args.vivado=='frontend':
            report['blocks']['frontend']=run_frontend_vivado(folder,command,args.fixture_kind)
            report['state']='complete'
            report['required_real_model_comparison']='seven archived stage boundaries only' if args.fixture_kind=='frozen' else 'pending'
            return
        if args.vivado in ('scalar','norm','dense','feedforward','attention','transformer','axi','axi-core'):
            runner={'scalar':run_scalar_vivado,'norm':run_norm_vivado,'dense':run_dense_vivado,
                    'feedforward':run_feedforward_vivado,'attention':run_attention_vivado,'transformer':run_transformer_vivado,
                    'axi':run_axi_vivado,'axi-core':run_axi_core_vivado}[args.vivado]
            report['blocks'][args.vivado]=(runner(folder,command,tokens=transformer_prefix_tokens(args.prefix),waveform=not args.no_waveform,vivado_bin=args.vivado_bin)
                                           if args.vivado=='transformer' else runner(folder,command))
            report['state']='complete'
            report['required_real_model_comparison']='component numerical tests; full connected logits still pending'
            return
        blocks = ('mac32','qk_rope','kv_cache') if args.block=='all' else (args.block,)
        for block in blocks:
            work = folder/block;work.mkdir()
            info = report['blocks'][block] = dict(state='incomplete',rows=args.rows if block=='mac32' else None)
            info['layout']=(projection_layout(manifest,args.rows) if block=='mac32' else
                            rope_layout(manifest) if block=='qk_rope' else cache_layout(manifest))
            sources = [RTL/(block+'.sv'),RTL/(block+'_tb.sv')]
            info['source_sha256']={str(p.relative_to(runtime.PROJECT)):runtime.sha(p) for p in sources}
            command(work,'compile',[args.vivado_bin/'xvlog','--sv',*sources])
            info['compiled']=True
            command(work,'elaborate',[args.vivado_bin/'xelab','work.'+block+'_tb','--debug','typical',
                    '--mt','2','--snapshot',block+'_sim',
                    *(['--generic_top','ROWS='+str(args.rows)] if block=='mac32' else [])])
            info['elaborated']=True
            if args.vivado!='compile':
                table=None
                if args.vivado=='frozen':
                    cases,info['transfer']=vivado_frozen(args.fixture_dir,args.manifest_sha256,block,
                                                        args.rows if block=='mac32' else None)
                    table=args.fixture_dir if block=='qk_rope' else None
                elif block=='mac32':
                    cases = matrix_synthetic_fixtures(args.rows) if args.rows>1 else [
                        matrix_case(c['name'],c['x'],[c['w']]) for c in scalar_synthetic_fixtures()]
                elif block=='qk_rope':cases=rope_synthetic_fixtures()
                else:
                    cases=cache_synthetic_banks()
                    # Existing TB requires three banks. Replay the original pattern;
                    # this is NOT a replacement model bank or third distinct payload.
                    cases.append(dict(cases[0],name='Replay of synthetic coordinate patterns'))
                plusargs=vivado_inputs(work,block,cases,table)
                output=command(work,'simulation',[args.vivado_bin/'xsim',block+'_sim','--runall',
                    '--onerror','quit','--onfinish','quit',
                    *[v for k,value in plusargs.items() for v in ('--testplusarg',k+'='+value)]])
                wanted = (f'PASS full_transactions={len(cases)+reset_probe_count(args.rows)+1} output_rows={args.rows} reset_probes={reset_probe_count(args.rows)} row_latency_edges=65'
                          if block=='mac32' else f'PASS rope_transactions={len(cases)+10} reset_probes=9 pair_latency_edges=6'
                          if block=='qk_rope' else 'PASS kv_cache banks=3 positions=256 coordinates=32')
                if wanted not in output:raise ValueError('Missing testbench success receipt')
                checker={'mac32':check_trace,'qk_rope':check_rope_trace,'kv_cache':check_cache_trace}[block]
                checks,_=checker(work/'cycles.csv',cases)
                if args.vivado=='synthetic' and block=='kv_cache':
                    checks['model_readback_values']=0;checks['distinct_synthetic_payloads']=2
                info.update(checks=checks,evidence='frozen Mac reference replay' if args.vivado=='frozen' else 'synthetic arithmetic/protocol only')
                print(block+': '+str(checks),flush=True)
            info['artifacts']={p.name:dict(bytes=p.stat().st_size,sha256=runtime.sha(p))
                               for p in work.iterdir() if p.suffix in ('.csv','.vcd','.hex','.json')}
            info['state']='complete'
            print(block+': compile/elaborate passed',flush=True)
        report['state']='complete'
        if args.vivado=='frozen':report['required_real_model_comparison']='replayed for this block only'
    except (Exception,KeyboardInterrupt) as error:
        report.update(state='failed',error=str(error) or type(error).__name__)
        if report['blocks'].get('implementation',{}).get('state')=='incomplete':
            report['blocks']['implementation']['state']='failed'
        raise
    finally:
        report['completed_at']=runtime.now()
        runtime.save(folder/'results.json',report)


if __name__=='__main__':
    vivado_main()
