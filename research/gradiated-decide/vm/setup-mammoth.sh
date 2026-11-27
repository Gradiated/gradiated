#!/usr/bin/env bash
# Install mammoth-1's release runtime in its own environment ($ROOT/venv-mm) and download the checkpoint, following
# the checkpoint's setup.sh: OneJev @81ce62f + serve.patch, packages pinned by constraints.txt, torch 2.8 / CUDA 12.8
# (the image its card names). Our kit (src/di) and package are added without dependencies so evaluation and suite IO
# are the same code as every other run. Usage on the VM: setup-mammoth.sh [MODEL=mammoth-1]
set -euo pipefail
source "$HOME/gdecide/env.sh"
MODEL=${1:-mammoth-1}
declare -A REVISION=([mammoth-1]=61cec44c281c693992e3d6ebeb44dd3402dfa186)
ONEJEV=81ce62f1597c91e46767d4d02d6ac2e18534fe94
cd "$ROOT"
export PATH=$HOME/.local/bin:$PATH
CK=ckpt/$MODEL
if [ ! -f "$CK/done" ]; then
  HF_HUB_DISABLE_XET=1 venv/bin/python -c "
from huggingface_hub import snapshot_download
snapshot_download('baselabs/$MODEL', revision='${REVISION[$MODEL]}', local_dir='$CK', max_workers=16)"
  echo "${REVISION[$MODEL]}" > "$CK/done"
fi
if ! venv-mm/bin/python -c "import qev.engine" 2>/dev/null; then
  [ -d OneJev ] || git clone -q https://github.com/OmniJev/OneJev.git
  git -C OneJev checkout -q -f $ONEJEV && git -C OneJev clean -fdq && git -C OneJev apply "$ROOT/$CK/serve.patch"
  uv venv -q -p 3.11 venv-mm
  export VIRTUAL_ENV=$ROOT/venv-mm
  printf 'torch==2.8.0\ntorchvision==0.23.0\n' > venv-mm/image-torch.txt
  uv pip install -q --index-strategy unsafe-best-match --extra-index-url https://download.pytorch.org/whl/cu128 \
    -c venv-mm/image-torch.txt torch torchvision
  uv pip install -q --index-strategy unsafe-best-match --extra-index-url https://download.pytorch.org/whl/cu128 \
    -c "$CK/constraints.txt" -c venv-mm/image-torch.txt -e "./OneJev[train]" huggingface_hub hf_xet brotli \
    flash-linear-attention httpx setuptools wheel ninja packaging
  CUDA_HOME=/usr/local/cuda TORCH_CUDA_ARCH_LIST=$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader | head -1) \
    MAX_JOBS=32 uv pip install -q --no-build-isolation -c "$CK/constraints.txt" -c venv-mm/image-torch.txt causal-conv1d
fi
VIRTUAL_ENV=$ROOT/venv-mm uv pip install -q pyarrow pandas numpy requests
# Our packages declare Python >= 3.12 while the release runtime is 3.11, so put them on the path instead of installing.
site=$(venv-mm/bin/python -c "import sysconfig; print(sysconfig.get_paths()['purelib'])")
printf '%s\n' "$ROOT/src/di" "$ROOT/src/gradiated-decide" > "$site/gdecide-src.pth"
venv-mm/bin/python -c "import qev.engine, decision_index, gdecide; print('venv-mm ready')"
