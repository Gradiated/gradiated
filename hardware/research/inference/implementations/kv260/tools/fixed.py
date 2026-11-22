"""Integer-only forward study; import installed libraries only inside our worker.

Offline table construction/calibration and the declared host sampler use floats.
The network forward uses checked integer operations throughout. NumPy int64 is
host storage, not a claim that the proposed hardware stores 64-bit activations.
"""
from contextlib import ExitStack
import math
import time
from unittest.mock import patch

SELECTED_SHA256 = '7b7f076e30a759ac9fa011d17f2bd85539397d031fd8e40f0630ce75d7cbbe37'
PREFIX = 'model.layers.0.'
NAMES = {'E':'model.embed_tokens.weight',
         **{n:PREFIX+'self_attn.'+n.lower()+'_proj.weight' for n in ('Q','K','V','O')},
         **{n:PREFIX+'mlp.'+n+'_proj.weight' for n in ('gate','up','down')},
         'gain1':PREFIX+'input_layernorm.weight',
         'gain2':PREFIX+'post_attention_layernorm.weight',
         'gain3':'model.norm.weight'}
ACTIVATIONS = ('norm1','q','k','v','qrot','krot','context','o','res1','norm2',
               'gate','up','silu','hidden','down','res2','normfinal')


def scalar_rne(numerator, denominator):
    """Independent scalar oracle: Python unbounded integers, magnitude rounding."""
    if denominator <= 0:
        raise ValueError('Positive denominator required')
    sign = -1 if numerator < 0 else 1
    quotient, remainder = divmod(abs(int(numerator)), int(denominator))
    if remainder > denominator-remainder or (remainder == denominator-remainder and quotient%2):
        quotient += 1
    return sign*quotient


def dependencies():
    global np
    import numpy as np


def implementation_sha256():
    """Bind arithmetic source without a circular hash of its selection-pin constant."""
    import hashlib
    import inspect
    import json
    functions = (maximum_abs,scalar_rne,divide,shift,multiply,dot,Fixed)
    payload = json.dumps([NAMES,ACTIVATIONS],sort_keys=True)+'\n'
    payload += '\n'.join(inspect.getsource(value) for value in functions)
    return hashlib.sha256(payload.encode()).hexdigest()


def maximum_abs(a):
    return max(abs(int(a.min(initial=0))), abs(int(a.max(initial=0))))


def divide(a, denominator):
    """Vector RNE: signed floor quotient and nonnegative remainder, not scalar oracle."""
    a = np.asarray(a, dtype=np.int64)
    d = np.asarray(denominator, dtype=np.int64)
    if np.any(d<=0) or np.any(d>2**62):
        raise OverflowError('Division denominator outside checked range')
    q,r = np.divmod(a,d)
    return q + ((r>d-r) | ((r==d-r) & ((q&1)!=0)))


def shift(a, amount):
    """Multiply by 2**amount, with RNE when shifting right; check before shifting."""
    a = np.asarray(a,dtype=np.int64)
    amount = np.asarray(amount,dtype=np.int64)
    if amount.ndim:
        a,amount = np.broadcast_arrays(a,amount)
        out = np.empty_like(a)
        for value in np.unique(amount):
            mask = amount==value
            out[mask] = shift(a[mask],int(value))
        return out
    value = int(amount)
    if value >= 0:
        if value>62 or maximum_abs(a)>((2**63-1)>>value):
            raise OverflowError('Left shift exceeds signed 64-bit scratch')
        return a<<value
    if value >= -62:
        return divide(a,1<<-value)
    # Rare extreme exponents still use exact integer semantics, never floating math.
    return np.asarray([scalar_rne(int(v),1<<-value) for v in a.flat],dtype=np.int64).reshape(a.shape)


def multiply(a,b):
    if maximum_abs(np.asarray(a))*maximum_abs(np.asarray(b)) > 2**63-1:
        raise OverflowError('Product exceeds signed 64-bit scratch')
    return a*b


def dot(a,b):
    if a.shape[-1]*maximum_abs(a)*maximum_abs(b) >= 2**47:
        raise OverflowError('Dot-product bound exceeds signed 48-bit accumulator')
    return a@b


def integer_call(net,tokens,cache=None):
    """Tripwire against accidentally calling floating nonlinear math in the network."""
    with ExitStack() as stack:
        for name in ('exp','sqrt','sin','cos','power'):
            stack.enter_context(patch.object(np,name,side_effect=AssertionError('Float '+name+' inside integer forward')))
        result = net.forward(tokens,cache)
    if any(v.dtype.kind not in 'iu' for v in result[1].values()):
        raise TypeError('Noninteger intermediate in fixed forward')
    return result


