#!/usr/bin/env python3
import json
import fcntl
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time


def process_start(pid):
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return None if fields[0] == "Z" else fields[19]
    except FileNotFoundError:
        return None


def alive(state):
    return state["start"] is not None and process_start(state["pid"]) == state["start"]


def execute(root, operation, request):
    with (root / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return execute_locked(root, operation, request)


def execute_locked(root, operation, request):
    if operation == "ping":
        return {"ready": True}
    if operation == "list":
        return [json.loads(p.read_text())["pod"] for p in root.glob("*/state.json")]
    uid = request["uid"]
    if not re.fullmatch(r"[0-9a-f-]{36}", uid):
        raise ValueError("Invalid pod UID")
    directory = root / uid
    state_file = directory / "state.json"
    if operation == "create":
        if state_file.exists():
            return {"created": False}
        count = request.get("gpu_count", 0)
        if type(count) is not int or not 0 <= count <= 4:
            raise ValueError("Invalid GPU count")
        selected = []
        if count:
            inventory = subprocess.run(
                ["nvidia-smi", "--query-gpu=uuid", "--format=csv,noheader"],
                check=True, capture_output=True, text=True, timeout=10,
            ).stdout.strip().splitlines()
            used = {gpu for state_path in root.glob("*/state.json")
                    for gpu in json.loads(state_path.read_text()).get("gpus", [])}
            selected = [gpu for gpu in inventory if gpu not in used][:count]
            if len(selected) != count:
                raise ValueError("Insufficient unclaimed GPUs")
        program = "import os,time; print('VK_READY uid='+str(os.getuid()),flush=True); time.sleep(600)"
        if count:
            program = (
                "import ctypes,json,os,time; lib=ctypes.CDLL('libcuda.so.1'); "
                "assert lib.cuInit(0)==0; count=ctypes.c_int(); "
                "assert lib.cuDeviceGetCount(ctypes.byref(count))==0; "
                "assert count.value==" + str(count) + "; "
                "print('VK_READY '+json.dumps({'uid':os.getuid(),'cuda_devices':count.value}),flush=True); time.sleep(600)"
            )
        directory.mkdir(mode=0o755)
        log = directory / "stdout.log"
        with log.open("wb") as output:
            pid = os.fork()
            if pid == 0:
                try:
                    os.setsid()
                    with open(os.devnull, "rb") as input_stream:
                        os.dup2(input_stream.fileno(), 0)
                    os.dup2(output.fileno(), 1)
                    os.dup2(output.fileno(), 2)
                    os.chdir("/tmp")
                    os.setgroups([])
                    os.setgid(65534)
                    os.setuid(65534)
                    os.execve("/usr/bin/python3", ["python3", "-u", "-c", program],
                              {"PATH": "/usr/bin:/bin", "CUDA_VISIBLE_DEVICES": ",".join(selected)})
                finally:
                    os._exit(1)
        state = {"pid": pid, "start": process_start(pid), "pod": request["pod"], "gpus": selected}
        state_file.write_text(json.dumps(state))
        return {"created": True}
    if operation == "delete" and not state_file.exists():
        return {"deleted": False}
    state = json.loads(state_file.read_text())
    if operation == "status":
        return {"running": alive(state), "ready": "VK_READY" in (directory / "stdout.log").read_text(), "pid": state["pid"]}
    if operation == "logs":
        return {"logs": (directory / "stdout.log").read_text()[-65536:]}
    if operation == "delete":
        if alive(state):
            os.killpg(state["pid"], signal.SIGTERM)
            for _ in range(20):
                if not alive(state):
                    break
                time.sleep(0.05)
            if alive(state):
                os.killpg(state["pid"], signal.SIGKILL)
        try:
            os.waitpid(state["pid"], os.WNOHANG)
        except ChildProcessError:
            pass
        state_file.unlink()
        (directory / "stdout.log").unlink(missing_ok=True)
        directory.rmdir()
        return {"deleted": True}
    raise ValueError("Unsupported operation")


if __name__ == "__main__":
    root = Path(__file__).resolve().parent / "pods"
    root.mkdir(mode=0o755, exist_ok=True)
    print(json.dumps(execute(root, sys.argv[1], json.load(sys.stdin))))
