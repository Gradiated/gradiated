# Research Log

## 2026-07-26T01:47:00Z — Exact offline retrieval admission

**Question.** Can request-adaptive retrieval recover the exact tied-head top-1
on the hash-bound 384-row hidden capture with a candidate set and physical
traffic bound credible enough to justify an H200 consumer?

**Action.** Implemented `adaptive_retrieval_vocab_offline.py` and ran it locally
on CPU against the exact hidden capture
`80625b878e7479cd626250396f4be1a319e781245335600cd285037ce00fc66d`,
the exact tied BF16 shard
`eeef8791537bc04f110967c513149e037d2a9ae97d49add7291ebfa62806bbfa`,
and the static-head terminal
`12cdd51e1a1081f95deee4325a558c45e6dfac52abbff5b75ee0c522d385d0ee`.
The first launcher attempt used an incorrect relative checkpoint path and
failed before reading inputs; the path-only defect was amended and the
canonical invocation was run once. No GPU, SSH, provider mutation, or paid
request was used.

**Evidence.**

- Measured: the full tied head returns token `240017` with a `5.08879` FP32
  top-1 margin. Repeating that ID for 384 rows reproduces the prior H200
  control digest `e1ebaa70d782fcec41a707c186f8eac634b07bfb127ac2631d1f8f5b0cfab6aa`.
- Measured: all 384 serialized hidden rows are identical, and every captured
  proposal ID is zero. The effective hidden-state sample size is one, so all
  request/depth strata are repeated observations of the same retrieval.
- Measured: rowwise W8A8 ranks the reference first at one candidate. The
  variance-selected BF16 coordinate families need 32, 512, 2,048, 4,096,
  8,192, and 32,768 tested candidates at widths 4,096, 2,048, 1,024, 512,
  256, and 128 respectively. W4A8 needs 8,192 candidates but is not a native
  H200 tensor-core path.
- Analytical, using vendor inventory peaks with deliberately discounted
  bandwidth/math rates: the best native materialized-score geometry is the
  256-coordinate index with 8,192 candidates (3.125% of vocabulary),
  134,218,240 index bytes, and a 1.023 ms additive H200 bound. Its fused
  lower-bound traffic is 222,331,392 bytes (7.89% of the dense BF16 weight);
  score materialization raises traffic to 1,027,637,760 bytes (36.46%).
  This is physically favorable against the measured 24.808 ms stock component,
  but actual kernel, gather, and graph costs remain unmeasured.

The complete recall curves, per-request/per-depth arrays, geometry, arithmetic,
and bounds are in
`ADAPTIVE_RETRIEVAL_VOCAB_OFFLINE_TERMINAL.json`
(`29644d701a38606f6a8f9230da753b2ecdccd969093ca80af75dfd9d6c3e54dd`).

**Interpretation.** The mechanism is physically credible on the single bound
state, but this capture cannot support a workload-level retrieval claim or a
GPU-spend decision. The apparent 384/384 recall is not 384 independent
decisions.

**Next move.** Close this admission without an H200 claim. A successor may
capture genuinely distinct verifier hidden states, bind their hashes, and run
the same W8A8/coordinate retrieval consumer before any GPU measurement.

## 2026-07-26T06:34:27Z — Exact diverse hidden-state capture hook

**Question.** Can the pinned NGRAM `TARGET_VERIFY` producer expose live,
request-owned hidden rows immediately before the tied LM head without changing
the logits or greedy acceptance consumed by verification?

**Action.** Implemented `diverse_hidden_capture_hook.py` at the
`Gemma4TextModel.forward` → `Gemma4ForCausalLM.forward` →
`LogitsProcessor.forward` boundary. The hook validates the pinned Gemma and
logits-processor source hashes, records request ID, request-pool slot, capture
row, request-major depth, proposal, position, and an owned CPU clone of each
hidden row, while passing the original hidden tensor into the original
consumer. The bootstrap is fail-open and audits observer faults. The later
one-shot command explicitly disables CUDA graphs: a Python observer installed
during graph construction otherwise sees synthetic graph-capture rows rather
than live replay rows, which is the causal defect behind the prior degenerate
capture.

Ran the synthetic producer-to-consumer fixture once, then amended the fixture
to directly exercise observer-failure isolation and re-executed only that
local contract. This was fixture validation, not a retrieval replay or an
independent model sample. No GPU was claimed, no SSH or provider action was
used, and no endpoint request was issued.

**Evidence.**

- Measured: three distinct request identities at four request-major depths
  produced 12 rows and 12 unique hidden states.
- Measured: hook-off and hook-on logits are bitwise equal; greedy acceptance
  is bitwise equal with eight accepted and four rejected rows.
