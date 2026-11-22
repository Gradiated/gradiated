# Earlier experiments and recovery

The active project was simplified at Aidan's request after selecting the 27K
BOS-only transformer. Earlier experiment code, raw transcripts, duplicate datasets
and launchers were removed from the working tree. Creative source material was
collected under material/; selected model artifacts are under model/.

## Findings worth retaining

- Tiny pretrained SmolLM variants did not reliably acquire the desired character.
  Aidan found an early 360M version funny, but later identity/style fits became
  incoherent. Overfitting was plausible, not an isolated proven cause.
- Plain Qwen was generally more conversational than the restrictive intern
  variants. Longer prompts, larger datasets and broader adapters did not reliably
  produce the intended funny character while preserving conversation.
- Aidan simplified acceptance to coherent chip jokes, including authored text.
  Lookup/constrained modes were explored and explicitly distinguished from neural
  generation of the displayed words.
- Keyed Qwen joke reproduction worked well. The accepted larger-model format was
  four-bit affine with groups of 32, with occasional wrong/mixed jokes accepted.
  This larger model is now retired from the active tree; it has not run on FPGA.
- Fresh 267K and 1.03M byte transformers reproduced all 48 trained keyed jokes.
  A 26,720-parameter one-block model did too. The host selected identifiers and
  controlled repeats, so that did not demonstrate autonomous varied generation.
- Removing identifiers and supervising the first byte yielded the current
  generator: 127/128 exact jokes across 41 distinct jokes on reserved seeds, with
  one preserved gibberish case and ordinary repetitions. Every joke is trained.
- Strict historical GPU numerical gates sometimes failed; CPU FP32 checks passed
  in their specific scopes. Later tiny runners explicitly disabled reduced
  precision and passed unchanged NumPy/cache tolerances. This does not erase
  prior failures, prove a single cause or establish all-model equivalence.

All outcomes above are scoped Mac results. No FPGA circuit, simulation, physical
fit, measured timing/energy or customer cost comparison has been completed.

## Recover tracked history

Local tag: `codex/fpga-experiments-before-cleanup`, commit `e164e1958`.
For example, from the repository root:

```sh
git show codex/fpga-experiments-before-cleanup:research/fpga-inference/data/generative-tiny-v1/comparison.md
git ls-tree -r --name-only codex/fpga-experiments-before-cleanup research/fpga-inference
```

Use a separate checkout if you need runnable old source; do not restore it over
the current project or the article checkout. The tag is local and is not published.
No Git history was rewritten. Old runtime weights were never in Git and were
removed locally during cleanup; recovering a retired tuned model would require
another backup or retraining, plus any necessary original model download.

The retained current FP32/q8 payloads are hash-pinned under ignored
`.agents/runtime/fpga-inference/models/tiny/`. Preserve those local files: a fresh
Git clone does not contain their weights. The original training implementation,
recipe and input bytes remain at the recovery checkpoint.
