# Frozen paired-quality interface

Validate the suite before sending requests:

```sh
python3 quality/validate_quality.py
```

Capture stock and candidate sequentially when both models cannot coexist. Start the exact frozen configuration, run capture, stop it, then start the paired configuration and run capture again:

```sh
python3 quality/run_pair.py \
  --mode capture \
  --suite quality \
  --split development \
  --base-url http://127.0.0.1:30000 \
  --responses /evidence/control-responses.jsonl \
  --evidence /evidence/control-quality-evidence.json

python3 quality/run_pair.py \
  --mode capture \
  --suite quality \
  --split development \
  --base-url http://127.0.0.1:30000 \
  --responses /evidence/candidate-responses.jsonl \
  --evidence /evidence/candidate-quality-evidence.json

python3 quality/run_pair.py \
  --mode score \
  --suite quality \
  --split development \
  --control-responses /evidence/control-responses.jsonl \
  --candidate-responses /evidence/candidate-responses.jsonl \
  --result-output /evidence/paired-quality-result.json
```

If two endpoints are already available, one command captures and scores both:

```sh
python3 quality/run_pair.py \
  --mode pair \
  --suite quality \
  --split development \
  --control-url http://127.0.0.1:30000 \
  --candidate-url http://127.0.0.1:30001 \
  --output-dir /evidence/paired-quality
```

Run the development split during falsification. The disjoint holdout remains sealed until the campaign gate permits it; substitute `--split holdout` only then.

The runner executes exact JSON tool formatting, sandboxed coding tests, synthetic long-context retrieval, multi-turn continuation, and two-repeat deterministic serving checks through `/v1/chat/completions`. It executes the loss sentinel through SGLang `/generate` with `return_logprob`, `logprob_start_len=0`, and the frozen input text. The scorer recomputes NLL from raw input-token logprobs. Model-emitted compliance flags and any `teacher_forced_nll` supplied by a response file are ignored and cannot pass the sentinel.

Capture writes one response per frozen case plus an evidence file binding the suite hash, response-file hash, request count, raw response hashes, deterministic identity, and scored-token count. Missing cases, malformed tool output, truncation, nondeterminism, absent input-token logprobs, caller-supplied NLL, or a policy/hash mismatch fails closed.
