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

## Generic merge-training comparison

Qwen2.5-Coder-7B-Instruct completed 3,419 steps on 29,090 examples from the same frozen training snapshot as the Qwen3.5-4B run. On the 611-conflict repository holdout, the 7B model exactly resolved 404 conflicts (66.1%) and the 4B model resolved 416 (68.1%). They disagreed on 96 conflicts, with 42 correct only for 7B and 54 correct only for 4B. The 7B minus 4B difference was −1.96 percentage points, with a paired 95% bootstrap interval from −5.42 to +1.40 points over 206 merge commits. This interval describes uncertainty within the evaluated repositories. The models differ in family and tokenizer as well as parameter count. This experiment is independent of the pooled DuckDB adaptation comparison.

[Four holdout comparisons with paired intervals](4b-7b-merge-comparison.csv)

Epoch 1 completed 851 optimizer updates. At full adapter strength validation instruction accuracy improved by 8.33 percentage points, but only 40 of 48 generated answers exactly matched the base outputs. No tested nonzero strength passed all retention checks. The reported epoch-1 whole-snapshot measurement therefore uses the base model (adapter scale zero). The training adapter and optimizer were checkpointed separately. This measurement leaves the unrestricted adapter’s full-corpus perplexity unknown.

[Perplexity of the retention-selected model by epoch](7b-source-loss.png) · [Token counts, cross-entropy, perplexity and adapter strength](7b-source-loss.csv)

Two of the three original spot workers stopped during epoch two. The last logged progress before interruption was step 1,100. The complete step-851 adapter and optimizer are preserved under `whole/diagnostics/epoch-1/` in the experiment bucket. A separate evaluation on the surviving H200 scores that adapter at full strength on every snapshot token.

The recovery experiment forks the epoch-one weights with fresh AdamW moments and adds a KL term (weight 3) on greedy base-model continuations for training-only instruction prompts. The original source objective and generic replay KL (weight 1.5) remain in the loss. Each full pass records source loss at both full and retention-selected adapter strength. The recovery experiment uses the original promotion criteria and an isolated `instruction-distill/` output prefix. Its optimizer trajectory starts a distinct experimental arm.

On one EU North node with eight H200s, the source-training benchmark processed 786,432 repository tokens in 14.944 seconds (52,626 tokens/s). It used a global batch of 48 sequences, three warm-up steps and 16 timed optimizer steps. This measures the original source-training loop. The instruction-distillation arm adds a teacher forward pass and a student forward/backward pass on generated instruction continuations, and each epoch also requires full-corpus evaluation.

The full-strength step-851 adapter scored 0.43499 nats/token over all 41,792,199 snapshot tokens and 0.43653 on first-party source. Perplexity fell by 11.77% across the whole repository and 8.87% on first-party source. This checkpoint missed both 30% reduction thresholds and the instruction-agreement threshold.

[Full-strength source curve](7b-raw-source.png) · [Measured losses and adapter digest](7b-epoch1-full-strength.json)

The revised training loop sustained approximately 29,500 source tokens per second on eight H200s between checkpoint uploads at steps 900 and 1,600 (34.41 million tokens in 1,165 seconds). That rate includes periodic checkpoint overhead. The spot VM stopped before the epoch-two evaluation. The step-1,600 adapter and optimizer checkpoint were present in S3, 102 optimizer updates before the epoch boundary.

### Epoch-one merge experiment

The exploratory branch starts from the full-strength step-851 adapter recorded above. Its first comparison repeats the previous 7B merge run on dataset 1795477893, with 29,090 eligible examples, seed 0 and 3,419 optimizer updates. The primary historical benchmark is exact resolution on the same 611 conflicts, where that model scored 404. The second comparison starts again from step 851 and uses the larger DuckDB-excluded pool from dataset 1795500749. Its control starts from the original 7B model and uses the same pool. The primary endpoint there is exact resolution on 1,000 forward DuckDB conflicts. Paired differences use merge-cluster bootstrap intervals on DuckDB and repository-cluster intervals on the unrelated holdout. Predictions and checkpoints for both experiments have their own prefixes under `epoch1-merge/`. The ongoing retention-constrained trial keeps its original eligibility criteria.

### Epoch two on the instruction-distillation branch

The full-strength step-1,702 adapter passed the development retention checks at scale 1.0. Whole-snapshot perplexity reached 1.51283 (0.41399 nats/token), down 13.61% from the base model. First-party source reached 1.51572 (0.41589 nats/token), down 10.74%. Both remain above their target perplexities. Independent retention and the closed-book calls probe remain pending. The curve follows the full-strength epoch-one adapter into the revised epoch-two recipe.

[Measured perplexity curve](7b-full-strength-through-epoch2.png) · [Token counts and cross-entropies](7b-full-strength-through-epoch2.csv)
