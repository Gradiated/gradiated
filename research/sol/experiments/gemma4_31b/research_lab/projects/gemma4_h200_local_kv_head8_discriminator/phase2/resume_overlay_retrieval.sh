#!/usr/bin/env bash
set -Eeuo pipefail

project=/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/gemma4_h200_local_kv_head8_discriminator
source="$project/artifacts/local-kv8-conversion-20260719t1402z/.overlay.safetensors.partial"
final="$project/artifacts/local-kv8-conversion-20260719t1402z/overlay.safetensors"
artifact="$project/artifacts/local-kv8-overlay-retrieval-20260719t1507z"
remote='/home/glmrunner/gemma-local-kv8/local-kv8-conversion-20260719t-phase2/distillation/overlay.safetensors'
host='89.169.102.23'
key='/root/.config/nebius/glm-campaign/ssh_ed25519'
expected_size=2202022184
expected_sha=e29faa6768d22aa6cae56bb15253d02f6af0aca2abdd6d4f0092a436cea05780

mkdir -p "$artifact"
before=$(stat -c %s "$source")
printf 'reget %s %s\n' "$remote" "$source" | sftp -b - -i "$key" -o BatchMode=yes -o StrictHostKeyChecking=accept-new "glmrunner@$host" >"$artifact/sftp.stdout" 2>"$artifact/sftp.stderr"
size=$(stat -c %s "$source")
sha=$(sha256sum "$source" | awk '{print $1}')
pass=false
if [[ "$size" -eq "$expected_size" && "$sha" == "$expected_sha" ]]; then
  mv "$source" "$final"
  pass=true
fi
python3 - "$artifact/RETRIEVAL_TERMINAL.json" "$before" "$size" "$sha" "$pass" "$expected_size" "$expected_sha" <<'PY'
import datetime,json,pathlib,sys
p=pathlib.Path(sys.argv[1]); q=p.with_suffix('.part')
x={'schema_version':1,'status':'terminal','classification':'overlay_retrieval_pass' if sys.argv[5]=='true' else 'overlay_retrieval_integrity_failure','pass':sys.argv[5]=='true','bytes_before':int(sys.argv[2]),'bytes_after':int(sys.argv[3]),'sha256':sys.argv[4],'expected_bytes':int(sys.argv[6]),'expected_sha256':sys.argv[7],'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z')}
q.write_text(json.dumps(x,indent=2,sort_keys=True)+'\n');q.replace(p)
PY
[[ "$pass" == true ]]
