"""Score exact merged hunks with the same final-split protocol as W1B."""

import argparse
import gzip
import json
import re
import time
from collections import Counter, defaultdict
from pathlib import Path

RESOLUTION = re.compile(r"<resolution>\n?(.*?)</resolution>", re.DOTALL)


def norm(lines):
    result = [line.rstrip() for line in lines]
    while result and not result[0]:
        result.pop(0)
    while result and not result[-1]:
        result.pop()
    return result


def parse(text):
    if "<abstain/>" in text[:40]:
        return "abstain", []
    found = RESOLUTION.search(text)
    return ("answer", found.group(1).splitlines()) if found else ("malformed", [])


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True)
    p.add_argument(
        "--test", nargs=2, metavar=("LABEL", "FILE"), action="append", required=True
    )
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--max-len", type=int, default=8192)
    p.add_argument("--limit", type=int, default=1000)
    a = p.parse_args()
    labels = [label for label, _ in a.test]
    if len(set(labels)) != len(labels) or any(
        not re.fullmatch(r"[a-zA-Z0-9_-]+", label) for label in labels
    ):
        p.error(
            "test labels must be unique and contain only letters, digits, hyphens or underscores"
        )

    from vllm import LLM, SamplingParams
    from vllm.config.kernel import KernelConfig

    a.out.mkdir(parents=True, exist_ok=True)
    base = LLM(
        a.model,
        dtype="bfloat16",
        max_model_len=a.max_len,
        seed=0,
        enforce_eager=True,
        kernel_config=KernelConfig(enable_jit_warmup=False),
        limit_mm_per_prompt={"image": 0, "video": 0},
    )
    tokenizer = base.get_tokenizer()
    report = {}
    for key, path in a.test:
        file = Path(path)
        source = gzip.open(file, "rt") if file.suffix == ".gz" else file.open()
        with source:
            rows = [
                r
                for r in map(json.loads, source)
                if r.get("code") and r.get("aligned") and r.get("subset") == "final"
            ][: a.limit]
        if not rows:
            raise ValueError(f"no eligible test rows in {file.name}")
        prompts = {}
        sampling = {}
        for i, r in enumerate(rows):
            prompt = r["prompt"]
            n = len(tokenizer(prompt, add_special_tokens=False)["input_ids"])
            source = "\n".join(r["ours"] + r["base"] + r["theirs"])
            sides = len(tokenizer(source, add_special_tokens=False)["input_ids"])
            limit = min(2 * sides + 64, a.max_len - n - 8, 4096)
            if limit > 8:
                prompts[i] = prompt
                sampling[i] = SamplingParams(
                    temperature=0,
                    max_tokens=limit,
                    stop=["</resolution>", "<abstain/>"],
                    include_stop_str_in_output=True,
                )
        t0 = time.time()
        outputs = base.generate(
            list(prompts.values()), list(sampling.values()), use_tqdm=False
        )
        out = dict(zip(prompts, outputs, strict=True))
        by_repo = defaultdict(Counter)
        counts = Counter()
        with (a.out / f"{key}.preds.jsonl").open("w") as f:
            for i, r in enumerate(rows):
                kind, lines = (
                    parse(out[i].outputs[0].text) if i in out else ("oversize", [])
                )
                correct = kind == "answer" and norm(lines) == norm(r["resolution"])
                outrow = dict(
                    uid=r["uid"],
                    repo=r["repo"],
                    merge=r.get("merge"),
                    kind=kind,
                    correct=correct,
                    cls=r["cls"],
                    aligned=True,
                    code=True,
                    subset="final",
                )
                counts.update(total=1, correct=int(correct))
                counts[kind] += 1
                by_repo[r["repo"]].update(total=1, correct=int(correct))
                f.write(json.dumps(outrow) + "\n")
        report[key] = dict(
            counts=counts, by_repo=by_repo, seconds=round(time.time() - t0, 2)
        )
    (a.out / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v["counts"] for k, v in report.items()}))


if __name__ == "__main__":
    main()
