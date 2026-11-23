"""Run a benchmark pilot or a quality-gated model ladder on an existing dev VM."""

import argparse
import json
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

SOURCE = Path(__file__).resolve().parent
OLD = "s3://gradiated-dev-training-873716897517/merge-model/ds-v1/dataset/w1b"
REVISIONS = {
    "0.8": "2fc06364715b967f1860aea9cf38778875588b17",
    "2": "15852e8c16360a2fea060d615a32b45270f8a8fc",
    "4": "851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a",
}
ENV = dict(
    os.environ,
    PATH=f"{Path.home()}/.local/bin:" + os.environ["PATH"],
    HF_HUB_DISABLE_TELEMETRY="1",
    AWS_RETRY_MODE="standard",
    AWS_MAX_ATTEMPTS="3",
)
BOOTSTRAP = r"""
set -eu
if [ ! -f /usr/include/python3.12/Python.h ]; then
 (sudo apt-get install -y -qq python3.12-dev || (sudo apt-get update -qq && sudo apt-get install -y -qq python3.12-dev)) &
 header=$!
else
 header=
fi
if ! command -v uv >/dev/null; then curl -LsSf https://astral.sh/uv/install.sh | sh; fi
if ! command -v aws >/dev/null; then uv tool install -q awscli; fi
if [ ! -x "$1/bin/python" ]; then uv venv -q -p 3.12 "$1"; fi
uv pip install -q --python "$1/bin/python" vllm==0.34.0 transformers==5.22.0 peft==0.22.0 flash-linear-attention==0.6.0
if [ -n "$header" ]; then wait "$header"; fi
"$1/bin/python" -c 'import torch, vllm, peft; assert torch.cuda.is_available(); print(torch.__version__, vllm.__version__, peft.__version__)'
"""


def log(name, **fields):
    print(json.dumps(dict(event=name, at=int(time.time()), **fields)), flush=True)


def run(args, deadline, max_seconds=300, env=ENV, output=None):
    left = min(max_seconds, int(deadline - time.time() - 5))
    if left < 3:
        raise TimeoutError("session deadline")
    with output.open("wb") if output else open(os.devnull, "wb") as f:
        subprocess.run(
            ["timeout", "-k", "10", str(left), *map(str, args)],
            env=env,
            stdout=f,
            stderr=subprocess.STDOUT,
            timeout=left + 14,
            check=True,
        )


def s3_copy(source, dest, deadline, max_seconds=85):
    run(["aws", "s3", "cp", "--quiet", source, dest], deadline, max_seconds)


def setup(work, deadline):
    env = work / "venv"
    log("runtime_setup")
    run(
        ["bash", "-c", BOOTSTRAP, "bootstrap", env],
        deadline,
        900,
        output=work / "bootstrap.log",
    )
    log("runtime_ready")
    return env / "bin/python"


