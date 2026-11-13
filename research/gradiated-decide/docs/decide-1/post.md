# decide-1: a day of post-training on an open decision model, and what it bought

*Gradiated research · November 2026 · draft*

This week Google launched the [Gemini Decisions API](https://blog.google/innovation-and-ai/technology/developers-tools/gemini-decisions-api/).
It joins a small but busy category: Perplexity's pplx-decider, Baseten's mammoth-1, PelaAI's KnowLine and a dozen
others on the Decision Index board. A decision model doesn't write text. You give it a state (a conversation, an
email, a diff) and a set of typed questions: yes/no, pick one of k, or grade on a rubric. It returns a probability for
every option, from one forward pass. That makes it a good fit for the unglamorous jobs inside agents and pipelines,
where you want a number you can threshold rather than a paragraph you have to parse:

- which tool to call;
- whether a message is phishing;
- which queue a ticket goes to;
- whether a PR description matches the diff.

Today we're releasing **decide-1**, the first Gradiated model. It is a 31B dense model, built by fine-tuning
[KnowLine-31B-Gen1.5](https://huggingface.co/PelaAI/KnowLine-31B-Gen1.5) (itself a Gemma 4 fine-tune) on about 520M
tokens of licence-clean public data, then averaging the result back with the original weights. Every benchmark number in
this post comes from public test sets we ran ourselves. On those it is a small, consistent step over its base. Most of this post is
how we got there in about a day of GPU time, what didn't work, and the bugs we hit along the way.

**Headline numbers (public test sets, all measured by us with the same harness for every model):**

| | KnowLine-31B-Gen1.5 (base) | decide-1 |
|---|---|---|
| Decision Index 0.3, public tests | 70.54 | **71.34** |
| JevBench, public split (231 decisions) | 90.91 | **91.34** |
| Mean calibration error (ECE) over the six Gemini launch benchmarks | 0.036 | **0.031** |

## What it looks like

One request carries a state and any number of questions; every question is answered from the same read of the
state.

```bash
curl -s localhost:8080/v1/systemone -d '{
  "state": {"email": {"from": "IT Service Desk <it-support@gradlated.com>", "subject": "Action required: ...", "body": "..."}},
  "questions": {
    "phishing": {"type": "noul", "instructions": "Is this email a phishing attempt?"},
    "tell": {"type": "choice", "instructions": "Which single detail is the strongest evidence?",
             "criteria": {"domain": "...", "urgency": "...", "link": "...", "greeting": "...", "none": "..."}}}}'
```

We ran ten small examples through decide-1 and, for comparison, through KnowLine, its base. Both ran on one H200,
one request at a time. Every probability below is copied from the response; the requests are in
[`examples.json`](examples.json) and the raw answers in [`answers.jsonl`](answers.jsonl).

**An agent picking tools.** The user writes: *"BA 2491 to Edinburgh just got cancelled. Get me on the next flight
tonight if there is one, and text Sam that I'll be late for dinner."* There are five tools, with one yes/no question
each, all answered in a single request:

| Tool | decide-1: P(call it) | KnowLine |
|---|---|---|
| `send_sms` | 0.97 | 0.96 |
| `search_flights` | 0.89 | 0.87 |
| `rebook` | 0.73 | 0.65 |
| `cancel_booking` | 0.00 | 0.01 |
| `get_weather` | 0.00 | 0.00 |

`rebook` is the least certain. That's fair, since you can't rebook until you've found a flight.

**Reading a diff.** The diff is a "no behaviour change" refactor that drops the parentheses from
`(user.is_admin or user.id == doc.owner_id) and not doc.locked`. Is the PR description accurate? decide-1 says *no,
the change alters who can edit locked documents* at 0.99. It also answers the two narrower questions correctly:
- After the change, can an admin edit a locked document? Yes, 0.99.
- Before the change, could they? P(yes) = 0.003, correctly no.

**Monty Hall, and a coin nobody has seen.** One state holds two puzzles:
- *Should you switch?* It says switch, at 0.98.
- *Does the sealed envelope say heads?* The right answer is 0.5. decide-1 says **0.65**, and KnowLine 0.69.

Yes/no questions with no evidence either way lean towards "yes". If you threshold yes/no outputs, that's worth
knowing.

**Business days.** An invoice is issued on Friday 27 November and is due 10 business days later. Today is Friday 11
December. Is it overdue?

| Question | decide-1 | KnowLine |
|---|---|---|
| Due date: 11 Dec (correct) / 10 Dec / 9 Dec / 14 Dec | **0.84** / 0.11 / 0.04 / 0.00 | **0.94** / 0.01 / 0.05 / 0.00 |
| Overdue at the end of today? (correct answer: no) | yes, 0.62 | yes, 0.73 |

Both models work out the due date correctly, then say an invoice due *today* is already overdue. decide-1 is less
sure of that wrong answer than KnowLine. This is exactly the kind of temporal question stage 2 targeted, and it
still isn't fixed.

**Phishing.** The email comes from `it-support@gradlated.com` (note the *l*) and links to `gradiated-sso.help`.
- Phishing? Yes, 0.96.
- Strongest evidence? The link (0.68) ahead of the lookalike domain (0.25).

Both are good answers.

**Routing a German support message.** *"Ich habe meine Karte im Zug liegen lassen und gerade hat jemand 300 Euro am
Automaten abgehoben. Bitte sofort sperren!"* (I left my card on the train and someone just withdrew €300 at a cash
machine. Block it now!) decide-1 splits it between:
- `lost_or_stolen_card`: 0.77;
- `cash_withdrawal_not_recognised`: 0.23.

