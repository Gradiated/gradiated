set -Eeuo pipefail
export DEBIAN_FRONTEND=noninteractive
if ! command -v docker >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install -y docker.io curl ca-certificates gnupg
fi
sudo systemctl enable --now docker
if ! command -v nvidia-ctk >/dev/null 2>&1; then
  curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor --yes -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
  curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#' | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list >/dev/null
  sudo apt-get update
  sudo apt-get install -y nvidia-container-toolkit
fi
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
sudo docker pull vllm/vllm-openai:v0.15.0@sha256:97187c9535fd6d6040444d68bb073f17344fd454e9241cc7a4e998141f244543
sudo docker image inspect vllm/vllm-openai:v0.15.0@sha256:97187c9535fd6d6040444d68bb073f17344fd454e9241cc7a4e998141f244543 --format '{{json .RepoDigests}}'
sudo docker run --rm --gpus all --entrypoint nvidia-smi vllm/vllm-openai:v0.15.0@sha256:97187c9535fd6d6040444d68bb073f17344fd454e9241cc7a4e998141f244543 --query-gpu=name,memory.total,driver_version --format=csv,noheader,nounits
sudo docker build --network=host -t glm-vllm:0.15.0-transformers-1618d44 - <<'DOCKERFILE'
FROM vllm/vllm-openai:v0.15.0@sha256:97187c9535fd6d6040444d68bb073f17344fd454e9241cc7a4e998141f244543
RUN python3 -m pip install --no-cache-dir --upgrade https://github.com/huggingface/transformers/archive/1618d44b9295361607ec74d7be860ba886aac039.tar.gz
DOCKERFILE
sudo docker image inspect glm-vllm:0.15.0-transformers-1618d44 --format '{{.Id}}'
sudo docker run --rm --gpus all -v /home/glmrunner/input:/input:ro --entrypoint bash glm-vllm:0.15.0-transformers-1618d44 -lc 'rm -f /etc/ld.so.conf.d/00-cuda-compat.conf /etc/ld.so.conf.d/cuda-compat.conf; ldconfig; ldconfig -p | grep libcuda.so.1; exec python3 /input/vllm_preflight.py'
docker --version
sudo dpkg-query -W -f='${Package}=${Version}
' docker.io nvidia-container-toolkit

