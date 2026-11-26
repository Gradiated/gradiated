"""Agent-side CLI: talk to the persistent engines on the GPU host over SSH.

Usage (from an agent workspace):
  tkcc submit CANDIDATE.py --tier fast|slow [--name TEXT] [--profile]
  tkcc status | tkcc baseline --tier fast | tkcc profile-baseline
  tkcc gpu-run SCRIPT.py [--timeout S]   # run a microbenchmark on the pod under the GPU lock
  tkcc board post "message" | tkcc board read [--last N]
"""

from __future__ import annotations

import argparse
import base64
import fcntl
import json
import os
import shlex
import sys
import time
import uuid
from pathlib import Path

POD_HOST = os.environ.get("TKCC_POD_HOST", "yzno396wdsidu4-64411814")
SSH_KEY = os.environ.get("TKCC_SSH_KEY", "/root/.ssh/gradiated-ops-runpod")
BOARD = Path(os.environ.get("TKCC_BOARD", "board.jsonl"))
AGENT = os.environ.get("TKCC_AGENT", "anon")
POD_ENV = "export PYTHONPATH=/home/tkcc/src; cd /home/tkcc"
BUNDLE_ENV = ". /home/tkcc/bin/env.sh; export PYTHONPATH=/home/tkcc/src:$PYTHONPATH CUDA_VISIBLE_DEVICES=0,1,2,3; cd /home/tkcc"


def run_remote(script: str, timeout: float) -> tuple[int, str]:
    import pexpect

    encoded = base64.b64encode(script.encode()).decode()
    child = pexpect.spawn(
        "ssh",
        ["-tt", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", "-i", SSH_KEY, f"{POD_HOST}@ssh.runpod.io"],
        encoding="utf-8",
        timeout=timeout,
        maxread=1 << 20,
    )
    try:
        child.expect(r"root@[^\r\n]+:/# ", timeout=90)
        child.sendline("stty -echo; unset HISTFILE; set +o history; printf '\\nTKCC_READY\\n'")
        child.expect_exact("\r\nTKCC_READY\r\n")
        child.expect(r"root@[^\r\n]+:/# ")
        name = f"/tmp/.tkcc-{uuid.uuid4().hex}.sh"
        child.sendline(f"echo {encoded} | base64 -d > {name}; bash {name} 2>&1; printf '\\nTKCC_EXIT:%s\\n' $?; rm -f {name}")
        child.expect(r"TKCC_EXIT:(\d+)")
        output = child.before.replace("\r\n", "\n")
        return int(child.match.group(1)), output
    finally:
        child.sendline("exit")
        child.close()


def _with_retries(script: str, timeout: float, attempts: int = 3) -> tuple[int, str]:
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            return run_remote(script, timeout)
        except Exception as exc:
            last = exc
            time.sleep(5 * (attempt + 1))
    return 255, f"remote call failed after {attempts} attempts: {last}"


def _put_file(path: str, content: str) -> str:
    encoded = base64.b64encode(content.encode()).decode()
    return f"mkdir -p {shlex.quote(str(Path(path).parent))}; echo {encoded} | base64 -d > {shlex.quote(path)}"


def cmd_submit(args) -> int:
    source = Path(args.candidate).read_text()
    remote = f"/home/tkcc/inbox/{AGENT}-{uuid.uuid4().hex[:8]}.py"
    flags = " --profile" if args.profile else ""
    script = "\n".join(
        [
            _put_file(remote, source),
            POD_ENV,
            f"python3 -m tkcc.client submit --tier {args.tier} --file {remote} --agent {shlex.quote(AGENT)} --name {shlex.quote(args.name)}{flags} --timeout {args.timeout}",
        ]
    )
    code, out = _with_retries(script, args.timeout + 120, attempts=1)
    print(out.strip())
    return code


def cmd_simple(command: str, timeout: float) -> int:
    code, out = _with_retries(f"{POD_ENV}\npython3 -m tkcc.client {command}", timeout)
    print(out.strip())
    return code


def cmd_gpu_run(args) -> int:
    source = Path(args.script).read_text()
    remote = f"/home/tkcc/inbox/{AGENT}-bench-{uuid.uuid4().hex[:8]}.py"
    script = "\n".join(
        [
            _put_file(remote, source),
            BUNDLE_ENV,
            f"exec 9>>/home/tkcc/run/gpu.lock; flock 9; timeout {int(args.timeout)} python3 {remote}; status=$?; echo exit=$status; exit $status",
        ]
    )
    code, out = _with_retries(script, args.timeout + 900, attempts=1)
    print(out.strip()[-20000:])
    return code


def cmd_board(args) -> int:
    BOARD.touch(exist_ok=True)
    if args.action == "post":
        with BOARD.open("a") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            handle.write(json.dumps({"t": time.strftime("%H:%M:%S"), "agent": AGENT, "msg": " ".join(args.text)}) + "\n")
        return 0
    lines = BOARD.read_text().splitlines()[-args.last :]
    for line in lines:
        entry = json.loads(line)
        print(f"[{entry['t']}] {entry['agent']}: {entry['msg']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tkcc")
    sub = parser.add_subparsers(dest="command", required=True)
    submit = sub.add_parser("submit")
    submit.add_argument("candidate")
    submit.add_argument("--tier", choices=("fast", "slow"), required=True)
    submit.add_argument("--name", default="")
    submit.add_argument("--profile", action="store_true")
    submit.add_argument("--timeout", type=float, default=3600)
    sub.add_parser("status")
    baseline = sub.add_parser("baseline")
    baseline.add_argument("--tier", choices=("fast", "slow"), default="fast")
    sub.add_parser("profile-baseline")
    gpu = sub.add_parser("gpu-run")
    gpu.add_argument("script")
    gpu.add_argument("--timeout", type=float, default=300)
    board = sub.add_parser("board")
    board.add_argument("action", choices=("post", "read"))
    board.add_argument("text", nargs="*")
    board.add_argument("--last", type=int, default=40)
    args = parser.parse_args(argv)
    if args.command == "submit":
        return cmd_submit(args)
    if args.command == "status":
        return cmd_simple("status", 120)
    if args.command == "baseline":
        return cmd_simple(f"baseline --tier {args.tier}", 120)
    if args.command == "profile-baseline":
        return cmd_simple("profile-baseline --tier fast", 1800)
    if args.command == "gpu-run":
        return cmd_gpu_run(args)
    return cmd_board(args)


if __name__ == "__main__":
    sys.exit(main())
