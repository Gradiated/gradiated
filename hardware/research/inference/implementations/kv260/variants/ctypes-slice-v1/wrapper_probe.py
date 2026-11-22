"""Compare two score extraction expressions in the pinned native session."""

import ast
from contextlib import ExitStack, contextmanager
import gc
import resource
from statistics import median
import time
from types import MethodType
from unittest.mock import patch


def orders(bench, index):
    first = bench.FORWARD[index]
    second = bench.REVERSE[index]
    pivot = second.index(first[-1]) + 1
    second = second[pivot:] + second[:pivot]
    return ([(case, False) for case in first],
            [(case, True) for case in first + second],
            ("stock", "slice") if index%2 == 0 else ("slice", "stock"))


def tail_order(bench):
    order = bench.FORWARD[0] + bench.REVERSE[1] + bench.FORWARD[2] + bench.REVERSE[0]
    return [(case, True) for case in order]


def extraction_methods(session, source):
    """Compile the pinned step twice, changing one exact expression for the candidate."""
    original = type(session).step
    source = source.decode('utf-8')
    marker = "'context_count': self.context_count, 'logits': list(values)}"
    if source.count(marker) != 1:
        raise ValueError('Pinned extraction expression differs')

    def step_from(text):
        tree = ast.parse(text)
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'NativeSession')
        step = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == 'step')
        if step.lineno != original.__code__.co_firstlineno or step.decorator_list or step.args.defaults:
            raise ValueError('Loaded step differs from sealed source')
        namespace = {}
        exec(compile(ast.Module(body=[step], type_ignores=[]), original.__code__.co_filename, 'exec'),
             original.__globals__, namespace)
        return namespace['step']

    stock = step_from(source)
    if any(getattr(stock.__code__, name) != getattr(original.__code__, name)
           for name in ('co_code', 'co_consts', 'co_names', 'co_varnames')):
        raise ValueError('Compiled stock step differs from the loaded implementation')
    sliced = step_from(source.replace(marker, marker.replace('list(values)', 'values[:]')))
    return {name: MethodType(method, session) for name, method in [('stock', stock), ('slice', sliced)]}


@contextmanager
def selected_step(runner, methods, mode):
    # Both arms use the same bound-method dispatch path with no per-score wrapper.
    with patch.object(runner.session, 'step', methods[mode]):
        yield


def thread_counters():
    usage = resource.getrusage(resource.RUSAGE_THREAD)
    return {name: getattr(usage, name) for name in ('ru_minflt', 'ru_majflt', 'ru_nvcsw', 'ru_nivcsw')}


@contextmanager
def tail_observers(now, bench, sections, counter_reader=thread_counters, cpu=time.thread_time_ns):
    phases = {'exact_check': [], 'receipt_digest': []}
    gc_events, open_events = [], []

    def callback(phase, info):
        if phase == 'start':
            open_events.append((now(), info['generation']))
        elif open_events:
            start, generation = open_events.pop()
            gc_events.append({'begin_ns':start, 'end_ns':now(), 'generation':generation,
                              'collected':info['collected'], 'uncollectable':info['uncollectable']})

    def observer(fn, name):
        def timed(*args, **kwargs):
            first = counter_reader()
            begin = now()
            before_cpu = cpu()
            value = fn(*args, **kwargs)
            after_cpu = cpu()
            end = now()
            last = counter_reader()
            phases[name].append({'begin_ns':begin, 'end_ns':end, 'cpu_ns':after_cpu-before_cpu,
                                 'events':{key:last[key]-first[key] for key in first}})
            return value
        return timed

    bench_globals = bench.run_block.__globals__
    sections_globals = sections.measured_block.__globals__
    settings = {'enabled':gc.isenabled(), 'threshold':list(gc.get_threshold())}
    with ExitStack() as changes:
        gc.callbacks.append(callback)
        changes.callback(gc.callbacks.remove, callback)
        changes.enter_context(patch.dict(bench_globals, {'check_actual':observer(bench_globals['check_actual'], 'exact_check')}))
        changes.enter_context(patch.dict(sections_globals, {'digest':observer(sections_globals['digest'], 'receipt_digest')}))
        yield {'phases':phases, 'gc_events':gc_events, 'gc_settings':settings}


def group(block):
    result = {}
    for row in block['requests']:
        t = row['timing']
        timings = result.setdefault(row['case'], {})
        for name, ns in {'ttft':t['first_byte_ns']-row['admitted_ns'],
                         'generation':t['inference_end_ns']-t['inference_begin_ns'],
                         'verified':row['verified_ns']-row['admitted_ns'],
                         'verification_tail':row['verified_ns']-row['returned_ns']}.items():
            timings.setdefault(name, []).append(ns/1e6)
    return {case:{name:median(values) for name, values in timings.items()} for case, timings in result.items()}


def check_tail(block, probes, require):
    phases = probes['phases']
    require(set(phases) == {'exact_check', 'receipt_digest'}
            and all(len(s) == len(block['requests']) for s in phases.values()), 'Tail probe count differs')
    points = ['ru_minflt', 'ru_majflt', 'ru_nvcsw', 'ru_nivcsw']
    for row, exact, digest in zip(block['requests'], phases['exact_check'], phases['receipt_digest'], strict=True):
        positions = [row['returned_ns'], exact['begin_ns'], exact['end_ns'], digest['begin_ns'],
                     digest['end_ns'], row['verified_ns']]
        require(positions == sorted(positions), 'Tail probe boundaries differ')
        for part in (exact,digest):
            require(type(part['cpu_ns']) is int and 0 <= part['cpu_ns'] <= part['end_ns']-part['begin_ns']
                    and set(part['events']) == set(points)
                    and all(type(value) is int and value >= 0 for value in part['events'].values()), 'Tail probe counters differ')
    for event in probes['gc_events']:
        require(type(event['generation']) is int and 0 <= event['generation'] <= 2
                and event['begin_ns'] <= event['end_ns'], 'GC receipt differs')


def conversion_trial(module, values, order):
    """Component-only timings. No device, session or inference is accessed."""
    native = (module.c_int32*320)(*values)
    assert all(type(item) is int for item in native[:]) and native[:] == list(native) == values
    extract = {'stock':lambda: list(native), 'slice':lambda: native[:]}
    samples = []
    for mode in order:
        convert = extract[mode]
        start = time.perf_counter_ns()
        for i in range(4000):
            convert()
        samples.append({'mode':mode, 'loops':4000, 'elapsed_ns':time.perf_counter_ns()-start})
    return samples