sudo docker build --network=host -t glm-vllm:0.15.0-transformers-1618d44 - <<'NSYS_DOCKERFILE'
FROM glm-vllm:0.15.0-transformers-1618d44
RUN set -eux;     apt-get update;     apt-get install -y --no-install-recommends curl ca-certificates gnupg;     curl -fsSL 'https://keyserver.ubuntu.com/pks/lookup?op=get&search=0xF60F4B3D7FA2AF80' -o /tmp/nvidia-devtools.asc;     gpg --show-keys --with-colons /tmp/nvidia-devtools.asc | grep -F 'fpr:::::::::AE09FE4BBD223A84B2CCFCE3F60F4B3D7FA2AF80:';     gpg --dearmor -o /usr/share/keyrings/nvidia-devtools.gpg /tmp/nvidia-devtools.asc;     echo 'deb [signed-by=/usr/share/keyrings/nvidia-devtools.gpg] https://developer.download.nvidia.com/devtools/repos/ubuntu2204/amd64/ /' > /etc/apt/sources.list.d/nvidia-devtools.list;     apt-get update;     apt-get install -y --no-install-recommends nsight-systems-cli=2026.3.1.157;     rm -rf /var/lib/apt/lists/*
NSYS_DOCKERFILE
sudo docker run --rm --gpus all --pid=host   --cap-add SYS_ADMIN --cap-add SYS_PTRACE --cap-add PERFMON --security-opt seccomp=unconfined   -v /home/glmrunner/input:/input:ro --entrypoint bash glm-vllm:0.15.0-transformers-1618d44 -lc '
set -Eeuo pipefail
rm -f /etc/ld.so.conf.d/00-cuda-compat.conf /etc/ld.so.conf.d/cuda-compat.conf
ldconfig
test -s /input/nsys-launch-help-2026.3.1.157.txt
sha256sum /input/nsys-launch-help-2026.3.1.157.txt
nsys --version | tee /tmp/nsys-version.txt
grep -F "2026.3.1.157" /tmp/nsys-version.txt
nsys status -e | tee /tmp/nsys-status.txt
grep -F "CPU Profiling Environment (process-tree): OK" /tmp/nsys-status.txt
nsys profile --help > /tmp/nsys-profile-help.txt
for flag in cuda-graph-trace sample cpuctxsw; do grep -F -- "--$flag" /tmp/nsys-profile-help.txt; done
nsys launch --help | tee /tmp/nsys-launch-help-2026.3.1.157.txt
python3 - /input/nsys-launch-help-2026.3.1.157.txt /tmp/nsys-launch-help-2026.3.1.157.txt <<'PY'
import difflib
import re
import sys

required = ("--session-new", "--trace", "--cuda-graph-trace", "--cuda-event-trace",
            "--sample", "--cpuctxsw")
forbidden = ("--force-overwrite",)

def normalize(raw):
    lines = raw.decode().replace("\r\n", "\n").replace("\r", "\n").split("\n")
    result = []
    previous_blank = False
    for line in lines:
        line = line.rstrip(" \t")
        if not line.strip():
            if previous_blank:
                continue
            result.append("")
            previous_blank = True
            continue
        previous_blank = False
        if re.search(r"(?:^|[ \t])-[-A-Za-z0-9]", line):
            line = re.sub(r"[ \t]+", " ", line).lstrip()
        result.append(line)
    while result and result[0] == "":
        result.pop(0)
    while result and result[-1] == "":
        result.pop()
    return "\n".join(result) + "\n"

expected = normalize(open(sys.argv[1], "rb").read())
observed = normalize(open(sys.argv[2], "rb").read())
if expected != observed:
    sys.stderr.write("".join(difflib.unified_diff(expected.splitlines(True), observed.splitlines(True), "fixture", "target")))
    raise SystemExit("nsys launch capability semantic mismatch")
for flag in required:
    if not re.search(r"(?<![A-Za-z0-9_-])" + re.escape(flag) + r"(?=$|[= ,])", observed, re.MULTILINE):
        raise SystemExit("required nsys launch flag missing: " + flag)
for flag in forbidden:
    if re.search(r"(?<![A-Za-z0-9_-])" + re.escape(flag) + r"(?=$|[= ,])", observed, re.MULTILINE):
        raise SystemExit("forbidden nsys launch flag present: " + flag)
PY
test "$(sha256sum /input/remote_observer_diagnostic.sh)" = "bce6f67f54e9da39f721892fe2e5419913a15f3144293af2f8d2f949a1a6ef8a  /input/remote_observer_diagnostic.sh"
nsys start --help > /tmp/nsys-start-help-2026.3.1.157.txt
test "$(sha256sum /tmp/nsys-start-help-2026.3.1.157.txt | cut -d " " -f1)" = "1b4e0715f1940684e27214ccc96780ad3b5cabbf09f30dd3e4ad1e316a6fecb6"
grep -F -- '-b, --backtrace=' /tmp/nsys-start-help-2026.3.1.157.txt
grep -F -- "Select 'none' to disable backtrace collection." /tmp/nsys-start-help-2026.3.1.157.txt
grep -F -- 'nsys launch --session-new="$session"' /input/remote_observer_diagnostic.sh
grep -F -- '--trace=cuda,nvtx,osrt' /input/remote_observer_diagnostic.sh
grep -F -- '--cuda-graph-trace=node' /input/remote_observer_diagnostic.sh
grep -F -- '--cuda-event-trace=true' /input/remote_observer_diagnostic.sh
grep -F -- '--sample="$sample_mode"' /input/remote_observer_diagnostic.sh
grep -F -- '--cpuctxsw="$context_switch_mode"' /input/remote_observer_diagnostic.sh
if grep -F -- '--backtrace' /input/remote_observer_diagnostic.sh; then
  echo "constructed backtrace option leaked into launch/start" >&2
  exit 1
fi
grep -F -- '--session="$session"' /input/remote_observer_diagnostic.sh
grep -F -- '--output="$arm_dir/trace"' /input/remote_observer_diagnostic.sh
if grep -F -- '--output="$arm_dir/trace"' /input/remote_observer_diagnostic.sh | grep -F "nsys launch"; then
  echo "nsys start-only output option leaked onto launch" >&2
  exit 1
fi
if nsys launch --session-new=backtrace-negative --backtrace=none /bin/true >/tmp/nsys-launch-backtrace-negative.log 2>&1; then
  echo "nsys launch unexpectedly accepted --backtrace=none" >&2
  exit 1
fi
grep -F -- "not supported by the launch command" /tmp/nsys-launch-backtrace-negative.log
if nsys launch --session-new=output-negative --output=/tmp/leak /bin/true >/tmp/nsys-launch-output-negative.log 2>&1; then
  echo "nsys launch unexpectedly accepted --output" >&2
  exit 1
fi
grep -F -- "unrecognised option '"'"'--output" /tmp/nsys-launch-output-negative.log
nsys launch --session-new=argv-contract-probe --trace=cuda,nvtx,osrt   --cuda-graph-trace=node --cuda-event-trace=true --sample=process-tree   --cpuctxsw=process-tree /bin/true
nsys start --session=argv-contract-probe --backtrace=none --output=/tmp/argv-contract-probe
echo gpu_metrics_collector=unsupported_on_l40s
cat > /tmp/nsys-probe.py <<"PY"
import torch
x = torch.ones(1024, device="cuda")
graph = torch.cuda.CUDAGraph()
torch.cuda.synchronize()
with torch.cuda.graph(graph):
    x.add_(1)
graph.replay()
torch.cuda.synchronize()
PY
nsys profile --force-overwrite=true --trace=cuda,nvtx,osrt --cuda-graph-trace=node   --cuda-event-trace=true --sample=process-tree --cpuctxsw=process-tree --backtrace=none   --duration=2 --output=/tmp/nsys-capability-probe python3 /tmp/nsys-probe.py
test -s /tmp/nsys-capability-probe.nsys-rep
nsys export --force-overwrite=true --type=sqlite --output=/tmp/nsys-capability-probe.sqlite /tmp/nsys-capability-probe.nsys-rep
test -s /tmp/nsys-capability-probe.sqlite
'