- Measured: the downstream consumer received the original hidden tensor
  storage, the serialized hidden/proposal rows reproduced the same logits and
  acceptance, non-target rows were ignored, ownership matched all 12 expected
  request/depth/row tuples, and an intentionally failing observer did not
  change or skip the original consumer.
- Bound source hashes: Gemma
  `bc8bc948a89e82b2118c32d380497ce76a568b8839c7f02150195af93a0e8989`,
  logits processor
  `e5d0d3a8781e74c1c7fe7508eb89d2eb198cc42bcd5e2fa4258217c756fdaf14`,
  and forward-batch ownership
  `c977296f3b90be69fff5312f2b3af7699a17b20af24614b139f69888e5776516`.

The complete ownership schema, fixture hashes, non-interference checks, source
hashes, graph-policy rationale, and exact later server command are in
`DIVERSE_HIDDEN_CAPTURE_HOOK_TERMINAL.json`
(`dbaa9ef8705091f05de4b5843663c65e437b397591cf5940be2c43a6b99cb303`).

**Interpretation.** The missing capture mechanism is now source-complete and
execution-tested. This does not validate retrieval or model quality; it makes
a later diverse exact c32 capture interpretable.

**Next move.** Close this zero-GPU iteration. A later director admission must
materialize the pinned endpoint and workload runner under this project before
claiming a bench, execute the terminal's eager capture command, and require a
real diversity gate before reusing the offline retrieval consumer.

## 2026-07-26T22:40:15Z — Exact diverse c32 capture packet

**Question.** Can the already-proven capture hook be admitted later without
resolving mutable sibling-project sources or opening a claim clock during
offline preparation?

**Action.** Consumed `DIVERSE_HIDDEN_CAPTURE_HOOK_TERMINAL.json` and copied only
the pinned endpoint entrypoint, exact c32 request producer, capture hook, and
bootstrap into content-addressed packet
`e606f47a04c0374692e5aa66ae30821b35f8a79196916582cacc904ed568bc54`.
Added a direct-hash manifest and built a deterministic five-member archive.
The terminal's coordinator-local `PYTHONPATH` and missing required FP8 audit
destinations were ordinary launcher defects; the packet contract binds
container-local `/work/input` and `/work/output` paths instead.

**Evidence.**

- Measured locally: regenerating the producer yields all 32 recorded request
  hashes, request-list digest
  `474ade195799249af8bdcc3e800bd532945ccc90da4d1e3127d8ac6bf2b36a23`,
  prompt-token digest
  `dad77c4038826ec058d2cc70935a6534b5c69d224f01eaa684d5b496fe16f1fc`,
  and canonical `WORKLOAD.json` digest
  `7f66b10e04467f174b9d94782ee906670c0efdb365f6756aeac15f0419f20935`.
- Measured locally: manifest
  `dbb8bec0010e268ea0ffa283fdd6b5b0ccd23f4e79492b98ea77dd6757ad4fd2`
  reproduces archive
  `92f9cfd862da2a275082884c4c0b8fe6a0a14b8dfd4f0844aa29662e144c0144`;
  all member sizes and hashes match.
- No checkpoint was materialized. No GPU was claimed, no SSH or provider
  contact occurred, no endpoint request was issued, and no retrieval ran.

**Interpretation.** The later capture now has a self-contained immutable input
packet, explicit workload identity, bounded owner destination, predeclared
capture schema/diversity gate, and same-claim repair/release contract. This is
offline admission evidence only; the exact c32 producer remains unconsumed.

**Next move.** Pause for director admission. A future turn needs positive spend
authority and a compatible released H200, then must stage this packet and the
separately verified checkpoint inside one durable claim owner and execute the
single eager capture without running retrieval.

## 2026-07-27T00:24:21Z — Producer completed; compact-path repair retained

**Action/Evidence.** The retained owner’s repair diagnostic named compact
terminal retrieval, but direct same-claim retrieval proved a completed,
interpretable producer: `c32/TERMINAL.json` has `pass: true` and 32 complete
requests, `science_started.json` is present, all 32 raw SSE responses are
durable, and the healthy server remains running. Retrieved compact evidence
is `compact-evidence-repaired.tar` SHA-256
`2aaf188879cdd510aa5b449b5ab9b92a9df3169fddc99484afd7e26b994d5759`.
After compact evidence, the immutable 16,600,643-byte hidden payload was
retrieved once; its SHA-256 is
`ce7095836aea47701fc34ebacb2f0754c9066066062500a05fbd6136c59b4d54`.

**Interpretation.** The c32 producer is consumed and must not be replayed.
The repair is confined to artifact terminal adoption/validation. The live
owner’s current retry entrypoint exits after observing a repair request rather
than dispatching that scope, so no request was sent: doing so would stop its
heartbeat and create the prohibited ownerless claim. The controller remains
live and the claim retained pending an executable same-claim repair dispatch.
