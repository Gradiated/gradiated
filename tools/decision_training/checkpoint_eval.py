"""Inference-only, singleton comparison of a frozen adapter with untouched Inkling."""

import argparse
import hashlib
import json
import math
import time
from collections import defaultdict
from pathlib import Path

from data import read_jsonl
from prompting import render_prompt


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_adapter(directory):
    manifest = json.loads((directory / "checkpoint-complete.json").read_text())
    for name in ("adapter_config.json", "adapter_model.safetensors"):
        if digest(directory / name) != manifest["files"][name]:
            raise ValueError("checkpoint payload hash mismatch: " + name)
    return manifest


def validate_row(row):
    labels = row["labels"]
    if not 2 <= len(labels) <= 26 or len(set(labels)) != len(labels):
        raise ValueError("unsupported option count or duplicate labels")
    if len(row["descriptions"]) != len(labels) or row["gold"] not in labels:
        raise ValueError("invalid aligned options or gold")
    return row


def predicted_label(labels, probabilities):
    return min(zip(labels, probabilities), key=lambda item: (-item[1], item[0]))[0]


def summarize(records):
    groups = defaultdict(list)
    for row in records:
        row = {
            **row,
            **{
                arm: {
                    **row[arm],
                    "label": predicted_label(row["labels"], row[arm]["probabilities"]),
                }
                for arm in ("base", "checkpoint")
                if arm in row
            },
        }
        groups[row["benchmark"]].append(row)
    report = {}
    for name, rows in groups.items():
        pairs = [r for r in rows if "base" in r and "checkpoint" in r]
        arms = {}
        for arm in ("base", "checkpoint"):
            items = [r for r in rows if arm in r]
            if not items:
                continue
            correct = [r[arm]["label"] == r["gold"] for r in items]
            brier = [
                sum(
                    (p - (label == r["gold"])) ** 2
                    for label, p in zip(r["labels"], r[arm]["probabilities"])
                )
                for r in items
            ]
            ece = 0
            for b in range(10):
                ids = [
                    i
                    for i, r in enumerate(items)
                    if min(9, int(max(r[arm]["probabilities"]) * 10)) == b
                ]
                if ids:
                    ece += abs(
                        sum(max(items[i][arm]["probabilities"]) for i in ids)
                        - sum(correct[i] for i in ids)
                    ) / len(items)
            f1s = []
            for label in sorted({l for r in items for l in r["labels"]}):
                tp = sum(r["gold"] == label and r[arm]["label"] == label for r in items)
                den = sum(r["gold"] == label for r in items) + sum(
                    r[arm]["label"] == label for r in items
                )
                f1s.append(2 * tp / den if den else 0)
            arms[arm] = {
                "n": len(items),
                "correct": sum(correct),
                "accuracy": sum(correct) / len(rows),
                "accuracy_supported_only": sum(correct) / len(items),
                "coverage": len(items) / len(rows),
                "brier": sum(brier) / len(items),
                "ece": ece,
                "macro_f1_supported_only": sum(f1s) / len(f1s),
            }
        wins = sum(
            r["checkpoint"]["label"] == r["gold"] and r["base"]["label"] != r["gold"]
            for r in pairs
        )
        losses = sum(
            r["checkpoint"]["label"] != r["gold"] and r["base"]["label"] == r["gold"]
            for r in pairs
        )
        n = wins + losses
        p = (
            min(
                1, 2 * sum(math.comb(n, k) for k in range(min(wins, losses) + 1)) / 2**n
            )
            if n
            else 1
        )
        report[name] = {
            "requested": len(rows),
            "paired": len(pairs),
            "wins": wins,
            "losses": losses,
            "mcnemar_exact_p": p,
            "arms": arms,
        }
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--rows", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--deadline-unix", type=float, required=True)
    parser.add_argument("--max-length", type=int, default=2048)
    args = parser.parse_args()

    def check():
        if time.time() >= args.deadline_unix - 120:
            raise TimeoutError("evaluation deadline; reserve two minutes for retention")

    check()
    manifest = verify_adapter(args.checkpoint)
    from snapshot import verify_snapshot

    model_identity = verify_snapshot(args.model_dir.parent, check)
    rows = [validate_row(row) for row in read_jsonl(args.rows)]
    if not rows or len({r["id"] for r in rows}) != len(rows):
        raise ValueError("empty evaluation or duplicate evaluation IDs")
    args.output_dir.mkdir(parents=True, exist_ok=False)
    identity = {
        "model_manifest_sha256": model_identity,
        "checkpoint_manifest_sha256": digest(
            args.checkpoint / "checkpoint-complete.json"
        ),
        "original_writer_identity": manifest.get("identity"),
        "checkpoint_manifest": manifest,
        "analysis_source_sha256": {
            name: digest(Path(__file__).with_name(name))
            for name in (
                "checkpoint_eval.py",
                "adapter_restore.py",
                "prompting.py",
                "snapshot.py",
                "runtime.py",
            )
        },
        "rows_sha256": digest(args.rows),
        "max_length": args.max_length,
        "evaluation": "individual unpadded native letter logits; no optimizer resume; no truncation",
        "deadline_unix": args.deadline_unix,
    }
    (args.output_dir / "identity.json").write_text(json.dumps(identity, indent=2))
    import torch
    from adapter_restore import restore_adapter
    from peft import LoraConfig, get_peft_model
    from runtime import runtime_fingerprint
    from safetensors.torch import load_file
    from transformers import AutoTokenizer, Inkling2LoopForConditionalGeneration

    torch.set_num_threads(12)
    (args.output_dir / "runtime.json").write_text(
        json.dumps(runtime_fingerprint(check), indent=2)
    )
    check()
    tokenizer = AutoTokenizer.from_pretrained(args.model_dir, local_files_only=True)
    model = Inkling2LoopForConditionalGeneration.from_pretrained(
        args.model_dir, dtype=torch.bfloat16, device_map="cuda", local_files_only=True
    ).eval()
    letter_ids = [
        tokenizer.encode(chr(65 + i), add_special_tokens=False) for i in range(26)
    ]
    assert all(len(ids) == 1 for ids in letter_ids)
    letter_ids = torch.tensor([ids[0] for ids in letter_ids], device="cuda")
    encoded = []
    for row in rows:
        check()
        ids = tokenizer.encode(render_prompt(tokenizer, row), add_special_tokens=False)
        encoded.append((row, ids))
    records = {
        r["id"]: {k: r[k] for k in ("id", "benchmark", "labels", "gold")} for r in rows
    }
    with (args.output_dir / "predictions.jsonl").open("w") as stream:
        for arm in ("base", "checkpoint"):
            check()
            if arm == "checkpoint":
                config = LoraConfig.from_pretrained(args.checkpoint)
                config.inference_mode = False
                model = get_peft_model(model, config)
                proof = restore_adapter(
                    model, load_file(args.checkpoint / "adapter_model.safetensors")
                )
                (args.output_dir / "adapter-proof.json").write_text(json.dumps(proof))
                model.eval()
            for i, (row, ids) in enumerate(encoded):
                check()
                record = records[row["id"]]
                if len(ids) > args.max_length:
                    event = {
                        "id": row["id"],
                        "arm": arm,
                        "status": "unsupported_length",
                        "input_tokens": len(ids),
                    }
                else:
                    start = time.monotonic()
                    x = torch.tensor([ids], device="cuda")
                    with torch.inference_mode():
                        logits = (
                            model(
                                input_ids=x,
                                attention_mask=torch.ones_like(x),
                                use_cache=False,
                                logits_to_keep=1,
                            )
                            .logits[0, -1, letter_ids[: len(row["labels"])]]
                            .float()
                        )
                        if not torch.isfinite(logits).all():
                            raise ValueError("nonfinite evaluation logits")
                        probabilities = logits.softmax(-1).tolist()
                    torch.cuda.synchronize()
                    result = {
                        "label": predicted_label(row["labels"], probabilities),
                        "probabilities": probabilities,
                        "logits": logits.tolist(),
                        "input_tokens": len(ids),
                        "seconds": time.monotonic() - start,
                    }
                    record[arm] = result
                    event = dict(id=row["id"], arm=arm, status="ok", **result)
                stream.write(json.dumps(event) + "\n")
                stream.flush()
                if (i + 1) % 50 == 0:
                    (args.output_dir / "comparison.json").write_text(
                        json.dumps(summarize(records.values()), indent=2)
                    )
                    (args.output_dir / "progress.json").write_text(
                        json.dumps(
                            {
                                "arm": arm,
                                "completed": i + 1,
                                "total": len(rows),
                                "observed_unix": time.time(),
                            }
                        )
                    )
                    print(
                        json.dumps(
                            {
                                "event": "progress",
                                "arm": arm,
                                "completed": i + 1,
                                "total": len(rows),
                            }
                        ),
                        flush=True,
                    )
            (args.output_dir / "comparison.json").write_text(
                json.dumps(summarize(records.values()), indent=2)
            )
    (args.output_dir / "COMPLETE.json").write_text(
        json.dumps(
            {"completed_unix": time.time(), "rows": len(rows), "identity": identity}
        )
    )


if __name__ == "__main__":
    main()
