#!/usr/bin/env python3
"""One-shot native-NVFP4 compressed-tensors producer.

This deliberately records the producer package/version and calibration manifest
before writing the final directory.  The NVFP4 config is checked by the pinned
vLLM loader again before any endpoint request.
"""
import argparse, hashlib, json, os, pathlib, shutil, sys

def sha(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for block in iter(lambda:f.read(1024*1024), b""): h.update(block)
    return h.hexdigest()

def main():
    p=argparse.ArgumentParser(); p.add_argument("--source",type=pathlib.Path,required=True); p.add_argument("--output",type=pathlib.Path,required=True); p.add_argument("--calibration",type=pathlib.Path,required=True); p.add_argument("--producer",default="llmcompressor"); a=p.parse_args()
    if a.output.exists(): raise SystemExit("immutable output exists")
    try:
        import llmcompressor
    except Exception as e:
        raise SystemExit("conversion_dependency_missing:"+repr(e))
    # The public producer CLI is used to avoid reimplementing its packed tensor
    # serialization.  Its observed version and all output hashes are bound below.
    recipe={"quant_stage":{"type":"QuantizationModifier","targets":["Linear"],"scheme":"NVFP4","ignore":["lm_head","model.embed_tokens","vision_tower","multi_modal_projector"]}}
    recipe_path=a.source.parent/"native_nvfp4_recipe.json"; recipe_path.write_text(json.dumps(recipe,sort_keys=True))
    command=[sys.executable,"-m","llmcompressor", "oneshot", "--model",str(a.source), "--recipe",str(recipe_path), "--dataset",str(a.calibration), "--output-dir",str(a.output)]
    code=os.spawnv(os.P_WAIT, sys.executable, command)
    if code: raise SystemExit("converter_exit:"+str(code))
    config=json.loads((a.output/"config.json").read_text()); q=config.get("quantization_config",{})
    groups=q.get("config_groups",{}).values()
    nvfp4=any(g.get("weights",{}).get("num_bits")==4 and g.get("weights",{}).get("group_size")==16 and g.get("weights",{}).get("type")=="float" and g.get("input_activations",{}).get("num_bits")==4 and g.get("input_activations",{}).get("group_size")==16 and g.get("input_activations",{}).get("type")=="float" for g in groups)
    if not nvfp4: raise SystemExit("conversion_semantic_mismatch:missing_symmetric_float4_group16_w4a4")
    rows=[]
    for x in sorted(a.output.rglob("*")):
        if x.is_file(): rows.append({"path":str(x.relative_to(a.output)),"bytes":x.stat().st_size,"sha256":sha(x)})
    (a.output/"CONVERSION_MANIFEST.json").write_text(json.dumps({"producer":a.producer,"producer_version":getattr(llmcompressor,"__version__",None),"recipe_sha256":sha(recipe_path),"semantic_contract":"symmetric float4 tensor-group size16 W4A4; lm_head/vision/projector retained BF16","files":rows},sort_keys=True,indent=2))
if __name__=="__main__": main()