That's an honest split, because the message is both. KnowLine is more decisive at 0.91. decide-1 also rates "needs a
human within five minutes" at 0.89.

**Grading a bug.** A Safari-only `crypto.randomUUID` crash on the Pay button hits 12% of checkouts, and the question
is a four-level rubric. decide-1 puts 0.71 on *critical* and 0.29 on *major*, an expected score of 2.71 out of 3.

**Taste.** For a cartoon of a golden retriever at a job interview with a cat, it picks *"It says here you're a good
boy. Can anyone confirm that?"* at 0.69. For *"Great, the 9am standup is now also a 9:30 sync. Love that for us."*
it is sure the message is sarcastic (0.95). For the reaction, it narrowly prefers 😔 (0.37) to 💀 (0.31) and 😂
(0.22), which we'd dispute. And it rates the Hacker News comment *"Ah yes, the yearly 'I rewrote X in Y' post"* as
within the guidelines at 0.04.

**Latency.** On one H200, with SGLang and one request at a time:
- one question: 55–60 ms per request;
- two to five questions: 110–120 ms.

Repeating a request doesn't
give bit-identical probabilities, because of batching and kernel nondeterminism.

**What these examples don't show** is a difference between decide-1 and KnowLine. On ten hand-picked prompts the two
models agree on every top answer, and the probabilities move by a few points either way. A 0.8-point gain on the
Decision Index is real, but you won't see it in a demo. That's why most of this post is about benchmarks.

## Benchmarks

### Decision Index 0.3 (public tests)

