"""Recover the Vivado archive and verify its receipt, with a 20-minute resume limit."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

SSH = (
    "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
    "-o", "ServerAliveInterval=5", "-o", "ServerAliveCountMax=3",
)
REMOTE_BASE = "/home/admin/projects/gradiated/.agents/runtime/fpga-inference"


def recover(attempt, output, host, deadline):
    if not re.fullmatch(r"logits-ddr4-prefetch-build-[0-9]{8}T[0-9]{6}Z", attempt):
        raise ValueError("Unexpected build attempt name")
    remote = f"{REMOTE_BASE}/{attempt}"
    ssh = [*SSH, host]
    receipt_bytes = subprocess.run(
        [*ssh, f"cat {remote}.receipt.json"], capture_output=True, check=True, timeout=25,
    ).stdout
    receipt = json.loads(receipt_bytes)
    if receipt["archive"] != remote + ".tar.gz":
        raise ValueError("Receipt names an unexpected archive")
    archive = output / "server.tar.gz"
    partial = output / "server.tar.gz.partial"
    if archive.exists():
        raise FileExistsError(archive)
    receipt_path = output / "server.receipt.json"
    if receipt_path.exists() and receipt_path.read_bytes() != receipt_bytes:
        raise ValueError("Previous recovery attempt used a different receipt")
    receipt_path.write_bytes(receipt_bytes)
    size = partial.stat().st_size if partial.exists() else 0
    print(f"Recovering {receipt['bytes']} bytes, resuming at {size}", flush=True)
    while size < receipt["bytes"]:
        remaining = deadline - time.monotonic()
        if remaining < 10:
            raise TimeoutError("Recovery deadline reached")
        with partial.open("ab") as stream:
            try:
                subprocess.run(
                    [*ssh, f"dd if={remote}.tar.gz bs=1M iflag=skip_bytes skip={size} status=none"],
                    stdout=stream, check=True, timeout=min(remaining, 240),
                )
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
                print(error, flush=True)
                if partial.stat().st_size == size:
                    time.sleep(min(2, max(0, deadline - time.monotonic())))
        size = partial.stat().st_size
        print(f"Received {size} bytes", flush=True)
    with partial.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if size != receipt["bytes"] or digest != receipt["sha256"]:
        raise ValueError("Recovered bytes differ from the receipt")
    partial.rename(archive)
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("attempt")
    parser.add_argument("output", type=Path)
    parser.add_argument("host")
    args = parser.parse_args()
    print(json.dumps(recover(args.attempt, args.output, args.host, time.monotonic() + 1200), sort_keys=True))
