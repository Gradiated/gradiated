"""Launch disjoint public-repo mining workers with scoped storage and deadlines."""

import argparse
import io
import json
import os
import shlex
import subprocess
import sys
import tarfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
GRADCTL = HERE.parents[1] / "tools/gradctl/gradctl"
PROFILE = dict(os.environ, AWS_PROFILE="gradiated-readonly")
PRESETS = {1: "1gpu-16vcpu-200gb", 8: "8gpu-128vcpu-1600gb"}

NODE = r"""
set -eu
umask 077
export PATH="$HOME/.local/bin:$PATH"
cd "$HOME/merge-corpus"
if ! command -v aws >/dev/null; then
    if ! command -v uv >/dev/null; then curl -LsSf https://astral.sh/uv/install.sh | sh; fi
    uv tool install -q awscli
fi
for slot in slots/*; do
    (cd "$slot"; exec bash ../../worker.sh "$1" "$2" "$3-$(basename "$slot")") > "$slot/worker.log" 2>&1 &
done
wait
"""

WORKER = r"""
set -o pipefail
umask 077
export PATH="$HOME/.local/bin:$PATH"
export AWS_RETRY_MODE=standard AWS_MAX_ATTEMPTS=3
deadline=$1
output=$2
name=$3
upload_progress() {
    timeout 30 aws s3 cp --quiet worker.log "$output/workers/$name.log"
}
trap upload_progress EXIT
git --version
upload_progress
left=$(( deadline - $(date +%s) - 65 ))
if ((left <= 0)); then exit 2; fi
timeout -k 10 "$left" python3 ../../mine.py repos.jsonl --work work \
    --out "$output" --deadline "$((deadline - 75))" --threads 12
status=$?
printf '{"worker":"%s","exit":%s}\n' "$name" "$status" > terminal.json
timeout 30 aws s3 cp --quiet terminal.json "$output/workers/$name.json"
exit "$status"
"""


def execute(args, seconds, data=None):
    return subprocess.run(
        args, input=data, capture_output=True, env=PROFILE, timeout=seconds, check=False
    )


def grad(args, seconds, data=None):
    result = execute([str(GRADCTL), "--json", *args], seconds, data)
    payload = json.loads(result.stdout)
    if result.returncode or not payload.get("ok"):
        error = payload.get("error") or {}
        stderr = (payload.get("data") or {}).get("stderr", "")
        raise RuntimeError(
            (error.get("message", "") + " " + stderr)[-500:]
            or "gradctl returned an error"
        )
    return payload.get("data") or {}


def remote(vm, command, seconds=35, data=None):
    return grad(
        ["compute", "ssh", "--provider", "nebius", vm, "--", command], seconds, data
    )


def watchdog(vm, deadline, state):
    command = (
        'left=$(( $1 - $(date +%s) )); if ((left>0)); then sleep "$left"; fi; '
        'for attempt in 1 2 3; do timeout 125 "$2" --json compute down --provider nebius "$3" '
        "&& exit 0; sleep 10; done; exit 1"
    )
    with (state / f"{vm}.watchdog.log").open("wb") as log:
        p = subprocess.Popen(
            ["bash", "-c", command, "watchdog", str(deadline), str(GRADCTL), vm],
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            env=PROFILE,
            start_new_session=True,
        )
    (state / f"{vm}.watchdog.pid").write_text(str(p.pid) + "\n")


def payload(repos, shards):
    data = io.BytesIO()
    members = {
        "mine.py": (HERE / "mine.py").read_bytes(),
        "worker.sh": WORKER.encode(),
        "node.sh": NODE.encode(),
    }
    for i in range(shards):
        members[f"slots/{i:02d}/repos.jsonl"] = "".join(
            json.dumps(r) + "\n" for r in repos[i::shards]
        ).encode()
    with tarfile.open(fileobj=data, mode="w:gz") as tar:
        for name, value in members.items():
            entry = tarfile.TarInfo(name)
            entry.size = len(value)
            tar.addfile(entry, io.BytesIO(value))
    return data.getvalue()


