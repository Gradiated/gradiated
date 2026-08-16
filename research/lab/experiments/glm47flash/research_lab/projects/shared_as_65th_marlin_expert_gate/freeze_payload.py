#!/usr/bin/env python3
"""Extract one exact layer and arrange tensors in vLLM WNA16 MoE pre-repack layout."""
from __future__ import annotations
import hashlib, json, struct
from pathlib import Path

STOCK = Path('/root/.cache/glm47flash-awq-ab31d120')
W4 = Path('/root/.cache/glm47flash-awq-full47-official-head-shared-w4-7ab75a5258cc')
OUT = Path(__file__).resolve().parent / 'artifacts/shared65_payload'
LAYER = 1

def header(root: Path, name: str):
    idx = json.loads((root/'model.safetensors.index.json').read_text())['weight_map']
    shard = root/idx[name]
    with shard.open('rb') as f:
        n = struct.unpack('<Q', f.read(8))[0]; h = json.loads(f.read(n))
    return shard, h[name]

def raw(root: Path, name: str) -> bytes:
    p, meta = header(root, name)
    with p.open('rb') as f:
        n = struct.unpack('<Q', f.read(8))[0]
        f.seek(8+n+meta['data_offsets'][0]); return f.read(meta['data_offsets'][1]-meta['data_offsets'][0])

def transpose(raw_bytes: bytes, rows: int, cols: int, item: int) -> bytes:
    a = [raw_bytes[i:i+item] for i in range(0, len(raw_bytes), item)]
    return b''.join(a[r*cols+c: r*cols+c+1][0] for c in range(cols) for r in range(rows))

def write_tensor(f, name, dtype, shape, data, entries):
    start = f.tell(); f.write(data); entries[name] = {'dtype':dtype,'shape':list(shape),'data_offsets':[start,start+len(data)],'sha256':hashlib.sha256(data).hexdigest()}

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    entries = {}; blobs = {}
    for e in range(64):
        base=f'model.layers.{LAYER}.mlp.experts.{e}'
        for p in ('gate_proj','up_proj','down_proj'):
            n=f'{base}.{p}.weight_packed'; blobs[f'routed_{e}_{p}_packed']=raw(STOCK,n)
            n=f'{base}.{p}.weight_scale'; blobs[f'routed_{e}_{p}_scale']=raw(STOCK,n)
    for p in ('gate_proj','up_proj','down_proj'):
        blobs[f'shared_w4_{p}_packed']=raw(W4,f'model.layers.{LAYER}.mlp.shared_experts.{p}.weight_packed')
        blobs[f'shared_w4_{p}_scale']=raw(W4,f'model.layers.{LAYER}.mlp.shared_experts.{p}.weight_scale')
        blobs[f'shared_bf16_{p}']=raw(STOCK,f'model.layers.{LAYER}.mlp.shared_experts.{p}.weight')

    # Build runtime pre-repack tensors: [E,K/8,2N], [E,N/8,K], scales [E,K/32,2N]/[E,N/32,K].
    def pack_w13(source, suffix, item, rows, cols, out_shape):
        out=[]
        for e in range(65):
            gp = blobs[f'routed_{e}_gate_proj_{suffix}'] if e<64 else blobs[f'shared_w4_gate_proj_{suffix}']
            up = blobs[f'routed_{e}_up_proj_{suffix}'] if e<64 else blobs[f'shared_w4_up_proj_{suffix}']
            out.append(transpose(gp, rows, cols, item)+transpose(up, rows, cols, item))
        return b''.join(out), out_shape
    # Packed gate/up tensors are [1536,256] I32 and scales [1536,64] BF16.
    w13p, s13 = pack_w13(None,'packed',4,1536,256,(65,256,3072))
    w13s, ss13 = pack_w13(None,'scale',2,1536,64,(65,64,3072))
    # Packed down tensor is [2048,192] I32; scale is [2048,48] BF16.
    w2p=[]; w2s=[]
    for e in range(65):
        p=blobs[f'routed_{e}_down_proj_packed'] if e<64 else blobs['shared_w4_down_proj_packed']
        s=blobs[f'routed_{e}_down_proj_scale'] if e<64 else blobs['shared_w4_down_proj_scale']
        w2p.append(transpose(p,2048,192,4)); w2s.append(transpose(s,2048,48,2))
    blobs['w13_packed']=w13p; blobs['w13_scale']=w13s; blobs['w2_packed']=b''.join(w2p); blobs['w2_scale']=b''.join(w2s)
    shapes={'w13_packed':(65,256,3072),'w13_scale':(65,64,3072),'w2_packed':(65,192,2048),'w2_scale':(65,48,2048)}
    dtypes={'w13_packed':'I32','w13_scale':'BF16','w2_packed':'I32','w2_scale':'BF16'}
    out_file=OUT/'payload.safetensors';
    header_obj={}; payload=bytearray()
    for n in ('w13_packed','w13_scale','w2_packed','w2_scale'):
        st=len(payload); payload.extend(blobs[n]); header_obj[n]={'dtype':dtypes[n],'shape':list(shapes[n]),'data_offsets':[st, len(payload)]}; entries[n]={'dtype':dtypes[n],'shape':list(shapes[n]),'bytes':len(blobs[n]),'sha256':hashlib.sha256(blobs[n]).hexdigest()}
    h=json.dumps(header_obj,separators=(',',':')).encode(); h += b' ' * ((8-len(h)%8)%8)
    out_file.write_bytes(struct.pack('<Q',len(h))+h+payload)
    for n in ('gate_proj','up_proj','down_proj'):
        entries['shared_bf16_'+n]={'dtype':'BF16','bytes':len(blobs['shared_bf16_'+n]),'sha256':hashlib.sha256(blobs['shared_bf16_'+n]).hexdigest()}
        (OUT/('shared_bf16_'+n+'.bin')).write_bytes(blobs['shared_bf16_'+n])
    manifest={'schema':1,'layer':LAYER,'routed_experts':64,'fused_experts':65,'group_size':32,'hidden_size':2048,'moe_intermediate_size':1536,'wna16_format':'official compressed-tensors uint4b8 pre-repack','tensors':entries,'payload_sha256':hashlib.sha256(out_file.read_bytes()).hexdigest()}
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'payload':str(out_file),'bytes':out_file.stat().st_size,'payload_sha256':manifest['payload_sha256'],'manifest_sha256':hashlib.sha256((OUT/'manifest.json').read_bytes()).hexdigest()},indent=2))
if __name__=='__main__': main()