def retain_log(path, prefix, deadline):
    try:
        s3_copy(path, f"{prefix}/{path.name}", deadline, 35)
    except (TimeoutError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        log("log_upload_error", path=str(path))


def train_arm(
    python, work, size, index, source, tests, prefix, deadline, examples, max_steps=0
):
    job = work / f"qwen-{size}b"
    job.mkdir(parents=True, exist_ok=True)
    env = dict(ENV, CUDA_VISIBLE_DEVICES=str(index))
    log("train_launch", size=size, gpu=index, examples=examples, deadline=deadline)
    try:
        argv = [
            python,
            SOURCE / "train.py",
            "--model",
            f"Qwen/Qwen3.5-{size}B",
            "--revision",
            REVISIONS[size],
            "--train",
            source,
            "--out",
            job,
            "--persist",
            prefix,
            "--deadline",
            str(deadline - 70),
            "--examples",
            str(examples),
            "--max-steps",
            str(max_steps),
        ]
        run(
            argv,
            deadline - 48,
            deadline - int(time.time()),
            env,
            output=job / "train.log",
        )
        metadata_path = job / "train_meta.json"
        s3_copy(metadata_path, f"{prefix}/train_meta.json", deadline)
        metadata = json.loads(metadata_path.read_text())
        if metadata["complete"] is not True:
            log(
                "arm_incomplete",
                size=size,
                steps=metadata["step"],
                planned_steps=metadata["config"]["steps"],
                tokens=metadata["tokens"],
            )
            return False
        log("eval_launch", size=size)
        args = [
            python,
            SOURCE / "evaluate.py",
            "--model",
            job / "merged",
            "--out",
            job / "evaluation",
        ]
        for label, test in tests:
            args.extend(["--test", label, test])
        run(args, deadline, 650, env, output=job / "evaluation.log")
        run(
            [
                "aws",
                "s3",
                "sync",
                "--quiet",
                job / "evaluation",
                f"{prefix}/evaluation/",
            ],
            deadline,
            100,
        )
        log("arm_finished", size=size, output=prefix)
        return True
    except (
        OSError,
        RuntimeError,
        TimeoutError,
        ValueError,
        KeyError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
    ) as error:
        log("arm_error", size=size, detail=str(error)[:500])
        return False
    finally:
        for name in ("train.log", "evaluation.log", "spec.json"):
            if (job / name).exists():
                retain_log(job / name, prefix, deadline)


def old_files(work, deadline, training):
    out = work / "w1b"
    out.mkdir(exist_ok=True)
    names = ["test_repo", "test_time"] + (["train"] if training else [])
    for key in names:
        path = out / f"{key}.jsonl"
        if not path.exists():
            tmp = path.with_suffix(".tmp")
            s3_copy(f"{OLD}/{key}__ctx60_c.jsonl", tmp, deadline, 100)
            tmp.replace(path)
    return out


def snapshot(a, work, protected):
    shards = work / "shards"
    shards.mkdir(exist_ok=True)
    out = work / "snapshots" / str(int(time.time()))
    out.mkdir(parents=True, exist_ok=True)
    run(["aws", "s3", "sync", "--quiet", f"{a.s3}/shards/", shards], a.deadline, 530)
    run(
        [
            "python3",
            SOURCE / "freeze.py",
            shards,
            out,
            "--protect",
            protected / "test_repo.jsonl",
            "--protect",
            protected / "test_time.jsonl",
        ],
        a.deadline,
        650,
        output=out / "freeze.log",
    )
    report = json.loads((out / "manifest.json").read_text())
    for name in ("train", "test_repo", "test_time"):
        s3_copy(
            out / f"{name}.jsonl.gz",
            f"{a.s3}/datasets/{out.name}/{name}.jsonl.gz",
            a.deadline,
            145,
        )
    s3_copy(
        out / "manifest.json", f"{a.s3}/datasets/{out.name}/manifest.json", a.deadline
    )
    split = report["splits"]
    log(
        "snapshot",
        output=f"{a.s3}/datasets/{out.name}",
        rows={k: v["rows"] for k, v in split.items()},
        train_repos=len(split["train"]["repos"]),
        train_languages=len(split["train"]["languages"]),
    )
    train = split["train"]
    passed = (
        train["rows"] >= a.min_examples
        and len(train["repos"]) >= 25
        and len(train["languages"]) >= 6
        and split["test_repo"]["rows"] >= 150
        and split["test_time"]["rows"] >= 150
    )
    return out, report, passed


def corpus(a, work):
    protected = old_files(work, a.deadline, False)
    ready = None
    while time.time() < a.deadline - 300:
        try:
            out, report, passed = snapshot(a, work, protected)
        except (
            OSError,
            ValueError,
            TimeoutError,
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
        ) as error:
            log("snapshot_error", detail=str(error)[:500])
        else:
            if passed:
                ready = (out, report)
                break
        time.sleep(max(0, min(1200, a.deadline - 350 - time.time())))
    if ready is None:
        log("training_gate_pending", minimum=a.min_examples)
        return 2
    out, report = ready
    if a.deadline - time.time() < 1200:
        log("dataset_ready_after_training_window", snapshot=out.name)
        return 2
    python = setup(work, a.deadline)
    examples = min(100_000, report["splits"]["train"]["rows"])
    test_splits = ("test_repo", "test_time")
    work_tests = [(f"w1b_{key}", protected / f"{key}.jsonl") for key in test_splits]
    work_tests.extend((f"corpus_{key}", out / f"{key}.jsonl.gz") for key in test_splits)
    arm_sizes = list(REVISIONS)
    with ThreadPoolExecutor(max_workers=len(a.devices)) as pool:

        def chain(index):
            device = a.devices[index]
            outcomes = []
            for size in arm_sizes[index :: len(a.devices)]:
                arm_deadline = min(
                    a.deadline,
                    int(
                        time.time()
                        + (a.deadline - time.time())
                        / max(
                            1, len(arm_sizes[index :: len(a.devices)]) - len(outcomes)
                        )
                    ),
                )
                passed = train_arm(
                    python,
                    work,
                    size,
                    device,
                    out / "train.jsonl.gz",
                    work_tests,
                    f"{a.s3}/training/{out.name}/qwen-{size}b",
                    arm_deadline,
                    examples,
                )
                outcomes.append(passed)
            return outcomes

        jobs = [pool.submit(chain, i) for i in range(len(a.devices))]
        outcomes = [
            completed for job in as_completed(jobs) for completed in job.result()
        ]
    return 0 if all(outcomes) else 1


def main():
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=("pilot", "corpus"))
    p.add_argument("--s3", required=True)
    p.add_argument("--work", type=Path, required=True)
    p.add_argument("--deadline", type=int, required=True)
    p.add_argument("--devices", type=int, nargs="+", default=[0])
    p.add_argument("--min-examples", type=int, default=25_000)
    a = p.parse_args()
    if len(set(a.devices)) != len(a.devices) or len(a.devices) > 4:
        p.error("provide up to four unique device IDs")
    a.work.mkdir(parents=True, exist_ok=True)
    if a.mode == "corpus":
        return corpus(a, a.work)
    pilot_deadline = min(a.deadline, int(time.time() + 3 * 3600))
    source = old_files(a.work, pilot_deadline, True)
    python = setup(a.work, pilot_deadline)
    tests = [
        (f"w1b_{key}", source / f"{key}.jsonl") for key in ("test_repo", "test_time")
    ]
    result = train_arm(
        python,
        a.work,
        "0.8",
        a.devices[0],
        source / "train.jsonl",
        tests,
        f"{a.s3}/pilot/w1b-qwen-0.8b-smoke",
        pilot_deadline,
        512,
        max_steps=2,
    )
    return 0 if result else 1


if __name__ == "__main__":
    raise SystemExit(main())