We ran the full public suite of the [Decision Index](https://github.com/apolinario/decision-index) (0.3 edition) for
every model in this table with the kit's own scorer. KnowLine and decide-1 ran through KnowLine's release serving
stack (SGLang plus its own front end), so the only difference between those two columns is the weights.

| Area | pplx-decider-v1.2 | KnowLine-31B-Gen1.5 | gd-kl1 (stage 1, 50% blend) | **decide-1** |
|---|---|---|---|---|
| Knowledge & reasoning | 56.2 | 59.6 | 60.4 | 60.3 |
| Language | 72.8 | 72.8 | 72.7 | **73.8** |
| Retrieval & routing | 68.4 | 73.2 | 75.2 | **75.8** |
| Tools & agents | 84.3 | **85.4** | 85.3 | 84.5 |
| Arts & taste | 56.0 | 60.7 | 60.3 | 60.8 |
| **Index** | 68.04 | 70.54 | 71.08 | **71.34** |

![Change per benchmark, decide-1 minus KnowLine](panel.svg)

Two caveats on these numbers:

- **Train splits.** Several of the biggest gains (BANKING77 +6.8, ESCI +3.1, New Yorker +3.1, CLINC150 +2.4) are on
  benchmarks whose *train* split is in our data. The test rows are decontaminated (exact match and 13-gram overlap),
  but this is still in-distribution training, so read those gains with that in mind.
- **Losses.** The losses (Home appliance simulator −4.5 on 160 items, NLI4CT −2.2, MuSR −1.9) sit on benchmarks where
  we found no training data we were allowed to use.

**Where this sits.** All of the above is the public test suite. The Decision Index board no longer ranks on it. Since 0.4 its score comes from
private tests, which we can't run. On the public 0.3 suite, several open models report higher numbers than ours:

| Model | DI 0.3 public score (board) |
|---|---|
| mammoth-1 | 75.34 |
| Jeffan-31b | 73.13 |
| StartLux v1.1 | 72.88 |
| GLiDE V1.2 | 71.99 |
| Sieve 31B v3 | 71.68 |

Some of those gaps shrink or reverse on the private score; mammoth-1, for example, scores 68.44 there. We'll submit
decide-1 to the board and report what it gets.

### Google's Gemini Decision 1 launch panel

Google's launch table uses benchmarks we can mostly reproduce. We built the text ones and ran them ourselves. Google
didn't publish prompts, subsets or its harness, so the Gemini and Jev columns are their numbers, not ours, and the
comparison is indicative.

| Benchmark | KnowLine | **decide-1** | mammoth-1 (we ran it) | Gemini Decision 1 (Google's numbers) | Jev 1.14 (Google's numbers) |
|---|---|---|---|---|---|
| JevBench public | 90.91 | 91.34 | **93.94** | 92.2 | 90.0 |
| Amazon ESCI (macro-F1) | 61.02 | 63.50 | **64.52** | 58.7 | 56.7 |
| New Yorker caption contest | 85.04 | **87.50** | 87.12 | 79.7 | 72.0 |
| PubMedQA | **82.10** | 81.20 | 81.50 | 79.8 | 78.2 |
| Global-MMLU-Lite | 84.03 | 84.20 | 84.47 | **86.0** | 85.0 |
| When2Call | 91.13 | 91.21 | **91.65** | 79.9 | 82.0 |
| Mean ECE (lower is better) | 0.036 | **0.031** | 0.038 | 0.025 (7 evals) | 0.049 (7 evals) |

mammoth-1 is better than decide-1 on five of the six benchmarks. decide-1's clearest win is calibration: when it says
90%, it is right closer to 90% of the time. That improvement is uneven, though. ECE fell on ESCI, PubMedQA, New Yorker
and When2Call, and *rose* on JevBench (0.036 → 0.048) and Global-MMLU-Lite. JevBench's accuracy gain over KnowLine is
one question out of 231, which is noise.

## How we trained it

### Data

All training data is public and licence-checked row by row. We dropped any source whose licence forbids commercial
use or is unstated: ANLI, ContractNLI, NLI4CT, RAGTruth, ACOS and others. That choice is why we have nothing to train
on for some of the benchmarks where decide-1 loses ground. From sources that mix authors (sn92, HelpSteer2/3), we
removed rows written by OpenAI, Anthropic or Google models, whose terms restrict training competing models. Every
source was decontaminated against the Decision Index test rows, the kit's full test pools, and the JevBench and Gemini
panel items.

Training ran in two stages:

1. **gd-kl1:** a broad mix of 952k rows:
   - procedural typed decisions;
   - the commercial-licence rows of tasksource's Jev-format decisions;
   - official train splits of 14 Decision Index benchmarks;
   - sn92's generalist and specialist sets.
2. **gd-kl2:** started from gd-kl1 and aimed at what gd-kl1 still got wrong:
   - temporal and numeric reasoning (TempReason, TimeQA, TAT-QA, FinQA);
   - long policies and contracts (ShARC, CUAD, MAUD, LexGLUE);
   - preference judging (HelpSteer2/3, OASST2, Stack Exchange);
   - dialogue state (MultiWOZ);
   - about one sixth replay of stage 1 data.

Neither stage used a full epoch; we stopped on a fixed step budget.

| | Stage 1 (gd-kl1) | Stage 2 (gd-kl2) |
|---|---|---|
| Rows in the mix | 952,252 | 562,689 |
| Steps | 1,155 (0.25 epoch) | 1,000 (0.35 epoch) |
| Tokens trained on (excluding padding) | ~265M | ~255M |
| Examples seen | ~238k | ~198k |
| Learning rate (body / readout) | 3e-6 / 1e-5 | 2e-6 / 1e-5 |
| Hardware | 8× B200 (spot) | 8× B300 (spot) |
| Training time | 8.9 h, 71 GPU-hours | 3.8 h, 30 GPU-hours |

- **Training setup:** full fine-tune, FSDP2, fp32 master weights, bf16 compute, 262k-token batches, cosine schedule.
- **Loss:** soft cross-entropy on the option distribution plus 0.5 × Brier score, which rewards calibration directly.
- **Total:** about **520M tokens and 101 GPU-hours** of training. That excludes evaluation, the pilots that went
  nowhere, and the hours lost to spot preemptions.

### Loss over training

![Training loss over tokens seen, both stages](loss.svg)

The training loss is noisy, because every batch mixes dozens of sources with very different difficulty. The held-out dev
sets are the better signal:

![Held-out dev accuracy and loss at each checkpoint](dev.svg)

- **Stage 1:** dev accuracy went 85.9% → 88.9% → 90.2% → 90.5% at steps 0, 400, 800 and 1,155.
- **Stage 2:** on its own dev set, dev accuracy went 82.2% → 83.9% → 84.5% → 84.5% → 84.9% at steps 0, 250, 500, 750
  and 1,000.

Stage 2's dev set is harder and different, so the two curves don't line up. At stage 2's first check (step 250), the
model got worse on sources it had already learned: GSM8K −3.3, CUAD −3.2, LEDGAR −1.9. By step 500 it had recovered
all of them except LEDGAR.

### The blend is doing a lot of the work

The fine-tuned model alone is *worse* than the base on the Decision Index. What makes it a gain is linear
interpolation: we average its weights 50/50 with KnowLine's.

![Decision Index dev-sample score against the share of fine-tuned weights](blend.svg)

| Share of fine-tuned weights | 100% | 70% | 50% |
|---|---|---|---|
| Stage 1 | 69.87 | 69.97 | 70.59 |
| Stage 2 | 68.60 | 69.77 | 70.49 |

KnowLine alone scores 69.83 on this dev sample.

The fine-tune drifts on benchmarks it has no data for, and the interpolation pulls those back while keeping most of
the gains where it did have data. We saw the same pattern on our earlier Qwen-based runs, where the 50% blend beat the
fine-tune alone by 0.7 points.

## Making training 2.3× faster

Stage 1 ran at 9.3k tokens/s on 8 B200s. Before stage 2 we profiled it and found 57% of GPU time inside FSDP's
reduce-scatter. NCCL wasn't slow: a 2 GiB fp32 reduce-scatter took 2.9 ms. The time was ranks *waiting*. Each rank
shuffled its own batches, so on any step one rank drew the long legal contracts and the other seven sat at the
collective until it finished.

Two changes fixed most of it:

1. **Global length-balanced batches.** Every rank loads the whole plan. Each step takes one window of length-sorted
   examples and cuts it into eight micro-batches of near-equal token count, so ranks finish together.
2. **Flex attention for Gemma 4's sliding-window layers.** We used `torch.nn.attention.flex_attention` with a
   causal-window block mask, and plain causal SDPA for the global layers, instead of a dense masked attention for
   everything.
   - We checked it against the masked reference: 1e-3 relative error on sliding layers, 1e-5 on global layers.

Together those took throughput to 20.3k tokens/s. Keeping the activations of 8 of the 60 layers, instead of
recomputing them, added another 5% (21.4k tokens/s at 218 GiB per GPU; 16 layers ran out of memory). That's 2.3×
overall.

**Checkpointing.** Spot instances get preempted, so we save the full training state every 20 minutes: 335 GB of
sharded weights and optimizer. The first version paused training for **13.5 minutes** per save. Making the save
asynchronous didn't help, because it was the write itself that was slow. One writer thread per rank managed about
55 MB/s, even into RAM. With 16 writer threads, saving to `/dev/shm` and uploading to S3 in the background, the pause
is 53 seconds.

We learned that one the hard way. A preemption hit during an unfinished 13-minute write and cost us 150 steps.

## What didn't work

- **A learned gate between two models.** Before KnowLine-based training, our best result was a 50/50 ensemble of
  KnowLine and our Qwen-based fine-tune. We trained a small gate on 66k held-out questions to choose the mix per
  question. In leave-sources-out cross-validation it nearly matched the fixed 50/50 average, but on the Decision Index
  it scored 1.2 points *below* it. Which model is right on a given question turned out not to be predictable from
  features of the answers.
- **A KL anchor to the base.** Adding a KL penalty towards the base kept the fine-tune closer to it, as intended, but
  the best blend ended up 0.26 points worse than without the anchor. Interpolating after training did the same job
  better.
- **Stage 2 alone.** Unblended, stage 2 is 1.2 points below the base on the dev sample. Targeted data moved the targeted
  benchmarks, and moved some others the wrong way.

## Limitations

- **Single seed, no error bars.** Differences of a few tenths of a point on the index are within the noise of our
  blending choices. One question on JevBench is 0.43 points.
- **Public suite only.** We have no score on the board's private Decision Index tasks.
- **Calibration is uneven.** It got worse on JevBench and Global-MMLU-Lite. If you threshold on probabilities, check
  calibration on your own data.
- **Size.** 31B dense, about 63 GB in bf16. We ran the examples above on one H200 (141 GB).
- **Languages.** Mostly English. KnowLine also covers Chinese; we didn't train or test on it.

## Getting it

decide-1 will be at **huggingface.co/gradiated/decide-1**:

- **Licence:** Apache-2.0, like its base.
- **Serving:** the same front end and SGLang setup as KnowLine-31B-Gen1.5, so existing KnowLine and Jev-format
  clients only change the model path.
- **Code:** training, data and evaluation code are in our repository.

<!-- TODO before publishing: confirm hosting, model card, CC-BY-SA question, board submission. -->
