# Merge-model learning curves

## Overnight 4B run

The fixed training probe contains 256 examples retained by the 4,096-token training limit. The repository holdout contains 611 conflicts from Apache Cloudberry, Roslyn and React Native. Each point scores the same gold resolution tokens with teacher forcing and includes EOS. The two samples contribute 16,316 and 56,494 scored tokens, respectively. The per-token cross-entropy uses natural logarithms. Step zero uses the public Qwen3.5-4B checkpoint. The other seven points use the exact saved adapters from the completed 3,671-step run.

The unseen-repository loss fell from 0.2471 to 0.0229 by step 195 and reached 0.01945 at the final checkpoint. The fixed training probe fell from 0.1961 to 0.01854. Exact historical resolution on the same repository holdout was 416/611 at the final checkpoint. A single token difference can change the exact-match score for an entire conflict.

![4B merge training and test loss](4b-loss.png)

[Checkpoint data](4b-checkpoint-loss.csv) · [Logged minibatch data](4b-training-loss.csv)

## Whole-repository 7B pretraining protocol

The source corpus is every UTF-8 text file at DuckDB commit `6978d121bcaf5d56f35be51caef6d7662ef3c1c4`. It has 2,397 files, 1,246,315 lines and 41,792,199 scored tokens including file separators. The snapshot contains 36 additional binary files. Every source epoch evaluates token-weighted cross-entropy over the entire text snapshot. This measures memorization of a known repository.

The initial model is Qwen2.5-Coder-7B-Instruct at `c03e6d358207e414f1eca0bb1891e29f1db0e242`. Continued pretraining uses rank-32 LoRA and distillation on unrelated inputs. Validation permits at most 3% perplexity regression on each of unrelated Python and English. ARC and short generated-answer accuracy may drop by at most 2.5 percentage points, with at least 94% and 90% answer agreement respectively. These probes cover a limited sample of base behavior.

The treatment requires three full epochs without a cumulative 0.01 nat/token improvement over the previous reference, at least 30% lower perplexity than the unadapted model on both the entire tree and first-party source, and passing independent retention probes. Both arms subsequently use the same frozen pooled merge dataset of 103,829 raw conflicts across 460 repositories, excluding DuckDB. The primary downstream comparison uses 1,000 later DuckDB conflicts from 329 merges. Unrelated repository holdouts and post-SFT source perplexity measure transfer and how much of the acquired knowledge survives merge training.


Measured base perplexity is 1.751 for the entire tree and 1.698 for first-party source. The corresponding promotion ceilings are 1.226 and 1.189. Training continues to the plateau even if a checkpoint crosses both thresholds early.

A separate closed-book probe asks which explicitly qualified C++ method a DuckDB method calls across files. It contains 217 caller methods from 129 files at the training snapshot. Each question has three distractors from the callee’s class, and all four answer orders are scored. The adapted model must reach 65% accuracy and improve by five percentage points over base (the relative target caps at 95%). This tests one aspect of repository knowledge. Forward merge accuracy remains the test of whether that knowledge transfers. Rebuild the questions with `repo_calls.py` from the frozen text corpus.