def worker(args, index, repos, deadline):
    vm = f"{args.name}-{index:02d}"
    readonly = ["--read", "merge-model/ds-v1/dataset/w1b"]
    package = payload(repos, args.gpus_per_vm)
    watchdog(vm, deadline, args.state)
    try:
        gpu_args = [
            "--provider",
            "nebius",
            "--platform",
            "gpu-h200-sxm",
            "--preset",
            PRESETS[args.gpus_per_vm],
            "--region",
            args.region,
            "--term",
            "spot",
        ]
        node = grad(
            [
                "compute",
                "up",
                vm,
                *gpu_args,
                "--max-price",
                str(args.max_price),
                "--disk-gib",
                str(650 if args.gpus_per_vm == 8 else 200),
                "--stage",
                "cleaning",
                "--run-id",
                args.name,
                "--workstream",
                "merge-model",
            ],
            290,
        )
        for _ in range(20):
            try:
                remote(vm, "true", 15)
                break
            except (RuntimeError, ValueError, subprocess.TimeoutExpired):
                time.sleep(6)
        else:
            raise RuntimeError("SSH startup exceeded retry limit")
        creds = grad(
            [
                "compute",
                "s3",
                "--provider",
                "nebius",
                vm,
                "--hours",
                "12",
                "--path",
                args.s3_prefix,
                *readonly,
            ],
            100,
        )
        s3 = f"s3://{creds['bucket']}/{args.s3_prefix}"
        remote(
            vm,
            'umask 077; mkdir -p "$HOME/merge-corpus" && tar -xzf - -C "$HOME/merge-corpus"',
            45,
            package,
        )
        params = shlex.join([str(deadline), s3, vm])
        command = (
            f'cd "$HOME/merge-corpus" && '
            f"(nohup bash node.sh {params} > node.log 2>&1 < /dev/null & echo $! > worker.pid) "
            '&& kill -0 "$(cat worker.pid)" && printf started'
        )
        got = remote(vm, command, 35)
        if got.get("stdout", "").strip() != "started":
            raise RuntimeError("worker did not acknowledge launch")
        result = dict(
            vm=vm,
            status="started",
            repos=len(repos),
            shards=args.gpus_per_vm,
            output=s3,
            deadline=deadline,
            rate=node.get("hourly_usd"),
        )
    except (
        OSError,
        KeyError,
        RuntimeError,
        ValueError,
        subprocess.TimeoutExpired,
    ) as error:
        result = dict(vm=vm, status="failed", detail=str(error))
        try:
            grad(["compute", "down", "--provider", "nebius", vm], 130)
            result["cleanup"] = "done"
        except (RuntimeError, ValueError, subprocess.TimeoutExpired) as cleanup:
            result["cleanup"] = str(cleanup)
    (args.state / f"{vm}.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--s3-prefix", required=True)
    parser.add_argument("--workers", type=int, default=7)
    parser.add_argument("--region", default="eu-west1")
    parser.add_argument("--gpus-per-vm", type=int, choices=PRESETS, default=1)
    parser.add_argument("--hours", type=float, default=7)
    parser.add_argument("--max-price", type=float, default=1.25)
    args = parser.parse_args()
    if not 1 <= args.workers <= 16 or not 0.25 <= args.hours <= 10:
        parser.error("set 1–16 workers and a window from 15 minutes to 10 hours")
    args.state.mkdir(parents=True, exist_ok=True)
    rows = list(map(json.loads, args.manifest.open()))
    if len(rows) < args.workers * args.gpus_per_vm or len(
        {r["id"] for r in rows}
    ) != len(rows):
        parser.error("manifest must contain enough unique repository IDs")
    deadline = int(time.time() + args.hours * 3600)
    (args.state / "deadline").write_text(str(deadline) + "\n")
    pool = ThreadPoolExecutor(min(args.workers, 4))
    with pool:
        jobs = [
            pool.submit(worker, args, i, rows[i :: args.workers], deadline)
            for i in range(args.workers)
        ]
        results = []
        for task in as_completed(jobs):
            result = task.result()
            results.append(result)
            print(json.dumps(result), flush=True)
    (args.state / "fleet.json").write_text(json.dumps(results, indent=2) + "\n")
    return 0 if all(r["status"] == "started" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
