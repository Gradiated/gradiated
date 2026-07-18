# Research log

Question: can the bounded request-aware code-only adapter recover the failed paired Python case without changing unrelated response bytes?

Action: implemented `adapter.py` and ran `run_adapter_experiment.py --benchmark-responses 100000` against the immutable BF16/FP8 captures, bound strict AST policy, Gemma suite runner, reference sentinel, and adversarial fixtures. The runner hashes every bound input, emits original/adapted response audits, validates the exact Gemma suite, and writes an atomic terminal.

Evidence: the only explicitly code-only request (`python`) has exactly one outer `python` fence, but its body calls `sorted(xs)`. The bound strict scorer permits only calls to defined functions plus `min`, `max`, `len`, `range`, `list`, and `tuple`; parity between the adapter policy and the bound scorer passed, and both reject this body as `unsafe_python`. Consequently neither arm transforms and the exact executable/NLL scorer remains false only on `python` (six other cases pass; control/candidate NLL remain `0.6548974996976843`, delta `0.0`). Every non-target output hash is identical, reference evidence remains true, and all ten independent positive/negative fixtures pass. The 100,000-response 50/50 CPU run measured p99 `0.083706 ms`, or `0.0230402609%` of `0.3633031778124973 s/request`, comfortably inside the overhead limits.

Interpretation: this adapter is closed. Extracting the fence safely cannot repair this capture under the bound policy; allowing `sorted` would relax the required safety contract. Raw SGLang and the adapter-enabled endpoint remain non-production-eligible, and the c64 concurrency route must stay paused.
