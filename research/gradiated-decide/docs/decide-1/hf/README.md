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

decide-1 is a fine-tune of [Gemma 4 31B](https://huggingface.co/google/gemma-4-31B-it). Our initial checkpoint was
[KnowLine-31B-Gen1.5](https://huggingface.co/PelaAI/KnowLine-31B-Gen1.5), PelaAI's decision fine-tune of Gemma 4 31B.
From it we trained on about 520M tokens of licence-checked public data in two stages: broad typed decisions first, then
temporal and numeric reasoning, long policies and contracts, preference judging and dialogue state (see
[Training](#training)). The released weights average the result 50/50 with the initial checkpoint. decide-1 uses
KnowLine's serving stack unchanged: the same SGLang engine, front end (`knowline_server.py`), prompt layout and
temperatures, so existing KnowLine clients only change the model path.

## Results

Every number is from public test sets, measured by us with the same harness and serving stack for every model.

| | KnowLine-31B-Gen1.5 (initial checkpoint) | decide-1 |
|---|---|---|
| Decision Index 0.3, public tests | 70.54 | **71.34** |
| JevBench, public split (231 decisions) | 90.91 | **91.34** |
| Mean calibration error (ECE) over six Gemini Decision 1 launch benchmarks | 0.036 | **0.031** |

Decision Index 0.3 by area:

| Area | KnowLine-31B-Gen1.5 | decide-1 |
|---|---|---|
| Knowledge & reasoning | 59.6 | 60.3 |
| Language | 72.8 | 73.8 |
| Retrieval & routing | 73.2 | 75.8 |
| Tools & agents | 85.4 | 84.5 |
| Arts & taste | 60.7 | 60.8 |

Several of the largest gains (BANKING77, ESCI, New Yorker, CLINC150) are on benchmarks whose train split is in our
data. Their test rows were decontaminated (exact match and word 13-gram overlap), but these are in-distribution gains.
We have no score on the Decision Index board's private tasks.

## Serving

```bash
pip install "sglang[all]==0.5.21" "transformers==5.12.1" requests
hf download gradiated/decide-1 --local-dir decide-1
bash decide-1/serve_knowline.sh decide-1 0 8080     # GPU 0, front end on port 8080
```

```bash
curl -s localhost:8080/v1/systemone -d '{
  "state": {"email": {"from": "IT Service Desk <it-support@gradlated.com>", "subject": "Action required", "body": "..."}},
  "questions": {"phishing": {"type": "noul", "instructions": "Is this email a phishing attempt?"}}}'
```

[INFERENCE.md](INFERENCE.md) is KnowLine's serving guide; all of it applies to decide-1. The weights are bf16, about
63 GB, and fit one 80 GB or larger GPU. Gradiated's hosted API serves decide-1 as `gradiated/decide-1`.

## Training

- **Initial checkpoint:** KnowLine-31B-Gen1.5 (PelaAI, Apache-2.0), itself fine-tuned from Gemma 4 31B. Both stages
  start from it (stage 2 from stage 1's result), and the final blend averages back towards it.
- **Stage 1:** 952k rows, 1,155 steps (0.25 epoch): procedural typed decisions, the commercial-licence rows of
  tasksource's Jev-format decisions, the official train splits of 14 Decision Index benchmarks and sn92's sets.
- **Stage 2:** 563k rows, 1,000 steps (0.35 epoch) from stage 1, aimed at its errors: temporal and numeric reasoning
  (TempReason, TimeQA, TAT-QA, FinQA), long policies and contracts (ShARC, CUAD, MAUD, LexGLUE), preference judging
  (HelpSteer2/3, OASST2, Stack Exchange), dialogue state (MultiWOZ), plus about a sixth replay of stage 1.
- **Setup:** full fine-tune, bf16 compute with fp32 master weights, soft cross-entropy on the option distribution plus
  0.5 × Brier score. About 101 GPU-hours on B200 and B300.
- **Blend:** the released weights are 0.5 × KnowLine-31B-Gen1.5 + 0.5 × the stage 2 checkpoint. The blend scores 0.7
  points above the initial checkpoint on our dev sample (70.49 vs 69.83); the stage 2 checkpoint alone scores 1.2 points
  below it.

### Data and licences

All training data is public and was licence-checked per source. We excluded sources whose licence forbids commercial
use or is unstated, and removed rows written by OpenAI, Anthropic or Google models from mixed-author sources. Every
source was decontaminated against the Decision Index 0.3 test rows, the kit's test pools, and the JevBench and Gemini
launch panel items.

Sources: procedural typed decisions; sn92 (generalist and specialists); tasksource Jev-format decisions (commercial
rows only); the train splits of API-Bank, BANKING77, CLINC150, SGD, ARC, WinoGrande, HellaSwag, GSM8K, ChessBench,
Amazon ESCI, HoVer, When2Call and the New Yorker caption contest; TAT-QA, FinQA, ConvFinQA, DROP, TimeQA, TempReason,
ShARC, CUAD, MAUD, LexGLUE, CondaQA, HelpSteer2, HelpSteer3, OASST2, Stack Exchange preferences, MASSIVE, sarcasm
headlines, IBM claim stance and MultiWOZ 2.2.

Their licences are permissive (Apache-2.0, MIT, BSD, CC-BY) or share-alike (CC-BY-SA, for example DROP, Stack Exchange
preferences, TempReason and ShARC). We release the weights under Apache-2.0, the licence of the base model, and credit
every source here.

## Limitations

- **Single seed, no error bars.** Differences of a few tenths of a point are within the noise of our blending choices.
- **Calibration is uneven.** ECE fell on ESCI, PubMedQA, New Yorker and When2Call and rose on JevBench and
  Global-MMLU-Lite. Check calibration on your own data before thresholding.
- **Yes/no lean.** With no evidence either way, `noul` answers lean towards yes.
- **Languages.** Mostly English. KnowLine also covers Chinese; we did not train or test on it.

## Licence

Apache-2.0. decide-1 contains code and weights from KnowLine-31B-Gen1.5 (Apache-2.0, PelaAI), which derives from Gemma
4 (Apache-2.0, Google). `MODIFICATIONS` describes what we changed.
