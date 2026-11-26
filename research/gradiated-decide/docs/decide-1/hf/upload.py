"""Assemble the gradiated/linden-1 Hugging Face repo and upload it.

Usage: HF_TOKEN=... python upload.py MERGE_DIR STAGING_DIR [--repo gradiated/linden-1] [--public] [--dry-run]

MERGE_DIR is the gd-kl2-s1000-a0.5 blend (s3://<dev bucket>/gradiated-decide/runs/merges/gd-kl2-s1000-a0.5). The repo
gets, in STAGING_DIR (hard links, no copies of the weights):
- from MERGE_DIR: the weights, index, config, generation config, tokenizer, chat template and processor config;
- from PelaAI/KnowLine-31B-Gen1.5 at the pinned revision (the code the production runtime pins): the serving code,
  temperatures, INFERENCE.md, LICENSE and .gitattributes;
- from this directory: README.md (the model card);
- SHA256SUMS of every file, written here.
The repo is created private unless --public; make it public on the Hub (or rerun with --public) once checked.
"""

import argparse
import hashlib
import os
import shutil
from pathlib import Path

from huggingface_hub import HfApi, hf_hub_download

KNOWLINE = "PelaAI/KnowLine-31B-Gen1.5"
KNOWLINE_REVISION = "56ca884a8e3195c9c0786a4ec22e651669d04ba9"
FROM_MERGE = ("config.json", "generation_config.json", "model.safetensors.index.json", "tokenizer.json",
              "tokenizer_config.json", "chat_template.jinja", "processor_config.json")
FROM_KNOWLINE = (".gitattributes", "LICENSE")
HERE = Path(__file__).resolve().parent


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 24), b""):
            h.update(block)
    return h.hexdigest()


def stage(merge: Path, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for old in out.iterdir():
        shutil.rmtree(old) if old.is_dir() else old.unlink()
    weights = sorted(merge.glob("model-*.safetensors"))
    if len(weights) != 12:
        raise SystemExit(f"expected 12 weight shards in {merge}, found {len(weights)}")
    for src in [*weights, *(merge / name for name in FROM_MERGE)]:
        os.link(src, out / src.name)
    for name in FROM_KNOWLINE:
        shutil.copy(hf_hub_download(KNOWLINE, name, revision=KNOWLINE_REVISION), out / name)
    shutil.copy(HERE / "README.md", out / "README.md")
    files = [p for p in sorted(out.iterdir()) if p.is_file() and p.name not in (".gitattributes", "SHA256SUMS")]
    sums = [f"{sha256(p)}  {p.name}" for p in files]
    (out / "SHA256SUMS").write_text("\n".join(sums) + "\n")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("merge", type=Path)
    p.add_argument("staging", type=Path)
    p.add_argument("--repo", default="gradiated/linden-1")
    p.add_argument("--public", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    stage(a.merge, a.staging)
    print("\n".join(sorted(x.name for x in a.staging.iterdir())))
    if a.dry_run:
        return
    api = HfApi()
    api.create_repo(a.repo, repo_type="model", private=not a.public, exist_ok=True)
    api.upload_large_folder(repo_id=a.repo, repo_type="model", folder_path=str(a.staging))
    print("revision", api.model_info(a.repo).sha)


if __name__ == "__main__":
    main()
