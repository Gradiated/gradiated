"""Derive the bounded two-autonomous-arm packet from the last accepted UART runner."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from materialise import replace

PRIOR_PIN = "d4614b800cf029b99e449e3428fca79d03034a96299842edd6c6f97e66ea9bf4"
OLD_ANCHOR = "29db873d990607570303f6b586402d61a6f781ca137dd3562884ff66f022bf9c"
NEW_ANCHOR = "b2c4740bb675ed0321f44e1e4fabf2150995f6555008b33123d7271329bff7a0"
OLD_RUN = "observer-qualification-20261115T182057Z-11c575"
NEW_RUN = "autonomous-prefill-decode-20261115T210134Z-97efcb"


def replace_region(text, start, end, replacement):
    offset = text.index(start)
    return text[:offset]+replacement+text[text.index(end,offset+len(start)):]


def supervisor(text):
    text = text.replace(OLD_RUN,NEW_RUN).replace(OLD_ANCHOR,NEW_ANCHOR).replace("KV_AUT_","KV_SKIP_")
    text = replace(text,"MODES = (('stock','candidate'),('candidate','stock'),('stock','candidate'))",
                   "MODES = (('control','candidate'),('candidate','control'),('control','candidate'))\nCONTROL = 'control'")
    text = replace(text,"    stock_sampler, obs_sampler = (modules[name] for name in ('power_sampler','observer_sampler'))",
                   "    samplers = {mode:modules[mode+'_sampler'] for mode in (CONTROL,OBSERVER)}")
    text = replace(text,"    runtime, comparison, probe = (modules[name] for name in ('autonomous_runtime','autonomous_comparison','wrapper_probe'))",
                   "    runtime, comparison = (modules[name] for name in ('autonomous_runtime','autonomous_comparison'))")
    text = replace_region(text,"    image, pin = ","    last_state =", '''    modes = (CONTROL,OBSERVER)
    names = {mode:lifecycle.image_spec(mode)[0] for mode in modes}
    firmware = {mode:setup.FIRMWARE.parent/name for mode,name in names.items()}
    bundles = {mode:args.evidence/(mode+'-bundle') for mode in modes}
    bundle_pins, image_owners = {}, {}
''')
    text = replace(text,"        if mode==OBSERVER:\n            lifecycle.pinned(observer_firmware,pin)",
                   "        if mode in firmware:\n            lifecycle.pinned(firmware[mode],assets['files'][names[mode]])")
    text = replace_region(text,"    def arm(","    def smoke(",'''    def arm(directory, pair, mode):
        warmup, scheduled = cases(bench,pair)
        sampler,path = samplers[mode],HERE/(mode+'_sampler.py')
        launcher = base_code.source(HERE/'energy_validation.py',base_code.SUPPORT['energy_validation.py'])
        launcher.run_arm.__globals__['POWER_SAMPLER_PIN'] = assets['sources'][path.name]
        launcher.run_arm.__globals__['block_summary'] = comparison.block_summary
        with lifecycle.open_arm(mode,resident,bundles[mode],bundle_pins[mode]) as runner:
            load = load_metadata(runner)
            validate_load(load,prior)
            energy.dump(directory/'load.json',load)
            abi = runtime.ABI if mode == CONTROL else runtime.SKIP_ABI
            port = runtime.Port(runner.session,HERE/lifecycle.OBS_ELF,abi)
            delivery = comparison.DeliveryBenchmark(runtime,port,deadline_ns=deadline_ns)
            check_native_deadline(runner)
            result = launcher.run_arm(directory,runner,(warmup,scheduled,'on'),reference,delivery,remaining,
                                      sampler,analysis,path)
            require(runner.requests==9,'Arm request count differs')
            return {'mode':mode,'pair':pair,'qualified_logger':result}

''')
    text = replace(text,"lifecycle.open_arm(OBSERVER,resident,observer_bundle,bundle_pin)",
                   "lifecycle.open_arm(OBSERVER,resident,bundles[OBSERVER],bundle_pins[OBSERVER])")
    text = replace(text,"port = runtime.Port(runner.session,HERE/lifecycle.OBS_ELF)\n",
                   "port = runtime.Port(runner.session,HERE/lifecycle.OBS_ELF,runtime.SKIP_ABI)\n")
    text = replace_region(text,"    def setup_run(","    def bos(",'''    def setup_run(directory, command):
        for label,bundle in (('original',prior.ORIGINAL),('candidate',prior.CANDIDATE)):
            require(prior.inspect_ok(sealed(directory,command,bundle,label,[],15)),'Stock sealed inspection failed')
        for member, info in assets['files'].items():
            lifecycle.pinned(HERE/member,info)
        prepared = ctypes.CDLL(str(HERE/lifecycle.OBS_ELF))
        for name in ('autonomous_read','autonomous_start','autonomous_wait'):
            getattr(prepared,name)
        for mode in modes:
            bundle_pins[mode] = lifecycle.prepare_bundle(prior.CANDIDATE,HERE,bundles[mode],resident,
                                                         assets['files'],mode=mode)
        require(bundle_pins==assets['derived_bundles'],'Autonomous package manifests differ')
        # Check both destinations before installing either temporary image.
        require(all(not path.exists() and not path.is_symlink() for path in firmware.values()),
                'Unexpected pre-existing temporary firmware file')
        for mode in modes:
            image=names[mode]
            lifecycle.install_observer(HERE/image,assets['files'][image],firmware[mode])
            metadata=firmware[mode].stat()
            image_owners[mode]=(metadata.st_dev,metadata.st_ino)
        return {'bundle_pins':bundle_pins,'new_firmware':{mode:assets['files'][names[mode]] for mode in modes}}

''')
    text = replace_region(text,"    def clean_image():","    def run_gate(",'''    def clean_image():
        for mode,path in firmware.items():
            lifecycle.pinned(path,assets['files'][names[mode]])
            metadata=path.stat()
            require((metadata.st_dev,metadata.st_ino)==image_owners[mode],'Temporary firmware identity changed')
        for path in firmware.values():
            path.unlink()
            require(not path.exists() and not path.is_symlink(),'Installed temporary image remains')

''')
    text = replace(text,"'switches':4","'switches':5")
    text = replace(text,"result = {'bundle_pin':assets['derived_bundle'],'new_firmware':assets['files'][lifecycle.OBSERVER_FILE]}",
                   "result = {'bundle_pins':assets['derived_bundles'],'new_firmware':{\n"
                   "                  mode:assets['files'][lifecycle.image_spec(mode)[0]] for mode in (CONTROL,OBSERVER)}}")
    text = replace_region(text,"        program_pin = (assets[","        result = {'from':",'''        if after==STOCK:
            program_pin=assets['stock_program_sha256']
        else:
            name=lifecycle.CONTROL_DTBO if after==CONTROL else lifecycle.OBS_DTBO
            program_pin=assets['files'][name]['sha256']
''')
    return replace(text,"sampler = modules['observer_sampler'] if candidate else modules['power_sampler']",
                   "sampler = modules[before+'_sampler']")


def host_launcher(text):
    text=text.replace(OLD_RUN,NEW_RUN).replace(OLD_ANCHOR,NEW_ANCHOR).replace("KV_AUT_","KV_SKIP_")
    text=text.replace("kv260-autonomous-v1.md","kv260-prefill-skip-v1.md").replace(
        "autonomous-prefill-decode-%Y%m%dT%H%M%SZ-","prefill-skip-%Y%m%dT%H%M%SZ-")
    text=replace(text,"TRANSFER_SECONDS = 540","TRANSFER_SECONDS = 960")
    text=replace(text,"def freeze(directory, bits, bit_pin, overlay, overlay_pin, reader, reader_pin):",
                 "def freeze(directory, bits, bit_pin, overlay, overlay_pin, reader, reader_pin,\n"
                 "           control_bits, control_bits_pin, control_overlay, control_overlay_pin):")
    text=replace(text,"lifecycle.OBS_DTBO:program,lifecycle.OBS_ELF:read(reader,reader_pin)}",
                 "lifecycle.OBS_DTBO:program,lifecycle.OBS_ELF:read(reader,reader_pin),\n"
                 "             lifecycle.CONTROL_FILE:read(control_bits,control_bits_pin),\n"
                 "             lifecycle.CONTROL_DTBO:read(control_overlay,control_overlay_pin)}")
    text=replace(text,"    require(len(files[lifecycle.OBSERVER_FILE])==7797692,'Unexpected full-image size')",
                 "    require(all(len(files[name])==7797692 for name in (lifecycle.OBSERVER_FILE,lifecycle.CONTROL_FILE)),"
                 "'Unexpected full-image size')")
    text=replace(text,"'autonomous_runtime','autonomous_comparison','wrapper_probe',","'autonomous_runtime','autonomous_comparison',")
    text=replace_region(text,"    sources['observer_sampler.py']","    with tempfile.TemporaryDirectory(",'''    for mode in ('control','candidate'):
        firmware=lifecycle.image_spec(mode)[0]
        sources[mode+'_sampler.py']=lifecycle.rewritten(sources['power_sampler.py'],
            f'"{lifecycle.STOCK_FILE}"'.encode(),f'"{firmware}"'.encode())
''')
    text=replace(text,"        bundle_pin = lifecycle.prepare_bundle(uart['LOCAL_MODELS']/'conditioned-6wbein7j',tmp,tmp/'package',resident,pins)",
                 "        bundle_pins = {mode:lifecycle.prepare_bundle(uart['LOCAL_MODELS']/'conditioned-6wbein7j',\n"
                 "                       tmp,tmp/mode,resident,pins,mode=mode) for mode in ('control','candidate')}")
    text=replace(text,"'derived_bundle':bundle_pin","'derived_bundles':bundle_pins")
    text=replace(text,"len(archive)<=2_300_000 and chunks<=4800","len(archive)<=3_100_000 and chunks<=6459")
    text=replace_region(text,"    for name in ('test_autonomous_runtime.py'","    directory.mkdir",'''    for name in ('prepare_comparison.py','comparison-tests.log'):
        captures[name] = read(HERE/name)
''')
    text=replace(text,"            console.owner()\n            save(directory/'dispatch-intent.json'",
                 r"""            console.owner()
            console.send(" /usr/bin/timeout -k 2s 5s /usr/bin/sudo -n /usr/bin/id -u >/dev/null 2>&1 ; "
                         "/usr/bin/printf '%s %s\\n' "+tag+'_FINAL_UID_EXIT "$?"')
            got = console.wait([tag+'_FINAL_UID_EXIT ([0-9]+)'],time.monotonic()+10)
            require(got and got[1]=='0','BOARD_SUDO_EXPIRED_AFTER_STAGING')
            save(directory/'dispatch-intent.json'""")
    text=replace(text,"for role in ('bits','overlay','reader'):","for role in ('bits','overlay','reader','control-bits','control-overlay'):")
    text=replace(text,"freeze(args.directory,args.bits,args.bits_pin,args.overlay,args.overlay_pin,args.reader,args.reader_pin)",
                 "freeze(args.directory,args.bits,args.bits_pin,args.overlay,args.overlay_pin,args.reader,args.reader_pin,\n"
                 "               args.control_bits,args.control_bits_pin,args.control_overlay,args.control_overlay_pin)")
    return text


def comparison(text):
    text=replace(text,'    if candidate:\n        cycles = data["request_cycles"]',
                 '    expected_skips = len(data["prefix_ids"])-1 if candidate else 0\n'
                 '    if data["skipped_positions"]!=expected_skips:\n'
                 '        raise ValueError("Completed skips differ from the image contract")\n'
                 '    cycles = data["request_cycles"]')
    text=replace_region(text,'        if (data["scores_consumed"]','    return context','''    if (data["scores_consumed"] != runtime.VOCAB * (context-expected_skips) or not 0 < cycles["done"] or
            cycles["done"] * 20 > data["done_ns"] - timing["inference_begin_ns"] or
            bool(data["output_ns"]) != ("first" in cycles and "last" in cycles) or
            data["output_ns"] and not 0 < cycles["first"] <= cycles["last"] <= cycles["done"]):
        raise ValueError("Autonomous work or output cycles disagree with the timed request")
''')
    text=replace(text,'self.port is not None)','self.port.abi == self.runtime.SKIP_ABI)')
    return replace(text,'for mode in ("stock", "candidate")','for mode in ("control", "candidate")')


def prepare(prior, destination, runtime, lifecycle):
    def read(path, pin):
        data=path.read_bytes()
        if sha256(data).hexdigest()!=pin:
            raise ValueError(f"Accepted source differs: {path.name}")
        return data
    manifest=json.loads(read(prior/"invocation.json",PRIOR_PIN))
    helpers=("uart_transport.py","wrapper_host.py","wrapper_validation.py","resident_validation.py",
             "benchmark_validation.py","board_resident.py","board_resident_benchmark.py",
             "energy_validation.py","energy_analysis.py","power_sampler.py","kv260_accept.py","kv260_speed_inventory.py")
    files={name:read(prior/name,manifest["sources"][name]) for name in helpers}
    for filename,derive in (("observer_validation.py",supervisor),("observer_host.py",host_launcher),
                            ("autonomous_comparison.py",comparison)):
        files[filename]=derive(read(prior/filename,manifest["sources"][filename]).decode()).encode()
    files["observer_lifecycle.py"] = lifecycle.read_bytes()
    files["autonomous_runtime.py"] = runtime.read_bytes()
    files["prepare_comparison.py"] = Path(__file__).read_bytes()
    for name,content in files.items():
        compile(content,name,"exec")
    destination.mkdir(mode=0o700)
    for name,content in files.items():
        (destination/name).write_bytes(content)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("prior","destination","runtime","lifecycle"):
        p.add_argument(name,type=Path)
    a=p.parse_args()
    prepare(a.prior,a.destination,a.runtime,a.lifecycle)