def float_forward(weights,tokens,cache=None):
    """FP32 observation path, cross-checked against the retained independent oracle."""
    import llama_numpy_reference as ref
    s = {'embed':weights['E'][tokens]}
    x = s['embed'];length = x.shape[1]
    offset = 0 if cache is None else cache[0].shape[2]
    s['norm1'] = ref.rms_norm(x,weights['gain1'],1e-5)
    for name in ('q','k','v'):
        s[name] = s['norm1']@weights[name.upper()].T
    def heads(a):return a.reshape(a.shape[0],length,2,16).transpose(0,2,1,3)
    def flat(a):return a.transpose(0,2,1,3).reshape(x.shape[0],length,32)
    positions = np.arange(offset,offset+length)
    def rotate(a):
        return np.stack([ref.rotary(batch,10000.,positions) for batch in heads(a)])
    q,k,v = rotate(s['q']),rotate(s['k']),heads(s['v'])
    s['qrot'],s['krot'] = flat(q),flat(k)
    if cache is not None:
        k = np.concatenate((cache[0],k),axis=2);v = np.concatenate((cache[1],v),axis=2)
    s['scores'] = (q@k.swapaxes(-1,-2))*np.float32(.25)
    future = np.arange(k.shape[2])[None,:]>positions[:,None]
    scores = np.where(future,np.float32(-np.inf),s['scores'])
    exp = np.exp(scores-scores.max(axis=-1,keepdims=True))
    s['prob'] = exp/exp.sum(axis=-1,keepdims=True,dtype=np.float32)
    s['context'] = flat(s['prob']@v)
    s['o'] = s['context']@weights['O'].T
    s['res1'] = x+s['o']
    s['norm2'] = ref.rms_norm(s['res1'],weights['gain2'],1e-5)
    for name in ('gate','up'):s[name] = s['norm2']@weights[name].T
    s['silu'] = ref.silu(s['gate'])
    s['hidden'] = s['silu']*s['up']
    s['down'] = s['hidden']@weights['down'].T
    s['res2'] = s['res1']+s['down']
    s['normfinal'] = ref.rms_norm(s['res2'],weights['gain3'],1e-5)
    s['logits'] = s['normfinal']@weights['E'].T
    if any(a.dtype!=np.float32 or not np.isfinite(a).all() for a in s.values()):
        raise FloatingPointError('Float observation path must be finite FP32')
    return s['logits'],s,(k,v)


