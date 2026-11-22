"""Prepare a boot-specific, hash-pinned KV260 row-burst comparison."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
from uuid import UUID

PRIOR = 'output-projection-ddr4-20261118T231117Z-e79741'
PRIOR_CONFIG = '3d9c2ce8d323e6e8536349558b7a0c72137f5b12e6bd69b861292a0e710983ce'
DRIVER = '7ac9bee066d09d9c9be16f7bd4889442757c40701d9f119d5f252cbd1620ad7c'
OLD_FW = 'gradiated-tiny-output-projection-ddr4-v1-50mhz.bit.bin'
FIRMWARE = OLD_FW.replace('ddr4-v1','ddr4-burst-v1')
PROGRAM = 'kv260-output-projection-ddr4-burst-program.dtbo'
DIRECT = 'kv260-ddr4-burst-dma-direct.dtbo'

def check(path, digest=None):
    if not path.is_file() or path.is_symlink():
        raise ValueError(f'Unexpected file: {path}')
    data=path.read_bytes()
    if digest and sha256(data).hexdigest()!=digest:
        raise ValueError(f'Unexpected digest: {path}')
    return data

def info(data):
    return {'sha256':sha256(data).hexdigest(),'bytes':len(data)}

def save(path,data):
    if path.exists():
        if check(path)!=data:raise ValueError(f'Existing content differs: {path}')
    else:
        with path.open('xb') as f:f.write(data)

def changed(source,old,new,n=1):
    if source.count(old)!=n:raise ValueError(f'Expected {n} occurrences of {old!r}')
    return source.replace(old,new)

def lifecycle(data):
    s=data.decode()
    start=s.index('SCHEDULE = ')
    end=s.index('OF_NOTICE = ',start)
    s=s[:start]+'''from measurement import MIXED_ORDERS, HOMOGENEOUS_ORDERS

SCHEDULE = tuple((group, mode) for group, order in enumerate(MIXED_ORDERS,1) for mode in order)
HOMOGENEOUS_BLOCKS = HOMOGENEOUS_ORDERS
'''+s[end:]
    s=changed(s,'Experiment 14','Experiment 15')
    s=changed(s,OLD_FW,FIRMWARE)
    s=changed(s,'time.monotonic() + 900','time.monotonic() + 2100')
    s=changed(s,'0x44445231','0x44445232',2)
    s=changed(s,'gradiated,kv260-ddr4-weights-v1','gradiated,kv260-ddr4-burst-v1')
    s=changed(s,'for mode in ("bram","ddr")','for mode in ("bram","scalar","beat","row")')
    compile(s,'lifecycle.py','exec')
    return s.encode()

def transport(source,boot):
    s=source.decode()
    s=changed(s,'0c865b88-1cfa-45ba-881b-0b388013ceeb',boot)
    s=changed(s,'output-projection-ddr4-', 'output-projection-ddr4-burst-',4)
    s=changed(s,'KV_DDR14_', 'KV_DDR15_')
    s=changed(s,'time.monotonic()+1100','time.monotonic()+2370')
    s=changed(s,'time.monotonic()+300','time.monotonic()+900')
    compile(s,'transport.py','exec')
    return s.encode()

def make(args):
    root=args.repo.resolve()
    inference=root/'hardware/research/inference'
    variant=inference/'implementations/kv260/variants/output-projection-ddr4-burst-v1'
    previous=root/'.agents/runtime/hardware/inference/outputs'/PRIOR/'preparation/packet-inputs'
    cfg=json.loads(check(previous/'config.json',PRIOR_CONFIG))
    boot=str(UUID(args.boot))
    if boot!=args.boot:raise ValueError('Expected canonical boot ID')
    args.out.mkdir(parents=True,exist_ok=True)
    old_transport=inference/'implementations/kv260/variants/output-projection-ddr4-v1/physical/transport14.py'
    save(args.out.parent/'transport.py',transport(check(old_transport,'8a4653c18b47b13da92ff95d27552ad5b33aff9eb69fd59784bc14c609a90b8c'),boot))
    changed_assets={'lifecycle.py','weights.py','measurement.py','bench_fixture.py','fixture_sampler.py','stock_sampler.py',cfg['driver'],cfg['firmware'],cfg['dma_overlay'],cfg['program_overlay']}
    data={n:check(previous/n,p['sha256']) for n,p in cfg['pins'].items() if n not in changed_assets}
    def original(name):return check(previous/name,cfg['pins'][name]['sha256'])
    data['lifecycle.py']=lifecycle(original('lifecycle.py'))
    for name in ('measurement.py','bench_fixture.py','weights.py'):
        data[name]=check(variant/('host' if name=='weights.py' else 'physical')/name)
    data['kv260_ddr4_weights.ko']=check(args.driver,DRIVER)
    for name in ('fixture_sampler.py','stock_sampler.py'):
        s=changed(original(name).decode(),cfg['boot'],boot)
        if name=='fixture_sampler.py':s=changed(s,OLD_FW,FIRMWARE)
        data[name]=s.encode()
    for name,value in data.items():save(args.out/name,value)
    if not args.build:return
    report=json.loads(check(args.build/'offline-acceptance.json'))
    if report['passed'] is not True or report['routed_hp0']['arlen_values']!=[0,7] or not report['generated_psu_matches_exp14']:
        raise ValueError('The routed build has not passed the required gates')
    release=report['firmware_assets']
    receipt=json.loads(check(args.project))
    if receipt['boot_id']!=boot or receipt['verified'] is not True or receipt['pl0_hz']!=50000000:
        raise ValueError('Original configuration does not match boot/clock')
    for name in (FIRMWARE,PROGRAM,DIRECT,cfg['interface_overlay'],cfg['afi_restore_overlay']):
        digest=release[name]
        if not re.fullmatch(r'[0-9a-f]{64}',digest):raise ValueError('Invalid build hash')
        folder=args.build/'server'
        blob=check((folder/'offline-package' if name==FIRMWARE else folder)/name,digest)
        if name in data and data[name]!=blob:raise ValueError('Previously verified overlay changed')
        data[name]=blob
    if len(data[FIRMWARE])!=7797692:raise ValueError('Unexpected bit.bin size')
    for name,value in data.items():save(args.out/name,value)
    details={**cfg,'boot':boot,'firmware':FIRMWARE,'program_overlay':PROGRAM,'dma_overlay':DIRECT,
             'project_state':{k:receipt[k] for k in ('board_path','sha256')},'pins':{n:info(v) for n,v in data.items()}}
    save(args.out/'config.json',(json.dumps(details,sort_keys=True,indent=2)+'\n').encode())

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('repo','out','driver','project','build'):p.add_argument('--'+name,type=Path,required=name in ('repo','out','driver'))
    p.add_argument('--boot',required=True)
    make(p.parse_args())
