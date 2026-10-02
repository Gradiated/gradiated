import hashlib
import json
import random
import urllib.request

from autotrain import Trainer
from autotrain.data import digest, read_examples


def transfer(url, destination=None, upload=None):
    if not url.startswith("https://"):
        raise ValueError("Artifact URL must use HTTPS")
    if upload is not None:
        with open(upload, "rb") as source:
            request = urllib.request.Request(url, data=source.read(), method="PUT")
        with urllib.request.urlopen(request, timeout=120) as response:
            response.read()
        return
    with (
        urllib.request.urlopen(url, timeout=120) as response,
        open(destination, "wb") as target,
    ):
        size = 0
        while chunk := response.read(1024 * 1024):
            size += len(chunk)
            if size > 256 * 1024 * 1024:
                raise ValueError("Artifact exceeds download limit")
            target.write(chunk)


class TrainingRuntime(Trainer):
    def download(self, reference, name):
        path = self.root / name
        transfer(reference["url"], destination=path)
        if digest(path) != reference["sha256"]:
            raise ValueError("Artifact digest mismatch")
        return path

    def upload(self, path, grant):
        transfer(grant["url"], upload=path)
        return {
            "key": grant["key"],
            "sha256": digest(path),
            "size_bytes": path.stat().st_size,
        }

    def run(self, command, emit):
        self.check()
        self.load()
        self.check()
        operation = command["operation"]
        if operation == "predict":
            return self.generate(
                command["messages"],
                adapted=False,
                max_tokens=256,
                max_prompt_tokens=4096,
            )
        if operation == "train":

            def save_checkpoint(step, path):
                checkpoint = self.upload(path, command["checkpoints"][str(step)])
                emit({"type": "trainer_checkpoint", "step": step, **checkpoint})

            adapter = self.train(
                self.download(command["dataset"], "train.jsonl"),
                self.download(command["validation"], "validation.jsonl"),
                checkpoint=self.download(command["checkpoint"], "resume.tar.gz")
                if command.get("checkpoint")
                else None,
                emit=emit,
                save_checkpoint=save_checkpoint,
            )
            artifact = self.upload(adapter, command["output"])
            emit({"type": "trainer_artifact_uploaded", "name": "adapter", **artifact})
            return artifact
        if operation in ("verify", "generate"):
            adapter = self.download(command["adapter"], "adapter.tar.gz")
            if operation == "verify":
                self.verify(adapter)
                return {"verified": True, "sha256": digest(adapter)}
            self.load_adapter(adapter)
            examples = read_examples(
                self.download(command["dataset"], "evaluation.jsonl")
            )
            results = []
            for index, example in enumerate(examples):
                self.check()
                fine_first = random.Random(
                    hashlib.sha256(example["id"].encode()).digest()
                ).choice((True, False))
                if command.get("external_evaluation"):
                    fine = self.generate(example["prompt"], adapted=True)
                    results.append(
                        {
                            "id": example["id"],
                            "group": example["group"],
                            "fine_tuned": fine,
                        }
                    )
                    emit(
                        {
                            "type": "evaluation_progress",
                            "completed": index + 1,
                            "total": len(examples),
                        }
                    )
                    continue
                if fine_first:
                    fine = self.generate(example["prompt"], adapted=True)
                    comparison = self.generate(example["prompt"], adapted=False)
                else:
                    comparison = self.generate(example["prompt"], adapted=False)
                    fine = self.generate(example["prompt"], adapted=True)
                first, second = (fine, comparison) if fine_first else (comparison, fine)
                prompt = (
                    "Compare the two answers to the user's request. Reply with exactly A, B, or TIE.\nRequest:\n"
                    + json.dumps(example["prompt"])
                    + "\nAnswer A:\n"
                    + first["text"]
                    + "\nAnswer B:\n"
                    + second["text"]
                )
                judgment = (
                    self.generate(
                        [{"role": "user", "content": prompt}],
                        adapted=False,
                        max_tokens=8,
                        max_prompt_tokens=4096,
                    )["text"]
                    .strip()
                    .upper()
                )
                results.append(
                    {
                        "id": example["id"],
                        "group": example["group"],
                        "fine_tuned": fine,
                        "comparison": comparison,
                        "judgment": judgment,
                        "fine_tuned_first": fine_first,
                    }
                )
                emit(
                    {
                        "type": "evaluation_progress",
                        "completed": index + 1,
                        "total": len(examples),
                    }
                )
            path = self.root / "predictions.json"
            path.write_text(json.dumps(results))
            return self.upload(path, command["output"])
        raise ValueError("Unknown trainer operation")
