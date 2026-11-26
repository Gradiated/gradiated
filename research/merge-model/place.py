"""Start the pilot or corpus trainer on a named dev VM with an existing deadline."""

import argparse
import io
import json
import shlex
import tarfile
import time

from launch import HERE, remote


def main():
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=("pilot", "corpus"))
    p.add_argument("--vm", required=True)
    p.add_argument("--s3", required=True)
    p.add_argument("--deadline", type=int, required=True)
    p.add_argument("--devices", type=int, nargs="+", default=[0])
    a = p.parse_args()
    if a.deadline - time.time() < 900:
        p.error("the training allocation needs at least 15 minutes remaining")
    blob = io.BytesIO()
    with tarfile.open(fileobj=blob, mode="w:gz") as tar:
        for name in ("night.py", "train.py", "evaluate.py", "freeze.py", "mine.py"):
            value = (HERE / name).read_bytes()
            item = tarfile.TarInfo(name)
            item.size = len(value)
            tar.addfile(item, io.BytesIO(value))
    root = f"merge-training-{a.mode}"
    stage = f'umask 077; mkdir -p "$HOME/{root}" && tar -xzf - -C "$HOME/{root}"'
    remote(a.vm, stage, 45, blob.getvalue())
    command = shlex.join(
        [
            "python3",
            "night.py",
            a.mode,
            "--s3",
            a.s3,
            "--work",
            "work",
            "--deadline",
            str(a.deadline),
            "--devices",
            *map(str, a.devices),
        ]
    )
    wrapped = f"""cd "$HOME/{root}" && (flock -n 9 || exit 9
if [ -f worker.pid ] && kill -0 "$(cat worker.pid)" 2>/dev/null; then
  printf already-running
else
  left=$(( {a.deadline} - $(date +%s) - 12 ))
  test "$left" -gt 0 || exit 4
  nohup timeout -k 7 "$left" {command} > run.log 2>&1 </dev/null 9>&- &
  echo $! > worker.pid
  kill -0 "$(cat worker.pid)" && printf started
fi
) 9>lock"""
    value = remote(a.vm, wrapped, 40).get("stdout", "").strip()
    if value not in ("started", "already-running"):
        raise RuntimeError("training process did not acknowledge launch")
    print(
        json.dumps(
            dict(
                vm=a.vm,
                mode=a.mode,
                status=value,
                root=root,
                deadline=a.deadline,
                devices=a.devices,
            )
        )
    )


if __name__ == "__main__":
    main()
