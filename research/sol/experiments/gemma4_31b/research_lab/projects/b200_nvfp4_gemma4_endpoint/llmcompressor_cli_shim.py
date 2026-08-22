import argparse

from llmcompressor.entrypoints.oneshot import oneshot


parser = argparse.ArgumentParser()
parser.add_argument("command", choices=["oneshot"])
parser.add_argument("--model", required=True)
parser.add_argument("--recipe", required=True)
parser.add_argument("--dataset", required=True)
parser.add_argument("--output-dir", required=True)
args = parser.parse_args()
oneshot(model=args.model, recipe=args.recipe, dataset=args.dataset, output_dir=args.output_dir)