class Fixed:
    """Static tensor exponents, explicit narrowing; no floats in forward()."""
    def __init__(self,weights,ranges,activation_bits=16):
        self.activation_bits = activation_bits
        self.we = {};self.q = {};self.e = {};self.stats = {}
        def exponent(m):return 0 if m==0 else math.ceil(math.log2(m/32767.))
        for name,value in weights.items():
            e = exponent(float(np.abs(value).max()))
            self.we[name] = e
            self.q[name] = np.rint(value.astype(np.float64)/2.**e).astype(np.int64)
            if maximum_abs(self.q[name])>32767:raise ValueError('Weight quantization clipped')
        for name in ACTIVATIONS:
            m = 2*ranges[name]
            self.e[name] = 0 if m==0 else math.ceil(math.log2(m/((1<<(activation_bits-1))-1)))
        self.e.update(embed=self.we['E'],scores=-16,prob=-15,logits=-16)
        position = np.arange(256,dtype=np.float64)[:,None]
        angle = position * (10000.**(-np.arange(8,dtype=np.float64)/8))[None,:]
        self.rope = np.rint(np.stack((np.cos(angle),np.sin(angle)),axis=-1)*2**14).astype(np.int64)
        self.exp_table = np.rint(np.exp(-np.arange(257,dtype=np.float64)*math.log(2)/256)*2**31).astype(np.int64)
        self.rsqrt_table = np.rint(2**30/np.sqrt(1+3*(np.arange(256)+.5)/256)).astype(np.int64)

    def narrow(self,name,value,bits=None,signed=True):
        if bits is None:bits = self.activation_bits
        lower,upper = (-(1<<(bits-1)),(1<<(bits-1))-1) if signed else (0,(1<<bits)-1)
        count = int(np.count_nonzero((value<lower)|(value>upper)))
        row = self.stats.setdefault(name,dict(values=0,saturated=0,min=0,max=0))
        row['values'] += value.size;row['saturated'] += count
        row['min'] = min(row['min'],int(value.min(initial=0)))
        row['max'] = max(row['max'],int(value.max(initial=0)))
        return np.clip(value,lower,upper)

    def cast(self,name,value,source,bits=None,signed=True):
        return self.narrow(name,shift(value,source-self.e[name]),bits,signed)

    def linear(self,x,source,weight,target,bits=None):
        return self.cast(target,dot(x,self.q[weight].T),source+self.we[weight],bits)

    def reciprocal_sqrt(self,r):
        if np.any(r<=0):raise ValueError('RMS denominator must be positive')
        # floor(log2(r)) using only integer comparisons and shifts.
        temp = r.copy();bits = np.zeros_like(r)
        for step in (32,16,8,4,2,1):
            mask = temp>=(1<<step)
            temp = np.where(mask,temp>>step,temp);bits += mask*step
        k = (bits-32)//2
        m = shift(r,-2-2*k)  # Q2.30 mantissa of r_real / 2**(2k).
        carry = m==(1<<32)
        m = np.where(carry,m>>2,m);k = k+carry
        index = np.minimum(((m-(1<<30))*256)//(3<<30),255)
        y = self.rsqrt_table[index]
        for _ in range(2):
            y2 = shift(multiply(y,y),-30)
            my2 = shift(multiply(m,y2),-30)
            y = shift(multiply(y,(3<<30)-my2),-31)
        return y,k

    def norm(self,x,source,gain,target):
        squares = multiply(x,x).sum(axis=-1,keepdims=True,dtype=np.int64)
        if maximum_abs(squares)>=2**47:raise OverflowError('RMS sum exceeds 48 bits')
        r = shift(squares,2*source+32-5)
        if maximum_abs(r)>2**63-1-42950:raise OverflowError('RMS epsilon addition exceeds signed scratch')
        r = r+42950
        y,k = self.reciprocal_sqrt(r)
        product = multiply(multiply(x,y),self.q[gain])
        return self.cast(target,product,source+self.we[gain]-30-k)

    def exp_negative(self,x):
        if np.any(x>0):raise ValueError('Exp range reduction must be nonpositive')
        if np.any(x<-2**62):raise OverflowError('Exp input exceeds checked negative scratch range')
        magnitude = np.minimum(-x,16*65536)
        power,remainder = np.divmod(magnitude,45426)
        index,fraction = np.divmod(remainder*256,45426)
        mantissa = self.exp_table[index]+divide((self.exp_table[index+1]-self.exp_table[index])*fraction,45426)
        result = shift(mantissa,-power)
        return np.where(-x>16*65536,0,result)

    def residual(self,a,ea,b,eb,target):
        base = min(ea,eb)
        left,right = shift(a,ea-base),shift(b,eb-base)
        if maximum_abs(left)+maximum_abs(right)>2**63-1:raise OverflowError('Residual alignment overflow')
        return self.cast(target,left+right,base)

    def forward(self,tokens,cache=None):
        if tokens.dtype.kind not in 'iu' or np.any(tokens<0) or np.any(tokens>=320):
            raise ValueError('Integer vocabulary IDs required')
        s = {'embed':self.q['E'][tokens]};x = s['embed'];batch,length,_ = x.shape
        offset = 0 if cache is None else cache[0].shape[2]
        if offset+length>256:raise ValueError('Context overflow')
        s['norm1'] = self.norm(x,self.we['E'],'gain1','norm1')
        for name in ('q','k','v'):
            s[name] = self.linear(s['norm1'],self.e['norm1'],name.upper(),name)
        def heads(a):return a.reshape(batch,length,2,16).transpose(0,2,1,3)
        def flat(a):return a.transpose(0,2,1,3).reshape(batch,length,32)
        positions = np.arange(offset,offset+length,dtype=np.int64)
        coefficients = self.rope[positions][None,None,:,:,:]
        def rotate(name):
            a = heads(s[name]);first,second = a[...,:8],a[...,8:]
            cosine,sine = coefficients[...,0],coefficients[...,1]
            both = np.concatenate((multiply(first,cosine)-multiply(second,sine),
                                   multiply(second,cosine)+multiply(first,sine)),axis=-1)
            return self.cast(name+'rot',flat(both),self.e[name]-14)
        s['qrot'],s['krot'] = rotate('q'),rotate('k')
        q,k,v = heads(s['qrot']),heads(s['krot']),heads(s['v'])
        if cache is not None:
            k = np.concatenate((cache[0],k),axis=2);v = np.concatenate((cache[1],v),axis=2)
        s['scores'] = self.cast('scores',dot(q,k.swapaxes(-1,-2)),self.e['qrot']+self.e['krot']-2,32)
        future = np.arange(k.shape[2])[None,:]>positions[:,None]
        maximum = np.where(future,-2**31,s['scores']).max(axis=-1,keepdims=True)
        delta = np.where(future,-16*65536-1,s['scores']-maximum)
        exp = self.exp_negative(delta)
        probability = divide(exp*32768,exp.sum(axis=-1,keepdims=True,dtype=np.int64))
        s['prob'] = self.narrow('prob',probability,16,False)
        s['context'] = self.cast('context',flat(dot(s['prob'],v)),self.e['prob']+self.e['v'])
        s['o'] = self.linear(s['context'],self.e['context'],'O','o')
        s['res1'] = self.residual(x,self.we['E'],s['o'],self.e['o'],'res1')
        s['norm2'] = self.norm(s['res1'],self.e['res1'],'gain2','norm2')
        for name in ('gate','up'):s[name] = self.linear(s['norm2'],self.e['norm2'],name,name)
        gate = s['gate'];g16 = shift(gate,self.e['gate']+16)
        decay = self.exp_negative(-np.abs(g16))
        denominator = (1<<31)+decay
        sigmoid = divide(np.where(gate>=0,1<<62,decay*(1<<31)),denominator)
        s['silu'] = self.cast('silu',multiply(gate,sigmoid),self.e['gate']-31)
        s['hidden'] = self.cast('hidden',multiply(s['silu'],s['up']),self.e['silu']+self.e['up'])
        s['down'] = self.linear(s['hidden'],self.e['hidden'],'down','down')
        s['res2'] = self.residual(s['res1'],self.e['res1'],s['down'],self.e['down'],'res2')
        s['normfinal'] = self.norm(s['res2'],self.e['res2'],'gain3','normfinal')
        s['logits'] = self.linear(s['normfinal'],self.e['normfinal'],'E','logits',32)
        return s['logits'],s,(k,v)

    def manifest(self):
        return dict(schema=1,implementation_sha256=implementation_sha256(),name='w16a'+str(self.activation_bits)+'-v3',matrix_bits=16,activation_bits=self.activation_bits,weight_exponents=self.we,activation_exponents=self.e,
                    rounding='nearest ties to even',narrowing='saturate and count',
                    dot_accumulator_bits=48,scratch_bits=64,nonnegative_scratch_limit=2**63-1,rope_fraction_bits=14,
                    exp_step='ln2/256',exp_range_reduce_ln2_Q16_16=45426,exp_cutoff=-16,exp_fraction_bits=31,
                    probability_fraction_bits=15,rsqrt_fraction_bits=30,rsqrt_iterations=2,
                    rms_epsilon_UQ32_32=42950,neural_forward='integer only',
                    float_work='offline calibration/tables and external token sampler',
                    parameters=sum(a.size for a in self.q.values()),
                    weight_bytes=2*sum(a.size for a in self.q.values()),kv_bytes=256*2*32*self.activation_bits//8)

    def freeze(self,folder):
        import runtime
        arrays = {n:a.astype('<i2') for n,a in self.q.items()}
        arrays.update(rope=self.rope.astype('<i2'),exp_table=self.exp_table.astype('<u4'),
                      rsqrt_table=self.rsqrt_table.astype('<u4'))
        import mlx.core as mx
        image = folder/'fixed-tensors.safetensors'
        mx.save_safetensors(str(image),{name:mx.array(value) for name,value in arrays.items()})
        manifest = self.manifest()
        manifest['images'] = dict(file=image.name,sha256=runtime.sha(image),bytes=image.stat().st_size,
                                  arrays={n:dict(shape=list(a.shape),dtype=a.dtype.str,bytes=a.nbytes) for n,a in arrays.items()})
        runtime.save(folder/'arithmetic.json',manifest)
        # Strict local SafeTensors reload; no pickle, remote code or object arrays.
        saved = mx.load(str(image))
        if set(saved)!=set(arrays):raise ValueError('Converted image keys changed')
        for name,value in arrays.items():
            actual = np.array(saved[name])
            if actual.dtype!=value.dtype or not np.array_equal(actual,value):
                raise ValueError('Converted image exact reload failed')
            if name in self.q:self.q[name] = actual.astype(np.int64)
            else:setattr(self,name,actual.astype(np.int64))

        return dict(manifest_sha256=runtime.sha(folder/'arithmetic.json'),**manifest)


def primitive_checks():
    """Independent scalar oracles, adversarial ranges and nonlinear error probes."""
    dependencies()
    rng = np.random.default_rng(947)
    checks = 0
    for denominator in (1,2,4,8,127,1024,1<<31,1<<39):
        values = np.concatenate((rng.integers(-2**45,2**45,512,dtype=np.int64),
                                 np.array([-5,-3,-1,0,1,3,5],dtype=np.int64)*(denominator//2)))
        expected = [scalar_rne(int(x),denominator) for x in values]
        np.testing.assert_array_equal(divide(values,denominator),expected);checks += len(values)
    for length,bits in ((16,16),(32,16),(128,16),(256,16),(32,18),(256,18)):
        bound = 1<<(bits-1)
        a = rng.integers(-bound,bound,(4,length),dtype=np.int64)
        b = rng.integers(-bound,bound,(length,5),dtype=np.int64)
        a[0,:] = -bound;b[:,0] = -bound
        expected = [[sum(int(x)*int(y) for x,y in zip(row,b[:,j])) for j in range(5)] for row in a]
        np.testing.assert_array_equal(dot(a,b),expected);checks += 20
    from fractions import Fraction
    for amount in (-40,-16,-1,0,1,16):
        values = rng.integers(-2**20,2**20,128,dtype=np.int64)
        expected = [round(Fraction(int(v))*Fraction(2)**amount) for v in values]
        np.testing.assert_array_equal(shift(values,amount),expected);checks += len(values)
    dummy = Fixed.__new__(Fixed);dummy.stats = {};dummy.activation_bits = 16
    dummy.exp_table = np.rint(np.exp(-np.arange(257)*math.log(2)/256)*2**31).astype(np.int64)
    dummy.rsqrt_table = np.rint(2**30/np.sqrt(1+3*(np.arange(256)+.5)/256)).astype(np.int64)
    x = np.arange(-16*65536,1,97,dtype=np.int64)
    actual = dummy.exp_negative(x).astype(np.float64)/2**31
    relative = float(np.max(np.abs(actual/np.exp(x/65536)-1)))
    if relative>.003:
        worst = int(np.argmax(np.abs(actual/np.exp(x/65536)-1)))
        raise AssertionError(f'Exp interpolation relative error {relative} at encoded input {int(x[worst])} exceeds .003')
    r = np.unique(np.rint(np.geomspace(42950,2**48,4096)).astype(np.int64))
    y,k = dummy.reciprocal_sqrt(r)
    relative_rsqrt = float(np.max(np.abs((y.astype(np.float64)/2**30)*2.**(-k)*np.sqrt(r/2**32)-1)))
    if relative_rsqrt>1e-7:raise AssertionError('Reciprocal sqrt error exceeds primitive limit')
    np.testing.assert_array_equal(dummy.exp_negative(np.array([0,-16*65536,-16*65536-1])),[2**31,242,0])
    saturated = dummy.narrow('adversarial',np.array([-40000,-32768,32767,40000]))
    np.testing.assert_array_equal(saturated,[-32768,-32768,32767,32767])
    assert dummy.stats['adversarial']['saturated']==2
    try:dot(np.full((1,256),2**30,dtype=np.int64),np.full((256,1),2**30,dtype=np.int64))
    except OverflowError:pass
    else:raise AssertionError('Accumulator overflow not rejected before host calculation')
    return dict(integer_oracle_cases=checks,exp_max_relative_error=relative,
                rsqrt_max_relative_error=relative_rsqrt,overflow_rejected=True,saturation_count_checked=True)


def sample(net,seeds,recipe,progress=False):
    import model
    rows = [dict(seed=s,tokens=[],eos=False) for s in seeds]
    rng = [np.random.default_rng(s) for s in seeds]
    live = list(range(len(rows)));tokens = np.full((len(live),1),256,dtype=np.int64)
    cache = None;started = time.perf_counter()
    for position in range(255):
        logits,_,cache = integer_call(net,tokens,cache)
        logits = logits[:,0,:].astype(np.float64)/65536
        following = [];keep = []
        for j,index in enumerate(live):
            if position<recipe['sample_bytes']:
                z = logits[j]/recipe['temperature'];z -= z.max()
                probabilities = np.exp(z);probabilities /= probabilities.sum()
                token = min(int(np.searchsorted(np.cumsum(probabilities),rng[index].random(),side='right')),319)
            else:token = int(logits[j].argmax())
            if token==257:rows[index]['eos'] = True
            else:
                rows[index]['tokens'].append(token);following.append(token);keep.append(j)
        if not keep:break
        live = [live[j] for j in keep]
        cache = (cache[0][keep],cache[1][keep])
        tokens = np.asarray(following,dtype=np.int64)[:,None]
        if progress and position%50==49:print('fixed decode position '+str(position+1)+', active '+str(len(live)),flush=True)
    for row in rows:row['text'],row['valid_utf8_bytes'] = model.decode(row['tokens'])
    return dict(results=rows,seconds=time.perf_counter()-started,recipe=recipe,model_input_tokens=[256],
                joke_identifiers=False,answer_bank_in_generation=False,output_constraints=False,
                host_sampling='FP64 softmax/inverse-CDF with independent NumPy RNG per seed')


def accepts(quality,numerical,stats,policy):
    """Teaching selection keeps normalized accuracy; strict also gates absolute error."""
    if policy not in ('strict','teaching'):raise ValueError('Unknown acceptance policy')
    normalized = numerical['by_operation']['logits']['worst_normalized_RMSE']<=.01
    return (quality and normalized and not any(v['saturated'] for v in stats.values())
            and (numerical['passed'] or policy=='teaching'))


def study(meta,rows,report,folder,load_selected,recipe,activation_bits=16,acceptance='strict'):
    import model
    import runtime
    import llama_numpy_reference as ref
    dependencies();start = time.perf_counter()
    study_report = report['fixed'] = dict(candidate='w16a'+str(activation_bits)+'-v3',acceptance_policy=acceptance,phases={},final_seeds_consumed=False,
        confirmation_role='matched comparison on seeds already examined for q8/W16A18; not a fresh holdout')
    def phase(name,value):
        study_report['phases'][name] = dict(elapsed_seconds=time.perf_counter()-start,**value)
        runtime.save(folder/'results.json',report)
        print(name+': '+str({k:v for k,v in value.items() if k not in ('results','states')}),flush=True)
    phase('primitives',primitive_checks())
    native = load_selected(meta)
    study_report['control_numerics'] = model.numerical(native,rows)
    original,_ = model.numpy_weights(native)
    weights = {short:original[full] for short,full in NAMES.items()}
    class OracleWeights:
        def shape(self,name):return original[name].shape
        def get(self,name,rows=None):return original[name] if rows is None else original[name][rows]
    probes = [(rows[0],1),(rows[2],18),(rows[47],63)]
    probes += [(row,len(model.sequence(row))-1) for row in rows]
    for row,length in probes:
        ids = model.sequence(row)[:length]
        actual,_,_ = float_forward(weights,np.asarray([ids],dtype=np.int64))
        expected = ref.forward(OracleWeights(),model.config(),ids)
        np.testing.assert_allclose(actual[0,-1],expected,atol=.002,rtol=.0002)
    phase('float_observation_oracle',dict(initial_prefix_lengths=[1,18,63],all48_teacher_endpoints=True,checks=len(probes),passed=True))
    development = list(range(2001,2065))
    control = model.grade(model.sample(native,development,recipe),rows)
    study_report['control_development'] = control
    paths = [model.sequence(r)[:-1] for r in rows]
    paths += [[256,*r['tokens']] for r in control['results']]
    ranges = dict.fromkeys(ACTIVATIONS,0.)
    for ids in paths:
        _,states,_ = float_forward(weights,np.asarray([ids],dtype=np.int64))
        for name in ranges:ranges[name] = max(ranges[name],float(np.abs(states[name]).max()))
    net = Fixed(weights,ranges,activation_bits=activation_bits)
    study_report['calibration'] = dict(teacher_sequences=48,teacher_prefixes=4535,
                                      development_seeds=development,activation_maxima=ranges,headroom=2)
    phase('calibration',dict(paths=len(paths),weight_bytes=53440,exponents=net.e))
    metrics = {};prefixes = 0;all_pass = True
    def compare(ids):
        nonlocal prefixes,all_pass
        tokens = np.asarray([ids],dtype=np.int64)
        _,floating,_ = float_forward(weights,tokens)
        _,fixed,_ = integer_call(net,tokens)
        prefixes += len(ids)
        for name,actual in fixed.items():
            expected = floating[name].astype(np.float64)
            decoded = actual.astype(np.float64)*2.**net.e[name]
            error = decoded-expected
            metric = metrics.setdefault(name,dict(values=0,max_abs=0.,sum_squared=0.,top_equal=0,top_count=0))
            metric['values'] += error.size;metric['sum_squared'] += float(np.square(error).sum())
            metric['max_abs'] = max(metric['max_abs'],float(np.abs(error).max()))
            if name=='logits':
                relative = np.sqrt(np.mean(error*error,axis=-1))/np.maximum(1,np.sqrt(np.mean(expected*expected,axis=-1)))
                metric['worst_normalized_RMSE'] = max(metric.get('worst_normalized_RMSE',0.),float(relative.max()))
                metric['top_equal'] += int(np.count_nonzero(decoded.argmax(axis=-1)==expected.argmax(axis=-1)))
                metric['top_count'] += len(ids)
                all_pass &= bool(relative.max()<=.01 and np.abs(error).max()<=.1)
    for i,ids in enumerate(paths):
        compare(ids)
        if i%16==15:print('numerical paths '+str(i+1)+'/'+str(len(paths)),flush=True)
    dev = model.grade(sample(net,development,recipe,progress=True),rows)
    study_report['development'] = dev
    for row in dev['results']:compare([256,*row['tokens']])
    for metric in metrics.values():metric['RMSE'] = math.sqrt(metric.pop('sum_squared')/metric['values'])
    study_report['numerical'] = dict(prefix_evaluations=prefixes,by_operation=metrics,passed=all_pass)
    study_report['development_saturation'] = {k:dict(v) for k,v in net.stats.items()}
    saturation = sum(v['saturated'] for v in net.stats.values())
    strict_dev = all_pass and saturation==0 and model.qualifies(dev)
    accepted_dev = accepts(model.qualifies(dev),study_report['numerical'],net.stats,acceptance)
    phase('development_gate',dict(accepted=accepted_dev,strict_accepted=strict_dev,policy=acceptance,numerical=all_pass,saturations=saturation,
                                  exact=dev['exact'],unique=dev['unique_exact'],largest=dev['largest_joke_count']))
    # Context/cache tests use teacher prefixes only, and are checked separately.
    cache_checks = []
    net.stats = {}
    for length in (1,18,63,255,256):
        base = model.sequence(rows[47])[:-1]
        ids = (base*((length+len(base)-1)//len(base)))[:length]
        full,_,full_cache = integer_call(net,np.asarray([ids],dtype=np.int64))
        cached = None
        for token in ids:last,_,cached = integer_call(net,np.asarray([[token]],dtype=np.int64),cached)
        np.testing.assert_array_equal(full[0,-1],last[0,-1])
        for a,b in zip(full_cache,cached):np.testing.assert_array_equal(a,b)
        cache_checks.append(len(ids))
    try:integer_call(net,np.asarray([[0]],dtype=np.int64),cached)
    except ValueError:pass
    else:raise AssertionError('257th cache position was accepted')
    phase('cache_checks',dict(prefix_lengths=cache_checks,bit_exact=True,
                              contexts_255_256='synthetic repeated training tokens, including BOS',
                              saturation={k:dict(v) for k,v in net.stats.items()},context_overflow_rejected=True))
    if any(v['saturated'] for v in net.stats.values()):raise ValueError('Context checks saturated')
    study_report['candidate'] = net.freeze(folder)
    study_report['teaching_projection'] = projection_trace(net)
    if not accepted_dev:
        study_report['accepted'] = False;report['accepted'] = False
        print('Development gate failed. Final seeds were not evaluated.',flush=True)
        return
    frozen_hashes = {name:runtime.sha(folder/name) for name in ('arithmetic.json','fixed-tensors.safetensors')}
    phase('frozen',dict(hashes=frozen_hashes))
    net.stats = {}
    study_report['final_seeds_consumed'] = True
    runtime.save(folder/'results.json',report)
    final_seeds = list(range(20001,20129))
    final = model.grade(sample(net,final_seeds,recipe,progress=True),rows)
    stock_final = model.grade(model.sample(native,final_seeds,recipe),rows)
    study_report['confirmation'] = final;study_report['control_confirmation'] = stock_final
    study_report['confirmation_saturation'] = {k:dict(v) for k,v in net.stats.items()}
    if any(runtime.sha(folder/name)!=digest for name,digest in frozen_hashes.items()):
        raise ValueError('Frozen arithmetic changed during confirmation')
    saturation = sum(v['saturated'] for v in net.stats.values())
    # Post-freeze comparison on actual confirmation paths; no recalibration or tuning.
    metrics = {};prefixes = 0;all_pass = True
    net.stats = {}
    for row in final['results']:compare([256,*row['tokens']])
    for metric in metrics.values():metric['RMSE'] = math.sqrt(metric.pop('sum_squared')/metric['values'])
    study_report['confirmation_numerical'] = dict(prefix_evaluations=prefixes,by_operation=metrics,passed=all_pass,
        saturation={k:dict(v) for k,v in net.stats.items()})
    strict_final = (model.qualifies(final,final=True) and saturation==0 and all_pass
                    and not any(v['saturated'] for v in net.stats.values()))
    accepted = (accepts(model.qualifies(final,final=True),study_report['confirmation_numerical'],net.stats,acceptance)
                and saturation==0)
    study_report['strict_accepted'] = strict_dev and strict_final
    study_report['accepted'] = accepted;report['accepted'] = accepted
    study_report['confirmation_same_tokens_as_q8'] = sum(a['tokens']==b['tokens'] and a['eos']==b['eos'] for a,b in zip(final['results'],stock_final['results']))
    phase('confirmation_gate',dict(accepted=accepted,strict_accepted=study_report['strict_accepted'],policy=acceptance,exact=final['exact'],unique=final['unique_exact'],
                                   largest=final['largest_joke_count'],saturations=saturation,
                                   seconds=time.perf_counter()-start))


def selected(meta):
    import runtime
    path = runtime.MODEL/'fixed.json'
    if runtime.sha(path)!=SELECTED_SHA256:raise ValueError('Fixed selection manifest changed')
    manifest = runtime.read(path)
    if manifest['implementation_sha256']!=implementation_sha256():
        raise ValueError('Fixed arithmetic implementation changed')
    if (manifest['runtime_path']!='models/tiny/fixed'
            or manifest['images']['file']!='fixed-tensors.safetensors'
            or manifest['source_q8_sha256']!=meta['weights']['q8']['files']['model.safetensors']['sha256']):
        raise ValueError('Unreviewed fixed payload location or origin')
    image = runtime.RUNTIME/manifest['runtime_path']/manifest['images']['file']
    if image.stat().st_size!=manifest['images']['bytes'] or runtime.sha(image)!=manifest['images']['sha256']:
        raise ValueError('Missing or modified fixed SafeTensors payload')
    dependencies()
    import mlx.core as mx
    saved = mx.load(str(image))
    expected = manifest['images']['arrays']
    if set(saved)!=set(expected):raise ValueError('Fixed tensor keys differ')
    net = Fixed.__new__(Fixed)
    net.we = manifest['weight_exponents'];net.e = manifest['activation_exponents']
    net.activation_bits = manifest['activation_bits'];net.q = {};net.stats = {}
    for name,info in expected.items():
        value = np.array(saved[name])
        if list(value.shape)!=info['shape'] or value.dtype.str!=info['dtype'] or value.nbytes!=info['bytes']:
            raise ValueError('Fixed tensor shape or dtype differs')
        value = value.astype(np.int64)
        if name in NAMES:net.q[name] = value
        elif name in ('rope','exp_table','rsqrt_table'):setattr(net,name,value)
        else:raise ValueError('Unreviewed integer tensor')
    for key,value in net.manifest().items():
        if manifest[key]!=value:raise ValueError('Fixed arithmetic contract differs: '+key)
    return net,manifest


def projection_trace(net):
    """Actual first Q output, independently checked with unbounded Python integers."""
    _,states,_ = integer_call(net,np.asarray([[256]],dtype=np.int64))
    x = states['norm1'][0,0];w = net.q['Q'][0]
    products = [int(a)*int(b) for a,b in zip(x,w)]
    running = [];total = 0
    for product in products:total += product;running.append(total)
    source = net.e['norm1']+net.we['Q'];amount = source-net.e['q']
    expected = scalar_rne(total,1<<-amount) if amount<0 else total*(1<<amount)
    if expected!=int(states['q'][0,0,0]):raise ValueError('Real Q-row Python-integer oracle failed')
    return dict(input_token=256,activation_bits=net.activation_bits,weight_bits=16,
                input_values=x.tolist(),weight_values=w.tolist(),products=products,partial_sums=running,
                accumulator=total,accumulator_exponent=source,output=expected,output_exponent=net.e['q'])


def verify_selected(meta,rows,recipe):
    import hashlib
    import json
    import model
    net,manifest = selected(meta)
    primitives = primitive_checks()
    net.stats = {}
    result = model.grade(sample(net,list(range(20001,20129)),recipe),rows)
    for row in result['results']:
        value = json.dumps([row['tokens'],row['eos']],separators=(',',':')).encode()
        if hashlib.sha256(value).hexdigest()!=manifest['study']['token_sha256'][str(row['seed'])]:
            raise ValueError('Frozen fixed-point token sequence changed')
    if not model.qualifies(result,final=True) or any(v['saturated'] for v in net.stats.values()):
        raise ValueError('Frozen fixed-point gate failed')
    answer = dict(regression=result,primitives=primitives,zero_saturation=True,
                  real_projection=projection_trace(net))

    if answer['real_projection']!=manifest['teaching_projection']:
        raise ValueError('Pinned real projection trace changed')
    return answer
