"""Materialise the exact prior UART, sampler and restoration paths for AU01.

The original qualification packet is unchanged. The replacements apply only
before freezing the new local packet. Each changed source is hashed separately.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path


SUPPORT = (
    "uart_transport.py", "wrapper_host.py", "wrapper_validation.py",
    "resident_validation.py", "benchmark_validation.py",
    "board_resident.py", "board_resident_benchmark.py",
    "energy_validation.py", "energy_analysis.py", "power_sampler.py",
    "kv260_accept.py", "kv260_speed_inventory.py",
)
FIRMWARE = "gradiated-tiny-autonomous-v1-50mhz.bit.bin"
OVERLAY_NAME = "gradiated-tiny-autonomous-v1-program"
DTBO = "kv260-autonomous-program.dtbo"
COMPANION = "autonomous_mmio.so"
PROTOCOL = "kv260-autonomous-v1.md"

ARM = '''    def check_native_deadline(runner):
        for callback in (runner.session.step, runner.session.clear):
            require(callback.__func__.__globals__.get('CALL_BUDGET_NS')==runtime.DEADLINE_NS,
                    'Verified native call lost its deadline parameter')

    def arm(directory, pair, mode):
        warmup, scheduled = cases(bench,pair)
        sampler,path = (stock_sampler,HERE/'power_sampler.py') if mode==STOCK else (obs_sampler,HERE/'observer_sampler.py')
        launcher = base_code.source(HERE/'energy_validation.py',base_code.SUPPORT['energy_validation.py'])
        launcher.run_arm.__globals__['POWER_SAMPLER_PIN'] = assets['sources'][path.name]
        launcher.run_arm.__globals__['block_summary'] = comparison.block_summary
        bundle = prior.CANDIDATE if mode==STOCK else observer_bundle
        with lifecycle.open_arm(mode,resident,bundle,bundle_pin) as runner:
            load = load_metadata(runner)
            validate_load(load,prior)
            energy.dump(directory/'load.json',load)
            port = None if mode==STOCK else runtime.Port(runner.session,HERE/lifecycle.OBS_ELF)
            delivery = comparison.DeliveryBenchmark(runtime,port,deadline_ns=deadline_ns)
            if mode==STOCK:
                sealed_source = resident.read_pinned(bundle/'board_bos.py',resident.SEALED_RUNNER_SHA256)
                methods = probe.extraction_methods(runner.session,sealed_source)
                step_scope = probe.selected_step(runner,methods,'slice')
            else:
                step_scope = nullcontext()
            with step_scope:
                check_native_deadline(runner)
                result = launcher.run_arm(directory,runner,(warmup,scheduled,'on'),reference,delivery,remaining,
                                          sampler,analysis,path)
            require(runner.requests==9,'Autonomous/control arm request count differs')
            return {'mode':mode,'pair':pair,'qualified_logger':result}

    def smoke(directory):
        expected_cases = [(case,False) for case in bench.CASES]
        with lifecycle.open_arm(OBSERVER,resident,observer_bundle,bundle_pin) as runner:
            check_native_deadline(runner)
            load = load_metadata(runner)
            validate_load(load,prior)
            energy.dump(directory/'load.json',load)
            full,examples = bench.run_block(runner,expected_cases,reference,remaining,capture_examples=True)
            require(set(examples)==set(bench.CASES),'Missing candidate diagnostic frames')
            energy.dump(directory/'fullscore.json',full)
            # The board already compared every signed value. Preserve full
            # score frame digests to independently check each position on Mac.
            port = runtime.Port(runner.session,HERE/lifecycle.OBS_ELF)
            delivery = comparison.DeliveryBenchmark(runtime,port,deadline_ns=deadline_ns)
            compact,_ = delivery.run_block(runner,expected_cases,reference,remaining)
            energy.dump(directory/'compact.json',compact)
            for cap in (1,0):
                name = 'encoded-hello'
                short = {name:comparison.capped_reference(reference[name],cap)}
                limited = comparison.DeliveryBenchmark(runtime,port,max_output=cap,deadline_ns=deadline_ns)
                block,_ = limited.run_block(runner,[(name,False)],short,remaining)
                energy.dump(directory/f'limit-{cap}.json',block)
            require(runner.requests==8,'Diagnostic/compact/cap smoke request count differs')
        return {'diagnostic_requests':3,'compact_requests':3,'cap_requests':2}

'''

CHECK_EXPORT = '''    else:
        ready = get('load')
        validate_load(ready,prior)
        runtime = modules['autonomous_runtime']
        comparison = modules['autonomous_comparison']
        index,prev,earliest = 0,0,ready['timing']['ready_ns']
        if kind=='smoke':
            cases_ = [(case,False) for case in bench.CASES]
            refs = {name:bench.compact(completion) for name,completion in fresh.items()}
            index,prev,earliest = bench.validate_block(get('fullscore'),cases_,refs,index,prev,earliest)
            index,prev,earliest = comparison.check_block(runtime,get('compact'),cases_,fresh,True,index,prev,earliest)
            for cap in (1,0):
                name = 'encoded-hello'
                short = {name:comparison.capped_reference(fresh[name],cap)}
                index,prev,earliest = comparison.check_block(runtime,get(f'limit-{cap}'),[(name,False)],
                                                             short,True,index,prev,earliest)
            require(index==8,'Diagnostic/compact/cap smoke schedule differs')
            result = {'diagnostic_requests':3,'compact_requests':3,'cap_requests':2}
        else:
            require(kind=='arm','Unknown autonomous arm')
            warmup_cases,timed_cases = cases(bench,pair)
            warmup,block,summary = get('warmup'),get('block'),get('arm')
            candidate = before==OBSERVER
            index,prev,earliest = comparison.check_block(runtime,warmup,warmup_cases,fresh,candidate,index,prev,earliest)
            context = prev
            index,prev,earliest = comparison.check_block(runtime,block,timed_cases,fresh,candidate,index,prev,earliest)
            result = {'mode':before,'pair':pair,'qualified_logger':{
                      'warmup':comparison.block_summary(warmup,{}),'block':comparison.block_summary(block,{}),
                      'mode':'on','idle_context':context}}
            require(index==9 and summary['mode']=='on' and summary['pid']==ready['pid']
                    and summary['candidate_begins']==1 and summary['idle_context']==context==prev
                    and warmup['requests'][-1]['case']==block['requests'][-1]['case'],
                    'Autonomous arm schedule, idle context or resident identity differs')
            sampler = modules['observer_sampler'] if candidate else modules['power_sampler']
            origin,phases = summary['schedule_start_ns'],summary['phases']
            last_start,last_end = block['begin_ns'],block['end_ns']
            require(warmup['end_ns']<summary['sampler_ready_ns']<origin and origin+3_000_000_000<=last_start
                    and last_end+2_650_000_000<summary['window_end_ns']==origin+analysis.WINDOW_NS
                    and phases=={'active':[last_start,last_end], 'idle_before':[origin+500_000_000,origin+2_500_000_000],
                                 'idle_after':[last_end+500_000_000,last_end+2_500_000_000]},
                    'Autonomous power boundary differs')
            condition = summary['before']
            require(condition==summary['after'] and condition['sensor']==sampler.SENSOR_STATE
                    and condition['srcversion']=='E3E534E022E8AD6F9699980'
                    and condition['health']==[baseline['boot_id'],'6.8.0-1015-xilinx','0',
                                              'operating','0',lifecycle.image_spec(before)[0]],
                    'Autonomous power sensor identity differs')
            started,trace = raw('sampler.stdout').split(b'\\n',1)
            require(started==b'READY' and get('sampler-process')=={'exit':0}
                    and not raw('sampler.stderr'),'Autonomous sampler exit differs')
            trace = json.loads(trace)
            reads = analysis.check_power(trace,origin,condition,summary['after'])
            counts = result['qualified_logger']['block']
            require(counts['requests']==6 and counts['output_bytes']==632,'Autonomous block denominator differs')
            rail = analysis.rail(reads,phases,counts['requests'],counts['output_bytes'])
            require(rail['admitted'],'Autonomous power coverage rejected')
            extra = {'timing':comparison.timings(block),'rail':rail,'power_samples':len(reads),
                     'missed':len(trace['missed'])}
'''


def cut(text, left, right, replacement):
    start = text.index(left)
    end = text.index(right, start + len(left))
    return text[:start] + replacement + text[end:]


def replace(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f"Expected one replacement point for {old!r}")
    return text.replace(old, new)


def put(folder, name, contents):
    with (folder / name).open("xb") as stream:
        stream.write(contents)


def read_pinned(folder, name, pin):
    path = folder / name
    data = path.read_bytes()
    if path.is_symlink() or sha256(data).hexdigest() != pin:
        raise ValueError(f"Prior reviewed source differs: {path}")
    return data


def main(prior, destination, host, probe_source):
    previous = json.loads(read_pinned(prior, "invocation.json",
                                      "912cdc0af81989f8f0b9b14ddfc1817f69516466bc32a6843cfa62c2a8271c2e"))
    known = previous["sources"]
    destination.mkdir(mode=0o700)
    put(destination, "prepare_support.py", Path(__file__).read_bytes())
    for name in SUPPORT:
        put(destination, name, read_pinned(prior, name, known[name]))
    for name in ("autonomous_runtime.py", "autonomous_comparison.py", "test_autonomous_runtime.py",
                 "test_autonomous_comparison.py", "autonomous_mmio.c", "native_clear_tb.c"):
        put(destination, name, (host / name).read_bytes())
    probe = read_pinned(probe_source.parent, probe_source.name,
                        "b55abb0ef97b9d0daea431e702c7b0fc8246b8676444f27e081d038bb542557e")
    put(destination, "wrapper_probe.py", probe)
    firmware_names = {
        "gradiated-tiny-observer-v1-50mhz.bit.bin": FIRMWARE,
        "gradiated-tiny-observer-v1-program": OVERLAY_NAME,
        "kv260-observer-program.dtbo": DTBO,
        "observer_read.so": COMPANION,
    }
    life = read_pinned(prior, "observer_lifecycle.py", known["observer_lifecycle.py"]).decode()
    for old, new in firmware_names.items():
        life = replace(life, old, new)
    life = life.replace("'observer'", "'candidate'").replace(
        "Verified runtime overlay transitions for the single KV260 observer image.",
        "Verified runtime overlay transitions for the KV260 autonomous comparison image.")
    life = life[:life.index("\ndef read_counters(")]
    put(destination, "observer_lifecycle.py", life.encode())

    supervisor = read_pinned(prior, "observer_validation.py", known["observer_validation.py"]).decode()
    supervisor = supervisor.replace("'observer'", "'candidate'").replace("KV_OBS_", "KV_AUT_").replace(
        "Independent board gates for the original and observation-only images.",
        "Independent board gates for the original and autonomous KV260 images.")
    supervisor = replace(supervisor, "import argparse\n", "import argparse\nfrom contextlib import nullcontext\n")
    supervisor = cut(supervisor, "\ndef compare_pairs(", "\ndef validate_load(",
                     "\ndef compare_pairs(gates, comparison):\n    return comparison.comparison(gates)\n\n")
    supervisor = supervisor.replace("    validator = modules['validate_snapshot'].validate_snapshot\n",
                                    "    runtime, comparison, probe = (modules[name] for name in "
                         "('autonomous_runtime','autonomous_comparison','wrapper_probe'))\n", 1)
    supervisor = replace(supervisor, "    deadline = time.monotonic() + INNER_SECONDS",
                         "    deadline_ns = time.monotonic_ns() + INNER_SECONDS * 1_000_000_000\n"
                         "    deadline = deadline_ns / 1_000_000_000")
    supervisor = cut(supervisor, "    def arm(", "    def setup_run(", ARM)
    supervisor = replace(supervisor, "bundle_pin, image_owner = None, None\n    companion = None",
                         "bundle_pin, image_owner = None, None")
    supervisor = replace(supervisor, "nonlocal bundle_pin,image_owner,companion", "nonlocal bundle_pin,image_owner")
    supervisor = replace(supervisor, "getattr(prepared,'observer_snapshot')\n        companion = prepared",
                         "for name in ('autonomous_read','autonomous_start','autonomous_wait'):\n"
                         "            getattr(prepared,name)")
    supervisor = replace(supervisor, "'smoke_requests':3,", "'diagnostic_smoke_requests':3,'compact_smoke_requests':3,'cap_smoke_requests':2,")
    supervisor = replace(supervisor, "    validator = modules['validate_snapshot'].validate_snapshot\n", "")
    supervisor = cut(supervisor, "    else:\n        ready = get('load')",
                     "    require(get('gate')", CHECK_EXPORT)
    supervisor = supervisor.replace("'observer-smoke'", "'autonomous-smoke'")
    compile(supervisor, "observer_validation.py", "exec")
    put(destination, "observer_validation.py", supervisor.encode())

    controller = read_pinned(prior, "observer_host.py", known["observer_host.py"]).decode()
    controller = controller.replace("kv260-observer-v1.md", PROTOCOL).replace("KV_OBS_", "KV_AUT_").replace(
        "Freeze or launch an explicitly reviewed KV260 observer packet via UART.",
        "Freeze or launch an explicitly reviewed KV260 autonomous packet via UART.")
    controller = replace(controller, "'kv260_speed_inventory','validate_snapshot',",
                         "'kv260_speed_inventory','autonomous_runtime','autonomous_comparison','wrapper_probe',")
    controller = replace(controller, "observer-qualification-%Y%m%dT%H%M%SZ-", "autonomous-prefill-decode-%Y%m%dT%H%M%SZ-")
    controller = replace(controller, "modules['energy_analysis'])", "modules['autonomous_comparison'])")
    controller = replace(controller, "    for name in ('test_observer_packet.py','offline-tests.log'):", "    for name in "
                         "('test_autonomous_runtime.py','test_autonomous_comparison.py','autonomous_mmio.c','native_clear_tb.c','prepare_support.py','offline-tests.log'):")
    compile(controller, "observer_host.py", "exec")
    put(destination, "observer_host.py", controller.encode())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("prior", "destination", "host", "probe"):
        parser.add_argument(key, type=Path)
    args = parser.parse_args()
    main(args.prior, args.destination, args.host, args.probe)
