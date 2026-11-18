---
license: apache-2.0
base_model:
  - google/gemma-4-31B-it
base_model_relation: finetune
library_name: transformers
pipeline_tag: text-classification
language:
  - en
tags:
  - decision-model
  - system-one
  - decision-index
  - calibration
---

# decide-1

**decide-1 is Gradiated's first decision model: a 31B dense model that answers typed questions about a state with a
calibrated probability for every option, from one forward pass.**

You send a state (a conversation, an email, a diff, a ticket) and any number of questions: yes/no (`noul`), pick one
of k (`choice`) or grade on a rubric (`score`). decide-1 returns a probability for each option. It does not generate
text.

decide-1 is a fine-tune of [Gemma 4 31B](https://huggingface.co/google/gemma-4-31B-it). We started from
[KnowLine-31B-Gen1.5](https://huggingface.co/PelaAI/KnowLine-31B-Gen1.5), PelaAI's decision fine-tune of Gemma 4 31B,
and trained it further on about 520M tokens of licence-checked public data (see [Training](#training)).

## Results

decide-1 against TypeSafe Jev 1.14 and GPT-6 Luna on the six text benchmarks of Google's Gemini Decision 1 launch
table. Accuracy (%) unless noted; higher is better except calibration error.

| Benchmark | **decide-1** | TypeSafe Jev 1.14 | GPT-6 Luna |
|---|---|---|---|
| JevBench (public split, 231) | **91.3** | 88.3 | 89.6 |
| Amazon ESCI (5,000, macro-F1) | **63.5** | 56.9 | 53.7 |
| New Yorker caption contest (528) | **87.5** | 72.0 | 69.5 |
| PubMedQA (1,000) | **81.2** | 79.4 | 71.9 |
| Global-MMLU-Lite, non-English (8,800) | 84.2 | **84.7** | 80.4 |
| When2Call (3,652) | **91.2** | 81.9 | 69.1 |
| Top-1 calibration error (ECE), mean of the six, lower is better | **0.031** | 0.067 | 0.093 |

We ran all three models ourselves in November 2026, on the same items with the same scorer: Jev 1.14 through
TypeSafe's API (`jev-1.14.0`) and GPT-6 Luna through OpenAI's Decisions API. A question a model refuses or cannot
answer counts as wrong. Each question is asked in each provider's native format (yes/no, choice or score); prompts,
options and states are identical.

On the public Decision Index 0.3 suite, decide-1 scores **71.34** (self-run), against 60.70 for Jev 1.14 on the board
and 70.54 for KnowLine-31B-Gen1.5, our initial checkpoint (self-run). We have no score on the board's private tasks.

## Using decide-1

decide-1 is available on the [Gradiated API](https://gradiated.com/docs) as `gradiated/decide-1`:

```bash
curl https://api.gradiated.com/v1/systemone \
  -H "Authorization: Bearer $GRADIATED_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gradiated/decide-1",
    "state": {"ticket": "I was charged twice. Please fix this today."},
    "questions": {
      "category": {"type": "choice", "instructions": "Choose the department for this ticket.",
                   "criteria": {"billing": "Charges or payments", "technical": "Something is broken",
                                "other": "Anything else"}}}}'
```

The weights in this repository are bf16, about 63 GB.

## Training

- **Initial checkpoint:** KnowLine-31B-Gen1.5 (PelaAI, Apache-2.0), a decision fine-tune of Gemma 4 31B.
- **Stage 1:** 952k rows, 1,155 steps (0.25 epoch): procedural typed decisions, the commercial-licence rows of
  tasksource's Jev-format decisions, the official train splits of 14 Decision Index benchmarks and sn92's sets.
- **Stage 2:** 563k rows, 1,000 steps (0.35 epoch) from stage 1, aimed at its errors: temporal and numeric reasoning
  (TempReason, TimeQA, TAT-QA, FinQA), long policies and contracts (ShARC, CUAD, MAUD, LexGLUE), preference judging
  (HelpSteer2/3, OASST2, Stack Exchange), dialogue state (MultiWOZ), plus about a sixth replay of stage 1.
- **Setup:** full fine-tune, bf16 compute with fp32 master weights, soft cross-entropy on the option distribution plus
  0.5 × Brier score. About 101 GPU-hours on B200 and B300.
- **Blend:** the released weights are 0.5 × the initial checkpoint + 0.5 × the stage 2 checkpoint. On our dev sample
  the blend scores 0.7 points above the initial checkpoint; the stage 2 checkpoint alone scores 1.2 points below it.

### Data and licences

All training data is public and was licence-checked per source. We excluded sources whose licence forbids commercial
use or is unstated, and removed rows written by OpenAI, Anthropic or Google models from mixed-author sources. Every
source was decontaminated (exact match and word 13-gram overlap) against the Decision Index 0.3 test rows, the kit's
test pools, and the JevBench and Gemini launch panel items.

Sources: procedural typed decisions; sn92 (generalist and specialists); tasksource Jev-format decisions (commercial
rows only); the train splits of API-Bank, BANKING77, CLINC150, SGD, ARC, WinoGrande, HellaSwag, GSM8K, ChessBench,
Amazon ESCI, HoVer, When2Call and the New Yorker caption contest; TAT-QA, FinQA, ConvFinQA, DROP, TimeQA, TempReason,
ShARC, CUAD, MAUD, LexGLUE, CondaQA, HelpSteer2, HelpSteer3, OASST2, Stack Exchange preferences, MASSIVE, sarcasm
headlines, IBM claim stance and MultiWOZ 2.2.

Their licences are permissive (Apache-2.0, MIT, BSD, CC-BY) or share-alike (CC-BY-SA, for example DROP, Stack Exchange
preferences, TempReason and ShARC). We release the weights under Apache-2.0, the licence of the base model, and credit
every source here.

Amazon ESCI, When2Call and New Yorker are among the benchmarks whose train splits we used; their test rows were
decontaminated, but these are in-distribution results.

## Limitations

- **Calibration is uneven.** Against the initial checkpoint, ECE fell on four of the six benchmarks above and rose on
  JevBench and Global-MMLU-Lite. Check calibration on your own data before thresholding.
- **Yes/no lean.** With no evidence either way, `noul` answers lean towards yes.
- **Languages.** Trained and evaluated mostly in English.

## Licence

Apache-2.0. decide-1 contains weights from KnowLine-31B-Gen1.5 (Apache-2.0, PelaAI), which derives from Gemma 4
(Apache-2.0, Google). `MODIFICATIONS` describes what we changed.
