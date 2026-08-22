import argparse

from datasets import load_dataset
from llmcompressor.entrypoints.oneshot import oneshot


parser = argparse.ArgumentParser()
parser.add_argument("command", choices=["oneshot"])
parser.add_argument("--model", required=True)
parser.add_argument("--recipe", required=True)
parser.add_argument("--dataset", required=True)
parser.add_argument("--output-dir", required=True)
args = parser.parse_args()
calibration = load_dataset("json", data_files=args.dataset, split="train")
oneshot(
    model=args.model,
    recipe=args.recipe,
    dataset=calibration,
    output_dir=args.output_dir,
    max_seq_length=4096,
)
