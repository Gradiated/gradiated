# Research supervisor log

Fresh campaign initialized on 2026-07-16. Intervene only when traces show a material research-throughput bottleneck.

## 2026-07-17 — paid-launch contract fidelity

**Bottleneck.** The lab's limiting factor is not portfolio breadth or agent cadence; it is failure to carry the admitted baseline contract into the paid endpoint runner. The campaign still has zero exact-model scientific endpoint outcomes, and the active corrected owner cannot produce the required baseline from its rendered script.

**Evidence.** The first H100 attempt spent 125.189 provider-active seconds (39.422 seconds to create, 37.611 more to SSH) before the user-owned process failed on `/workspace`; cleanup took 47.489 seconds and verified zero resources. The corrected owner reached SSH after 84.267 seconds and was still locally active at 2026-07-16T22:39:03Z, but had emitted no setup phases, useful-GPU timing, server result, request result, or GPU telemetry. Static trace of `gemma_h100_owner.py` shows that its corrected workspace is `/home/glmrunner/gemma-workspace` while the request runner opens `/workspace/gemma-frontier/stock-request.json`; the container mounts only the former path. The loop labeled concurrency 1/8/16 performs synchronous requests one at a time, and the script omits the required 10K single-stream arm, prompt/decode and queueing measurements, and retained MTP/async arm. The researcher trace shows only `py_compile` before provider create even though the named shared `vllm_methodology_runner.py` already implements simultaneous load. Therefore this lineage can yield operational evidence or a canary, but its current script cannot establish the campaign baseline. The active owner was neither changed nor stopped.

**Change.** Added one focused rule to `.agents/skills/researcher/SKILL.md`: before a paid endpoint create, compare the rendered remote runner to the admitted arms, paths, served/request model identity, real concurrency, telemetry retrieval, and retained follow-ups; prefer a named shared runner and do not treat syntax compilation as the audit.

**Expected effect.** A seconds-scale pre-create contract check should prevent full checkpoint staging and paid exposure for path-invalid or scientifically incomplete runners, while preserving the instruction to launch immediately after one focused check. Judge the change by whether the next paid endpoint create reaches complete requests with the declared workload geometry and usable telemetry, not by extra readiness artifacts.

## 2026-07-17 — expose repeated pre-science allocation failures

**Bottleneck.** The prior contract rule improved the L40S workload geometry but did not prevent project-local lifecycle defects or a false-positive rendered audit. The lab has spent its completed paid attempts on setup and transport without one complete exact-model request, while the required daily efficiency report incorrectly hides those outcomes.

**Evidence.** Since the prior review, the L40S lane completed three operational attempts before the current shared-transport owner: pool-a provider create returned 3 (1.189 seconds), pool-d exposed the uppercase-hostname request defect (0.981 seconds), and the lowercase instance reached creation but project-local raw SCP failed before staging (124.309 seconds, including 43.306 seconds cleanup). The H100 attempts add 125.189 and 10,704.584 provider-active seconds without scientific output. Between reviews the harness completed 155 cycles, with 151 director and 152 researcher deferrals, but the durable waits are not the limiting work; five completed allocations produced zero scientific outcomes and no useful-GPU timing. The prior skill change did cause the L40S audit to check true simultaneous c8, primary/10K arms, and telemetry, yet it missed its own served/request identity requirement: the active owner starts `vllm serve "$m"` without `--served-model-name` while both its probe and shared runner request `google/gemma-4-31B-it`. The running owner remains untouched; this is a static mismatch until its terminal artifacts arrive.

**Change.** Updated `.agents/skills/experiment-run/scripts/research_efficiency.py` to consume the project-owner schema actually emitted by the lab: `owner_error`, typed `failure.json`, and verified `cleanup.json`. It now closes these allocations, infers their pre-science phase, uses recorded cleanup duration, reports live exposure through the observation time, and recommends returning to the last valid shared transport after repeated pre-science failures. Added a behavioral regression fixture in `test_research_efficiency.py`.

**Expected effect.** Supervisors and directors will now see repeated setup/transport failures and paid exposure instead of a false zero, making an evidence-backed shared-transport pivot happen before another project-local repair. At the fixed 2026-07-17T01:50:48Z observation, the report changes from zero completed/zero provider seconds to five completed operational outcomes, 10,956.252 provider-active seconds, five missing useful-GPU timings, and zero scientific outcomes; the live owner separately shows 236.932 seconds. Judge the change by fewer consecutive pre-science creates and by the next paid terminal containing a complete request plus useful-GPU timing.

## 2026-07-17 — bind immutable identities before paid delegation

**Bottleneck.** The corrected efficiency telemetry caused the right scientific pivot, but the new checkpoint-free paid lane is idle because its director-authored brief hand-transcribed the wrong immutable runtime digest. The constraint is delegation identity fidelity, not provider availability, model geometry, or the intervention choice.

**Evidence.** The shared-transport endpoint owner terminated after 7,125 seconds inside remote setup; total exposure was 7,254.924 seconds and cleanup took 56.984 seconds, with no model-load, request, useful-GPU, or GPU-telemetry artifact. The fixed efficiency report now correctly shows six completed operational outcomes, 18,211.176 provider-active seconds, zero scientific outcomes, and six missing useful-GPU timings. The director consumed that evidence and replaced endpoint staging with `gemma_l40s_fp8_exact_shape_microbench`, which is a shorter objective-relevant CUDA falsifier. However, its `PROJECT.md` pins unavailable image digest `sha256:952594c7e9337f1d3495ef2f0b3ebf3049791484a9d937c9d0da9f8488ea2520`, while both named authoritative FP8/FP8-KV packets pin resolvable `sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79` and amd64 manifest `sha256:8e86cb93b724092cd4dc892fb129a6c5538613b38a5cd34e40aab9e6aea72b03`. The researcher spent 143.584 seconds proving that mismatch and correctly created no provider resource. No paid owner is active.

**Change.** Added one rule to `.agents/skills/research-director/SKILL.md`: before activating paid work, mechanically extract checkpoint, runtime image, workload, and other immutable identities from the named authoritative artifacts and exact-match the brief; resolve disagreements in the director turn rather than delegating a readiness successor.

**Expected effect.** Paid projects should enter their first researcher turn with executable content identities, removing a full director/researcher cycle of preventable pre-create idling and keeping the next turn focused on the exact-shape CUDA result. Judge the change by whether the corrected microbenchmark launches through the named shared controller without another identity-only terminal and emits useful-GPU timing within its 45-minute exposure budget.

## 2026-07-17 — preserve primary evidence before conditional GPU arms

**Bottleneck.** The identity rule worked: the exact-shape L40S owner became the campaign's first allocation to reach target-GPU component science. The remaining bottleneck is that a late optional arm can erase the primary measurement needed to decide whether the model-specific FP8/L40S mechanism remains viable, forcing another paid allocation rather than advancing the campaign objective.

**Evidence.** The first exact-shape allocation started at 04:07:38Z, reached SSH at 04:08:10Z, and ran remotely for 540.682 seconds. It entered the conditional KV arm, so all primary exact-shape FP8 linear cases passed their finite-output and absolute-error gates by control-flow inference, but their rows and timings were buffered until the whole script completed. The KV arm then attempted one `33712 x 450560` BF16 tensor and failed on a measured 28.29 GiB CUDA allocation. The retrieved artifact contains the traceback, runtime identity, only three one-second telemetry samples, and no primary result or `useful_gpu_seconds`; the efficiency report consequently records zero scientific outcomes. The owner remained exposed for 1,213.960 seconds including its repair window and cleanup, costing a derived $0.255388. Authenticated cleanup passed with zero instances and disks. The director has already admitted exactly one bounded correction that atomically writes primary rows and uses per-layer 128-token KV tiles; its durable owner is active and was not polled, modified, or stopped by this review.

**Change.** Added one reusable rule to `.agents/skills/researcher/SKILL.md`: paid multi-stage experiments must atomically persist and retrieve each decision-bearing stage—including typed rows, timings, identity, telemetry interval, and a success marker—before a conditional or higher-memory arm; later control flow is not evidence, and optional high-memory arms must use bounded or tiled allocation geometry that cannot destroy primary evidence.

**Expected effect.** A late OOM or optional-arm defect should leave the completed primary result terminally usable, avoiding an otherwise unnecessary paid retry and letting the director decide immediately from exact-shape FP8 timing and numerical evidence. Judge the change by whether future paid multi-arm failures retain independently evaluable primary rows plus useful-GPU timing, and whether no new allocation is needed solely to reproduce a stage that already ran successfully.

## 2026-07-17 — audit the final scientific benchmark after harness integration

**Bottleneck.** Atomic stage persistence worked on the corrected generic run, but the campaign still has no execution-equivalent result for Gemma 4's actual pinned vLLM FP8 linear or KV consumer. The limiting failure is now final benchmark readiness: lifecycle/controller work passed while the staged scientific program was knowingly still a constructor/introspection placeholder.

**Evidence.** The corrected predecessor preserved its rows, passed after 621.989 provider seconds and `$0.131123`, and cleaned to zero resources; source reconciliation then correctly rejected its exact-consumer claim because four fused dimensions were wrong and its KV operation was `Tensor.copy_`. The successor consumer bridge created one L40S, reached SSH in 66.192 controller seconds, and ended after 659.202 seconds at a derived `$0.138968`; cleanup took 42.718 seconds and verified zero instances/disks. Roughly 531 seconds after SSH were spent bootstrapping the image before an approximately 18-second primary/retrieval interval. The retrieved typed result contains zero rows and no useful-GPU timing or telemetry: it selected `CutlassFP8ScaledMMLinearKernel`, then failed before `apply` because no current vLLM config context was set. Static inspection of the final staged script shows no required-shape execution loop, an unconditional placeholder exception immediately after `Fp8LinearMethod` construction, another placeholder for `ParallelLMHead`, and unconditional process exit zero. Its remote wrapper also omitted the controller-required internal manifest, so the controller raised `FileNotFoundError` after retrieval and its summary lost the typed stage record. These are harness-readiness failures, not evidence that the pinned consumer or L40S mechanism is unsupported. The owner was already terminal before intervention and was not modified.

**Change.** Tightened the existing paid component audit in `.agents/skills/researcher/SKILL.md` to run against the final staged benchmark after integration. It now explicitly fails closed before create on constructor/import-only probes, unconditional placeholder exceptions, empty required-case rows, missing required stage manifests or telemetry, and exit-zero envelopes around typed failures; lifecycle tests cannot substitute for the scientific benchmark audit.

**Expected effect.** The next checkpoint-free component allocation should begin only when its staged program can reach every required actual consumer and preserve the declared artifact contract, preventing another roughly nine-minute image bootstrap for a statically incomplete probe. Judge the change by whether the next paid terminal contains nonempty source-derived consumer rows, invoked symbols, timings, telemetry and `useful_gpu_seconds`, or instead closes before provider creation with the exact unresolved consumer-construction blocker.

## 2026-07-17 — bind component readiness to the immutable runtime image

**Bottleneck.** The final-program rule removed the obvious placeholder, but the next paid W4/FP8 component still launched on a static source/string audit that was not execution-bound to the immutable image. The campaign remains blocked on actual consumer rows because runtime identity and import availability are being discovered after provider creation.

**Evidence.** The W4 audit marked all ten readiness checks true using `py_compile` plus source-substring assertions, including the claimed Marlin method, FP8 method, six-shape loop, telemetry, and artifact contract. The resulting L40S allocation reached SSH in 67.942 controller seconds, ran for 661.545 seconds, cost a derived `$0.139462`, and cleaned to authenticated zero resources. Its typed primary had zero rows: after a script-reported 3.291 seconds that included import/setup rather than a scored kernel interval, it failed on `No module named 'vllm.model_executor.layers.quantization.auto_awq'`. The exact immutable image actually reports vLLM `0.19.1.dev6+g6d4a8e6d2`, not the source revision asserted by the brief. A later no-provider exact-image probe found the genuine `vllm.model_executor.layers.quantization.awq_marlin.AWQMarlinLinearMethod` and `vllm.model_executor.layers.quantization.fp8.Fp8LinearMethod`, proving this was a readiness mismatch rather than a W4 or FP8 mechanism result. Across nine completed allocations the efficiency report now shows 21,183.888 provider-active seconds, `$0.533817` invalid/operational cost, and no useful-GPU seconds; its one nominal scientific outcome is the generic-Ada result whose exact-consumer claim the director already rejected. The current bounded local image owner remains provider-gated and was not polled, changed, or stopped.

**Change.** Extended the paid-component audit in `.agents/skills/researcher/SKILL.md`: when consumer availability is image-bound, the researcher must run a CPU-safe import/construction probe inside the exact immutable image and bind the observed runtime, concrete class, source hash, and final staged imports. Static source checks or evidence from another revision cannot authorize provider creation.

**Expected effect.** Missing or renamed runtime consumers should close locally before the roughly nine-minute image/bootstrap charge, while a passing probe gives the paid run the exact import and class identity it will execute. Judge the change by whether the next component create is preceded by a passing exact-image terminal and produces nonempty W4/FP8 rows, or remains at `$0` with a typed image-bound blocker.

## 2026-07-17 — count typed staged science and preserve the model-scope denominator

**Bottleneck.** The lab finally produced a genuine exact-runtime component measurement, but its required efficiency report discarded that result while still crediting a source-rejected generic-Ada run. This hid both credible progress toward the exact Gemma objective and the dominant remaining process constraint: immutable setup is consuming nearly all paid GPU exposure for seconds-scale scored work.

**Evidence.** The lowercase final owner ran the pinned image and actual `vllm.model_executor.layers.vocab_parallel_embedding.ParallelLMHead` on L40S, passed all M=1/2/4/8/16/32 rows, recorded 1.401232476 useful GPU seconds, and cleaned to zero resources after 681.499 controller-measured seconds and `$0.143668052`. M=1 measured 3.918944 ms p50 and maps to 1.402982 seconds across 358 decode steps; M=2 falls to 0.703267 seconds/request. Before this review, `research_efficiency.py` classified the staged `PASS` as operational and reported zero useful GPU seconds because the retained controller emits `stage_records[].terminal.result`, not the older `allocation_result` schema. Conversely it counted the corrected FP8 allocation as science even though that project's terminal status says `terminal_partial_mechanism_pass_exact_shape_claim_rejected`.

**Change.** Updated `.agents/skills/experiment-run/scripts/research_efficiency.py` to recognize only fully passing, error-free typed stage records with nonempty scored rows; extract their staged `useful_gpu_seconds`; honor a matching project terminal's explicit scope/claim rejection; and report allocation plus campaign useful/provider fractions. A low measured fraction now recommends queueing compatible decision-bearing arms in one retained allocation. Added two behavioral regression fixtures in `test_research_efficiency.py`.

**Expected effect.** The throughput signal now reports one objective-valid scientific outcome, 1.401 useful GPU seconds, and 12 invalid/operational or scope-rejected outcomes across 21,953.990 observed provider seconds, rather than crediting the rejected proxy and missing the real result. The final head allocation's observed useful/provider fraction is 0.22% and the campaign-wide fraction rounds to 0.01%; this should make setup amortization visible when the director chooses compatible arms without weakening scientific gates or changing the active portfolio. Judge the change by increased scope-valid useful GPU time per provider second, not raw allocation count.

## 2026-07-17 — make launch-ready paid turns terminally accountable

**Bottleneck.** The scope-aware throughput correction worked: the director consumed the exact head result and activated the campaign's first matched full-stack H200 endpoint experiment. Progress is now limited by a non-monotonic launch handoff. Passed pre-create evidence is being revisited across researcher turns, and the latest explicitly assigned launch turn returned after orientation without either executing the renderer/launcher or discovering a new blocker.

**Evidence.** The H200 project was activated at 07:25:46Z. Four researcher turns totaling 429.849 seconds materialized and hashed the exact checkpoint in 311.706 local seconds, diagnosed the zero-byte inventory formatter, produced authenticated empty instance/disk proof, and then received an explicit director instruction to render, audit, and launch. The final 34.593-second trace contains only two read-only commands: it listed project/shared-controller files and reread the already passing checkpoint/inventory terminals. It created no runner, final-program terminal, durable service, provider resource, typed blocker, or project-log update, and returned that the remaining work was still the mandatory rendered program and H200 execution. `STATUS.json` consequently has `active_session: null` and the same launch next action; no provider owner is live. The campaign still has one scope-valid component outcome and no exact-model endpoint measurement.

**Change.** Added a launch-readiness monotonicity rule near the top of `.agents/skills/researcher/SKILL.md`. Once project status names provider launch and mandatory pre-create terminals pass, the researcher must consume rather than reopen them and may exit only with a durable-owner snapshot after executing the admitted renderer/launcher or with a new typed blocker produced by that execution. Controller inspection, another readiness artifact, or restating remaining launch work is explicitly not a handoff.

**Expected effect.** The next H200 researcher turn should spend its context on the narrow endpoint adapter and reach provider ownership or an actionable execution blocker, rather than consuming another director/researcher cycle on settled gates. This preserves every identity, audit, spend, watchdog, and cleanup condition and does not alter the scientific portfolio. Judge the change by whether launch-ready paid projects require at most one implementation turn between the last passing pre-create terminal and a live durable owner or typed launcher failure.

## 2026-07-17 — observe the live owner schema instead of reporting GPU idleness

**Bottleneck.** The monotonic launch rule worked, but execution exposed repeated project-local audit/launcher defects before the current corrected owner: the first matched H200 owner reused the known uppercase-hostname failure, its sole retry pre-created the output directory and invalidated its own audit, and the first simplified vLLM owner used raw SCP without the shared host-key contract. The final corrected vLLM owner is now making forward progress; the safe process constraint during its checkpoint transfer is observability. The required efficiency report silently omitted it because this owner writes `timestamp_utc` and `provider_created`, while the report accepted only `timestamp` and `instance_created`.

**Evidence.** The active `gemma-vllm-h200-20260717t084247z-owner.service` has a bound H200 instance and independent watchdog. Its durable events record owner start at 08:42:55.098Z, provider creation 45.877 seconds later, and SSH readiness after another 37.603 seconds; a shared resumable checkpoint transfer was active at review time. No scored GPU result exists yet, so the correct disposition is preserve and wait. Before the change, the fixed-time efficiency report returned no H200 allocation and still showed only 13 historical completions. After the change it reports this owner as `in_progress` with 94.902 observed seconds and the provisioning/SSH split. The earlier SGLang and first-vLLM pre-science failures remain a documented limitation because their directories have verified cleanup/failure files but no event stream; no synthetic timestamps were invented.

**Change.** Updated `.agents/skills/experiment-run/scripts/research_efficiency.py` to accept either `timestamp` or `timestamp_utc` in campaign-owner events and to treat `provider_created` as the current-owner alias of `instance_created`. Added a behavioral live-owner regression fixture in `test_research_efficiency.py`.

**Expected effect.** Supervisors and directors can now distinguish a correctly retained setup/transfer from an idle or missing GPU lane, see live exposure against the H200 deadline, and avoid duplicate launch or premature strategy changes while the owner progresses. This does not poll, mutate, or slow the active service. Judge the change by whether current owners appear in the daily report from owner start through terminal cleanup with accurate create/SSH timing, followed by useful-GPU and scientific classification when their typed result arrives.

## 2026-07-17 — establish owner workspaces before execution

**Bottleneck.** The live-owner observability fix correctly preserved the H200 transfer, but the next two paid lanes both terminated on missing workspace-parent contracts rather than reaching the exact Gemma endpoint objective. With every scientific lane now closed and no paid owner active, the limiting constraint is owner initialization at the local/remote filesystem boundary, not experiment selection or GPU availability.

**Evidence.** The corrected H200 owner successfully transferred the exact 62,578,655,922-byte checkpoint once in 946.696 seconds, then failed before image pull, model load, or a request because `/home/glmrunner/gemma` remained root-owned and the `glmrunner` session could not create sibling `input`. Cleanup passed after 55.936 seconds; the two vLLM attempts total 1,131.601 provider seconds, `$0.777757` derived cost, and zero useful GPU seconds. The director then spent 900.570 seconds selecting a materially different L40S online-FP8 lane. Its 294.872-second researcher turn launched the sole owner, but that owner raised `FileNotFoundError` while creating its run directory under a nonexistent project `artifacts/` parent; it created no provider resource, watchdog, checkpoint transfer, model load, or request. These are two independent manifestations of the same precondition gap: child paths were assumed writable without establishing their parent workspace. Neither result bears on H200, L40S, vLLM, FP8, or endpoint economics. Service inventory at review time showed no active Gemma or lab experiment owner.

**Change.** Added two small pre-execution guarantees at shared boundaries. The lab harness now creates `<project>/artifacts` immediately before submitting an admitted researcher, so project-local durable owners can create their run root without weakening any scientific or provider gate. Shared Nebius `session_staging.py` now rejects targets without a dedicated parent and uses `sudo install -d -o glmrunner -g glmrunner` on both the session parent and checkpoint target during state query/initialization, allowing later sibling inputs and program files after a long checkpoint transfer. No project was reopened or retried. Added regression assertions for both local artifact parents and remote `/home/glmrunner/gemma` plus `/workspace` ownership; 29 focused tests and the repository DevEx check pass.

**Expected effect.** The next admitted endpoint owner should fail any workspace preparation before provider creation locally and should retain a writable remote session root before transferring tens of gigabytes. This removes the observed immediate local failure and the post-transfer sibling-permission failure while preserving checkpoint identity, workload, audit, spend, watchdog, and cleanup gates. Judge the change by whether the next paid owner advances past workspace setup into image/model/request execution or returns a genuinely model- or runtime-specific typed blocker, with no further allocation ending solely on a missing or root-owned owner-workspace parent.

## 2026-07-17 — bind cleanup watchdogs to the owner's systemd manager

**Bottleneck.** The workspace guarantee worked, but the campaign's new direct SGLang H200 allocation still ended before SSH or model execution because the shared cleanup-watchdog helper assumed every durable owner used the user systemd manager. The direct owner was deliberately launched as a system service, so its first post-create safety action targeted an unavailable bus. The campaign remains at one exact-runtime component result and no complete exact-model endpoint request; lifecycle-manager compatibility, not SGLang or H200 performance, is the immediate measured constraint.

**Evidence.** After the previous review, the corrected L40S turn passed project artifact initialization, created one L40S, verified the exact image digest, and closed later on an unoverridden image entrypoint after 389.732 provider seconds; this confirms the earlier local-parent fix removed its observed failure. The director then spent 900.620 seconds and the SGLang researcher 437.790 seconds on a direct H200 lane. Its 25-check final-program audit marked `watchdog` true only from the helper's presence. Provider create passed in 41.291 seconds, but at 69.860 seconds the shared `start_independent_watchdog` called `systemd-run --user` from `/system.slice/gemma-sglang-h200-20260717t101700z-owner.service`; the typed error reports no `DBUS_SESSION_BUS_ADDRESS` or `XDG_RUNTIME_DIR`. Verified cleanup consumed 69.854 seconds and ended with zero instances/disks. No SSH, checkpoint transfer, model load, request, telemetry, or useful GPU time occurred, so this is not SGLang/H200 evidence. The owner and watchdog are terminal and no experiment service was active at intervention time.

**Change.** Made shared `vllm_smoke_control.start_independent_watchdog` manager-aware. It now accepts an explicit `system`/`user` manager, defaults to the user manager only when the owner has a user runtime bus, otherwise uses the system manager, queries health through the same manager, rejects invalid values, and records the selected manager in its typed snapshot. Existing user-service behavior is preserved; system-service owners no longer cross manager boundaries. Added regression coverage for both `/user.slice` and `/system.slice` launch/query paths. The focused 49-test suite, Python compilation, DevEx checks, and diff checks pass. No project status, allocation, or scientific portfolio was changed.

**Expected effect.** A system-owned paid owner should establish its independent cleanup watchdog immediately after create instead of cleaning an otherwise healthy GPU solely because the user bus is absent, while existing user-owned controllers continue unchanged. Judge the improvement by the next admitted owner reaching SSH and model/scientific execution or a typed route-specific blocker with a manager-matched watchdog snapshot; no future allocation should terminate on a user/system watchdog-manager mismatch.

## 2026-07-17 — make local checkpoint validation results unambiguous

**Bottleneck.** The manager-aware watchdog worked: subsequent H200 owners passed owner/watchdog creation and SSH. Progress then stopped at the local checkpoint handoff in three consecutive vLLM endpoint lineages, with no model load or complete exact-model request. The latest `$0` owner-local gate proved the bytes valid but rejected its own success because the shared validator overloaded `False` to mean “freshly hashed successfully” and exposed no explicit distinction between payload and transfer-contract file counts. Transfer-contract semantics, not H200, vLLM, or checkpoint validity, are the measured constraint.

**Evidence.** The first post-review H200 owner passed user-scope watchdog, create, SSH, and remote session-parent setup, then closed because the raw checkpoint lacked the staging checksum contract: 131.544 provider seconds, `$0.090411`, and zero useful GPU seconds. A cross-project hardlink view then passed the shared validator over 62,578,655,922 bytes and nine staged files in 77.389 local seconds, but disappeared before its paid owner consumed it; that owner again passed watchdog/create/SSH and cleaned after 144.482 provider seconds and `$0.099304`, with zero useful GPU time. The director correctly moved view construction into the sole owner before create. That final owner completed a fresh full hash in 76.818 seconds with matching hardlinks, sizes, manifest, and all eight payload hashes, yet its terminal failed at `$0`: `validate_local_files_cached()` returned `False` solely because it had just written the valid marker, and the project compared the nine-file transfer inventory (eight payloads plus `model-files.sha256`) to an expected payload count of eight. Across the two paid post-review attempts this boundary consumed 276.026 provider seconds and `$0.189715` without transferring a checkpoint byte or producing science. No experiment owner was active during intervention; the director is independently pivoting to a checkpoint-free H200 falsifier and was not modified.

**Change.** Changed shared `session_staging.validate_local_files_cached()` to return an explicit JSON-ready record on every successful validation rather than a cache-hit boolean. The record contains `pass`, `marker_reused`, payload file/byte totals, and the distinct transfer file/byte inventory. Corruption still raises the same typed error, and existing production callers that ignore the return remain unchanged. Regression coverage now proves that a successful first hash reports `pass: true` with `marker_reused: false`, a warm validation reports reuse, and one payload plus its checksum contract is explicitly two transfer files. Thirteen focused staging tests, Python compilation, DevEx, and diff checks pass. No closed project, stop rule, active experiment, or portfolio decision was changed.

**Expected effect.** Future checkpoint-backed owners can bind one authoritative validation record directly into their pre-create terminal without treating a fresh successful hash as failure or inventing a contradictory cardinality gate. Judge the change by whether the next use of this staging path either closes locally on an actual checksum/identity error or proceeds through checkpoint transfer; no further lineage should fail because `False` meant “validated but marker newly written” or because the checksum contract was counted as payload.

## 2026-07-17 — preserve the correctly gated exact endpoint owner

**Bottleneck.** The local checkpoint-contract defect is resolved. The campaign's limiting step is now the sole live, exact-model H200 endpoint owner producing complete c32 latency and telemetry, not researcher activity, reporting cleanliness, or another shared-code change. Exact component evidence plus the independent KV-read bound has already eliminated c1, c4, c8, and c16; c32 is the only concurrency still capable of clearing the campaign ceiling. Mutating the harness or shared staging code while that owner is live would add risk without increasing objective-relevant information.

**Evidence.** The active `gemma-vllm-c16c32-20260717t1500z.service` consumed the prior validator change exactly as intended: its local terminal reports `pass: true`, `marker_reused: false`, eight payload files totaling 62,578,655,208 bytes, and nine transfer files totaling 62,578,655,922 bytes including `model-files.sha256`. Provider preflight passed with empty inventories and eight fresh preemptible H200 slots; the final audit passed all 31 checks. At the review snapshot the durable user-systemd owner was the only experiment owner, had completed local hashing and pre-create gates, and was executing provider creation. Separately, the exact H200 transformer-linear and `ParallelLMHead` component project completed with 586.894 provider seconds, 1.068793 useful GPU seconds, derived spend of `$0.400999`, and verified cleanup. Its combined component floors are 6.625177, 1.691650, 0.879517, 0.442462, and 0.224770 seconds/request at c1/c4/c8/c16/c32. Adding the optimistic exact-geometry KV-read floors yields 0.500338 seconds/request at c16, above the approximately 0.472–0.478-second ceiling, and 0.282767 at c32, which remains viable. Recent 900-second director timeouts still yielded that component result, the KV falsifier, and this endpoint launch; generic turn duration is therefore not the measured constraint.

**Change.** No new skill, tool, harness, project, or owner mutation is warranted this turn. I left the live owner, its imported shared bytes, and the scientific portfolio untouched. The supervisory disposition is to preserve exclusive ownership and let the already-audited c16/c32 run reach a typed terminal; the earlier shared-validator intervention is now validated by its first production consumer.

**Expected effect.** Avoiding a concurrent process patch removes supervisor-induced launch and import risk at the first correctly gated exact endpoint attempt. The terminal should now provide either complete c32 endpoint throughput/latency/economics evidence or a route-specific typed failure that identifies the next actual constraint. Judge this disposition by one terminal owner outcome with verified cleanup and no duplicate allocation, not by additional supervisor activity.

## 2026-07-17 — require behavioral evidence from paid final-program audits

**Bottleneck.** Paid program-readiness audits are repeatedly certifying source inventories rather than executable scientific contracts. The campaign is selecting relevant H200 and L40S questions, but provider time is ending on defects that an honest pre-create behavioral audit should catch. This is now the constraint on model-specific evidence: not director cadence, GPU supply, or cleanup, but false-positive admission of programs that cannot execute or interpret their claimed exact-Gemma consumers.

**Evidence.** The preserved exact-vLLM H200 owner later received a post-create behavioral audit that invalidated its already passing 31-check final audit: the captured runner lacked the required semantic, repetition, c32 headroom/cache-state, 10K counter, metrics, economics, and prefix-arm contracts and retained an unauthorized SGLang trigger. Because the live program was immutable, it transferred 62,578,655,922 bytes and then intentionally failed before remote execution; 1,069.058 provider seconds and `$0.727553` produced zero useful GPU seconds. The next H200 attention program also passed its paid static audit, but an independent behavioral audit predicted its scalar `window_size=-1` TypeError, dense non-paged sliding path, missing oracle/residual arm, and 358x aggregation error. The paid run confirmed that TypeError after one invalid sliding row: 573.717 provider seconds, `$0.391995`, and zero decision-bearing useful GPU seconds. Together these false-positive gates consumed 1,642.775 provider seconds and about `$1.119549` without objective-valid science. Recent director timeouts still produced the attention falsifier, successor decision, and current L40S launch, so generic 900-second turn duration is not the limiting signal. At the review snapshot the sole L40S owner had created one instance, reached SSH in 80.684 seconds, and had an independent watchdog; I did not mutate or poll it. Its passing audit illustrates the future risk by deriving every scientific readiness boolean from `all(x in source ...)` token presence while executing only an image import/hash probe.

**Change.** Added one prominent rule near launch readiness in `.agents/skills/researcher/SKILL.md`: a paid final-program audit is a behavioral result, not a source inventory. Hash, AST, import, and token checks may bind identity but cannot pass scientific acceptance claims. Non-CUDA claims must execute through the staged call/evaluator with representative inputs; CUDA-only calls must be exact-image constructor/signature-bound and become the first atomically retrieved fail-fast stage. An audit that cannot meet that contract fails before create. No active project, controller, shared executable, portfolio decision, or provider owner was changed.

**Expected effect.** Future paid owners should stop spending setup and transfer time on programs whose required calls, aggregation, oracle, or conditional arm exist only as text. The next admitted allocation should either close at `$0` on a typed behavioral audit failure or retrieve a first-stage result whose acceptance claims were actually exercised; judge the change by eliminating static-audit-pass/behavioral-audit-fail pairs and increasing decision-bearing useful GPU seconds per provider second, not by adding audit artifacts.

## 2026-07-17 — keep durable terminals runnable until scientific reconciliation

**Bottleneck.** The behavioral-audit intervention improved the execution geometry enough to produce valid exact-shape L40S FP8 evidence, but the durable controller then marked its project `complete` before a researcher interpreted that evidence. The harness schedules researchers only for `active` or `ready` projects, so the first decisive CUTLASS FP8 terminal is absent from the project log and exposed to the director only as an unreviewed summary. Turning completed GPU measurements into a typed scientific decision is now the immediate constraint, not provider access, GPU execution, or portfolio generation.

**Evidence.** The direct L40S owner executed an atomically retrieved M12 sentinel before its conditional sweep, invoked the installed `vllm._custom_ops.cutlass_scaled_mm` path, and passed separate kernel-correctness and representation-loss oracles. It then retrieved all twelve exact c12 rows over the six Gemma shapes at M12 and M3679. The architecture-weighted linear floor is 1.926667333 seconds/request; adding the independent 0.164631539-second attention/KV residual gives 2.091298872 seconds/request, falsifying both the 1.394580641 planning and 0.863293105 conservative L40S service ceilings. The owner passed after 694.880 provider seconds and derived `$0.146489`, with authenticated cleanup to zero. Yet `STATUS.json` says `status: complete` and “reconcile retrieved artifacts,” while `RESEARCH_LOG.md` ends with the owner still live and contains no terminal interpretation. The launch researcher returned at 15:01, the controller terminal arrived at 15:11, and the next researcher completed an unrelated H100 mechanism project; no provider owner was active at this review. Five recent 900-second director timeouts still produced the single-rank quarantine, corrected oracle, direct packet, paid launch, and H100 branch, so generic coordinator duration is not the limiting signal.

**Change.** Tightened the durable-owner handoff in `.agents/skills/researcher/SKILL.md`. A terminal controller must now clear `active_session` while leaving project `status: active`, set `reconciliation_pending: true`, name its `terminal_artifact`, and schedule reconciliation. Only the later researcher turn that interprets the typed scientific result and authenticated cleanup may mark the project complete or closed. This uses the harness's existing active-project scheduling path; no harness reload, provider mutation, current project artifact, or scientific portfolio decision was changed.

**Expected effect.** Future durable terminals will receive one automatic reconciliation turn instead of disappearing from researcher scheduling at owner exit. That turn should convert raw rows, cost, and cleanup into the project's durable decision before the slot is retired, allowing the next director cycle to act on a scope-valid result rather than rediscovering it from archives. Judge the change by every terminal owner receiving exactly one post-owner interpretation and by eliminating `complete` projects whose summary requests reconciliation while their log still describes a live session.

## 2026-07-17 — finish independent program audits before provider create

**Bottleneck.** The durable-terminal change worked: the L40S CUTLASS result received an offline reconciliation turn, became a typed falsification, and the director selected a materially different H100 portfolio. H100 progress is now limited by audit ordering. Independent final-program audits are being delegated only after paid immutable owners reach create or SSH; failed audits can then quarantine science but cannot prevent the spend or repair the frozen program.

**Evidence.** Three recent H100 owners were followed by independent audits that failed on defects visible in their immutable local bytes. The paged-KV audit found no selected paged-backend call, FP8 arm, oracle, counters, sweep, or conditional; its owner consumed 579.072 controller seconds and `$0.347399` with zero decision-bearing rows. The corrected raw-FP8 audit found unmeasured sampling cadence, unscoped liveness telemetry, and no remote equality gate for the correction; that owner consumed 569.165 seconds and `$0.341455`, and its liveness subprocess additionally failed before CUDA so the sweep never ran. The W4 audit found an unset `SESSION_STARTED_EPOCH`, unbound remote inputs and telemetry, and unreachable head logic; its owner consumed 567.880 seconds and `$0.340684` before a typed pre-timing failure. Those three post-create audit failures total 1,716.117 provider/controller seconds and about `$1.029538` with no campaign-valid aggregate. The intervening H100 raw-FP8 audit did pass and preserved one valid 0.048064-ms M8 row, showing that an immutable audit can make an interpretation decision; coarse telemetry nevertheless blocked its sweep. Across all four H100 owners, 2,271.648 seconds and about `$1.362814` yielded only that isolated row. The current BF16 H100 project instead failed closed at `$0` because its conditional predicate lacks measured same-session setup input, and no provider owner was active at this review. Recent long director turns still generated distinct paged-KV, raw-FP8, W4, and BF16 branches, so portfolio ideation and generic turn duration are not the immediate constraint.

**Change.** Added one ordering rule to `.agents/skills/research-director/SKILL.md`: never authorize provider create while a separate final-program audit is pending or planned. The director must either accept the launch researcher's behavioral pre-create audit as sufficient, or require one independent audit of immutable staged bytes and consume its typed terminal before activation. A read-only audit launched after create is explicitly not a safe parallel lane. I did not modify the active BF16 project, its shared-controller repair, any project artifact, or provider state.

**Expected effect.** The next paid project that needs independent scrutiny should either close locally on the audit's real defect or launch with an interpretation-safe frozen program; it should not create first and discover afterward that all science is quarantined. Judge the change by zero new owner/audit pairs in which the provider-created timestamp precedes the audit terminal, reduced paid pre-science exposure, and more complete decision-bearing sweeps per allocation—not by the number of audits produced.

## 2026-07-17 — route mechanism discovery to deep researchers

**Bottleneck.** The lab can identify broad hardware/kernel opportunities, but its recent Gemma hardware frontier stopped at labels such as fused attention because static round-robin routing assigned the mechanism-discovery project to a medium-effort fast researcher. The missing work was source-, shape-, and chip-level causal interpretation, not another experiment gate.

**Change.** Added one optional `researcher_profile: deep` project hint. The director uses it only for mechanism discovery or surprising-telemetry interpretation; the harness routes those turns to Sol high and leaves implementation, provider operation, and sweeps on Terra/Luna. The researcher skill now asks for a concrete observation-to-limiter-to-source-to-change-to-measurement chain while explicitly rejecting long reports and checklists. Focused routing tests and all 93 factory tests pass.

**Expected effect.** Promising bottlenecks should receive sustained mechanism-level reasoning without slowing routine execution. Judge it by whether deep projects produce concrete source-level hypotheses and exact-shape measurements, then hand settled implementation back to the fast pool—not by the number of deep turns or documents.

## 2026-07-17 — keep local audit corrections inside the scientific project

**Bottleneck.** Moving final-program audits before provider creation eliminated the recent paid audit quarantines, but the lab is now treating a defect in the local audit itself as a terminal scientific no-repair condition. This fragments one executable H100 question into successor projects and prevents the shortest proven exact-Gemma component measurement from reaching the GPU, even though no immutable provider state or scientific variable has changed.

**Evidence.** The three post-ordering H100 execution turns for `h100_bf16_exact_linear_head_floor`, `h100_parallel_lm_head_direct_floor`, and `h100_head_two_stage_direct_floor` consumed 684.641 researcher seconds and all closed before provider creation without H100 science. The subsequent `h100_parallel_lm_head_single_stage` removed the multi-stage controller mismatch by reusing the byte-for-byte proven L40S `ParallelLMHead` benchmark and wrapper as one unconditional six-row H100 program. Its internal audit passed the bound program identities, placement, lowercase request, archive, telemetry, accounting, watchdog, cleanup, budgets, and empty provider inventory. The sole failure was `one_primary_container`: the predicate searched for the benchmark name as a standalone argv element, while the rendered create argv correctly carries it inside `MICROBENCH_PATH=/input/<benchmark>`. The project log classifies this as an internal audit blocker rather than H100 evidence, and `STATUS.json` nevertheless closes the project under a one-audit, zero-repair contract and requires successor authorization to fix the predicate. No provider request, create, active owner, or GPU charge resulted. The independent B200 mechanism project produced a useful candidate at `$0`, so mechanism ideation and generic activity are not the limiting signal.

**Change.** Clarified `.agents/skills/research-director/SKILL.md` that paid no-repair/no-retry limits begin at provider create. Before create, a false negative caused by the audit or evaluator rather than the staged scientific program is a local integration defect: correct it in the same project, rerun the audit, and proceed if it passes within budget. This complements the existing mutable retained-session rule without weakening identity, watchdog, spend, behavioral-audit, exclusivity, or cleanup gates. I did not reopen a closed project, alter a scientific arm, modify the shared provider controller, or touch provider state.

**Expected effect.** The next otherwise-ready experiment with an audit-harness mismatch should move within one project to either provider ownership or a genuine scientific/operational blocker, rather than consuming another director cycle and successor directory for the same question. Judge the change by zero new `$0` project closures whose only blocker is a correctable audit/evaluator predicate and by restored objective-valid GPU measurement cadence—not by additional audit artifacts.

## 2026-07-17 — remove remaining >20% cadence constraints

**Bottleneck.** The 24-hour efficiency report records 23 completed allocations but only three scientific outcomes: 20 invalid or operational outcomes consumed 79.92% of measured spend, and 17 allocations lacked useful-GPU timing. The recent H100 head success used 566.638 provider seconds for 1.086 useful GPU seconds, so cold setup still dominates experiment latency. Separately, 68 director turns consumed 36,006.7 seconds versus 20,669.5 researcher seconds; the generated status and two logs are 144,805 bytes, and a recent director turn retrieved roughly 140 KB of broad status/log context. The live director then issued at least ten empty `wait` calls while the H100 owner ran instead of returning to the harness. Tool wait was only 18.15% of aggregate active coordinator time, so further ordinary shell-call optimization does not clear the requested 20% impact threshold; eliminating whole director monitoring intervals does.

**Change.** Corrected the stale campaign sentence that still limited paid concurrency to one allocation, preserving the `$25` total spend cap while allowing independent paid sessions up to the five-researcher cap. Changed the director prompt to inject only the active portfolio and latest director/supervisor sections and to avoid generated `STATUS.md`, full logs, closed projects, and unrelated briefs by default. The director skill and prompt now require one snapshot decision and immediate return, explicitly forbidding wait, sleep, polling, monitoring, and internal subagents. When cold setup dominates a likely compatible arm, another researcher now prepares that arm offline during bootstrap so the owner can reuse resident state if it becomes ready without delaying the primary. No warm-pool infrastructure was added before observing this lighter mechanism.

**Expected effect.** Parallel paid work removes the former global serialization. The director context reduction should lower total agent-cycle time by roughly 25–35% if director latency falls from its 529.5-second mean toward 300 seconds. Retaining compatible environments should save well over 50% on short component iterations when another arm or repair follows the first call. Judge both from the next daily report: director duration, scientific outcomes per active hour, provider seconds per scientific outcome, and useful-GPU/provider fraction.

## 2026-07-17 — hold recoverable microbenchmark failures inside the paid owner

**Bottleneck.** The new development-session scheduling policy keeps the same researcher attached to a live allocation, but the shared checkpoint-free microbenchmark controller still entered verified cleanup as soon as a stage raised. `mode: development` was therefore only a scheduling label: the researcher could observe normal setup, but a remote traceback would destroy the exact image and GPU before the next harness turn could patch and rerun. Cold restart after recoverable integration failure, not H100 execution or mechanism selection, is the measured throughput loss.

**Evidence.** The earlier H100 W4 owner reached SSH after 83.935 seconds and then exposed a recoverable single-rank integration defect: the retrieved primary traceback was `AssertionError: tensor model parallel group is not initialized`. Its controller surfaced a missing-manifest error and wrote `experiment_error` and `cleanup_verified` at the same 17:52:43 timestamp. The project consequently spent 567.880 provider seconds and about `$0.340684` for zero timing rows and zero useful GPU science. The repaired TP adapter was ready only after the resource had disappeared, so it could not reuse the allocation. The reopened H100 head project validates the adjacent process changes: the local audit predicate was corrected in the same project, the unchanged six-row actual `ParallelLMHead` program produced 1.086352 useful GPU seconds over 566.638 provider seconds, and cleanup passed. But its setup completed before the W4 repair packet, forcing the current W4 question onto another cold H100. At this review, that new owner was live with watchdog and SSH ready, `active_session.mode` was `development`, and the harness rescheduled the same researcher for a 37.424-second grouped snapshot; the researcher correctly preserved normal setup. Inspection of the already-loaded controller showed that any later exception would still leave `VerifiedRetainedOwner` immediately. I did not alter or poll that active process.

**Change.** Wired the shared `mla_microbench_control` repair hold inside the verified cleanup-owner context. A new explicit `repair_window_seconds` option, capped at 600 seconds and defaulting to zero, wraps development execution so a traceback is persisted while the instance, image, and resident state remain available; an explicit `repair-decision.json` teardown or the absolute deadline then releases normal authenticated cleanup. Batch/canonical callers retain immediate cleanup unless they opt in. Added a behavioral regression test proving the repair window opens before the original exception is re-raised, and clarified the researcher skill that `mode: development` is valid only when the launcher exposes such an owner-side repair path. The live W4 owner had already imported the old module and was left untouched; watchdog, spend deadline, trace capture, exclusivity, and final cleanup semantics remain unchanged.

**Expected effect.** The next opted-in checkpoint-free development run with an import, runtime-context, benchmark, telemetry, or artifact-packaging failure should give the owning researcher up to ten minutes to patch and rerun on the same GPU instead of paying another 80–90 seconds for readiness plus image bootstrap and losing resident CUDA state. Judge the change by recovery attempts sharing one resource identity and cleanup terminal, fewer pre-science cold allocations per scientific question, and increased useful-GPU/provider fraction. Do not judge it by repair-window count; scientific negatives and batch runs should still clean immediately.

## 2026-07-17 — preserve the objective-critical c32 residual owner

**Bottleneck.** The owner-side repair intervention worked. Process lifecycle is no longer the immediate constraint: the campaign now has scope-valid H100 W4 Machete timing, and the only remaining question before this component combination can promote is whether actual c32 paged E4M3 KV update plus attention fits the measured `0.0738631898962037 s/request` residual. That scientific GPU result—not another skill, audit, controller, or portfolio change—is the current rate limiter.

**Evidence.** The retained Machete owner created one H100, reached SSH in 86.345 seconds, passed the actual TP-initialized M8 sentinel, and retrieved its primary stage. Its conditional wrapper then failed after producing valid rows because `SESSION_STARTED_EPOCH` was unset and `ncu` was unavailable. At 20:44:44Z the new shared lifecycle opened a 600-second repair window instead of cleaning. The same researcher remained scheduled, attached to the same resource, changed the wrapper to consume the typed timing profile when counters were unavailable, suppressed the disallowed head arm, and retrieved `h100-w4-conditional-repair.tar.gz` from that owner. All 24 paired W4/BF16 rows and dual oracles passed. Reconciled W4 floors are `0.995345/0.636049/0.463243 s/request` at c8/c16/c32; only c32 survives the `0.547975 s/request` planning ceiling, with the measured head adding `0.010869 s/request`. Authenticated cleanup passed at 20:51:32Z after 951.101 provider seconds and derived `$0.570587362`. This is the first production proof that a recoverable failure became objective-valid science without a cold restart; missing counters correctly remain a mechanism limitation rather than invalidating timing.

The director then activated one narrowly scoped c32 residual experiment. At review, `h100_w4_machete_fp8kv_residual_falsifier` had one H100 owner and watchdog live, SSH ready after 82.559 seconds, `active_session.mode: development`, an explicit 600-second repair window, and normal pinned-image bootstrap progress. Its exact actual-runtime program registers real attention layers, establishes forward context, writes real page-table slots, and measures paired BF16/E4M3 cache update plus attention calls. The 421.682-second implementation/launch turn and 61.875-second attachment turn produced a durable owner rather than another readiness project; the latest director decision took 24.504 seconds. No local error or scientific row existed at the snapshot, so intervention would only risk the decisive run.

**Change.** No additional skill, shared-tool, harness, project, or provider mutation is warranted while this owner is healthy. I left the resource, watchdog, imported controller bytes, project files, and scientific portfolio untouched. The prior repair-window change is validated and should remain unchanged until its current consumer reaches a typed terminal.

**Expected effect.** Preserving the live owner should yield either scope-valid c32 FP8-KV/attention rows that close or promote the measured W4-plus-head combination, or a recoverable traceback that the already-attached researcher repairs on the same H100 before the absolute deadline. Judge this disposition by a single resource identity spanning any repair and final authenticated cleanup, plus a decision on the `0.0738631898962037 s/request` residual—not by further supervisor activity.

## 2026-07-17 — keep the launching researcher through a development repair window

**Bottleneck.** The campaign's scientific constraint is now executable global-attention semantics for the only surviving H100 c32 W4 combination, not generic cadence or cleanup. The retained owner path is working, but the harness can change researcher model and thread during the most context-sensitive part of that path when a director changes `researcher_profile` while `active_session.mode` remains `development`. This weakens the intended same-researcher patch/rerun loop precisely when a typed CUDA failure arrives.

**Evidence.** The first c32 residual owner demonstrates that retention is valuable: one H100 remained allocated while the researcher corrected current-config scoping, real `CacheConfig`, CUDA-resident scale buffers, metadata, and packaging through five retrieved repair archives. It reached both actual producer and consumer calls before the global finite-zero semantic oracle stopped interpretation; cleanup passed after `1028.537` provider seconds and `$0.617042852`. The source-level follow-up then ran for `1086.312` agent seconds on `gpt-5.6-sol`, produced the content-bound global-route correction, and launched a second retained owner. That owner's M1 terminal arrived at `21:44:49Z`, opening its 600-second repair window 33 seconds after the Sol turn returned. The director changed the project back to execution, so the next attachment at `21:45:54Z` was a fresh `gpt-5.6-terra` thread rather than the launching Sol thread. Terra correctly reused the same H100 and inspected live installed source, but after 250 seconds requested teardown because populated BF16 KV pages still produced exactly zero output. The result is a valid semantic negative for that proposed route, not a recoverable traceback and not a residual measurement: `3.182044105` useful GPU seconds over `817.235` provider seconds, `$0.49027813`, zero timing rows, and authenticated empty cleanup. Across both owners the `0.0738631898962037 s/request` decision remains open. No paid owner was active at intervention time.

**Change.** The shared lab harness now pins a live `mode: development` project to its recorded launching model route, including the deep Sol route, until that session reaches terminal. A director may still change the post-terminal project profile, and batch owners retain the existing defer/reroute behavior. Because the existing project thread is keyed by model, preserving the model also preserves the resumable researcher thread instead of silently starting a new one. Added a regression that reproduces a Sol-launched retained session whose status is changed to execution and proves the attachment still routes to Sol. All 19 focused harness tests pass. The terminal residual project, provider inventory, scientific program, budgets, and portfolio were not modified.

**Expected effect.** Future recoverable integration failures should be diagnosed and patched by the researcher that formed and launched the live program, preserving its source/runtime context and using more of the bounded repair window for an actual rerun. Judge the change by one model/thread identity spanning development launch, attachment, and any repair; one provider resource identity spanning failed and corrected stages; and fewer development windows ending without a rerun solely after a profile handoff. Semantic negatives such as the populated-cache zero-output result should still clean promptly, and this change should not be used to prolong them or create another project.

## 2026-07-18 — wake retained researchers on owner evidence, not a one-minute poll

**Bottleneck.** The previous route pin worked: every attachment to the new retained H100 owner stayed on its launching Terra route. The remaining coordination waste is unconditional rescheduling of that same development researcher while the owner has emitted no new actionable evidence. This spends the campaign's dominant resource—model/orchestration time—on repeated healthy-bootstrap snapshots without accelerating the objective-bearing GPU program.

**Evidence.** The residual project is now scientifically resolved at c32: the valid local FP8 producer-plus-attention lower bound is `0.17950119981542229 s/request`, making W4 linears plus actual head plus local attention at least `0.6536132414387539`, above the `0.5479752315195353` H100 ceiling. The director therefore admitted one actual-consumer c48/c64/c96/c128 frontier, and its launching researcher spent `206.803` seconds implementing and starting a retained owner. H100 `computeinstance-e00hmt044zjv0vm3ed` then reached SSH in `94.619` seconds under an independent watchdog. The first `30.362`-second attachment consumed that new lifecycle evidence. The next cycle had no new controller event, stage, diagnostic, or GPU result, yet a `24.721`-second director turn and `31.537`-second researcher turn repeated the preserve decision—`56.258` orchestration seconds caused only by the prior attachment rewriting status/log text. During final verification the actionable primary terminal arrived: all actual consumers passed and rows were retrieved, but the wrapper rejected the new geometry with `expected exactly six unique shapes at M8/M16/M32/M3679`, a predecessor-cardinality integration defect rather than a GPU or W4 result. The controller opened its 600-second repair window at `22:21:04Z`; the owner and H100 remain live and untouched for the pinned Terra researcher. The 24-hour efficiency report independently classifies model orchestration as the primary bottleneck: `1.50` active coordinator hours, `97.5%` orchestration share, `351` tool calls, four scientific outcomes, and only `3.6` observed useful GPU seconds across `528.2` provider-active minutes.

**Change.** The shared harness now records an observation digest for each live `mode: development` session from stable owner identity plus actionable artifact metadata (`.json`, `.jsonl`, `.sha256`, and retrieved `.tar.gz`). After the first attachment, an unchanged active owner emits typed `researcher_deferred: unchanged_development_session` instead of launching another model turn. A new controller event, stage/repair JSON, digest, archive, owner identity, or terminal changes the observation and immediately reschedules the same pinned researcher/thread. Mutable `forward_progress` prose and streaming bootstrap/telemetry logs do not create wakeups. Batch-owner deferral, spend reservation, watchdog, deadline, trace capture, repair hold, and final cleanup are unchanged. A failing-then-passing regression proves an unchanged session is deferred and appending `repair_window_open` wakes it; all 98 factory tests, compilation, diff checks, and repository DevEx checks pass.

**Expected effect.** Healthy image/bootstrap intervals should consume no repeated director/researcher turns after the first ownership snapshot, while the newly arrived cardinality failure and future recoverable failures wake their original researcher on the next 60-second harness cycle, leaving roughly nine minutes of a 600-second repair hold for diagnosis, patch, and same-resource rerun. Judge this by `unchanged_development_session` deferrals during silent setup, the pinned Terra thread consuming this stage event, no duplicate H100 allocation, and an objective-valid c48/c64/c96/c128 terminal or typed scientific negative with authenticated cleanup—not by reduced activity alone.

## 2026-07-18 — resolve retained-owner artifacts from the owning project

**Bottleneck.** The objective-bearing constraint has moved to deterministic local construction of the first exact-revision W4 checkpoint for a complete H100 endpoint, not GPU availability, portfolio breadth, or generic process hygiene. The retained-development policy is already doing the right scientific work: ordinary materialization defects are being corrected by the same researcher in the same durable owner. One path-resolution defect in the new evidence-triggered scheduler could nevertheless delay that owner at its most actionable transition. The live project records `artifact_root: artifacts/w4-checkpoint-owner-20260717T223754Z`, but the harness interpreted relative roots from its repository working directory rather than from the project that owns the session. While the unit stayed active, a new checkpoint terminal or repair diagnostic under the real project artifact directory would therefore look unchanged and would not wake the retained researcher.

**Evidence.** The preceding H100 frontier validates both retention interventions. Its original c48/c64/c96/c128 primary rows were preserved after a stale wrapper-cardinality assertion, the pinned Terra researcher repaired and reran against the same H100, and all 24 W4/BF16 rows plus four actual `ParallelLMHead` rows passed. The resulting W4-plus-head floors were `0.132040`, `0.098819`, `0.073818`, and `0.057101` seconds/request at c48/c64/c96/c128; the owner cleaned after `864.598` provider seconds and derived `$0.518692361`. The current full-endpoint project then kept one local systemd unit, invocation, artifact root, source revision, image, and deadline through two recoverable checkpoint-writer layout errors; provider creation remains forbidden. At this review, repair-2's first shard had grown from the logged `3,764,035,727` bytes to `5,414,976,669` bytes, the same unit and PID were active, and no provider resource existed. A regression using that same project-relative artifact convention reproduced the missed wake: unchanged state deferred correctly, but appending `repair_window_open` did not schedule the researcher.

**Change.** The shared lab harness now resolves a relative development-session `artifact_root` against `row["path"]`, the owning project directory, before hashing actionable JSON, JSONL, digest, and archive metadata. Absolute roots keep their existing behavior. The focused regression now uses `artifacts/session`, fails on the old implementation, and passes after the change; all 98 factory tests, compilation, and diff checks pass. I did not modify the active project, materializer, unit, artifact stream, provider state, or scientific portfolio.

**Expected effect.** The local checkpoint owner may continue streaming unchanged safetensors bytes without repeated model turns, but its typed W4 terminal or repair diagnostic will wake the same retained researcher on the next harness cycle. That researcher can consume the gate and either continue to the one retained H100 endpoint or patch the existing local owner without a cold restart. Judge the change by one checkpoint-owner identity spanning any remaining repair, exactly one terminal reconciliation, provider creation only after a passing `W4_CHECKPOINT_TERMINAL.json`, and no duplicate materializer or GPU allocation—not by additional projects or static checks.

## 2026-07-18 — treat the admitted endpoint runner as implementation work

**Bottleneck.** The exact-revision W4 checkpoint gate has passed, so the objective-critical constraint is now implementation of the admitted c96/c128 complete-endpoint runner. This is neither an external blocker nor a reason for a preparation project: Stage B explicitly authorizes a narrow adapter on the proven retained H100 lifecycle. The execution researcher instead anchored on the absence of an already-wired project-local runner and returned that absence as a blocker, despite having authority and budget to implement it.

**Evidence.** The retained local owner completed after `1,932.449` seconds with all 1,188 source tensors accounted for, two content-hashed W4 shards totaling 19,188,358,069 bytes, finite/nontrivial samples, matching tokenizer metadata, and a passing pinned-image AWQ metadata load. The first post-terminal researcher turn usefully reconciled that result and cleared local ownership. Afterward, three execution turns consumed `22.851`, `9.688`, and `7.197` seconds and their director turns consumed `76.100`, `14.754`, and `13.004` seconds—`143.594` coordinator seconds in total—without a code change, durable endpoint owner, typed external failure, project-log update, or provider create. The latter two researcher traces ran no tools and merely repeated that a narrow endpoint adapter was missing. No lab experiment unit or project `active_session` existed at intervention time. The latest GPU evidence remains the preceding retained frontier: all 24 c48/c64/c96/c128 W4/BF16 rows and four actual-head rows passed on one H100, c128 left `0.490874320141839 s/request` under the planning ceiling, and authenticated cleanup completed after `864.598` provider seconds and `$0.518692361` derived spend.

**Change.** Made the current `STATUS.json` action more explicit in the shared researcher prompt: when that action needs a runner, adapter, or experiment script that is absent, implement the narrow in-scope version now and continue; missing project-local code is not a typed blocker. This sits beside the live scheduled action rather than adding another audit, validation artifact, or project. The existing researcher skill, retained-owner lifecycle, spend reservation, watchdog, repair window, cleanup semantics, and scientific contract are unchanged. A focused prompt regression failed before the change and passes after it; all 98 factory tests, compilation, and diff checks pass.

**Expected effect.** On the next cycle, the same project researcher should turn the already-passing checkpoint and proven lifecycle into an executable endpoint owner rather than repeat the missing-runner conclusion. The first real c96 invocation should occur inside one mutable retained H100 session, where ordinary load, API, request-harness, telemetry, or packaging defects can be patched and rerun against resident checkpoint and model state. Judge the intervention by a project-local endpoint adapter plus one durable owner snapshot or a genuinely typed external blocker, followed by complete-request rows per provider second—not by another readiness artifact, static check, or successor project.

## 2026-07-18 — retire an exhausted conversation, not the retained experiment

**Bottleneck.** The more explicit implementation prompt did not move Stage B because the persisted Terra conversation itself has exhausted its response capacity. This is a coordinator-thread terminal, not a scientific, provider, code, or project blocker. Continuing to resume that conversation cannot produce the admitted endpoint adapter and would keep the H100 lane idle indefinitely.

**Evidence.** After the previous harness reload, the director made the next action even more explicit: implement the missing endpoint runner now, launch one retained H100 owner, and treat absent code as routine implementation. The same researcher thread `019f7236-4d0c-75b2-bdee-bf376a5b1eb1` then returned four more times in `5.539`, `7.357`, `4.782`, and `4.630` seconds. The first promised implementation but immediately said it could not complete within the response; the next three ran no tools and each reported no remaining response capacity. Their four director turns consumed another `88.862` seconds, for `111.170` coordinator seconds with no adapter, project-log evidence, typed blocker, owner, or GPU create. `STATUS.json` still has no `active_session`, and the only running lab services at intervention time were the scheduler and notifier. The objective evidence is otherwise unchanged: the exact W4 checkpoint gate passes, while the preceding retained H100 frontier passed all component and head rows and cleaned after `864.598` provider seconds.

**Change.** The shared harness now reads the previous researcher trace before resuming a project. If the latest agent message explicitly reports `remaining response capacity`, it emits `researcher_thread_reset: response_capacity_exhausted`, discards only that unusable conversation ID, and starts a fresh conversation on the same pinned model route. Project identity, route, status, spend reservation, owner/resource identity, artifacts, watchdog, repair window, and cleanup contract are preserved. This is not a timeout heuristic and does not rotate healthy threads. A focused regression reproduces the explicit capacity terminal and proves the next call receives no stale thread ID while remaining on Terra; all 99 factory tests, compilation, and diff checks pass.

**Expected effect.** The next cycle should immediately give the admitted Stage B action a usable Terra context, allowing it to implement the narrow endpoint adapter and enter one retained H100 development owner. If a first-call integration defect occurs, that fresh project thread should remain attached to the same resident checkpoint/model session for patch and rerun; the GPU is not torn down or recreated by this change. Judge it by one `researcher_thread_reset` event followed by code or a durable owner snapshot, and then by complete c96/c128 endpoint rows per provider second—not by repeated capacity messages, another project, or more static validation.

## 2026-07-18 — preserve the corrected endpoint owner through its first request

**Bottleneck.** The exhausted-thread recovery worked, and the objective-critical constraint is now the actual full-endpoint path: finish staging the 19.22-GB exact-revision W4 proxy, load it on H100, and execute the first c96 FP8-KV request. Coordinator capacity, missing code, and portfolio selection are no longer limiting. A new supervisor change during healthy transfer would not shorten this path and could disrupt the only owner capable of producing the campaign's first complete W4 endpoint row.

**Evidence.** At `23:36:07Z` the harness emitted exactly one `researcher_thread_reset: response_capacity_exhausted` and kept the Terra route. The fresh thread then spent `394.192` seconds implementing `endpoint_runner.py`, `h100_endpoint_owner.py`, and `launch_owner.py`, and launched Stage B in the same project. The first owner exposed two ordinary local staging defects after provider create—a `Path` passed to `transfer_timeout_seconds` and a missing flat transfer manifest—but its repair hold was not yet inside the cleanup context, so it cleaned before attachment. That cold restart consumed `144.242` provider seconds and derived `$0.086631` with zero endpoint evidence. The same project researcher corrected the manifest and timeout and, crucially, placed the shared 600-second development window inside `VerifiedRetainedOwner` before launching the replacement; no repair or successor project was created.

The corrected durable unit `gemma-h100-w4-endpoint-20260717t23471784324846z.service` is active under PID `2240225` and invocation `1c6c51487ab646c38aa51af6cde0e369`. It owns H100 `computeinstance-e00xzv5h3g0znq5dpb`, disk `computedisk-e00gnnabbj82j9w604`, and an active independent cleanup watchdog. Its pre-create terminal passes ten files, 19,220,755,443 transfer bytes, and a 1,142-second bound. A scope-matched remote snapshot found 10,775,116,800 bytes already resident, no remote error, and no premature server process; the owner and watchdog remained active. The next harness cycle correctly emitted `unchanged_development_session` rather than another attachment. No complete-request GPU row exists yet; the latest scientific GPU result remains the prior all-pass c48-c128 W4/head frontier.

**Change.** No additional skill, shared-tool, harness, project, or provider mutation is warranted in this interval. I preserved the active owner unchanged. The project-local lifecycle correction already implements the required process improvement: any new exception now opens the bounded repair window before `VerifiedRetainedOwner` can clean, allowing the pinned Terra researcher to patch and rerun against the same resident H100 state. Spend deadline, trace capture, watchdog, and final authenticated cleanup remain intact.

**Expected effect.** Normal transfer and model load should proceed without coordinator turns. The next actionable artifact should wake the same Terra project route for either a c96/c128 endpoint terminal or an in-owner repair while the checkpoint, image, and H100 remain resident. Judge this disposition by one current resource identity spanning any first-call repair and final cleanup, plus complete-request service time against the `0.5479752315195353 s/request` ceiling—not by more supervisor edits, static validation, or project count.

## 2026-07-18 — reserve repair time before entering the remote program

**Bottleneck.** The corrected H100 owner completed checkpoint staging but then ran the entire image/load/request path as one opaque SSH command whose timeout extended through the absolute allocation deadline. When that command finally raised, the nominal 600-second development hold had only `0.107` seconds left. The owner therefore cleaned before any useful patch/rerun opportunity, and the campaign obtained no complete endpoint row. The constraint was remote execution geometry and observability, not Gemma W4 performance or GPU availability.

**Evidence.** The H100 terminal records `TimeoutExpired` after `4,081` seconds in `ssh ... bash -s`; no remote stdout, stderr, server log, result archive, or endpoint terminal was retrieved. Its events contain only `repair_window_open(maximum_seconds=0.107)` followed by expiration. Authenticated cleanup passed, but the two H100 attempts consumed `78.17` cumulative provider minutes and produced zero inference evidence. The director then selected a distinct H200 placement; I did not alter that portfolio decision. Its live owner improves the failed geometry materially: provider create, workspace, checkpoint transfer, image pull, launch, readiness, each concurrency arm, retrieval, and cleanup are separately observable, and its work bounds reserve 660–1,260 seconds before the absolute deadline. At final verification, H200 `computeinstance-e00r8ncgc1zyry8z6h` and its watchdog were active; all 19,220,755,443 checkpoint bytes transferred in `310.322` seconds, image pull and server launch completed, and telemetry started. No H200 endpoint row exists yet.

**Change.** Corrected the shared `mla_microbench_control` runtime geometry. A new `repairable_work_deadline` subtracts the configured 0–600-second repair window from the absolute owner deadline. Public-IP readiness, SSH readiness, host bootstrap, the deadline passed into the remote container, and the controlling SSH timeout now all use that earlier work deadline. A long remote program can no longer consume its own repair interval or extend another 180 seconds beyond the allocation deadline; when work times out, the existing owner-side development context still has the configured interval to accept a patch/rerun or explicit teardown before verified cleanup. This changes execution timing, not pre-create validation, scientific acceptance, spend authority, watchdogs, or cleanup. The live bespoke H200 process had already imported its code and was left untouched. A failing-then-passing regression covers the deadline subtraction; all 309 campaign controller tests, compilation, and diff checks pass.

**Expected effect.** Future shared retained-development owners with a 600-second repair window should surface a timeout while roughly ten minutes of resource life remain, allowing the same researcher to inspect the real traceback/logs and rerun against resident image/checkpoint/GPU state instead of buying another cold allocation. The currently active H200 owner should continue through its already-phased program; its next JSONL phase transition will wake the pinned Terra route without polling. Judge the shared change by nonzero repair-window duration after remote timeouts, one resource identity across recoverable reruns, and more complete endpoint rows per provider minute—not by additional audits or projects.

## 2026-07-18 — retain the corrected H200 owner through readiness diagnosis

**Bottleneck.** The first H200 allocation reached the exact W4 server launch but converted a recoverable readiness-observability defect into another cold teardown. It therefore measured neither the campaign's `0.472101737924523 s/request` H200 endpoint ceiling nor a Gemma runtime limitation. The objective-critical path remains one valid c128 or c96 complete-request row; another process gate, project, or supervisor edit cannot substitute for that row.

**Evidence.** The first owner transferred all `19,220,755,443` checkpoint bytes in `310.322` seconds, pulled the pinned image, launched the server, and started telemetry. It then spent about `1,206` seconds in readiness before a `readiness_logs` phase returned two empty local streams: `docker logs` had been redirected to an uncollected remote file. The owner had also omitted the promised `retained_development_window`. When the actionable event woke the pinned Terra researcher, direct attachment first hit the changing provider address record and then `ResourceNotFound`; verified cleanup had already deleted H200 `computeinstance-e00r8ncgc1zyry8z6h`. That allocation consumed `1,846.914` provider seconds and `$1.261915171` with no c128/c96 row, GPU telemetry artifact, throughput result, or economic inference.

The same project and execution researcher corrected the actual lifecycle rather than opening a successor: container log/state/exit/OOM/GPU diagnostics are now copied locally, the 600-second development context is nested inside `VerifiedRetainedOwner`, and long work stops 660–1,260 seconds before the absolute deadline. Corrected unit `gemma-h200-w4-endpoint-20260718t01551784332506z.service`, PID `2266140`, invocation `957deafd72f541a0a819fe1e40ae14cc`, and its independent watchdog are active. At final observation it owned new H200 `computeinstance-e00swbc4133rnvn1sc`, had completed workspace setup, and was transferring the existing checkpoint. No endpoint row exists yet.

**Change.** I made no additional skill, shared-tool, harness, project, or provider mutation. The warranted process correction is already executing in the same scientific project: a real mutable retained owner with retrievable live diagnostics. I left it untouched. Its local regression is only launch evidence; it is not research progress and is not the answer to the failure mode.

**Expected effect.** If server readiness or the first c128 call fails again, the failure should emit an actionable diagnostic and open a nonzero repair window before cleanup, waking the same Terra route while the checkpoint, image, server state, and H200 remain resident. The researcher can then patch and rerun in place or explicitly request teardown. Judge the correction by one current instance identity spanning any repair, retrieved server/GPU evidence, and a typed c128/c96 endpoint result before authenticated cleanup—not by the regression pass, new project count, or generic activity.

## 2026-07-18 — lease a progressing repair to the absolute watchdog

**Bottleneck.** Retained development has become scientifically useful, but its owner-side hold still expires after a fixed 600 seconds even when the same researcher has begun a safe repair whose measured duration is longer. That converts an absolute spend watchdog into a second, premature cleanup deadline. The resulting workarounds—manual process suspension or racing model load—are now the immediate constraint on reaching a complete Gemma endpoint row.

**Evidence.** The corrected W4 H200 opened its repair window at `02:27:28Z` and expired it exactly 600 seconds later. During that one retained interval, the pinned Terra researcher spent `395.000` seconds diagnosing and correcting four ordinary integration faults on H200 `computeinstance-e00swbc4133rnvn1sc`: deleted failed-container state, `fp8_e4m3fn` versus `fp8_e4m3`, duplicated image entrypoint, and AWQ `bfloat16` versus `float16`. The same image and checkpoint then resolved Gemma4, initialized FP8 KV, loaded both shards, and reported `18.41 GiB` model memory. The timer nevertheless released verified cleanup before readiness or c128. The project closed after `4,419.201` provider seconds and `$3.019446090` with zero endpoint rows; the final GPU outcome is model-load compatibility only.

The active SGLang H200 exposes the same geometry more starkly. Its original checkpoint `scp` returned 255 because it omitted the established host-key options. The same researcher attached to the existing writable workspace; an authenticated retry made sustained progress but died with a partial `13.2-GB` shard. The full bound payload is `62.58 GB` and the observed transfer rate was about `58 MB/s`, so a healthy retry cannot fit in 600 seconds. To avoid another cold allocation, the researcher had to put only owner PID `2280803` into `SIGSTOP` while H200 `computeinstance-e00mcm2qt1zmxsgxgh`, its disk, independent watchdog, and a durable replacement transfer remain active. This preserves the experiment but makes the controller unresponsive and is not a reusable retained-session protocol. No SGLang GPU science exists yet.

**Change.** Extended the shared `mla_microbench_control` repair protocol with an explicit owner lease. While the initial repair window remains capped at 600 seconds, the owning researcher may write `repair-decision.json` with `action: retain` and an `until_epoch` no later than the already-authorized absolute deadline. The live owner consumes that decision, emits `repair_retention_extended`, and remains responsive while the researcher patches or reruns against resident state. `action: teardown`, the default zero-window batch behavior, the absolute watchdog, spend deadline, verified cleanup, and scientific acceptance are unchanged. The currently active SGLang process had already imported the old helper and was left untouched. A focused regression failed on the old repeated-decision/expiry behavior and now proves one consumed lease extends retention only to the requested in-budget epoch; all 20 controller tests and compilation pass.

**Expected effect.** A long but progressing checkpoint retry, image correction, model load, or first-call repair can now remain under the original responsive owner until the absolute watchdog rather than requiring `SIGSTOP` or a replacement allocation. The same researcher can preserve checkpoint/image/GPU state, finish the corrected command, retrieve evidence, and then request teardown. Judge the change by `repair_retention_extended` followed by a rerun on one resource identity, fewer pre-science cold allocations, and more complete endpoint rows per provider minute—not by longer holds themselves. Repairs without measured forward progress should still expire or tear down.

## 2026-07-18 — let the absolute watchdog finish provider cleanup

**Bottleneck.** The retained-session repair no longer causes an immediate cold restart, but its independent cleanup fallback did not produce a verified deadline terminal. The watchdog began deletion at the authorized deadline while the main owner was paused, then systemd killed the watchdog's provider command before it could finish and record an outcome. Provider absence was not authenticated until much later, forcing conservative exposure accounting far beyond the project limit. Reliable deadline cleanup—not scientific direction or another validation gate—is the measured constraint.

**Evidence.** SGLang H200 `computeinstance-e00mcm2qt1zmxsgxgh` was created at `02:52:19Z` with an absolute deadline of `04:11:30Z`. Its owner was deliberately `SIGSTOP`-paused to retain a progressing checkpoint repair, so the independent watchdog was the only deadline enforcer. The system journal records `RuntimeMaxSec` at `04:12:30Z`, exactly 60 seconds after the deadline, followed by systemd killing the watchdog's live `nebius` subprocess with `SIGKILL` and marking the service timed out. The owner did not resume into authenticated cleanup until `06:05:13Z`. With no durable watchdog terminal establishing the actual provider deletion time, the project conservatively records `11,621.894` exposure seconds (`193.698` minutes) and about `$7.909344264` compute before disk against an 80-minute/`$3.75` limit. Zero image load, model load, endpoint request, GPU telemetry bundle, or economic evidence exists.

The source explains the timing. `start_independent_watchdog` allowed runtime only through deadline plus 60 seconds, while `placement_control.watchdog` may legitimately need a 120-second instance-delete call, up to 180 seconds waiting for absence, and additional disk listing/deletion time. The main owner's later cleanup passed in `1.118` seconds because provider state was eventually absent, but it cannot recover the missing deletion timestamp or endpoint opportunity. The currently active lease-enabled W4 owner is healthy: it transferred all `19,220,755,443` checkpoint bytes in `347.325` seconds, pulled the exact image, launched the corrected server, and started telemetry on H200 `computeinstance-e00cbyv3mdazv0cbje`; no readiness failure or endpoint row exists yet.

**Change.** Increased the shared Nebius watchdog service's post-deadline runtime reserve from 60 to 600 seconds. The scientific/spend deadline at which `placement_control.watchdog` starts deletion is unchanged; the extra service lifetime exists only so the already-triggered instance-absence and disk-cleanup path can finish instead of being killed mid-command. Owner cleanup, repair leases, provider identity, and acceptance logic are unchanged. The live W4 watchdog had already been launched from the old bytes and was not restarted or reconfigured. A focused regression failed with `RuntimeMaxSec=1060s` for a 1,000-second remaining owner and now passes with `1600s`; the existing user/system service-manager tests also pass.

**Expected effect.** A crashed, suspended, or unresponsive retained owner should no longer turn its absolute deadline into an open-ended provider charge merely because deletion takes more than one minute. Judge the change by watchdog services completing rather than timing out, named instances/disks disappearing close to the deadline, provider exposure staying within the authorized owner window plus bounded cleanup latency, and more budget remaining for objective-valid endpoint rows—not by additional watchdog checks or shorter scientific sessions.

## 2026-07-18 — retry the repaired operation instead of the original exception

**Bottleneck.** Resource retention is now working, but retained control flow still cannot resume the failed scientific operation. The latest exact W4 H200 owner preserved its checkpoint, image, server, and GPU while the same researcher repaired the integration path; the controller nevertheless remained parked in the first readiness exception until the lease expired, re-raised that stale exception, and cleaned the repaired live session. This is the immediate process loss between a successful in-place repair and the objective's required complete c128/c96 request—not model performance, another project opportunity, or missing static validation.

**Evidence.** The lease-enabled owner transferred all `19,220,755,443` checkpoint bytes, then recorded an ordinary startup-profile failure: `max_num_batched_tokens=524288` drove a 21.00-GiB dummy allocation with only 16.81 GiB free. At `06:42:05Z`, the owner consumed a preseeded retain decision and emitted `repair_retention_extended` through epoch `1784358702.7530787`. The same pinned Terra researcher used that owner to lower the bound to `8192`, reach `/v1/models`, replace unavailable runner dependencies and the Gemma4 nested-vocabulary lookup, and launch the repaired c128 consumer as remote PID `23586`. Yet the original owner had no retry/resume branch: at `07:11:45Z` it emitted `repair_window_expired`, re-raised its original readiness failure, and entered cleanup. Authenticated cleanup passed in 51.171 seconds, but no c128/c96 row was retrieved; the project closed after `8069.200642` cumulative provider seconds and about `$5.513331098` derived spend. The current checkpoint-free H200 component project was scientifically distinct and directly tested price-normalized c96/c128 W4-plus-head hurdles. I did not signal, reload, or mutate its already-imported process. During verification it independently retrieved passing primary and conditional terminals and authenticated zero-resource cleanup after 600.841 provider seconds and `$0.410528435`. Its measured combined c128 component time is `0.05696907804079819 s/request` versus the `0.049194631328675076` hurdle, and c96 is `0.0743674577451311` versus `0.06359729426941725`; both miss the project thresholds. That scientific terminal is for the project researcher/director to reconcile and does not change the process diagnosis from the preceding endpoint loss.

**Change.** Added an explicit reusable `run_repairable_operation` path to the shared Nebius microbenchmark controller and wired both primary and conditional remote stages through it. During a retained failure, `repair-decision.json` may now carry `action: retry`; the owner consumes the decision, emits `repair_retry_started`, and calls the same operation again in the same Python process and verified provider owner. The first attempt still stops at the earlier work deadline to reserve repair time, while a requested repaired attempt may use the remaining absolute watchdog lease. Teardown, lease extension, zero-window batch behavior, typed artifact retrieval, spend deadline, watchdog, and authenticated cleanup remain unchanged. Failures outside a retryable stage fail closed and emit `repair_retry_unavailable` rather than pretending a context manager can resume an unwound block. A behavioral regression fails before the change and now proves one recoverable exception becomes attempt 2 on the same owner and consumes the retry decision. All 312 campaign controller tests, compilation, repository DevEx, and diff checks pass.

**Expected effect.** Future shared retained-development owners can convert a patched import, runtime-context, remote-wrapper, telemetry, or artifact-integration defect directly into another scientific stage attempt without cold provider create, checkpoint transfer, image pull, or model initialization. Judge the change by `repair_retry_started` followed by a retrieved typed terminal under one resource identity and cleanup record, and by complete objective-valid rows per provider minute—not by longer idle retention, new projects, or additional preflight checks. The H200 component owner loaded the prior module bytes and completed without needing repair; this intervention applies to subsequent owner processes only.

## 2026-07-18 — make mutable retry a call, not an import

**Bottleneck.** The shared retry primitive exists and retained-resource repair is producing objective-valid science, but the next execution owner treated the outer retention context as if it were resumable control flow. A Python context manager can delay cleanup after an exception, but it cannot return execution to a transfer, launch, readiness, request, or retrieval call whose block has already unwound. The immediate process constraint is therefore correct adoption of the mutable operation boundary—not coordinator cadence, another scientific project, or another static gate.

**Evidence.** The reactivated H100 W4 endpoint validates the retained-session policy: the same H100, staged checkpoint, image, and server survived an obsolete Machete import and a missing host `transformers` dependency; the pinned Terra researcher repaired both in place and retrieved valid c128 and c96 terminals before authenticated zero-resource cleanup. Those rows closed the line scientifically at `1.6419997604140635` and `1.8852607194687512 s/request`, but the original controller remained parked behind its stale Machete exception and its failure classification had to be manually superseded during reconciliation. The newly active SGLang v0.5.12 stock/MTP project explicitly requires `run_repairable_operation`. Its owner imports that helper but never calls it: the sole outer `retained_development_window` surrounds direct checkpoint transfer, image/telemetry stages, stock launch/readiness/request/retrieval, and MTP launch/readiness/request/retrieval. A first ordinary exception would therefore retain state briefly, emit `repair_retry_unavailable` for an explicit retry decision, re-raise, and clean instead of re-entering the corrected operation. This is an implementation/adoption gap, not a current failure. At inspection, owner PID `2352896`, its watchdog, H200 `computeinstance-e00v1y11h92cdp0y9b`, and the authenticated `scp` child were all live; workspace and assistant transfer had passed and the 62.58-GB target transfer was progressing. I did not signal, reload, patch, or attach to that already-imported owner. Since the preceding supervisor turn, 18 director and 10 researcher deferrals across 24 completed cycles also show that event-driven waiting is working and is not the current constraint.

**Change.** Clarified the shared researcher execution skill at the exact retained-development boundary. It now states that the outer context only delays cleanup, that merely importing the helper does not make an owner retryable, and that each patchable remote transfer, launch/readiness, request, and artifact-retrieval operation must actually be called through `run_repairable_operation`; provider creation and final cleanup stay outside the loop. It also names `repair_retry_unavailable` as evidence that the owner was not wired for mutable continuation. This adds no validation phase, project, provider action, deadline extension, or active-owner mutation.

**Expected effect.** The next owner generated by an execution researcher should turn an explicit `action: retry` into a second call on the same instance after an ordinary patch, rather than sleeping over resident state and later rethrowing the first exception. Judge the change by `repair_retry_started`, a repeated operation under one owner/resource identity, and a typed scientific terminal plus authenticated cleanup. Do not judge it by imports, pre-create checks, documentation volume, or project count. The current SGLang owner continues under its original loaded bytes and must be preserved through its normal stock/MTP terminal or researcher-led in-place repair.

## 2026-07-18 — fence an expired, already-cleaned warm-bench record

**Bottleneck.** The new shared GPU pool converted an expired, already-cleaned H200 lifecycle back into an `available` bench. This is not idle provider spend—the provider resource is gone—but it makes a nonexistent bench claimable and would route the next compatible researcher into dead instance/disk identities instead of objective-valid Gemma work. The warm-session policy itself remains useful: the quality owner repaired checkpoint transport and the BF16 control on one H200. The defect is the release transition after the director-owned lifecycle deadline, not retained development or the scientific portfolio.

**Evidence.** The one-shot authenticated Nebius listing returned zero instances and zero disks. Inventory bench `h200-quality-e00rttap31wr3bzk96` nevertheless had `status: available` and exact resource IDs `computeinstance-e00rttap31wr3bzk96` and `computedisk-e00e9eam9z5809azn5`; its own contents said authenticated cleanup removed the resource, checkpoint, image, and server. Recorded owner `gemma-h200-paired-quality-20260718t10321784363555z.service` and watchdog `gemma-h200-paired-quality-20260718t10321784363555z-watchdog.service` are both absent/inactive with PID zero. The lifecycle deadline was `2026-07-18T11:42:35Z`, while `gpu_events.jsonl` records `bench_released` as `available` at `11:42:52.465309Z`, 17.465 seconds after expiry. The claim was otherwise healthy: registered/claimed at `11:18:18Z`, heartbeated at `11:27:51Z`, updated at `11:28:17Z`, and released with no stale claim. During that claim, a fixed 180-second SCP timeout left 11.89 GB on the resident disk; the same owner retained the H200, completed transfer through a helper, consumed actual retry attempt three, repaired the BF16 HTTP-400 fixture in place, and reached the paired-quality terminal. Scientifically, stock SGLang remains a market pass at `0.3633031778 s/request` versus `0.4720118230`, but quality is quarantined because the BF16 executable Python control failed; the FP8 concurrency project is correctly paused. No compatible queued work justifies representing the destroyed bench as reusable.

**Change.** Marked bench `h200-quality-e00rttap31wr3bzk96` `draining` through the atomic pool interface. I did not perform provider cleanup or retire the inventory record; the director should verify the already-empty provider listing and retire this exact instance/disk record. Hardened the shared pool so a claim released at or after its lifecycle deadline becomes `draining`, records `lifecycle_deadline_passed: true`, clears idle availability, and cannot be made ready again under the expired deadline. A focused regression failed with the prior `available` transition and now passes; all seven GPU-pool tests pass.

**Expected effect.** Expired or watchdog-ended benches can no longer re-enter the claim queue between researcher release and director reconciliation. The next director turn should see the draining record and exact resource IDs, confirm Nebius remains empty once, and retire the record without cleanup work. Future compatible projects should reuse resident state only while the provider resource, lifecycle owner, watchdog, and unexpired deadline all remain real; otherwise they receive no false bench claim and can make an explicit portfolio/allocation decision. Judge the change by zero claims against absent provider IDs and by warm reuse that actually spans multiple projects before cleanup—not by inventory event count.

## 2026-07-18 — decouple warm GPUs from research projects

**Bottleneck.** The successful SGLang/H200 c32 measurement spent about 49 minutes transferring the checkpoint, pulling the image, and reaching readiness for 11.6 seconds of scored work. Project-owned lifecycle then cleaned the H200 after the MTP image incompatibility, discarding state that could have supported the next repair or experiment. Setup and teardown ownership, not GPU execution time, dominated experiment cadence.

**Change.** Added one atomic lab-level GPU inventory and lease tool at `runtime/gpus.json` plus `runtime/gpu_events.jsonl`. The director now owns provider create, watchdog/deadline, drain, cleanup, and retire. Researchers claim compatible benches, heartbeat, patch and measure, update the resident model/checkpoint/image/runtime/cache/server description, and release without teardown. Claims are exclusive and idempotent; expired claims remain fenced until the director explicitly reclaims them to maintenance. No daemon, database, provider abstraction, automatic teardown policy, or additional experiment gate was added. The role skills, harness prompts/status, factory README, and Sol instructions now use this boundary.

**Evidence and expected effect.** Concurrency, stale-lease, resident-state preservation, drain, and verified-retire tests pass. After the harness reloaded at a cycle boundary, the live director immediately registered H200 `h200-quality-e00rttap31wr3bzk96` with its Nebius resource, `$2.46/hour` rate, watchdog/deadline, exact Gemma checkpoint and SGLang state; `sglang_v0512_h200_stock_quality_validation` then claimed it atomically. Future compatible experiments should pay checkpoint/image/model setup once per bench rather than once per project. Judge the change by useful GPU seconds per provider-active minute, experiments per model load, warm claim handoffs, and fewer cold allocations—not inventory activity itself.

## 2026-07-18 — audit provider GPUs independently of director activity

**Bottleneck and evidence.** The periodic supervisor was skipped whenever the director deferred on unchanged durable work. That is the most likely interval for a dead owner, failed watchdog, stale claim, or provider resource missing from the shared inventory to leak spend unnoticed. The live lab is configured for one supervisor turn every four one-minute cycles. At implementation time its sole Nebius H200, disk, owner PID, watchdog PID, fresh claim, and inventory record all agreed; no current orphan was found.

**Change and expected effect.** Supervisor cadence is now independent of director deferral. Each periodic turn begins with one grouped provider-versus-inventory safety audit, checks lifecycle owners/watchdogs, claims, deadlines, and unjustified idle benches, and returns without logging when healthy. It fences an objectively expired, unsafe, or ownerless registered bench as draining but leaves provider deletion and retirement to the director. Supervisor-log identity is now part of the director's material observation, so an exact orphan handoff wakes cleanup on the next cycle. This adds no experiment gate, polling daemon, provider abstraction, or healthy-audit paperwork. All 107 factory tests, skill validation, compilation, DevEx, and diff checks pass.

## 2026-07-18 — retain warm benches beyond one project budget

**Bottleneck.** Shared ownership allowed in-place repair, but the prior H200 was still destroyed at a project-sized watchdog deadline after roughly 50 minutes of paid setup. The next compatible project therefore inherited no checkpoint, image, cache, or server state. The new safe-code H200 repeated that risk with an initial `13:38:48Z` deadline even though cold setup dominates scored work and compatible follow-ups are plausible.

**Change.** Made retention the default judgment in the director, researcher, supervisor, and harness prompts: size bench lifetime for a short portfolio itinerary, compare idle cost with cold-setup cost and lost time, and require a positive reason to destroy a healthy bench. Added a tested atomic `gpu_pool replace-watchdog` operation so the director can extend a live bench without recreating it. For current bench `h200-safe-code-e00b98a5fh80nwj2jj`, launched and verified replacement watchdog `gemma-safe-code-h200-retained-20260718t1225z-watchdog.service`, atomically moved the deadline to `16:00:00Z`, then stopped and verified the old watchdog inactive. The claimed quality owner and checkpoint transfer remained live. Reserved an additional `$6` under the existing `$100` cap; total reservations are `$42.65`.

**Expected effect.** The current paid setup can feed the quality run and later compatible experiments instead of ending at the first project terminal. Judge this by a released warm bench being claimed by another project, experiments per checkpoint transfer/model load, and follow-up setup measured in minutes rather than another cold allocation. Teardown remains mandatory for exhausted authority, unsafe state, required hardware/environment replacement, or no plausible reuse within the measured cold-setup break-even window.

## 2026-07-18 — preserve released state through portfolio selection

**Bottleneck.** The retained safe-code H200 repaired bootstrap and scoring failures in place and produced a decision-bearing negative quality terminal after `2872.206` provider seconds and `$1.962674` derived compute. It released at `12:57:24Z` with the exact checkpoint, image, and caches resident, but the director drained it at `13:00:21Z` and retired it at `13:01:54Z` while the campaign remained open and before the next portfolio selection completed. The momentarily empty queue was treated as proof of no likely reuse, so cross-project warm handoff again did not occur.

**Change and expected effect.** Clarified the director, supervisor, and harness prompts without adding a timer or gate: when a campaign remains open, keep newly released reusable state through the next portfolio selection, choose the next experiment and hardware first, and only then drain if the selected work cannot reuse it. This preserves judgment and spend limits while preventing a few minutes of portfolio latency from discarding a 20m42s checkpoint transfer and 5m10s image pull. Judge the next compatible terminal by an actual second project claim before teardown.

## 2026-07-18 — wake the retained researcher on a live launch failure

**Bottleneck.** The objective-critical generation-equivalence discriminator reached the exact H200 runtime but its project session was classified as opaque batch work. The harness therefore deferred the researcher solely because the durable owner service remained active, even after the child container had exited. A recoverable launch parameter error was spending the full readiness timeout instead of entering the existing mutable repair path.

**Evidence.** The one-shot Nebius audit exactly matched claimed bench `h200-generation-equivalence-e00ms57nn1c4k1cx0k` to instance `computeinstance-e00ms57nn1c4k1cx0k` and disk `computedisk-e00z6arpjjmr7vpetr`; its owner and watchdog were active, the claim lease runs through `14:20:58Z`, and the lifecycle deadline is `15:45:42Z`. The exact 62.58-GB checkpoint and pinned SGLang image are resident. Container `gemma-generation-equivalence` loaded 59.61 GB of BF16 weights, then exited normally at `13:48:15Z` with `RuntimeError: Not enough memory. Please try to increase --mem-fraction-static`; the launch used `0.06`. The owner remained in a 90-by-8-second HTTP loop while harness cycles emitted `researcher_deferred: durable_session_active`. GPU memory was back to zero, so this is an ordinary in-place launch correction, not a scientific result or unsafe bench.

**Change.** Marked only this project's existing `active_session` as `mode: development`, bound it to the current bench ID, and refreshed its operational next action. This uses the harness's already-tested artifact-change wakeup and mutable-session prompt; it does not alter the running owner, provider resources, checkpoint, image, watchdog, spend deadline, scientific question, or portfolio. No validation project or replacement allocation was added.

**Expected effect.** The next harness cycle should invoke the same project researcher while the bench is still resident. It can inspect the captured error once, raise the static-memory fraction, and rerun the server and five-case discriminator on `computeinstance-e00ms57nn1c4k1cx0k` without another checkpoint transfer or image pull. Judge the intervention by a repaired launch and typed Transformers/SGLang terminal under the same resource IDs, not by another cold setup or readiness artifact.

## 2026-07-18 — resume the failed operation, not the whole setup script

**Bottleneck.** The mutable-session wakeup succeeded, but the replacement controller interpreted “rerun in place” as replaying its monolithic script from line one. It retained the H200 yet retransferred the entire exact checkpoint instead of resuming at the failed server launch. Transport, not the generation-equivalence discriminator, again dominates the campaign's remaining decision time.

**Evidence.** The one-shot Nebius audit still exactly matches claimed bench `h200-generation-equivalence-e00ms57nn1c4k1cx0k` to instance `computeinstance-e00ms57nn1c4k1cx0k` and disk `computedisk-e00z6arpjjmr7vpetr`; the claim was heartbeated at `14:03:55Z`, its lease runs through `15:03:55Z`, and watchdog `gemma-generation-equivalence-h200-20260718t131542z-watchdog.service` remains active through `15:45:42Z`. The previous server had already read the resident checkpoint and loaded 59.61 GB of weights, proving the remote files usable, and the exact image was present. The same researcher correctly changed only `--mem-fraction-static 0.06` to `0.85`, but replacement owner `gemma-generation-equivalence-execution-20260718t1350z.service` then started `tar -C ... checkpoint -cf - . | ssh ... tar -xf -` at `14:00:39Z`; that 62.58-GB replay was still active more than six minutes later. The first cold transfer had already cost about 20 minutes before image and load, while the scored five-case question still has no GPU result.

**Change.** Tightened the shared harness's development-session prompt at the existing shared-bench attachment boundary. It now requires a replacement controller to resume at the failed operation, inspect resident identity once, and skip settled host bootstrap, checkpoint transfer, image pull, and model preparation unless evidence invalidates that state. Provider creation and final cleanup remain outside researcher ownership. The active owner, transfer, resource, claim, watchdog, deadline, scientific scope, and portfolio were not signaled or modified. A focused prompt regression failed before the change and now passes; all 26 harness tests, Python compilation, and diff checks pass.

**Expected effect.** Future recoverable launch, request, telemetry, or retrieval defects should restart only the invalidated operation on the same remote workspace, turning a repair into minutes of server/request work rather than another tens-of-minutes checkpoint transfer. Judge the change by one checkpoint transfer per unchanged storage identity and a typed scientific terminal under the same instance/disk IDs—not merely by retaining the provider allocation or launching another controller.

## 2026-07-18 — make a changed repair action wake its researcher

**Bottleneck.** The director correctly redirected the retained project from full setup replay to failed-operation resume, but the harness treated the development session as unchanged and never delivered that new action to the researcher. The development observation tracked active-session metadata and artifacts but omitted `STATUS.json.next_action`, so coordination stalled while the redundant 62.58-GB transfer kept running.

**Evidence.** The one-shot Nebius audit exactly matches the claimed H200 to instance `computeinstance-e00ms57nn1c4k1cx0k` and disk `computedisk-e00z6arpjjmr7vpetr`; the claim lease remains valid through `15:03:55Z`, the lifecycle watchdog is active through `15:45:42Z`, and there is no idle or orphaned provider resource. At `14:11:44Z` the director changed the project's next action to stop the redundant transfer, validate resident identity once, and resume the corrected `0.85` launch. Cycles at `14:12:44Z`, `14:13:45Z`, and `14:14:45Z` nevertheless emitted `researcher_deferred: unchanged_development_session` with the same observation hash and ran no researcher. At `14:15:09Z` owner `gemma-generation-equivalence-execution-20260718t1350z.service` was still active in the same local `tar | ssh tar` process after more than 14 minutes, with no generation-equivalence GPU terminal.

**Change.** Added the scheduled `next_action` to the harness's development-session observation identity. An unchanged owner and artifact stream still defer normally, but a director-issued repair action now creates one material observation change and schedules the same pinned researcher. No provider state, claim, owner, watchdog, deadline, project scope, or active process was mutated. A focused regression reproduces an unchanged retained session, changes only `next_action`, and proves the next researcher prompt contains the new action; all 27 harness tests, Python compilation, and diff checks pass.

**Expected effect.** After the harness reloads at its cycle boundary, the new repair action should reach the same researcher on the next cycle instead of waiting for an unrelated artifact. The researcher can stop the redundant transfer within its claim and resume from resident checkpoint validation and corrected server launch, preserving the same instance and disk. Judge the change by one researcher wake per material action change and a subsequent typed discriminator result—not by more director turns or owner restarts.

## 2026-07-18 — fence a released bench when its watchdog deadline passes

**Bottleneck.** A healthy warm H200 was released shortly before its lifecycle deadline and successfully reused by a second project, but after the watchdog cleaned the provider resources the inventory still described the nonexistent bench as `available`. Claims already reject expired deadlines, so this did not launch work against dead hardware; the stale state nevertheless obscures cleanup reconciliation and advertises resident state that no longer exists.

**Evidence.** The one-shot authenticated Nebius listing at `15:49Z` returned zero instances and zero disks. Inventory bench `h200-generation-equivalence-e00ms57nn1c4k1cx0k` remained `available`, with exact resource IDs `computeinstance-e00ms57nn1c4k1cx0k` and `computedisk-e00z6arpjjmr7vpetr`, while deadline `2026-07-18T15:45:42.393928Z` had passed and watchdog `gemma-generation-equivalence-h200-20260718t131542z-watchdog.service` was absent/inactive. The bench had been released ready at `15:42:44Z`, 178 seconds before deadline. Retention was scientifically productive before cleanup: generation-equivalence released it at `15:29:59Z`, `gemma4_h200_critical_path_profile` claimed the same bench at `15:32:48Z` without checkpoint transfer, and measured exact cache-flushed c16/c32 serving through `15:42:44Z`; c32 delivered `0.775796 s/request`, while the prior `0.363303 s/request` comparator was reclassified as a fully cache-read lower bound. The remaining precision project correctly declined the final 178-second window as too short for safe execution.

**Change.** Marked bench `h200-generation-equivalence-e00ms57nn1c4k1cx0k` draining through the atomic pool interface. I did not perform provider cleanup or retire the record; the director should reconcile and retire the exact absent instance/disk IDs above. Hardened `GpuPool.snapshot()` so any unclaimed `available` or `maintenance` bench whose lifecycle deadline has passed is atomically moved to `draining`, clears `idle_since`, and emits `bench_lifecycle_expired`. This covers watchdog cleanup after a pre-deadline release; the earlier release-time fence covers releases that occur after deadline. A focused regression failed before the change and now passes; all nine GPU-pool tests, Python compilation, and diff checks pass.

**Expected effect.** The first ordinary director or pool snapshot after a watchdog deadline will fence expired unclaimed state without waiting for a provider-specific supervisor audit, while leaving provider deletion and retirement director-owned. The next director turn should retire `computeinstance-e00ms57nn1c4k1cx0k` / `computedisk-e00z6arpjjmr7vpetr` after confirming the already-empty provider state, then decide whether the prepared H200 FP8 exact-shape falsifier merits a new authorized bench. Judge the fix by zero expired benches represented as reusable and by continued cross-project claims before—not after—their real watchdog deadlines.

## 2026-07-18 — snapshot cross-project bound inputs before a GPU claim

**Bottleneck.** A mutable cross-project input race consumed a paid warm-H200 claim without invoking the admitted exact workload. Retaining the server made recovery cheap, but resolving a hash-bound runner from another project's live path after claiming the bench can repeat the same waste whenever compatible projects overlap.

**Evidence.** The first `gemma4_h200_triton_kv_split_endpoint` owner claimed `h200-attention-endpoint-e00vbbb709tzxscaan` from `20:17:29Z` to `20:21:45Z` and observed runner SHA-256 `235f5de7a5ae66aa9732742c2fef65e49fe13bffcfae5299823c5c1e9837622d` instead of admitted `143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7`. It correctly invoked zero requests and conservatively recorded `$0.17` exposure. The canonical path was restored, and the same healthy split-4 server was retained. A project-local immutable snapshot then let the repair claim run exactly one 32-row consumer from `20:25:45Z` to `20:28:17Z`; it produced a valid negative result at `0.934844753 s/request`, 1.6735% slower than the frozen control. The one-shot Nebius audit at `20:28:38Z` exactly matched live instance `computeinstance-e00vbbb709tzxscaan` and disk `computedisk-e00y9hv4e79xdh2g7b` to the available inventory bench, with its watchdog active through `20:55:00Z` and no stale claim or unsafe state.

**Change.** Tightened the existing researcher harness prompt: when a GPU invocation consumes a hash-bound file from another project or shared mutable path, materialize the admitted bytes under the consuming project before claiming the bench and transfer that immutable snapshot without resolving the shared path again. This changes sequencing, not the experiment gate, project portfolio, or active provider lifecycle. The focused prompt regression and Python compilation pass.

**Expected effect.** Cross-project reuse should preserve exact admitted bytes without spending a claim on a transient shared-path revision. Judge the change by zero future `runner_invoked: false` terminals caused by shared input mutation, fewer repair claims, and unchanged ability to patch and rerun ordinary remote defects against resident model/server state.

## 2026-07-18 — keep pre-invocation wiring repair inside the claimed session

**Bottleneck.** Ordinary integration defects that occurred before the first scientific invocation were repeatedly classified as project terminals. The provider allocation stayed warm, but each correction still required release, a director override, and a second researcher/claim instead of letting the same researcher repair the invalidated operation against resident state.

**Evidence.** The pinned vLLM arm rejected obsolete `--enable-metrics`, released at `19:20:31Z`, and needed a director/researcher cycle before the same bench reran at `19:26:12Z`. The split-4 arm stopped on a transient runner identity before any request, released at `20:21:45Z`, and resumed from the same loaded server only at `20:25:45Z`. Most recently, the 32,768-token prefill candidate proved a healthy loaded server, 170,792-token pool, zero queue, and HTTP-200 flush, but a lexical numeric guard rejected that sufficient capacity before the runner; it released at `20:57:26Z`, then a director override and consumer-only repair reclaimed at `21:01:04Z` and produced a valid negative result. By contrast, `gemma4_global_head_dim256_backend_unlock` repaired its discovery helper and page-index dtype inside one `21:15:31Z`-`21:30:31Z` claim before reaching the decision-bearing XQA CUDA fault. The one-shot Nebius audit at `21:34:39Z` matched available bench `h200-attention-endpoint-e00vbbb709tzxscaan` to instance `computeinstance-e00vbbb709tzxscaan` and disk `computedisk-e00y9hv4e79xdh2g7b`; watchdog `gemma-global-head256-h200-202607182110z-watchdog.service` was active through `22:30:00Z`, and the post-fault GPU health check reported zero allocated MiB, 28 C, and no unsafe state.

**Change.** Tightened the researcher harness prompt so a launcher, path, CLI/API, parser, numeric-guard, telemetry, or retrieval defect before the first scientific invocation does not consume the candidate arm. When intervention, workload, bound identities, and decision gates are unchanged, the researcher now patches and repeats only that invalidated operation inside the same claim/session. No-retry rules still prohibit a second scientific candidate invocation or scope change, and an explicitly preregistered runtime incompatibility remains decision-bearing. The focused prompt regression and Python compilation pass.

**Expected effect.** Recoverable wiring defects should cost one in-place patch rather than a release/director/reclaim cycle, while scientific stop rules remain intact. Judge the change by fewer pre-invocation terminals followed by director overrides, shorter time from typed wiring error to first workload, and continued one-invocation discipline for actual candidates.

## 2026-07-19 — keep the claim in an outer mutable-session controller

**Bottleneck.** The pre-invocation repair guidance removed extra director cycles, but per-attempt owner scripts still exited through unconditional release traps. One researcher repaired multiple defects in one turn and reused the same provider allocation, yet repeatedly dropped and reacquired the exclusive claim, creating idle gaps and collision risk instead of a genuinely retained mutable session.

**Evidence.** `gemma4_global_head_dim256_sliced_endpoint` repaired deadline, source binding, config, loader, namespace, V-pool, and serialization defects before its sole scientific c32 invocation, but `gpu_events.jsonl` records nine claims between `21:59:35Z` and `22:26:06Z`; its eight inter-claim gaps total about nine minutes while the paid H200 stayed live. `gemma4_global_head_dim256_rope_preserving_endpoint` similarly used two claims around one pre-request oracle adapter repair, and `gemma4_global_head_dim256_attention_distillation` used three claims around deadline and optional-dependency repairs before its one frozen training/coherence candidate. All retained the same instance, disk, checkpoint, and image, so the repeated lease transitions supplied no scientific isolation. The one-shot Nebius audit at `23:36:37Z` exactly matched available bench `h200-attention-endpoint-e00vbbb709tzxscaan` to instance `computeinstance-e00vbbb709tzxscaan` and disk `computedisk-e00y9hv4e79xdh2g7b`; watchdog `gemma-head256-distill-h200-202607182305z-watchdog.service` was active through `2026-07-19T00:40:00Z`, and the final distilled server remained healthy and responsive.

**Change.** Refined the researcher harness prompt so one bounded outer controller owns claim, heartbeat, and final release across repair attempts. Inner attempt workers must not unconditionally release on a recoverable pre-invocation exit. Release remains mandatory when the scientific terminal or a nonrecoverable typed boundary is recorded, or when the absolute deadline requires director disposition. The focused prompt regression, Python compilation, and diff checks pass.

**Expected effect.** A mutable development experiment should normally produce one claim interval even when several integration repairs precede its single scientific invocation. Judge the change by fewer same-project release/reclaim pairs, less paid idle time between repairs, no competing claim race during patching, and unchanged prompt release at terminals and deadlines.

## 2026-07-19 — select the next portfolio arm before a no-work drain

**Bottleneck.** A reusable H200 was destroyed under a no-compatible-work/campaign-terminal judgment, then the immediately following director turn reopened the campaign and created another H200 for a compatible checkpoint-free experiment. This discarded resident image and Triton state and paid provider create/bootstrap latency that the existing bench could have avoided.

**Evidence.** Distillation released `h200-attention-endpoint-e00vbbb709tzxscaan` ready at `23:33:23Z`, with instance `computeinstance-e00vbbb709tzxscaan`, disk `computedisk-e00y9hv4e79xdh2g7b`, exact checkpoint, pinned SGLang image, and caches resident. The `23:38:56Z` director turn concluded no compatible work remained, drained at `23:43:57Z`, and retired it at `23:44:41Z`. The next director began at `23:46:52Z`, identified fused paged native GQA as the final scope-matched mechanism, and registered replacement H200 `computeinstance-e00ar2p5bk4a8qgqa9` / disk `computedisk-e00ky1wszvsbgj07x3` at `23:54:32Z`. That project used the same accelerator and pinned image, staged no checkpoint because its component gate failed, and did not claim until `00:06:39Z`; its conservative replacement-bench exposure was 1,343.10 seconds and `$0.918`. The outer-controller improvement did work on this run: one claim spanned the pre-invocation container-start diagnosis and sole scientific invocation through release at `00:14:23Z`. The final authenticated audit at `00:23:50Z` returned zero provider instances and disks, and both benches are retired with verified cleanup, so there is no current safety mismatch.

**Change.** Tightened the director harness prompt so a drain justified by no compatible work or campaign termination must follow the next portfolio selection in the same turn. If that selection would create the same compatible accelerator or environment, the director retains and assigns the existing bench instead of draining in one cycle and reopening onto replacement hardware in the next. Deadline, spend, unsafe-state, and genuinely incompatible-hardware drains remain unchanged. The focused prompt regression, Python compilation, and diff checks pass.

**Expected effect.** Terminal portfolio decisions should not create a one-cycle teardown/recreate race. Judge the change by zero same-accelerator replacements immediately after no-work drains, lower create-to-claim latency for final hypotheses, and continued prompt cleanup when the selected work is incompatible or the campaign is genuinely closed.

## 2026-07-19 — defer the director on an unchanged terminal snapshot

**Bottleneck.** The campaign has reached its model-specific terminal, but the harness still invokes the high-reasoning director every cycle because an empty runnable portfolio is categorically non-deferrable. These turns cannot improve the Gemma objective: the final fused paged-GQA specialization missed its required endpoint gain, only `$0.05` remains unreserved under the hard cap, every project is terminal, and there is no live GPU state to repair or reuse.

**Evidence.** The required one-shot authenticated Nebius listing returned zero instances and zero disks. `runtime/gpus.json` contains only six retired benches with null claims, so there is no provider/inventory mismatch, owner/watchdog loss, stale claim, passed live deadline, or idle-cost decision. After final GPU retirement at `00:21:08Z`, `runtime/events.jsonl` records 46 completed director turns through `01:25:23Z`, totaling 744.066 seconds. The five most recent traces all independently preserve campaign termination and make no project, GPU, budget, status, or log mutation. This is repeated interpretation of an unchanged terminal snapshot, not research progress.

**Change.** Extended the shared harness's existing observation-based director deferral to a quiescent lab with no active or ready projects. It now records `unchanged_quiescent_lab` and skips the director while the decision snapshot is identical. For safety, the snapshot now includes `CAMPAIGN.md` and `runtime/spend_cap.json` in addition to project statuses/summaries, GPU inventory, and the supervisor handoff; any changed objective, spend authority, project result, actionable audit handoff, or live-bench urgency wakes the director. Active or ready work without a running durable session retains the prior immediate-director behavior. No project, provider resource, GPU inventory record, or scientific decision was changed. All 29 harness tests pass, including focused terminal-deferral and campaign/spend wakeup regressions.

**Expected effect.** An unchanged terminated lab should spend zero director turns between material events, while a real reopening signal still schedules the director on the next cycle. Judge the change by `director_deferred` events with reason `unchanged_quiescent_lab`, disappearance of repeated terminal no-op traces, and prompt wakeup after an objective, spend, project, GPU, or supervisor-handoff change—not by generic cycle count or process tidiness.

## 2026-07-19 — back off full supervisor turns on an unchanged empty terminal lab

**Bottleneck.** Observation-based director deferral removed repeated portfolio interpretation, but the harness still launched a high-reasoning supervisor every four one-minute cycles on the same empty terminal snapshot. These turns repeatedly performed the same provider reconciliation and reread the same terminal evidence without changing the Gemma cost objective, GPU safety, harness, or supervisor handoff.

**Evidence.** The required one-shot authenticated Nebius listing again returned zero instances and disks, matching six retired inventory benches with no claims, owners, watchdogs, live deadlines, or idle-cost decisions. No project is active or ready, only `$0.05` remains unreserved, and the final paged-GQA discriminator remains a scientific miss at `-0.003998862109` seconds/request versus `+0.045972869706` required. Since `01:30Z`, `runtime/events.jsonl` records 32 completed supervisor turns totaling `1,341.269` seconds; the five latest each took `34.406`–`54.673` seconds while the director observation stayed `7a771c73...`, GPU events stayed at 47 claims/47 releases/6 verified retirements, and `SUPERVISOR_LOG.md` did not change.

**Change.** Added a six-interval supervisor backoff only when the director has proven `unchanged_quiescent_lab` and the inventory has no non-retired bench. At the configured four-cycle cadence this changes full empty-terminal audits from roughly every four minutes to every 24 cycles, recording `supervisor_deferred: unchanged_empty_quiescent_lab` between them. Any live bench preserves the original cadence, and objective, spend, project, supervisor-handoff, or GPU-inventory changes continue through the existing observation wakeup path. No provider resource, inventory record, project, budget, or scientific decision changed. All 31 harness tests and the repository DevEx check pass.

**Expected effect.** An unchanged empty terminal lab should spend about 83% fewer high-reasoning supervisor turns while retaining an authenticated external safety audit about every 24 minutes. Judge the change by five `supervisor_deferred` events between full audits, immediate restoration of the normal cadence whenever a live bench exists, and unchanged wakeup behavior after material campaign or project evidence—not by generic cycle count.

## 2026-07-19 — fence the retained H200 on a post-reboot disk-geometry mismatch

**Bottleneck.** The promoted local-KV-head 16→8 line is blocked before checkpoint transfer because an in-place boot-disk expansion did not reach the guest after reboot. Continuing the filesystem grow or checkpoint staging against contradictory provider and guest geometry would be unsafe; tearing down the retained H200 would also discard the pinned image and compilation caches that were deliberately preserved for the admitted conversion.

**Evidence.** The one-shot authenticated Nebius listing at `13:39Z` exactly matched registered bench `h200-local-kv8-e00tnyt66qqx2n7qqg` to running instance `computeinstance-e00tnyt66qqx2n7qqg` and READY managed disk `computedisk-e00vhr1v8p2aj4b5dv`, whose provider size is `214,748,364,800` bytes. A single read-only SSH probe 125 seconds after reboot still reported `/dev/vda` as `107,374,182,400` bytes and only `50,627,629,056` bytes free on `/`; the frozen owner requires at least `66,500,000,000` free bytes for the `62,578,655,208`-byte checkpoint. The controller-side watchdog `gemma-local-kv8-h200-202607191254-watchdog.service` is active under PID `2779981` through `17:15Z`; the bench has no claim and was intentionally in maintenance. The retained session has already produced decision-relevant evidence: the checkpoint-free discriminator saved `0.032131702656` seconds/request versus `0.018165158891` required. Its phase-two preflight held the claim for only 1.775 seconds and invoked no checkpoint transfer, model load, training update, server, or scientific candidate.

**Change.** Marked the registered bench draining through the atomic pool interface to fence new claims while provider and guest disk geometry disagree. I did not stop, delete, resize, clean, or retire the instance or disk. The director should use the exact IDs above to recover the existing allocation in place and return it to maintenance or ready only after the guest exposes 200 GiB and the required free capacity; this drain is a safety fence, not a teardown recommendation. Also clarified the shared supervisor skill and generated harness prompt so watchdog health is checked in the recorded controller manager namespace rather than inferred from a guest systemd probe; the focused prompt regression covers the clarification.

**Expected effect.** No researcher can grow the wrong device or start the 62.58-GB transfer while the geometry is contradictory, but the director can preserve the same H200, disk, pinned image, and caches during repair. Once the guest observes 200 GiB, the same frozen conversion owner can resume without cold allocation or setup. Future audits should avoid false watchdog-loss findings when lifecycle units are controller-owned.

## 2026-07-19 — wake the retained resize repair after the asynchronous stop completes

**Bottleneck.** The director correctly chose an asynchronous stop rather than teardown after the resized disk remained 100 GiB in the guest, but completion of that external operation does not change the inventory observation used by director deferral. Without a material supervisor handoff, the stopped retained session would remain fenced and the admitted local-KV8 conversion would not reach the required clean reattach.

**Evidence.** The one-shot authenticated Nebius listing at `13:50Z` reports exact instance `computeinstance-e00tnyt66qqx2n7qqg` as `STOPPED` with `spec.stopped=true`; its managed disk `computedisk-e00vhr1v8p2aj4b5dv` remains attached, READY, and `214,748,364,800` bytes. Inventory bench `h200-local-kv8-e00tnyt66qqx2n7qqg` remains draining with no claim, and controller watchdog `gemma-local-kv8-h200-202607191254-watchdog.service` is active under PID `2779981` through `17:15Z`. The director issued stop operation `computeoperation-e00vdep3yk8r6vnzkz` at `13:47Z`; subsequent cycles deferred on unchanged observation `32119f90...`, as expected because provider state is deliberately not polled every cycle. No checkpoint, server, training update, or scientific candidate ran during this lifecycle transition.

**Change.** Appended this material provider transition so the existing supervisor-handoff wakeup schedules the director. No provider start, stop, resize, cleanup, retirement, inventory mutation, project change, or new experiment was performed. The director should start the same instance, retain the same disk/image/caches, and keep the drain fence until a later bounded guest probe sees 200 GiB and the filesystem has at least `66,500,000,000` free bytes.

**Expected effect.** The next director turn can continue the already-chosen in-place repair without a cold allocation or repeated polling. If clean reattach exposes 200 GiB, the frozen conversion owner can resume from checkpoint staging; otherwise the director receives a new typed provider boundary while the exact resources remain fenced.

## 2026-07-19 — release the resize fence after clean reattach succeeds

**Bottleneck.** The retained H200 storage repair has succeeded externally, but the inventory remains draining and the project remains blocked because provider/guest readiness is intentionally not part of the per-cycle director observation. The admitted local-KV8 conversion cannot reclaim the bench until the director receives this material transition and clears the safety fence.

**Evidence.** The one-shot authenticated Nebius listing at `13:57Z` reports the same instance `computeinstance-e00tnyt66qqx2n7qqg` RUNNING with the same READY 200-GiB managed disk `computedisk-e00vhr1v8p2aj4b5dv`. A single read-only SSH probe 195 seconds after the clean start reports `/dev/vda` at `214,748,364,800` bytes, root partition `/dev/vda1` at `213,673,557,504` bytes, root filesystem size `206,900,281,344` bytes, and `154,625,036,288` bytes free—well above the frozen `66,500,000,000`-byte gate. Controller watchdog `gemma-local-kv8-h200-202607191254-watchdog.service` remains active under PID `2779981` through `17:15Z`. Inventory is still draining with no claim, so no researcher raced the repair and no checkpoint, server, training update, or scientific candidate ran.

**Change.** Appended this readiness transition to wake the director through the existing supervisor-handoff observation. I did not mark the bench ready, claim it, update resident contents, start checkpoint transfer, or mutate provider state. The director can now record the expanded filesystem, clear the drain fence, and schedule the same frozen conversion owner against the retained instance, disk, image, and caches.

**Expected effect.** The local-KV8 phase-two owner should resume directly from checkpoint staging with more than twice its required free capacity, avoiding a replacement allocation and repeated image/compilation setup. Judge the repair by one ready transition followed by one retained claim and a quality-gated conversion result, not by more lifecycle turns.

## 2026-07-19 — ignore successful heartbeats when deciding whether to wake retained-session agents

**Bottleneck.** The repaired retained H200 and its phase-two owner are healthy, but routine 45-second heartbeats were treated as material observation changes. The harness repeatedly launched director and researcher turns during the correct 62.58-GB immutable checkpoint transfer; every trace concluded that the owner should remain uninterrupted and produced no experiment or portfolio decision.

**Evidence.** The one-shot authenticated Nebius listing at `14:10Z` exactly matches claimed bench `h200-local-kv8-e00tnyt66qqx2n7qqg` to RUNNING instance `computeinstance-e00tnyt66qqx2n7qqg` and READY 200-GiB disk `computedisk-e00vhr1v8p2aj4b5dv`. The expected project owns the claim, heartbeats advance every 45 seconds, the lease is fresh through `14:20:08Z`, and controller watchdog `gemma-local-kv8-h200-202607191254-watchdog.service` is active through `17:15Z`. The durable owner `gemma-local-kv8-phase2-202607191402.service` is transferring the exact eight-file `62,578,655,208`-byte checkpoint with no terminal or failure artifact. After that owner was established, three researcher turns totaling `38.746` seconds and three director turns totaling `132.029` seconds only said to leave it untouched. `outer-events.jsonl` changed between those turns solely by successful `heartbeat` rows, while `runtime/gpus.json` changed only in `updated_at`, `heartbeat_at`, and `lease_until_utc`.

**Change.** Normalized retained-session observations so successful `heartbeat` and `claim_heartbeat` JSONL rows do not change the development observation identity; nonzero heartbeat failures and every other event remain material. Normalized the director's GPU identity to ignore only inventory and claim renewal timestamps. Claim owner/status, contents, drain state, lifecycle, resources, next action, non-heartbeat artifacts, and project status still wake agents, while the existing live snapshot check still prevents deferral for stale claims or passed lifecycle deadlines. The active owner and provider state were not mutated. Two focused regressions and all 31 harness tests pass, along with Python compilation and diff checks.

**Expected effect.** Long checkpoint transfers and other healthy retained development phases should run under one owner without minute-scale no-op director/researcher turns. Agents should wake on a terminal, failure, material artifact, changed action, ownership/state transition, stale lease, or deadline—not on successful lease renewal. Judge the change by `researcher_deferred: unchanged_development_session` and `director_deferred: unchanged_durable_sessions` during the remaining transfer, followed by an immediate wake when the owner emits its first typed terminal.

## 2026-07-19 — preserve a completed producer across a recoverable consumer binding failure

**Bottleneck.** The admitted local-KV8 schedule completed its sole distillation producer and passed the fidelity gates, but the later SGLang consumer stopped at an ordinary model-config binding guard before server readiness. Treating this consumer wiring defect as a scientific conversion miss, rerunning the 24-update producer, or replacing the retained H200 would discard valid decision-bearing work and repeat the campaign's dominant transfer/setup cost.

**Evidence.** The required one-shot Nebius listing at `14:44Z` exactly matches claimed bench `h200-local-kv8-e00tnyt66qqx2n7qqg` to RUNNING instance `computeinstance-e00tnyt66qqx2n7qqg` and READY disk `computedisk-e00vhr1v8p2aj4b5dv`; the claim and controller-host watchdog remain healthy with future deadlines. `DISTILL_TERMINAL.json` records one candidate invocation, 24 optimizer updates, improved held-out block and final-hidden fidelity, a passing fidelity gate, and a content-addressed 100-tensor overlay (`2,202,022,184` bytes, SHA-256 `e29faa67...`). The subsequent `OWNER_TERMINAL.json` is `startup_failure: server_not_ready`. Its server traceback is deterministic and local to the patched consumer: `model_config.py` rejects the already-transformed expected geometry `{num_key_value_heads: 4, swa_num_key_value_heads: 8}` because its guard still requires local KV heads `16` before assigning `8`. The owner retained the exact checkpoint/image/caches and was still claimed while retrieving the overlay; no coherence, retrieval, or exact-c32 consumer ran, and no teardown or replacement occurred.

**Change.** Extended the reusable researcher skill and generated harness prompt for paid multi-stage experiments: once a producer stage is completed and persisted, an ordinary later configuration/import/path/API/numeric-guard/harness defect must preserve that producer artifact and patch only the failed consumer on the same retained bench. Training, conversion, calibration, or another scientific producer invocation remains forbidden; the defect is decision-bearing only when the project preregisters that exact incompatibility or resident state is unsafe. Added prompt regressions; all 31 harness tests pass, along with Python compilation and diff checks. I did not patch the project's model code, alter its scientific schedule, interrupt the owner, mutate inventory, or perform provider lifecycle work.

**Expected effect.** After the current overlay retrieval and release complete, the same project should reclaim the same H200, checkpoint, overlay, image, and caches; repair only the mixed-geometry consumer binding; and resume at server startup without another checkpoint transfer or distillation invocation. Judge the change by one retained consumer repair leading to coherence/retrieval or a genuine typed incompatibility, with zero repeated producer runs, new projects, cold allocations, or teardown/recreate cycles.

## 2026-07-19 — do not serialize retained consumer repair behind bulk artifact retrieval

**Bottleneck.** After the local-KV8 producer and fidelity gate completed, its outer owner serialized the recoverable consumer repair behind a controller-bound copy of the `2,202,022,184`-byte overlay. The H200 was idle while the only bytes needed for repair were already content-addressed and durable on the protected remote bench. This turned evidence preservation into the critical path instead of resuming the failed consumer in place.

**Evidence.** The one-shot Nebius audit at `14:54Z` still matched the exact RUNNING instance `computeinstance-e00tnyt66qqx2n7qqg` and READY disk `computedisk-e00vhr1v8p2aj4b5dv` to bench `h200-local-kv8-e00tnyt66qqx2n7qqg`; its claim, controller watchdog, and deadlines were healthy. The compact distillation terminal, fidelity metrics, overlay SHA-256, server traceback, and owner terminal were already retrieved by `14:41:39Z`. From then until `14:56:40Z`, the owner held the claim solely in `scp` while telemetry showed no active server and zero GPU utilization. The 900-second transfer timed out after only `585,953,280` bytes (26.6%), emitted `outer_error: TimeoutExpired`, and released the warm bench ready; the full overlay remains remotely available alongside the exact checkpoint/image/caches. The released inventory description incorrectly says the overlay was retrieved project-locally even though only `.overlay.safetensors.partial` exists. This contents mismatch is actionable but not a safety reason to drain; the next project-owned claim/release should correct it.

**Change.** Extended the reusable researcher skill and generated harness prompt so a large producer artifact that is content-addressed and durable on a protected retained bench is represented first by its compact terminal, hash, and manifest. A recoverable later consumer must use that remote artifact in place; bulk retrieval happens after the final terminal or concurrently only when it does not delay GPU progress. The existing rules still prohibit a second producer invocation and require eventual durable retrieval before provider cleanup. Added two prompt regressions; all 31 harness tests pass with Python compilation and diff checks. I did not interrupt the transfer, claim the released bench, patch scientific code, alter the project schedule, or mutate provider lifecycle.

**Expected effect.** The next researcher can immediately reclaim the same available H200, correct the inventory contents, patch the mixed-geometry guard, and restart only the SGLang consumer against the remote content-addressed overlay. Future multi-stage owners should spend zero claimed GPU-idle time waiting for a controller-bound bulk copy when the protected remote artifact and compact local evidence already make in-place continuation safe.

## 2026-07-19 — provider cleanup verified; retire the drained local-KV8 inventory record

**Bottleneck.** Director-owned cleanup has completed externally, but the lab inventory still contains the local-KV8 bench as draining. Leaving this verified-absent record pending would keep a false live lifecycle surface in GPU audits and prevent the empty terminal lab from reaching a clean reconciled state.

**Evidence.** The required one-shot Nebius listing at `15:19Z` returned zero instances and zero disks. Exact instance `computeinstance-e00tnyt66qqx2n7qqg` and disk `computedisk-e00vhr1v8p2aj4b5dv` are absent; inventory bench `h200-local-kv8-e00tnyt66qqx2n7qqg` is already `draining` with no claim, and its controller watchdog `gemma-local-kv8-h200-202607191254-watchdog.service` is inactive. The project is scientifically terminal: the retained repair reclaimed the same H200 at `15:03:12Z`, patched only the consumer, reached server readiness, and produced repetitive gibberish on all 3/3 coherence prompts before releasing at `15:05:09Z`; no producer, checkpoint transfer, retrieval gate, or c32 run repeated. The exact `2,202,022,184`-byte overlay was then resumed and SHA-256 verified locally without a GPU claim. The director requested drain at `15:16:08Z` and recorded both provider objects deleting pending this authenticated absence check.

**Change.** Appended this provider-absence handoff so the existing supervisor-log wakeup schedules director reconciliation. I did not repeat cleanup, retire or otherwise mutate the inventory record, stop a watchdog, change a project, or open another experiment. The director should retire exact bench `h200-local-kv8-e00tnyt66qqx2n7qqg` against the absent resource IDs above and avoid another provider delete call.

**Expected effect.** The next director turn should perform one inventory-only retirement, leaving zero provider resources and zero non-retired benches. The campaign can then return to quiescent deferral with the scientific terminal, overlay, spend, and successful retained-consumer repair preserved.

## 2026-07-20 — make large immutable staging durable and manifest-resumable before copying

**Bottleneck.** The reopened kernel phase needs a measured in-memory H200 FP8 endpoint to attack the roughly 23% cost gap, but the direct lane crossed three ordinary setup boundaries before its first CUDA or scientific invocation: a stale provider-IP host key, a checkpoint transfer launched as an ordinary turn-bound background process, and an all-files SCP retry that attempted to overwrite already-matched `0444` files. The retained bench avoided teardown, but setup and repair—not GPU science—remain the critical path.

**Evidence.** The required one-shot Nebius listing at `23:08Z` exactly matches claimed bench `h200-kernel-frontier-e00pfvrckjvwn7bhet` to RUNNING instance `computeinstance-e00pfvrckjvwn7bhet` and READY disk `computedisk-e00hnms4mwjf6crmcb`. The controller-host watchdog `gemma4-kernel-frontier-202607192225-watchdog-v2.service` and durable owner `gemma4-inmemory-fp8-c32-20260719t230415z.service` are active; the expected project owns the claim and heartbeats every about 45 seconds with future claim, project, and lifecycle deadlines. The current owner correctly preserved six matched metadata files and the complete `12,761,549,884`-byte second shard, removed only the `38,906,880`-byte partial first shard, and is transferring only the missing `49,784,788,364`-byte first shard before verifying all eight hashes. Image pull, CUDA, server launch, and the frozen exact-c32 candidate remain unconsumed. The provider disk ID was missing from the registered resource despite its disk name being present.

**Change.** Added one narrow rule to the reusable researcher skill and generated harness prompt: when large immutable staging can outlive a turn, start it inside the durable claim owner before copying bytes; reconcile the remote size/hash manifest first; preserve matches; transfer only missing or mismatched files to temporary paths; verify and atomically finalize them; never retry an all-files overwrite against matched read-only files. Added focused prompt regressions; the targeted harness test, Python compilation, and diff checks pass. Under the GPU pool lock, reconciled disk ID `computedisk-e00hnms4mwjf6crmcb` into the live bench resource and emitted `bench_resource_reconciled`; the active claim heartbeat remained fresh. I did not signal either service, touch the guest, release/drain the bench, or mutate provider lifecycle.

**Expected effect.** Future large checkpoint staging should survive agent-turn boundaries from its first byte and resume by file identity rather than replaying tens of gigabytes or bouncing through maintenance. The current owner should continue uninterrupted from the sole missing shard into image load and the one frozen FP8 endpoint schedule; afterward the queued QKV epilogue lane can inherit the same checkpoint/image/caches without cold setup. Judge the change by zero additional pre-science release/reclaim cycles, zero repeated matched-file transfers, one typed FP8 terminal, and prompt reuse by the queued component experiment.

## 2026-07-20 — defer an exact-bench dependent project while another owner holds a fresh claim

**Bottleneck.** The repaired FP8 staging owner is healthy and should be left alone, but the harness repeatedly scheduled the queued QKV researcher and director while that exact H200 remained freshly claimed. Each QKV turn only reconfirmed `shared_bench_claimed` and rewrote its observation timestamp/log, which woke the next director cycle. This spent reasoning time without advancing the 23% cost-gap objective and created a self-sustaining coordination loop around normal setup.

**Evidence.** The required one-shot Nebius listing at `23:19Z` exactly matches the registered RUNNING instance `computeinstance-e00pfvrckjvwn7bhet` and READY disk `computedisk-e00hnms4mwjf6crmcb`. Inventory records both IDs, the expected FP8 project owns the claim, heartbeats advance about every 45 seconds with a fresh lease, and the controller-host watchdog plus durable owner are active with future deadlines. Since the preceding `23:08Z` audit, the QKV researcher ran four times for `146.602` total seconds and only appended fresh-heartbeat variants of the same `shared_bench_claimed` boundary; four director turns consumed another `138.816` seconds and repeatedly chose to preserve the same owner. No QKV CUDA call, claim, spend, scientific result, or portfolio change occurred. The FP8 owner continued transferring the sole missing shard and produced no error or terminal.

**Change.** Added dependency-aware scheduling to the lab harness. A project whose `STATUS.json.external_dependency.type` is `shared_bench_claimed` is deferred when the named bench is actually claimed by another project with a non-stale lease. The director may likewise defer when all runnable work is either a live durable owner or such an exact-bench dependent. The boundary is derived from current pool state rather than the dependency timestamp: release, missing/different ownership, stale claim, changed dependency type/bench, or lifecycle urgency immediately wakes normal scheduling. Added a behavioral regression proving no dependent researcher/director work under the fresh claim and immediate dependent launch after release; four focused harness tests, Python compilation, and diff checks pass. I did not modify either project, claim, unit, guest, or provider lifecycle.

**Expected effect.** While the FP8 transfer and subsequent frozen endpoint run progress normally, the harness should emit cheap `researcher_deferred: shared_bench_claimed` and `director_deferred: unchanged_durable_sessions` events instead of minute-scale QKV/director turns. The QKV outer should wake on the first release/terminal transition and inherit the resident checkpoint/image/caches without polling or cold setup. Judge the change by zero further QKV agent runs before release and one prompt launch promptly after the pool claim clears.

## 2026-07-20 — retrieve remote failure evidence before releasing a claimed bench

**Bottleneck.** The QKV epilogue owner repaired its first pre-CUDA integration defect on the retained H200, but its retry returned nonzero and the outer controller released the claim before retrieving the remote worker terminal or diagnostic. The campaign therefore cannot tell whether the frozen candidate CUDA arm was consumed. This is an observability/release-order defect, not a component result, and a blind replay would risk either wasting the sole arm or suppressing an admissible first invocation.

**Evidence.** The required one-shot Nebius listing exactly matches registered bench `h200-kernel-frontier-e00pfvrckjvwn7bhet` to RUNNING instance `computeinstance-e00pfvrckjvwn7bhet` and READY disk `computedisk-e00hnms4mwjf6crmcb`; both exact IDs are inventoried. The bench is in maintenance with no claim, its controller-host watchdog `gemma4-kernel-frontier-202607192225-watchdog-v2.service` is active, and its lifecycle deadline remains future, so there is no owner-loss, deadline, or safety basis to drain it. The queued FP8 consumer is compatible with its retained checkpoint/image state, so reuse remains economically justified. The prior dependency change worked: QKV and director turns deferred under FP8's fresh claim and QKV launched promptly after release. Its outer then held the H200 for `179.252` seconds (`$0.122489` conservatively derived). The first worker failed before CUDA on a pinned `get_rope()` scheduler-argument integration defect and was patched under the same claim. The retry returned nonzero with empty outer-captured stdout/stderr; local compact component terminal/result artifacts were not retrieved, candidate consumption remains unknown, and the controller released the bench to maintenance. Inspection of the controller confirms remote terminal/result retrieval occurs only after a successful worker return, while `finally` performs the failure release.

**Change.** Added one narrow rule to the reusable researcher skill and generated harness prompt: before releasing a claimed bench after a remote worker failure, retrieve its compact terminal, bounded raw stdout/stderr, and an explicit marker of whether the candidate CUDA/scientific invocation began. Missing retrieval is a recoverable retrieval defect to repair under the same claim; release without those artifacts is reserved for an unsafe/unreachable guest or the absolute deadline requiring director handoff. Added focused prompt regressions; three focused harness tests, Python compilation, and diff checks pass. I did not patch either project controller, claim or probe the guest, run or replay an experiment, mark the bench draining, or mutate provider lifecycle.

**Expected effect.** Future remote failures should retain the same warm claim long enough to establish exact arm consumption and preserve the diagnostic needed for a bounded repair. For the current maintenance handoff, the director should retrieve the retained remote diagnostic and compact terminal first, then decide whether the same H200 can be reused by QKV or the queued FP8 consumer; no blind scientific replay or cold allocation is justified from the current evidence.

## 2026-07-20 — preserve exact-bench deferral when optional dependency metadata is dropped

**Bottleneck.** The active in-memory FP8 endpoint owner is making normal same-claim progress, but the queued QKV project stopped carrying `external_dependency` after its failure reconciliation even though its exact `bench_id` and next action still explicitly say to wait for FP8's terminal and release. The harness consequently relaunched QKV and the director every cycle to rediscover the same fresh-claim boundary. This coordination churn does not move the roughly 23% cost gap and risks distracting from the first deployable FP8 endpoint measurement.

**Evidence.** The required one-shot Nebius listing reports exactly one RUNNING instance, `computeinstance-e00pfvrckjvwn7bhet`, and one READY disk, `computedisk-e00hnms4mwjf6crmcb`; both match registered bench `h200-kernel-frontier-e00pfvrckjvwn7bhet`, with no unregistered provider resource or missing live inventory resource. The controller-host watchdog `gemma4-kernel-frontier-202607192225-watchdog-v2.service` and project owner `gemma4-inmemory-fp8-c32-20260720t2348z.service` are active in their recorded user-manager control groups, the lifecycle deadline is future, and the FP8 claim heartbeat is fresh. The owner matched all eight immutable checkpoint files, staged the bound inputs, and has continued successful roughly 45-second heartbeats; it has not released, failed, or emitted a terminal. QKV's status has no `external_dependency`, but names the same bench and begins its next action with `Wait for the current primary FP8 durable owner...`. The three QKV turns after that state consumed `41.094`, `14.134`, and `7.367` seconds and only restated that no claim, mutation, invocation, or spend was allowed. The corresponding director turns consumed `32.316`, `12.492`, and `11.363` seconds and made the same unchanged-owner decision.

**Change.** Extended the existing exact-bench deferral helper to accept either the structured `shared_bench_claimed` dependency or an explicit `Wait ...` next action paired with the project's exact `bench_id`. It still verifies current pool reality: the bench must actually be claimed by another project with a non-stale claim. Release, stale claim, same-project ownership, a changed next action, or a different bench immediately restores scheduling. Updated the behavioral regression to reproduce the observed missing-metadata case and prove immediate launch after release; three focused harness tests, Python compilation, and diff checks pass. I did not modify either project, owner, claim, guest, inventory, watchdog, or provider lifecycle.

**Expected effect.** While FP8 runs, the harness should emit cheap `researcher_deferred: shared_bench_claimed` for QKV and settle the director on `unchanged_durable_sessions` instead of spending about two agent-minutes every three cycles restating the same boundary. The first FP8 terminal/release should still wake QKV immediately for its already-prepared, unconsumed component arm. No drain or teardown is warranted for the healthy claimed bench.

## 2026-07-20 — wake a researcher for an active owner's bounded repair handshake

**Bottleneck.** The in-memory FP8 worker reached a recoverable `server_not_ready` consumer failure and its durable outer explicitly opened a ten-minute in-place repair handshake, but the harness unconditionally deferred every batch-mode active session. The owner therefore kept the warm H200 claimed and heartbeat-safe while waiting for `REPAIR_REQUEST.json`, yet no researcher could inspect and repair the integration defect before the handshake deadline. This would turn the campaign's direct endpoint lane into another avoidable release/reclaim cycle.

**Evidence.** The required one-shot Nebius listing exactly matches RUNNING instance `computeinstance-e00pfvrckjvwn7bhet` and READY disk `computedisk-e00hnms4mwjf6crmcb` to claimed bench `h200-kernel-frontier-e00pfvrckjvwn7bhet`. Its controller-host watchdog and project owner are active in their recorded user-manager control groups, the claim heartbeat and lifecycle deadline are fresh, and there is no resource mismatch or drain condition. The owner matched all eight checkpoint files and then wrote `REPAIR_READY.json` at `00:05:34Z` with classification `consumer_failure`, message `server_not_ready`, and a repair deadline around `00:15:35Z`; `REPAIR_REQUEST.json` and the final terminal were absent while heartbeats continued every roughly 45 seconds. The owner code waits for that request before copying the repaired scripts and retrying in the same claim. Existing scheduling instead emitted `researcher_deferred: durable_session_active`, so the protocol's only repair participant was suppressed.

**Change.** Added a narrow durable-repair detector to the harness. A running batch owner wakes its own researcher only when its declared artifact root contains a valid, unexpired `REPAIR_READY.json` and contains neither `REPAIR_REQUEST.json` nor `TERMINAL.json`. The generated prompt tells the researcher to inspect the decision-bearing diagnostic once, patch only the recoverable defect, write the documented request, and never stop, replace, release, cold-restart, or replay a consumed stage. Once a request or terminal exists—or the deadline expires—normal active-session deferral resumes. Three focused tests, Python compilation, and diff checks pass. I did not modify the project controller, repair request, claim, guest, owner, inventory, watchdog, or provider lifecycle.

**Expected effect.** The next harness reload should wake the FP8 researcher during the bounded repair window so it can repair `server_not_ready` under the existing warm claim rather than let the owner time out and force another setup cycle. Future durable owners can safely expose the same handshake without being mistaken for either normal progress or a terminal session, while unrelated active owners remain deferred.

## 2026-07-20 — keep pre-measurement consumer repairs inside the durable claim

**Bottleneck.** The in-memory FP8 endpoint finally produced the campaign's most important new result—`0.7485534847` seconds/request with exact c32 accounting and proven scheduler-side FP8 execution—but the last four integration/consumer corrections repeatedly finalized their attempt and released the same compatible warm H200 before the scientific arm had begun. The existing repair-handshake wakeup can preserve an active owner, but controllers were not told to use that protocol as the default for a proven pre-invocation defect.

**Evidence.** The required one-shot authenticated Nebius listing reports only RUNNING instance `computeinstance-e00pfvrckjvwn7bhet` and READY disk `computedisk-e00hnms4mwjf6crmcb`, exactly matching available inventory bench `h200-kernel-frontier-e00pfvrckjvwn7bhet`; there is no unregistered provider resource or missing live inventory resource. The controller-host watchdog `gemma4-kernel-frontier-202607192225-watchdog-v2.service` is active under PID `2849518`, the bench has no claim or stale lease, and its `03:30Z` lifecycle deadline is future. It was released ready at `01:36:49Z` after the successful endpoint arm, so its few minutes of idle time at audit were justified for immediate director selection against the resident checkpoint, image, caches, and FP8 server; no drain or safety mutation is warranted. GPU events show four preceding warm claims lasting `104.205`, `103.737`, `219.514`, and `309.624` seconds, separated by `674.359`, `522.095`, `434.967`, and `788.509` seconds of idle director/researcher handoff time: `2,419.930` idle seconds, about `$1.654` at `$2.46/hour`, versus `737.081` claimed seconds. Project evidence classifies the boundaries as an absent scheduler audit path, an over-strict coherence parser, and a labeled-Prometheus queue parser defect before c32; the final owner then repaired an ordinary Docker identity assertion under the same claim and reached the useful endpoint result without a cold allocation.

**Change.** Extended the reusable researcher skill and generated harness prompt with one explicit controller rule: after retrieving evidence that an ordinary integration or consumer defect occurred before the admitted scientific arm, keep the outer owner and heartbeat alive, write `REPAIR_READY.json` with the diagnostic and absolute deadline, wait for `REPAIR_REQUEST.json`, and repeat only the invalidated operation. Such an attempt terminal must not become the project's final terminal or cause warm-bench release unless the boundary is preregistered, the guest is unsafe/unreachable, or the absolute deadline arrives. The handshake does not authorize intervention changes or replay of a consumed arm. Two focused prompt/handshake regressions and Python compilation pass. I did not modify the completed FP8 project, claim the bench, stop or restart its server, change inventory, or mutate provider lifecycle.

**Expected effect.** Future direct endpoint integrations should convert recoverable parser, path, runtime-context, and identity failures into one bounded claimed repair window rather than another director/researcher/reclaim cycle. Judge the change by fewer pre-measurement releases, materially less compatible-bench idle time, no repeated setup, and unchanged scientific-arm accounting; director authority still governs genuine scope changes and final resource disposition.

## 2026-07-20 — reset an execution thread that explicitly exhausts its turn

**Bottleneck.** SGLang v0.5.13 dynamic FP8 moved the exact endpoint to `0.6979244360` seconds/request, beyond the working price frontier, so the critical path is now the already-admitted QKV stack followed by transferable production validation. The QKV project's execution thread recognized that the v0.5.13 stack runner was missing but then returned twice more without implementing it, leaving the warm H200 idle and causing the dependent quality project to repeat the same terminal check.

**Evidence.** The required one-shot authenticated Nebius listing contains only RUNNING instance `computeinstance-e00pfvrckjvwn7bhet` and READY disk `computedisk-e00hnms4mwjf6crmcb`, exactly matching inventory bench `h200-kernel-frontier-e00pfvrckjvwn7bhet`; there is no extra or missing provider object. The recorded controller-host watchdog `gemma4-kernel-frontier-202607200245-watchdog-v3.service` is active under PID `2969423` through `06:15Z`, with no claim, stale lease, or passed deadline. I initially probed the superseded v2 unit and briefly fenced the bench, then resolved the inventory's actual v3 metadata, confirmed it continuously active since `02:44:40Z`, and immediately restored the bench to available; no provider, guest, claim, project, or watchdog operation occurred. Warm reuse remains justified: MTP used the same resident checkpoint/caches from `02:12:45Z` to `02:23:40Z`, produced a valid same-session FP8 control at `0.6979244360` seconds/request, and released without teardown; QKV and quality validation are both compatible queued work. After QKV was rebased onto this frontier, its execution-profile turns at `02:38:59Z`, `02:45:37Z`, and `02:48:58Z` lasted only `25.610`, `12.692`, and `11.389` seconds. The latter two ended with explicit variants of “couldn't complete ... within this turn,” made no claim or scientific invocation, and did not advance project state. The existing harness reset only the narrower phrase “remaining response capacity,” so it kept resuming the same saturated thread.

**Change.** Extended the existing trace-based thread-reset detector to recognize only explicit incomplete-turn handoffs that combine `within this turn` with `unable to complete`, `couldn't complete`, or `cannot complete`. On the next cycle the harness will start a fresh thread on the same configured researcher route; it does not change the project's scientific scope, priority, budget, profile, model policy, or arm accounting. Added a focused regression for the observed wording while preserving the existing response-capacity behavior. I did not edit either active project or its artifacts.

**Expected effect.** QKV should receive a fresh execution context on the next harness cycle and either materialize the missing v0.5.13 stack runner, launch the bounded paired arm, or return a real typed blocker instead of another short turn-capacity handoff. This should unblock the already-bound production validation and convert the retained H200's idle time into the two campaign-critical decisions without cold setup or a new project.

## 2026-07-20 — fence the provider-absent production-validation bench

**Bottleneck.** The fresh-thread correction worked and converted the retained H200 into the next performance result, but the immediately following production-quality owner lost the provider instance during execution/retrieval. The campaign now has a durable frontier-performance candidate but no transferable quality verdict, and the stale inventory record must not accept another claim.

**Evidence.** The required one-shot authenticated Nebius listing returned zero instances and zero disks. Inventory still recorded maintenance bench `h200-kernel-frontier-e00pfvrckjvwn7bhet` with exact instance `computeinstance-e00pfvrckjvwn7bhet` and disk `computedisk-e00hnms4mwjf6crmcb`; its controller-host watchdog `gemma4-kernel-frontier-202607200245-watchdog-v3.service` is now inactive. The watchdog journal shows a successful exit after its loop observed the instance absent, and its code then deletes any matching orphan disk, which explains the empty provider listing without evidence of researcher teardown. There is no claim or stale lease. The previous supervisor change was effective: the harness emitted `researcher_thread_reset` at `03:02:32Z`; the fresh QKV turn then ran `500.958` seconds, reused the warm H200, and produced two valid c32 arms. The candidate measured `0.6928421805` seconds/request versus `0.7004446705` control, a `1.085%` same-session gain with 32/32 rows, exact cache accounting, proven FP8 consumption, and exact QKV epilogue rows. Production validation then held three short claims of about `9.9`, `30.0`, and `87.5` seconds. Its first attempt failed before capture on an input-path defect; the repair attempt lost SSH during post-worker retrieval as the provider instance disappeared; the last bounded direct retrieval returned no bytes. No compact terminal or invocation-state marker survived, so BF16/FP8 quality-arm consumption is unknown and replay is not authorized from current evidence.

**Change.** Marked the registered bench draining through the atomic pool interface. I did not issue provider deletion, repeat the provider listing, retire the inventory record, alter the blocked quality project, or change scientific scope. No skill or harness patch is warranted for the provider disappearance: the prior thread-reset behavior produced its intended result, and the independent lifecycle watchdog performed cleanup after observing the instance absent rather than forcing a cold restart after a recoverable integration error.

**Expected effect.** The drain fence prevents another researcher from claiming a nonexistent H200 while preserving exact lifecycle and spend history. The director should retire only inventory bench `h200-kernel-frontier-e00pfvrckjvwn7bhet` against the two absent resource IDs above, without another provider cleanup call, then decide how to recover production-quality evidence under the existing campaign objective and remaining authority. Preserve the durable `0.6928421805`-second QKV-stacked performance result regardless of that portfolio decision.

## 2026-07-20 — preserve the retained H100 repair in scheduler state

**Bottleneck.** The matched H100 placement remains the campaign's sole active economic falsifier, but its live `STATUS.json` lost one comma while recording transfer progress. The harness safely classifies malformed project status as blocked, yet that fallback necessarily hides the active session and its repair handshake. Leaving it malformed would convert a healthy claimed mutable bench into an apparent project blocker and could delay the only remaining objective-bearing arm.

**Evidence.** The one grouped authenticated Nebius reconciliation exactly matches RUNNING instance `computeinstance-e00nmpn5czcb44jqm1` and READY disk `computedisk-e00rd32znm10exgyy3` to claimed inventory bench `h100-v0513-fp8qkv-r2-e00nmpn5czcb44jqm1`; there is no extra or missing provider object. Controller-host units `gemma4-h100-r2-watchdog.service` and `gemma4-h100-r2-owner.service` are active in their recorded user-manager control groups, the claim heartbeat is fresh, and the `14:09:17Z` lifecycle deadline is future. The first H100 attempt spent a conservatively recorded `5,903.551` seconds and `$3.525739` on sequential cold staging before its absolute deadline, with `candidate_science_started=false`; its watchdog then cleaned the absent provider resources and the director retired the record. The replacement has corrected that measured bottleneck under one retained claim: two parallel resumable SFTP streams are active, shard 2 is finalized, shard 1 resumed from `27,697,259,520` to `33,138,478,080` bytes, and no scientific marker exists. The H200 residual itinerary produced decision-bearing negative results, was drained after no compatible work remained, and is correctly absent and retired.

**Change.** Restored the missing comma only, making the active H100 status valid JSON again. No owner, claim, repair request, transfer, guest, provider resource, watchdog, experiment scope, or arm accounting changed. The shared harness already isolates malformed status rather than crashing, so no additional static validation or new project was added.

**Expected effect.** Subsequent harness cycles should again see the exact active session, defer normal polling while the transfer progresses, and wake the same researcher only for a valid unconsumed repair handshake or terminal. This preserves the replacement's partial bytes and avoids another cold allocation while the sole H100 c32 arm remains unconsumed.

## 2026-07-20 — align H100 audit environment names before warm repair

**Bottleneck.** The replacement H100 completed its 62.6-GB checkpoint transfer and image pull under the retained claim, but the endpoint scheduler died before science because the launcher omitted the two audit environment names required by the bound entrypoint. The automatic same-claim retry reused the unchanged launcher, so it is spending a second readiness window on the identical deterministic startup defect rather than reaching the sole economic measurement.

**Evidence.** The required one-shot Nebius reconciliation exactly matches claimed bench `h100-v0513-fp8qkv-r2-e00nmpn5czcb44jqm1` to RUNNING instance `computeinstance-e00nmpn5czcb44jqm1` and READY disk `computedisk-e00rd32znm10exgyy3`; the controller-host owner and watchdog are active, heartbeats advance about every 45 seconds, and both deadlines are future. The retrieved worker terminal at `12:32:30Z` is `integration_failure: server_not_ready` with `candidate_cuda_started=true` and `candidate_science_started=false`. Its server log gives the causal exception: `KeyError: 'FP8_MODULE_AUDIT'`. The launcher exported only `FP8_STACK_MODULE_AUDIT` and `FP8_STACK_CONSUMER_AUDIT` for `stack_sitecustomize.py`, while `proven_v0513_endpoint_entrypoint.py` independently requires `FP8_MODULE_AUDIT` and `FP8_CONSUMER_AUDIT`. The retry is still running under the same owner and claim; I did not signal it, touch the guest, release the bench, or mutate provider lifecycle.

**Change.** Added the two missing entrypoint audit aliases to the project launcher, pointing at the same module and consumer JSONL paths already used by the QKV stack. This changes neither model/runtime arguments nor the scientific intervention and will be staged by the next owner invocation by content hash. Shell syntax and an exact environment-contract check pass. The active process continues on its already-loaded script, so the change does not disrupt it.

**Expected effect.** If the unchanged retry returns the same pre-science failure, the director/researcher can reuse this exact claimed-or-released warm H100, restage only the corrected small launcher, and start the server without another checkpoint transfer, image pull, provider allocation, or scientific-arm replay. Judge the change by a server-ready marker followed by one c32 terminal on the retained resource, with no additional cold setup.
## 2026-07-22 — keep the current-runtime claim live during long staging

**Bottleneck.** The independent current-vLLM H200 owner made useful immutable-checkpoint transfer progress, but its shell harness did not renew the pool claim while blocking on transfer, image setup, and the endpoint run. It then stopped before CUDA on a recoverable working-directory error and misclassified the retrieved worker terminal because the outer harness checked the wrong path. Without an in-place repair, these integration defects could turn retained bytes into a stale-claim/reclaim cycle or cold restart before the objective-bearing endpoint arm.

**Evidence.** The one grouped authenticated Nebius listing exactly matches both registered live benches: runtime instance `computeinstance-e00s5ggxfqbn6ctb02` with disk `computedisk-e00pm4484qpn6nykmn`, and kernel instance `computeinstance-e00fpjxk4ww2g49apd` with disk `computedisk-e00nt4vk8nf3kgzy01`. Both provider instances are RUNNING, both disks READY, both controller-host watchdogs active, and both lifecycle deadlines future; no bench warrants draining. Warm reuse is working: the kernel H200 moved from the rejected partitioned-attention component to FP8 fusion without teardown, and both pre-CUDA fusion wiring faults were repaired on the retained bench. Fusion heartbeats continue every 45 seconds. In contrast, `gemma4-current-vllm-h200-20260722t1307z.service` stayed active through the complete 62.55-GB checkpoint transfer, but inventory's last runtime heartbeat remained `2026-07-22T13:08:31Z` with lease expiry `2026-07-22T14:08:31Z`; inspection showed no heartbeat loop. At `13:22:35Z` the owner exited into its retained repair boundary with no CUDA/science marker. Its remote stderr proves `sha256sum -c` ran from the checkpoint directory rather than the staged input directory, and retrieval placed the valid `integration_failure` worker terminal under `remote-retrieved/current-vllm-h200/` while the outer owner checked the parent. The claim and all remote bytes remain retained under the active lifecycle watchdog.

**Change.** Added the same simple 45-second pool-heartbeat pattern used by the healthy Python owner to the current-runtime shell owner, with cleanup on terminal and repair exits. Also made input-manifest verification run in the input directory, reconciled the actual nested worker-terminal path, and kept a retrieved integration/startup terminal in the claimed repair path when science has not begun. The service was not signaled, restarted, reclaimed, released, or otherwise disrupted; it reached its own repair boundary while this audit was in progress. The director should preserve the claim and exact runtime resource IDs above, then let the same researcher restage only these small corrected scripts and rerun against the resident checkpoint before the present lease expires.

**Expected effect.** The next bounded in-place repair should skip the completed checkpoint transfer, classify its remote terminal correctly, keep exclusive claim state aligned across image load/server startup/measurement, and reach the sole current-vLLM c32 arm. This removes a stale-claim/reclaim cycle without adding validation, a new project, cold setup, or scientific-arm replay.

## 2026-07-22 — restore portfolio continuity after hypothesis closure

**Bottleneck.** The director treated three terminal hypothesis results as permission to close the campaign, leaving no objective-bearing project even though `CAMPAIGN.md` makes the campaign perpetual until the user pauses it or authorized spend is exhausted. This is now the limiting factor to reaching the model-specific objective: the retained frontier is `0.689220` s/request against the `0.6381105231` ceiling, while the spend ledger still reports `$1.80` available.

**Evidence.** One grouped authenticated Nebius reconciliation returned no instances and no disks, exactly matching an all-retired inventory; there is no absent inventory object, unregistered provider object, live claim, owner/watchdog, passed live deadline, or bench requiring drain. The final kernel bench `h200-residual-kernel-e00fpjxk4ww2g49apd` (`computeinstance-e00fpjxk4ww2g49apd`, `computedisk-e00nt4vk8nf3kgzy01`) retired at `14:19:52Z`; the current-runtime bench (`computeinstance-e00s5ggxfqbn6ctb02`, `computedisk-e00pm4484qpn6nykmn`) had already retired at `13:59:18Z`. GPU events show the fusion researcher correctly retained and reclaimed the same kernel bench across the recoverable pre-CUDA artifact-isolation fault, then released it only after the repaired real-checkpoint arm produced a component-negative result; there was no cold restart between fault and repair. However, the director then retired the last bench and declared the campaign closed before admitting a successor. From `14:22Z` through `14:38Z`, `runtime/events.jsonl` records 17 consecutive `director_deferred` events with `unchanged_quiescent_lab` and four `supervisor_deferred` events with `unchanged_empty_quiescent_lab`, while every project remained terminal and `$1.80` remained available. The latest director trace explicitly says there is “no credible successor” and closes the campaign, contrary to the campaign's empty-portfolio prohibition.

**Change.** Recorded this once as a durable director handoff under the supervisor skill's empty-portfolio rule. No provider cleanup, inventory retirement, GPU state, project state, experiment, or scientific priority was changed. The director owns the scientific choice and should admit a materially different direct, objective-bearing experiment before another quiescent deferral, using the remaining authority; if no GPU arm fits `$1.80`, it should choose a cheaper scope-admissible falsifier rather than interpreting completed hypotheses as a campaign terminal. No further skill or harness patch is warranted because the campaign and supervisor skill already encode this rule.

**Expected effect.** The next director cycle should replace repeated empty-lab deferrals with one new objective-bearing admission consistent with the campaign contract, without the supervisor taking over portfolio selection. Future lifecycle cleanup should follow selection of the next compatible project where practical so recoverable warm state is not discarded prematurely.

## 2026-07-22 — make the retained static-FP8 repair schedulable

**Bottleneck.** The reopened portfolio is producing direct evidence on one shared warm H200, but the priority-1010 static-FP8 repair was invisible to the harness. Its owner reached a recoverable `fp8_scaled_mm` scale-shape ABI failure with no completed timing or numerical row, wrote a repair handshake, and kept the claim alive; three later cycles nevertheless deferred the researcher as `durable_session_active`. This stranded the only active scientific consumer at its repair boundary instead of patching and rerunning against resident state.

**Evidence.** The single grouped authenticated Nebius listing exactly matches inventory bench `h200-continuity-e00hzj9a8khp0fevy5` to RUNNING instance `computeinstance-e00hzj9a8khp0fevy5` and READY disk `computedisk-e00kw1vv5ytx76hxcp`; there are no unregistered or missing resources. The controller-host lifecycle watchdog and owner units are active in their recorded user-manager control groups, the claim heartbeat advanced to `16:07:43Z`, its lease extends to `16:52:43Z`, and the lifecycle deadline is `18:12:00Z`, so no drain is warranted. GPU events show useful warm reuse without provider teardown: current SGLang held the bench through checkpoint/image staging, partitioned attention immediately reused it for a decision-bearing negative, and static FP8 then claimed it. The static owner wrote project-root `REPAIR_READY.json` at `15:42:09Z` and waits until `16:18:27Z`, but `STATUS.json.active_session.artifact_root` pointed to `artifacts/`; additionally, the ready record supplied `absolute_repair_deadline_utc` while `_pending_durable_repair` accepted only `repair_deadline_epoch`. Consequently the `15:55:21Z`, `16:00:11Z`, and `16:03:19Z` cycles all deferred the project despite the director's immediate repair dispatch. About 26 minutes of a `$2.46/hour` claim elapsed by verification, mostly waiting after the integration boundary, while current SGLang's path-only retry remained correctly queued for the same warm bench.

**Change.** Corrected the live active-session repair root to the project directory and added the equivalent epoch deadline to the existing ready record, without touching the owner, claim, guest, serialized FP8 bytes, intervention, or scientific invocation. Hardened the shared harness deadline reader to accept either its existing epoch field or the documented absolute UTC form, and added a focused regression test. The scheduler predicate now resolves the live project root with an unconsumed, future repair handshake; both the existing epoch wake test and the new UTC-deadline test pass.

**Expected effect.** On the next harness cycle, the same project should emit `researcher_woken: durable_repair_ready`, patch only the scalar-to-per-row scale binding, refresh the small manifest, and write the request consumed by the already-running owner before its repair deadline. This should convert paid waiting time into the intended static-FP8 component result without checkpoint/image restaging, a new owner, a new project, or a cold GPU restart; after release, current SGLang can reuse the same bench for its already-prepared path-only retry.

## 2026-07-22 — drain the final warm H200 after the last compatible arm closes

**Bottleneck.** The final shared H200 is healthy and available, but there is no longer compatible queued work to justify retention. All objective-bearing residual-frontier projects are terminal, the spend ledger has `$0.00` unreserved authority, and the last admitted static-FP8 component has now produced a decision-bearing negative. Keeping the bench until its watchdog deadline would add idle cost without a route to the `0.6381105231 s/request` ceiling.

**Evidence.** One grouped authenticated Nebius listing at `16:52Z` reports only RUNNING instance `computeinstance-e00hzj9a8khp0fevy5` and READY disk `computedisk-e00kw1vv5ytx76hxcp`, exactly matching available inventory bench `h200-continuity-e00hzj9a8khp0fevy5`; there is no unregistered or missing provider object, claim, stale lease, or passed deadline. Controller-host watchdog `gemma4-continuity-h200-20260722t1443-watchdog.service` is active in its recorded user-manager control group through `18:12:00Z`. GPU events show effective warm reuse rather than teardown: standalone TensorRT-LLM released after a same-bench GPU-passthrough repair and measured `0.704970844 s/request` at 32/32; static FP8 then claimed the same bench for 88.401 seconds and measured a 20.55% M=32 regression, only a 2.22% M=2048 gain, and numerical-gate failure at both shapes before releasing at `16:51:21Z`. The generated status has no active project and reports the full `$200` cap reserved. From release to the lifecycle deadline, idle exposure is up to approximately `$3.31` at `$2.46/hour`. The inventory contents still describe the prior static owner failure because the researcher's `gpu_pool update --contents-json` command was rejected before its successful release; project terminals and logs contain the authoritative outcomes.

**Change.** Recorded a director-owned drain recommendation for exact bench `h200-continuity-e00hzj9a8khp0fevy5`, instance `computeinstance-e00hzj9a8khp0fevy5`, and disk `computedisk-e00kw1vv5ytx76hxcp`. I did not mark the healthy available bench draining, alter its stale descriptive contents, stop its watchdog, perform provider cleanup, retire inventory, change project state, or admit another experiment. No skill, shared-tool, or harness change is warranted: the measured integration repairs were consumed in place and the present constraint is exhausted authorized capacity, not scheduling or cold-restart behavior.

**Expected effect.** Unless the director can name an already-authorized compatible reuse before cleanup, it should mark this exact bench draining and perform its normal provider cleanup and later inventory retirement. That removes otherwise unavoidable idle exposure while preserving the retained `0.689220013 s/request` frontier and every negative runtime/static-FP8 artifact; supervision should not manufacture a new project or spend authority to keep the bench busy.

## 2026-07-22 — defer unchanged director turns after authorized capacity is exhausted

**Bottleneck.** After the latest harness source reload, an unchanged terminal lab began launching the director every cycle even though the campaign's valid exhausted-spend stop condition, empty portfolio, and empty GPU inventory were stable. This consumed coordinator time without a possible objective-bearing admission.

**Evidence.** The one grouped authenticated Nebius listing returned zero instances and zero disks, matching 15 retired inventory records and no live claim, owner, watchdog, deadline, or idle bench. The spend reservation map totals the full `$200` cap with `$0` available, all 122 project states are non-runnable, and the durable observation remains `35801db1...`. Nevertheless, four consecutive director turns from `21:28:31Z` through `21:33:13Z` consumed `101.773` agent-seconds and each returned the same terminal-hold decision. The deferral function unconditionally returned false for an empty runnable set, which is correct while authority remains but wrong for this fully exhausted and resource-empty state.

**Change.** Narrowed empty-portfolio deferral to the conjunction of no runnable project, no live bench, configured spend authority with `available_usd <= 0`, and an unchanged director observation. Empty labs with remaining or unbounded authority still wake the director, and any live bench still requires director disposition. Four focused harness tests pass, covering open empty replenishment, exhausted empty deferral, periodic supervisor safety audit, and live-bench director cadence. No project, scientific scope, GPU state, provider resource, or lifecycle record changed.

**Expected effect.** Stable funded-out labs should emit cheap `director_deferred: unchanged_quiescent_lab` events instead of one high-reasoning director turn per cycle, while a changed campaign, spend ledger, project artifact, supervisor handoff, or GPU inventory still wakes the director. This preserves the campaign's strict empty-portfolio rule whenever any experiment authority remains.

## 2026-07-23 — do not consume an arm when the candidate never reached workers

**Bottleneck.** The campaign is again producing objective-bearing endpoint evidence, but the latest scheduler-overlap project closed its no-retry arm after a candidate-labeled workload in which the candidate path was mechanically absent. This turns a recoverable worker-local installer-order defect into a terminal project and releases the warm bench instead of repairing the exact mutable environment that exposed it.

**Evidence.** The one grouped authenticated Nebius reconciliation at `03:15Z` returned exactly RUNNING instance `computeinstance-e00vhh6h29fj68x91g` and READY disk `computedisk-e00x25hxd1pnnxjn8b`, matching available inventory bench `h200-sync-linear-e00vhh6h29fj68x91g`; there is no unregistered or missing provider resource, claim, stale lease, or passed deadline. Controller-host watchdog `gemma4-sync-linear-h200-20260722t2226z-watchdog.service` is active in its recorded user-manager control group with main PID `3421402` through `2026-07-23T08:27:53Z`. The bench had been idle for about seven minutes at `$2.46/hour`, below the approximately 36-minute / `$1.48` measured cold-setup break-even, immediately after repeated same-resource claims and releases with no teardown, so retention through the next director selection is justified. In `gemma4_h200_scheduler_gap_pipeline_overlap`, iteration 2 correctly rebound the intervention to live `schedule_batch.py` hash `b6480f792867d7aba3dc39ef66048408c6c92ddad3ed81b23934493a351be459` and completed `32/32` requests with exact accounting in both arms. However, multiprocess startup reran the non-idempotent predecessor installer before scheduler installation; candidate and control audits are byte-identical (`93312a0b…`) and neither contains `Scheduler.run_batch.observed_source_schedule_stream_forward_penalty_snapshot`. Therefore `0.674524976 -> 0.674440688 s/request` (`0.0125%`) is control-equivalent noise, not a consumed scheduler candidate, despite `$1.08` cumulative project exposure.

**Change.** Clarified the shared researcher skill and generated researcher prompt: a candidate label alone does not consume an arm when mechanical path evidence proves candidate code was wholly absent. In that exact case, retain the same claim and resident state, repair only installation or injection, and rerun only the invalidated candidate invocation. The exception is forbidden when candidate bytes partially executed, path evidence is ambiguous, or any intervention, workload, identity, or decision gate changes. Added focused prompt assertions; the skill validator, Python compilation, targeted harness test, and diff check pass. I did not reopen the completed project, claim or drain the bench, change scientific priority, mutate provider lifecycle, or admit a successor.

**Expected effect.** Future worker-local injection or installer-order failures should reach the admitted candidate under the same warm owner instead of spending another endpoint setup, terminalizing on a control-equivalent run, or creating a support successor. The explicit partial/ambiguous-execution fence preserves genuine no-retry accounting while converting provably zero-candidate attempts into bounded in-place repair.

## 2026-07-23 — preserve a completed endpoint arm across a terminal owner repair

**Bottleneck.** The direct MTP endpoint lane has a valid exact c32 control and an unstarted candidate, but its durable owner finalized after an ordinary post-control validator defect. `STATUS.json` still tells the next researcher to run the whole control/MTP pair, so the existing generic terminal-session handoff risks replaying the already-complete control instead of repairing the validator and running only MTP. This delays the one active intervention capable of directly closing the gap to the campaign ceiling.

**Evidence.** The required single grouped Nebius reconciliation at `2026-07-23T06:47:53Z` reports exactly RUNNING instance `computeinstance-e00vhh6h29fj68x91g` and READY disk `computedisk-e00x25hxd1pnnxjn8b`, matching available inventory bench `h200-sync-linear-e00vhh6h29fj68x91g`; there is no unregistered provider resource, missing live inventory resource, claim, stale lease, or passed lifecycle deadline. The controller-host watchdog `gemma4-sync-linear-h200-20260722t2226z-watchdog.service` is active in its recorded user-manager control group with main PID `3421402` through `2026-07-23T08:27:53Z`. The bench had been idle for about seven minutes at `$2.46/hour`, with the exact MTP project still active and compatible with resident state, so reuse is justified and no drain is warranted. GPU events show repeated same-bench claims across scheduler, residual-H2D, MTP diagnostics, dense FP8, and W4/FP8 work without provider teardown. The prior supervisor correction also worked: the scheduler project repaired worker-local injection on this bench and produced a valid 32/32 candidate that regressed control by `0.017537%`, closing that mechanism on real evidence.

The MTP pair owner claimed the same H200 for `157.161` seconds, costing `$0.107393`, and persisted a passing `retrieved/control/TERMINAL.json`: 32/32 complete requests, exact `117728` fresh plus `17120` cached prompt-token accounting, and `21.578427489` batch seconds. It then called its stack validator with the control role configured to require an assistant-QKV path even though the control has no assistant. The owner terminal is `integration_failure: control.stacked_path_missing`; `INVOCATION_STATE.json` records `control_science_started=true` and `mtp_science_started=false`. The owner unit is now inactive, while project status still carries that dead session and the stale whole-pair action. This is a recoverable consumer/validator boundary after a durable producer result, not an MTP result and not a reason for cold setup.

**Change.** Added a narrow terminal-session repair handoff to the shared lab harness. When an inactive durable artifact root has a failed reconciled terminal, an `integration_failure` worker terminal, invocation-state markers, and persisted passing stage terminals, the next researcher prompt now names those completed stages and start markers. It directs the researcher to preserve every passing stage, repair only the invalidated validator/consumer or ordinary integration operation, execute only stages proven unstarted, and reclaim the same compatible warm bench when available; it explicitly forbids replaying a whole pair merely because the scheduled action is stale. Scientific incompatibility still reconciles terminal without replay. Added a focused regression reproducing a passing control plus unstarted candidate. All 39 harness tests, Python compilation, the repository DevEx check, and diff checks pass. I did not edit the MTP project, claim or probe the guest, change project or portfolio state, mark the bench draining, or mutate provider lifecycle.

**Expected effect.** On the next harness source reload and project turn, the researcher should reconcile the stale owner, retain the measured control, patch the impossible control-only stack assertion, and run only the unstarted MTP arm against resident H200 state. This should avoid another approximately 22-second exact control plus setup/reconciliation overhead, preserve no-retry accounting, and turn the remaining reservation into the direct candidate decision without teardown, cold restart, or a support project.

## 2026-07-23 — restore portfolio continuity after the MTP terminal

**Bottleneck.** The completed-arm repair worked and produced the direct MTP decision, but its final source-bound successor closed the lab's last active project. At `2026-07-23T07:21:17Z`, the generated portfolio has zero active or ready projects while the campaign remains explicitly perpetual, the retained stack is still above the `0.6381105231 s/request` ceiling, and the spend ledger reports `$63.072331` currently available. The limiting factor is now successor admission, not GPU execution or integration repair.

**Evidence.** The required single grouped Nebius reconciliation at `07:21:57Z` reports exactly RUNNING instance `computeinstance-e00vhh6h29fj68x91g` and attached READY disk `computedisk-e00x25hxd1pnnxjn8b`, matching available inventory bench `h200-sync-linear-e00vhh6h29fj68x91g`; there is no unregistered provider object, missing live inventory object, claim, stale lease, passed lifecycle deadline, or owner loss. Controller-host watchdog `gemma4-sync-linear-h200-20260722t2226z-watchdog.service` is active in its recorded user-manager control group with main PID `3421402` through `08:27:53Z`. The previous supervisor change had its intended effect: after a roughly 23-minute warm idle gap, still below the measured approximately 36-minute cold-setup break-even, the researcher reclaimed this same H200, preserved the passing `21.578427489`-second control, and ran only the unstarted MTP candidate. The claim lasted about `197` seconds and added `$0.1343476`; no checkpoint transfer, provider allocation, control replay, or teardown occurred.

The resulting MTP path is scientifically real and negative: 32/32 requests, 354 assistant forwards and target verifies, 4,880 accepted drafts, and 8,898 target/assistant QKV audit rows nevertheless took `40.968634829` batch seconds (`1.280269838 s/request`) versus the preserved `0.674325859 s/request` control, an `89.86%` regression. The director then kept the same project for one materially distinct overlap/serialization mechanism. Its deep researcher correctly avoided another claim: exact source and trace accounting show target verify alone costs `25.976945748` batch seconds (`0.811779555 s/request`), already `27.22%` above the entire ceiling, so overlap-only work cannot qualify. That project is now terminal with zero new GPU spend, and `runtime/status.json` lists no active project. The healthy bench has been idle since `07:07:36Z`; retaining it through the imminent portfolio selection is justified, but keeping it to its deadline without a compatible successor would cost up to roughly `$3.29`.

**Change.** Recorded this one-time empty-portfolio handoff for the director; no additional skill, shared-tool, or harness change is warranted because completed-stage preservation, warm reuse, active-owner deferral, and the offline GPU gate all behaved correctly. The director should admit a materially different objective-bearing experiment before another quiescent cycle. It should reuse exact bench `h200-sync-linear-e00vhh6h29fj68x91g` when the selected intervention is compatible with its resident H200 checkpoint/image/caches; otherwise it should mark that bench draining and clean exact provider resources `computeinstance-e00vhh6h29fj68x91g` and `computedisk-e00x25hxd1pnnxjn8b` through the normal director-owned lifecycle. I did not choose the scientific successor, alter project or spend state, claim the bench, mark it draining, stop its watchdog, perform provider cleanup, or retire inventory.

**Expected effect.** The next director cycle should replace the empty portfolio with a new direct or independently causal experiment derived from the latest residual telemetry, while making an explicit reuse-versus-drain decision before the warm-state break-even and lifecycle deadline. This preserves the successful no-replay workflow and converts the remaining authority into objective-bearing evidence instead of an idle H200 or repeated `unchanged_quiescent_lab` cycles.

## 2026-07-23 — replace the closed mixed-KV portfolio before warm-state expiry

**Bottleneck.** The E4M3/mixed-KV portfolio produced its preregistered decisions, but both final projects closed in the same cycle and left zero active or ready work at `2026-07-23T10:32:01Z`. The campaign remains open, the retained `0.674325859 s/request` qualified frontier is still above the `0.6381105231` ceiling, and the spend snapshot reports `$41.364619` currently available before the two terminal reservations settle. Successor admission—not GPU safety, setup, or integration—is again the immediate throughput constraint.

**Evidence.** The required single grouped Nebius reconciliation at `10:32:29Z` reports exactly RUNNING instance `computeinstance-e00vhh6h29fj68x91g` and attached READY disk `computedisk-e00x25hxd1pnnxjn8b`, matching available bench `h200-sync-linear-e00vhh6h29fj68x91g`; there is no unregistered or missing provider object, claim, stale lease, passed deadline, or owner loss. Controller-host watchdog `gemma4-sync-linear-h200-20260723t0800-watchdog-v2.service` is active in its recorded user-manager control group with main PID `3575964` through `12:30:00Z`. The bench was released at `10:30:17Z`, so retaining it through the next portfolio selection is below the measured cold-setup break-even; leaving it idle to deadline would add about `$4.91`.

Warm reuse and scientific gating otherwise worked. Uniform E4M3 KV was 4.1461% slower than E5M2. The subsequent layerwise path correctly proved 50 local E4M3 and ten global E5M2 producer/consumer routes, but its exact c32 result was still `0.7022734025 s/request`, 4.1445% slower than the frontier and indistinguishable from uniform E4M3. Its dependent local-FA3 component was numerically sound and reduced the producer-plus-consumer boundary by 24.0777%, but required 27.0671% merely to erase the mixed-KV penalty; the conservative projection was `0.6774124618 s/request`, so the endpoint was correctly not run. Both projects reused the same checkpoint/image/caches without provider teardown. Ordinary pre-science API, permission, and retrieval defects caused short release/reclaim gaps, but no scientific stage was replayed and cumulative FA3 exposure remained `$0.1585471`; the existing in-place-repair guidance is sufficient and does not justify another static rule.

**Change.** Recorded this one-time empty-portfolio handoff for the director. Admit a materially different objective-bearing replacement before another quiescent cycle, using the latest endpoint telemetry rather than reopening uniform E4M3, layerwise mixed KV, local FA3 tuning, window-512, NGRAM, or other closed arms. Reuse exact bench `h200-sync-linear-e00vhh6h29fj68x91g` if the selected experiment is compatible with the resident checkpoint, pinned SGLang image, and compiled caches; otherwise mark it draining and clean exact resources `computeinstance-e00vhh6h29fj68x91g` and `computedisk-e00x25hxd1pnnxjn8b` through the director-owned lifecycle. I did not choose the successor, alter project or spend state, claim or drain the bench, stop the watchdog, perform provider cleanup, or retire inventory. No skill, shared-tool, or harness change is warranted because warm reuse, stage preservation, and conditional measurement behaved correctly.

**Expected effect.** The next director turn should restore at least one direct or independently causal experiment and make the reuse-versus-drain decision while warm state remains economical. This prevents the completed local-KV branch from becoming an invalid campaign terminal and converts remaining authority into fresh evidence without wasting the retained H200 or replaying closed interventions.

## 2026-07-23 — wake a project-root repair handshake without releasing its owner

**Bottleneck.** The combined width-16,384 plus repaired E5M2 local-ring endpoint is the most direct remaining measurement against the `0.6381105231 s/request` ceiling, with an analytical composed estimate of `0.6127388539 s/request`. Its durable owner reached CUDA and proved both intervention paths, but candidate science remained unstarted because a pre-science smoke consumer incorrectly required coherent language from the already-declared incoherent width proxy. The director issued the correct bounded in-place repair, yet the scheduler repeatedly deferred its researcher: the active session declared `artifacts/repair1` while `REPAIR_READY.json` was written at the project root, and that ready record used `absolute_deadline_utc`, a deadline spelling the loaded predicate did not recognize. This was a repair-discovery deadlock, not a reason to release the warm owner, rerun components, or change the scientific portfolio.

**Evidence.** The required single grouped Nebius reconciliation at `2026-07-23T17:03:56Z` reports exactly RUNNING instance `computeinstance-e00vhh6h29fj68x91g` and READY disk `computedisk-e00x25hxd1pnnxjn8b`, matching claimed inventory bench `h200-sync-linear-e00vhh6h29fj68x91g`; there is no unregistered or missing provider object. Its claim heartbeat advanced to `17:03:19Z`, the lease extends to `19:33:19Z`, and the lifecycle deadline is `20:30:00Z`. Controller-host watchdog `gemma4-sync-linear-h200-20260723t1545-watchdog-v4.service` is active in its recorded user-manager control group with main PID `3724671`, so there is no stale claim, owner loss, passed deadline, or drain condition. GPU events show continuous same-bench reuse without provider teardown; the current combined owner claimed it at `16:34:04Z` and retained resident state.

The component evidence is objective-bearing: width 16,384 measured `0.6323543743 s/request` versus `0.6743258590` (6.2242% faster) with exact 32/32 accounting and path audits, although its outputs are explicitly quality-unsafe; the repaired contiguous E5M2 local ring measured `0.6556567115` versus `0.6766461551` (3.1020% faster), also with exact accounting and semantic/path gates. The combined owner has `candidate_cuda_started=true` and `candidate_science_started=false`. A project-root ready handshake set an `18:27:00Z` repair deadline, but no request existed; cycles at `17:00:30Z`, `17:01:30Z`, `17:02:30Z`, and `17:03:30Z` all emitted `researcher_deferred: durable_session_active` instead of waking the bounded repair.

**Change.** Hardened the shared harness repair detector to search the declared artifact root first and then the project root, while preserving request/terminal consumption checks, and to accept `absolute_deadline_utc` alongside the existing epoch and absolute-repair deadline fields. Added a focused regression that failed before the change and passes afterward. Because the running scheduler had already loaded the old source, corrected only the live session metadata: its artifact root now names the project root and its ready record also carries the equivalent `absolute_repair_deadline_utc`. The detector resolves that exact live project as pending; all 40 harness tests and Python compilation pass. I did not edit candidate science, write `REPAIR_REQUEST.json`, signal or restart the owner, alter the claim or watchdog, replay a component/control, touch the guest service manager, or mutate provider lifecycle.

**Expected effect.** The next scheduler cycle should emit `researcher_woken: durable_repair_ready`. The researcher can patch only the smoke consumer, require finite nonempty transport plus exact agreement with the persisted incoherent arithmetic response, and write the request before `18:27:00Z`; the existing owner can then run only the unstarted combined c32 candidate against resident state. This removes the release/reclaim and cold-restart risk while leaving the mirrored-ring project queued behind the active claim.

## 2026-07-23 — do not let a pre-call intent flag consume a zero-request endpoint arm

**Bottleneck.** The project-root repair-discovery fix had its intended effect, but the resumed combined width-plus-ring endpoint exposed a second ordinary wiring boundary. The worker set `candidate_science_started=true` immediately before launching the c32 runner; that runner then failed its first `/v1/models` probe on port 30000 while the newly loaded server was healthy on port 30001. No decision-bearing workload request reached the server, no request row or candidate terminal exists, and `ENDPOINT_RESULT.json` was never produced. Treating the conservative pre-call marker as proof of arm consumption would strand or terminalize the campaign's most direct remaining measurement after another recoverable integration error.

**Evidence.** The required single grouped Nebius reconciliation at `2026-07-23T17:17:18Z` reports exactly RUNNING instance `computeinstance-e00vhh6h29fj68x91g` and READY disk `computedisk-e00x25hxd1pnnxjn8b`, matching claimed bench `h200-sync-linear-e00vhh6h29fj68x91g`; there is no unregistered or missing provider object. Its heartbeat was current at `17:16:49Z`, its lease extends to `19:46:49Z`, and its lifecycle deadline is `20:30:00Z`. Controller-host watchdog `gemma4-sync-linear-h200-20260723t1545-watchdog-v4.service` is active in its recorded user-manager control group with main PID `3724671`; owner `gemma4-width16384-ring-stack-owner-repair1.service` is also active there with main PID `3738424`. No drain condition exists.

The prior supervisor change woke the researcher at `17:11:45Z`; it patched only the authorized smoke consumer, verified all 18 manifest inputs, wrote the request, and the same owner consumed it at `17:12:46Z` without release, reclaim, provider teardown, component replay, or control replay. The replacement server completed load and CUDA-graph capture, logged `GET /v1/models` 200 on port 30001 at `17:16:27Z`, and retained passing width/ring path evidence. The runner's fixed `BASE` is port 30000, so its first health probe raised `ConnectionRefusedError`; stdout is empty, `candidate/` contains only the immutable `WORKLOAD.json`, and the worker terminal is `integration_failure: candidate_runner_failed`. The continuous claim had cost about `$1.7730` by the audit; restarting cold would discard that retained setup while the exact unchanged workload remains unmeasured.

**Change.** Clarified the generated researcher prompt that a pre-call `*_science_started` marker records intent, not arm consumption by itself. When retrieved evidence proves the first health/model probe failed before any decision-bearing request was accepted and no request row or scientific terminal exists, the researcher must retain the owner and claim, repair only endpoint addressing or liveness, and run the unchanged workload. If any workload request reached the target or evidence is ambiguous, the arm remains consumed and retry is forbidden. Added focused prompt assertions; all 40 harness tests, Python compilation, and diff checks pass. I did not edit the active project script or handshake, write a repair request, signal/restart the owner, alter the claim/watchdog, or touch provider lifecycle.

**Expected effect.** After the harness reload, the pending ready handshake should wake the project researcher, who can bind the runner to the already-proven port 30001 and let the same owner execute the still-unstarted 32-request c32 workload before its `18:27Z` repair deadline. This converts the existing resident checkpoint, image, compilation, and path proofs into the intended combined endpoint result without a false no-retry terminal, release/reclaim, or cold model load; the mirrored-ring kernel owner remains queued behind the claim.

## 2026-07-23 — resume repair owners at the failed consumer, not the monolithic entrypoint

**Bottleneck.** The zero-request arm-consumption correction worked, but the durable owner still re-invokes the entire monolithic remote worker after each repair request. The port fix therefore reloaded the model, reran settled smoke/path work, and reached the unchanged c32 runner only to fail before its first probe because the previous zero-request attempt had left `candidate/WORKLOAD.json` and the runner requires a nonexistent output root. The arm is still unconsumed, but claim time is being spent replaying setup rather than measuring the combined endpoint that directly tests the `0.6381105231 s/request` objective.

**Evidence.** The required single grouped Nebius reconciliation at `2026-07-23T17:28:42Z` reports exactly RUNNING instance `computeinstance-e00vhh6h29fj68x91g` and READY disk `computedisk-e00x25hxd1pnnxjn8b`, matching claimed bench `h200-sync-linear-e00vhh6h29fj68x91g`; there is no unregistered or missing provider object. Its heartbeat advanced to `17:28:04Z`, its lease extends to `19:58:04Z`, and its lifecycle deadline is `20:30:00Z`. Controller-host watchdog `gemma4-sync-linear-h200-20260723t1545-watchdog-v4.service` is active with main PID `3724671`; claimed stack owner `gemma4-width16384-ring-stack-owner-repair1.service` is active with PID `3738424`, and queued mirrored-ring owner `gemma4-mirrored-ring-e5m2-owner.service` is active with PID `3741561` without a claim or provider spend. No drain condition exists.

The previous harness change woke the stack researcher at `17:23:53Z`; in 76.5 seconds it proved the prior attempt had zero accepted requests, changed only the runner base to port 30001, revalidated all 18 manifest inputs, and wrote the request. The same claim was preserved. However, the owner consumed it by executing `remote_combined_candidate.sh` from line one. The final server alone spent about 64 seconds loading weights and capturing graphs from `17:27:16Z` to readiness at `17:28:20Z`, after earlier smoke/path work in the same retry. At `17:28:28Z`, the runner failed `root.mkdir(..., exist_ok=False)` with `FileExistsError` on `/work/ring/endpoint-artifacts/candidate`. That root contains only the immutable 2,491-byte `WORKLOAD.json`; runner stdout is empty, there are no request rows, candidate terminal, or endpoint result, and the server was healthy on port 30001. The continuous claim had reached about 3,277.6 seconds and `$2.2397` by audit time, with no provider teardown but repeated in-claim model setup.

**Change.** Tightened only the generated durable-repair handoff. Before signaling an owner, the researcher must inspect its retry entrypoint and ensure the request resumes at the invalidated operation rather than blindly rerunning a monolithic worker that reloads the model or replays passing setup, smoke, or path stages. It must reuse a still-healthy server; when a pre-request consumer left a zero-request partial output root, atomically archive that root with its hashes and give the unchanged retry a fresh output path, never deleting or overwriting decision-bearing rows. Added focused repair-prompt assertions; all 40 harness tests, Python compilation, and diff checks pass. I did not edit the active project or owner, archive its live artifacts, write a request, signal/restart either owner, alter the claim/watchdog, or touch provider lifecycle.

**Expected effect.** After source reload, the pending handshake should wake the stack researcher to make the existing repair entrypoint resume directly at the c32 runner boundary, archive the zero-request `candidate/` residue, and use the healthy port-30001 server. The next request should therefore produce the first 32 decision-bearing rows without another checkpoint/model load, smoke/path replay, release/reclaim, or cold restart; afterward the queued mirrored-ring owner can claim the same retained H200.

## 2026-07-23 — do not advertise a full-HBM retained server as generally available

**Bottleneck.** The retained H200 was released `available` after a consumed static-c32 component even though its terminal server still occupied nearly all accelerator memory. The next, incompatible tied-head endpoint claimed that apparently free bench, repaired one pre-invocation marker defect in place, and then OOMed before accepting a workload. The scientific arm remains unconsumed, but objective-bearing endpoint time was replaced by another director maintenance round.

**Evidence.** The required one-shot authenticated Nebius reconciliation at `2026-07-23T20:58:06Z` returned exactly RUNNING instance `computeinstance-e00vhh6h29fj68x91g` and attached READY disk `computedisk-e00x25hxd1pnnxjn8b`, matching registered bench `h200-sync-linear-e00vhh6h29fj68x91g`; there is no unregistered or missing provider resource, claim, stale lease, passed deadline, or safety drain. Controller-host watchdog `gemma4-sync-linear-h200-20260723t1750-watchdog-v5.service` is active in its recorded user manager with main PID `3764663` through `2026-07-24T01:30:00Z`. The bench is correctly in `maintenance`, not idle or unsafe, and records terminal container `gemma-static-c32`, port `30001`, and `122,636 MiB` occupied.

GPU events show the process defect precisely. `gemma4_h200_static_c32_multitoken_decode_engine` released the bench `ready` at `20:21:53Z` while that terminal container remained resident. Priority-4500 `gemma4_h200_fp8_tied_head_endpoint` then claimed it at `20:40:45Z`, heartbeated through `20:45:15Z`, and accepted no smoke or endpoint request because the candidate process could not coexist in HBM. Its researcher took `627.572` seconds and conservatively records `$1.2721954466` cumulative exposure before releasing the bench to maintenance at `20:46:52Z`. This repeats earlier terminal-server conflicts that forced director removal of `mtp-depth-candidate`, `gemma-ngram-pair` / `gemma-ngram-control`, and `gemma-ring-candidate` before the next incompatible project could load. The campaign remains open against the `0.6381105231 s/request` qualified target with `$18.945995` unreserved; both current projects already carry an exact director-maintenance handoff, so I did not alter their states or choose a successor.

**Change.** Tightened only the shared researcher skill's release semantics. A loaded accelerator-resident server may now be released `available` only when an explicitly identified compatible successor can inherit that exact server without freeing memory. Otherwise the researcher preserves it but releases the bench to `maintenance` with the exact process/container, port, and memory occupancy for director reuse-versus-removal disposition. A recoverable same-project integration or consumer defect keeps its claim and owner instead of releasing either state; a healthy unoccupied bench remains promptly available. The skill validator and repository DevEx checks pass. I did not stop the current server, claim or drain the bench, change either scientific intervention, perform provider cleanup, or retire inventory.

**Expected effect.** Incompatible projects should stop claiming a bench that is only nominally free, avoiding several minutes of model startup, OOM diagnosis, and a second release/reclaim cycle. Compatible successors can still inherit resident servers, and recoverable owners still patch and rerun in place. Director maintenance should occur once, before the next incompatible claim, without adding a static validation ladder or a support project.

## 2026-07-24 — honor explicit single-bench queue order

**Bottleneck.** The prior full-HBM release correction worked, but two researchers launched concurrently against the same retained H200 and generic atomic availability overrode the director's explicit order. The lower-priority project claimed first despite a durable “prepare offline behind priority-4900” gate, so the higher-priority objective-bearing decode experiment completed its turn after preparation without running its frozen component.

**Evidence.** The required one-shot authenticated Nebius reconciliation at `2026-07-23T22:10:51Z` returned exactly RUNNING instance `computeinstance-e00vhh6h29fj68x91g` and attached READY disk `computedisk-e00x25hxd1pnnxjn8b`, matching available bench `h200-sync-linear-e00vhh6h29fj68x91g`; there is no unregistered or missing provider resource, claim, stale lease, passed deadline, owner loss, or safety drain. Controller-host watchdog `gemma4-sync-linear-h200-20260723t1750-watchdog-v5.service` is active in its recorded user manager with main PID `3764663` through `2026-07-24T01:30:00Z`. The bench had been genuinely empty and idle only since `22:07:57Z`, with exact compatible successor `gemma4_h200_static_c32_multitoken_decode_engine` recorded, so warm reuse is justified.

The previous supervisor change had its intended effect: the completed tied-head server was released to maintenance rather than advertised generally available, and director maintenance removed only that incompatible container, verifying zero compute processes, zero MiB, and zero utilization before returning the H200 ready. That enabled the exact E4M3 tied-head endpoint to produce a measured incremental win at `0.6518282820` versus `0.6556567115 s/request` (0.5839%), although it remains above the qualified `0.6381105231` ceiling.

The latest director then made priority-4900 `gemma4_h200_static_c32_multitoken_decode_engine` the first GPU consumer and explicitly told priority-4850 `gemma4_h200_fp8_tied_head_fused_greedy_top1` to “prepare offline behind priority-4900.” Both researcher turns nevertheless started at `21:51:35Z`. The lower-priority lane claimed the sole H200 at `21:53:34Z`; the priority-4900 researcher finished its implementation and had its one claim attempt refused at `21:55:12Z`, ending after `264.582` seconds with no CUDA invocation or new spend. The lower-priority claim continued until its terminal at `22:10:30Z`; its `1,135.081`-second turn and `$0.5128754151` exposure produced a valid but slower component reject. The higher-priority stream-ordered candidate remains active, scientifically unstarted, and now waits another cycle despite the H200 being free.

**Change.** Added one queue-order rule to the shared researcher skill. An explicit `PROJECT.md`, `STATUS.json`, or director instruction to prepare offline behind a named project or priority now overrides generic launch readiness: the lower-priority researcher may prepare, but cannot claim the shared bench until the named predecessor releases or the director changes the order. A momentarily available pool record no longer defeats that dependency. The skill validator, repository DevEx checks, and diff checks pass. I did not alter either project, claim the currently free bench, change reservations or scientific scope, mutate provider lifecycle, or choose a new hypothesis.

**Expected effect.** Sequential single-bench portfolios should execute in the director's decision order while preserving useful offline parallel preparation. The next comparable cycle should let the highest-priority ready experiment claim immediately instead of losing a full scheduler cycle to a lower-priority claim race; independent projects on different benches remain unaffected.

## 2026-07-24 — do not release a repairable claim from an unconditional finalizer

**Bottleneck.** The grammar-safe NGRAM experiment preserved its provider allocation but repeatedly relinquished and reclaimed the same warm H200 after ordinary owner and consumer defects. Its generated owners contradicted the lab's in-place repair policy by putting `gpu_pool release --condition ready` in unconditional `finally` blocks, turning recoverable exceptions into five claim boundaries during one experiment.

**Evidence.** The required one-shot authenticated Nebius reconciliation at `2026-07-24T01:48Z` returned exactly RUNNING instance `computeinstance-e00q45wf04571cb67n` and READY disk `computedisk-e00a75b8406tsvjg5d`, matching claimed inventory bench `h200-dflash-e00q45wf04571cb67n`; no provider resource is unregistered or missing. Its claim heartbeat was current at `01:46:46Z`, lease extends through `02:46:46Z`, and controller-host watchdog `gemma4-dflash-h200-20260723t2337z-watchdog.service` is active in its recorded user-manager control group with main PID `3881377` through `09:35:00Z`. The retired original H200 and disk are absent from both provider and live inventory as expected, so no safety drain is warranted.

GPU events for `gemma4_h200_ngram_grammar_safe_routing_endpoint` show claims at `01:16:45Z`, `01:18:07Z`, `01:22:14Z`, `01:26:15Z`, and `01:30:51Z`, with four intervening releases to ready before the final maintenance disposition. The trace identifies recoverable causes: a local inventory/CLI owner bug, missing entrypoint staging, and host-side rather than container-side c32 consumer invocation. Both `run_owner.py` and `run_candidate_owner.py` unconditionally released in `finally`, and the researcher explicitly reported that the owner had already released after the exception. No provider teardown occurred and later claims reused resident state, but every boundary discarded claim continuity and made cold restart possible. In contrast, the active DFlash lane has retained one claim since `23:40:50Z` through multiple pre-invocation build/import repairs, preserving its pinned checkout and image layers; it remains the only active objective-bearing project, with no workload yet accepted.

**Change.** Tightened only the shared researcher skill at the exact owner-construction boundary: an owner that can encounter recoverable pre-science or consumer exceptions must not place `gpu_pool release` in an unconditional `finally`. Release is gated on a terminal disposition; recoverable exceptions keep the heartbeat and claim active through the existing repair handshake, and a local owner bug is not grounds for immediate release/reclaim. This adds no validator, project, scientific gate, or static readiness step. The skill validator, repository DevEx check, and diff checks pass. I did not edit the completed NGRAM project, active DFlash owner or intervention, GPU inventory, claim, watchdog, provider lifecycle, or scientific portfolio.

**Expected effect.** Future integration failures should remain one mutable claimed session from diagnosis through patch and rerun, eliminating avoidable claim gaps and preventing another project or cleanup path from taking the warm bench between repairs. DFlash can continue building and testing unchanged; the next comparable owner should show one claim through all recoverable setup/consumer repairs and one release only at a scientific terminal, unsafe/unreachable guest, or absolute deadline.

## 2026-07-24 — replace the terminal overnight portfolio and decide both warm benches

**Bottleneck.** Both overnight GPU projects reached decision-bearing terminals in the same cycle, leaving no active or ready project while the campaign remains open, the `0.6381105231 s/request` qualified H200 objective is unmet, and `$48.139787` remains available. Successor selection and explicit warm-state disposition—not provider access, watchdog safety, or another integration rule—are now the limiting factors.

**Evidence.** The required one-shot authenticated Nebius reconciliation at `2026-07-24T03:32Z` returned exactly two RUNNING instances and two READY disks: DFlash H200 `computeinstance-e00q45wf04571cb67n` / `computedisk-e00a75b8406tsvjg5d`, and QServe L40S `computeinstance-e00a74kcbps8v00fk4` / `computedisk-e00svftc564m2pcp68`. They match the only two non-retired inventory records; no provider object is unregistered or missing. Controller-host watchdogs `gemma4-dflash-h200-20260723t2337z-watchdog.service` (PID `3881377`, deadline `09:35:00Z`) and `gemma4-qserve-l40s-20260724t0230z-watchdog.service` (PID `3941582`, deadline `08:30:59Z`) are active in their recorded user-manager control groups. There is no stale claim, passed deadline, lost watchdog, or safety drain condition.

The prior release-finalizer correction substantially improved useful continuity: DFlash retained one claim through its stale-path, overlay-probe, and launcher-argument repairs, and L40S retained its repaired claim through disk attachment refresh, filesystem growth, image pull, compilation, and the scientific packet. DFlash then executed target prefill, reached 100% GPU utilization and 131,052 MiB HBM, returned two first tokens, and closed because its tied Gemma embedding head cannot satisfy the pinned DFlash vocab-parallel greedy-head contract; its c32 pair was correctly not started. QServe produced correct finite production-shape rows and a 1.84–1.89x component speedup over online FP8, but the preregistered positive-extreme boundary was nonfinite and closed the fixed schedule. These are terminal local hypotheses, not campaign closure.

`runtime/status.json` now has no active or ready project, only an unrelated historical blocked L40S project. The DFlash H200 is unclaimed in maintenance with its exact target, draft, source, image, and caches resident but no healthy server; reuse is justified only if the director admits a compatible successor immediately. The L40S has been available since `03:11:07Z`, about 21 minutes at audit, retaining the pinned image and compiled SM89 extension with no authorized continuation. At `$0.8629833/hour`, that idle exposure is already about `$0.31`, comparable to its measured warm execution exposure; without an immediate compatible successor, drain is economically preferable.

**Change.** Recorded this one-time empty-portfolio handoff for the director. Admit a materially different objective-bearing experiment before another quiescent cycle; do not reopen consumed DFlash, unchanged QServe, native NGRAM, or another static validation project. Reuse H200 `h200-dflash-e00q45wf04571cb67n` only when the selected experiment can exploit its resident target/draft/image state, and reuse L40S `l40s-qserve-e00a74kcbps8v00fk4` only for a compatible SM89/image/cache consumer. Otherwise mark the corresponding benches draining and clean exact provider resources through the normal director-owned lifecycle. I did not choose a scientific successor, mark either bench draining, claim a GPU, stop a watchdog, perform provider cleanup, retire inventory, or alter either terminal project.

**Expected effect.** The next director cycle should restore at least one direct or independently causal experiment and make explicit reuse-versus-drain decisions before the two watchdog deadlines. This converts remaining authority into new model/workload evidence while avoiding up to roughly `$3.32/hour` of combined idle exposure and preventing terminal local hypotheses from becoming an invalid campaign stop.

## 2026-07-24 — make KV4 diagnostic retrieval atomic before reusing the warm L40S

**Bottleneck.** The director correctly replaced the terminal overnight portfolio and reused the retained L40S for exact-Gemma KV4, but two pre-science integration attempts each released the same bench to maintenance. The second repaired producer reached its remote worker and then failed in the owner’s compact-evidence fallback, so the active KV4 project again lost its claim before the resident diagnostic could be retrieved. The limiting factor is now this owner-side retrieval/release path, not hypothesis selection, static readiness, or GPU availability.

**Evidence.** The required one-shot authenticated Nebius reconciliation at `2026-07-24T07:13Z` returned exactly RUNNING instance `computeinstance-e00a74kcbps8v00fk4` and READY disk `computedisk-e00svftc564m2pcp68`, matching the only non-retired inventory bench `l40s-qserve-e00a74kcbps8v00fk4`; there is no unregistered or missing provider object. The controller-host watchdog `gemma4-qserve-l40s-20260724t0230z-watchdog.service` is active in its recorded user manager with main PID `3941582` through `2026-07-24T08:30:59Z`. The bench is unclaimed in maintenance, no deadline has passed, and no safety drain is warranted. Its image, checkpoint, compiled SM89 extension, immutable packet, and remote outputs remain resident with zero compute processes, zero GPU memory, and zero utilization. Exact compatible project `gemma4_l40s_qserve_kv4_attention_component` remains active with `$4` cumulative authority, so immediate reuse is economically justified at `$0.8629833/hour`.

GPU events show the avoidable boundary. The first immutable packet claimed at `07:00:03Z`, exposed the L40S for `28.060699` seconds / `$0.006726643`, and released to maintenance after Triton rejected illegal SSA tensor indexing before producer completion or a scientific terminal. The director correctly returned the same bench ready at `07:00:32Z` and admitted a pointer-only repair. That owner claimed at `07:12:17Z`, ran for `24.247039` seconds / `$0.005812441`, then released to maintenance at `07:12:41Z` with `typed_retrieval_boundary:compact_pack_failed`. Its compact fallback opened `compact.tar.gz` and then selected every file in the directory, including that archive itself; tar therefore failed while reading its own output. No compact diagnostic was retrieved, the durable owner is now inactive, and project `STATUS.json.active_session` still names that dead unit. This is a recoverable owner integration defect after about 52 seconds and `$0.0125390845` total claim exposure, not KV4 evidence and not a reason for another cold allocation or project.

**Change.** Replaced only the project owner’s compact-evidence command with an atomic `compact.tar.gz.part` build over the existing remote files while explicitly excluding both final and partial archive names, followed by a rename. The changed wrapper compiles, a narrow missing-terminal simulation packs and lists only `worker.stdout` and `worker.stderr`, and the diff check passes. I did not claim or ready the bench, replay the component, alter the KV4 representation or schedule, change project state, stop the watchdog, perform provider cleanup, or retire inventory.

**Expected effect.** The director should reconcile the dead active-session metadata, return exact bench `l40s-qserve-e00a74kcbps8v00fk4` ready, and continue the same KV4 project against resident instance `computeinstance-e00a74kcbps8v00fk4` and disk `computedisk-e00svftc564m2pcp68`. The corrected owner can retrieve whichever invocation or error files actually exist without self-including its archive, preserving the diagnostic needed for an in-place patch instead of another blind maintenance release. If the resident result is another ordinary pre-science integration boundary, the same claimed mutable session should repair and rerun before the absolute deadline; do not create a new project or cold bench.

## 2026-07-24 — keep retrieval failures inside the claimed AWQ repair session

**Bottleneck.** The prior KV4 archive fix had its intended effect: a retrieval-first owner reused the same L40S without CUDA replay, held one claim for about 44 minutes, recovered the resident constexpr diagnostic, and released only when the `08:15Z` repair window expired. Its exact-AWQ successor then repeated the release failure at a different archive boundary. The AWQ owner had a claimed repair handshake, but labeled bulk pack/SCP failures `typed_retrieval_boundary` while its exception path retained the claim only for messages beginning `recoverable_`; it therefore released to maintenance immediately after a recoverable retrieval fault.

**Evidence.** The required one-shot authenticated Nebius reconciliation at `2026-07-24T08:33:58Z` returned exactly RUNNING instance `computeinstance-e00a74kcbps8v00fk4` and READY disk `computedisk-e00svftc564m2pcp68`, matching the sole non-retired inventory bench `l40s-qserve-e00a74kcbps8v00fk4`; there is no unregistered or missing provider object. Controller-host watchdog `gemma4-awq-exact-l40s-20260724t1400-watchdog.service` is active in its recorded user manager with main PID `4033410` through `14:00Z`. The bench is unclaimed in maintenance, no deadline or stale claim exists, and no safety drain is warranted. At audit it had been idle for only `198.97` seconds / approximately `$0.0477`, retaining the exact checkpoint, pinned image, compiled SM89 extension, AWQ packet/data, and raw remote output. Retention through the imminent director decision is cheaper than cold reconstruction.

The AWQ owner claimed at `08:28:54Z`, staged immutable packet `e3bc8f…` and data `a98b0c…`, compiled the candidate to 127 registers with zero spills, and released at `08:30:39Z` after `104.074334` seconds / `$0.024948444`. `INVOCATION_STATE.json` proves the first M=1 candidate CUDA chain started, no candidate row completed, and the control never started because `sgl_kernel.fp8_scaled_mm` required column-major `mat_b`. The owner then wrote `retrieval.tar.gz` inside the directory it was archiving, returned `typed_retrieval_boundary:remote_pack_failed`, bypassed its `recoverable_` hold branch, and released. A 9,478,462-byte remote archive and the raw invocation evidence remained, allowing a later unclaimed retrieval, but the control-only same-session repair opportunity was already lost. This is process evidence, not a completed AWQ comparison.

The generated portfolio now contains no active or ready project, only this blocked AWQ project and an unrelated historical blocker, while the campaign remains open, the qualified `0.6381105231 s/request` objective is unmet, and `runtime/spend_cap.json` reports `$82.637673` available. The director must resolve the empty portfolio once: do not create a support project to replay the consumed AWQ candidate. If no same-project, no-replay disposition can use the resident evidence, admit a materially different objective-bearing experiment and reuse this L40S only when its resident state is compatible; otherwise recommend draining bench `l40s-qserve-e00a74kcbps8v00fk4` and normal director cleanup of instance `computeinstance-e00a74kcbps8v00fk4` plus disk `computedisk-e00svftc564m2pcp68`.

**Change.** Changed only `run_exact_outer.py`: the bulk archive is now built as a partial file outside the source directory and atomically renamed, so it cannot include or mutate itself. Pack and SCP failures are classified `recoverable_retrieval_failure`, which routes them through the existing `REPAIR_READY.json` heartbeat/claim hold rather than the maintenance release path. Python compilation, an archive simulation containing a partial invocation state, and diff checks pass. I did not claim or ready the bench, repair or replay AWQ, alter scientific gates, change project or portfolio state, stop the watchdog, perform provider cleanup, or retire inventory.

**Expected effect.** On the next comparable owner fault, evidence retrieval remains part of one mutable claimed session: the owner keeps heartbeating, the harness wakes the same researcher from `REPAIR_READY.json`, and a consumer/control-only repair or retrieval retry can use resident outputs without rerunning settled candidate work. The next director should separately replace the empty portfolio and decide reuse versus drain before the warm-state advantage or `14:00Z` lifecycle expires.

## 2026-07-24 — detach remote experiment owners from the SSH session

**Bottleneck.** The target-passing decode-equivalent NGRAM endpoint has reached
the campaign's direct production-quality gate, but its fresh paired
GPQA-Diamond/TauBench owner spent its first turn repairing four pre-result
integration failures. Two were ordinary packet/scorer defects; the other two
were lifecycle defects: a local SSH wrapper dropped the session and terminated
the remote worker, then a guest user-systemd unit was stopped when its SSH
launcher returned. No control score or candidate request had persisted at
either boundary. The current bounded `nohup` repair is alive under the original
claim, so the remaining bottleneck is durable remote ownership rather than
scientific portfolio selection, static validation, or GPU provisioning.

**Evidence.** The required single authenticated Nebius reconciliation at
`2026-07-24T11:10Z` returned exactly RUNNING instance
`computeinstance-e00kcm9nfhwt7e7gbc` and READY disk
`computedisk-e00yvdxaa48q0t115t`, matching the sole non-retired inventory bench
`h200-ngram-verifier-e00kcm9nfhwt7e7gbc`; there is no unregistered provider
resource or missing inventory resource. The bench has been continuously
claimed by
`gemma4_h200_ngram_decode_equivalent_production_validation` since
`10:50:28Z`, its heartbeat is `10:59:47Z`, lease extends through `14:59:47Z`,
and its lifecycle deadline is `17:00Z`. Controller-host watchdog
`gemma4-ngram-verifier-h200-20260724t1700-watchdog.service` is active in its
recorded user manager and control group with main PID `4051134`. No stale
claim, passed deadline, owner loss, or safety drain exists. Retention is
economically justified: the active semantic validation is using the resident
checkpoint/image and the compatible priority-6790 critical-path packet is
queued immediately behind it.

GPU events show warm reuse rather than provider churn. The same H200 served the
verifier and its corrected continuation, and no instance, disk, image, or
checkpoint was torn down between claim cycles. The latest production owner has
also correctly retained one mutable claim through its JSON-record parser,
GPQA scorer, SSH-child, and user-systemd repairs; it now records a
`remote-shell` PID-backed owner, fresh control capture in progress, and NGRAM
unstarted. Close-quality review found no project to reopen: the verifier
researcher called the 24-versus-41 tool-token difference a reject, but the next
director explicitly inspected the parsed tool payload and corrected that
conclusion to a performance survivor. The current fresh GPQA-Diamond/TauBench
comparison is the missing semantic and output-cost evidence required by
`CAMPAIGN.md`, not an observer-only or cumulative/delta close.

**Change.** Added the small shared
`research/factory/tools/detached-owner` primitive. It launches a guest command
in a new session with stdin disconnected and output redirected to a durable
log, atomically records its PID plus Linux process start time, labels the
manager `remote-shell`, rejects a second live owner under a file lock, and
reports status without relying on the guest's session-scoped systemd manager.
The command remains responsible for its experiment timeout, claim heartbeats,
terminal, and retrieval. Added concise shared-tool documentation and two
behavioral tests proving that the child survives launcher exit, later reports
completion, and cannot be replaced while live. Both tests, Python compilation,
and diff checks pass. I did not replace or signal the active `nohup` owner,
alter either scientific project, claim or release the bench, change the
watchdog, perform provider cleanup, or retire inventory.

**Expected effect.** Future paid owners can use one reproducible detached
launch path instead of discovering SSH-child and user-systemd session
lifecycle behavior on the GPU. The PID/start-time identity prevents a recycled
PID from being mistaken for the experiment, while duplicate-start rejection
protects the single-owner claim. On a comparable integration repair this
should preserve the resident server and claim through launcher exit, removing
one full model-start/retrieval cycle without adding another project, readiness
ladder, provider allocation, or scientific replay.

## 2026-07-24 — continue remote-shell projects when their agent slot frees

**Bottleneck.** The detached-owner improvement preserved the claimed H200
through two sustainable-cost consumer repairs, but the controller agent
returned just as the repaired remote process failed. The synchronous researcher
batch then waited for its independent 46-minute sibling before another lab
cycle could observe the dead owner. The quality-qualified NGRAM candidate
therefore spent the remainder of its short lifecycle idle instead of producing
the separate 10K and fixed-arrival sustainable-cost evidence required by
`CAMPAIGN.md`.

**Evidence.** The one permitted grouped Nebius listing at
`2026-07-24T14:09Z` returned exactly two RUNNING instances and two READY disks:
critical-path H200 `computeinstance-e00bwcwgsxawx1jmgw` /
`computedisk-e00ptxcxg2dwsg6xg6`, and verifier H200
`computeinstance-e00kcm9nfhwt7e7gbc` /
`computedisk-e00yvdxaa48q0t115t`. They exactly match the two non-retired
inventory benches. Controller-host watchdogs
`gemma4-ngram-critical-h200-20260724t1428-watchdog.service` (PID `4081483`)
and `gemma4-ngram-verifier-h200-20260724t1700-watchdog.service` (PID
`4051134`) are active in their recorded user-manager control groups. No
provider object is unregistered or missing.

The verifier bench was released at `13:59:43Z` after one continuous
variable-compaction claim; its checkpoint, image, JIT, and runtime caches are
resident. At audit it had been idle for about 15 minutes, approximately
`$0.15`, far below the campaign's observed checkpoint/model setup time and
cost. The campaign remains open and its NGRAM endpoint has just passed the
direct semantic gate: both AR and NGRAM scored GPQA-Diamond `55/198` and
TauBench `10/165`, while NGRAM used 18 fewer completion tokens and reduced
aggregate capture latency from `150.420s` to `85.398s`. Retain
`h200-ngram-verifier-e00kcm9nfhwt7e7gbc` through the next director portfolio
selection and reuse it for a compatible successor; do not drain it merely
because the two current mechanism realizations closed.

The critical bench was still represented as claimed by
`gemma4_h200_ngram_sustainable_cost_surface`, but its inventory heartbeat
stopped at `13:28:28Z`. One snapshot in the explicitly recorded
`remote-shell` namespace at `14:10:58Z` proved owner PID `38705` dead, no final
terminal, zero GPU utilization and zero MiB, and only
`INVOCATION_STATE.json`, `launch.json`, and pre-metrics persisted. The consumer
set `science_started=true` before its first 10K request returned HTTP 400 at
`13:30:06Z`; no valid 10K row or primary-stream sample exists. This is an
ordinary transport integration failure, not an arm-consumed marker or
sustainable-cost conclusion. The researcher completed at `13:30:29Z`, but the
parallel variable-compaction researcher did not complete until `14:08:36Z`,
creating about 38 minutes / `$1.56` of avoidable dead-owner exposure before
this supervisor turn. The project's `14:12Z` session deadline has now passed.

**Change.** Requested drain on registered bench
`h200-ngram-critical-e00bwcwgsxawx1jmgw`; because it is still claimed, the
atomic pool interface set `drain_after_release=true`. The director should
reconcile the invalid active session and clean exact instance
`computeinstance-e00bwcwgsxawx1jmgw` plus disk
`computedisk-e00ptxcxg2dwsg6xg6`; I did not release or reclaim the stale
project claim, stop its watchdog, perform provider cleanup, or retire the
inventory record.

Hardened only the shared harness batch boundary. When a researcher turn returns
with its project still active, a `remote-shell` session recorded, and the same
project holding a non-stale claim, the freed agent slot now runs one immediate
continuation before the harness waits for slower sibling researchers. That
continuation takes one owner snapshot without sleeping or polling: a live owner
gets an accurate handoff; a dead or terminal owner gets immediate retrieval,
stage-preserving reconciliation, and release/fence disposition. It can occur
only once per project per batch. A focused concurrency regression proves the
continuation runs before a slow sibling finishes, and all 41 harness tests,
both detached-owner tests, Python compilation, DevEx, and diff checks pass.

**Expected effect.** In the observed timeline, the continuation would have
found the dead PID and HTTP 400 within the same 13:30Z batch boundary, while
the independent compaction experiment kept running. The same researcher could
have preserved the invalid attempt and either repaired the unconsumed 10K
transport in the existing claim or released before the short deadline. Future
detached paid jobs should no longer wait for the slowest unrelated researcher
to finish before their owner exit is reconciled, reducing dead-claim exposure
without adding a validation ladder, support project, scientific replay, or
provider allocation.

## 2026-07-24 — continue a new remote owner once, not every cycle

**GPU audit.** The one grouped Nebius listing at `14:31Z` returned exactly
RUNNING instance `computeinstance-e00kcm9nfhwt7e7gbc` and READY disk
`computedisk-e00yvdxaa48q0t115t`. They exactly match the sole non-retired
inventory bench `h200-ngram-verifier-e00kcm9nfhwt7e7gbc`; no provider object
is unregistered or missing. The previously fenced critical-H200 instance and
disk are absent from both the live provider listing and the non-retired
inventory after director cleanup.

The verifier bench is claimed by
`gemma4_h200_ngram_sustainable_cost_surface`; its lease runs through
`16:47:11Z`, lifecycle deadline through `17:00Z`, and controller-host user unit
`gemma4-ngram-verifier-h200-20260724t1700-watchdog.service` is active in its
recorded control group with PID `4051134`. The same explicitly remote owner
PID `52118` was confirmed live at `14:30Z` with the valid `TEN_K.json`
persisted, the frozen 1,036-arrival primary stream active, no terminal yet,
100% GPU utilization, 128,514 MiB HBM, and 490.77 W. There is no stale claim,
passed deadline, available idle bench, lost owner/watchdog, or unsafe
registered resource to drain. `runtime/gpu_events.jsonl` also confirms the
recoverable sustainable-cost work moved directly onto this resident verifier
bench at `14:16:29Z`; no cold provider replacement was created.

**Bottleneck.** The completion-driven remote-shell continuation added in the
prior supervisor turn worked at the relevant boundary: after the repaired
researcher returned at `14:21:00Z`, the continuation started 16 milliseconds
later instead of waiting for another researcher or cycle. However, it was
keyed only to the current batch. Each later harness cycle therefore treated
the same unchanged PID, owner record, artifact root, and bench as eligible for
another immediate continuation. From `14:20:21Z` through `14:30:51Z`, four
cycles launched eight researcher observer turns totaling `239.654` agent
seconds; four were duplicate continuations totaling `118.173` seconds. The
last seven observations changed only instantaneous GPU telemetry while the
same primary stream remained live and produced no decision-bearing terminal.
Three ensuing director turns explicitly concluded that these snapshots did
not change the portfolio or lifecycle. This is observer work, not progress
toward the campaign's sustainable end-to-end cost decision.

The scientific closes remain appropriately scoped. The direct NGRAM candidate
is quality-qualified on fresh matched captures (AR and NGRAM both
GPQA-Diamond `55/198` and TauBench `10/165`; NGRAM used 18 fewer completion
tokens and reduced aggregate capture latency from `150.420s` to `85.398s`).
Variable-draft compaction closed on its measured implementation because
11.98% fewer target rows were 53.45% slower and failed c4 exactness. The first
sustainable-cost HTTP 400 consumed no valid arm; the director correctly
repaired and resumed the same project rather than treating it as a scientific
negative or opening a replacement project.

**Change.** Tightened only the shared harness continuation predicate. It now
captures the remote-session identity before each researcher turn from the
artifact root, bench, PID, owner/controller unit, and unit manager, and runs
the immediate continuation only when the turn establishes or relaunches a
different remote owner. An unchanged long-running owner receives no second
observer in the same cycle. The original concurrency regression still proves
that a newly established remote owner is continued before a slow sibling
finishes; a new regression proves that a pre-existing unchanged remote session
gets exactly one normal researcher turn and no duplicate continuation. Both
focused tests, all 42 harness tests, DevEx, and diff checks pass. The active
owner, claim, workload, watchdog, project contract, and provider resources
were not changed.

**Expected effect.** The fast failure-reconciliation path is preserved for the
integration boundary it was designed to protect, while the observed steady
stream would use four fewer observer turns over ten minutes. That frees about
half of the researcher-agent time currently spent watching an unchanged
remote job and avoids duplicate status/log churn and the director reviews it
triggers, without polling less at ordinary cycle boundaries, delaying a new
owner check, adding static validation, or changing scientific scheduling.

## 2026-07-24 — detach the claim controller, not only its guest worker

**GPU audit.** The one grouped Nebius listing at `15:44:42Z` returned exactly
RUNNING instance `computeinstance-e00kcm9nfhwt7e7gbc` and READY disk
`computedisk-e00yvdxaa48q0t115t`, matching the sole non-retired inventory
bench `h200-ngram-verifier-e00kcm9nfhwt7e7gbc`. No provider resource is
unregistered or missing. Controller-host watchdog
`gemma4-ngram-verifier-h200-20260724t1700-watchdog.service` is active/running
with PID `4051134` in its recorded user-manager control group, and the
lifecycle deadline remains `17:00Z`.

The bench claim is actionable but not unsafe: its last heartbeat was
`15:38:57Z` and its five-minute lease expired at `15:43:57Z`, 45 seconds before
the grouped audit. The recorded foreground controller PID `4167142` is gone,
but the explicitly remote detached worker was confirmed live in
`wave_admission_primary` at `15:43:43Z`, with no terminal yet. The claim still
names the correct active project and the watchdog remains healthy, so this is
not an objectively ownerless bench and I did not mark it draining. No
available idle bench exists.

**Bottleneck.** The wave researcher correctly used the shared detached owner
for its guest worker, but ran the outer claim/heartbeat/retrieval controller
as a foreground command tied to the agent turn. The controller heartbeated
every 45 seconds from `15:29:57Z` through `15:38:57Z`, then stopped when the
`938.723`-second researcher turn ended at `15:39:22Z`; the 12-minute
scientific arm had entered `wave_admission_primary` only at `15:36Z` and
continued remotely. The same turn spent much of its duration sleeping and
repeatedly observing the guest. Because `foreground-controller` is not a
durable harness owner, later cycles launched two more observer turns
(`25.423s` and `21.580s`) while the claim aged stale. A durable guest alone
therefore did not preserve claim freshness or guaranteed terminal retrieval.

Warm-bench reuse itself is healthy. The valid rolling surface completed
`1,036/1,036` requests at `$0.139109/M` finite-run cost but failed queue
stability after request 700. The next retained-H200 discriminator showed that
resetting the tiny online NGRAM corpus at request 650 did not move the
request-800 phase transition; corpus synchronization was only `47.4ms` across
8,483 prepares. Its semantic hashes were not valid cross-run comparators, so
the director correctly refused to accept the intervention, while the repeated
late backlog still validly rejects corpus lifetime as the timing cause. The
current fixed c32-wave admission is a serving-schedule discriminator based on
the already qualified c32 result, not a replay or an invalid scientific close.
The bench, checkpoint, image, and caches were reused throughout; no cold
provider replacement followed either recoverable integration error.

**Change.** Extended the existing shared `detached-owner` rather than adding a
new controller. It now accepts `--unit-manager pid` for a controller-host
outer owner while retaining `remote-shell` as the guest default. The harness
recognizes these local durable sessions only when both PID and Linux process
start time match `/proc`, so PID reuse cannot suppress a researcher turn. The
researcher skill, generated prompt, and shared-tool documentation now state
that any outer owner responsible for claim heartbeats, repair coordination,
retrieval, or release must itself be detached and recorded with the emitted
owner-state path, PID, start ticks, and `unit_manager: pid`; a detached guest
does not make a foreground controller durable.

Focused owner/PID tests, all 43 harness tests, skill validation, DevEx, Python
compilation through the tests, and diff checks pass. I did not alter the live
controller record, claim, guest worker, scientific arm, watchdog, project
contract, or provider resources.

**Expected effect.** A comparable 12-minute remote arm can return its
researcher immediately after launching one durable outer owner while that
owner keeps 45-second claim heartbeats, retrieves the terminal, and releases
at the recorded disposition. For the observed wave run this removes roughly
the final 12 minutes of turn-owned sleeping/remote observation, prevents the
claim from becoming stale mid-arm, and suppresses the two follow-up observer
turns while preserving the same warm bench and single scientific trajectory.

## 2026-07-24 — make recoverable repair retention executable

**GPU audit.** One grouped Nebius listing at approximately `16:57Z` returned
exactly RUNNING instance `computeinstance-e00kcm9nfhwt7e7gbc` and READY disk
`computedisk-e00yvdxaa48q0t115t`, matching the sole non-retired inventory
bench `h200-ngram-verifier-e00kcm9nfhwt7e7gbc`. There is no unregistered or
missing provider resource, claim, GPU process, stale owner, or passed
deadline. The controller-host user unit
`gemma4-ngram-verifier-h200-20260724t1900-watchdog.service` is active/running
with PID `4190394` in its recorded control group, and its `19:00Z` deadline is
still future. The H200 was available and unclaimed from
`16:56:43.785388Z`, with its exact checkpoint, pinned image, CUDA graph, JIT,
tokenizer, and runtime caches resident. This was less than one minute of idle
time at audit, immediately after a result and before the next portfolio
selection, so no drain is warranted.

The provider/inventory lifecycle is healthy and the same H200 was reused
throughout the latest work; there was no provider teardown, cold resource, or
checkpoint reload. The fixed-wave result is a valid sustainable-cost negative
for that policy: all `1,036/1,036` requests completed, but the 12-request tail
released `9.306848s` late and planning cost was `$0.140122/M`, just above the
campaign gate. The QLEN close is also correctly scoped. Observer-v3 proves the
unchanged compact-mask component exact and gives a measured positive
`6.55934%` whole-request bound. Its endpoint had zero candidate-path audit
rows and semantic mismatch, so the recorded `+33.69396%` service delta is an
integration observation, not evidence against the QLEN mechanism.

**Bottleneck.** The three QLEN continuations exposed the same process failure
the campaign explicitly asks us to avoid. Measured-v1 reached an unpatched
production consumer; repair-v2 compared the candidate against a malformed
global-row sliding observer; and observer-v3 first hit root-owned staging
files before science. Each was a recoverable consumer, observer, or staging
defect on the same reachable warm bench, yet the custom outer owner finalized
and released instead of retaining the claim for a repair handshake. The
release-to-next-claim gaps were `994.020s`, `638.418s`, and `127.758s`:
`29m20.196s` of paid unclaimed time, about `$1.203` at the inventory's
`$2.46/hour`, plus three director dispositions and repeated
maintenance/ready/claim transitions. The final component evidence is useful,
but none of that cadence moved the campaign's cost frontier.

At this supervisor boundary every schedulable project is terminal while the
campaign remains explicitly perpetual and the authoritative spend snapshot
still has `$32.9544` available after current reservations. That momentary
empty portfolio should last only until the next director turn: choose a
materially different objective-relevant experiment, and decide whether it can
reuse the warm H200 before considering drain. The supervisor does not choose
that experiment or authorize another QLEN endpoint replay.

**Change.** Added shared `research/factory/tools/repair-handshake`, a small
atomic coordination utility for the existing harness protocol. A durable
outer owner uses `ready` to write a deadline-bound failure diagnostic and
exact retry scope; the harness already wakes the same researcher, whose
`request` is SHA-256-bound to that precise ready record. `status` distinguishes
waiting, requested, expired, and terminal states. Conflicting scopes,
post-deadline requests, and overwritten requests fail closed. The tool does
not own heartbeats, select a repair, validate science, or authorize replay.
The researcher skill and shared-tool documentation now point owners to this
primitive instead of requiring every project to invent the two-file protocol.

Three focused handshake tests cover the hash-bound path, expired request, and
idempotent/conflicting ready records. All five shared owner/handshake tests,
all 43 harness tests, skill validation, DevEx, Python compilation, and diff
checks pass. No project brief, active experiment, claim, bench state,
watchdog, provider resource, or scientific artifact was mutated.

**Expected effect.** On the next ordinary integration failure, the outer owner
can keep one claim and heartbeat while exposing a deterministic wake signal,
then resume only the invalidated consumer on the resident environment. Applied
to the observed QLEN sequence, this would remove the three release/reclaim
boundaries and up to `29m20s` of same-project paid idle delay without adding
static validation, another project, or a cold restart. It preserves director
disposition for genuinely scientific or scope-changing repairs.

## 2026-07-24 — keep the repair owner on the controller host

**GPU audit.** One grouped Nebius listing at `18:24:30Z` returned exactly
RUNNING instance `computeinstance-e00kcm9nfhwt7e7gbc` and READY attached disk
`computedisk-e00yvdxaa48q0t115t`, matching the sole non-retired inventory
bench `h200-ngram-verifier-e00kcm9nfhwt7e7gbc`. Its claim for
`gemma4_h200_ngram_contiguous_swa_ring_stack` began at `18:20:13Z`; the
inventory heartbeat at `18:22:01Z` was current under the 300-second lease.
The recorded controller-host watchdog
`gemma4-ngram-verifier-h200-20260724t1900-watchdog.service` is active/running
with PID `4190394` in the exact recorded control group, and its deadline is
still future. There is no unregistered or missing provider resource, stale
claim, passed deadline, or reason to drain the claimed warm H200.

**Bottleneck.** The live-suffix repair produced useful direct evidence:
exactly the 1,024 live K/V tokens were byte-exact with zero duplicate physical
destinations. The required first Q12 consumer did not run, however: the
retained endpoint patch still routed target verification through stock extend
attention, emitted zero `ring_transition_decode` consumer rows, and the one
response diverged. This rejects the integration attempt, not the retained
ring mechanism. The researcher correctly identified that structural boundary
but prepared to release the healthy claim to maintenance instead of opening
the existing repair handshake.

The missed handoff has a concrete lifecycle cause. `STATUS.json.active_session`
remained null while the trace launched
`/home/glmrunner/gemma4-ngram-ring-live-suffix/OWNER2.json` on the guest with
`unit_manager: pid`. The harness therefore had no controller-host durable
owner or local repair root to observe and repeatedly deferred the director as
`unchanged_durable_sessions`. A guest PID cannot own controller-side claim
heartbeats, repair coordination, retrieval, or release, so the existing
handshake could not preserve this attempt automatically.

**Change.** Tightened the researcher skill's existing durable-owner rule:
`detached-owner --unit-manager pid` must be invoked directly on the controller
host, never inside SSH; its local command may run SSH to the guest. Only that
controller-local state path may populate `STATUS.json.active_session`.
Guest-side workers must remain `unit_manager: remote-shell` and must not be
copied into the controller lifecycle field. DevEx skill validation passes.
No project contract, running process, claim, watchdog, provider resource, or
scientific artifact was changed.

**Expected effect.** Future paid remote attempts will expose a locally
verifiable controller owner before launch. When a required consumer produces
zero audit rows or another ordinary integration boundary, that owner can keep
the same claim heartbeating, write `REPAIR_READY.json`, and let the harness
wake the same researcher to patch only the invalidated consumer. This avoids
the release/maintenance/reclaim boundary and preserves resident model and
server state without adding static validation or another project.

## 2026-07-24 — make repeated repair retrievals immutable

**GPU audit.** One grouped Nebius listing at `18:59:50Z` returned exactly
RUNNING instance `computeinstance-e00kcm9nfhwt7e7gbc` and READY attached disk
`computedisk-e00yvdxaa48q0t115t`, matching the sole non-retired inventory
bench `h200-ngram-verifier-e00kcm9nfhwt7e7gbc`. The controller-host watchdog
`gemma4-ngram-verifier-h200-20260724t2000-watchdog.service` is active/running
with recorded PID `36681` and exact control group; its deadline remains
future. The bench is unclaimed in maintenance. The researcher verified and
stopped orphan guest PID `115183`, found no scientific invocation marker or
running component container, and recorded the accelerator unoccupied.
Maintenance already fences reuse, so there is no stale claim, missing
resource, unsafe live worker, or reason for the supervisor to mark it
draining. The director has the exact instance, disk, and bench IDs for the
required maintenance-to-available disposition.

**Bottleneck.** The deep QLEN turn did reach the production two-stage branch,
but its first captured row was CUDA-graph setup geometry (`seq_len=1`,
`row_stride=13`, one KV index per request), not the admitted real request; it
was correctly invalidated and the endpoint stayed unconsumed. The same
controller then retrieved `REPAIR_READY.json`, restarted only the component
under the retained claim, and attempted another compact retrieval. Its local
`retrieve()` always created the same `retrieved/` directory with
`Path.mkdir()`. The second snapshot therefore raised
`FileExistsError(17, 'File exists')`; the broad exception handler released
the bench to maintenance after `381.4` claimed seconds and about `$0.2606`.
This is a retrieval/lifecycle failure, not evidence against QLEN. The
corrected component and conditional endpoint remain unconsumed.

**Change.** Added shared `research/factory/tools/artifact-snapshot`. It hashes
each retrieved tar archive and atomically extracts it under
`RETRIEVALS/<sha256>`. Repeating identical bytes is idempotent; a changed
repair snapshot receives a distinct immutable destination; an existing
unmarked conflict fails without mutation. Shared-tool documentation now
directs repeated monitoring, repair, and terminal retrieval passes to use
the returned content-addressed path instead of one mutable `retrieved/`
directory. Three focused tests cover idempotent replay, distinct evolving
snapshots, and fail-closed conflict preservation. All eight artifact,
repair-handshake, and detached-owner tests plus DevEx checks pass. No bench,
claim, watchdog, provider resource, project packet, remote process, or
scientific artifact was changed by the supervisor.

**Expected effect.** Future durable owners can retrieve an initial diagnostic,
an in-place repair snapshot, and a final terminal without colliding locally
or converting a recoverable integration defect into release/maintenance.
This removes the exact `FileExistsError` path observed here while preserving
hash identity, the existing claim/repair protocol, and resident warm state;
it adds no static science gate, project, or cold restart.

## 2026-07-24 — preserve adaptive-depth repairs and fence a lost watchdog

**GPU audit.** The single grouped authenticated Nebius listing at
`21:51:45Z` returned exactly RUNNING instance
`computeinstance-e00kcm9nfhwt7e7gbc` and READY attached disk
`computedisk-e00yvdxaa48q0t115t`. They match the sole non-retired inventory
bench `h200-ngram-verifier-e00kcm9nfhwt7e7gbc`; there is no unregistered or
missing provider object. The director made that warm bench available and the
same adaptive-depth project reclaimed it at `21:53:13Z`. Its controller-host
owner PID `134965` is live with the recorded start tick `104602323`, and the
claim heartbeat is fresh. The controller-host user-manager check for recorded
watchdog `gemma4-ngram-verifier-h200-20260724t2230-watchdog.service`, however,
returned `ActiveState=inactive`, `SubState=dead`, `MainPID=0`, and an empty
control group while inventory still records PID `105188`. This is an
objectively lost watchdog in the recorded namespace, not a guest-systemd
inference. I atomically set `drain_after_release=true` on the claimed bench;
the owner and experiment remain running, and I did not reclaim the claim,
stop a process, clean provider resources, or retire inventory. The director
must restore safe lifecycle coverage or, after release, clean exact instance
`computeinstance-e00kcm9nfhwt7e7gbc` and disk
`computedisk-e00yvdxaa48q0t115t`.

**Bottleneck.** The objective-bearing adaptive 12/6 draft-depth mechanism is
still unmeasured, not scientifically negative. The first warm claim was
released after about 40 seconds for a donor/archive integration defect. The
second reached real CUDA in both component phases but produced no comparable
terminal; its owner correctly opened an in-place observer repair, then read
shared `REPAIR_REQUEST.json` using legacy `packet_path` while
`repair-handshake request` emitted only canonical `patch_artifact`.
`KeyError('packet_path')` released the same compatible bench to maintenance
after `417.65` claimed seconds. There was no provider teardown and the warm
state was reused, but two recoverable integration boundaries still became
release/ready/reclaim cycles before the exact component terminal or
conditional endpoint. That controller/schema mismatch—not lack of projects
or static validation—is the immediate throughput bottleneck to measuring
whether load-adaptive depth reduces the late NGRAM drift.

**Change.** The shared `research/factory/tools/repair-handshake` now writes
an identical backward-compatible `packet_path` alias beside canonical
`patch_artifact` in every request. The shared documentation names both
fields, and the focused test asserts their equality. All 12 GPU-pool and
repair-handshake tests pass, as does `python3 tools/devex/check.py`. I did not
edit the active project controller, its frozen 12/6 rule, repair packet,
scientific artifacts, threshold, endpoint, claim, or provider resources.

**Expected effect.** Older and current durable owners can consume the same
hash-bound repair request without an exception, keep heartbeating the
existing mutable bench, patch only the failed observer/consumer, and proceed
to the exact adaptive component terminal without another maintenance and
reclaim boundary. The drain fence separately prevents a watchdog-less bench
from becoming available after this active owner exits; it gives the director
an explicit safe lifecycle disposition without disrupting the experiment
already in flight.

## 2026-07-24 — correct controller user-manager lifecycle checks

**GPU audit.** The one grouped authenticated Nebius listing at
`21:59:56Z` returned exactly RUNNING instance
`computeinstance-e00kcm9nfhwt7e7gbc` and READY attached disk
`computedisk-e00yvdxaa48q0t115t`, matching sole non-retired bench
`h200-ngram-verifier-e00kcm9nfhwt7e7gbc`; there is no extra or missing
provider object. The current claim heartbeat was fresh at `22:00:11Z`,
controller PID `134965` matched recorded start tick `104602323`, and both
the `22:20Z` owner deadline and `22:30Z` bench deadline were future. Crucially,
the watchdog metadata says `unit_manager: user`: querying the recorded
controller-host user manager with `systemctl --user` found
`gemma4-ngram-verifier-h200-20260724t2230-watchdog.service` active/running in
the exact control group with PID `105188`. The prior system-manager query was
a false namespace mismatch, not a lost watchdog. The director already
cancelled the false drain fence at `21:57:16Z`; the healthy claimed bench does
not warrant drain, cleanup, retirement, or an idle-cost recommendation.

**Bottleneck.** Warm reuse remains valuable and no cold restart occurred:
after the prior repair-schema failure released the bench at `21:48:59Z`, the
director made it ready at `21:52:07Z` and the same project reclaimed it at
`21:53:13Z`. The current owner has retained that claim through the next
recoverable boundary. The repaired observer now shows the objective-bearing
constraint precisely: all eight depth-12 reference requests completed, while
all eight depth-6 target-verify requests returned HTTP 500 after a fixed
depth-12 CUDA graph was replayed against live depth-6 geometry and triggered
an illegal CUDA memory access. No comparable component terminal or endpoint
sample exists, so this is a dynamic graph/metadata integration defect, not a
negative adaptive-depth result. The researcher has correctly localized the
narrow eager-target-verify repair and is applying it against resident state
under the same owner. The avoidable process cost in this interval was the
false drain plus a `146.606`-second director turn needed to verify the already
healthy watchdog and clear the fence.

**Change.** Tightened the reusable `research-supervisor` skill with an
explicit namespace mapping: use `systemctl --user` for `unit_manager: user`,
`systemctl` for `unit_manager: system`, and recorded PID plus start time for
`unit_manager: pid`; a result from the wrong manager cannot prove a unit
dead. The skill validator and repository DevEx checks pass. I did not edit
the active project, its repaired source, 12/6 rule, owner, claim, watchdog,
provider resources, component evidence, or conditional endpoint.

**Expected effect.** Future audits will not fence a healthy user-manager
watchdog after accidentally probing the controller system manager. That
removes an unnecessary drain/cancel round trip and director verification
turn, while allowing the current and future researchers to keep a compatible
warm bench claimed through ordinary integration repairs until they produce
decision-bearing Gemma component or endpoint evidence.

## 2026-07-24 — avoid shared-temp archive extraction failures

**GPU audit.** The one grouped authenticated Nebius listing at `22:27:12Z`
returned exactly RUNNING instance `computeinstance-e00kcm9nfhwt7e7gbc` and
READY attached disk `computedisk-e00yvdxaa48q0t115t`, matching sole
non-retired bench `h200-ngram-verifier-e00kcm9nfhwt7e7gbc`; there is no
unregistered or missing provider object. The bench is claimed by
`gemma4_h200_ngram_two_stage_target_verify`, controller PID `152784` is live
with matching start tick `104803622`, its heartbeat was fresh at
`22:28:29Z`, and the recorded controller-host user-manager watchdog is
active/running with PID `145440` through `01:00Z`. No claim, deadline,
lifecycle, or drain mismatch exists. Warm reuse is justified: the compatible
researcher has frozen and launched the two-stage packet against the resident
checkpoint/runtime, so teardown would discard useful state during the
objective-bearing run.

**Bottleneck.** Before claiming the H200, the researcher attempted to unpack
the retained installed-source archive with `mktemp -d` under shared `/tmp`.
Extraction failed with repeated `No space left on device`: the 32-GiB tmpfs
was 100% full while the workspace filesystem still had 372 GiB free. The
shared temp root contains 122 `tmp.*` directories, with many retained source
trees around 450 MiB each. The researcher recovered by streaming individual
archive members with `tar -xO`, then implemented, froze, and launched the
candidate, so no scientific arm or warm claim was lost. The failed extraction
and manual recovery are nevertheless avoidable local setup latency on the
path to the exact two-stage verifier result.

**Change.** The reusable `researcher` skill now directs large-archive
inspection to stream only required members and, when full extraction is
unavoidable, to use a project-local workspace-backed temporary directory
with cleanup installed before extraction. I did not delete shared temp
contents, edit the active project packet or controller, interrupt the claim,
or alter provider resources.

**Expected effect.** Future researchers avoid the exhausted 32-GiB tmpfs and
stop adding abandoned multi-hundred-megabyte extraction trees. Source
inspection proceeds directly to implementation and GPU measurement while
failed commands clean their project-local scratch state, without changing
scientific gates or warm-bench ownership.

## 2026-07-24 — release researcher turns after durable launch

**GPU audit.** The one grouped authenticated Nebius listing at `22:34:01Z`
returned exactly RUNNING instance `computeinstance-e00kcm9nfhwt7e7gbc` and
READY attached disk `computedisk-e00yvdxaa48q0t115t`, matching sole
non-retired bench `h200-ngram-verifier-e00kcm9nfhwt7e7gbc`; there is no
extra or missing provider object. The two-stage project claim heartbeat was
fresh at `22:33:44Z`, controller PID `152784` was live with matching start
tick `104803622`, and the recorded controller-host user-manager watchdog was
active/running with PID `145440` through `01:00Z`. The remote owner is live,
the fixed prefix is executing at 100% GPU utilization, and the researcher
reports healthy early-load behavior. There is no stale claim, passed
deadline, lifecycle mismatch, idle-cost issue, or reason to drain.

**Bottleneck.** After freezing and launching the durable controller, the
researcher correctly recorded `STATUS.json.active_session` and observed
forward progress, but then kept its deep-reasoning turn occupied with at
least 365 seconds of explicit sleep commands, nine repeated Nebius
`get_instance` lookups, and repeated SSH/GPU progress snapshots. The prefix
had no repair request or terminal to act on; early concurrency remained below
the intervention's eight-request trigger. The durable owner already handles
claim heartbeats, experiment progress, retrieval, and final release, while
the harness can resume the project on a terminal or repair boundary. These
polls therefore consume coordinator time and provider calls without
accelerating the objective-bearing measurement.

**Change.** The reusable `researcher` skill now says to return immediately
after one grouped snapshot proves a recorded durable controller is live,
heartbeating, and progressing. It explicitly forbids keeping the turn open
with sleep loops, repeated provider lookups, SSH progress checks, or GPU
polling, and names harness resumption on terminal or durable repair. I did
not interrupt or edit the active owner, candidate, packet, claim, watchdog,
or provider resources.

**Expected effect.** Long endpoint trajectories continue under durable
ownership while the expensive researcher slot becomes available within one
snapshot instead of several minutes. The same project is resumed only when
there is decision-bearing evidence or a repair action, reducing provider API
traffic and reasoning time without weakening heartbeats, telemetry,
retrieval, or warm-bench reuse.

## 2026-07-24 — recognize the live repair deadline alias

**GPU audit.** The single grouped authenticated Nebius listing at
`23:25:15Z` returned exactly RUNNING instance
`computeinstance-e00kcm9nfhwt7e7gbc` and READY disk
`computedisk-e00yvdxaa48q0t115t`, matching sole non-retired bench
`h200-ngram-verifier-e00kcm9nfhwt7e7gbc`; there is no unregistered or
missing provider object. The high-load-bypass claim heartbeat remained fresh
at `23:27:02Z`, controller PID `174152` matched start tick `105078364`, and
the controller-host user-manager watchdog was active/running in its exact
recorded control group under PID `145440` through `01:00Z`. The claim and
`00:50Z` owner deadline are valid, so there is no lifecycle, stale-claim,
idle-cost, or drain action.

**Bottleneck.** The candidate server exited before the first candidate CUDA
call and before any prefix persisted; the retrieved attempt terminal records
`ConnectionRefusedError` while reading post-run metrics and classifies the
attempt as a recoverable harness/runtime failure. The durable controller
correctly retained the same warm claim and wrote `REPAIR_READY.json` at
`23:24:38Z`, but named its future deadline `repair_deadline_utc`. The harness
recognized only `repair_deadline_epoch`, `absolute_repair_deadline_utc`, and
`absolute_deadline_utc`, so cycles through `23:26:03Z` continued emitting
`researcher_deferred: durable_session_active` instead of waking the same
project for the typed repair. This schema alias—not the scientific mechanism
or portfolio—is blocking the objective-bearing prefix.

**Change.** The shared harness now accepts `repair_deadline_utc` as a
backward-compatible bounded-repair deadline. A focused regression covers the
alias, and all 50 harness tests, Python compilation, repository DevEx checks,
and diff checks pass. The current repair-ready file also carries the
equivalent already-supported `absolute_repair_deadline_utc` field so the
running scheduler can cross its normal reload boundary without restarting
the controller. I did not change the frozen load rule, candidate, comparator,
owner, claim, watchdog, provider resources, or retry scope.

**Expected effect.** After the safe harness reload requested at `23:27:03Z`,
the same researcher should receive `durable_repair_ready`, inspect the
retrieved failure once, and submit a hash-bound in-place repair before
`00:44Z`. The controller can then retry only the invalidated operation
against resident state and produce the request-870 semantic/performance
terminal without releasing, reclaiming, reloading, or cold-starting the H200.

## 2026-07-24 — preserve PID-managed owners across harness reloads

**GPU audit.** The single grouped authenticated Nebius listing at
`23:33:05Z` returned exactly RUNNING instance
`computeinstance-e00kcm9nfhwt7e7gbc` and READY disk
`computedisk-e00yvdxaa48q0t115t`, matching sole non-retired bench
`h200-ngram-verifier-e00kcm9nfhwt7e7gbc`; there is no extra or missing
provider object. The recorded controller PID `174152` is objectively absent,
its final claim heartbeat is `23:27:47Z`, and the claim remains assigned to
`gemma4_h200_ngram_high_load_bypass`. The independent controller-host
user-manager watchdog remains active/running under PID `145440` in the exact
recorded control group through `01:00Z`. I marked the ownerless registered
bench draining (`drain_after_release: true`) without releasing the claim,
cleaning provider resources, or retiring the record. Director lifecycle
disposition must use the exact instance and disk IDs above.

**Bottleneck.** The previous deadline-alias fix worked: after the harness
restarted at `23:28:43Z`, the director admitted the typed repair and the same
project researcher started at `23:30:59Z`. It produced a hash-bound
metrics-persistence repair and `REPAIR_REQUEST.json` at `23:32:52Z`, but the
controller had already died and could not consume it. The causal timing and
service contract isolate the process failure: the harness requested a source
reload at `23:27:03Z`; the PID-managed owner emitted its last 45-second
heartbeat at `23:27:47Z`; the supervisor turn completed at `23:28:27Z`; and
the harness service, whose unit uses `KillMode=control-group`, restarted at
`23:28:43Z`. A POSIX session created by `detached-owner` survives its launcher
and SSH session but remains in the harness service cgroup, so the reload
killed the supposedly durable claim owner. No prefix or interpretable
candidate result persisted; this is an orchestration failure, not scientific
evidence against the high-load bypass.

**Change.** The shared harness now defers source reload while any active or
ready project has a live, start-time-matched `unit_manager: pid` session. It
records the blocking project IDs once per changed source and reloads normally
after those owners terminate; dead PID records do not block reload. A focused
regression proves a changed harness preserves a live PID session while the
existing no-owner reload behavior remains intact. All 51 harness tests,
Python compilation, repository DevEx checks, and diff checks pass. I did not
restart or replace the lost owner, submit another repair, alter the frozen
mechanism, create a resource, release the claim, or perform provider cleanup.

**Expected effect.** Future harness or supervisor edits cannot turn an
in-place recoverable integration failure into an ownerless claim. A live
controller continues heartbeats, consumes its hash-bound repair request, and
retries only the invalidated operation against resident state; the harness
loads new source after that controller reaches its normal terminal. For the
current already-lost owner, the drain fence prevents unsafe reuse and gives
the director an exact cleanup/recovery handoff without misclassifying the
unstarted prefix or cold-restarting it automatically.

## 2026-07-24 — isolate and reclaim leaked agent temporary workspaces

**GPU audit.** The single grouped authenticated Nebius listing at `23:52:40Z`
returned exactly RUNNING instance `computeinstance-e00kcm9nfhwt7e7gbc` and
READY disk `computedisk-e00yvdxaa48q0t115t`, matching sole non-retired bench
`h200-ngram-verifier-e00kcm9nfhwt7e7gbc`; there is no extra or missing
provider object. The repaired prefix released normally to maintenance at
`23:50:22Z`, the controller-host user-manager watchdog remains active/running
under PID `145440` in its recorded control group through `01:00Z`, and the
director correctly localized the result to a pre-bypass threshold-transition
failure: all 791 completed rows were exact, zero bypass steps ran, and the
remaining endpoint was not consumed. The same warm bench was reclaimed at
`23:55:39Z` for the admitted eight-request discriminator without teardown,
cold allocation, or model/checkpoint restaging.

**Bottleneck.** The controller host's 32-GiB `/tmp` tmpfs was 100% full with
98 stale temporary Git index/object directories. None was referenced by a
live process through an open descriptor, cwd, or root, and the standard
DevEx startup check already failed while flushing output with
`OSError: [Errno 28] No space left on device`. This can fail agent commands
and portfolio turns even while GPU execution is healthy.

**Change.** I removed only those unreferenced Git temporary directories older
than one hour, reclaiming `32,460,877,824` bytes and returning `/tmp` to 4%
usage. `CodexAgentRunner` now gives every child turn an isolated temporary
directory under that lab's durable trace filesystem through `TMPDIR`, `TMP`,
and `TEMP`, and removes it automatically when the child exits. A focused
regression verifies isolation and cleanup; all 52 harness tests, Python
compilation, and repository DevEx checks pass. No scientific contract,
provider object, claim, watchdog, or experiment process was changed.

**Expected effect.** Large temporary Git object stores cannot accumulate on
the small shared tmpfs across repeated agent turns. Agent launches, evidence
retrieval, and director decisions retain working temporary space while each
turn cleans its own files at its normal boundary.

## 2026-07-25 — fence an unowned live candidate after release

**GPU audit.** The single grouped authenticated Nebius listing at
`00:36:38Z` returned exactly RUNNING instance
`computeinstance-e00kcm9nfhwt7e7gbc` and READY disk
`computedisk-e00yvdxaa48q0t115t`, matching the sole non-retired bench
`h200-ngram-verifier-e00kcm9nfhwt7e7gbc`; there is no extra or missing
provider object. The controller-host user-manager watchdog remains
active/running under PID `145440` in its recorded control group through
`01:00Z`.

**Mismatch.** The metrics-guard controller and remote PID owner are both
terminal, a content-addressed component terminal was retrieved, and the claim
released the bench to available at `00:36:03Z`. The release record is unsafe:
its own final remote inspection says container PID `2531` is still running and
reports GPU process IDs `2805, 123374`, while the inventory simultaneously
claims `gpu_processes: none` and `server_state: Candidate container exited
cleanly`. No lifecycle owner or claim now governs those processes.

**Close-quality boundary.** The retrieved component terminal has eight rows,
zero request errors, and exact output-token, finish-reason, and usage matches
for all eight. It reports zero bypass/decode events and zero target rows
saved, so `component_reject` does not reject the high-load bypass semantics or
economics; it shows that the measured intervention did not activate in this
attempt. Portfolio disposition should preserve that distinction without
replaying any settled arm.

**Change.** I marked the registered bench `draining`. I did not stop the
container, clean provider resources, or retire the inventory record. Director
lifecycle disposition must use exact instance
`computeinstance-e00kcm9nfhwt7e7gbc` and disk
`computedisk-e00yvdxaa48q0t115t`.

**Expected effect.** The drain fence prevents another researcher from claiming
and mutating a bench whose released candidate is still live. The director can
inspect or clean the exact resource without racing a new experiment or
mistaking the terminal component result for proof that runtime cleanup
completed.

## 2026-07-25 — make terminal release fail closed on residual GPU work

**GPU audit.** The single grouped authenticated Nebius listing at `00:47:52Z`
returned exactly RUNNING instance `computeinstance-e00kcm9nfhwt7e7gbc` and
READY disk `computedisk-e00yvdxaa48q0t115t`, matching the sole non-retired
bench `h200-ngram-verifier-e00kcm9nfhwt7e7gbc`; there is no extra or missing
provider object. The controller-host user-manager watchdog is active/running
under PID `221596` in its recorded control group through `01:50Z`.

**Mismatch.** The corrected controller PID `225024` and remote owner PID
`7005` are terminal, the claim released at `00:48:02Z`, and the content-bound
terminal exists. The same release record nevertheless reports container PID
`7068` still running plus GPU process IDs `7305, 123280`, while stale fields
claim `gpu_processes: none` and `Candidate container exited cleanly`. No claim
or experiment owner governs those processes. I marked the registered bench
`draining`; provider cleanup and inventory retirement remain director-owned
for exact instance `computeinstance-e00kcm9nfhwt7e7gbc` and disk
`computedisk-e00yvdxaa48q0t115t`.

**Scientific boundary.** This is a lifecycle defect after a valid result, not
a reason to reject or replay the mechanism. The repaired eight-request
component is exact 8/8 with zero errors, 357 real bypass steps, preserved
cache/token invariants, and target rows reduced from `34,272` to `2,856`
(`31,416` saved). The admitted 80-request suffix is exact 80/80. Portfolio
disposition should use that evidence without replaying the component, settled
prefix, or suffix.

**Change.** The project owner harness now parses its final `docker inspect`
and `nvidia-smi` snapshot instead of unconditionally declaring a clean exit.
A running container, any GPU process row, an unparsable snapshot, or an
inspection error causes release to `maintenance`; only a clean stopped/empty
snapshot releases ready. The recorded `server_state` and `gpu_processes`
fields now agree with that decision. Python compilation, four focused parser
cases, and `git diff --check` pass. No active experiment, provider resource,
scientific contract, or terminal artifact was changed.

**Expected effect.** Future terminal retrieval cannot expose an ownerless live
GPU workload as an available warm bench. The director receives the exact
residual state for deliberate reuse or cleanup, while clean releases remain
immediately reusable and successful scientific evidence is not conflated with
process teardown.

## 2026-07-25 — retain recoverable wave failures and fail closed on release

**GPU audit.** The single grouped authenticated Nebius listing at `01:27:15Z`
returned exactly RUNNING instance `computeinstance-e00kcm9nfhwt7e7gbc` and
READY disk `computedisk-e00yvdxaa48q0t115t`, matching sole non-retired bench
`h200-ngram-verifier-e00kcm9nfhwt7e7gbc`; no provider object is extra or
missing. The controller-host user-manager watchdog is active/running under PID
`221596` through `01:50Z`. The project claim is non-stale, and controller PID
`244982` matches recorded start ticks `105856944`, so I did not drain or
otherwise disturb the active bench.

**Bottleneck.** Remote worker PID `16244` launched at `01:22:39Z` and was
already `live:false` by `01:27:16Z`, far earlier than the prior measured
`756.86`-second 1,036-request trajectory, while no `FINAL_TERMINAL.json` or
local retrieved attempt existed. The project owner source waited until the
absolute deadline when a dead worker lacked a typed terminal. Worse, any
retrieved `ATTEMPT_TERMINAL.json` followed the same path as a scientific
terminal: it removed the resident container and unconditionally released the
bench `ready`. Its cleanup path also trusted cleanup output without a
fail-closed container/GPU inspection. This converts a recoverable integration
failure into idle claimed time and a cold restart, and can expose residual work
as reusable.

**Change.** I changed only
`projects/gemma4_h200_ngram_wave_frontier_stack/run_owner.py`. A dead remote
owner now triggers immediate compact retrieval; a missing typed terminal is
classified from the retrieved owner log as a recoverable attempt. Unconsumed
attempts preserve resident state, write `REPAIR_READY.json`, and release to
`maintenance` for in-place director/researcher repair rather than deleting the
container. Completed terminals remove the candidate, then release `ready` only
when a parsed `docker inspect` plus `nvidia-smi` snapshot proves no live
workload; errors, malformed output, a running container, or any GPU row fail
closed to `maintenance`. The already-running controller is unaffected.
Python compilation, six focused inspection-parser cases, dead-worker and
maintenance-path assertions, and `git diff --check` pass.

**Expected effect.** Future wave attempts stop spending claim time as soon as
their worker dies, retain warm checkpoint/container state after ordinary
integration failures, and cannot advertise an uncertain GPU as ready. The
director can repair and rerun only the invalidated operation on exact instance
`computeinstance-e00kcm9nfhwt7e7gbc` and disk
`computedisk-e00yvdxaa48q0t115t` without a cold setup or duplicate scientific
arm.

## 2026-07-25 — drain after activation-repair owner loss

**GPU audit.** The single grouped authenticated Nebius listing at `04:00:14Z`
returned exactly RUNNING instance `computeinstance-e00kcm9nfhwt7e7gbc` and
READY disk `computedisk-e00yvdxaa48q0t115t`, matching sole non-retired bench
`h200-ngram-verifier-e00kcm9nfhwt7e7gbc`; there is no extra or missing provider
resource. The controller-host user-manager watchdog remains active/running
under PID `308560` through `04:30Z`.

**Mismatch and action.** Repair owner PID `329136` with recorded start ticks
`106767294` exited after writing `OWNER_EXCEPTION.json`, but the bench remained
claimed through a last heartbeat at `04:00:16Z`. The typed failure is
`recoverable_activation_proof_missing`: the correctly loaded overlay's
`patched_init` indexed positional argument `a[0]` even though SGLang invoked
the draft worker with keyword arguments, causing `IndexError` before the
requests-0-through-790 discriminator. No candidate science was consumed. I
marked the registered bench `drain_after_release`; provider cleanup and
inventory retirement remain director-owned.

**Expected effect.** The dead repair session cannot silently leave an
ownerless loaded H200 advertised as reusable. The director has the exact
instance/disk IDs and can deliberately reclaim this same warm bench for the
small keyword-argument activation repair, preserving resident checkpoint,
image, and caches rather than creating a project or cold resource. The failed
startup is implementation evidence only and must not reject or consume the
request-local verified-trunk mechanism.

## 2026-07-25 — stop chained repair-owner reloads

**GPU audit.** The single grouped authenticated Nebius listing at `04:11:20Z`
returned exactly RUNNING instance `computeinstance-e00kcm9nfhwt7e7gbc` and
READY disk `computedisk-e00yvdxaa48q0t115t`, matching sole non-retired bench
`h200-ngram-verifier-e00kcm9nfhwt7e7gbc`; there is no extra or missing provider
resource. The controller-host user-manager watchdog remains active/running
under PID `308560` through `04:30Z`. The claim heartbeat at `04:10:39Z` is
fresh and the prior `drain_after_release` safety fence remains set.

**Bottleneck.** After the original repair owner died, four replacement
controller PIDs (`335234`, `336704`, `338437`, and `339510`) also exited before
a valid discriminator. Activation was positively proved once, but later
attempts repeatedly restarted and reloaded the model, failed before request
release on metrics/server availability or retrieval, and one changed the
overlay hash. Candidate science remains unconsumed. This is repeated
integration setup, not evidence about request-local verified trunks.

**Change.** I added one narrow rule to the shared `researcher` skill: when an
outer owner and its first replacement both die before a valid sample, stop
launching replacement owners in that turn and preserve the typed failures and
resident state for deliberate recovery. A subsequent operation may continue
without restart on a healthy resident server, or use one unavoidable restart
for a newly proved startup defect; metrics/retrieval repair must preserve a
positive activation proof and cannot reload solely to re-prove it. No active
project file, scientific contract, provider resource, or running process was
changed.

**Expected effect.** Future recoverable integration failures retain the warm
bench without spending the remaining claim window on repeated model loads and
graph captures. Researchers return a decision-bearing repair boundary after
the second owner death, allowing the director to reuse or drain the exact
resource deliberately while preserving valid activation evidence and
unconsumed scientific arms.

## 2026-07-25 — enforce the campaign lane floor

**GPU audit.** The grouped authenticated Nebius listing at `05:09:51Z`
returned exactly RUNNING instance `computeinstance-e00kcm9nfhwt7e7gbc` and
READY disk `computedisk-e00yvdxaa48q0t115t`, matching sole non-retired bench
`h200-ngram-verifier-e00kcm9nfhwt7e7gbc`. Its controller-host user-manager
watchdog is active/running under PID `344296`; the completed-request claim
heartbeat is fresh, and PID-managed owner `374143` has the recorded start
ticks `107185555`. No GPU lifecycle mutation was required.

**Bottleneck.** `CAMPAIGN.md` explicitly requires at least two materially
independent performance lanes while budget permits, including one direct GPU
lane and one independent deep mechanism lane. At cycle `5562` the portfolio
contains only active priority-8500
`gemma4_ngram_completed_request_commit_gate`; the harness reports a free
researcher slot and remaining spend authority. Repeated preservation-only
director decisions therefore leave the final direct discriminator without
the required independent successor or parallel lane.

**Change.** I tightened the shared `research-director` skill by one sentence:
when a campaign sets an explicit lane floor, a preservation-only decision is
insufficient while researcher capacity and spend remain; the director must
admit a materially independent lane or record the concrete external blocker.
No active project, scientific contract, provider resource, claim, watchdog,
or running process was changed.

**Expected effect.** The next director turn selects the scientific lane rather
than waiting for the 791-request discriminator to close, preserving portfolio
continuity without serializing new model/workload evidence behind the current
warm-H200 run.

## 2026-07-25 — keep repair-ready owners alive

**GPU audit.** The grouped authenticated Nebius listing at `05:58Z` returned
exactly RUNNING instance `computeinstance-e00kcm9nfhwt7e7gbc` and READY disk
`computedisk-e00yvdxaa48q0t115t`, matching sole non-retired bench
`h200-ngram-verifier-e00kcm9nfhwt7e7gbc`. Its controller-host user-manager
watchdog remains active/running under PID `397483` through `07:15Z`; no
provider mismatch, deadline breach, or unsafe guest condition requires
draining.

**Bottleneck.** The v0.5.15 owner pulled and launched the bound official image,
then hit an ordinary pre-request Docker-socket permission error. Retrieved
evidence proves `science_started:false` and `candidate_sample_consumed:false`,
and `REPAIR_PATCH.json` already narrows the correction to running the
discriminator with permission while reusing the resident server. The outer
owner nevertheless returned immediately after writing `REPAIR_READY.json`,
stopping claim heartbeats and forcing a maintenance release at `05:56:55Z`
after about `$0.40` exposure. This is a lifecycle failure, not evidence against
the upstream runtime.

**Change.** I added `repair-handshake wait --root ARTIFACT_ROOT` to the shared
factory helper. It blocks a durable outer owner until a hash-bound repair
request, terminal, or absolute repair deadline while releasing the file lock
between checks so the researcher can issue the request. The tools README now
states that the owner's heartbeat thread must remain active and the owner must
not return merely because `REPAIR_READY.json` exists. Five focused handshake
tests, including request unblocking and deadline expiry, pass. No active
project, resident server, claim, watchdog, or provider resource was changed.

**Expected effect.** Future recoverable consumer defects keep the claimed warm
bench and durable owner alive long enough to patch and rerun only the
invalidated operation, avoiding maintenance handoffs, repeated image/model
setup, and false scientific rejection.

## 2026-07-25 — scope repair wakes to the current artifact

**GPU audit.** The grouped authenticated Nebius listing at `06:15Z` returned
exactly RUNNING instance `computeinstance-e00kcm9nfhwt7e7gbc` and READY disk
`computedisk-e00yvdxaa48q0t115t`, matching sole non-retired bench
`h200-ngram-verifier-e00kcm9nfhwt7e7gbc`. Its controller-host user-manager
watchdog remains active/running under PID `397483` through `07:15Z`. The H200
is available with the official v0.5.15 server resident for the admitted
endpoint; there is no provider mismatch or unsafe lifecycle state.

**Bottleneck.** The recovery run produced a valid 171-request discriminator in
`119.896` seconds: exact normalized semantics, zero failures, bounded release
drift, and native depth-12 activation, so the endpoint is admitted. While its
current owner was still live, the harness nevertheless emitted
`researcher_woken: durable_repair_ready` from the prior failed session's
project-root `REPAIR_READY.json`, whose `artifact_root` names the old
`v0515-discriminator-20260725t054742z` run rather than the current
`v0515-discriminator-20260725t060739z` run. That stale wake consumed a
redundant 155-second researcher turn.

**Change.** I narrowed the harness's legacy project-root repair fallback:
when a repair marker declares an `artifact_root`, it is eligible only if that
root matches the current `STATUS.json.active_session.artifact_root`. Unbound
legacy markers still fall back as before, and current-session repair markers
still wake the researcher. The focused current-session, legacy-fallback, and
stale-root regression tests pass. No project, scientific contract, owner,
claim, watchdog, or provider resource was changed.

**Expected effect.** Completed or superseded repairs no longer consume
researcher slots or interrupt live owners, while genuine current-session
repair requests retain the same immediate wake behavior.

## 2026-07-25 — require an exact endpoint terminal sentinel

**GPU audit.** One grouped authenticated Nebius listing at `06:19Z` returned
exactly the two registered resources: RUNNING H100 instance
`computeinstance-e00mfea030cdngg54z` with READY disk
`computedisk-e00y5knbt7nmzqeztk`, and RUNNING H200 instance
`computeinstance-e00kcm9nfhwt7e7gbc` with READY disk
`computedisk-e00yvdxaa48q0t115t`. Both controller-host user-manager watchdogs
are active/running: H100 PID `431508` through `07:45Z` and H200 PID `397483`
through `07:15Z`. The H100 was claimed at `06:25:03Z` for its compatible
v0.5.15 discriminator. The H200 endpoint owner claimed at `06:25:40Z`,
launched remote-shell PID `74086` against the resident server without reload,
but released the bench to maintenance at `06:26:05Z`. Maintenance prevents
reassignment and the watchdog remains healthy, so I did not drain, clean up,
or retire either provider resource. The director should preserve or recover
that exact H200 instance/disk and remote owner rather than cold-starting a
replacement.

**Bottleneck.** The admitted first-791-request endpoint did not reach a timing
or scientific terminal. Its outer launcher treated any occurrence of the
substring `ENDPOINT` in detached-owner status as proof that the standalone
`ENDPOINT` terminal sentinel had been emitted. The status necessarily contains
`ENDPOINT_OWNER.json` and `endpoint-stage`, so the first 20-second check
matched, retrieved an empty owner log with no `ENDPOINT_TERMINAL.json` or
`ATTEMPT_TERMINAL.json`, and released while the remote owner was reported
live. This is a recoverable endpoint-handoff defect on the warm server, not a
v0.5.15 result.

**Change.** I changed the endpoint harness's two sentinel checks from substring
matching to exact whole-line matching (`grep -qx`) for `ENDPOINT` and
`ATTEMPT`. `bash -n` and a focused false-positive/true-sentinel shell check
pass. I did not relaunch, claim, stop, or modify the active remote experiment.

**Expected effect.** Detached-owner metadata can no longer masquerade as a
scientific terminal. A recovered owner will keep heartbeating and wait on the
resident mutable H200 until the real endpoint terminal, repair terminal, or
deadline, avoiding an empty retrieval, premature maintenance release, and a
cold model restart.

## 2026-07-25 — repair the H100 owner's claim heartbeat

**GPU audit.** One grouped authenticated Nebius listing at `06:32Z` returned
exactly the two non-retired inventory pairs: RUNNING H100 instance
`computeinstance-e00mfea030cdngg54z` with READY attached disk
`computedisk-e00y5knbt7nmzqeztk`, and RUNNING H200 instance
`computeinstance-e00kcm9nfhwt7e7gbc` with READY attached disk
`computedisk-e00yvdxaa48q0t115t`. Both controller-host user watchdogs are
active/running under their recorded PIDs `431508` and `397483`. The H200 was
returned available for only `181.435` seconds and was re-claimed at
`06:33:23Z` by the bound retrieval-only project; no workload replay or cold
restart occurred. H100 PID `440810` and its checkpoint tar-to-SSH children are
live, with the immutable 62.6-GB staging transfer in progress. Neither bench
is ownerless, expired, unsafe, or unjustifiably idle, so I did not drain or
perform provider cleanup.

**Bottleneck.** The H100 claim's `heartbeat_at` remained at its initial
`06:25:03Z` value even though the durable owner was live. Its heartbeat thread
ran `gpu_pool heartbeat --project ... --bench ...`, but the shared pool's
heartbeat interface accepts only `--project`; every 45-second call therefore
returned argument error code 2 and produced no `claim_heartbeat` event. The
lease is still valid through `07:25:03Z`, so this was not yet a stale claim,
but it would make a healthy long staging/run appear stale five minutes before
the owner's `07:30Z` experiment deadline.

**Change.** I removed the unsupported `--bench` argument from the H100
execution owner's heartbeat command. Python compilation, AST parsing, and a
focused command-shape assertion pass. The already-running owner had loaded its
old code, so I did not restart, signal, or otherwise disturb its active
checkpoint transfer; its recorded PID/start ticks remain the authoritative
liveness evidence for this session.

**Expected effect.** Subsequent durable H100 owners extend the correct
project-bound claim every 45 seconds during long staging and server work,
preventing false stale-claim handoffs or competing recovery while preserving
the live mutable bench and expensive transferred state.

## 2026-07-25 — stage the H100 consumer packet on warm repair

**GPU audit.** One grouped authenticated Nebius listing at `07:02Z` returned
exactly the two non-retired inventory pairs: RUNNING H100 instance
`computeinstance-e00mfea030cdngg54z` with READY attached disk
`computedisk-e00y5knbt7nmzqeztk`, and RUNNING H200 instance
`computeinstance-e00kcm9nfhwt7e7gbc` with READY attached disk
`computedisk-e00yvdxaa48q0t115t`. Both controller-host user watchdogs are
active/running under recorded PIDs `431508` and `452824`, with deadlines
`07:45Z` and `08:00Z`. The H200 has a content-addressed 218-request
decode-attention discriminator admitted for its resident official v0.5.15
state, so its roughly 19-minute / `$0.78` idle interval remains justified
while the director makes the reservation durable. H100 repair PID `459828`
ended with a typed terminal at `07:02:42Z`; its last claim heartbeat was
`07:02:32Z`. The director detected that completed-owner/fresh-claim handoff
and created an exact same-bench repair binding, so I did not race it with a
drain or provider mutation.

**Bottleneck.** H100 repair-1 successfully started the digest-pinned official
server after reusing the verified 62.6-GB checkpoint, but no scientific
request ran. `--reuse-staged` skipped the separately staged 9.1-MB packet,
leaving remote `packet/h100_matched_runner.py` absent. The invocation also
omitted `UPSTREAM_REBASE_CONTAINER=gemma4-h100-v0515`, which would have made
the runner inspect its H200-default container name after the missing-file
repair. This is a recoverable consumer integration failure; the candidate
sample remains unconsumed.

**Change.** I changed the H100 execution owner to stage the small immutable
packet on both cold and reuse paths while continuing to reuse the checkpoint,
image, server, and caches. Both discriminator and conditional-endpoint
invocations now pass the explicit H100 container identity. Python compilation
and a focused owner-reuse assertion pass. I did not claim, restart, stop, or
otherwise mutate either bench.

**Expected effect.** The director-authorized repair can patch and rerun on the
resident H100 without another checkpoint transfer or cold allocation, and
future `--reuse-staged` recovery cannot repeat the missing-runner or
wrong-container failures before reaching the bound discriminator.

## 2026-07-25 — preserve the first H100 consumer failure

**GPU audit.** One grouped authenticated Nebius listing at `07:18Z` returned
exactly the two non-retired inventory pairs: RUNNING H100 instance
`computeinstance-e00mfea030cdngg54z` with READY attached disk
`computedisk-e00y5knbt7nmzqeztk`, and RUNNING H200 instance
`computeinstance-e00kcm9nfhwt7e7gbc` with READY attached disk
`computedisk-e00yvdxaa48q0t115t`. Their controller-host user watchdogs are
active/running under recorded PIDs `431508` and `452824`, with deadlines
`07:45Z` and `08:00Z`. H100 is safely fenced in maintenance after its owner
emitted a terminal and released its claim. H200 is available with the
corrected, compatible request-217 retry queued; at audit time it had been idle
for only about 2.5 minutes, approximately `$0.10` at `$2.46/hour`. There is no
missing provider resource, unregistered provider resource, dead lifecycle
process, stale claim, passed deadline, or unjustified idle bench, so I did not
drain or perform provider cleanup.

**Bottleneck.** The final H100 repair reached the immutable matched runner and
started the official server, but still consumed no candidate request. The
server log measured `10.63 GB` available after graph capture and `1.06 GB`
used by the target-verify graph, while the runner's exact-string observer
looked only for the older generic CUDA-graph label and raised
`fit_log_field_missing:post_graph_available_gib`. This is an observer-boundary
failure, not a content-bound fit rejection. The mutable outer owner then
ignored that nonzero runner exit, attempted to retrieve an absent
`FINAL_TERMINAL.json`, and replaced the actionable cause with a generic
`FileNotFoundError`.

**Change.** I added return-code guards to both discriminator and conditional
endpoint paths in the mutable H100 execution owner. The owner still persists
runner stdout, stderr, and server logs first, but now raises the original
runner failure before terminal retrieval. Python compilation and focused
ordering checks pass. I did not modify the immutable packet, fit gate, claim,
bench state, or launch another retry.

**Expected effect.** The director will receive the first actionable consumer
error directly instead of spending another forensic turn reconstructing it
from side artifacts or mistaking it for a scientific rejection. The current
H100 remains in maintenance; the director retains ownership of any
parser-only repair, warm reuse, or drain decision.

## 2026-07-25 — derive staged packets from their manifests

**GPU audit.** One grouped authenticated Nebius listing at `07:25Z` returned
exactly the two non-retired inventory pairs: RUNNING H100 instance
`computeinstance-e00mfea030cdngg54z` with READY disk
`computedisk-e00y5knbt7nmzqeztk`, and RUNNING H200 instance
`computeinstance-e00kcm9nfhwt7e7gbc` with READY disk
`computedisk-e00yvdxaa48q0t115t`. Their controller-host user watchdogs are
active/running under the recorded PIDs `431508` and `452824`, with deadlines
`07:45Z` and `08:00Z`. During this review the director validated the H100
observer repair and returned that bench available, then dispatched both warm
projects. H200 was claimed at `07:29:04Z` by controller PID `490837`; its
recorded start ticks `108056212` match `/proc`. H100 had been available for
about 3.4 minutes, roughly `$0.17`, with its exact 171-request observer repair
queued. No provider/inventory mismatch, dead lifecycle process, stale claim,
passed deadline, unsafe bench, or unjustified idle interval warrants a drain.

**Bottleneck.** The request-217 H200 discriminator remained unconsumed after
two consecutive pre-sample claims of `7.532` and `5.927` seconds. The first
manually enumerated tar omitted manifest-required `DIRECTOR_BINDING.json`; its
replacement included that file but omitted `analyze_localization.py` and the
manifest-bound `source/` tree. The direct claim cost was only about `$0.0092`,
and the warm server/checkpoint were correctly retained, but the second member
list duplicated the packet manifest imperfectly and delayed the first real
candidate attempt from `07:11Z` until the final warm claim at `07:29Z`.

**Change.** I added shared `research/factory/tools/manifest-pack`. It constructs
the archive membership directly from either supported packet-manifest schema,
includes the manifest itself, verifies declared sizes and SHA-256 values before
writing, rejects unsafe paths and symlinks, and atomically publishes the tar.
This replaces the independent hand-written tar member list rather than adding
another validation gate. Three focused tests pass, and a read-only application
to the actual request-217 packet produced exactly 19 members: all 18 declared
files plus `PACKET_MANIFEST.json`. I did not alter either active project's
bound packet, claim, owner, or launch.

**Expected effect.** Future warm repairs cannot repeat this class of
manifest-member omission: packet construction fails locally before a claim or
stages the complete hash-bound packet. This should convert the observed
roughly 18-minute two-repair detour into one local construction step while
leaving scientific admission and retry decisions with the director.

## 2026-07-25 — fence an endpoint that cannot fit its watchdog

**GPU audit.** One grouped authenticated Nebius listing at `07:56Z` returned
exactly the two non-retired inventory pairs: RUNNING H100 instance
`computeinstance-e00mfea030cdngg54z` with READY disk
`computedisk-e00y5knbt7nmzqeztk`, and RUNNING H200 instance
`computeinstance-e00kcm9nfhwt7e7gbc` with READY disk
`computedisk-e00yvdxaa48q0t115t`. Both controller-host user watchdogs were
active/running in their recorded control groups under PIDs `505530` and
`511603`; the H100 durable PID owner `510004` also matched its recorded start
ticks. H200 was available for about two minutes with the exact compatible
stock multiplex experiment queued, so its idle cost remained justified. H100
had a fresh claim and heartbeat, but its `07:55Z` scientific deadline had
passed and its independent lifecycle watchdog was due at `08:00Z`. I marked
registered bench `h100-v0515-ngram-e00mfea030cdngg54z` draining after release.
The director should extend or terminate it using the exact instance and disk
IDs above. I did not stop the live owner, clean up provider resources, or
retire inventory records.

**Bottleneck.** Repair 5 produced a valid persisted discriminator terminal:
all `171/171` requests completed with zero failures, normalized semantics,
native depth-12 NGRAM activation, bounded release drift, and endpoint
admission. Its measured service time was `0.7073339939` seconds/request. At
`07:57Z` the admitted 791-request endpoint had no local terminal while its
owner remained live. The mutable owner wraps that arm in a minimum 600-second
timeout and the server restart in a 1200-second timeout even when less
lifecycle time remains. The measured request rate alone implies about 559.5
seconds for the endpoint, before restart and retrieval, so the arm could not
finish safely before the provider watchdog. The real throughput loss is
deadline-insensitive conditional execution racing lifecycle cleanup, not a
lack of validation or project ideas.

**Change.** I updated the shared researcher skill to derive every blocking
timeout from the remaining absolute owner/lifecycle time and to avoid starting
a conditional arm whose measured or conservative duration plus retrieval
cannot fit. In that case the owner must preserve the completed stage and emit a
typed handoff. This changes runtime decision geometry rather than adding a
static readiness gate. I left the active H100 process and both scientific
packets untouched.

**Expected effect.** Future owners should retain valid discriminator evidence
and request a bounded extension or handoff before launching an endpoint that
cannot fit, avoiding cold restart or watchdog teardown after a recoverable
integration sequence. The director keeps authority over extension, reuse, and
provider cleanup.

## 2026-07-25 — bind remote access identity to the current bench

**GPU audit.** One grouped authenticated Nebius listing at `08:21Z` matched
the inventory exactly: RUNNING H100 instance
`computeinstance-e00jjdbxgvxwbzbfsr` with READY disk
`computedisk-e00hf9gkq3ee80yhvp`, and RUNNING H200 instance
`computeinstance-e00kcm9nfhwt7e7gbc` with READY disk
`computedisk-e00yvdxaa48q0t115t`. Both controller-host user watchdogs were
active/running in their recorded control groups under PIDs `528520` and
`511603`. H200 had a fresh claim, heartbeat, live durable owner, and active
stock/candidate science. H100 was in maintenance after a roughly 119-second
claim, with its watchdog still healthy and a same-bench repair already bound;
its short idle cost was justified by compatible recovery and resident state.
No bench was missing, unregistered, stale, past its lifecycle deadline, or
objectively ownerless, so I did not drain, clean up, or retire anything.

**Bottleneck.** The H100 claim failed before any candidate or endpoint sample
because remote preflight tried retired bench address `195.242.29.133` and
timed out. The current healthy replacement is the exact instance and disk
above at `89.169.112.211`; the director has already bound that address for a
same-bench preflight repair. The replacement bench registration persisted
provider resource IDs but not its connection identity, allowing a launcher to
inherit the old address. This lost one claim/release cycle to an ordinary
integration error while the expensive resident bench remained usable.

**Change.** I updated the shared research-director skill's provider
registration contract: remote benches must persist their resolved host/IP,
SSH user, and known-hosts namespace (or equivalent) in the current registered
resource metadata, and launchers must consume that identity rather than reuse
one from a retired or replaced bench. The existing GPU-pool schema already
accepts these resource fields, so this is a small durable handoff correction,
not another static validation gate. I left the active H100 recovery and H200
experiment untouched.

**Expected effect.** Future replacement benches should hand researchers the
correct access endpoint with the claim, preventing stale-host preflight
failures and preserving warm state for patch-and-rerun recovery. The current
H100 lane can continue its already-bound same-bench repair without cold
allocation or teardown.

## 2026-07-25 — make science-start markers mean actual invocation

**GPU audit.** One grouped authenticated Nebius listing at `08:36Z` matched
the inventory exactly: RUNNING H100 instance
`computeinstance-e00jjdbxgvxwbzbfsr` with READY disk
`computedisk-e00hf9gkq3ee80yhvp`, and RUNNING H200 instance
`computeinstance-e00kcm9nfhwt7e7gbc` with READY disk
`computedisk-e00yvdxaa48q0t115t`. H100's controller-host user watchdog was
active/running under PID `528520`; its fresh claim was heartbeating and
durable owner PID `548568` matched start ticks `108443676`. During the audit,
the director atomically replaced the H200 watchdog with active controller-user
unit `gemma4-ngram-verifier-h200-20260725t0930-watchdog.service` under PID
`549916`, so the inactive superseded 08:50 unit was not a dead lifecycle.
H200 was unclaimed in maintenance for only a few minutes with the official
stock server, checkpoint, image, and caches resident and an exact compatible
same-project repair bound. Reuse is cheaper than cold setup; no mismatch,
stale claim, passed lifecycle deadline, or unsafe bench warranted a drain.

**Bottleneck.** The H200 stock-multiplex owner held its first claim from
`07:57:16Z` until its deadline recovery, but produced no request row or
economic measurement. Retrieval proved `stock_packet/PACKET_ID.json` was
absent from the archive and the runner failed while validating the packet,
before constructing request bodies or making a generate call. The wrapper had
already written `science_started=true` on entry to the control/candidate
phase, so the first close decision conservatively consumed and terminalized an
uninvoked 139-request discriminator. An earlier harness prompt already warned
consumers that a pre-call marker is only intent; this recurrence shows that
consumer-side reinterpretation alone does not prevent producers from placing a
generic science marker too early. The director later corrected the evidence,
reclassified it as invalid pre-sample, retained the same H200, and bound one
manifest-derived repair; I did not alter that scientific decision.

**Change.** I tightened the shared researcher skill's arm-consumption
semantics: early launcher progress is `pre_science`; `science_started` may be
written only after packet, identity, and runtime validation pass and
immediately before the first request or kernel submission. Per-arm submission
or result evidence, not a phase label, determines consumption. This is a state
boundary correction rather than another validation gate, and it leaves the
active H100 endpoint owner and retained H200 repair untouched.

**Expected effect.** A recoverable packet, path, import, or runtime integration
failure can no longer close an uninvoked scientific arm merely because its
wrapper entered a named phase. Researchers can patch and run the actual
candidate once on the claimed mutable bench, reducing false rejections and
preserving warm state for decision-bearing Gemma 4 cost evidence.

## 2026-07-25 — recognize canonical PID-owner state without redundant identity copies

**GPU audit.** One grouped authenticated Nebius listing at `08:55Z` exactly
matched both registered resource pairs: RUNNING H100 instance
`computeinstance-e00jjdbxgvxwbzbfsr` with READY disk
`computedisk-e00hf9gkq3ee80yhvp`, and RUNNING H200 instance
`computeinstance-e00kcm9nfhwt7e7gbc` with READY disk
`computedisk-e00yvdxaa48q0t115t`. Both controller-host user watchdogs were
active/running, both claims had fresh heartbeats, and their PID-managed owners
matched recorded start ticks. H100 remained in exact checkpoint
staging/verification. H200 later hit an SSH terminal-read timeout; the
researcher retained the same claim and installed retrieval-only owner PID
`572761` at start ticks `108593712`, without replaying or restarting the
scientific workload. No missing provider object, stale claim, passed deadline,
idle-cost case, or unsafe bench warranted draining.

**Bottleneck.** The H200 `active_session` declared `unit_manager: pid` and
pointed to the canonical detached-owner JSON containing PID `554828` and start
ticks `108490102`, but duplicated neither field in `STATUS.json`. The harness
therefore failed its live-PID check and launched six read-only researcher turns
between `08:43Z` and `08:55Z`; each unchanged turn emitted
`researcher_no_progress` and forced another director wake. Those turns consumed
`179.724` researcher seconds and `345.294` director seconds while the actual
GPU owner was already progressing. The simultaneously active H100 session,
which duplicated both fields, was correctly deferred.

**Change.** The shared lab harness now resolves missing PID identity from the
canonical owner-state JSON named by a PID-managed session's `unit`, then still
requires an exact `/proc` PID/start-tick match. The H200 launcher also records
its own PID and start ticks directly for future sessions. Focused tests cover
both explicit identity and owner-state-pointer forms; both passed, as did the
repository DevEx check. Active GPU owners and scientific contracts were left
unchanged.

**Expected effect.** Durable owners created through shared `detached-owner`
will be deferred even when a project records only the canonical state-file
pointer. This removes unchanged researcher/director wake loops, preserving
agent capacity for terminal interpretation and new objective-bearing work
while GPU measurements continue uninterrupted.

## 2026-07-25 — drain provider-stopped H200; retain H100 for bounded disk repair

**GPU audit.** The single grouped authenticated Nebius listing at `09:05Z`
showed H100 instance `computeinstance-e00jjdbxgvxwbzbfsr` RUNNING with READY
disk `computedisk-e00hf9gkq3ee80yhvp`, exactly matching inventory. Its
controller-user watchdog remained active, the prior owner had exited and
released the bench to maintenance, and no claim was stale or stranded.
Nebius simultaneously reported H200 instance
`computeinstance-e00kcm9nfhwt7e7gbc` as STOPPED while READY disk
`computedisk-e00yvdxaa48q0t115t` remained present. Inventory still showed a
fresh claimed bench, active controller-user watchdog, and identity-matched
retrieval owner PID `572761` at start ticks `108593712`; its minute-spaced
diagnostics all failed with SSH connection timeouts. A live controller
watchdog does not make the stopped provider instance usable.

**Action.** I marked registered bench
`h200-ngram-verifier-e00kcm9nfhwt7e7gbc` drain-after-release. This preserves
the current retrieval owner's typed-terminal path but prevents the stopped
instance from returning to the available pool. The director owns provider
cleanup and inventory retirement; exact provider resources are instance
`computeinstance-e00kcm9nfhwt7e7gbc` and disk
`computedisk-e00yvdxaa48q0t115t`.

**Research bottleneck.** The H100 endpoint owner spent about 28 minutes
staging and hash-verifying the exact 59-GiB checkpoint and packet, then the
digest-pinned Docker pull failed pre-science with `no space left on device`.
No endpoint request was submitted. This is a retained-bench integration and
storage-geometry failure, not H100 price/performance evidence. The director
has already kept it in the same project and bound one bounded cleanup and
server-start repair; repeating static validation, replaying the consumed
discriminator, or creating another project would add no information.

**Expected effect.** The stopped H200 cannot be accidentally reclaimed for
new work, and its exact IDs are ready for director cleanup. Keeping the
RUNNING H100 briefly is justified by its fully staged checkpoint and the
still-unconsumed compatible endpoint: the bound repair can remove only
incomplete pull state and expendable caches, then either run the endpoint on
the resident state or emit a typed disk-fit terminal. If that bounded repair
cannot establish enough space before the lifecycle fence, the director should
drain rather than cold-restart the same failed geometry.

## 2026-07-25 — back off globally when the agent service is unavailable

**GPU audit.** One grouped authenticated Nebius listing at `09:47Z` reported
only the registered RUNNING H100 instance
`computeinstance-e00jjdbxgvxwbzbfsr` and READY disk
`computedisk-e00hf9gkq3ee80yhvp`. The previously stopped H200 provider pair was
absent and its inventory record had already been cleanup-verified and retired
at `09:12Z`, so provider reality and non-retired inventory matched. The H100
was available, unclaimed, and retained for the same endpoint-only disk repair;
its controller-host user watchdog was active with the recorded PID and control
group. The director subsequently replaced that watchdog with active unit
`gemma4-h100-v0515-endpoint-20260725t1050-watchdog.service` and a `10:50Z`
deadline after verifying that transport failures, not project work, consumed
the earlier window. Its staged checkpoint and still-unconsumed compatible
endpoint make the brief idle cost preferable to another 28-minute cold stage.
No bench warranted draining.

**Bottleneck.** Since `09:15Z`, external Codex service-capacity failures
produced 13 failed H100 researcher turns, 13 failed director turns, and six
failed supervisor turns. The failed turns consumed `715.967`, `629.414`, and
`188.138` agent-seconds respectively. Each researcher failure left the project
unchanged, so the harness classified it as `researcher_no_progress`, retried
after 60 seconds, and forced a high-reasoning director wake even though both
roles' traces reported the same `biscuit_baker_service_me_circuit_open`,
high-demand, or concurrency-throttle condition. No turn claimed the H100 or
advanced the sole endpoint.

**Change.** The shared lab harness now recognizes only failed, non-timeout
Codex runs whose own stdout/stderr tail contains a known service-capacity
marker. One such result opens a five-minute global launch backoff across
researcher, director, and supervisor roles. A transport-failed researcher gets
the same project cooldown without being mislabeled as scientific no-progress
or waking a director into the same outage. Successful runs, ordinary
experiment/tool failures, timeouts, and unknown errors keep existing behavior.
Focused classification, scheduler-backoff, unchanged-researcher, and fallback
cadence tests pass, as do the repository DevEx check, Python compilation, and
diff hygiene.

**Expected effect.** During a shared agent-service outage the lab will make one
bounded retry every five minutes instead of amplifying the outage with
minute-spaced researcher/director/supervisor launches. This preserves agent
capacity and the warm H100 repair window; once service recovers, the queued
director/researcher work resumes against the same staged checkpoint and can
produce the missing endpoint cost result without a cold restart.

## 2026-07-25 — do not turn an unknown disk-size observation into teardown

**GPU audit.** One grouped authenticated Nebius listing at `10:01Z` returned
no instances or disks while inventory still showed H100 bench
`h100-v0515-endpoint-e00jjdbxgvxwbzbfsr` draining. The claim had already been
released, its PID owner had exited, and its controller-host user watchdog was
inactive because the director had begun cleanup. During this audit the
director completed cleanup verification and retired the record at `10:02Z`,
so no unsafe reusable inventory remains and no supervisor lifecycle action is
possible or warranted. The deleted provider IDs were instance
`computeinstance-e00jjdbxgvxwbzbfsr` and disk
`computedisk-e00hf9gkq3ee80yhvp`. This supervisor did not perform provider
cleanup or inventory retirement.

**Bottleneck.** Warm reuse initially worked: the H100 was available at
`09:50:00Z`, claimed at `09:54:43Z`, and held by one identity-matched owner
with four fresh heartbeats until release at `09:58:41Z`. The exact checkpoint
and packet were reused. The attempt stopped before image validation, server
start, CUDA, or the sole 791-request endpoint because the image-manifest size
parser returned `image_manifest_size_unavailable`. Its terminal was explicitly
`typed_external_or_recoverable_failure`; both candidate and endpoint
consumption were false, and the project log correctly called it an ordinary
parser defect. The director nevertheless treated unknown manifest size plus
`22,307,127,296` free bytes as a failed disk-fit proof, invoked a local attempt
stop rule, and deleted the warm H100. That discarded the fully staged
62.6-GB checkpoint after a roughly 28-minute cold setup and leaves the
objective-bearing endpoint unmeasured.

**Change.** The shared director skill now states the missing semantic boundary:
an unavailable manifest size, failed parser, absent observer field, or
incomplete inspection is unknown evidence, not a negative physical bound. For
an explicitly recoverable, unconsumed integration failure, same-turn draining
and provider cleanup are forbidden unless independent evidence establishes
unsafe state, passed lifecycle deadline, exhausted total spend, or a selected
higher-value experiment that cannot reuse the bench. The director must keep
the watchdog and maintenance state long enough to decide the smallest in-place
repair versus a genuinely better use; a local attempt stop rule alone cannot
authorize teardown.

**Expected effect.** Future pre-science parser and observer defects will retain
resident checkpoints, images, and caches long enough for a mutable same-bench
repair. This avoids paying setup time twice and prevents an unknown observer
result from eliminating the only affordable path to a Gemma 4 endpoint cost
measurement.

## 2026-07-25 — maintain independent research runway

**Bottleneck.** The overnight scheduler used only about 13% of its five
researcher-slot capacity, and the current durable portfolio exposed one active
project despite the campaign requesting three materially different lanes. The
harness can schedule five projects and independent GPU benches concurrently;
the limiting behavior was portfolio admission. Closely related projects also
formed a serial chain around the same H200 result rather than independent work
that could advance while a GPU owner ran.

**Change.** The director skill now defines one turn as one portfolio rebalance,
which may admit or update several disjoint projects, rather than one project
choice. It asks for research runway across resource-independent work without a
fixed occupancy quota, counts projects sharing a bench or prerequisite as one
serial lane, and makes exhausted paid authority block only paid runs rather
than useful zero-cost work. The supervisor skill now audits independent
runnable lanes instead of project count or raw slot occupancy.

**Expected effect.** A long GPU run, provider setup, or narrow repair should
have independent causal, source, kernel, runtime, representation, simulation,
or hardware work progressing beside it. This should raise useful researcher
occupancy and keep a ready follow-up queue for warm GPUs without manufacturing
documentation or validation projects merely to fill five slots.

## 2026-07-25 — prevent an obsolete watchdog from deleting its replacement bench

**GPU audit.** One grouped authenticated Nebius listing at `10:20Z` returned
no instances or disks while inventory still marked
`h100-v0515-endpoint-200g-e00wthpm1fp735xd44` available. The missing provider
IDs are instance `computeinstance-e00wthpm1fp735xd44` and disk
`computedisk-e00d0aezed6d804hmp`. The recorded controller-host user unit
`gemma4-h100-v0515-endpoint-20260725t1220-watchdog.service` was not found and
PID `625957` was absent. The supervisor marked the stale registered bench
draining at `10:23:25Z`; provider cleanup and inventory retirement remain
director-owned.

**Bottleneck.** The director initially launched watchdog PID `625713` with
epoch `1784974800` (`10:20Z`) and then noticed that it intended `12:20Z`.
It launched corrected watchdog PID `625957` with epoch `1784982000` but did
not stop the first watchdog. The controller-host user journal shows both
watchdogs started at `10:16Z` and exited at `10:21Z`: the obsolete watchdog
deleted the newly registered instance at its earlier deadline, then the
corrected watchdog observed the missing instance and removed the managed disk.
The endpoint remained unconsumed, so another paid cold setup replaced no
scientific result.

**Change.** The shared Nebius `start_independent_watchdog` launcher now scans
live `/proc` command lines for an existing exact
`placement_control.py watchdog <instance_id> <disk_name>` owner and refuses
to launch a second watchdog for that provider resource. Replacement callers
must stop and verify the old watchdog instead of leaving two cleanup deadlines
armed. Two focused tests cover exact-resource matching and duplicate launch
rejection; Python compilation and diff hygiene pass.

**Expected effect.** A corrected lifecycle deadline can no longer appear
healthy while an older watchdog remains armed to delete the same instance.
This converts a silent two-hour-to-four-minute lifetime collapse into an
immediate local error before registration, avoiding another checkpoint/image
cold start and preserving the direct Gemma 4 endpoint lane for actual cost
measurement.
## 2026-07-25T11:33Z — prevent guessed SSH identity paths at warm-owner launch

Evidence: the priority-8490 H100 descriptor-repair researcher correctly reused the retained bench `h100-v0515-endpoint-200g-r2-e00yfnrrfczsdjevms`, captured the real 28,697-byte registry manifest, unified the parser, and passed its fixtures. Its detached endpoint-only owner then ran for about 99 seconds and terminated pre-science at `REMOTE_PREFLIGHT` because the launch command guessed nonexistent `/root/.ssh/id_ed25519`; stderr records `Identity file ... not accessible` and `Permission denied (publickey)`. Every prior successful owner for this same bench/provider used `/root/.config/nebius/glm-campaign/ssh_ed25519`. The owner released to maintenance without consuming the endpoint; the 62.6-GB verified checkpoint, packet, and candidate remain resident. Nebius still reports exactly the registered RUNNING instance `computeinstance-e00yfnrrfczsdjevms` and attached READY disk `computedisk-e00cjpqvtz8x59514m`; the controller-host user watchdog is active through 12:30Z, so no drain or provider cleanup is indicated. The active director has already localized the wrong key and is handling the smallest same-bench correction.

Change: amended `.agents/skills/researcher/SKILL.md` so SSH owners must take host/user/known-hosts data from the current inventory, reuse an established provider identity rather than guessing a default key, and verify required local identity paths before starting the durable owner.

Expected effect: turn missing-key mistakes into a zero-cost controller preflight failure instead of a claim/release cycle, preserving warm state and avoiding another cold stage or preventable delay before the campaign's sole unconsumed 791-request H100 endpoint.

## 2026-07-25T12:20Z — do not advertise a resident endpoint server as a free accelerator

**Bottleneck.** The completed 791-request endpoint owner released
`h100-v0515-endpoint-200g-r2-e00yfnrrfczsdjevms` as `ready` while its
SGLang scheduler still held `74,814 MiB` of H100 memory. The next admitted
packed-mask component researcher claimed that supposedly free bench at
`12:14:43Z`, spent its short window identifying and stopping only the released
endpoint process, and released at `12:17:36Z` without submitting either stock
or candidate CUDA. The attempt is correctly typed `invalid_pre_science`; it
cost `$0.13` and produced no campaign performance evidence.

**Change.** The endpoint owner harness now releases to `maintenance` after
every terminal, including a scientific terminal. That owner intentionally
leaves its server resident, so only the director may inspect the exact process,
port, and memory state and decide whether a compatible successor can inherit
it or whether it should be stopped before making the bench available. The
current bench and active semantic-divergence project were not mutated.

**Expected effect.** A downstream component project can no longer atomically
claim this owner’s released bench while 74.8 GiB is still occupied. Warm-server
reuse remains possible through director disposition, while incompatible work
avoids losing its paid measurement window to cleanup.

## 2026-07-25T12:50Z — keep recoverable observer repairs inside the warm claim

**Bottleneck.** The fresh sentinel A/A completed all four responses and found
identical isolated and co-batched output, but its observer raised
`TypeError("'int' object is not iterable")` 97 times because it treated the
flattened draft-token buffer as per-row. The required conservation invariant
was therefore empty and the result correctly classified `typed_invalid`.
Despite this being a localized observer-only defect, the project owner
released `h100-v0515-endpoint-200g-r2-e00yfnrrfczsdjevms` to maintenance at
`12:45:45Z`; the director then removed the healthy resident sentinel container
before rebinding the same project. This turns a patch-and-rerun into another
model/server cold start. The provider resource and controller-host user
watchdog remain healthy, and the same project has been reactivated for fresh
indices `60002` and `60003`, so draining is not warranted.

**Change.** Moved the existing repair-in-place invariant to the opening of the
researcher skill: recoverable observer, instrumentation, launcher, retrieval,
or consumer defects must retain the claim and healthy resident runtime, use
the shared repair handshake, and rerun only the invalidated operation. A typed
invalid attempt is no longer a reason to follow an unconditional stop/release
path.

**Expected effect.** Future localized measurement defects should pay only for
the patch and invalidated request, preserve loaded weights and caches, and
avoid the release/maintenance/director-cleanup/reclaim cycle that consumed this
sentinel's warm state.

## 2026-07-25T13:03Z — repair completed evidence offline before replay

**Bottleneck.** The observer-repair run spent another `$0.9055` and collected
the missing decision-bearing data: 256 trace rows, zero instrumentation
errors, 128/128 passing target→accept→KV→scheduler steps, four complete
358-token responses, and identical isolated/co-batched sentinel-A outputs.
It still classified `typed_invalid` because runtime traces use four generated
hex request IDs while the response bundle is keyed by four logical
`sentinel-*-repair-*` labels. The postprocessor joined responses with
`responses.get(runtime_rid)`, leaving all 128 `response_output_ids` links
null; it also tested stale pre-repair response names when computing
`sentinel_exact`. The owner then unconditionally removed the container and
released the H100 to maintenance. This is an offline result-construction
defect, not missing GPU evidence, so another request replay would waste the
consumed indices and setup.

**Change.** The director skill now requires an offline reconstruction from
immutable raw responses and traces when only identifier joining,
serialization, scoring, or classification fails after a complete paid
invocation. Director bindings may no longer prescribe unconditional container
stop or bench release for every classification; cleanup must depend on a
decision-bearing terminal, unsafe state, or the absolute deadline.

**Expected effect.** The current semantic result can be recovered without a
third paid sentinel run, and future completed GPU evidence will survive a
postprocessor typo instead of triggering another cold load and request
consumption. The original H100 is healthy in maintenance through `13:30Z`;
with the independent packed-mask endpoint now on its own registered H100, the
director should either bind a concrete compatible reuse promptly or drain the
original bench based on idle cost.

## 2026-07-25T13:21Z — verify a fresh remote identity before advertising the bench

**Bottleneck.** The fresh packed-mask endpoint researcher prepared the exact
runtime source, applied only the measured candidate, passed its CPU oracle,
and then claimed `h100-v0515-packed-endpoint-200g-e00y7ay83sma59j0hz`.
Its first strict SSH probe found that reused public IP `89.169.103.97` still
had a different ED25519 key at line 103 of the campaign known-hosts file. The
researcher correctly sent no guest command or artifact, released to
maintenance after 44 seconds, and classified the `$0.28` exposure as
pre-science. Instance `computeinstance-e00y7ay83sma59j0hz`, disk
`computedisk-e00akg7bscxwvgq2jp`, and the controller-user watchdog remain
healthy. The director reconciled the exact provider identity, replaced only
that stale entry, and proved strict SSH succeeds, so the same bench can resume
without teardown or cold restart.

**Change.** The director skill now requires a newly created remote bench to
reconcile reused endpoint host keys against the authenticated provider
instance, pass a strict SSH probe, and persist the verified fingerprint before
the bench becomes claimable. Registration metadata alone is no longer treated
as a completed connection-identity handoff.

**Expected effect.** IP reuse should be resolved during director-owned
provisioning instead of consuming a researcher claim and repair cycle. Fresh
Gemma endpoint lanes can start checkpoint staging immediately while preserving
strict host-key security and the same registered provider resource.

## 2026-07-25T13:54Z — carry successful staging into execution under one claim

**Bottleneck.** The corrected packed-endpoint owner held
`h100-v0515-packed-endpoint-200g-e00y7ay83sma59j0hz` from `13:28:46Z`,
streamed and SHA-256-verified all eight checkpoint files, and atomically
finalized the 59-GiB checkpoint, packet, and patched runtime source at
`13:48:56Z`. Its script ended there: it contained no workload construction,
server launch, stock arm, candidate arm, terminal, or release. The resumed
researcher proved the guest was healthy, the GPU was empty, no container
existed, and no scientific arm had started, but released the same project's
claim to maintenance at `13:53:42Z`. The checkpoint remains resident and the
controller-user watchdog is active through `18:00Z`, so immediate same-bench
reuse is strongly preferred over drain or teardown.

**Change.** The researcher skill now names successful staging-only owner exit
as a nonterminal handoff: while the same bound experiment remains, keep the
claim and launch one durable execution continuation against the verified
resident inputs, recording its `active_session` before yielding. Do not
release merely to force a director rebind/reclaim, and never restage the
verified inputs. The existing bounded replacement-owner stop rule still
applies if the continuation also exits before a valid sample.

**Expected effect.** Large checkpoint staging should flow directly into model
load and the fresh 791-request stock/candidate pair without another claim
transition, director cycle, or transfer. This preserves the approximately
20-minute staging investment and shortens time to the objective-bearing H100
endpoint cost result without weakening watchdogs or failure accounting.

## 2026-07-25T14:07Z — execution continuations must reach the GPU consumer

**GPU audit.** One grouped authenticated Nebius listing exactly matched the
two registered instances and disks; there are no provider-only or
inventory-only resources. Both claims have current heartbeats, future leases
and deadlines, and controller-user watchdogs whose recorded units and cgroups
are active on the controller. The packed endpoint was reclaimed warm at
`14:01:55Z` without reprovisioning or checkpoint replay, so no bench is
objectively ownerless, expired, or unsafe and no drain transition is
warranted.

**Bottleneck.** The new packed-endpoint owner is labeled a post-staging
execution continuation, but its complete 21-line command graph only pulls the
bound image and constructs `fresh_workload.jsonl`; it has no server launch,
stock arm, candidate arm, measurement, terminal, or repair handshake. After
preparation it loops on `sleep 30` until `17:30Z`, while the exact fresh
791-request endpoint pair remains queued. Thus the prior handoff correction
preserved the 59-GiB resident checkpoint but did not yet convert warm-bench
time into the campaign's direct endpoint service-time and cost evidence.
Director reuse target: bench
`h100-v0515-packed-endpoint-200g-e00y7ay83sma59j0hz`, instance
`computeinstance-e00y7ay83sma59j0hz`, and disk
`computedisk-e00akg7bscxwvgq2jp`. Repair or replace the command graph under
the current claim; do not restage, teardown, or cold-start it.

**Change.** Tightened the researcher handoff rule: an execution continuation
must carry its command graph directly from remaining preparation into the
bound server or GPU consumer without another harness turn. Image pull or
workload construction followed by a deadline sleep remains staging, and may
not be used as an inert claim holder; a recoverable pause must instead expose
the existing repair handshake while preserving resident state.

**Expected effect.** The next durable continuation should cross the only
remaining objective-bearing boundary—fresh stock/candidate endpoint
measurement—on the already claimed mutable bench. This avoids up to roughly
3.5 hours of paid H100 reservation with zero endpoint samples while preserving
the verified checkpoint, exact runtime, frozen workload contract, and active
watchdog.

## 2026-07-25T14:15Z — freeze persisted state, not an intended producer step

**GPU audit.** One grouped authenticated Nebius listing at `14:12:53Z`
exactly matched both registered RUNNING H100 instances and READY disks. Their
controller-user watchdog units and recorded cgroups are active with deadlines
at `16:00Z` and `18:00Z`; no provider-only, inventory-only, expired, unsafe,
or watchdog-owner mismatch exists. The adaptive-depth bench subsequently
released ready after a valid component result. Its retained bound image and
CUDA compilation cache cost substantially more to cold-establish than this
first short idle interval, so preserve it through the next portfolio
selection rather than drain it now.

**Bottleneck.** The packed continuation finished the image pull but raised
`KeyError: 'prompt'` while building the fresh workload. Consequently neither
`fresh_workload.jsonl` nor `FRESH_WORKLOAD.json` was ever persisted. The
director's inert-owner audit listed workload construction as an implemented
command step, then the GPU-consumer repair binding promoted that intended step
to “constructed” resident state and prohibited reconstructing or mutating it.
The replacement researcher correctly found both files absent, kept
`h100-v0515-packed-endpoint-200g-e00y7ay83sma59j0hz` claimed and heartbeating,
and submitted no request. Instance `computeinstance-e00y7ay83sma59j0hz` and
disk `computedisk-e00akg7bscxwvgq2jp` remain healthy with the 59-GiB
checkpoint, image, packet, and exact runtime resident. This is a recoverable
producer-schema defect before science, not a reason to restage or cold-start.

**Change.** The director skill now distinguishes intended, attempted, and
atomically persisted state at owner transitions. A follow-up binding may
freeze or prohibit reconstruction of a producer output only after its
completion marker and content identity were actually persisted. A traceback
before that marker keeps only the incomplete producer step repairable under
the same claim while settled resident inputs remain immutable.

**Expected effect.** The director can amend this handoff to patch the workload
schema and rerun only workload construction, then proceed directly to the
fresh stock/candidate endpoint pair. Future repair bindings will not turn an
ordinary pre-science producer failure into a self-imposed integrity blocker,
avoiding another director/researcher cycle while retaining warm state.

## 2026-07-25T14:31Z — a requested repair must unblock its replacement owner

**GPU audit.** One grouped authenticated Nebius listing at `14:30:35Z`
exactly matched the sole registered RUNNING endpoint instance
`computeinstance-e00y7ay83sma59j0hz` and READY disk
`computedisk-e00akg7bscxwvgq2jp`. The controller-user watchdog is active in
its recorded cgroup through `18:00Z`; the project claim heartbeat, lease, and
PID/start-tick identity for owner `783217/110494413` are current. No resource
is missing, unregistered, expired, stale, unsafe, or eligible for drain.

**Bottleneck.** The director correctly issued the atomic workload-schema
repair binding and wrote its hash-bound `REPAIR_REQUEST.json` at
`14:30:01Z`. The boundary owner's success branch does not consume that repair
or exit: after `repair-handshake wait` returns success, lines 47–49 only log
the request, sleep 60 seconds, and repeat forever. Because PID `783217`
remains the recorded durable session, the harness deferred the endpoint
researcher at `14:30:49Z` with `reason=durable_session_active`. Thus the
requested repair cannot reach the replacement owner, while the objective-
bearing H100 remains claimed without a server or endpoint sample.

**Change.** Tightened the researcher repair-owner contract without adding a
validation gate. An owner that advertises `REPAIR_READY` must have an
executable success path after the request. When the repair explicitly needs a
replacement owner, the boundary owner must exit promptly after observing the
hash-bound request so the harness can stop deferring the project and transfer
heartbeat responsibility under the still-live lease; acknowledging the
request and continuing a heartbeat-only sleep is forbidden.

**Expected effect.** The current director can terminate or supersede this
identity-matched boundary owner and dispatch the already-bound workload repair
without releasing the claim or restaging the 59-GiB checkpoint and image.
Future repair handshakes should require one wake/transfer instead of becoming
durable-session deadlocks that burn warm-GPU time.

## 2026-07-25T14:44Z — retry a localized pre-science launcher defect in-turn

**GPU audit.** One grouped authenticated Nebius listing at `14:42Z` exactly
matched the sole active inventory instance
`computeinstance-e00y7ay83sma59j0hz` and attached READY disk
`computedisk-e00akg7bscxwvgq2jp`. The recorded controller-user watchdog is
active with PID `730607` in its exact cgroup through `18:00Z`; the project
claim heartbeat and lease are current. No provider-only, inventory-only,
expired, stale, ownerless, unsafe, or idle-drain mismatch exists.

**Bottleneck.** The workload-repair replacement owner failed at `14:38:38Z`
with the retained raw diagnostic `permission denied while trying to connect
to the docker API at unix:///var/run/docker.sock`. No workload marker, server,
CUDA invocation, request, stock arm, or candidate arm started, and the same
bench had already proved `sudo docker` works. The researcher localized the
one-line command-prefix amendment but interpreted the bounded replacement-owner
rule as requiring it to stop and defer the retry to a new director/researcher
cycle. This turned an ordinary pre-science launcher correction into paid warm-
bench coordination latency while the campaign still lacks the fresh endpoint
service-time and cost result.

**Change.** Clarified the researcher bounded-owner rule: after retrieving a
diagnostic, one localized mutable launcher/controller defect before any server,
CUDA work, or scientific arm may be patched and retried once in the same turn
under the existing claim. The retry is continuation of the invalid attempt,
not a new scientific sample. Unlocalized, state-uncertain, or twice-failed
paths still stop and hand back safely.

**Expected effect.** Future permission, command-prefix, path, and import
mistakes should cost one patch-and-rerun rather than a director authorization
and harness redispatch, while preserving the warm checkpoint/image state,
scientific binding, attempt accounting, lease, and watchdog. The current
director has already bound the exact `sudo --non-interactive docker`
amendment, so the endpoint recovery can proceed without restaging or provider
restart.

## 2026-07-25T15:01Z — prove the repaired command, not only owner liveness

**GPU audit.** One grouped authenticated Nebius listing at `14:59Z` exactly
matched the sole active inventory instance
`computeinstance-e00y7ay83sma59j0hz` and attached READY disk
`computedisk-e00akg7bscxwvgq2jp`. Its controller-user watchdog is active with
PID `730607` in the recorded cgroup through `18:00Z`; the project claim is
fresh through `15:57Z`. No provider-only, inventory-only, expired, stale,
unsafe, or idle-drain mismatch exists. The candidate repair's experiment
controller PID `814600/110748047` is absent, but the independent lifecycle
watchdog remains healthy and the retained claim is recoverable, so do not
drain or teardown the bench.

**Bottleneck.** The completed stock arm is durable and decision-bearing:
791/791 completions, zero failures, bounded release drift, and
`0.7239557313 s/request`. Its candidate never launched. The first repair had
correctly added `--gpus all` to the module-path probe, but the GPU-enabled
container printed its CUDA license banner on stdout before
`/sgl-workspace/sglang/python/sglang/srt/speculative/ngram_worker.py`.
Command substitution captured the banner and path together, producing a
multiline Docker volume spec and `too many colons`. The researcher checked the
new detached owner immediately, recorded PID liveness as progress, and
returned; the owner died 23 seconds later before candidate server, CUDA, or
request submission. A generic `docker version` preflight did not exercise the
repaired command's output contract.

**Change.** Tightened the researcher durable-owner handoff rule: for a repair
owner, PID liveness is not forward progress. Before yielding, one grouped
snapshot must show a durable phase beyond the exact repaired command, or the
newly amended launcher command and its output contract must be exercised once
inside the launch path. This is an execution-equivalent smoke test followed
directly by the experiment, not a static readiness ladder or repeated poll.

**Expected effect.** Path, permission, quoting, and output-capture amendments
should fail while the researcher still owns the turn and can apply the one
bounded retry, rather than producing another dead detached owner and
director/harness cycle. The valid workload and stock arm remain immutable and
reusable; only the unstarted candidate consumer should rerun on the same H100
claim, checkpoint, image, and watchdog.

## 2026-07-25T15:25Z — accept inline resident-state objects in the GPU pool CLI

**GPU audit.** One grouped authenticated Nebius listing at `15:23Z` exactly
matched both registered instances and attached READY disks: H100
`computeinstance-e00y7ay83sma59j0hz` /
`computedisk-e00akg7bscxwvgq2jp` and H200
`computeinstance-e00vyqp7gxsr34wrtz` /
`computedisk-e00dryj6tbensjs413`. Both recorded controller-user watchdogs are
active with their exact PIDs and cgroups. The H200 was claimed by the bound
DFlash project at `15:23:24Z`. The H100 was safely released ready at
`15:23:07Z`; retain it for the already-active compatible adaptive-depth
consumer rather than drain it.

**Bottleneck.** The H100 endpoint produced a valid contemporaneous terminal:
791/791 requests per arm, zero failures, stock `0.7239557313 s/request`,
candidate `0.7228112454 s/request`, and a semantic divergence at fresh index
61671. Closing this candidate is sound because the measured `0.16%` speed
change is negligible even before the semantic failure. Finalization exposed a
repeated shared-tool defect instead: both the director and endpoint owner
passed an inline object to `gpu_pool update --contents`, but the CLI treated
every value as a filename. The final update failed and left the available
bench's resident description saying the completed candidate was unstarted,
which can misroute warm reuse.

**Change.** Updated the shared GPU-pool CLI so `update`, `release`, and `ready`
accept either an inline JSON object or a JSON-object file, while retaining
object validation and clearer help/error text. Added a behavioral CLI test;
all 10 dependency-free GPU-pool unit tests pass. No bench or scientific state
was mutated by this supervisor change.

**Expected effect.** Detached owners can atomically persist terminal resident
state during release without first creating a throwaway file or silently
leaving stale inventory after a successful run. The director should receive
accurate checkpoint, server, and result state soon enough to route the next
compatible project onto the warm H100 instead of restaging or cold-starting.

## 2026-07-25T15:55Z — keep pinned-source digest typos out of scientific closes

**GPU audit.** One grouped authenticated Nebius listing exactly matched the
two registered RUNNING instances and attached READY disks: H100
`computeinstance-e00y7ay83sma59j0hz` /
`computedisk-e00akg7bscxwvgq2jp` and H200
`computeinstance-e00vyqp7gxsr34wrtz` /
`computedisk-e00dryj6tbensjs413`. Both controller-user watchdogs are active
with their recorded PIDs and cgroups. The H100 claim now has a durable
controller at PID `862980` and a current heartbeat; the H200 controller PID
`841139` is live, its heartbeat is current, its image build completed, and
exact model materialization has begun. No deadline, lease, idle-cost, or
safety drain condition is present.

**Bottleneck.** The zero-cost DFlash FP8 tied-head composition produced a
source-complete overlay and passed its deterministic fixtures, including
1,048,576 logit comparisons, but was terminalized as
`localized_negative_bound_source_hash_mismatch`. The sole failed check was a
one-character typo in the declared digest for exact pinned-commit
`dflash_accept_bonus.py`: declared `...6fd4e`, observed `...6fdce`; the other
48 binding checks passed. This rejects binding metadata, not the composition
mechanism, and converting it to a scientific terminal forces an avoidable
director rebind/reschedule cycle.

**Change.** Tightened only the shared researcher skill: when bytes from the
exact pinned revision prove a declared digest wrong, preserve completed work
and report a repairable same-project binding defect rather than a localized
scientific negative. A genuine pinned-identity mismatch remains fail-closed.
The rule explicitly prohibits a validator or successor project. No active
project, owner, claim, watchdog, provider resource, or scientific contract was
changed.

**Expected effect.** Future digest typos should cost one mechanical director
rebind and immediate same-project continuation, without discarding valid
source work, falsely shrinking the scientific portfolio, or adding another
static-validation project before the real GPU consumer.

## 2026-07-25T16:05Z — make endpoint owners notice a dead resident server

**GPU audit.** One grouped authenticated Nebius listing exactly matched the
two active inventory records: RUNNING H100
`computeinstance-e00y7ay83sma59j0hz` with attached READY disk
`computedisk-e00akg7bscxwvgq2jp`, and RUNNING H200
`computeinstance-e00vyqp7gxsr34wrtz` with attached READY disk
`computedisk-e00dryj6tbensjs413`. Their recorded controller-user watchdogs
are active with PIDs `730607` and `828601` in the exact recorded cgroups,
through `18:00Z` and `22:00Z`. Both claims heartbeat about every 45 seconds,
their leases extend past `17:02Z`, and controller PIDs
`862980/111089359` and `841139/110944877` match their recorded start ticks.
No provider-only, inventory-only, stale, expired, ownerless, unsafe, or
idle-drain mismatch exists. Warm reuse is sound: the H100 was idle only about
8.7 minutes before the compatible endpoint reclaimed its resident
checkpoint/image/cache, while H200 was claimed about 1.7 minutes after ready
and has retained one mutable claim across image build and exact model staging.

**Bottleneck.** The earlier digest rule already worked: the director
reactivated the same `$0` DFlash FP8 stack project for one local identity
correction, without a validator, successor, or GPU. The current paid delay is
instead inside the H100 endpoint owner. Its control container became ready and
accepted the first-arm requests, then exited with code `0` at
`15:58:15Z` after request timeouts and SGLang shutdown traces. It is not OOM
and the guest has 81 GiB free. The controller and its SSH child remain live
and heartbeating, but the remote request driver permits 1,200-second request
waits and has emitted no arm result or failure marker. Consequently the
harness repeatedly defers the researcher as `durable_session_active` while
there is no resident server or GPU process. PID and claim liveness are masking
a recoverable integration failure, delaying same-claim diagnosis and risking
an unnecessary cold restart. The independent H200 owner is making real
progress: its bound image is complete and exact target/draft downloads are
advancing.

**Change.** Tightened only the shared researcher owner contract. An endpoint
owner must supervise both request driver and resident server/container. If the
server dies or loses health while requests block, it must persist the server
exit/log and exact arm-submission state, then enter the existing repair
handshake under the same claim or exit promptly for a replacement owner.
Claim heartbeats may not hide that state. The rule explicitly preserves
checkpoint, image, workload, and caches, forbids release or cold restart before
consumption is known, and reruns only the invalidated or unstarted arm. The
active owner, bench, requests, claims, watchdogs, and scientific contracts
were not mutated.

**Expected effect.** A dead endpoint server should become an actionable repair
within one owner observation interval instead of burning up to a 1,200-second
client timeout while the harness defers recovery. Researchers should retain
the mutable warm bench, retrieve the exact failure boundary, and patch/rerun
only the affected arm, reducing paid idle time and avoiding checkpoint/image
restaging after recoverable serving failures.

## 2026-07-25T16:26Z — keep spend reserved through an active repair turn

**GPU audit.** One grouped authenticated Nebius listing exactly matched the
two registered resources: RUNNING H100
`computeinstance-e00y7ay83sma59j0hz` with READY disk
`computedisk-e00akg7bscxwvgq2jp`, and RUNNING H200
`computeinstance-e00vyqp7gxsr34wrtz` with READY disk
`computedisk-e00dryj6tbensjs413`. Both recorded controller-user watchdogs are
active with PIDs `730607` and `828601` in their exact cgroups, through
`18:00Z` and `22:00Z`. Both claims have current heartbeats and live
PID/start-tick-matched owners. No provider-only, inventory-only, stale,
expired, ownerless, unsafe, or idle-drain condition exists.

**Bottleneck.** Fixed-M384 reused the released H200 within eight minutes and
reached a pre-science filesystem ownership defect, but the harness settled its
`$8` reservation when the project transiently wrote `status: blocked` even
though the researcher turn was still running. The same turn repaired the
hard-link path, reclaimed the same resident bench 59 seconds after the
maintenance handoff, and launched durable PID `890499`; checkpoint files that
failed unprivileged materialization are now succeeding through the bounded
privileged path. Event evidence shows `spend_settled` at `16:22:00Z` and the
replacement claim at `16:22:12Z`. Thus the scientific run remained warm and
correctly unconsumed, but its ongoing paid exposure temporarily disappeared
from the campaign reservation ledger.

**Change.** The shared harness now excludes currently running researcher
labels from terminal-reservation settlement, even if their project status
briefly becomes blocked during an in-turn repair. Settlement proceeds normally
after the researcher exits and the project remains non-active. Added a
regression covering blocked-during-repair retention and subsequent settlement;
all 57 lab-harness tests pass. The harness source reload is safely deferred
while PID-managed sessions are live, and no active project, claim, owner,
watchdog, or provider resource was mutated.

**Expected effect.** Repair turns can persist a typed intermediate boundary and
launch a bounded same-project continuation without releasing their spend
authority for reuse by another lane. Campaign available-spend telemetry should
remain conservative throughout warm-bench repair, preventing accidental
overcommit while preserving fast in-place continuation.

## 2026-07-25T17:33Z — surface repeated repairs under one warm claim

**GPU audit.** One grouped authenticated Nebius listing exactly matched the
sole active inventory record: RUNNING H200
`computeinstance-e00vyqp7gxsr34wrtz` with attached READY disk
`computedisk-e00dryj6tbensjs413`. Its recorded controller-user watchdog is
loaded and active at PID `828601` in the exact recorded cgroup through
`22:00Z`. The claimed fixed-M384 owner PID `915680` is live and its start tick
`111434248` matches `STATUS.json`; claim heartbeats remain current. There is no
provider-only, inventory-only, stale, expired, ownerless, unsafe, or
idle-drain mismatch. The prior H100 was drained only after the director selected
the continuing H200 and independent offline portfolio, then provider cleanup
was verified and the record retired.

**Bottleneck.** The fixed-M384 owner correctly retained one mutable H200 claim
across two earlier observer repairs, without replaying its measured
`20.2089%` weighted attention component or its completed NCU producer. It then
reached a third recoverable boundary at the conditional endpoint consumer:
remote `REPAIR_READY.json` reports
`endpoint_pair_harness_invalid:1`, with candidate CUDA and scientific
invocation started. The outer owner used one boolean `repair_seen`, so it
continued heartbeating and reporting `repair` but did not surface this later
generation locally. The harness also treated the mere presence of the prior
hash-bound `REPAIR_REQUEST.json` as satisfying every later ready marker.
Consequently a live owner and healthy claim could hide a new actionable repair
until the absolute deadline.

**Change.** The shared harness now considers a repair satisfied only when the
request's `ready_sha256` matches the current canonical ready record; a new
ready generation wakes the same researcher even if an older request remains.
Added a regression for this case. The fixed-M384 outer-owner source now
fingerprints each remote ready record rather than suppressing all repairs after
the first. For the already-running owner, the prior counter-consumer request
was archived intact and the current endpoint-consumer ready marker was surfaced
locally, allowing the existing harness process to wake repair immediately.
No remote worker, server, claim, watchdog, provider resource, or scientific
contract was changed. All 58 harness tests, owner compilation, DevEx checks,
and diff checks pass.

**Expected effect.** Multi-stage experiments can repair several distinct
consumer boundaries within the same paid claim instead of becoming
heartbeat-only sessions after the first repair. The current researcher should
inspect the endpoint-consumer diagnostic, preserve exact arm-submission state,
and rerun only the invalidated consumer against resident model/image/cache
state, avoiding a cold restart and protecting completed component and counter
evidence.

## 2026-07-25T18:03Z — fence an ownerless DFlash claim without discarding the warm server

**GPU audit.** One grouped authenticated Nebius listing exactly matched the
sole non-retired inventory resource: RUNNING H200 instance
`computeinstance-e00vyqp7gxsr34wrtz` with attached READY disk
`computedisk-e00dryj6tbensjs413`. Its controller-user watchdog remains active
at PID `828601` in the recorded cgroup through `22:00Z`. The bench handed off
from mixed-M384 to DFlash in 14.6 seconds and reused the resident checkpoint,
image, and caches. However, DFlash controller PID `976489` is gone, its last
claim heartbeat was `17:55:57Z`, and the inventory still records the bench
claimed. The registered bench is therefore objectively ownerless and has been
marked `drain_after_release: true`; no provider cleanup or inventory retirement
was performed.

**Bottleneck.** The one-request oracle reached a healthy resident DFlash server
and then failed in an observer call because this endpoint returns 404 for
`/metrics`. Its compact remote terminal records `science_started: true`,
`stage: oracle_request`, and exit `1`; the container remains running with the
exact target, draft, patched source, and CUDA graphs resident. The controller
then attempted non-recursive `scp` retrieval, failed on the `oracle/`,
`overlay/`, and `request/` directories, and exited before a durable project
terminal or claim release. This is a recoverable observer/retrieval boundary,
not evidence against the DFlash relay mechanism, and cold teardown would waste
the warm state.

**Change.** The DFlash owner harness now retrieves the remote artifact tree
recursively, so a resumed same-claim consumer can preserve the oracle,
overlay, request, and terminal evidence instead of dying during handoff. The
scientific observer repair and disposition remain with the researcher and
director. The director should either establish a bounded replacement owner on
this same registered bench and rerun only the invalidated oracle request, or
release and clean up deliberately using the exact instance and disk IDs above.

**Expected effect.** A narrow same-claim repair can reuse the already-loaded
model, draft, image, and CUDA graphs, recover complete per-cycle evidence, and
avoid another model load or cold allocation. If recovery is declined, the
drain fence prevents the ownerless claim from being handed to queued grouped
LM-head work as though it were safe.

## 2026-07-25T19:23Z — back off explicit agent usage exhaustion and fence the second dead owner

**GPU audit.** One grouped authenticated Nebius listing exactly matched the
sole non-retired inventory resource: RUNNING H200 instance
`computeinstance-e00vyqp7gxsr34wrtz` with attached READY disk
`computedisk-e00dryj6tbensjs413`. The controller-user watchdog is active at
PID `828601` in its exact recorded cgroup through `22:00Z`. Replacement
DFlash owner PID `992013` with recorded start tick `111899118` is absent,
while the bench remains claimed with its final heartbeat at `18:20:49Z` and
lease ending `19:20:49Z`. I marked the registered bench
`drain_after_release: true` again. I did not reclaim the claim, clean up the
provider resource, or retire inventory.

**Bottleneck.** The replacement owner preserved the warm bench, passed the
fresh 112-cycle DFlash oracle, and collected raw depth-4/8/12/16 timing
artifacts before exiting after localhost connection failures. All four output
trees are retrieved, so teardown and a cold scientific replay would be waste;
the remaining work is offline reconciliation and director disposition.
Instead, from `18:21Z` through `19:17Z`, 183 director, researcher, and
supervisor completions failed with the identical Codex terminal
`You've hit your usage limit`. The harness classified each as ordinary
no-progress and retried every 60 seconds, repeatedly waking the director while
the paid H200 claim had no owner. The existing global service-backoff
predicate covered capacity and circuit-open errors but not this explicit
usage-exhaustion message.

**Change.** Added the exact lowercased usage-limit marker to the existing
failed-run service-unavailability classifier. Such a failure now enters the
existing global 300-second backoff and does not emit a researcher-no-progress
director wake; successful runs and ordinary experiment failures are
unchanged. The source reload is already queued for the normal boundary after
active agent turns finish. All 58 harness tests, Python compilation, and diff
checks pass.

**Expected effect.** A future explicit account/service exhaustion should
produce one bounded probe per backoff window rather than a director and every
runnable researcher each minute. This preserves coordinator capacity and
prevents failure storms from obscuring dead-owner reconciliation, while still
retrying automatically when service returns. The director should now
reconcile the retrieved DFlash depth artifacts without replaying the consumed
oracle, reclaim or release the stale claim deliberately, and then either reuse
the retained checkpoint/image state for the queued grouped-head consumer or
clean up the exact instance and disk IDs above.

## 2026-07-25T20:08Z — move Codex prompts out of the process argument vector

**GPU audit.** One grouped authenticated Nebius listing exactly matched the
sole non-retired inventory resource: RUNNING H200 instance
`computeinstance-e00vyqp7gxsr34wrtz` with attached READY disk
`computedisk-e00dryj6tbensjs413`. Its controller-user watchdog is active at
PID `828601` in the recorded cgroup through `22:00Z`. The bench is available,
unfenced, and has been idle since `19:56:22Z`; about 11.7 minutes or `$0.48`
of idle exposure had accrued at the audit snapshot. Warm retention remains
justified because the director admitted the compatible 55-local/5-global H200
component and an independent zero-GPU grouped-head continuation.

**Bottleneck.** The admitted portfolio could not start. From `20:04:40Z`
onward, every director and both researcher launches failed before an agent
turn with `OSError: [Errno 7] Argument list too long: 'codex'`, then retried
each minute. `CodexAgentRunner` appended the full generated prompt to the
`codex exec` argument vector; the enlarged campaign/project context exceeded
the host's argv limit. This left the H200 idle despite a claim gate ending at
`20:15Z` and produced no scientific work.

**Change.** `CodexAgentRunner` now invokes both new and resumed turns with the
CLI's `-` prompt sentinel and streams the unchanged prompt through stdin.
Model routing, prompt construction, timeouts, traces, retry policy, and
project scopes are unchanged. The runner regression verifies that the prompt
is absent from argv and present on stdin. All 58 lab-harness tests, Python
compilation, and scoped diff checks pass.

**Expected effect.** Large durable lab contexts can launch without OS argv
failure, allowing the already-admitted hybrid component to claim and reuse the
resident H200 before its gate closes while grouped-head advances independently.
This should end the minute-scale no-progress loop without a cold restart or
new project.

## 2026-07-25T20:34Z — launch admitted work before a queued follow-up director wake

**GPU audit.** One grouped authenticated Nebius listing exactly matched the
sole non-retired inventory resource: RUNNING H200 instance
`computeinstance-e00vyqp7gxsr34wrtz` with attached READY disk
`computedisk-e00dryj6tbensjs413`. Its controller-user watchdog is active at
PID `828601` in the recorded cgroup through `22:00Z`. The bench remained
available, unfenced, and warm after the hybrid component released at
`20:19:40Z`; retention was justified by the already-admitted compatible
endpoint continuation.

**Bottleneck.** The first director had made the hybrid endpoint runnable when
it completed at `20:26:07Z`, but a grouped-head completion wake accumulated
during that turn. The event loop dispatched a second director immediately and
blocked researcher slot filling until `20:28:55Z`, leaving only 65 seconds
before the endpoint binding's `20:30:00Z` claim gate. The researcher started
at `20:28:56Z`, checked the gate at `20:30:35Z`, and correctly terminalized
`unrun_claim_gate_closed` with no claim, invocation, or new spend. This lost
the direct endpoint measurement despite a healthy resident bench and was
scheduler ordering, not scientific or provider failure.

**Change.** After a director future completes, the event loop now fills free
researcher slots from that director's durable active/ready portfolio before
dispatching a director wake that accumulated during the same turn. The wake
is preserved and still runs next; only already-admitted work receives the
free slot first. A concurrency regression reproduces a researcher completion
during a director turn and verifies that the admitted successor is launched
before the queued follow-up wake. All 59 lab-harness tests and the
warning-strict targeted regression pass.

**Expected effect.** Time-sensitive, already-admitted experiments should begin
one director turn earlier instead of losing claim runway to a redundant
follow-up pass. The director can still consume concurrent terminals while the
researcher claims and patches the warm bench, preserving scientific ownership
and avoiding a cold restart. If endpoint evidence remains worthwhile, the
director may issue a fresh binding against the same exact instance and disk;
the closed binding must not be claimed late.

## 2026-07-25T20:50Z — rotate a context-exhausted control-plane thread

**GPU audit.** One grouped authenticated Nebius listing exactly matched the
sole non-retired inventory bench: RUNNING H200 instance
`computeinstance-e00vyqp7gxsr34wrtz` and attached READY disk
`computedisk-e00dryj6tbensjs413`. No provider-only or inventory-only resource
was present. The controller-user watchdog remains active at PID `828601` in
its recorded cgroup through `22:00Z`; no deadline or stale-claim fence is
indicated. The grouped-head owner first claimed at `20:44:55Z`, encountered a
pre-science `Operation not permitted` hardlink error, released after 3.9
seconds, and returned the mistakenly maintenance-marked bench to ready. It
then corrected both staging and cumulative-spend handling and reclaimed the
same warm bench at `20:46:53Z`; PID `1195308` with start ticks `112843095` is
live and claim heartbeats advanced through `20:48:23Z`. No provider teardown,
cold setup, or new resource occurred. The approximately 24-minute warm gap
since the hybrid release cost about `$0.98` and was justified by this
source-complete, resident-state-compatible replay.

**Bottleneck.** The scheduler reload fix worked: the grouped-head researcher
launched immediately after the `20:42:03Z` director completion and patched
both integration failures against the retained bench. The control plane then
failed independently. Three consecutive fallback directors at `20:45:21Z`,
`20:46:33Z`, and `20:47:39Z` resumed the same saturated Codex thread and
failed in 10--12 seconds with `Codex ran out of room in the model's context
window`, before any decision. This prevented the director from consuming the
new pre-science evidence or correcting a portfolio that currently has only
the H200 grouped-head lineage active, despite the campaign contract requiring
a direct endpoint lane plus an independent deep-mechanism/hardware lane while
authority remains.

**Change.** `lab_harness.py` now recognizes that exact failed-run marker and
clears only the affected role's resumable thread ID, recording
`agent_thread_rotated`. Startup reconciliation also rotates a saturated
thread recorded by the prior harness process, so this live reload will not
waste another wake replaying it. Durable repository state, reservations,
bench ownership, and other agent threads are untouched. Two regressions cover
same-process and post-reload recovery; all 61 lab-harness tests pass and
`git diff --check` is clean.

**Expected effect.** The next director wake starts a fresh context from the
compact durable portfolio instead of failing once per minute, restoring
scientific scheduling without disturbing the claimed mutable H200 repair.
The revived director should preserve that live owner and use free researcher
capacity for an independent no-H200 source/kernel/simulation/telemetry or
hardware-comparison opportunity; after the serial H200 queue clears, it should
decide whether to issue a fresh direct-endpoint binding rather than treating
the missed `20:30Z` binding as satisfied.

## 2026-07-25T20:59Z — make context-rotation recovery decision-first

**GPU audit.** One grouped authenticated Nebius listing exactly matched the
sole non-retired inventory bench: RUNNING instance
`computeinstance-e00vyqp7gxsr34wrtz` with READY disk
`computedisk-e00dryj6tbensjs413`. No provider-only or inventory-only resource
was present. The recorded controller-user watchdog is loaded and active at
PID `828601` in its exact cgroup through `22:00Z`. The grouped-head owner
heartbeated its claim, completed in 93.46 seconds, and released ready at
`20:48:27Z`; no stale claim, passed deadline, dead lifecycle owner, teardown,
or cold restart exists. The available bench retained the exact checkpoint,
image, compiler, CUDA, source, and newly materialized tied-weight state. Its
short idle exposure is justified by the director's in-progress matched
endpoint continuation and remains far below the measured cold-setup cost.

**Outcome and bottleneck.** The replay answered the model-specific question:
the exact captured `[384,262144]` live-buffer consumer preserved target IDs,
top-two values, accepted decisions, pointer identity, and replay exactly while
reducing median graph time from `9.201120` to `4.182976 ms` (`54.5384%`) for
`$0.0662405`. The prior harness change also worked: startup emitted
`agent_thread_rotated` at `20:50:49Z` and the fresh director correctly chose
one matched H200 endpoint pair plus an independent no-GPU mechanism lane.
However, before its first durable mutation that fresh turn used more than
seven minutes, 50 tool actions, and about 1.2 MB of trace, mostly enumerating
completed projects, rereading historical evidence reviews, and reconstructing
settled reservations already summarized by the compact prompt. During that
orientation the portfolio remained empty and the warm H200 remained idle.

**Change.** The `research-director` skill now makes context-rotation recovery
explicitly decision-first. The compact active portfolio, latest director and
supervisor handoffs, GPU snapshot, and spend snapshot are the resume contract;
before the first portfolio mutation the director reads only the governing
campaign section and one or two newly named decision artifacts. It must not
enumerate completed projects or reread historical reviews merely to regain
orientation, and an empty portfolio regains its direct and independent lanes
before any necessary history synthesis is delegated. This instruction affects
future turns only and does not interrupt the director currently binding those
two lanes.

**Expected effect.** A rotated director should convert a new terminal into
durable experiments within roughly one focused decision pass instead of
spending the warm handoff window rebuilding campaign history. That should
reduce paid idle time, avoid another context saturation, and preserve the
campaign's required direct endpoint plus independent deep-mechanism
concurrency without prescribing either scientific hypothesis.

## 2026-07-25T21:23Z — accept bench identity on owned heartbeat and release

**GPU audit.** One grouped authenticated Nebius listing exactly matched the
sole non-retired inventory bench: RUNNING instance
`computeinstance-e00vyqp7gxsr34wrtz` and READY disk
`computedisk-e00dryj6tbensjs413`. The recorded controller-user watchdog was
loaded and active at PID `828601` in its exact cgroup through `22:00Z`. The
phase-selective project claimed the same warm H200 at `21:16:17Z`; the active
researcher repaired against resident state after two pre-terminal integration
failures, retrieved a conservative infrastructure terminal, and released the
bench ready at `21:21:25Z`. No provider teardown, cold restart, stale claim,
passed deadline, or unsafe ownerless interval remained.

**Bottleneck and evidence.** The scientific worker eventually completed, but
its third PID-backed owner died after terminal retrieval because it invoked
the shared pool as `release --project ... --bench <exact-id>`, while
`gpu_pool` accepted `--bench` only on claim. The same owner encoded heartbeat
with this exact unsupported shape, so it never advanced the claim heartbeat.
The researcher had to recognize the lifecycle-only failure and issue a
separate release despite already possessing the exact bench identity. This
was the final one of three project-local owner repairs during a roughly
five-minute claim; it did not justify teardown or invalidate the measured
artifact.

**Change.** `grad_research.gpu_pool` now accepts an optional `--bench` on
heartbeat and release. It does not ignore the field: the pool verifies that
the project owns that exact bench before mutating the claim, preserving
fail-closed ownership while remaining backward-compatible with existing
project-only callers. Two regressions cover successful CLI heartbeat/release
and mismatched identity rejection; all 12 GPU-pool tests pass and
`git diff --check` is clean.

**Expected effect.** Generated detached owners can carry the exact resource ID
through claim, heartbeat, and release without a command-shape translation or
terminal-owner crash. Future recoverable worker faults should remain one
claimed mutable-bench repair, with live heartbeat and immediate release after
retrieval, rather than consuming researcher time on a separate lifecycle
repair.

## 2026-07-25T21:37Z — retry context exhaustion without a director detour

**GPU audit.** One grouped authenticated Nebius listing exactly matched the
sole non-retired inventory bench: RUNNING instance
`computeinstance-e00vyqp7gxsr34wrtz` and READY disk
`computedisk-e00dryj6tbensjs413`. The controller-host user watchdog was loaded
and active at recorded PID `1230392` in its exact cgroup through `01:30Z`.
There was no provider-only or inventory-only resource, stale claim, passed
deadline, or owner/watchdog mismatch. The H200 was available from `21:21:25Z`
until the fresh phase-selective researcher claimed it at `21:35:02Z`; its
heartbeat advanced at `21:36:49Z`. Retaining the resident checkpoint, pinned
image/source, compiler, and CUDA caches for this compatible full-model run was
therefore justified. No drain, teardown, or cold restart occurred.

**Bottleneck and evidence.** The first newly admitted direct researcher exited
after `5.725 s` because its resumed Codex context was exhausted before any
project mutation, claim, spend, or scientific invocation. The harness correctly
cleared the thread, but then classified the unchanged project as generic
`researcher_no_progress`, imposed its cooldown, and woke the director. The
director spent `207.294 s` and about `1.26 MB` of trace to authorize the same
unchanged experiment in a fresh context. This added roughly 3.5 minutes to a
13.6-minute warm-bench handoff without creating a portfolio decision. The
fresh researcher has since claimed the retained H200 and is replacing the
synthetic adapter with a durable pinned full-model owner. In parallel, the
certified-lazy vocabulary lane returned a source-complete exact-fallback
candidate at `$0`, and the FP8 weight-stream lane remains independently active.

**Change.** The event-driven lab harness now treats its already typed
`context_window_exhausted` researcher result as a transport retry: after
`_run_agent` clears the exhausted thread, it records
`researcher_retry_queued` and immediately makes the unchanged active project
eligible on the same model route. It does not apply the generic no-progress
cooldown or wake the director. Ordinary unchanged turns, service-capacity
failures, scientific terminals, project mutations, and director decisions
retain their existing paths. The complete harness module passes all 62 tests,
including a new event-loop regression proving two fresh-thread attempts and no
intervening director/no-progress event.

**Expected effect.** A future exhausted researcher context should resume the
same unconsumed experiment in seconds rather than spending one director turn
and several paid-idle minutes on an identical admission decision. This
preserves scientific authority and the active project's exact contract while
shortening time from direct-lane admission to a warm-bench claim.

## 2026-07-25T21:51Z — fence ownerless full-model H200 claim

**GPU audit and actionable mismatch.** One grouped authenticated Nebius
listing exactly matched the sole non-retired inventory resource: RUNNING
instance `computeinstance-e00vyqp7gxsr34wrtz`
(`gemma4-dflash-h200-adapter-20260725t1512z`) and READY disk
`computedisk-e00dryj6tbensjs413`
(`gemma4-dflash-h200-adapter-20260725t1512z-boot`). The controller-host user
watchdog remains loaded and active at recorded PID `1230392` in its exact
cgroup through `01:30Z`. The experiment lifecycle owner does not: project
metadata records `unit_manager: pid`, PID `1246836`, start ticks `113153601`,
but `/proc/1246836` is absent. Its state last advanced to
`full_model_invocation` at `21:42:27Z`, the claim heartbeat stopped at
`21:44:38Z`, and no component or endpoint terminal exists. This is an
objectively ownerless claimed bench even though the one-hour pool lease has not
yet aged stale.

**Safety action and director handoff.** Marked registered bench
`h200-dflash-adapter-e00vyqp7gxsr34wrtz` draining; because it is still claimed,
the inventory now has `drain_after_release: true` and retains the claim for
director inspection rather than stealing or releasing it. The director should
inspect whether a remote full-model worker or partial 62.5-GB snapshot remains,
then reclaim to maintenance and decide warm repair/reuse versus provider
cleanup. Exact provider cleanup identifiers are instance
`computeinstance-e00vyqp7gxsr34wrtz` and disk
`computedisk-e00dryj6tbensjs413`. Do not let the queued certified-lazy
real-weight component claim this bench until that inspection and an explicit
`ready` transition. No provider cleanup or inventory retirement was performed.

**Expected effect.** The drain fence prevents a second researcher from
mutating a bench whose remote process and partially copied checkpoint are
unknown, while preserving the resident checkpoint, image, compiler, and CUDA
caches for a director-authorized in-place recovery. It also prevents the
healthy absolute watchdog from being mistaken for a healthy experiment owner.

## 2026-07-25T22:02Z — recheck durable owners at the reload boundary

**GPU audit and recovered outcome.** One grouped authenticated Nebius listing
again exactly matched the sole non-retired inventory resource: RUNNING instance
`computeinstance-e00vyqp7gxsr34wrtz` and READY disk
`computedisk-e00dryj6tbensjs413`. The controller-host user watchdog remains
loaded and active at PID `1230392` in its recorded cgroup through `01:30Z`.
The director's single fenced-guest inspection found no worker, container, or
GPU process, an intact 62.58-GB project-local checkpoint, and a typed terminal
written remotely at `21:48Z`. It atomically reclaimed the dead claim to
maintenance, recovered the terminal, and returned bench
`h200-dflash-adapter-e00vyqp7gxsr34wrtz` available at `22:00:49Z` with the
drain fence cleared. The terminal is a pre-science full-model construction OOM;
no candidate invocation or scientific component was consumed. The retained
bench is compatible with the already queued certified-lazy and FP8
exact-consumer components, so its short idle cost is justified. No provider
cleanup or inventory retirement was performed.

**Bottleneck and evidence.** The missing terminal was caused by a harness
reload race, not a failed remote worker. The harness observed changed source
and committed to `drain_active_agent_turns_then_reload` at `21:37:18Z`, before
the phase-selective researcher registered PID owner `1246836` at `21:38:38Z`.
The owner then copied the resident checkpoint and entered the full-model
invocation, but the pending reload did not recheck PID-managed sessions after
the agent turns drained. The harness restarted at `21:45:17Z`; the controller
heartbeat stopped at `21:44:38Z`, while the guest container survived long
enough to write its terminal roughly three minutes later. This stranded a
valid infrastructure result, held the only H200 behind an ownerless claim, and
delayed the two ready component falsifiers until supervisor fencing and
director recovery. It also explains why the nominally detached controller
survived its researcher turn but not the later harness restart.

**Change.** The event-driven harness now rechecks live PID-managed
`STATUS.json.active_session` records at the actual reload boundary, after all
agent futures have drained. If a researcher registered a durable owner after
the initial source-change snapshot, the harness cancels the pending reload,
records `harness_reload_deferred` with disposition
`cancel_pending_reload_for_new_pid_sessions`, and continues until that owner
finishes. Once the owner is gone, the unchanged source digest triggers the
normal reload. A new event-loop regression reproduces registration during the
drain window and proves the pending reload is canceled. All 63 harness tests
pass.

**Expected effect.** Harness improvements can no longer kill a newly launched
claim controller merely because its owner appeared after the first reload
check. Long checkpoint materialization, warm-bench integration repair, compact
terminal retrieval, and final release should remain in one claimed mutable
session, avoiding stranded remote outcomes, stale claims, director recovery
turns, and cold-restart pressure without delaying reloads once the owner
actually completes.

## 2026-07-25T22:19Z — reconcile claim-dependent director decisions at commit

**GPU safety audit (measured).** One grouped authenticated Nebius listing
contained exactly the registered live resources: RUNNING instance
`computeinstance-e00vyqp7gxsr34wrtz` and READY disk
`computedisk-e00dryj6tbensjs413`. There were no provider-only or
inventory-only resources. On the recorded controller-host namespace,
`gemma4-phase-selective-h200-20260726t0130-watchdog.service` was active with
main PID `1230392` and its `2026-07-26T01:30:00Z` deadline had not passed. The
certified-lazy project claimed the H200 from `22:14:53Z` to `22:17:27Z`,
persisted an exact-input boundary without starting CUDA, and released the
bench ready with resident state intact. Its preceding 843.9-second idle gap
and current short idle cost at `$2.45/hour` remain justified by the prepared
FP8 component and DFlash capture queued for the same H200. No claim was stale,
no lifecycle owner was lost, and no drain, provider cleanup, or inventory
retirement was warranted.

**Bottleneck and evidence.** The live release crossed two concurrent
scheduler turns. The FP8 successor started at `22:17:17Z` from the earlier
claimed snapshot, the lazy owner released ten seconds later, and FP8 still
returned `researcher_no_progress` at `22:17:36Z`. The concurrent director
likewise continued toward parking FP8 behind the purported live lazy owner
after the bench was already available. The lazy researcher correctly cleared
its `active_session` before exiting, so the defect was not an unsafe or
orphaned claim; it was a stale decision premise at commit time. This directly
delays the next model-scoped H200 falsifier and leaves a paid warm bench idle.

**Change.** The research-director skill now requires one local durable-record
re-read immediately before persisting any portfolio or lifecycle mutation
whose premise is a live claim, project owner, predecessor terminal, or bench
availability. If that premise changed during the turn, the director must
recompute or abandon the stale mutation. This is dynamic commit-time
reconciliation, not provider polling, static validation, or a new project.

**Expected effect.** A release or owner exit that races a director snapshot
will advance the already-prepared warm successor instead of parking it behind
work that has finished. The change should remove avoidable one-minute retry
cycles and paid idle gaps without changing experiment order, replaying a
scientific arm, or disrupting an active claim.

## 2026-07-25T22:26Z — make the next warm-bench claimant exclusive

**GPU safety audit (measured).** One grouped authenticated Nebius listing
again contained exactly the sole non-retired inventory resources: RUNNING
instance `computeinstance-e00vyqp7gxsr34wrtz` and READY disk
`computedisk-e00dryj6tbensjs413`. The recorded controller-host user watchdog
was loaded and active at PID `1230392` in its exact cgroup, with the
`2026-07-26T01:30:00Z` deadline still open. No provider-only or
inventory-only resource, stale claim, passed deadline, or lost lifecycle
watchdog was found. The current certified-lazy claim is fresh and its
foreground researcher turn is still active, so it is not objectively
ownerless and was not fenced. The H200's 462.3-second idle interval after the
previous release was justified by two compatible prepared measurements; no
drain or provider cleanup was warranted.

**Bottleneck and evidence.** The previous commit-time reconciliation worked:
at `22:20Z` a fresh director snapshot reactivated the prepared FP8 component
for the available H200. The director nevertheless left the higher-priority
certified-lazy project scheduler-active even though its durable handoff says
the required exact 384-row capture is absent and must be staged before
reclaim. At `22:25:09Z` certified-lazy therefore repeated its claim before the
input existed. FP8 launched its admitted PID-backed owner at `22:25:27Z`, but
the atomic pool rejected that owner before staging or CUDA and PID `1289161`
exited with `typed_pool_boundary:claim`. The pool prevented double ownership,
but prose queue order and priority did not prevent a non-runnable project
from displacing the model-scoped measurement chosen by the director.

**Change.** The research-director skill now requires an exclusive serial-lane
admission: when choosing the next claimant for one warm bench, the director
must pause or dependency-gate every competing same-bench project until its
own prerequisite is durable. A project missing a required input may continue
offline work only when its scheduler state cannot claim the bench. This is a
portfolio-state correction, not another validator, project, or hardware rule.

**Expected effect.** The next admitted exact-consumer measurement should claim
the warm H200 once, while capture-building or later-retry projects remain
offline until runnable. Atomic claim failures, dead detached owners, repeated
input discovery, and paid queue churn should fall without changing scientific
order, taking over candidate selection, or interrupting a live experiment.

## 2026-07-25T22:46Z — use the established Nebius Docker privilege path

**GPU safety audit (measured).** One grouped authenticated Nebius listing
exactly matched the sole non-retired inventory resource: RUNNING instance
`computeinstance-e00vyqp7gxsr34wrtz` and READY disk
`computedisk-e00dryj6tbensjs413`. The controller-host user watchdog is loaded
and active at PID `1230392` in its recorded cgroup through `01:30Z`. At the
audit snapshot, FP8 weight-stream held a fresh claim with heartbeat
`22:43:26Z` and live PID-managed outer owner `1304499`. A final local
reconciliation found that owner had subsequently released the unoccupied
bench to `maintenance` at `22:45:31Z`, before its deadline and without
provider teardown. No provider mismatch, stale claim, passed deadline, lost
owner, or unsafe state was found, so no drain, provider cleanup, or inventory
retirement was warranted. The preceding 348.9-second idle gap cost about
`$0.237` and ended in the prepared FP8 claim; the independent B200
block-scaled screen remains active without a GPU claim.

**Bottleneck and evidence.** The FP8 owner first invoked `docker` directly as
`glmrunner`; `/var/run/docker.sock` rejected the command before the container
or CUDA. This launch defect is recurrent rather than project-specific: prior
DFlash, sustained-ngram, upstream-runtime, and H100 verify-pipeline artifacts
record the same denial and establish `sudo -n docker` as the non-destructive
repair. The live claim and repair handshake did preserve resident state, and
the privileged retry then executed M32. That retry exited `1` with repeated
`sm90a` target diagnostics and an exact-output mismatch, including final-BF16
maximum absolute error `0.01092529296875`; M384 correctly did not run. This is
an invalid implementation/exact-consumer outcome, not a latency measurement or
evidence against the whole weight-stream mechanism.

The repaired outcome was not adopted by the durable record:
`REPAIR_TERMINAL.json` and `STATUS.json` still contain only the original
Docker-permission error, say `scientific_sample_consumed: false`, and instruct
the next turn to repeat the Docker repair and unchanged M32. The raw repaired
stdout/stderr and exit file prove that operation already ran. This stale
terminal can cause a duplicate candidate invocation and a false close or
reopen decision.

**Change.** The researcher skill now tells Nebius `glmrunner` owners to use
`sudo -n docker` from the first execution-equivalent command unless the bench
record explicitly proves direct socket access, and forbids socket or account
permission mutation. It also requires a researcher-executed repair to persist
exit status, evidence paths, invocation markers, and classification before
release, and requires the owner to adopt that repaired terminal rather than
overwrite it with the original error. The skill validates successfully. The
director should reconcile the existing FP8 raw M32 outcome before authorizing
any retry; the supervisor did not mutate that project's scientific status.

**Expected effect.** Future Nebius component and endpoint owners should cross
the first real container/CUDA boundary without spending a paid claimed attempt
and repair turn on a known account-permission failure. When another defect
appears after repair, the lab should consume the actual repaired outcome once
instead of releasing with a stale pre-repair terminal and replaying it. No
static readiness ladder, cold restart, or new project was added.

## 2026-07-25T23:06Z — preserve the original claim clock across repair owners

**GPU safety audit (measured).** One grouped authenticated Nebius listing
contained exactly the sole non-retired inventory resources: RUNNING instance
`computeinstance-e00vyqp7gxsr34wrtz` and READY disk
`computedisk-e00dryj6tbensjs413`. The recorded controller-host user watchdog
`gemma4-phase-selective-h200-20260726t0130-watchdog.service` is loaded and
active with main PID `1230392` in its exact cgroup, and its
`2026-07-26T01:30:00Z` deadline has not passed. The H200 is unclaimed in
`maintenance` after DFlash released it; no provider-only or inventory-only
resource, stale claim, passed deadline, lost lifecycle owner, or unsafe state
was found. No drain, provider cleanup, or inventory retirement is warranted.
Warm retention remains justified because DFlash needs only a corrected
immutable source binding to resume on the resident pinned image and
checkpoint.

**Bottleneck and evidence.** DFlash repaired its controller-list and remote
staging defects without teardown, then correctly failed closed before CUDA
when three admitted source hashes differed from the retained image. The pool
records one continuous claim from `22:59:05.486523Z` through
`23:01:47.135132Z`: `161.648609` seconds, or `$0.110010858903` at
`$2.45/hour`. Its project terminal instead starts the clock at the final
replacement owner's launch and reports `96.649062` seconds and
`$0.065774266639`, undercounting the retained repair claim by `64.999547`
seconds and `$0.044236592264`. This does not alter the typed
`binding_metadata_defect` outcome, but repeated owner handoffs would make
experiment cost and budget settlement systematically optimistic. The
independent FP8 lane meanwhile localized its consumed failure to an `sm_90`
versus `sm_90a` build defect without another GPU sample, so the weight-stream
mechanism was not falsely closed.

**Change.** The researcher skill now requires replacement owners and repair
handoffs to inherit the pool claim's original `claimed_at` timestamp and to
compute `claim_seconds` and experimental spend across the full continuous
`bench_claimed`-to-`bench_released` interval. The supervisor did not rewrite
the DFlash terminal or project status; the director should reconcile this
specific `$0.044236592264` exposure delta during normal settlement.

**Expected effect.** Warm repair remains the default, but restarting a
controller can no longer reset its accounting clock. Future repaired
experiments should preserve accurate cost-per-outcome and remaining-budget
decisions without adding static validation, another project, a cold restart,
or any interruption to the retained H200.

## 2026-07-25T23:18Z — make maintenance-to-claim a director-owned handoff

**GPU safety audit (measured).** One grouped authenticated Nebius listing
again exactly matched the sole non-retired inventory resources: RUNNING
instance `computeinstance-e00vyqp7gxsr34wrtz` and READY disk
`computedisk-e00dryj6tbensjs413`. The recorded controller-host user watchdog
`gemma4-phase-selective-h200-20260726t0130-watchdog.service` is loaded and
active with main PID `1230392` in its exact cgroup, and the `01:30Z` deadline
remains open. The H200 is unclaimed in `maintenance`; no provider-only or
inventory-only resource, stale claim, passed deadline, lost lifecycle owner,
or unsafe state was found. No drain, provider cleanup, or inventory retirement
is warranted because the prepared DFlash capture is exactly compatible with
the resident image and checkpoint.

**Bottleneck and evidence.** At `23:12:25Z` the director reactivated DFlash as
the sole warm-H200 claimant but explicitly retained the named bench unclaimed
in `maintenance`. The researcher rematerialized only the corrected six-hash
binding, passed the existing observer fixtures, and at `23:15:13Z` made the
single authorized atomic claim. The pool correctly rejected it because claims
admit only `available` benches. The resulting
`DFLASH_EXACT_REQUEST_STATE_CAPTURE_AVAILABILITY_BLOCKER.json` is
`pre_science`: no remote access, CUDA invocation, or sample occurred. The
researcher turn then completed after `318.255` seconds with status
`blocked_external_bench_availability`. The bench had remained maintenance
from `23:01:47Z` through the audit, about `956.865` seconds and `$0.6512` of
idle exposure. This is not a provider or scientific blocker; it is an
incomplete director-owned lifecycle handoff that prevented the direct lane
from reaching the campaign's exact-c32 causal measurement.

**Change.** The research-director skill now requires a maintenance-to-claim
decision to complete before scheduling the sole claimant. When recorded state
and any required inspection prove a bench safe, unoccupied, and compatible,
the director marks it `ready`; otherwise it keeps the project durably
non-claimable and records the exact remaining lifecycle action. The supervisor
did not mutate the pool or take over the DFlash project. The director should
reconcile bench `h200-dflash-adapter-e00vyqp7gxsr34wrtz` and then resume the
already-prepared same-project capture.

**Expected effect.** Prepared warm-bench experiments should atomically claim
on their first execution turn instead of spending a researcher slot and paid
idle interval rediscovering a known maintenance state. This removes a
coordination-only turn without adding validation, another project, a cold
restart, or any change to scientific ordering.

## 2026-07-25T23:50Z — namespace repeated in-place repair episodes

**GPU safety audit (measured).** One grouped authenticated Nebius listing
exactly matched the sole non-retired inventory resources: RUNNING instance
`computeinstance-e00vyqp7gxsr34wrtz` and READY disk
`computedisk-e00dryj6tbensjs413`. The controller-host user watchdog
`gemma4-phase-selective-h200-20260726t0130-watchdog.service` is active with
main PID `1230392` in its recorded cgroup, and its
`2026-07-26T01:30:00Z` deadline remains open. The H200 is unclaimed in
`maintenance`; no provider-only or inventory-only resource, stale claim,
passed deadline, lost lifecycle owner, or unsafe state was found. No drain,
provider cleanup, or inventory retirement is warranted. Warm reuse remains
justified by the director's serialized corrected SM90a retry and then the
already-prepared DFlash exact-c32 arm.

**Bottleneck and evidence.** The FP8 SM90a arm claimed the warm H200 at
`23:42:34.399Z`, heartbeated it, and released it to maintenance at
`23:42:57.125Z`: only `22.727651` claimed seconds before any CUDA or M32
invocation. The pinned CUTLASS tree lacked one explicitly included epilogue
header, so the researcher removed only that redundant include and produced
corrected source hash
`6fbf49458dd9020f6d8f5c94bc98a5ebbf0606ef42e223216618d2c09399803`.
This was an ordinary pre-science integration repair. The owner nevertheless
could not create a new repair request because the project root still held the
hash-bound Docker-permission `REPAIR_REQUEST.json` from the prior episode;
that earlier READY deadline had already expired at
`2026-07-25T23:07:41.523592Z`. The collision forced release and director
re-admission instead of an in-place patch-and-rerun against resident state.

**Change.** The shared `repair-handshake` helper now accepts an optional
validated `--repair-id` on `ready`, `request`, `status`, and `wait`. Repeated
episodes under one project root are isolated at
`.repair-handshakes/CLAIM_OR_ATTEMPT_ID/`, retaining each old hash-bound pair
while preserving the existing unscoped behavior. The emitted
`handshake_root` can be recorded as the harness session's `artifact_root`.
Focused tests cover two independent episodes, request binding, legacy
idempotence, deadlines, waits, and path-traversal rejection; all seven tests,
Python compilation, DevEx checks, and diff checks pass. No active project,
pool state, or lifecycle process was mutated.

**Expected effect.** A later recoverable integration defect can open a fresh,
bounded repair episode without deleting prior evidence or relinquishing the
warm GPU claim. This should turn the observed release/re-admission cycle into
one retained-claim patch-and-rerun while preserving deadline and hash-binding
safety, without adding static validation, another project, or a cold restart.

## 2026-07-25T23:59Z — stop scheduling completed offline lanes while queued

**GPU safety audit (measured).** One grouped authenticated Nebius listing
contained exactly the sole non-retired inventory resources: RUNNING instance
`computeinstance-e00vyqp7gxsr34wrtz` and READY disk
`computedisk-e00dryj6tbensjs413`. At the initial audit, FP8 held a fresh claim
with a `23:55:03Z` heartbeat and live controller PID `1363573` whose recorded
start ticks matched `/proc`; the controller-host user watchdog
`gemma4-phase-selective-h200-20260726t0130-watchdog.service` was active as PID
`1230392` in its exact cgroup with deadline `2026-07-26T01:30:00Z`. During the
review the bounded FP8 owner persisted its terminal and released the bench to
`maintenance`. No provider/inventory mismatch, stale claim, passed deadline,
lost owner, or unsafe state exists. Do not drain: the already-prepared
candidate-only DFlash arm is compatible with the resident image, checkpoint,
and caches; the director should reuse the bench after its normal
maintenance-to-ready handoff.

**Bottleneck and evidence.** DFlash completed its zero-GPU RID-lifetime repair
before `23:49Z` and its only next action was to wait behind SM90a. Four director
decisions kept it `active` with `allocation_limit: 0` and prose saying
non-claimable. The harness schedules every `active` or `ready` project and does
not interpret `allocation_limit` as a researcher-turn gate, so it launched
DFlash four times between `23:49:56Z` and `23:58:03Z`. Those turns consumed
`89.045 + 104.430 + 47.543 + 3.744 = 244.762` agent-seconds, produced no new
model/workload evidence, emitted one `researcher_no_progress`, rotated one
exhausted thread, and caused repeated director wake/reconciliation cycles.
This was one serial bench lane, not useful portfolio concurrency.

**Change.** The research-director skill now states the executable scheduler
semantics: once offline work is complete and a project only awaits a
predecessor terminal or bench handoff, set `STATUS.json.status` to `paused`;
`allocation_limit: 0` plus prose queue order is not a turn gate. Reactivate it
in the director turn that observes the prerequisite durably satisfied. This
clarifies the skill's existing requirement to pause or dependency-gate serial
successors without changing any current project, GPU state, or active owner.
All eight repository skills validate and the patch passes `git diff --check`.

**Expected effect.** Serialized warm-bench successors should stop spending
researcher turns re-reading an unchanged queue boundary and stop waking the
director without evidence. The released slot can advance an independent
model-scoped lane, while the queued project resumes immediately after the
predecessor terminal and retains the same warm-bench itinerary—no added
project, static readiness ladder, teardown, or cold restart.

## 2026-07-26T00:12Z — trip required observers on the first live exception

**GPU safety audit (measured).** One grouped authenticated Nebius listing
exactly matched the sole non-retired inventory resources: RUNNING instance
`computeinstance-e00vyqp7gxsr34wrtz` and attached READY disk
`computedisk-e00dryj6tbensjs413`. DFlash held a continuous fresh claim from
`00:03:00.434997Z` with heartbeat `00:10:22.686958Z`; its controller-local
candidate-only owner was alive through evidence retrieval. The controller-host
user watchdog
`gemma4-phase-selective-h200-20260726t0130-watchdog.service` was active as
recorded PID `1230392` in its exact cgroup, before the
`2026-07-26T01:30:00Z` deadline. No provider/inventory mismatch, stale claim,
passed deadline, lost owner, unsafe state, or unjustified idle bench exists.
No drain, provider cleanup, or inventory retirement is warranted.

**Bottleneck and evidence.** The candidate-only DFlash owner correctly reused
the warm claimed H200 and never replayed immutable `ar-c32`, but its required
request-state observer encountered `ForwardBatch.rids is unavailable`. The
hook swallowed and logged that same live API mismatch `340` times (`317`
DFlash-worker and `23` TP-worker exceptions), allowing all 32 candidate
requests and `48.361031647` seconds of candidate batch time to complete before
retrieval reported `worker_exit_code: 1` and `summarize_exit_code: 79`.
Consequently the paid arm produced complete responses but no interpretable
state capture and no scientific DFlash comparison. This is a live observer
integration failure, not evidence about the mechanism; the active researcher
is retaining the claim and repairing it in place.

**Change.** The researcher skill now requires a decision-critical injected
observer to trip on its first runtime exception: persist one compact
diagnostic, suppress repeated hook errors, stop or cancel remaining workload
as soon as safely possible, and enter same-claim repair. It explicitly rejects
both completing a full arm under a failing required observer and substituting
another static preflight. No active project, owner, GPU record, or scientific
scope was changed.

**Expected effect.** The next ordinary observer/runtime mismatch should consume
only the shortest live discriminator needed to expose it, rather than an
entire endpoint arm plus hundreds of redundant exceptions. The researcher can
patch and rerun against the same resident server, checkpoint, image, and
claim, shortening time and spend to the first interpretable exact-c32
comparison without adding a project, validation ladder, teardown, or cold
restart.

## 2026-07-26T00:20Z — reuse the released DFlash bench after observer repair

**GPU safety audit and transition (measured).** The single grouped
authenticated Nebius listing exactly matched the sole non-retired inventory
resources: RUNNING instance `computeinstance-e00vyqp7gxsr34wrtz` and attached
READY disk `computedisk-e00dryj6tbensjs413`. At `00:17:39Z`, DFlash held the
continuous claim opened at `00:03:00.434997Z`, with a fresh
`00:17:25.400154Z` heartbeat and live controller-host user watchdog
`gemma4-phase-selective-h200-20260726t0130-watchdog.service` (recorded PID
`1230392`, exact cgroup, deadline `01:30Z`). During this review the project
released the bench to `maintenance` at `00:17:48.629271Z`; the claim is now
clear and the lifecycle watchdog remains active. No provider/inventory
resource mismatch, passed deadline, unsafe state, or reason to drain exists.

**Actionable mismatch.** The replacement observer obtained logical RIDs from
the schedule requests, but its prefill sizing still referenced absent
`ScheduleBatch.rids`. This second attempt therefore ended with
`worker_exit_code: 1` and `summarize_exit_code: 79`, again without an
interpretable state capture or scientific DFlash sample. The project has
already implemented the narrow sizing fix, but its controller unconditionally
maps every nonterminal summarizer code to `gpu_pool release --condition
maintenance`. Consequently a recoverable observer integration error broke the
same-claim repair loop. Project status still records
`candidate_scientific_sample_consumed: false` and the now-dead replacement
owner PID, while inventory's resident description remains mostly the prior
FP8 state even though the retrieved DFlash container record was running.

**Director handoff and expected effect.** Do not tear down or cold-start.
Reconcile this exact maintenance bench back to ready and reuse instance
`computeinstance-e00vyqp7gxsr34wrtz` plus disk
`computedisk-e00dryj6tbensjs413` for the already-prepared final observer sizing
repair; refresh the resident description from the retrieved DFlash state.
The researcher skill change logged at `00:12Z` already forbids this
full-arm/release behavior, but the current researcher turn and its controller
predated that change, so no duplicate rule or new project is warranted.
Applying it on the next owner should retain the warm claim through any further
ordinary observer defect and shorten time to the first interpretable
exact-c32 comparison.

## 2026-07-26T00:49Z — preauthorize process-start-only same-claim repairs

**Bottleneck and evidence.** The phase-selective project retained
`h200-dflash-adapter-e00vyqp7gxsr34wrtz`, kept its claim heartbeating, and
produced the missing `forward_batch_dual_cache_driver.py` plus a healthy
resident-model probe without consuming a scientific arm. The loaded server
predates that hook, so the repair can affect `ModelRunner.forward` only at
process start. The director binding nevertheless forbade restarting a healthy
server, forcing `REPAIR_READY.json` and another director approval cycle even
though model, workload, claim, provider lifecycle, spend, and deadlines are
unchanged. The registered Nebius resources remain exactly
`computeinstance-e00vyqp7gxsr34wrtz` and
`computedisk-e00dryj6tbensjs413`; the controller watchdog is active through
`01:30Z`.

**Change and expected effect.** Amended the researcher and director skills to
preauthorize a prepared, hash-bound experiment server/container replacement
when an admitted ordinary integration patch is provably process-start-only.
The exception preserves the same claim, watchdog, immutable inputs, caches,
scientific arm, spend, and absolute deadline and does not authorize provider
mutation. Future owners can preload such a repair and continue directly into
the unconsumed operation, removing one director/researcher round trip while
avoiding provider teardown, restaging, or an extra project.

## 2026-07-26T01:06Z — reserve readiness labels for executable interventions

**GPU safety audit.** One grouped authenticated Nebius listing found running
instance `computeinstance-e00vyqp7gxsr34wrtz` and ready boot disk
`computedisk-e00dryj6tbensjs413`; they exactly match the sole non-retired
inventory bench `h200-dflash-adapter-e00vyqp7gxsr34wrtz`, with no live
provider resource absent from inventory and no non-retired inventory resource
missing at the provider. The controller-host user unit
`gemma4-phase-selective-h200-20260726t0130-watchdog.service` is active with
recorded PID `1230392` in its exact control group. The hybrid claim ran
continuously from `00:29:34Z` to `00:59:57Z`, heartbeated through `00:59:13Z`,
and released before both its project and `01:30Z` lifecycle deadlines. The
director then found no GPU compute process, returned the bench from maintenance
to available at `01:05:16Z`, and reactivated the compatible prepared DFlash
request-25 boundary probe. There is no stale claim, passed deadline,
owner/watchdog loss, provider mismatch, or drain action; immediate reuse is
more valuable than an idle-cost drain in the remaining watchdog window.

**Bottleneck and evidence.** The campaign still needs a direct measured route
from the locked `0.625149101968745 s/request` denominator to at most
`0.500119281574996`, but the admitted hybrid lane spent about 30.4 continuous
H200 claim minutes and reports `$1.61` cumulative exposure without one
interpretable component sample. Its offline terminal called the repair
`source_complete_operational_repair`, and the later handoff called
`forward_batch_dual_cache_driver.py` a completed production driver. In the
first real c32 activation, that file instead crashed its validation wrapper at
line 38 on `int(None)` before any `ForwardBatch` observation; the project
terminal also states that executable proxy-local and stock-shadow KV
operations are still absent. The director correctly paused this unprepared
repair and handed the warm bench to the already-runnable DFlash probe. The
process bottleneck is therefore not insufficient validation or too few
projects: support plumbing was promoted to measurement readiness before the
scientific intervention existed.

**Change and expected effect.** Amended the researcher and director skills so
`source-complete`, `operational repair`, and `measurement-ready` require the
intervention itself from production input through its first decision-bearing
consumer. Observers, validators, metadata hooks, attach proofs, and launchers
cannot satisfy that claim. Hardware-dependent implementation remains allowed
and should be patched and exercised inside the same paid project on a retained
mutable bench; the amendment explicitly forbids answering the gap with another
static gate or readiness project. This should prevent another full model-load
claim from discovering only that the core operation was never implemented,
while preserving the fast in-place repair behavior added at `00:49Z`.

## 2026-07-26T01:13Z — count the scientific submission, not pre-science launcher attempts

**GPU safety audit.** The one grouped authenticated Nebius listing returned
RUNNING instance `computeinstance-e00vyqp7gxsr34wrtz` and READY disk
`computedisk-e00dryj6tbensjs413`, exactly matching the sole non-retired
inventory bench `h200-dflash-adapter-e00vyqp7gxsr34wrtz`; there is no extra
provider resource or missing inventory resource. Controller-host user unit
`gemma4-phase-selective-h200-20260726t0130-watchdog.service` is active with
recorded PID `1230392` in its exact control group through `01:30Z`. At audit
start the bench was available with the compatible admitted DFlash probe. That
project claimed it at `01:12:24Z`, released it to maintenance at `01:12:32Z`
before the deadline, and left no stale claim. No owner/watchdog loss, unsafe
state, provider mismatch, or mandatory drain exists. The exact instance and
disk should be returned to ready and reused for the unsubmitted same-project
probe if its corrected launch still fits the watchdog window; provider cleanup
or inventory retirement remains a director decision.

**Bottleneck and evidence.** The request-25 project spent about 5.6 agent
minutes between scheduling and claim, then only `7.463872` claimed seconds
and `$0.0050786867` before terminalizing without starting a server, CUDA work,
or a scientific request. `remote.stderr` shows the localized cause:
`ValueError: not enough values to unpack` in the source-identity parser because
it split every output line as a SHA-256 row. This is the same banner/framing
class already repaired in place during the project's prior retained H200
attempt. The new binding nevertheless said both “exactly one” and “do not
repair or resubmit inside this binding”; the owner classified any remote
terminal as final and unconditionally released in its `finally` path.
`request_submission_count=0` and `science_started=false` prove that the
scientific one-request limit was never consumed. Cold restart after director
reconciliation is avoidable waste created by conflating one scientific
submission with one launcher attempt.

**Change and expected effect.** Amended the director skill so a one-request,
one-kernel-call, or one-sample binding counts only submissions after the
durable `science_started` marker. It now forbids encoding that limit as
no-in-run-repair, stop-on-any-infrastructure-terminal, or unconditional
release for recoverable pre-science launcher, identity-parser, or observer
defects. The owner must retain the claim through the repair handshake and
make the still-unsubmitted scientific call once; bound inputs remain immutable
and post-submission replay remains forbidden. This removes the binding
conflict that overrode the existing researcher repair-in-place rule without
adding validation, a project, or authority to broaden the experiment.

## 2026-07-26T01:25Z — keep support-parser gates proportional to observed input

**GPU safety audit.** One grouped authenticated Nebius listing returned
RUNNING instance `computeinstance-e00vyqp7gxsr34wrtz` and READY boot disk
`computedisk-e00dryj6tbensjs413`; these exactly match the sole non-retired
inventory bench `h200-dflash-adapter-e00vyqp7gxsr34wrtz`, with no provider
resource absent from inventory and no inventory resource missing at the
provider. The controller-host user unit
`gemma4-dflash-request25-repair-20260726t0140-watchdog.service` is active with
recorded PID `1421493` in its exact control group through `01:40Z`. The bench
has been available and unclaimed since `01:18:07Z`; there is no stale claim,
passed deadline, owner/watchdog loss, unsafe state, or drain action. Reuse is
still justified by the compatible DFlash retry and the active zero-GPU hybrid
implementation that requires a later H200 consumer check.

**Bottleneck and evidence.** The repaired request-25 owner was scheduled at
`01:19:41Z` but never claimed the warm bench or submitted its scientific call.
The observed Docker output had a banner plus eight exact bound digest rows,
and the local repaired parser passed its positive fixture plus missing,
altered, and unexpected identity cases. It stopped only because a newly added,
unobserved identical-duplicate-row fixture was accepted by dictionary
overwrite. `DFLASH_REQUEST25_BOUNDARY_PROBE_H200_RETRY1_TERMINAL.json` records
`science_started=false`, `request_submission_count=0`, zero incremental spend,
and another required source-hash rebinding. Thus an exhaustive support-parser
hardening case—not uncertainty in the actual source identities or the
scientific intervention—consumed another researcher/director cycle while the
bench idled. This is the static-validation failure mode the campaign should
not answer with more gates or projects.

**Change and expected effect.** Amended the director skill so a pre-science
support-parser gate remains fail-closed for missing, altered, unexpected, or
ambiguous required identities but stays proportional to the observed producer
contract. Unobserved robustness cases that change only support-code hygiene
must not force another hash binding and researcher round trip; any further
ordinary pre-science defect belongs in the retained-claim repair path. This
preserves exact identity and immutable scientific inputs while allowing the
next same-project owner to reach the one still-unsubmitted request instead of
adding another static gate.

## 2026-07-26T01:33Z — return before a near-term claim window erodes

**GPU safety audit.** One grouped authenticated Nebius listing returned
RUNNING instance `computeinstance-e00vyqp7gxsr34wrtz` and READY boot disk
`computedisk-e00dryj6tbensjs413`, exactly matching the sole non-retired
inventory bench `h200-dflash-adapter-e00vyqp7gxsr34wrtz`; no provider or
inventory resource is unmatched. The controller-host user unit
`gemma4-dflash-request25-repair-20260726t0148-watchdog.service` is active with
recorded PID `1430911` in its exact control group. The director atomically
replaced the prior watchdog at `01:29:58Z`, extending the deadline from
`01:40Z` to `01:48Z` without an unprotected interval. The bench remains
available, unclaimed, and compatible with the admitted DFlash probe and later
hybrid component. There is no stale claim, passed deadline, owner/watchdog
loss, unsafe state, or drain action; retention is justified against another
cold image/checkpoint setup.

**Bottleneck and evidence.** The director turn began at `01:24:22Z`. By
`01:30Z` it had persisted a runnable DFlash binding with a `01:36Z`
claim-before deadline and a `01:47Z` release bound, but the harness cannot
start that researcher until the director returns. When the independent hybrid
researcher completed its valid zero-GPU consumer implementation, the director
reconciled it, then continued inspecting closed projects to refill the second
lane. At `01:32:17Z` the director was still running, no successor DFlash
researcher had started, and `runtime/gpu_events.jsonl` contained no claim
after the `01:18:07Z` ready transition. Almost eight foreground director
minutes therefore consumed most of a twelve-minute admission window for the
still-unsubmitted scientific request. This is scheduling latency, not a need
for more validation or another project.

**Change and expected effect.** Amended the director skill so a newly durable
lane with a near-term claim, start, or warm-state deadline causes an immediate
return once lifecycle safety and claim exclusivity are persisted. Optional
capacity filling and completed-project scouting move to the already-queued
next director wake; concurrent reconciliation remains required only to prevent
an unsafe or conflicting claim. This should let the harness launch urgent GPU
work with the full intended window while preserving a later portfolio
rebalance and without changing scientific priorities or active experiments.

## 2026-07-26T01:46Z — failure-isolate observers inside one-shot science

**GPU safety audit.** One grouped authenticated Nebius listing returned
RUNNING instance `computeinstance-e00vyqp7gxsr34wrtz` and READY boot disk
`computedisk-e00dryj6tbensjs413`, exactly matching the sole non-retired
inventory bench `h200-dflash-adapter-e00vyqp7gxsr34wrtz`; no provider or
inventory resource is unmatched. The bench is unclaimed in `maintenance`
after DFlash released it at `01:39:01Z`, with no stale claim or passed
deadline. During this review the director atomically replaced the `01:48Z`
watchdog with controller-host user unit
`gemma4-hybrid-ngram-20260726t0225-watchdog.service`; it is active/running
under recorded PID `1443837` in the exact recorded control group through
`02:25Z`. Retention is justified by the newly bound compatible hybrid
ngram/H200 lane. There is no owner/watchdog loss, unsafe state, or drain
action.

**Bottleneck and evidence.** The DFlash retry used the retained H200 for about
200 seconds and submitted its one authorized request exactly once after
`science_started`. The request itself completed and produced the durable
228,550-byte `REQUEST25_RESPONSE.json`, but the required boundary observer
raised `AttributeError: 'ForwardBatch' object has no attribute
'req_to_token_pool'` at `dflash_worker_v2.py:528`. Consequently the terminal
contains no decision-bearing boundary record and correctly classifies this as
an infrastructure terminal rather than a scientific result; the submitted
request cannot be replayed. Seven CPU fixtures and exact source binding did
not protect the live call because the optional derived observer was allowed to
raise through the primary execution path. More static validation or a
successor project would not recover this evidence.

**Change and expected effect.** Amended the researcher skill's live-observer
contract. Pre-submission observer failures still stop and enter same-claim
repair, but an observer attached to a bounded or one-shot submission must now
be failure-isolated from the primary workload: persist the raw response and
smallest primitive snapshot before derived access, catch and serialize
observer errors, issue no further requests, and reconstruct offline from
immutable artifacts without replay when possible. This should preserve the
only paid invocation and its decision evidence when optional interpretation
code encounters a runtime API mismatch, while keeping fail-fast behavior for
unsubmitted or multi-request work and adding neither a static gate nor a new
scientific project.

## 2026-07-26T01:54Z — retain pre-science runtime failures for in-place repair

**GPU safety audit.** One grouped authenticated Nebius listing returned
RUNNING instance `computeinstance-e00vyqp7gxsr34wrtz` and READY boot disk
`computedisk-e00dryj6tbensjs413`, exactly matching the sole non-retired
inventory bench `h200-dflash-adapter-e00vyqp7gxsr34wrtz`; there are no
unregistered provider resources or missing inventory resources. The recorded
controller-host user watchdog
`gemma4-hybrid-ngram-20260726t0225-watchdog.service` is active/running at PID
`1443837` in its exact control group through `02:25Z`. The hybrid owner PID
`1449272` initially matched recorded start ticks `114661750` and heartbeated
its claim, with no stale claim or passed deadline. It subsequently released
the bench to `maintenance` at `01:52:10Z`; the watchdog remains healthy.
Retain and immediately reuse this bench for the same compatible hybrid repair
rather than drain it. Exact director-owned provider resources are instance
`computeinstance-e00vyqp7gxsr34wrtz` and disk
`computedisk-e00dryj6tbensjs413`.

**Bottleneck and evidence.** The admitted hybrid run reused the warm H200 at
`01:48:47Z`, loaded the exact model's 59.61 GiB of weights in 20.08 seconds,
and then failed before science because
`sglang.srt.speculative.ngram_worker` in the pinned resident runtime does not
export the staged `NGramWorker` symbol. `science_started=false`, so this is an
ordinary mutable import/API integration defect, not evidence about the
dual-cache mechanism. Nevertheless the project-local owner encoded
`pool("release", "maintenance")` directly on its preload/server-health
failure branch. It released after roughly 203 seconds of claim exposure,
forcing another scheduler handoff and likely another model load instead of
patching the import against resident bytes and rerunning under the same claim.
The prior two-minute warm handoff and preserved image/checkpoint caches show
that provider teardown is not the problem; premature claim release is.

**Change and expected effect.** Tightened the researcher skill's durable-owner
contract to close the conditional-branch loophole. Recoverable pre-science
source-copy, process-start, preload-hook, runtime import/API, and server-health
failures must now funnel through one retained-claim disposition that persists
the diagnostic, exposes the repair handshake, and keeps heartbeats active. If
a replacement owner is required, the boundary owner exits only after the
hash-bound repair request and leaves the claim live. This is an execution
default, not another validation gate: future localized runtime mismatches
should be patched on the mutable bench without a director/reclaim cycle,
repeated weight load, cold restart, or new scientific project.

## 2026-07-26T02:11Z — version sequential retained-claim repairs

**GPU safety audit.** One grouped authenticated Nebius listing returned
RUNNING instance `computeinstance-e00vyqp7gxsr34wrtz` and READY boot disk
`computedisk-e00dryj6tbensjs413`, exactly matching the sole non-retired
inventory bench `h200-dflash-adapter-e00vyqp7gxsr34wrtz`; no provider or
inventory resource is unmatched. The controller-host user watchdog
`gemma4-hybrid-ngram-20260726t0225-watchdog.service` is active/running at PID
`1443837` in its recorded control group through `02:25Z`. The hybrid claim has
remained continuous since `01:58:40Z` and heartbeated at `02:08:14Z`, with no
stale claim or passed deadline. The bench is actively serving a compatible
same-project repair, so neither drain nor idle-cost action is warranted.

**Bottleneck and evidence.** The first retained repair correctly persisted
`REPAIR_READY.json` at `02:03:29Z`, received its hash-bound
`REPAIR_REQUEST.json` at `02:05:14Z`, and transferred the still-live claim to
replacement PID `1458909`. That replacement loaded the 59.61 GiB model in
9.31 seconds and localized a second pre-science defect: the adapter installs
inside `ModelRunner.load_model` before the production token/KV allocator
exists. It correctly retained the claim, but reused repair ID
`ngram-readmission-20260726t0159z`. Because that ID already had a completed
ready/request pair, `repair-handshake ready` returned
`repair_request_already_exists`; the old handshake could not represent or wake
the harness for the new diagnostic. The active researcher recovered by
reading the dead PID and controller state directly and is patching lazy
consumer-time binding, but the collision added avoidable coordination delay.
No scientific component or endpoint was consumed.

**Change and expected effect.** Amended the researcher skill so every
sequential repair under one continuous claim uses a fresh `repair_id`
generation and records its predecessor while preserving the original claim
timestamp, scientific contract, artifact lineage, and deadline. Completed
ready/request directories may not be reused. This lets the existing shared
handshake atomically expose each new runtime defect and wake the next repair
turn immediately, while preserving the successful in-place patch-and-rerun
behavior and avoiding static gates, claim release, repeated cold setup, or a
new scientific project.

## 2026-07-26T02:39Z — fail fast when the readiness child has already exited

**GPU safety audit.** One grouped authenticated Nebius listing returned
RUNNING instance `computeinstance-e00vyqp7gxsr34wrtz` and READY disk
`computedisk-e00dryj6tbensjs413`, exactly matching sole non-retired bench
`h200-dflash-adapter-e00vyqp7gxsr34wrtz`. The claim has remained continuous
since `02:23:33Z` and heartbeated at `02:37:52Z`; the recorded controller-host
user watchdog
`gemma4-hybrid-component-readmission-20260726t0315-watchdog.service` is
active/running at PID `1469591` in its exact control group through `03:15Z`.
There is no stale claim, passed deadline, provider mismatch, or idle-cost
action.

**Bottleneck and evidence.** The repaired cached server reached the real
production consumer at `02:28:49Z` and failed pre-science on a pinned-runtime
ABI difference: `NgramVerifyInput` exports `prepare_for_v2_verify`, not the
staged `prepare_for_verify`. The server log immediately recorded the fatal
traceback and process shutdown, but detached controller PID `1474490` remained
the durable owner until `02:38:22Z`, when it finally emitted
`REPAIR_READY.json`. The claim therefore spent about 9.5 minutes waiting on an
HTTP-readiness deadline after the launched child was already dead. The
component and endpoint remain unconsumed, and the harness correctly started a
replacement researcher seven seconds after the repair became visible.

**Change and expected effect.** Added one dynamic readiness rule to the
researcher contract: readiness deadlines are upper bounds, and a claimed
controller must concurrently observe its launched server/container/PID,
persist a fatal child exit or traceback immediately, and enter retained repair
without waiting out the HTTP deadline. This adds no static validation and does
not change the scientific portfolio. Future localized runtime/API failures
should reach the existing repair handoff minutes earlier while preserving the
same claim, caches, scientific contract, and absolute deadline.

**Follow-up handoff evidence.** The replacement researcher started at
`02:38:29Z` and its grouped snapshot correctly returned `live:false` plus
controller phase `repair_ready`, but an unrelated local inventory lookup used
the benches object as a list and raised `KeyError: 0`. Despite the completed
liveness evidence, the turn then incorrectly reported that the controller
remained live and returned no progress. The harness did wake the director on
that no-progress terminal. The same skill rule now makes `live:false` or a
PID/start-time mismatch authoritative across partial grouped-command failure
and forbids a live/no-progress report until the failed local read is narrowly
reconciled. This should prevent a dead repair owner from being falsely deferred
for another scheduler cycle.

## 2026-07-26T03:08Z — do not schedule a restart that cannot fit its window

**GPU safety audit.** One grouped authenticated Nebius listing returned
RUNNING instance `computeinstance-e00vyqp7gxsr34wrtz` and READY disk
`computedisk-e00dryj6tbensjs413`, exactly matching sole non-retired bench
`h200-dflash-adapter-e00vyqp7gxsr34wrtz`; no provider or inventory resource is
unmatched. The controller-host user watchdog
`gemma4-hybrid-component-readmission-20260726t0315-watchdog.service` is
active/running at recorded PID `1469591` in its exact control group through
`03:15Z`. The prior detached owner is dead and the claim last heartbeated at
`02:58:31Z`, but the replacement researcher started at `03:04:35Z` and is
actively executing the director-bound release-to-maintenance path before the
`03:10Z` release boundary. Do not drain during that live handoff; exact
director-owned provider resources remain the instance and disk IDs above.
The researcher completed that handoff at `03:08:19Z`: inventory now records
the bench unclaimed in `maintenance`, before both the release and lifecycle
deadlines.

**Bottleneck and evidence.** The cached v2-verify replacement ran from
`02:48:00Z` until its pre-science repair handoff at `02:59:00Z`, spending
about eleven minutes to reach the next pinned-runtime consumer mismatch. The
director started at `03:00:16Z`, took `258.598` seconds, and finished at
`03:04:35Z` by authorizing another cached restart with an unchanged
`03:05Z` execution deadline. The harness dispatched the researcher
immediately, but fewer than 25 seconds remained. Its trace correctly concluded
that a full cached restart could not finish and chose evidence reconciliation
plus release instead. Thus the late repair binding could not produce Gemma
component evidence; it consumed a researcher turn only to rediscover an
already elapsed execution window.

**Change and expected effect.** Amended the director skill so a same-claim
restart is runnable only when the remaining execution/release window exceeds
the closest measured same-lineage setup duration plus terminal and safe-release
margin. If it cannot fit, the director must bind offline repair plus
release/maintenance, or safely extend and verify lifecycle first when authority
and spend permit. This is a commit-time decision from observed timings rather
than more static validation. It should prevent impossible late GPU handoffs,
preserve cleanup margin, and make the next paid window start with an executable
repair instead of another deadline-reconciliation turn.

## 2026-07-26T03:27Z — retain a feasible pre-science repair instead of tearing down

**GPU safety audit.** One grouped authenticated Nebius listing returned only
RUNNING instance `computeinstance-e00vyqp7gxsr34wrtz` and READY disk
`computedisk-e00dryj6tbensjs413`, exactly matching sole non-retired bench
`h200-dflash-adapter-e00vyqp7gxsr34wrtz`; no provider or inventory resource is
unmatched. The controller-host user watchdog
`gemma4-hybrid-source-proven-readmission-20260726t0400-watchdog.service` is
active/running at recorded PID `1497490` in its exact control group through
`04:00Z`. The bench is unclaimed in `maintenance` after an orderly release at
`03:24:14Z`; no claim is stale and no lifecycle deadline has passed. The
director is already reconciling this fresh terminal, so do not mark the bench
draining. Its retained checkpoint, image, and build caches remain compatible
with the still-unconsumed same-project component.

**Bottleneck and evidence.** The source-proven claim ran from `03:19:16Z` to
`03:24:14Z` (about 298 seconds) and heartbeated through `03:24:07Z`. The exact
model loaded, CUDA graphs completed, and the adapter/ForwardBatch hook attached,
but the readiness `/health` generation entered
`NGRAMWorker.forward_batch_generation` with `batch.seq_lens_cpu=None` and
raised `TypeError` at the pinned worker's speculative-preparation path. SGLang
then SIGQUIT the server before candidate CUDA or the component invocation.
This is the third post-load pre-science integration failure; cumulative project
exposure is `$4.56` and the component remains wholly unconsumed. The itinerary's
one-server/no-further-repair clause caused the researcher to remove the
container and release immediately even though the guest and retained caches
were safe and the `03:55Z` release window had more than 30 minutes remaining.

**Change and expected effect.** Tightened the director contract so one-server
or no-further-integration-repair limits cannot force release after a recoverable
pre-science crash. Scientific submission/sample limits remain intact, while a
mutable discovery claim must retain one feasible material correction and cached
replacement; maintenance is reserved for unsafe/unreachable guests, absolute
deadlines, or a restart that cannot fit the measured setup plus terminal/release
margin. This removes a restrictive handoff rather than adding validation. The
next localized launch defect should be patched and rerun under the same claim,
avoiding another director round trip, warm-bench gap, and paid model reload
when resident process state can be preserved.

**Follow-up.** The concurrent director reconciliation retained the bench,
extended its lifecycle to `04:15Z`, installed the controller-host user
watchdog `gemma4-hybrid-seqlens-repair-20260726t0415-watchdog.service`
(active/running at recorded PID `1507484` in the exact control group), and
marked it unclaimed/available at `03:28:13Z` for the localized repair. This
confirms reuse rather than drain; the director still owns the repair admission
and eventual provider disposition.

## 2026-07-26T03:40Z — wait for post-graph readiness before scientific submission

**GPU safety audit.** One grouped authenticated Nebius listing returned only
RUNNING instance `computeinstance-e00vyqp7gxsr34wrtz` and READY disk
`computedisk-e00dryj6tbensjs413`, exactly matching sole non-retired bench
`h200-dflash-adapter-e00vyqp7gxsr34wrtz`; no provider or inventory resource is
unmatched. The controller-host user watchdog
`gemma4-hybrid-seqlens-repair-20260726t0415-watchdog.service` is
active/running at recorded PID `1507484` in its exact control group through
`04:15Z`. The bench is unclaimed/available since `03:34:17Z`; no claim is
stale and no deadline has passed. Retain it for the still-unconsumed compatible
same-project repair rather than drain: four minutes of idle exposure is about
`$0.16`, below the repeated paid model-load and director-reconciliation cost.

**Bottleneck and evidence.** The seq-lens repair claim lasted from
`03:31:41Z` to `03:34:17Z` (about 156 seconds) and increased cumulative
project exposure from `$4.56` to `$4.67`. The controller accepted adapter
attachment plus a live container as request readiness at `03:34:05Z`, while
the raw server log shows CUDA-graph capture began at `03:34:06Z`. It then
submitted all 32 local c32 requests; every connection was refused before
NGRAM or candidate CUDA entry. The typed terminal correctly records no
scientific sample, but the live owner state had already asserted
`science_started=true` and `candidate_cuda_invocation_started=true`. The
component therefore remains wholly unconsumed; this attempt measured a
readiness race, not the Gemma hybrid-placement intervention.

**Change and expected effect.** Replaced that predicate in
`ngram_readmission_controller.py` with the runtime's own dynamic post-graph
`The server is fired up and ready to roll!` marker plus an explicitly tagged
live-container check. The controller no longer calls the unsafe generation
health endpoint, and it keeps owner science/CUDA fields false before invoking
the component. Added three focused tests covering graph-capture rejection,
post-graph acceptance, and stopped-container rejection. The tests, Python
compile, repository DevEx check, and diff check pass. This is not another
static validation stage: it prevents the one allowed request from racing the
server port, removing an avoidable reload/director cycle and making the next
claim reach model-scoped evidence.

## 2026-07-26T03:53Z — preserve the request-submission science boundary

**GPU safety audit.** One grouped authenticated Nebius listing returned only
RUNNING instance `computeinstance-e00vyqp7gxsr34wrtz` and READY disk
`computedisk-e00dryj6tbensjs413`, exactly matching sole non-retired bench
`h200-dflash-adapter-e00vyqp7gxsr34wrtz`; no provider or inventory resource is
unmatched. The controller-host user watchdog
`gemma4-hybrid-seqlens-repair-20260726t0415-watchdog.service` is
active/running at recorded PID `1507484` in its exact control group through
`04:15Z`. The bench is unclaimed/available since `03:48:36Z`; no claim is
stale and no deadline has passed. Retain it briefly for director disposition:
the compatible same-project state is fresh, the prior cold model-load cycle is
material, and idle exposure was only about two minutes at audit time. Exact
director-owned provider resources remain the instance and disk IDs above.

**Bottleneck and evidence.** The readiness-gated claim ran from `03:44:32Z`
to `03:48:36Z` (about 244 seconds), adding `$0.17` and bringing conservative
project exposure to `$4.84`. CUDA graphs completed at `03:46:07Z`, the server
declared readiness at `03:46:15Z`, and the component submitted all 32 c32
requests. The installed repair then materialized `seq_lens_cpu` for nine rows
inside the NGRAM runtime, after which the request manager timed out and all 32
requests returned HTTP 500 without a response or comparator result. Thus the
attempt produced no interpretable component sample, but it did cross the
durable scientific request-submission boundary. The harness and typed terminal
incorrectly recorded `science_started=false` merely because `complete=0`,
contradicting the researcher contract and masking a bounded failed scientific
invocation as another pre-science integration failure.

**Change and expected effect.** Updated
`forward_batch_activation_component.py` to persist a separate pre-science
`PREPARED.json`, set `science_started=true` immediately before the request
pool submission in `INVOCATION.json`, and preserve that fact independently of
response success in `TERMINAL.json`. Candidate-CUDA and usable-response fields
remain conservative, and the historical failed terminal is left untouched.
This prevents runtime-entering failures from receiving an effectively
unlimited pre-science retry allowance, while still allowing the director to
treat a no-response attempt as invalid rather than positive or negative model
evidence. It should focus the next disposition on the actual implementation
failure or a higher-value route instead of another accounting-reset cycle.

## 2026-07-26T04:08Z — retain the claim across a typed consumer repair

**GPU safety audit.** One grouped authenticated Nebius listing returned only
RUNNING instance `computeinstance-e00vyqp7gxsr34wrtz` and READY disk
`computedisk-e00dryj6tbensjs413`, exactly matching sole non-retired bench
`h200-dflash-adapter-e00vyqp7gxsr34wrtz`; no provider or inventory resource is
unmatched. The controller-host user watchdog
`gemma4-hybrid-seqlens-repair-20260726t0430-watchdog.service` is
active/running at recorded PID `1522791` in its exact control group through
`04:30Z`. The latest claim released ready at `04:03:28Z`, with no stale claim
or passed deadline. Retain the available bench for director disposition: at
audit it had been idle for about three minutes, and its checkpoint, image, and
build caches remain compatible with the just-localized consumer boundary.
Exact director-owned provider resources remain the instance and disk IDs
above; no drain or provider cleanup is warranted.

**Bottleneck and evidence.** The tensor-correction claim ran from
`04:00:53Z` to `04:03:28Z` (about 155 seconds), adding `$0.13` and bringing
conservative project exposure to `$4.97`. The exact CPU-tensor contract and
all four readiness gates passed, but the component stopped before
TARGET_VERIFY on `RuntimeError: proxy allocator did not return a distinct
logical slot vector`. This is another narrow consumer-integration boundary,
not hybrid-placement evidence. Despite a healthy guest, 20-plus minutes of
lifecycle protection, and a compatible patchable state, the controller
unconditionally removed the container and released the claim after every
component return. Its existing `repair()` path also published
`REPAIR_READY.json` and immediately exited, stopping heartbeats instead of
waiting for the hash-bound repair request.

**Change and expected effect.** Changed
`ngram_readmission_controller.py` so a failed component enters the existing
repair handshake with `science_started=true`, keeps the outer owner and claim
heartbeating while `repair-handshake wait` blocks, and exits with the lease
live only after a hash-bound request identifies the replacement owner.
Handshake failure or the absolute repair deadline still removes the container
and releases safely; successful component terminals retain their prior cleanup
path. This does not authorize the allocator repair or another scientific
submission. It removes the measured release/director/reclaim gap from any
director-admitted continuation and preserves mutable guest, image, checkpoint,
and build-cache state instead of forcing another cold setup cycle.

## 2026-07-26T04:33Z — empty token vectors are missing evidence, not exactness

**GPU safety audit.** One grouped authenticated Nebius listing returned only
RUNNING instance `computeinstance-e00vyqp7gxsr34wrtz` and READY disk
`computedisk-e00dryj6tbensjs413`, exactly matching sole non-retired bench
`h200-dflash-adapter-e00vyqp7gxsr34wrtz`; no provider or inventory resource is
unmatched. The controller-host user watchdog
`gemma4-c32-graph-gap-20260726t0520-watchdog.service` is active/running at
recorded PID `1531696` in its exact control group through `05:20Z`. The graph
claim ran from `04:25:58Z` to `04:30:47Z`, heartbeated throughout, released
ready, and cost `$0.196882`; no claim is stale and no deadline has passed.
Retain the warm available bench briefly for the active director's compatible
successor decision rather than drain or cold-restart it.

**Bottleneck and evidence.** The matched exact-c32 pair completed 32/32
requests per arm with valid request hashes, usage/cache accounting, and clean
shutdowns; candidate service time was `0.613578 s/request`, `0.769%` below
control. The terminal correctly rejected because 17 projected internal
emitted-token traces on each side were unmatched. However,
`sse_token_ids_exact=true` was vacuous: all 32 control and all 32 candidate SSE
token-ID vectors were empty, and the endpoint driver defined equality as only
length 32 plus list equality. Treating this as positive semantic evidence
could obscure the valid internal mismatch or support a false promotion.

**Change and expected effect.** Tightened `$research-supervisor` so equality
over empty or unavailable token vectors is always missing observation, not
exactness; token-exact claims now require nonempty response-level vectors or an
independent semantic oracle. The completed terminal and scientific portfolio
remain unchanged. This should prevent vacuous observer fields from distorting
future close decisions while preserving genuine internal-trace failures as
separate evidence.

## 2026-07-26T04:52Z — recognize the shared tool's namespaced repair handshake

**GPU safety audit.** One grouped authenticated Nebius listing returned only
RUNNING instance `computeinstance-e00vyqp7gxsr34wrtz` and READY disk
`computedisk-e00dryj6tbensjs413`, exactly matching sole non-retired bench
`h200-dflash-adapter-e00vyqp7gxsr34wrtz`; there are no provider-only or
inventory-only resources. The recorded controller-host user watchdog
`gemma4-c32-graph-gap-20260726t0520-watchdog.service` is active/running at PID
`1531696` in its exact control group through `05:20Z`. The bench is legitimately
claimed by `gemma4_h200_fp8_weight_stream_schedule`: claim heartbeats remained
fresh through `04:51:13Z`, the PID-managed owner
`artifacts/owner/sm90a_reactivated_20260726t044112z.owner.json` is live at PID
`1553056`, and its `05:12Z` repair deadline has not passed. This is compatible
queued work on resident state, so reuse is justified; do not drain. Exact
director-owned provider resources remain the instance and disk IDs above.

**Bottleneck and evidence.** The claimed component stopped before candidate
CUDA on a recoverable `torch.utils.cpp_extension`/Ninja build failure at
`04:41:47Z`. The durable owner correctly retained the claim and published
`artifacts/sm90a-component-20260726t044127z/repair/.repair-handshakes/sm90a-sm90a-component-20260726t044127z/REPAIR_READY.json`,
but no matching `REPAIR_REQUEST.json` existed at `04:51:47Z`. During those ten
minutes the GPU claim heartbeated every roughly 45 seconds while the harness
repeatedly emitted `researcher_deferred` with `durable_session_active` from
`04:44:17Z` through `04:51:20Z`. The scheduler's pending-repair detector checked
only flat `REPAIR_READY.json` files at the active artifact root and project
root, while the shared `repair-handshake` tool intentionally writes
repair-ID-scoped markers under `.repair-handshakes/<repair-id>/`. The process
bottleneck is therefore a path-contract mismatch that suppresses the exact
researcher needed for in-place repair, not a lack of projects, direction, or
GPU capacity.

**Change and expected effect.** Changed the lab harness's pending-repair
discovery to recognize both flat markers and bounded shared-tool layouts at
`.repair-handshakes/<id>/` and `<child>/.repair-handshakes/<id>/`; it now binds
the request and prompt to the exact handshake directory and still rejects
expired, terminal, artifact-mismatched, or already hash-bound requests. Added a
focused namespaced-handshake regression; all 64 harness tests pass. The running
harness correctly deferred its source reload rather than disrupting the live
PID owner, so this change does not mutate the active experiment. After the safe
reload boundary it will wake a researcher for the existing typed repair state,
letting that researcher patch and submit the hash-bound request while the owner,
claim, guest, and caches stay resident. This removes the observed warm-GPU
coordination idle and prevents the same recoverable integration failure from
ending in deadline expiry and cold restart.

## 2026-07-26T06:06Z — preserve economic evidence across numerical kernel reorders

**GPU safety audit.** One grouped authenticated Nebius listing returned only
RUNNING instance `computeinstance-e00vyqp7gxsr34wrtz` and READY disk
`computedisk-e00dryj6tbensjs413`, exactly matching sole non-retired bench
`h200-dflash-adapter-e00vyqp7gxsr34wrtz`; no provider-only or inventory-only
resource exists. The controller-host user watchdog
`gemma4-weightstream-20260726t0730-watchdog.service` is active/running at its
recorded PID `1582718` and exact control group through `07:30Z`. The retained
claim ran from `05:49:16Z` to `05:58:51Z`, heartbeated throughout, and released
ready with no owner or worker remaining. At audit the bench had been idle for
about four minutes while the replacement director was actively running, so
its `$2.45/hour` idle cost remains justified by compatible warm-state reuse;
no drain or lifecycle mutation is warranted.

**Bottleneck and evidence.** The persistent Stream-K arm recovered two
pre-CUDA source-integration defects inside that single claim, compiled a fresh
SM90a module, and reached the exact M32 consumer. Gate/up BF16, GELU product,
down-input FP8, and down scale were finite and bitwise equal; only the final
BF16 result differed after the arm deliberately changed the down-projection
reduction order (`max |delta| 0.00225830078125`, relative L2
`0.1942131668329239`). The project's bitwise stop then consumed the arm before
any timing, graph test, or M384 run. This is valid evidence against that
project's exact-output admission rule, but it leaves the mechanism's speed and
economic value entirely unobserved. `CAMPAIGN.md` does not require bitwise
kernel output: it permits plausibly quality-preserving kernel changes, cheap
numerical sanity during exploration, and later task-quality validation for
performance survivors. A bitwise-only pre-timing gate can therefore reject
normal floating-point accumulation reorders before the campaign learns
whether quality investigation is worth buying.

**Change and expected effect.** Tightened `$research-director` so future
floating-point reduction/reordering candidates use an A/A envelope or justified
numerical tolerance, localize finite deltas, and—when cheap in the same bounded
invocation—persist timing before a close decision. Nonfinite, structural, or
gross preregistered failures may still stop immediately, and the consumed
Stream-K arm remains closed and unreplayed. This should prevent future kernel
schedules from becoming economically uninterpretable on bitwise variance
alone while keeping quality-unsafe candidates out of endpoint promotion until
they earn the campaign's semantic gates.

## 2026-07-26T06:13Z — make near-term GPU admissions directly launchable

**GPU safety audit.** One grouped authenticated Nebius listing returned only
RUNNING instance `computeinstance-e00vyqp7gxsr34wrtz` and READY disk
`computedisk-e00dryj6tbensjs413`, exactly matching sole non-retired bench
`h200-dflash-adapter-e00vyqp7gxsr34wrtz`; no provider or inventory resource is
unmatched. The recorded controller-host user watchdog
`gemma4-weightstream-20260726t0730-watchdog.service` is active/running at PID
`1582718` in its exact control group through `07:30Z`. The prior claim released
ready at `05:58:51Z`; no stale claim, owner, or passed deadline exists. At
audit the bench had been idle for about twelve minutes, costing about `$0.49`,
but the director had just admitted a compatible full-model H200 component and
an independent GPU-free oracle. Retention remains cheaper than the measured
cold model/build setup and preserves the imminent claim, so no drain or
provider mutation is warranted.

**Bottleneck and evidence.** The replacement director took `630.244` seconds
and activated `gemma4_hybrid_attention_placement_codesign` at `06:09:37Z` with
a `06:15Z` claim gate. Its binding
`DIRECTOR_CORRECTED_ALLOCATOR_H200_COMPONENT_20260726T0604Z.json` specifies the
scientific arm, exact bench, spend, and terminal/release bounds, but contains
no launcher, runner, entrypoint, or command. The execution researcher therefore
spent the first minutes of a roughly five-minute remaining admission window
searching historical files, reading six old owner implementations plus six
component/adapter files, and rerunning an already-settled allocator unit test;
the H200 was still available with a null claim at `06:11:54Z`. This is not
scientific work or necessary mutable checking. The missing executable handoff
turns a source-complete, time-gated project back into orientation and risks
losing the warm window before the first GPU action.

**Change and expected effect.** Tightened `$research-director` so every
near-term provider admission must name the exact project-relative launcher or
owner entrypoint and its single start command/helper. When no existing
entrypoint fits, the director must bind the smallest in-project launcher
mutation without starting the claim clock; no separate readiness project is
introduced. The active hybrid project, researcher, bench, and deadlines were
left untouched. Future execution researchers should move from the durable
binding to an atomic claim without rediscovering historical controllers,
reducing paid warm idle and preserving more of each bounded claim for
decision-bearing GPU execution and same-claim repair.

## 2026-07-26T06:21Z — make recoverable controller disposition structural

**GPU safety audit.** One grouped authenticated Nebius listing returned only
RUNNING instance `computeinstance-e00vyqp7gxsr34wrtz` and READY disk
`computedisk-e00dryj6tbensjs413`, exactly matching sole non-retired bench
`h200-dflash-adapter-e00vyqp7gxsr34wrtz`; no provider or inventory resource is
unmatched. The recorded controller-host user watchdog
`gemma4-weightstream-20260726t0730-watchdog.service` is active/running at PID
`1582718` in its exact control group through `07:30Z`. The hybrid project
released at `06:17:57Z`, before its claim and lifecycle deadlines, and the
bench is `available` with no claim or owner. Its roughly three minutes of idle
time at `$2.45/hour` is not yet a drain case: the director is actively
processing the just-produced H200 repair result, and the image, checkpoint,
compiler, and CUDA caches remain compatible with that route. No inventory,
drain, or provider mutation was made.

**Bottleneck and evidence.** The campaign frontier remains the
quality-qualified `0.625149101968745 s/request`, versus the
`0.500119281574996 s/request` objective. The direct hybrid lane spent two
claims (`06:11:35–06:12:17Z` and `06:14:42–06:17:57Z`) without a timing or
interpretable component result. The first claim invoked a stale controller and
released after 42 seconds; the second rebuilt the execution path and loaded the
model, then failed in the mutable candidate source at
`forward_batch_dual_cache_driver.py:192` with `RuntimeError: proxy allocator
exhausted before logical-slot allocation`. Its terminal records
`scientific_component_consumed:false` and
`candidate_cuda_invocation_started:false`. Despite that recoverable,
unconsumed integration failure, `corrected_allocator_component_owner.py`
routed every outcome through one `finish` helper that ran
`docker rm -f phase-selective-readmission` and `gpu_pool release`. This
ended the continuous claim after the allocator exception had crashed the
server, rather than patching the source and doing the necessary process-only
restart against the same resident checkpoint and caches. The independent DFlash depth oracle
completed GPU-free and found no project-local route whose scope-matched
ceiling beats the current frontier, so adding projects or more static
validation would not address the current objective bottleneck.

**Change and expected effect.** Tightened `$researcher` so newly authored bench
owners must separate retained-repair and terminal cleanup/release control
paths. A generic failure-capable `finish` helper may not stop the runtime or
release; unconsumed or unclassified outcomes default to retention, while
cleanup-and-release requires explicit decision-bearing evidence,
unsafe/unreachable state, or the absolute deadline. This converts the existing
warm-repair policy into a controller construction rule and should preserve the
claim and resident caches across the next localized consumer or allocator bug,
preserve the model load when the server remains healthy, and keep a necessary
process-only restart inside the same spend interval when the server has
crashed.

## 2026-07-26T06:40Z — stop serializing the repaired arm behind command seams

**GPU safety audit.** One grouped authenticated Nebius listing returned only
RUNNING instance `computeinstance-e00vyqp7gxsr34wrtz` and READY disk
`computedisk-e00dryj6tbensjs413`, exactly matching sole non-retired bench
`h200-dflash-adapter-e00vyqp7gxsr34wrtz`; no provider or inventory resource is
unmatched. The controller-host user watchdog
`gemma4-weightstream-20260726t0730-watchdog.service` is active/running at PID
`1582718` in its exact control group through `07:30Z`. The bench is
`available`, unclaimed, and ownerless by design, with no passed deadline or
unsafe state. At audit it had been idle since `06:17:57Z`, about 21 minutes or
`$0.85`, but its checkpoint, image, compiler, and CUDA caches remain directly
compatible with the active hybrid lane. Recommend immediate reuse rather than
drain; no inventory or provider mutation was made.

**Bottleneck and evidence.** The campaign still needs to move the
quality-qualified `0.625149101968745 s/request` frontier toward
`0.500119281574996 s/request`. The allocator repair terminal became durable at
`06:33:30Z` and advertised
`target_only_proxy_allocator_component_owner.py` plus the exact start command,
but that owner contains no scientific runner: it requires an unbound
`component_command`. Both discoverable existing component commands contain the
cleanup/release defect that prompted the repair. The director therefore spent
more than five minutes rereading historical controllers and, at `06:37:18Z`,
opened a new 20-minute CPU-only
`DIRECTOR_TARGET_ONLY_COMPONENT_COMMAND_SEAM_20260726T0637Z.json` iteration
with no GPU claim or provider contact. This is another support project after an
offline repair was already declared ready, not progress toward a timing or
component result. It prolongs warm idle and repeats the explicit failure mode
of answering a recoverable integration defect with more static validation and
projects.

**Change and expected effect.** Tightened `$research-director` so a
disposition-tested owner with an unbound `component_command` is not considered
runnable unless the same terminal hash-binds a lifecycle-pure runner through
the scientific consumer. After one offline repair terminal, the director may
not open another CPU-only command-seam, owner-composition, or synthetic
transport iteration for the same unconsumed arm; a remaining localized seam
must be implemented on the mutable retained claim and continued into the real
component when the measured window is safe. The active scientific contract,
bench, watchdog, and provider resources were left untouched. This should turn
the next wake into one same-project claim/patch/measure path, eliminating
another offline handoff and converting the warm window into decision-bearing
GPU evidence.

## 2026-07-26T07:03Z — keep retained repair reusable after runtime death

**GPU safety audit.** One grouped authenticated Nebius listing returned only
RUNNING instance `computeinstance-e00vyqp7gxsr34wrtz` and READY disk
`computedisk-e00dryj6tbensjs413`, exactly matching sole non-retired bench
`h200-dflash-adapter-e00vyqp7gxsr34wrtz`; no provider or inventory resource is
unmatched. The controller-host user watchdog
`gemma4-weightstream-20260726t0730-watchdog.service` is active/running at PID
`1582718` in its exact control group through `07:30Z`. The bench is claimed by
the hybrid project, heartbeating through `07:01:51Z`; detached owner PID
`1631873` is live with matching start ticks and a `07:24Z` project deadline.
There is no stale claim, owner loss, unsafe state, or drain condition.

**Bottleneck and evidence.** The first retained-claim repair worked as
intended: the researcher patched the live producer/retrieval join, signalled
the same owner, and brought the single resident target server ready at
`06:59:20Z` without releasing the H200. TARGET_VERIFY then returned HTTP 500
for all 32 requests after roughly 20.5 seconds each; the persisted terminal
records zero completions, no candidate CUDA start, and no consumed scientific
component, while the server trace shows request-manager timeout followed by
SGLang SIGQUIT process-tree termination. The owner correctly retained the
claim, but `STATUS.json` states that it has no repair-time replacement action
after this second recoverable outcome. The execution researcher therefore
finished with a live owner and paid claimed bench but no server and no way to
submit another repair request, turning retention into idle exposure instead of
a mutable measurement session.

**Change and expected effect.** Tightened `$research-director` so a retained
discovery repair handshake cannot be single-use: after every recoverable,
non-decision-bearing result it may accept another hash-bound correction and
cached process/container replacement while the arm remains unconsumed and the
measured restart plus terminal/release margin fits. The active owner, claim,
scientific contract, and provider lifecycle were not modified. Future owners
should keep source repair and bounded runtime replacement iterative within one
claim, avoiding a new project, cold allocation, or paid idle owner whenever a
replacement server itself dies before interpretable GPU evidence.

## 2026-07-26T07:40Z — keep launcher parse repair inside the warm claim

**GPU safety audit.** One grouped authenticated Nebius listing returned only
RUNNING instance `computeinstance-e00vpenjwp83n0nxmr` and READY disk
`computedisk-e00zn7md79crad33jd`, matching sole non-retired bench
`h100-paged-fp8-e00vpenjwp83n0nxmr`. Its controller-host user watchdog
`gemma4-h100-paged-fp8-20260726t0814-watchdog.service` was active/running at
PID `1642730` in the recorded control group through `08:14:14Z`. At
`07:37:54Z` the bench was unclaimed in `maintenance`: the recorded owner PID
`1652746` had exited after an explicit release at `07:37:32Z`, not from
watchdog loss or an unsafe guest. The compatible pinned image was resident,
the deadline had not passed, and the project still had repair time, so reuse
was preferable to drain. The researcher returned the safe bench to ready and
re-claimed the same resource at `07:39:11Z`. A second pre-science workdir
defect caused another maintenance release at `07:39:28Z`; the researcher
returned it to ready and re-claimed it again at `07:40:39Z`, with replacement
owner PID `1660223` live at matching start ticks. No provider restart or
cleanup occurred.

**Bottleneck and evidence.** The first-use image pull completed and verified
the exact digest, but Docker retained the image's `vllm` entrypoint. It parsed
`paged_fp8_execution.py run ...` as invalid CLI arguments and exited with
usage text before the Python scientific program, CUDA, or a request began.
`run_h100_controller.py` nevertheless wrote
`candidate_invocation_started_utc.txt` before `docker run`, failed to retrieve
the nonexistent terminal, and released the warm claim to maintenance. This
turned a localized pre-science command-prefix defect into an owner handoff and
release/reclaim cycle, while also making its marker overstate scientific
consumption. The first corrected owner then reached Python but inherited the
image's `/vllm-workspace` working directory, could not find the mounted script,
and repeated the same release/reclaim cycle before CUDA or science.

**Change and expected effect.** Tightened `$researcher` so shell-side
submission markers before Docker, SSH, or program startup are only
`launch_attempted`; scientific-start markers must be written by the bound
program after runtime/identity validation and immediately before its first
request or kernel. Container entrypoint, command-prefix, argument-parsing,
permission, and executable-path failures now explicitly remain same-owner,
same-claim launcher repairs. This should preserve warm images and continuous
spend accounting, prevent false arm-consumption labels, and turn the next
localized invocation defect directly into a corrected run rather than a
maintenance release or cold restart.

## 2026-07-26T07:47Z — keep runtime adapters mutable inside scientific bindings

**GPU safety audit.** One grouped authenticated Nebius listing returned only
RUNNING instance `computeinstance-e00vpenjwp83n0nxmr` and READY disk
`computedisk-e00zn7md79crad33jd`, matching sole non-retired bench
`h100-paged-fp8-e00vpenjwp83n0nxmr`. Its controller-host user watchdog
`gemma4-h100-paged-fp8-20260726t0814-watchdog.service` is active/running at
PID `1642730` in the recorded control group through `08:14:14Z`. At
`07:45:50Z` the bench was unclaimed in `maintenance`; all four prior
controller-local owner PIDs were gone after explicit releases, the deadline
had not passed, and the guest was not unsafe. The exact image is resident and
the director is actively evaluating a same-project repair, so recommend reuse
rather than drain. No inventory or provider mutation was made.

**Bottleneck and evidence.** Attempt 4 finally entered the exact pinned Python
program after three pre-science launcher failures. It then stopped before CUDA
or pair timing because pinned vLLM now Pydantic-validates
`VllmConfig(model_config=None)`. The typed terminal is
`integration_error` with `scientific_sample_consumed:false`; source identity,
image, workload, component geometry, oracle, and timing contract remain
unchanged. Nevertheless the director admission's blanket prohibition on a
source repair/readiness successor caused the researcher to classify this
localized constructor/API mismatch as blocked and release to maintenance.
That made operational adapter source accidentally as immutable as the
scientific arm.

## 2026-07-26T08:01Z — make pre-science retention executable in the H100 controller

**GPU safety audit.** One grouped authenticated Nebius listing returned only
RUNNING instance `computeinstance-e00vpenjwp83n0nxmr` and READY disk
`computedisk-e00zn7md79crad33jd`, exactly matching sole non-retired bench
`h100-paged-fp8-e00vpenjwp83n0nxmr`; there was no provider-only resource or
missing live inventory resource. The controller-host user watchdog
`gemma4-h100-paged-fp8-20260726t0814-watchdog.service` was active/running at
PID `1642730` in its recorded control group through `08:14:14Z`. The owner PID
seen during the listing later exited normally after persisting a terminal and
releasing at `07:57:34Z`, so it was not a lost owner. At `08:00:05Z` the same
project reclaimed the exact bench for its next compatible repair; the
deadline has not passed and resident image/source state plus active queued
work justify reuse at `$2.95/hour`. No drain or provider/inventory cleanup is
warranted.

**Bottleneck and evidence.** The constructor amendment is correctly
localizing pinned-vLLM adapter requirements, but it still has no
decision-bearing GPU evidence. The latest terminals remain
`integration_error` with `scientific_sample_consumed:false`: successive
generations exposed read-only `head_dtype`/`use_mla` state, the required
tokenizer string, and then inherited `_architecture`, before registered
Attention or candidate CUDA. `runtime/gpu_events.jsonl` records claim/release
pairs at `07:52:40/07:53:09`, `07:53:34/07:55:08`, and
`07:56:07/07:57:34`; the following `07:59:13` attempt ran after that release
and before the next `08:00:05` claim. The direct cause is
`run_h100_controller.py` releasing unconditionally in `finally` whenever any
terminal exists, despite the terminal explicitly proving a recoverable
pre-science result. Thus written skill policy was not controlling runtime
disposition, and the mutable resident repair loop repeatedly crossed the pool
ownership boundary.

**Change and expected effect.** Changed this active project's controller
harness so an explicit `integration_error` with
`scientific_sample_consumed:false` retains the claim before the bound hard
deadline and writes `retained_claim.json`; decision-bearing terminals,
unreadable/missing terminals, and deadline expiry preserve the existing
release path. Pure disposition checks cover recoverable/future, expired, and
scientific-terminal cases, and Python compilation passes. The current
scientific program, source identities, workload, oracle, image, provider
lifecycle, and running researcher were not changed. The next adapter failure
should now leave the same pool claim available to the replacement owner,
eliminating release/reclaim churn and preventing another unclaimed warm-bench
execution while the researcher reaches the first scientific submission.

Commit-time reconciliation then exposed a second, independent ownership race:
the director inspected the `08:00:05` claim at `08:00:47`, a replacement
owner launched at `08:00:56`, and the director's delayed maintenance release
still succeeded at `08:01:00` because release checked only the project name.
The controller correctly wrote `retained_claim.json` after the resulting
`08:01:14` pre-science terminal, but ownership had already been removed. Added
an optional compare-and-release guard,
`gpu_pool release --expected-claimed-at`, which atomically rejects a stale
same-project claim generation; the director skill now requires it after an
inspection or handoff. All 13 GPU-pool tests pass, including a same-project
release/reclaim/release race.

The concurrent director selected offline adapter work and no compatible use
for the remaining paid window, then marked the now-empty registered bench
draining at `08:01:28`. Preserve that decision and give cleanup ownership the
exact resources: bench `h100-paged-fp8-e00vpenjwp83n0nxmr`, instance
`computeinstance-e00vpenjwp83n0nxmr`, and disk
`computedisk-e00zn7md79crad33jd`. No supervisor provider cleanup or inventory
retirement was performed. The compare-and-release guard should prevent future
director observations from racing a newer owner into unclaimed GPU execution
without serializing normal researcher release paths.

**Change and expected effect.** Tightened `$research-director` so paid bindings
must explicitly partition immutable scientific identities from mutable
launcher, runtime-constructor, API-adapter, path, and retrieval code. A
pre-science API mismatch may receive a narrow, hash-bound causal amendment in
the same project and warm bench while the checkpoint, workload, intervention,
oracle, timing boundary, and submission count remain frozen. This should let
the current director issue one direct constructor repair and measurement
without another readiness project, and prevent future immutable packets from
turning ordinary runtime drift into false scientific closure or cold setup.

## 2026-07-26T08:18Z — bind provider exposure to retirement and reserve before create

**GPU safety audit.** The single grouped authenticated Nebius snapshot taken
at the start of this audit returned zero instances and zero disks, matching
the empty non-retired inventory after verified cleanup of
`h100-paged-fp8-e00vpenjwp83n0nxmr`. A concurrent director turn subsequently
created provider-only instance `computeinstance-e00s5pkzna5fw6tars`, disk
`computedisk-e00zeakhrr60ddfcdx`, and public IP `89.169.112.171`; the
director's authenticated transaction records the instance RUNNING, while the
inventory remains empty pending strict SSH identity verification. Its
controller-host user watchdog
`gemma4-h100-paged-fp8-20260726t0907-watchdog.service` is active/running at
PID `1684262` in the recorded control group through
`2026-07-26T09:07:59.475265Z`. There is no registered claim, stale owner,
passed deadline, or registered bench to mark draining. The exact repaired
H100 component is compatible queued work, so reuse is economically relevant
only if spend is reconciled and the promised reservation becomes durable;
otherwise the director should drain/clean these exact provider resources
before the unreconciled exposure consumes the remaining authority. No
provider cleanup, inventory registration, or retirement was performed by the
supervisor.

**Bottleneck and evidence.** The scientific portfolio now has useful
model-specific work: the MI355X source-bound candidate analytically clears
`0.6000950932112802 s/request` only at its `$2.60/hour` planning point, the
B200 zero-spend screen is active against its
`0.315609255362861553 s/request` hurdle, and the H100 project completed its
pinned-vLLM consumer adapter offline with the BF16/E4M3 arm still
unconsumed. The limiting risk is no longer another readiness project; it is
whether the last remaining paid measurement can be executed without
breaching the campaign cap. The prior H100 lifecycle was registered from
`07:23:14.228256Z` until verified retirement at `08:02:57.116999Z`, an
inventory-residence estimate of `$1.952645` at `$2.95/hour`; the known
watchdog/provider lifecycle from approximately `07:15:05Z` through retirement
is about `$2.353540`. The harness nevertheless settled that reservation at
only `$1.00` at `08:10:09Z`. The new director binding then requested another
`$3.00` reservation and created the fresh resource, but
`runtime/spend_cap.json` still has no current
`h100_hybrid_attention_kernel_mechanism` reservation. Its claimed
`$3.068805` available balance therefore depends on the likely
`$0.95–$1.35` prior undercount. The director must reconcile the old lifecycle
and new resource before registration, claim, or another paid invocation; a
pending harness reservation is not authority.

`runtime/gpu_events.jsonl` also shows why this matters for research cadence:
the retired H100 paid for repeated claim/release and adapter setup cycles
without one interpretable scientific sample. The offline adapter repair is a
sound recovery, but a cold replacement is useful only if it reaches the exact
consumer inside the remaining reconciled spend and deadline. Opening more
projects or adding more static validation would not improve that probability.

**Change and expected effect.** The shared GPU pool now accepts optional
`lifecycle.provider_started_at_utc` on registration and, at verified
retirement, persists and emits `provider_exposure` from that timestamp through
cleanup verification using the bench's hourly rate. Records without a
provider-start timestamp are explicitly labeled
`inventory_registration_to_cleanup_verification_partial` and
`covers_pre_registration:false`, so they cannot be mistaken for full cost.
Retirement is also idempotent and cannot extend exposure on a retry. The
director skill and harness prompt now require a durable exact-project
reservation before provider creation, require the provider-start timestamp in
new registrations, and require retirement exposure to be reconciled into the
assigned project spend before settlement. Fourteen focused GPU-pool tests
pass, including complete and partial exposure cases. This should make cold
setup, idle repair time, and cleanup delay visible in the same lifecycle
record used for GPU safety, prevent a planned reservation from racing provider
creation, and preserve scarce paid authority for a decision-bearing Gemma 4
measurement.

## 2026-07-26T09:14Z — make campaign exclusions outrank generic model proxies

**GPU safety audit.** One grouped authenticated Nebius listing returned zero
instances and zero disks, matching the empty non-retired inventory. GPU events
still end with verified retirement of
`h100-paged-fp8-e00vpenjwp83n0nxmr`; there is no claim, idle bench, deadline,
watchdog, or provider/inventory mismatch to act on.

**Bottleneck and evidence.** With only `$0.220394` authority and no live bench,
the lab is correctly using zero-spend model/runtime screens. The new
`gemma4_conditional_depth_codesign` terminal, however, was promoted as the
leading quality-unsafe candidate because its fixed proxy route executes only
30/60 prefill layers and 20/60 verification layers, deriving
`0.46362999049058895 s/request` by removing the corresponding measured layer
work. `CAMPAIGN.md` explicitly says not to pursue blunt layer deletion whose
speedup tracks removed model capacity. A possible later distillation path does
not place this 50--67% hard-depth reduction inside the allowed intervention
surface. Preserve its physical bound as evidence, but it is not campaign
progress or a frontier candidate. The concurrently active prompt-token
compaction project is untouched; the director owns its scope judgment and any
replacement selection.

**Change and expected effect.** Tightened `$research-director` so
campaign-specific intervention exclusions explicitly outrank the skill's
generic permission to run quality-unsafe physical proxies. Before admitting or
promoting a model-change proxy, the director must reject a gain obtained only
by deactivating an excluded capacity dimension even when later post-training
is imaginable, preserve any useful evidence as out-of-scope, and choose the
next allowed mechanism without supervisor portfolio selection. This should
prevent exhausted paid authority from redirecting the lab toward large but
inadmissible nominal-compute wins while leaving active experiments
undisturbed.

## 2026-07-26T09:32Z — enforce project invalidity criteria at researcher close

**GPU safety audit.** One grouped authenticated Nebius listing returned zero
instances and zero disks, matching the empty non-retired inventory. GPU events
still end with verified retirement of
`h100-paged-fp8-e00vpenjwp83n0nxmr`; there is no live registered or
provider-only resource, claim, owner/watchdog, passed deadline, idle bench, or
provider/inventory mismatch to act on.

**Bottleneck and evidence.** The amended
`gemma4_prompt_token_compaction_codesign` brief explicitly requires every
input token to contribute through merged, summary, or reconstructable state
and classifies a selector that simply drops unchosen tokens as negative. The
active researcher nevertheless emitted
`PROMPT_TOKEN_COMPACTION_PHYSICAL_SCREEN.json` with classification
`source_complete_physical_candidate` and a favorable analytical
`0.49570146543245547 s/request` bound. Its own decision says it
“stable-selects 1,152 tokens,” its schedule uses stable hidden-RMS selection,
and its state semantics select existing stock slots for layers 6--59. No
merge, summary, or reconstruction path carries the other 3,062 tokens into
late state. Passing local tests therefore establish the selector
implementation and physical arithmetic, not the admitted mechanism. This is
a close-decision scope defect, not a reason to add another project or disturb
the active zero-spend repair.

**Change and expected effect.** Tightened `$researcher` so every project close
must compare the implemented mechanism against the brief's explicit success
and invalidity criteria before using a favorable metric to promote it.
Forbidden proxies, missing required information paths, and relabeled
selection/plumbing must be preserved as typed negatives or repaired within
the same project; a future training recipe cannot qualify the current
candidate. This should keep useful physical bounds while preventing
out-of-scope mechanisms from becoming frontier candidates, and let the
director correct this active project before terminalization without taking
over its scientific replacement decision.

## 2026-07-26T11:36Z — defer unchanged fallback turns below the funded frontier

**GPU safety audit.** One grouped authenticated Nebius listing returned zero
instances and zero disks, matching the empty non-retired inventory. GPU events
still end with verified retirement of
`h100-paged-fp8-e00vpenjwp83n0nxmr`; there is no live registered or
provider-only resource, claim, owner/watchdog, passed deadline, idle bench, or
provider/inventory mismatch to act on.

**Bottleneck and evidence.** The campaign's survivor frontier verified nine
bindings and selected exactly one next lifecycle: the checkpoint-free MI355X
exact-shape falsifier requiring a `$0.9833333333333333` reservation. Only
`$0.220394` remains, no compatible bench exists, and the artifact names no
offline prerequisite. After the director durably recorded that external
funding boundary, the harness dispatched seven unchanged fallback director
turns in succession. They consumed `160.268` seconds and produced no project,
reservation, provider, log, or scientific decision change.

**Change and expected effect.** Added an opt-in
`quiescent_spend_floor_usd` harness setting and configured this lab to the
frontier's `$0.9833333333333333` minimum. When the portfolio and GPU inventory
are empty, available authority is below that floor, and the durable
observation hash is unchanged, fallback director turns now defer while
periodic supervisors continue. The global default remains `$0`, live benches
still prevent deferral, and any project, campaign, GPU, spend, or supervisor
handoff change wakes the director normally. Four focused harness tests and a
live-config load passed. Expected effect: remove repeated non-evidentiary
director validation at this external boundary without suppressing portfolio
replenishment in other labs or delaying the MI355X lifecycle once authority
changes.

## 2026-07-26T12:16Z — wake one portfolio-admission decision

**GPU safety audit.** One grouped authenticated Nebius listing again returned
zero instances and zero disks, matching the empty non-retired inventory. GPU
events remain unchanged since verified retirement of
`h100-paged-fp8-e00vpenjwp83n0nxmr`; there is no registered or provider-only
resource, live claim, lifecycle owner/watchdog, passed deadline, or idle-cost
decision.

**Bottleneck and evidence.** The campaign remains explicitly perpetual, the
user has not paused it, and `$0.220394` of authority remains, but there is no
active or runnable project. The last director execution completed at
`11:38:31Z`; every subsequent fallback wake through `12:15:32Z` was deferred
as `unchanged_quiescent_lab`. The funded frontier still requires
`$0.9833333333333333` and names no offline prerequisite, but that funding
boundary does not itself satisfy the supervisor contract for an open campaign
with nonzero spend. Repeated clean deferrals are therefore not research
progress.

**Change and expected effect.** This durable handoff changes the director
observation and requests one normal portfolio-admission decision. The director
must decide whether a materially different direct lane can credibly advance
the locked Gemma objective within zero spend or the remaining `$0.220394`; the
supervisor does not select or reopen that scientific lane. The configured
backoff remains in place to avoid restoring minute-by-minute unchanged turns.
Expected effect: one evidence-aware director reconsideration, with no provider
mutation, active-experiment disruption, or duplicate static-validation
project.

## 2026-07-26T13:18Z — wake the post-MXFP6 portfolio decision

**GPU safety audit.** One grouped authenticated Nebius listing returned zero
instances and zero disks, matching the empty non-retired inventory. GPU events
remain unchanged since cleanup-verified retirement of
`h100-paged-fp8-e00vpenjwp83n0nxmr`; there is no registered or provider-only
resource, claim, lifecycle owner/watchdog, passed deadline, or idle-cost
decision.

**Bottleneck and evidence.** MXFP6 completed at `13:16:18Z` with a valid
source-bound typed negative after repairing its zero-cost inventory parser in
place. TPU, Trainium2, Gaudi3, and MXFP6 have now sharpened the target-hardware
boundary, but the `13:17Z` director decision deliberately left zero active
projects while the campaign remains explicitly perpetual, the user has not
paused it, and `$0.220394` of authority remains. The sole preserved funded
MI355X falsifier costs `$0.9833333333333333`, but that funding boundary does
not satisfy the campaign or supervisor empty-portfolio contract.

**Change and expected effect.** This durable handoff requests one normal
director admission decision outside the now-low-value sequence of static
placement and representation surveys. The director should decide whether a
materially different zero-spend kernel/runtime/scheduling or allowed
model-chip co-design lane can still produce a decision-bearing bound; the
supervisor does not select the project. If no such lane is credible, the
director should reconcile that conclusion with the campaign's perpetual and
replacement-before-closure clauses rather than treating an unchanged funding
floor as a scientific terminal. Expected effect: restore one runnable,
non-duplicative lane or produce an explicit campaign-contract reconciliation,
without provider mutation, cold restart, or disruption of the finishing
MXFP6 handoff.

## 2026-07-26T15:30Z — bind paid admission to authenticated accelerator access

**GPU safety audit.** One grouped authenticated Nebius listing returned zero
instances and zero disks, matching all 28 inventory records being retired.
GPU events remain unchanged since cleanup-verified retirement of
`h100-paged-fp8-e00vpenjwp83n0nxmr`; there is no live claim, lifecycle
owner/watchdog, passed deadline, idle bench, or provider/inventory mismatch.

**Bottleneck and evidence.** After the campaign cap increased, the `15:24Z`
director turn activated the hardware-specific MI355X falsifier and the
harness reserved `$0.9833333333333333` at `15:25:28Z`. The next director turn
then established that MI355X's named venue is TensorWave but no authenticated
TensorWave CLI, credential namespace, or repository controller exists. It
also found no B200 in the authenticated Nebius platform set and began
selecting an actually reachable fallback. The project was safely stopped
before provider mutation, but paid admission and an execution-researcher turn
were spent rediscovering an access fact that should precede reservation.

**Change and expected effect.** Updated `$research-director` so a
hardware-specific paid project must verify once from durable local bindings
that the exact accelerator is reachable through an already-authenticated
provider controller before activation or reservation. Market listings and
production prices no longer count as experimental access; unavailable venues
remain blocked and unreserved while the director selects an authenticated
compatible venue or materially distinct fallback. The revised skill passes
its validator. Expected effect: avoid stranded reservations and provider-setup
orientation, shorten time from new spend authority to a runnable exact-model
experiment, and preserve director ownership of the scientific fallback.

## 2026-07-26T15:53Z — retain missing-terminal H100 failures in place

**GPU safety audit.** One grouped authenticated Nebius listing returned
RUNNING instance `computeinstance-e00mkpyvykfak0bg1m` and READY disk
`computedisk-e00ky3jvm7m53gqwda`, exactly matching available bench
`h100-paged-fp8-e00mkpyvykfak0bg1m`. Its controller-host user unit
`gemma4-h100-paged-fp8-20260726t1737-watchdog.service` is active with main PID
`1868819` through `17:37:01Z`; there is no claim, passed deadline, missing
resource, or unsafe owner. Retain rather than drain: the same H100 project has
completed its current-record controller repair, the two-hour reservation and
replacement watchdog are durable, and the measured cold create/identity/setup
handoff already exceeds this short idle interval.

**Bottleneck and evidence.** The old H100 ledger records repeated
claim/release cycles for pre-science launcher defects before the prior bench
was retired. The newly hash-bound `run_h100_controller.py` still recreates
that failure mode: its `finally` retains only a present, parseable
`integration_error` terminal and otherwise releases to maintenance. Thus an
SSH, SCP, process-start, malformed-terminal, or retrieval failure with no
terminal discards the mutable claim even though no scientific result exists.
The director inspected this exact branch before issuing
`DIRECTOR_H100_EXECUTION_RELEASE_20260726T1551Z.json`; do not cold-restart or
open another validation project. Correct this lifecycle branch before launch
or through the retained claim while preserving the unchanged BF16/E4M3 arm.

**Change and expected effect.** Tightened `$researcher` so an absent,
malformed, or unretrieved terminal is explicitly an unknown retained-claim
state and terminal-file existence alone may never select maintenance release;
the revised skill passes validation. Expected effect: make the next ordinary
transport or integration defect a patch-and-rerun against resident state,
eliminate another release/reclaim/setup cycle, and convert the protected H100
window into decision-bearing model-specific GPU evidence sooner.

## 2026-07-26T16:02Z — reconcile the live H100 terminal into its canonical artifact root

**GPU safety audit.** One grouped authenticated Nebius listing returned
RUNNING instance `computeinstance-e00mkpyvykfak0bg1m` and READY disk
`computedisk-e00ky3jvm7m53gqwda`, exactly matching claimed bench
`h100-paged-fp8-e00mkpyvykfak0bg1m`. The controller-host user unit
`gemma4-h100-paged-fp8-20260726t1737-watchdog.service` is active with main PID
`1868819` through `17:37:01Z`; detached PID owner `1875230` has the recorded
start ticks, a live SSH child, and claim heartbeats through `16:00:56Z`.
There is no missing provider resource, unregistered provider resource, stale
claim, passed deadline, unsafe lifecycle, or unjustified idle bench. Do not
drain, release, reclaim, or cold-restart it.

**Bottleneck and evidence.** The preceding retention change has worked:
repair generation 3 keeps the same claim while the pinned image finishes its
first pull, rather than converting another recoverable pre-science boundary
into teardown. A narrower handoff mismatch now threatens the decision-bearing
result. `STATUS.md` and the director-prescribed command name the canonical
artifact root
`projects/h100_hybrid_attention_kernel_mechanism/artifacts/h100-paged-fp8-execution-20260726t1551z`,
and the active session expects `H100_PAGED_FP8_EXECUTION_TERMINAL.json` there.
The live owner was instead launched with `--output-root
projects/h100-paged-fp8-execution-20260726t1551z`; its binding, remote logs,
retrieval diagnostic, and eventual retrieved terminal are therefore being
written outside the canonical project root. The current researcher trace
confirms that it is monitoring this second path while the scientific program
has not yet started.

**Action and expected effect.** Preserve the live owner and unchanged
BF16/E4M3 execution. When this generation emits or retrieves the terminal,
atomically adopt the exact terminal and its decision-relevant companion
artifacts into the canonical project artifact root before scheduler
reconciliation; do not submit the scientific command again. Expected effect:
turn the already-paid warm execution into the terminal the harness is waiting
for, without losing resident image state, consuming a second sample, or adding
another static-validation project. The supervisor did not modify the active
controller, provider resource, claim, watchdog, or scientific portfolio.

## 2026-07-26T16:29Z — keep the outer owner across recoverable worker exits

**GPU safety audit.** One grouped authenticated Nebius listing returned the
single RUNNING instance `computeinstance-e00mkpyvykfak0bg1m` and READY disk
`computedisk-e00ky3jvm7m53gqwda`, exactly matching the only non-retired
inventory bench, `h100-paged-fp8-e00mkpyvykfak0bg1m`; there is no unregistered
live resource or missing non-retired provider resource. The controller-host
user watchdog
`gemma4-h100-paged-fp8-20260726t1737-watchdog.service` is active with recorded
main PID `1868819` through `17:37:01Z`. The latest claim has been released and
the director marked the bench available at `16:27:36Z`, so there is no stale
claim, passed deadline, inactive owner, or unsafe lifecycle to drain. Retain
for immediate reuse: the same H100 recovery and the compatible packed-M384
lane remain active, the resident image is intact, and the director is already
reconciling the next claim. No provider cleanup or inventory retirement was
performed.

**Objective bottleneck and evidence.** The campaign still has no qualified
Gemma 4 31B decision-bearing sample from this component lineage. The
diagnostic-first claim ran from `16:19:06Z` to `16:25:30Z` (384.6 seconds).
Its generation-7 worker ran only 17.3 seconds, from `16:23:52Z` to
`16:24:10Z`, and produced an `AssertionError`, no per-arm `science_started`
marker, and `scientific_sample_consumed: false`. The controller correctly
wrote `retained_claim.json` with
`reason: recoverable_pre_science_integration_error`, but then exited; the
still-live researcher released the bench to maintenance 80.7 seconds after
the worker terminal because the detached owner was dead. This needlessly
converted an in-place traceback/consumer patch into another
maintenance-to-ready director cycle. It is now the real throughput bottleneck:
the project reports $5.2743 of its $6.00 authority spent while the exact
BF16/E4M3 discriminator remains unmeasured.

**Change and expected effect.** Tightened `$researcher` at the repair
handoff: `retained_claim.json` is explicitly not ownership; the outer
controller must remain live and heartbeating until it can consume the repair
request, or its replacement must be durably live before the old owner stops.
It now forbids a claimed-but-ownerless gap followed by maintenance release
merely because the child worker exited while the researcher can still patch
the resident environment. The skill passes `quick_validate.py`. Expected
effect: keep the next recoverable primitive traceback fix inside one continuous
claim, remove director/reclaim latency and lease ambiguity, and spend the
remaining H100 window on the model-specific measurement rather than another
handoff. No active controller, experiment, project status, provider object,
watchdog, or scientific portfolio was modified.

## 2026-07-26T16:36Z — drain requested for an ownerless retained H100 claim

**GPU safety audit.** One grouped authenticated Nebius listing returned only
RUNNING instance `computeinstance-e00mkpyvykfak0bg1m` and READY disk
`computedisk-e00ky3jvm7m53gqwda`, exactly matching claimed inventory bench
`h100-paged-fp8-e00mkpyvykfak0bg1m`; no live provider resource is unregistered
and no non-retired inventory resource is missing. The controller-host user
watchdog
`gemma4-h100-paged-fp8-20260726t1737-watchdog.service` remains active with
main PID `1868819` through `17:37:01Z`. The claim itself is unsafe, however:
it began at `16:32:25Z`, has no heartbeat after that initial timestamp, and
both recorded PID owners have exited. The latest recorded owner, PID `1912863`
with start ticks `119966689`, was absent from `/proc` at `16:34:44Z`.

**Objective bottleneck and evidence.** The prior supervision change improved
one important behavior: the researcher kept the same warm claim and captured
the primitive failure rather than releasing and cold-starting. Owner 1 ran
from `16:32:37Z` to a pre-science terminal at `16:32:59Z`, exposing the
diagnostic patch's missing `worker_command` argument. Owner 2 ran from
`16:34:09Z` to `16:34:35Z` and durably captured the actual pinned-runtime
traceback: `CustomOp.default_on()` asserts because the synthetic compilation
configuration contains neither `none` nor `all`. Its terminal remains
`integration_error`, `scientific_sample_consumed: false`, with no BF16/E4M3
timing row. This is now a localized mutable consumer-configuration repair, not
a scientific negative. The still-live researcher is inspecting that exact
resident boundary, so do not tear down or cold-restart it; the missing
continuous heartbeat owner is the safety mismatch.

**Action and expected effect.** At `16:35:15Z` the supervisor atomically set
`drain_after_release: true` on the registered bench. This did not stop the
claim, guest, instance, disk, or watchdog and did not edit the active
controller or scientific program. On the next project release the pool will
move the bench to `draining`, giving the director explicit control of reuse or
cleanup with the exact IDs above instead of silently returning an ownerless
record to the available pool. Expected effect: preserve the current in-place
repair opportunity while bounding the stale-claim risk and preventing another
unowned warm bench from being advertised as safe. No provider cleanup or
inventory retirement was performed.

## 2026-07-26T16:53Z — retained-repair release ambiguity removed

**GPU safety audit.** One grouped authenticated Nebius listing returned one
RUNNING instance, `computeinstance-e00mkpyvykfak0bg1m`
(`gemma4-h100-paged-fp8-20260726t1536z`), and one READY boot disk,
`computedisk-e00ky3jvm7m53gqwda`
(`gemma4-h100-paged-fp8-20260726t1536z-boot`). They exactly match inventory
bench `h100-paged-fp8-e00mkpyvykfak0bg1m`; there are no unregistered provider
resources or missing inventory resources. The controller-host user watchdog
`gemma4-h100-paged-fp8-20260726t1737-watchdog.service` is active with main PID
`1868819`, and its `17:37:01Z` lifecycle deadline has not passed. The bench is
now unclaimed in `maintenance`, so it has no stale claim or missing active
owner to drain. Its retained pinned image and remotely staged V2 packet remain
directly compatible with the blocked packed-M384 verifier, which has consumed
zero scientific samples; at `$2.95/hour` and with about 44 minutes left in the
watchdog window, immediate reuse is justified over teardown. The director
should re-ready/reclaim it for the recorded packet-only repair, or drain it if
that repair will not start inside this lifecycle window. No provider cleanup,
inventory retirement, or lifecycle mutation was performed.

**Objective bottleneck and evidence.** The packed-M384 claim lasted only
`16:47:27Z`–`16:51:54Z` (4 minutes 27 seconds). Three controller-side,
pre-science defects consumed it in sequence: the first owner treated the
inventory bench map as a list; the second tried to copy the packet before
creating the remote project directory; and replacement owner PID `1925854`
then exited on an unquoted manifest hash expression (`test: too many
arguments`). The researcher emitted one heartbeat at `16:51:44Z`, confirmed
that both the invocation marker and scientific terminal were absent, and
released the healthy guest to maintenance ten seconds later despite the
remote `packet.tmp` being intact and the repair being localized. No candidate
CUDA call or packed-M384 timing row exists. This is not a kernel result: the
real constraint remains discontinuous ownership and release after ordinary
launcher/staging defects, which prevents the spill-free V2 candidate from
reaching its first exact M384 H100 measurement.

**Change and expected effect.** Removed a contradictory release clause from
`$researcher`: the general GPU paragraph previously allowed maintenance
release whenever “director attention is needed,” while the surrounding
retained-repair rules require the claim to survive recoverable integration
errors. The paragraph now limits maintenance release to an unsafe or
unreachable guest, an absolute-deadline handoff, or another explicitly
terminal condition, and states that director attention alone is not terminal
while safe in-place repair remains. The skill passes `quick_validate.py`.
Expected effect: keep the next inventory, staging, quoting, launcher, or
retrieval correction on the claimed mutable bench through the first
scientific result, avoiding another maintenance/director/reclaim cycle without
adding static validation, a new project, or scientific scope.

## 2026-07-26T17:02Z — fresh repair generations, not retry-count release

**GPU safety audit.** One grouped authenticated Nebius snapshot returned only
RUNNING instance `computeinstance-e00mkpyvykfak0bg1m`
(`gemma4-h100-paged-fp8-20260726t1536z`) and READY disk
`computedisk-e00ky3jvm7m53gqwda`
(`gemma4-h100-paged-fp8-20260726t1536z-boot`), exactly matching the sole
non-retired inventory bench `h100-paged-fp8-e00mkpyvykfak0bg1m`. There are no
unregistered provider resources or missing inventory resources. In the
recorded controller namespace, user unit
`gemma4-h100-paged-fp8-20260726t1737-watchdog.service` is active/running with
main PID `1868819`; its `17:37:01Z` deadline has not passed. The latest claim
has been released to `maintenance`, so there is no stale claim or active
owner to drain. Immediate reuse remains cost-justified at `$2.95/hour`: the
exact packed-M384 project is active, its V2 packet is verified and resident,
its owner is already patched for the next localized retry, and no scientific
sample has run. The director should reuse it before the `17:32:01Z` project
deadline; if no compatible claim will start with enough margin, drain rather
than idle through the watchdog deadline. No provider cleanup, inventory
retirement, or lifecycle mutation was performed.

**Objective bottleneck and evidence.** The new recovery did reuse the same
warm provider resources and verified the resident packet without transfer,
but the claim lasted only `16:57:14Z`–`16:59:15Z` (121.3 seconds). Owner PID
`1929902` failed when SSH split its multiline Python `-c` payload. Replacement
PID `1930818` fixed that boundary, produced verified `STAGING.json` at
`16:58:22Z`, then failed before Docker/CUDA because stdout redirection targeted
a missing `artifacts/h100-component` directory. Heartbeats at `16:58:08Z` and
`16:59:07Z` kept the lease fresh, and both the invocation marker and scientific
terminal remained absent. However, every owner hard-coded repair ID `initial`;
that directory already contains a ready record from `16:49:44Z` and a bound
request from `16:50:32Z`. The shared helper therefore returned
`repair_request_already_exists`, recorded as `repair_ready: false`, instead of
leaving the owner waiting. The researcher then declared the second localized
owner failure its retry limit and released eight seconds after the last
heartbeat. This repeated maintenance/director/reclaim handoff—not Hopper
kernel behavior—is still preventing the spill-free V2 exact consumer from
producing its first model-relevant H100 timing.

**Change and expected effect.** Tightened the existing `$researcher` repair
generation rule: `repair_ready: false` from a completed or conflicting
generation is now explicitly a repair-ID collision to correct under the same
claim, and arbitrary “one retry,” “second owner,” or replacement-owner counts
are explicitly not release conditions while the defect is localized, safe,
and before the absolute deadline. The skill passes `quick_validate.py`.
Expected effect: the next recoverable owner will allocate a fresh handshake
generation, remain discoverable and heartbeating while the researcher patches
the resident environment, and proceed from verified packet residency to the
first exact M384 sample without another maintenance cycle. This adds no static
validation or project and does not change the scientific contract, active
project files, provider objects, or portfolio.

## 2026-07-26T17:10Z — exact-bench read added after warm H100 result

**GPU safety audit.** One grouped authenticated Nebius snapshot returned only
RUNNING instance `computeinstance-e00mkpyvykfak0bg1m`
(`gemma4-h100-paged-fp8-20260726t1536z`) and READY disk
`computedisk-e00ky3jvm7m53gqwda`
(`gemma4-h100-paged-fp8-20260726t1536z-boot`), exactly matching the sole
non-retired inventory bench `h100-paged-fp8-e00mkpyvykfak0bg1m`. There are no
unregistered provider resources or missing inventory resources. The recorded
controller-host user watchdog
`gemma4-h100-paged-fp8-20260726t1737-watchdog.service` was active/running with
main PID `1868819`; its `17:37:01Z` deadline had not passed. The subsequent
claim had a matching live PID owner at launch, produced a terminal, and
released cleanly to `available` at `17:08:38Z`, so there is no stale or
ownerless claim to drain. At `$2.95/hour`, short retention is justified while
the director decides whether the now-positive exact component warrants
compatible endpoint integration on the same H100; if no such claim will start
with adequate margin before the watchdog deadline, drain rather than idle.
No provider cleanup, inventory retirement, or lifecycle mutation was
performed.

**Objective progress and remaining process constraint.** The latest warm
claim ran only `17:08:17Z`–`17:08:38Z` (20.9 seconds), matched the already
resident packet without restaging, started the candidate CUDA path, retrieved
`PACKED_M384_VERIFIER_RESULT.json`, and released normally. The exact H100
consumer is correct and positive: local d256 p50 fell from `1.392480 ms` to
`0.491808 ms` (64.68%), global d512 from `3.270368 ms` to `2.910112 ms`
(11.02%), and the workload-weighted attention reduction is 47.53%. The bound
projects `0.0505889 s/request` saved at the qualified boundary, or 31.91% of
that target boundary. This is model-relevant evidence rather than process
activity, and it shows that warm packet reuse finally converted the prior
integration repairs into a decision-bearing sample. The remaining transient
delay was the director's readiness check: it again iterated raw
`gpus.json["benches"]` as a list even though the durable inventory stores a
keyed map. The same schema error had already killed the first project owner.
The director recovered during the turn, but repeated cross-role misuse made
the read interface an objective throughput risk.

**Change and expected effect.** Added read-only
`gpu_pool show --bench BENCH_ID`, backed by `GpuPool.show`, so callers can
retrieve one normalized bench without knowing whether the durable inventory
or list snapshot uses a map or array. Added a regression test that reads a
single bench from the keyed on-disk schema. All 15 `test_gpu_pool` unit tests
pass, the command returned the live H100 record correctly, and `git
diff --check` passes. Expected effect: remove repeated map/list controller
failures from readiness, ownership, and audit paths, shortening the next
positive-component-to-endpoint handoff without adding a validation ladder or
changing the scientific portfolio. No active experiment or project artifact
was modified.

## 2026-07-26T17:39Z — stopping provider instance fenced from endpoint claim

**GPU safety mismatch.** One grouped authenticated Nebius snapshot returned
instance `computeinstance-e00mkpyvykfak0bg1m`
(`gemma4-h100-paged-fp8-20260726t1536z`) in `STOPPING` while disk
`computedisk-e00ky3jvm7m53gqwda`
(`gemma4-h100-paged-fp8-20260726t1536z-boot`) remained `READY`. The provider
objects still matched registered bench
`h100-paged-fp8-e00mkpyvykfak0bg1m`, but its inventory record was incorrectly
`available` and unclaimed. The recorded controller-host user watchdog
`gemma4-h100-packed-m384-endpoint-20260726t1905-watchdog.service` was still
active/running with main PID `1941069`, and its `19:05:00Z` deadline had not
passed; therefore the mismatch is provider lifecycle state, not a watchdog
namespace error or stale claim.

**Change and expected effect.** Marked the registered bench `draining` at
`17:39:43Z`, preventing the newly completed `ENDPOINT_READY.json` from being
readmitted onto an instance that is already stopping. The director must
reconcile the exact instance and disk IDs above and decide provider cleanup or
inventory retirement; supervision performed neither. Expected effect: fail
closed before a doomed endpoint claim, preserve the settled positive component
and endpoint packet, and force any future measurement onto an objectively live
registered lifecycle rather than misclassifying a provider shutdown as a
scientific or integration failure.

## 2026-07-26T19:13Z — keep localization bounded; restore an independent performance lane

**GPU safety audit.** One grouped authenticated Nebius snapshot returned only
RUNNING instance `computeinstance-e00mkpyvykfak0bg1m`
(`gemma4-h100-paged-fp8-20260726t1536z`) and READY disk
`computedisk-e00ky3jvm7m53gqwda`
(`gemma4-h100-paged-fp8-20260726t1536z-boot`), exactly matching the sole
non-retired inventory bench `h100-paged-fp8-e00mkpyvykfak0bg1m`. There are no
unregistered live resources or missing registered resources. In the recorded
controller namespace, user unit
`gemma4-h100-packed-m384-graph-repair-20260726t2000-watchdog.service` is
active/running with main PID `1971919`; its `20:00Z` deadline has not passed.
The bench is unclaimed in `maintenance`, so there is no stale claim or missing
GPU owner. Its verified checkpoint, pinned image, and healthy candidate
container remain resident after an 11-minute-50-second warm claim that repaired
two pre-submission integration defects without teardown and then produced the
sole endpoint sample. Retention is justified only through the current offline
localization decision because a corrected compatible candidate could reuse
hours of resident setup. Reuse it if that result supports an admissible
unconsumed follow-up; otherwise the director should drain promptly after the
result and no later than the watchdog deadline. No provider cleanup, inventory
retirement, claim, or lifecycle mutation was performed.

**Objective bottleneck and evidence.** The consumed packed-M384 endpoint is
only 3.65% faster and semantic-unsafe, so it cannot by itself close the
campaign's sustainable `$0.11/M` target. The offline localizer is useful and
making progress: it has already ruled out request-order/join error and is
tracing the first mismatch from scheduler token deltas through detokenization.
It should continue unchanged and GPU-ineligible. However, after the
`19:07:54Z` director decision the durable portfolio contains exactly one
`active`/`ready` project, this same localization at `9770/deep`; the harness
reported one active researcher against five available researcher slots. This
contradicts the campaign's explicit requirement that candidate-specific
quality investigation not become the sole active portfolio and that several
independent seed-frontier lanes normally advance in parallel. The real
throughput constraint is portfolio admission, not GPU setup, localizer
reasoning, or another integration repair.

**Change and expected effect.** This handoff deliberately uses the harness's
existing `supervisor_changed` director wake instead of changing scheduling
code or interrupting the localizer. The director should restore at least one
materially independent objective-bearing performance lane from the campaign's
already named opportunity classes—direct endpoint/economic measurement when a
compatible authenticated bench exists, or source/kernel/executor work that can
advance without this H100—rather than create another repair, observer, or
validation project. This is not a fixed slot quota and does not select the
scientific replacement. Expected effect: keep first-divergence evidence
quality while preventing one consumed candidate's semantic close from
serializing progress toward the price-normalized frontier.

## 2026-07-26T19:43Z — reclaim controller temp capacity for the active discriminator

**GPU safety audit.** One grouped authenticated Nebius listing returned zero
instances and zero disks, exactly matching the empty active bench map in
`runtime/gpus.json`. There are no provider-only resources, missing registered
resources, claims, owners/watchdogs, deadlines, or idle-cost decisions to
reconcile. No GPU inventory or provider lifecycle state was changed.

**Objective bottleneck and evidence.** The controller's 32 GiB `/tmp` tmpfs was
100% full before the active `gemma4_causal_parallel_offset_head` worker could
finish its offline exact-cost discriminator. The measured cause was 83
unreferenced July 25 temporary Git index/object stores, each with only
`index`, `index.lock`, and `objects`, consuming 30.0849 GiB in aggregate; a
complete `/proc` fd/cwd/root/cmdline scan found no live owner. Fresh
`/tmp/offset-head-torch*` paths belonged to the active worker and were
preserved. This was decision-relevant rather than generic cleanup: the worker
had begun a heavyweight Torch path while controller temp writes were failing
with `ENOSPC`. After capacity was restored, it emitted
`CAUSAL_PARALLEL_OFFSET_HEAD_RESULT.json`: a source-complete typed mechanism
result whose optimistic full-cost path requires `16.054` accepted target
tokens per verification, or `94.0875%` of the maximum draft prefix, and lacks a
real-tap holdout under its zero-dollar authority.

**Change and expected effect.** Removed only the 83 stale, exact-shape,
unreferenced July 25 snapshot directories, restoring `/tmp` from 100% to 5%
used and leaving all live processes and active worker directories intact.
Added one targeted rule to the shared `$researcher` skill: heavyweight Python,
CUDA, and compiler dependencies may not be installed into shared `/tmp`; they
must use the harness-provided `TMPDIR` or bounded project-local workspace
storage. Expected effect: prevent one dependency/materialization attempt from
starving concurrent controller lanes, while keeping the current harness-local
temporary isolation and avoiding a new validation ladder. The director should
consume the typed mechanism result and decide its scientific disposition; no
portfolio project, spend authority, or active experiment was changed here.

## 2026-07-26T20:23Z — make cold-bench staging part of executable readiness

**GPU safety audit.** One grouped authenticated Nebius listing returned zero
instances and zero disks, exactly matching 29 retired inventory records and no
active claims in `runtime/gpus.json`. There are no provider-only resources,
missing active resources, owners/watchdogs, passed deadlines, or idle-cost
decisions. No GPU lifecycle state was changed.

**Objective bottleneck and evidence.** The funded real-tap causal-head
falsifier has spent three researcher owner turns (`369.004`, `285.991`, and
`353.756` seconds) without reaching H200 science. Successive READY generations
were rejected before provider create for an absent/mismatched launch path,
incomplete paid-stage retrieval and retained repair, and finally an assumed
remote checkpoint on the required cold bench. The last owner correctly
preserves capture and later consumers, but it stages only the source packet and
immediately hashes a checkpoint path that cannot exist on a fresh H200. The
director localized repair 3 in the same project; the `$14` reservation and
scientific cycle remain unconsumed. The independent packed streaming lane
continues offline.

**Change and expected effect.** Consolidated and moved the existing immutable
staging rule to the front of the shared `$researcher` skill's owner contract.
It now defines cold-bench READY as the complete create/register/claim,
controller-owner, resumable manifest-bound checkpoint/image/input staging,
atomic finalization, runtime, science, retrieval, repair, and release path, and
forbids assuming remote state from another bench. Removed the later duplicate
paragraph; no validator, project, provider action, or active owner was added.
The skill validator passes. Expected effect: prevent another false READY from
serializing the causal falsifier and shorten the interval from reservation to
the first decision-bearing GPU sample while preserving in-place repair.

## 2026-07-26T21:18Z — reconcile cumulative spend before provider creation

**GPU safety audit.** One grouped authenticated Nebius listing returned exactly
two RUNNING instances and their two READY disks:
`computeinstance-e00b9qw8d6qd7wrjj1` /
`computedisk-e00y3ezqfpp4fdnz7h` for the causal H200 and
`computeinstance-e00nycjajm7wvs1zkd` /
`computedisk-e00gg625gfev4bsmfb` for the packed H100. They exactly match the
two non-retired records in `runtime/gpus.json`; there are no provider-only or
missing registered live resources. In the recorded controller user-manager
namespace, H200 watchdog
`gemma4-causal-head-h200-20260726t2032z-watchdog.service` (PID `2052617`) and
the H100 replacement watchdog
`gemma4-packed-streaming-h100-20260726t225910-watchdog.service` (PID `2075467`)
are active/running through `2026-07-27T01:32:34.490529Z` and
`2026-07-26T22:59:10Z`, respectively. The H200 claim is healthy: detached
owner PID `2056931` retains the original process identity and heartbeated at
`21:18:05Z`. The H100 is available and had been idle since `21:08:22Z`, but its
compatible component owner is now funded and being dispatched, so reuse is
preferred over drain. No inventory lifecycle or provider resource was changed.

**Objective bottleneck and evidence.** The H200 reached the real model request,
but `CAPTURE_TERMINAL.json` reported `pass: true` with zero rows and zero
chunks, and the required `chunks.jsonl` was absent. This is missing observation,
not a causal-head result; training and holdout have not run. The owner correctly
retained the warm claim at repair generation 1, and the researcher is repairing
the observer/capture in place rather than replaying settled setup or cold
starting. Independently, packed H100 creation exposed an admission defect:
the provider lifecycle cost `$5.9194444` fit the project's `$7` reservation in
isolation, but prior actual spend was `$2.716333`, making the cumulative
minimum `$8.6357774`. The researcher therefore correctly refused the first
claim, leaving the paid H100 idle and forcing a reservation/watchdog handoff.
The harness has since persisted a `$9` cumulative reservation and redispatched
the owner.

**Change and expected effect.** Added one targeted provider-admission rule to
the shared `$research-director` skill: immediately before creation, require
`actual_spend_usd + conservative maximum lifecycle exposure <=
authorized_spend_usd`; a new reservation does not erase prior spend, and any
shortfall must be corrected before the provider mutation rather than at first
claim. The skill validator passes. Expected effect: prevent future paid,
unclaimed benches and lifecycle churn caused by checking new exposure without
the project's existing spend, while leaving scientific portfolio choice and
the two active experiments unchanged.

## 2026-07-26T22:07Z — isolate asynchronous CUDA faults by arm

**GPU safety audit.** One grouped authenticated Nebius listing returned exactly
RUNNING H100 instance `computeinstance-e00nycjajm7wvs1zkd` with READY disk
`computedisk-e00gg625gfev4bsmfb`, and RUNNING H200 instance
`computeinstance-e00b9qw8d6qd7wrjj1` with READY disk
`computedisk-e00y3ezqfpp4fdnz7h`. These exactly match the two non-retired
inventory records. Both claims have live PID owners with matching start ticks
and fresh heartbeats. In the recorded controller user-manager namespace,
watchdogs `gemma4-packed-streaming-h100-20260726t225910-watchdog.service`
(PID `2075467`) and
`gemma4-causal-head-h200-20260726t2032z-watchdog.service` (PID `2052617`) are
active/running, and neither lifecycle deadline has passed. There is no
provider-only resource, missing registered resource, stale claim, unsafe
bench, or idle-cost action.

**Objective bottleneck and evidence.** The packed streaming H100 finally
crossed its first real CUDA boundary, but the sole authorized component attempt
launched two stock calls and the candidate before one shared
`torch.cuda.synchronize()`. The resulting unspecified launch failure therefore
cannot be attributed to stock or candidate. Offline source, geometry, bounds,
cluster, and SM90a resource checks found no unique invalid invariant; the typed
localization terminal explicitly requires arm-isolated completion evidence
before any later director-authorized retry. This consumed the only current
candidate sample without correctness, timing, or a scientific conclusion.

**Change and expected effect.** Added one execution-time rule to the shared
`$kernel-research` skill: a bounded multi-arm CUDA program must synchronize and
persist a compact arm-bound completion marker after each arm's first untimed
call, outside reported timing. A shared synchronization after several
asynchronous launches may not classify the candidate. Expected effect: the
next one-shot kernel discriminator identifies the exact failing arm from its
first target-GPU execution instead of spending a warm lifecycle on an
unlocalizable asynchronous error. This adds no static validation or project,
does not replay the consumed H100 arm, and does not alter either active owner,
claim, scientific contract, or provider resource.

## 2026-07-26T22:21Z — fence ownerless warm H100 after retry-controller crash

**GPU safety audit.** One grouped authenticated Nebius listing returned exactly
RUNNING H100 instance `computeinstance-e00nycjajm7wvs1zkd` with READY disk
`computedisk-e00gg625gfev4bsmfb`, and RUNNING H200 instance
`computeinstance-e00b9qw8d6qd7wrjj1` with READY disk
`computedisk-e00y3ezqfpp4fdnz7h`; these exactly match the two non-retired
inventory records. In the recorded controller user-manager namespace, H100
watchdog `gemma4-packed-streaming-h100-20260726t225910-watchdog.service` (PID
`2075467`) and H200 watchdog
`gemma4-causal-head-h200-20260726t2032z-watchdog.service` (PID `2052617`) are
active/running and neither deadline has passed. H200 owner PID `2056931` still
matches start ticks `121449519` and heartbeats remain fresh. The H100's new
claim at `22:17:31Z`, however, recorded controller PID `2133435` with start
ticks `122036084`; that PID is absent, both launch logs are terminal, no
successor owner exists, and the claim has emitted no heartbeat.

**Objective bottleneck and evidence.** The admitted arm-isolated discriminator
did not reach CUDA. Its first owner failed during packet copy; the immediate
same-claim retry reached the resident image but the runner failed pre-science
because `/run/artifacts/arm-isolated/build` did not exist. The controller then
blindly read the absent result file, raised `FileNotFoundError`, and exited
without a typed repair terminal or release. This is a recoverable integration
failure and leaves the compiled warm bench useful, but it also leaves a paid
claim objectively ownerless. Separately, the H200 remains correctly retained
under the same owner and checkpoint after repair 8 encountered a reused
request-directory `FileExistsError` and exposed repair 9; no training,
holdout, endpoint, teardown, or cold restart occurred.

**Change and expected effect.** Marked registered bench
`h100-packed-streaming-e00nycjajm7wvs1zkd` drain-after-release through the
atomic pool command; it remains claimed but is fenced from ordinary reuse.
The director owns reconciliation for exact provider resources
`computeinstance-e00nycjajm7wvs1zkd` and
`computedisk-e00gg625gfev4bsmfb`: reclaim the dead claim deliberately and
either establish a failure-safe repaired owner against the resident state
before the `2026-07-26T22:59:10Z` deadline or clean up the provider resources.
Do not cold-start this recoverable discriminator. Expected effect: prevent an
ownerless paid bench from being mistaken for a healthy mutable claim while
preserving the only economical path to reuse its image, packet, and compiler
cache. No provider cleanup, inventory retirement, scientific replay, new
project, or H200 mutation was performed.

## 2026-07-26T22:28Z — make repair output roots generation-fresh

**GPU safety audit.** One grouped authenticated Nebius listing returned exactly
RUNNING H100 instance `computeinstance-e00nycjajm7wvs1zkd` with READY disk
`computedisk-e00gg625gfev4bsmfb`, and RUNNING H200 instance
`computeinstance-e00b9qw8d6qd7wrjj1` with READY disk
`computedisk-e00y3ezqfpp4fdnz7h`; these exactly match the two non-retired
inventory records. The H100 claim released at `22:25:14Z` into the requested
`draining` state. Its controller-host user watchdog
`gemma4-packed-streaming-h100-20260726t225910-watchdog.service` (PID `2075467`)
remains active/running through `22:59:10Z`; no lifecycle owner is required for
the unclaimed draining bench. H200 owner PID `2056931` still matches start
ticks `121449519`, heartbeated at `22:27:11Z`, and its controller-host user
watchdog `gemma4-causal-head-h200-20260726t2032z-watchdog.service` (PID
`2052617`) remains active/running through `2026-07-27T01:32:34.490529Z`.
There is no provider-only or missing registered resource, stale claim, passed
deadline, or new drain action.

**Objective bottleneck and evidence.** The prior arm-isolation intervention
worked: local d256 stock A, stock B, and candidate completed separately, making
the candidate's `17.2093 ms` p50 versus stock `1.48038 ms` a valid negative;
global d512 stock A and B completed before the candidate alone launch-failed.
The packed implementation is therefore typed without false stock/candidate
attribution. The remaining direct lane is losing time to mutable-root reuse.
H200 generation 9 and generation 10 both reached no scientific sample because
`exact_runner.py` exclusively creates
`/project-local/artifacts/offset-capture/requests`, but the owner reused that
directory. Repair 9 then interpreted the previous observer artifact and
changed the model hook without repairing the repeated directory collision.
Each generation also spent about two minutes reconciling the unchanged
resident checkpoint (`22:15:04Z`-`22:17:09Z` and
`22:22:30Z`-`22:24:31Z`). After ten repair generations and a continuous claim
since `20:41:17Z`, capture, training, holdout, and endpoint evidence remain
unstarted.

**Change and expected effect.** Added one execution-path rule to the shared
`$researcher` skill: bind mutable remote output roots to the repair generation,
or atomically archive the prior root before invoking a consumer that requires
exclusive directory creation; continue reusing resident checkpoints, images,
packets, and immutable caches. A recurring existing-directory failure must be
repaired before stale observer or mechanism artifacts are interpreted.
Expected effect: repair 10 can patch and rerun the invalidated capture on the
same H200 without another directory collision or cold setup, shortening the
path to the first nonzero mapped-row manifest. This adds no static validation,
project, scientific replay, provider mutation, or teardown and does not touch
the active owner or project harness.

## 2026-07-26T22:47Z — preserve dynamic observer diagnostics in repair handoffs

**GPU safety audit.** One grouped authenticated Nebius listing returned only
RUNNING instance `computeinstance-e00b9qw8d6qd7wrjj1` and READY disk
`computedisk-e00y3ezqfpp4fdnz7h`, exactly matching the sole non-retired H200
inventory record. Claim owner PID `2056931` matches start ticks `121449519`,
heartbeats remain current, and the controller-host user watchdog
`gemma4-causal-head-h200-20260726t2032z-watchdog.service` (PID `2052617`) is
active/running through `2026-07-27T01:32:34.490529Z`. There is no provider-only
or missing resource, stale claim, passed deadline, idle bench, or drain action.

**Objective bottleneck and evidence.** Repair 11 corrected the mutable-root
defect: generation 12 archived the prior roots, crossed its in-program science
marker, completed all 32 exact requests, and preserved request outputs.
However, the current guest root also contains the specific dynamic diagnostic
`OBSERVER_ERROR.json` with `RuntimeError:aux_tap_contract` and zero mapped
rows, while repair 12 was published only as
`RuntimeError:capture_terminal_or_manifest_retrieval_failed`. The researcher
therefore had to inspect the guest again to recover evidence the owner already
had. After a continuous claim since `20:41:17Z` and twelve repair generations,
decision-bearing mapped capture, training, holdout, and endpoint evidence
remain unstarted; losing the root cause at each repair boundary directly
extends that serial path.

**Change and expected effect.** Added one dynamic-evidence rule to the shared
`$researcher` skill: when an observer artifact explains an absent terminal,
retrieve and hash-bind it before repair-ready rather than collapsing it to a
generic retrieval failure. Expected effect: future capture owners hand the next
turn the exact on-guest failure immediately, removing a redundant SSH
localization pass and shortening same-claim repair latency without adding a
validator, project, scientific replay, provider mutation, or interference with
the active owner.

## 2026-07-26T23:24Z — exercise repaired consumers on retained artifacts

**GPU safety audit.** One grouped authenticated Nebius listing returned only
RUNNING instance `computeinstance-e00b9qw8d6qd7wrjj1` and READY disk
`computedisk-e00y3ezqfpp4fdnz7h`, exactly matching the sole non-retired H200
inventory record. Claim owner PID `2056931` still matches start ticks
`121449519`; 215 heartbeats span `20:42:02Z` through `23:22:46Z`, and the
controller-host user watchdog
`gemma4-causal-head-h200-20260726t2032z-watchdog.service` (PID `2052617`) is
active/running through `2026-07-27T01:32:34.490529Z`. There is no
provider-only or missing non-retired resource, stale claim, passed deadline,
idle bench, or drain action.

**Objective bottleneck and evidence.** Warm-bench recovery is preserving the
decision-bearing producer: generation 16 retrieved the same 90 hashed chunks,
11,544 capture rows, and 32 request mappings without request replay. Repair 16
then materialized the omitted immutable train/holdout inputs and remained
consumer-only. Repair 17 retrieved the next full traceback and all duplicate
row provenance, finding 56 duplicates confined to offset-zero prefill taps,
but verified its amendment only with local spot assertions before publishing
the request. Generation 18 consequently spent `120.1 s` reconciling the
unchanged checkpoint (`23:21:31Z` to `23:23:31Z`) and then failed before
optimization on `duplicate_capture_row_unresolved:(27, 0)`. Repair 18 is
available under the same owner and claim; capture, split, training, holdout,
and endpoint identities have not been replayed or changed.

**Change and expected effect.** Added one repair-loop rule to the shared
`$researcher` skill: before publishing a repair request, run the amended
invalidated boundary once over the complete retained resident artifact set
when it is GPU-free and does not replay a producer or consume science; bind
that dynamic result to the repair artifact. CUDA-only boundaries use the first
tiny retained-owner call instead. Expected effect: a consumer patch such as
repair 17 runs its real `load_capture` boundary over all 90 resident chunks
before paying another immutable-checkpoint reconciliation, catching incomplete
discriminators while preserving the same mutable H200 session. This adds no
static validation ladder, project, scientific replay, provider mutation, or
interference with repair 18.

## 2026-07-26T23:36Z — dispatch narrow repair scopes before settled setup

**GPU safety audit.** One grouped authenticated Nebius listing returned only
RUNNING instance `computeinstance-e00b9qw8d6qd7wrjj1` and READY disk
`computedisk-e00y3ezqfpp4fdnz7h`, exactly matching the sole non-retired H200
inventory record. The continuous claim released normally at `23:35:01Z` into
`available`; there is no stale claim or owner requirement on the unclaimed
bench. Its controller-host user watchdog
`gemma4-causal-head-h200-20260726t2032z-watchdog.service` (PID `2052617`) is
active/running through `2026-07-27T01:32:34.490529Z`. Idle time was seconds at
audit, and the source-ready `gemma4_adaptive_retrieval_vocab_head` explicitly
requests a compatible released H200, so immediate reuse is preferred over
drain while the director selects the next lane. There is no provider-only or
missing resource, passed deadline, unsafe state, or drain action.

**Objective bottleneck and evidence.** Generation 19 completed the exact
request-disjoint holdout and closed this causal-head realization scientifically:
depths 4/8/12/16 all measured `1.001953125` mean accepted target tokens versus
the `16.054` campaign gate, with zero full-prefix fraction. Repair 19 correctly
classified this as terminal adoption and its patched consumer exited without
CUDA or retraining. The retained owner nevertheless has no retry-scope
dispatcher: every repair enters the same packet, checkpoint-stage, and training
command path. Consequently the adoption-only generation wrote its command
graph at `23:32:52Z`, finished rehashing the unchanged checkpoint at
`23:34:55Z` (`122.5 s`), then adopted and retrieved the existing result by
`23:35:01Z`. This spent about `$0.084` and two minutes on settled setup after
the scientific result already existed.

**Change and expected effect.** Added one owner-design rule to the shared
`$researcher` skill: dispatch a hash-bound retry scope before broad generation
setup; retrieval-only, terminal-adoption, and later-consumer paths must bypass
unrelated checkpoint reconciliation, model loading, producer launch, and
settled stages, and unsupported scopes fail closed instead of falling through.
Expected effect: future terminal adoption reaches verification, retrieval, and
release in seconds while preserving exact artifacts, eliminating the measured
two-minute reconciliation without adding static validation, a project,
scientific replay, provider mutation, or interference with the director's next
H200 reuse decision.

## 2026-07-26T23:44Z — prepare the selected warm successor before release

**GPU safety audit.** One grouped authenticated Nebius listing returned only
RUNNING instance `computeinstance-e00b9qw8d6qd7wrjj1` and READY disk
`computedisk-e00y3ezqfpp4fdnz7h`, exactly matching the sole non-retired H200
inventory record. The bench is unclaimed and available, with no stale claim or
required experiment owner. Its controller-host user watchdog
`gemma4-causal-head-h200-20260726t2032z-watchdog.service` (PID `2052617`) is
active/running through `2026-07-27T01:32:34.490529Z`. There is no provider-only
or missing non-retired resource, passed deadline, unsafe state, or drain
action. Immediate reuse remains preferable because a compatible successor is
now active and the retained state avoids a cold lifecycle.

**Objective bottleneck and evidence.** The causal-head cycle closed with a
mechanism-negative result, not an integration failure: all four depths measured
`1.001953125` accepted target tokens against the `16.054` gate. The independent
retrieval-head lane had already persisted its exact self-contained c32 capture
packet at `22:40:15Z` and was explicitly queued behind the H200. However, its
routine durable owner entrypoint was left unimplemented until after the
predecessor released at `23:35:01Z`. The director admitted that local work at
`23:40Z`, and the harness started the execution researcher at `23:42:18Z`.
Thus a selected source-ready successor incurred at least `436.8 s` of paid H200
idle time, about `$0.298` at `$2.4597222/hour`, before its zero-GPU preparation
even began. This did not tear down resident state or cold-restart after a
recoverable error, but it unnecessarily delayed the next direct experiment.

**Change and expected effect.** Added one narrow warm-handoff rule to the
shared `$research-director` skill: once a compatible successor is selected,
finish its routine zero-GPU launcher/owner implementation in the same project
while the predecessor still owns the bench; at release, make it promptly
claimable or drain only when reuse cannot fit the measured break-even. Expected
effect: future source-ready successors enter the retained mutable bench without
post-release plumbing delay, saving the measured handoff idle interval without
adding static validation, a readiness project, provider action, scientific
replay, or interference with the active retrieval-head preparation.

## 2026-07-26T23:51Z — remove full-path rehearsal from warm claims

**GPU safety audit.** One grouped authenticated Nebius listing returned only
RUNNING instance `computeinstance-e00b9qw8d6qd7wrjj1` and READY disk
`computedisk-e00y3ezqfpp4fdnz7h`, exactly matching the sole non-retired H200
record. The bench remains unclaimed and available, and its controller-host user
watchdog `gemma4-causal-head-h200-20260726t2032z-watchdog.service` (PID
`2052617`) is active/running through
`2026-07-27T01:32:34.490529Z`. There is no provider-only or missing resource,
stale claim, passed deadline, lost lifecycle process, unsafe state, or drain
action. The inventory's resident-content description is stale—it still names
the completed causal-head owner and an unconsumed cycle—so the director should
refresh it when the successor claims, but the authoritative status, claim,
resource IDs, and lifecycle remain safe. Reuse is still preferable to drain
because the admitted compatible successor is active and the cold setup already
cost substantially more than this handoff.

**Objective bottleneck and evidence.** By `23:49:52Z`, the released H200 had
been idle `890.5 s`, costing about `$0.609`, with no GPU event after the
`23:35:01Z` release. The retrieval researcher materialized its owner at
`23:44:42Z`, but the director-required full-path offline exercise then streamed
SHA-256 over the existing `62.6 GB` checkpoint inventory. After `49.207 s`, it
failed before claim because `inventory_bench` iterated the current keyed
`gpus.json` bench mapping as strings and called `bench.get`. A second direct
`validate_identities` invocation repeated the heavy checkpoint read and reached
the same schema error. Director turns at `23:46Z` and `23:47Z` kept the claim
closed on the absent exercise terminal. This is static validation of unchanged
bytes and shared lifecycle plumbing, not evidence about the retrieval-head
mechanism or the campaign's `$0.11/M` objective.

**Change and expected effect.** Narrowed the shared `$research-director` skill:
a selected warm exploratory successor may bind source and compact manifests,
but must not rehash unchanged checkpoint shards, simulate the complete detached
lifecycle, or exercise the full scientific command before claim. Reuse prior
storage-identity verification and shared atomic claim/release behavior; expose
and repair ordinary launcher or inventory-schema defects on the retained
mutable claim. Expected effect: the next warm handoff reaches exact target
execution instead of paying repeated 50-second controller scans and extended
H200 idle time, without adding a project, weakening scientific identities,
replaying a consumed arm, touching the active retrieval files, or performing
provider cleanup.

## 2026-07-27T00:08Z — reuse verified checkpoints across project roots

**GPU safety audit.** One grouped authenticated Nebius listing returned only
RUNNING instance `computeinstance-e00b9qw8d6qd7wrjj1` and READY disk
`computedisk-e00y3ezqfpp4fdnz7h`, exactly matching the sole non-retired H200
inventory record. The bench is claimed by
`gemma4_adaptive_retrieval_vocab_head`; its detached controller owner PID
`2199890` is live and heartbeating, and controller-host user watchdog
`gemma4-causal-head-h200-20260726t2032z-watchdog.service` (PID `2052617`) is
active/running through `2026-07-27T01:32:34.490529Z`. The claim lease and
lifecycle deadline have not passed. There is no provider-only or missing
non-retired resource, stale claim, lost lifecycle process, unsafe state, or
drain action. The active claim remains the justified use of the retained bench.

**Objective bottleneck and evidence.** The retrieval successor is healthy but
is retransferring the exact checkpoint already verified on the same retained
bench. Its owner is running `scp` for the first
`49,784,788,364`-byte shard from the controller into the project-specific
`/home/glmrunner/gemma4-adaptive-retrieval-vocab-head/.../checkpoint` path.
The predecessor's final stage terminal records the identical eight-file
checkpoint resident at `/home/glmrunner/causal-offset-head/checkpoint`; a
normalized comparison of names, byte counts, and SHA-256 digests against the
successor manifest is byte-identical, with manifest digest
`864f24f4631315cd17cc8a3ff1ea57b2725d2a24f29c45778b101f16b5228a4f`.
The predecessor reverified those files immediately before its `23:35:01Z`
release. Prior timings show copying and verifying the two model shards consumed
more than 20 minutes. Repeating that work inside the successor's 45-minute
claim materially reduces time available for its one exact eager c32 capture,
which is the next evidence-bearing step toward the campaign latency target.

**Change and expected effect.** Added one narrow rule to the shared
`$researcher` skill: immutable checkpoints are bench-owned across project
handoffs; compare manifests before transfer, bind the verified absolute remote
path read-only (or link/reflink it), copy only missing or mismatched files, and
persist the resident path plus manifest digest in inventory. Expected effect:
future retained-bench handoffs avoid the measured duplicate 62.6 GB transfer
and reserve roughly 20 minutes for direct target experiments. The current
retrieval owner and transfer were left untouched, so this change does not
disrupt the active claim, add static validation or projects, restart cold, or
perform provider cleanup.

## 2026-07-27T00:34Z — replace superseded structured evidence on recovery

**GPU safety audit.** One grouped authenticated Nebius listing returned only
RUNNING instance `computeinstance-e00b9qw8d6qd7wrjj1` and READY disk
`computedisk-e00y3ezqfpp4fdnz7h`, exactly matching the sole non-retired H200
record. The retrieval claim released safely to `maintenance` at `00:30:31Z`;
its PID-owned controller exited as expected, while controller-host user
watchdog `gemma4-causal-head-h200-20260726t2032z-watchdog.service` (PID
`2052617`) remains active/running through `01:32:34Z`. There is no stale claim,
provider-only or missing resource, passed deadline, lost lifecycle watchdog,
unsafe state, or drain action. Retention is presently justified: the director
is actively selecting the next disposition, and the bench has been unclaimed
for only minutes versus more than 20 minutes of measured cold checkpoint
staging. Prefer prompt compatible reuse; otherwise the director should drain
when that break-even window closes. The inventory's descriptive contents still
name the exited owner and pending terminalization, so the director should
refresh the exact resident server/container state before reuse or drain.

**Objective bottleneck and evidence.** Recovery produced valid new evidence:
`STATUS.json.result` is `exact_diverse_c32_capture_complete_recovered`, and its
summary records 1,536 finite width-5,376 rows, all 32 request mappings, and
1,536 unique hidden rows. The same file's structured `evidence`, however,
still describes the superseded degenerate capture (`capture_rows: 384`,
`unique_hidden_rows: 1`) and says `gpu_claimed: false`,
`capture_producer_run: false`, and
`current_capture_scientific_sample_consumed: false`. The next retrieval-head
decision depends specifically on the recovered diverse capture, so this
contradiction can cause a downstream worker or director to reuse the rejected
sample, falsely reject the new sample, or replay an already consumed producer.

**Change and expected effect.** Added one narrow `$researcher` rule: when a
recovered terminal supersedes prior evidence, atomically replace every
decision-bearing structured field and boolean from that accepted terminal,
keeping historical values only under explicit `prior_*` state or terminal
references. Expected effect: downstream retrieval scoring binds the canonical
1,536-row capture without ambiguity or replay. This adds no validation stage or
project, changes no scientific value, and does not touch the released bench,
provider resources, or the active director turn.

## 2026-07-27T00:45Z — make local experiment continuations durable

**GPU safety audit.** One grouped authenticated Nebius listing returned only
RUNNING instance `computeinstance-e00b9qw8d6qd7wrjj1` and READY disk
`computedisk-e00y3ezqfpp4fdnz7h`, exactly matching the sole non-retired H200
inventory record. The bench is unclaimed in `maintenance`; controller-host user
watchdog `gemma4-causal-head-h200-20260726t2032z-watchdog.service` (PID
`2052617`) is active/running through `2026-07-27T01:32:34.490529Z`. There is no
provider-only or missing resource, stale claim, passed deadline, lost lifecycle
owner/watchdog, or unsafe state, so no drain-state mutation is warranted. The
H200 has been idle since `00:30:31Z`. Immediate reuse remains justified only if
the same-project offline gate is relaunched durably and completes inside the
measured greater-than-20-minute cold-staging break-even. Otherwise the director
should drain exact instance `computeinstance-e00b9qw8d6qd7wrjj1` and disk
`computedisk-e00y3ezqfpp4fdnz7h`; provider cleanup and inventory retirement
remain director-owned.

**Objective bottleneck and evidence.** The admitted zero-GPU diverse-capture
falsifier is the decision gate for spending more H200 time on retrieval. The
researcher first lost PID `2218433`, then launched replacement child PID
`2220656`; at `00:42:57Z` it returned success while reporting that child as a
durable local session. By `00:45:21Z` the process no longer existed. Neither
`ADAPTIVE_RETRIEVAL_DIVERSE_C32_OFFLINE_TERMINAL.json` nor its `.part` file
exists, and `STATUS.json` has no `active_session`, PID, start ticks, deadline,
or artifact root. The harness therefore recorded a successful researcher turn
while the actual experiment silently ended, leaving the scientific gate
pending and the paid maintenance bench warm. This is lost experiment ownership,
not negative retrieval evidence or a reason for another project or static gate.

**Change and expected effect.** Added one narrow `$researcher` rule: a
background child remains turn-owned; unfinished local work must stay attached
through its typed terminal or use the controller-host durable-owner mechanism,
be verified once after the launching shell exits, and atomically populate
`STATUS.json.active_session`. A researcher may not report a durable handoff
from an unrecorded child. Expected effect: bounded CPU falsifiers survive turn
return or fail visibly, so their result can promptly select same-bench reuse or
drain instead of silently consuming the warm-state break-even window. This
does not alter the retrieval hypothesis, replay capture, claim the GPU, add
validation or a project, disrupt an active experiment, or perform provider
cleanup.

## 2026-07-27T01:04Z — preserve the true idle interval across ready refreshes

**GPU safety audit.** One grouped authenticated Nebius listing returned only
RUNNING instance `computeinstance-e00b9qw8d6qd7wrjj1` and READY disk
`computedisk-e00y3ezqfpp4fdnz7h`, exactly matching the sole non-retired H200
inventory record. The bench is unclaimed and available; controller-host user
watchdog `gemma4-causal-head-h200-20260726t2032z-watchdog.service` (PID
`2052617`) is active/running through `2026-07-27T01:32:34.490529Z`. There is no
provider-only or missing resource, stale claim, passed deadline, lost lifecycle
owner/watchdog, or unsafe state, so no drain-state mutation is warranted.
Compatible project `gemma4_exact_block_bound_vocab_head` has a durable `$2.00`
reservation and explicit warm-H200 claim authority through `01:10Z`; retain
through that cutoff. If it does not claim by then, the director should drain
exact instance `computeinstance-e00b9qw8d6qd7wrjj1` and disk
`computedisk-e00y3ezqfpp4fdnz7h`. Provider cleanup and inventory retirement
remain director-owned.

**Objective bottleneck and evidence.** The H200 released at
`2026-07-27T00:52:11.532262Z` and has had no intervening claim. Nevertheless,
three `bench_ready` calls at `00:58:12Z`, `00:58:22Z`, and `01:02:09Z` each
reset `idle_since`; inventory therefore reports `01:02:09.855434Z` rather than
the continuous idle interval beginning at release. The calls refreshed
resident contents and successor bindings, but did not change resource
occupancy. Resetting the clock masks paid idle cost and can make an already
expired warm-state break-even window look fresh, delaying a reuse-or-drain
decision while the campaign is still trying to reach the locked
`0.500119281574996 s/request` objective.

**Change and expected effect.** Made shared `GpuPool.ready` preserve the
existing `idle_since` when the bench is already available, while still starting
a new interval for a real maintenance-to-available transition. Content,
`updated_at`, and `bench_ready` events continue to refresh normally. Added a
focused regression test proving that a later ready/content refresh retains the
original idle timestamp. Expected effect: supervisors and directors compare
actual idle exposure against measured cold setup cost and make timely warm
reuse or drain decisions instead of extending retention through bookkeeping.
This changes no scientific contract, claim, provider resource, active
experiment, or portfolio admission.

## 2026-07-27T01:18Z — make privileged-container retrieval non-replaying

**GPU safety audit.** One grouped authenticated Nebius listing returned only
RUNNING instance `computeinstance-e00b9qw8d6qd7wrjj1` and READY disk
`computedisk-e00y3ezqfpp4fdnz7h`, exactly matching the sole non-retired H200
inventory record. Bench `h200-causal-head-e00b9qw8d6qd7wrjj1` is continuously
claimed by `gemma4_exact_block_bound_vocab_head` from
`2026-07-27T01:10:22.676483Z`; its PID-owned controller is live with matching
start ticks and heartbeats every approximately 30 seconds. Controller-host
watchdog `gemma4-causal-head-h200-20260726t2032z-watchdog.service` (PID
`2052617`) is active/running through `2026-07-27T01:32:34.490529Z`. The claim
began 22.7 seconds after the nominal `01:10Z` cutoff, but the director explicitly
accepted that bounded deviation because the continuous claim, retrieval, and
release still fit the `01:25:22Z` repair deadline and `01:29Z` release
deadline. There is no provider-only or missing resource, stale claim, passed
deadline, lost lifecycle owner/watchdog, unsafe state, or drain action.

**Objective bottleneck and evidence.** The same-claim repair policy worked:
attempt 0 failed before science on a localized broadcast defect, and attempt 1
ran without teardown, reclaim, capture replay, or checkpoint transfer. Attempt
1 then completed the scientific program and printed its decision-bearing
result: `0.0082219444` block-pruning fraction, `9.943840 ms` candidate median
versus `0.860144 ms` dense, and non-exact output, closing this exact-bound
mechanism. However, all four retrievals failed with `scp: Permission denied`
because the privileged Docker worker created root-owned terminal and marker
files in the bind-mounted output tree. The generic owner consequently emitted
`component_terminal_absent` and a retry scope that would rerun the already
consumed scientific program. The director has correctly frozen attempt 1 and
admitted retrieval-only recovery under the retained claim.

**Change and expected effect.** Added one narrow rule to the shared
`$researcher` skill: privileged containers whose bind-mounted outputs will be
retrieved by an unprivileged SSH user must produce or normalize a readable
output tree in the execution path and verify the compact terminal before
retrieval. A successful worker or captured decision-bearing stdout plus failed
retrieval now requires retrieval-only or terminal-adoption repair, never a
generic consumer retry. Expected effect: future owners recover immutable
terminals without replaying CUDA science, avoid an unnecessary second sample,
and shorten retained-claim idle time after completed measurements. Skill
validation and the repository DevEx check pass. This future-facing change does
not touch the active owner, submit its repair handshake, mutate provider
resources, or alter the scientific portfolio.

## 2026-07-27T01:32Z — decide the warm lifecycle before empty-portfolio synthesis

**GPU safety audit.** One grouped authenticated Nebius listing returned only
RUNNING instance `computeinstance-e00b9qw8d6qd7wrjj1` and READY disk
`computedisk-e00y3ezqfpp4fdnz7h`, exactly matching the sole non-retired H200
inventory record. The prior exact-block-bound claim released safely at
`01:20:18.549926Z`; the bench is unclaimed and available with no live server
or GPU process. Controller-host user watchdog
`gemma4-causal-head-h200-20260726t2032z-watchdog.service` (PID `2052617`) was
active/running through `2026-07-27T01:32:34.490529Z`. There was no stale claim,
provider-only or missing resource, lost watchdog, passed deadline, or unsafe
state at the grouped audit snapshot, so no drain-state mutation was warranted.
The bench had nevertheless exhausted its useful idle-retention window. At
`01:32:48Z`, a local commit-time reconciliation found the lifecycle deadline
passed while the unclaimed inventory record was still `available`; the
supervisor therefore marked bench
`h200-causal-head-e00b9qw8d6qd7wrjj1` `draining` at `01:33:00Z`. The director
must reconcile and clean exact instance
`computeinstance-e00b9qw8d6qd7wrjj1` and disk
`computedisk-e00y3ezqfpp4fdnz7h`, then retire the record only after cleanup
verification. Provider cleanup and inventory retirement remain director-owned.

**Objective bottleneck and evidence.** The campaign is open with spend
remaining, but every project status is terminal, closed, completed, blocked,
or paused. The director started at `01:21:22Z` promising one warm-H200 direct
experiment and one independent zero-GPU lane. By `01:30Z` neither project nor
claim binding existed. Its trace had spent the interval on more than twenty
historical searches, repeated price reads, the complete kernel skill and
playbook, and further closed-line reconciliation. Meanwhile the H200 idled for
almost ten minutes at `$2.4597222/hour`; less than three minutes remained in
the lifecycle, which could not fit implementation, an exact consumer, terminal
persistence, and safe release. This is an empty-portfolio admission-latency
failure, not evidence that the model-specific opportunity space is exhausted.

**Change and expected effect.** Added one narrow empty-portfolio fast path to
the shared `$research-director` skill. When a reusable bench has finite
lifetime, the director must first compare the remaining window with measured
setup/execution/release time, persist an already-runnable successor before
optional synthesis when it fits, or make the lifecycle decision immediately
and admit an independent zero-GPU lane from the current phase and latest
terminal when it does not. Expected effect: future director turns convert
warm state into objective-relevant execution or release it promptly, while
restoring research concurrency before lengthy historical synthesis. Skill
validation and repository DevEx checks pass. The change is future-facing and
does not interrupt the active director, create a scientific project, claim the
bench, or perform provider cleanup.

## 2026-07-27T01:54Z — register created benches before connection probes

**GPU safety audit.** One grouped authenticated Nebius listing found newly
created H200 instance `computeinstance-e00dam5825ffjyxd8b` in `STARTING` state
while `runtime/gpus.json` had no non-retired record. The in-flight director
create then completed with exact managed disk
`computedisk-e00syfz2dr5znq5kg7`, instance state `RUNNING`, and controller-host
user watchdog
`gemma4-hybrid-55l5g-h200-20260727t0149z-watchdog.service` active/running as
PID `2258131` through `2026-07-27T02:39:55.411237Z`. Its first strict SSH probe
timed out, so the director paused the hybrid claimant and deliberately left
the protected provider resources unregistered for a later wake. There is no
claim or scientific invocation, and the watchdog makes this bounded rather
than immediately unsafe, but the live instance and disk are absent from the
shared inventory. The director must register them non-claimable before any
further connection/setup work, then mark the bench ready only after identity
verification. Provider cleanup and retirement remain director-owned.

**Bottleneck, change, and expected effect.** The shared GPU pool previously
forced every new registration directly to `available`, leaving the director a
bad choice after create: expose an unverified host to claims or leave paid
resources untracked. Added backward-compatible
`gpu_pool register --condition maintenance`, with maintenance registrations
having no idle/claim eligibility, and updated `$research-director` to treat
provider create, watchdog start, and maintenance registration as one safety
transaction before SSH or setup. Expected effect: provider resources become
durably attributable and deadline-visible immediately, while failed boot/SSH
probes remain safely non-claimable and can be repaired without cleanup or a
cold restart. The GPU-pool test suite (17 tests), skill validation, and
repository DevEx checks pass. This change did not query the provider again,
claim the H200, alter the scientific endpoint, clean resources, or interrupt
the active entropy lane.

## 2026-07-27T02:55Z — fence the ownerless retained H200 without a cold restart

**GPU safety audit.** One grouped authenticated Nebius listing at
`02:54:20Z` returned RUNNING instance
`computeinstance-e00dam5825ffjyxd8b` and READY managed disk
`computedisk-e00syfz2dr5znq5kg7`, exactly matching claimed bench
`h200-hybrid-55l5g-e00dam5825ffjyxd8b`. Its claim heartbeat stopped at
`02:49:45Z`; recorded PID owner `2279528` no longer exists. The owner traceback
shows a local stale retrieved-terminal path after hash-verified checkpoint and
image staging, before SSH, server launch, CUDA, requests, or scientific
sampling. A concurrent director reconciliation replaced the controller-host
user watchdog with
`gemma4-hybrid-55l5g-h200-20260727t0319z-watchdog.service` (PID `2294019`);
the replacement is active/running through `03:19Z`. The supervisor marked the
claimed bench `drain_after_release=true`. This fenced future claims without
releasing the original claim, removing resident inputs, cleaning provider
resources, or retiring the inventory record.

**Bottleneck and expected effect.** The real loss was a recoverable,
project-local runtime placeholder and stale artifact-root binding discovered
only after roughly 22 minutes of cold staging. The director has selected a
bounded same-claim adoption and in-place runtime repair within the existing
`$10.00` authority, which preserves the resident checkpoint and image instead
of paying another cold start. No additional static validation or shared-tool
change is warranted from this localized failure. The drain fence makes the
bench unavailable to unrelated work if the repair terminates, while retaining
the mutable claimed session for the director-authorized patch and rerun.
Provider cleanup and inventory retirement remain director-owned for the exact
instance and disk IDs above.

## 2026-07-27T03:14Z — stock server death is hidden by the readiness wait

**GPU safety audit.** One grouped authenticated Nebius listing at
`03:10:53Z` returned RUNNING instance
`computeinstance-e00dam5825ffjyxd8b` and READY managed disk
`computedisk-e00syfz2dr5znq5kg7`, exactly matching claimed bench
`h200-hybrid-55l5g-e00dam5825ffjyxd8b` and its original
`02:27:43.881452Z` claim generation. Corrected adoption owner PID `2302482`
matches start ticks `123764240`, its heartbeat was current through
`03:12:05Z`, and controller-host user watchdog
`gemma4-hybrid-55l5g-h200-20260727t031945z-watchdog.service` is
active/running as PID `2299482` through `03:19:45Z`. There is no provider-only
or missing resource, stale claim, passed deadline, lost lifecycle owner, or
unsafe guest. The existing `drain_after_release=true` fence remains
appropriate; do not clean or retire provider resources here.

**Objective bottleneck and evidence.** A single read-only guest snapshot at
`03:12:39Z` found no running experiment container, `0 MiB` GPU memory and
`0%` utilization. The exited `hybrid-55l5g-stock` log shows that SGLang failed
before model load, CUDA allocation, endpoint requests, or science:
`ValueError: Unrecognized model in /models/target. Should have a model_type
key in its config.json.` The durable staging marker records only the two
62,546,338,248-byte safetensor shards; it does not record model configuration
or tokenizer files. Despite the already-terminal container, child PID
`2302501` remains in the runtime's fixed four-second health loop, whose
`420`-second readiness deadline is treated as a mandatory wait. This hides a
localized resident-path/input integration error while the harness defers the
researcher as `durable_session_active`, consuming the final retained-claim
margin without objective-relevant GPU work. The endpoint sample remains
unconsumed and this is not evidence about the 55-local/5-global mechanism.

**Disposition and expected effect.** Do not interrupt the bounded owner or
cold-start another bench. If a director-authorized continuation still fits,
it should preserve the exact instance, disk, checkpoint shards, image, claim
timestamp, and scientific pair, repair only the missing pinned model-root
inputs/path, and rerun the unstarted stock arm under retained state; otherwise
let the existing deadline and drain fence hand the exact resource IDs above
back to the director. No new skill, validator, project, or shared-tool change
is warranted: the shared `$researcher` skill already says that readiness is an
upper bound, requires concurrent child/container liveness, and routes fatal
startup tracebacks through the existing `repair-handshake`. Following that
execution-path rule would surface this failure in seconds, wake an in-place
repair while useful lease margin remains, and avoid both the seven-minute
idle wait and another checkpoint cold stage. Another static validation gate
would not address the observed failure.

## 2026-07-27T03:24Z — make server readiness observe container death

**GPU safety audit.** One grouped authenticated Nebius listing returned no
instances and no disks. This matches `runtime/gpus.json`, which has no
non-retired benches after cleanup verification at
`2026-07-27T03:18:53.017113Z`. The former hybrid bench
`h200-hybrid-55l5g-e00dam5825ffjyxd8b` released its original claim at
`03:17:05.502771Z` and retired at `03:18:53.021665Z`; exact provider resources
`computeinstance-e00dam5825ffjyxd8b` and
`computedisk-e00syfz2dr5znq5kg7` are absent from both provider and live
inventory. Provider exposure was `5,337.605876` seconds and
`$3.646952130013235`. There is no provider-only or missing resource, live
claim, stale heartbeat, lifecycle owner/watchdog to resolve, passed deadline,
or idle paid bench. No drain, provider cleanup, or inventory mutation is
warranted.

**Objective bottleneck and timing evidence.** The endpoint pair is correctly
typed `pre_science_model_root_integration_terminal_budget_exhausted`: zero
stock requests, zero candidate requests, no model load, and no CUDA
invocation. The claim nevertheless lasted from `02:27:43.881452Z` to
`03:17:05.502771Z`. The lab did reuse that claim for in-place owner repairs
instead of tearing down and restaging, but the final stock container exited
immediately on the incomplete mounted model root while the child continued a
fixed `420`-second health wait. Thus the last recoverable integration signal
was delayed until almost all lease margin was gone. This feedback latency,
not the unmeasured 55-local/5-global mechanism, is the actionable process
bottleneck. After cleanup the open campaign briefly had no runnable project;
the harness's normal fallback dispatched a director at `03:21:38.469297Z`, so
the supervisor did not create a project or issue a redundant wake.

**Change and expected effect.** Updated the project endpoint harness
`run_h200_55l5g_endpoint_runtime.py` so every failed health probe also inspects
the launched container. An objectively stopped container now writes
`<arm>.startup-failure.json` with `science_consumed=false`, the Docker state,
and a bounded log tail, then exits the readiness loop immediately. Transient
SSH/inspect failures do not prove death and therefore do not trigger the fast
path. The harness compiles successfully. Expected effect: the same missing
model-root failure becomes a typed repair input within one probe cycle instead
of after the full seven-minute upper bound, leaving the claimed mutable bench
and resident state available for director-authorized patch-and-rerun. This is
dynamic execution liveness, not another static validator, and it does not
change the scientific intervention, replay an experiment, provision hardware,
or disturb the active director turn.

## 2026-07-27T06:10Z — preserve repair relaunches after the initial start fence

**GPU safety audit.** One grouped authenticated Nebius listing at
`06:08:23Z` showed instance `computeinstance-e00wyscpm4cm4k42jg` and managed
disk `computedisk-e00b5dnbxf2bsmbm2d` both deleting, exactly matching the
registered draining L40S bench. Its controller-host user watchdog was still
the recorded active PID `2402841`; the lifecycle deadline
`06:35:53.449330Z` had not passed and there was no claim. The director then
verified both provider resources absent, stopped the watchdog, and retired the
bench at `06:08:47Z`. There is no remaining provider-only resource, live
inventory record, stale claim, ownerless paid bench, or lifecycle action for
the supervisor. Provider cleanup and retirement remained director-owned.

**Objective bottleneck and evidence.** The fixed-`0.953` L40S exact-c32 arm
never reached a claim, checkpoint staging, image pull, CUDA, endpoint request,
or scientific submission. The initial owner launched at `06:04:18Z`, before
its `06:04:30Z` start fence. It then exposed two ordinary pool-integration
defects: the first claim omitted the required `nvidia-l40s` selector at
`06:05:28Z`; the second used a bare model selector against the inventory's
revision-qualified model field at `06:07:31Z`. Both diagnostics record
`sample_consumed=false`, and the researcher had already removed the brittle
model selector from the director-bound explicit-bench claim. Nevertheless the
bench was drained at `06:07:36Z` and provider deletion began at `06:07:42Z`,
with about 28 minutes left before the watchdog. The cleanup decision treated
the elapsed initial start fence as a repair-relaunch deadline, despite the
timely first start and the still-unconsumed scientific arm. This discarded the
only paid L40S chance to test whether the positive local-KV4 representation
could reach the campaign's `0.500119281574996 s/request` target.

**Change and expected effect.** Narrowly amended `$research-director`: a
timely first owner launch consumes the initial start fence, while a recoverable
pre-science replacement is judged against the remaining absolute release and
watchdog windows. The director should shorten the replacement's relative
deadline when the measured repair and execution still fit, rather than drain
only because the original start-by time elapsed. This does not add a validator,
project, provider action, or scientific freedom. Expected effect: selector,
launcher, and similar runtime defects can be patched and rerun on the same
mutable paid bench, preserving boot/identity/setup time and converting the
next bounded L40S lifecycle into objective-relevant GPU evidence instead of
another pre-science terminal.

## 2026-07-27T07:05Z — make retained image reuse precede a repair pull

**GPU safety audit.** One grouped authenticated Nebius listing at `07:03Z`
returned RUNNING instance `computeinstance-e00d0a3gmts94zmm63` and READY
attached disk `computedisk-e00h6mymz45dxg6c62`, exactly matching claimed bench
`l40s-kv4-sm89-computeinstance-e00d0a3gmts94zmm63`; there is no provider-only
or missing inventory resource. Controller-host user watchdog
`gemma4-kv4-sm89-20260727t064222z-watchdog.service` is active/running as PID
`2431263` in its recorded control group through `07:09:22Z`. PID owner
`2436801` is live with matching start ticks `125123219`, and the claim
heartbeat was current at `07:04:01Z`. No claim, owner, or deadline safety
mismatch existed at the audit snapshot. During the review the director
requested drain at `07:05:22Z`; the owner released the claim at `07:06:06Z`
as `absolute_repair_deadline`, and the exact registered bench is now
`draining` with `drain_after_release=true`. The owner is exited, the
controller watchdog remains active, and provider cleanup plus inventory
retirement remain director-owned for the exact instance and disk IDs above.

**Objective bottleneck and evidence.** The exact checkpoint-free SM89
component still has no CUDA invocation or scientific sample. The cold pinned
image pull began inside the retained owner and timed out after `521` seconds
at `07:02:34Z`, consuming nearly all of the 840-second owner window. The
hash-bound `g1` repair correctly preserved the same claim, packet, and guest
and resumed at `07:03:46Z`. After its successful preflight, however, the
`prepare` state called the combined pull-and-identity function again. Its
300-second terminal reserve made the computed pull timeout zero, producing
`OWNER_ERROR_g2.json` at `07:03:57Z` as `TimeoutExpired(..., 0)` instead of
checking whether the first pull had left the immutable image resident. This
is a warm-repair harness defect, not evidence about KV4, E5M2, SM89, or the
campaign's `0.500119281574996 s/request` target. The independent tiered-KV
terminal remains objective-relevant but explicitly requires this later SM89
component; adding projects or static validation would not answer it.

**Change and expected effect.** Updated the project owner so `pull_image`
first performs a bounded digest-and-runtime-revision inspection and returns
immediately when the exact immutable image is already resident. It attempts a
network pull only when that probe fails and at least 60 seconds of the
pull-specific budget remain; exhausted budgets now produce a typed
`insufficient_time_for_runtime_image_pull` boundary rather than another
zero-second SSH timeout. The live process was not restarted or mutated and
kept its claim until its existing absolute boundary. Expected effect: an
ordinary pre-science timeout after a long cold pull can resume on the same
mutable bench and proceed directly to the unconsumed component when the image
landed, while genuinely incomplete pulls fail promptly and honestly. Judge
the change by eliminating repeated `docker pull`/timeout-zero repair episodes
and increasing objective-valid GPU work per retained L40S claim, not by adding
validation artifacts or experiments. Python compilation and three focused
mocked behavior paths (resident image, missing image with exhausted budget,
and missing image with pull budget) pass.

## 2026-07-27T07:14Z — reconcile provider exposure after early reservation release

**GPU safety audit.** One grouped authenticated Nebius listing returned no
instances and no disks. This exactly matches `runtime/gpus.json`, whose last
live bench was cleanup-verified and retired at `07:12:41Z`; there are no
provider-only or missing registered resources, claims, owners, watchdogs,
passed live deadlines, or idle paid benches. No drain, provider cleanup, or
inventory mutation is warranted.

**Objective bottleneck and evidence.** The SM89 component is a pre-science
terminal, so the fixed local/global KV4 path still lacks its required
target-GPU discriminator. Canonical provider exposure was `1,818.369060`
seconds and `$0.43589503667130497`, exceeding the project's `$0.40`
reservation and putting campaign spend `$0.02660003667130497` beyond the hard
`$350` cap. The durable spend ledger nevertheless settled the component twice
at `$0`—at `06:45:05Z` and `07:08:15Z`—while its provider lifecycle was still
live or draining. Both settlements removed the reservation; when cleanup
later raised `STATUS.json.actual_spend_usd` to the canonical `$0.435895`, the
harness had no reservation left to settle and still exposed approximately
`$0.409295` as available. That stale availability could authorize another
paid lane despite the actual cap breach. The independent zero-GPU dual-KV4
integration remains active and made source/packet progress through `07:13Z`;
it is not blocked or disturbed by this change.

**Change and expected effect.** Updated the shared lab spend reconciler to
treat project `actual_spend_usd` as cumulative: a later increase is charged
only as the delta above the greatest prior settlement, including after a
reservation was already released. Settled spend may now honestly exceed the
cap, yielding negative availability; the existing reservation check then
rejects all further paid work instead of crashing on, or hiding, an overrun.
The running harness and current ledger were not hot-mutated; the director's
explicit no-new-spend disposition remains the live guard. The harness detected
the source change at `07:17:03Z` and requested its normal
`drain_active_agent_turns_then_reload` transition, so reconciliation will load
after this supervisor and the already-finishing offline researcher return.
Seven focused spend/reservation tests pass, including the exact
zero-settlement followed by `$0.435895` cleanup pattern; all 232 factory
tests, repository DevEx checks, Python compilation, and diff checks also pass.
Expected effect:
delayed provider cleanup can no longer reopen fictitious budget, repeated
cumulative settlements cannot double-charge prior exposure, and future
direct GPU evidence starts only under genuinely available authority.

## 2026-07-28T08:27Z — make the reopened direct lane reach target hardware

**GPU safety audit.** One grouped authenticated Nebius listing returned no
instances and no disks, exactly matching `runtime/gpus.json`, whose 35 benches
are retired. There is no provider-only or missing registered resource, live
claim, owner/watchdog, passed deadline, or idle paid bench. The reopened
campaign has `$329.117519` settled against its new `$400` cap and a durable
`$1.50` reservation for
`gemma4_l40s_dual_kv4_allocator_0953_integration`, leaving `$69.382481`
available. No drain, cleanup, or inventory mutation is warranted.

**Objective bottleneck and evidence.** The campaign now explicitly requires
decision-bearing GPU work and a cheap target-hardware discriminator before
more setup validation. The director admitted two active lanes at `08:22:42Z`,
but neither can currently touch a GPU. The zero-cost RTX 6000 Ada lane is a
venue/rate study. The paid L40S lane is labeled direct and has a source-complete
fixed local/global KV4 path, positive memory-fit interval, unconsumed
scientific arm, durable reservation, and authenticated compatible Nebius
controller; nevertheless its `next_action` requires another CPU-only
`L40S_DUAL_KV4_SM89_COMPONENT_READY.json` and explicitly forbids provider,
claim, SSH, image, or CUDA activity until a later director turn. Its live trace
is dominated by orientation, historical hashes, source inspection, prior
owner review, and offline contract checks. This repeats the readiness-before-
execution pattern after the previous L40S lifecycle ended pre-science, rather
than patching and running against a claimed mutable bench.

**Change and expected effect.** Narrowly clarified `$research-director`: a
source-complete paid lane whose next result is another offline readiness
artifact does not satisfy the direct-GPU floor. Once the reservation is
durable and an authenticated compatible provider exists, the director should
provision/register the bounded bench and let ordinary launcher composition,
the first tiny target-runtime call, and recoverable repairs proceed inside the
mutable claim. Offline preparation may continue in parallel but cannot
substitute for an actually ready or running GPU lane. The two active
researchers and their scientific scopes were not edited or interrupted.
Expected effect: the next director wake converts the existing `$1.50`
reservation into the unconsumed SM89 measurement instead of adding another
CPU gate, shortening time to target-GPU evidence and keeping integration
defects repairable in one claimed session.

## 2026-07-28T08:43Z — keep paid exposure reserved through provider retirement

**GPU safety audit.** One grouped authenticated Nebius listing returned
RUNNING instance `computeinstance-e00nczqf2p0x2y51wt` and READY managed disk
`computedisk-e00wjqwz8zdc3ph7sr`. They exactly match registered bench
`l40s-dual-kv4-sm89-computeinstance-e00nczqf2p0x2y51wt`; there is no
provider-only or missing inventory resource. The controller-host user
watchdog
`gemma4-dual-kv4-sm89-20260728t083202z-watchdog.service` is active/running as
recorded PID `2728448` in its recorded control group, and its
`2026-07-28T10:02:02.551113Z` deadline has not passed. The bench moved from
maintenance to ready at `08:38:55Z`, was claimed by
`gemma4_l40s_dual_kv4_allocator_0953_integration` at `08:40:31Z`, and has a
fresh `08:43:02Z` heartbeat with a live PID-managed owner. It is therefore
neither stale nor an unjustified idle-cost bench. No drain, provider cleanup,
or inventory retirement is warranted.

**Objective bottleneck and evidence.** The campaign's required cheap
target-hardware discriminator is now correctly inside one continuous mutable
L40S claim; source/readiness work is complete, the scientific sample remains
unconsumed, and the owner is staging and running under the existing
`$1.50` authority. The remaining bottleneck is the live target integration,
not portfolio breadth or another static gate, so the supervisor did not touch
the owner or create work. One accounting defect briefly made that same live
integration unsafe for future scheduling: after the readiness researcher
became terminal, the harness emitted `spend_settled` with `$0` actual at
`08:34:54Z` and removed its full `$1.50` reservation even though the exact
paid bench had been registered since `08:33:12Z` and remained live. This
exposed `$1.50` as available for about five minutes while provider cost was
still accruing. Normal project reactivation restored the reservation at
`08:40:00Z`, before the claim, so the current ledger is conservative; relying
on reactivation would still repeat the mismatch for terminal cleanup or a
long repair hold.

**Change and expected effect.** Updated the shared lab spend reconciler so a
non-retired GPU inventory record keeps the reservation for the project named
by either its live claim or resident `contents.project`, even when the
researcher status is terminal. If the earlier bug has already removed that
reservation, the reconciler restores only the remaining authorized amount
above cumulative spend and records `spend_reservation_restored`; settlement
and late-delta reconciliation resume after retirement. This changes only
budget accounting and does not alter claims, watchdogs, experiments, or
scientific scope. The harness observed the source change but correctly
deferred reload because the current PID-managed owner is live, preserving the
active mutable session. Two new regression cases cover retention and repair
of an early release; five focused settlement tests and all 234 factory tests
pass. Expected effect: a recoverable integration failure can remain claimed
and be patched in place without silently reopening its provider authority,
while cleanup-time exposure still settles once the director retires the
bench.

## 2026-07-28T09:03Z — replace the single-generation owner, retain the warm L40S

**GPU safety audit.** One grouped authenticated Nebius listing returned
RUNNING instance `computeinstance-e00nczqf2p0x2y51wt` and READY managed disk
`computedisk-e00wjqwz8zdc3ph7sr`, exactly matching registered bench
`l40s-dual-kv4-sm89-computeinstance-e00nczqf2p0x2y51wt`; there is no
provider-only or missing inventory resource. The controller-host user
watchdog
`gemma4-dual-kv4-sm89-20260728t083202z-watchdog.service` remains
active/running as recorded PID `2728448` in its recorded control group, and
its `2026-07-28T10:02:02.551113Z` deadline has not passed. The bench is
unclaimed in `maintenance`, not ownerless or unsafe: its exact compatible
project has an active replacement-owner implementation task and an unconsumed
sample. Warm reuse therefore justifies its current `$0.8629833/hour` idle
cost. No drain, provider cleanup, or inventory retirement is warranted.

**Objective bottleneck and evidence.** The paid target-hardware lane reached
the fixed component, but its controller encoded exactly one repair
generation. Attempt 0 failed before compilation because the extension lock
parent was absent; the same claim correctly consumed repair generation `g1`
and preserved resident state. Attempt 1 then reached NVCC and exposed two
ordinary CUDA 12 source incompatibilities
(`__nv_bfloat16` conversion and `CUDART_INF_F`). No extension, arm-specific
first-call marker, interpretable terminal, or scientific sample was produced.
Nevertheless the owner classified the result
`repair_attempt_unretrieved_or_uninterpretable` and released the claim at
`08:51:28Z` after `656.490110` claim seconds, with roughly 70 minutes still
left before the watchdog deadline. This converted a narrow prepared `g2`
source repair into paid idle maintenance after approximately 19.4 minutes
and `$0.279466268` of provider-start-to-release exposure. The independent c48
lane is already a typed capacity negative, so more portfolio breadth cannot
consume this bench or answer the open c32 component question.

**Change and expected effect.** The director preserved the instance, disk,
resident image, packet, diagnostics, attempts 0/1, and sample count, and at
`09:00Z` hash-bound
`DIRECTOR_DUAL_KV4_SM89_REPAIR_OWNER_BINDING_20260728T0900Z.json`
(`sha256
87b0bf8eb91da0a7b1edfba162e04c5e2297b4b6335b137649dcd6ec614d548b`).
It keeps the bench non-claimable while one 12-minute offline task implements
and tests `l40s_dual_kv4_repair_owner.py`, then permits only the same bench and
the prepared `g2` bytes under a shortened absolute release window. The
replacement must loop fresh repair generations and refuse to release an
unconsumed recoverable or uninterpretable nonterminal. This is the smallest
safe harness correction and does not alter the scientific portfolio or touch
the active provider lifecycle. No additional shared-skill or static-validator
change was made: `$research-director` and `$researcher` already explicitly
forbid fixed repair-count and unconditional pre-science release, so duplicating
that text would not address the implementation defect. Expected effect: the
next launch pays no cold-create/image/packet setup, attempt 2 applies the
localized CUDA repair against resident state, and any further ordinary
integration defect remains within one continuous mutable claim until
decision-bearing evidence or the absolute safety boundary.

## 2026-07-28T09:12Z — reject expired launch fences before claiming a warm bench

**GPU safety audit.** One grouped authenticated Nebius listing returned
RUNNING instance `computeinstance-e00nczqf2p0x2y51wt` and READY managed disk
`computedisk-e00wjqwz8zdc3ph7sr`, exactly matching registered bench
`l40s-dual-kv4-sm89-computeinstance-e00nczqf2p0x2y51wt`; there is no
provider-only or missing inventory resource. The recorded controller-host user
watchdog
`gemma4-dual-kv4-sm89-20260728t083202z-watchdog.service` is active/running as
PID `2728448` in the recorded control group, and its
`2026-07-28T10:02:02.551113Z` deadline has not passed. The repaired owner
claimed, heartbeated, retrieved a scientific terminal, and released safely;
the bench is now available and unclaimed. Its release contents are
inconsistent: `result=scientific_terminal_retrieved`, but
`scientific_terminal` still says the sample is unconsumed and `next` still
names the expired g2 launch. The current director is consuming the new
terminal, so retain only through that selection turn. If it does not select a
source-ready compatible checkpoint-free L40S follow-up, recommend draining
the exact instance and disk above; the fixed dual-KV4 sample is consumed and
the independent c48 placement is already a typed capacity negative.

**Objective bottleneck and evidence.** Warm reuse worked and avoided teardown:
after the first `656.490110`-second claim released at `08:51:28Z`, the image,
packet, diagnostics, and extension state survived an approximately
`1,079`-second repair/binding gap. The g2 owner then needed only
`108.143198` claim seconds, from `09:09:27Z` to `09:11:15Z`, to compile, run
attempt 2, retrieve the result, and release. That result closes this exact
mechanism rather than another integration boundary. Local KV4 was
`3.789697 ms` mean versus `0.324938 ms` all-E5M2 with relative-L2 error
`0.150925`; global tiered KV4 was `32.358512 ms` versus `0.813310 ms` with
relative-L2 error `0.999379`. Both promotion margins are strongly negative,
and the global consumer is also numerically incoherent. More repair or a
full endpoint for this fixed representation is therefore not the campaign
bottleneck; the director should use the result to select a materially
different allowed cost mechanism.

**Process change and expected effect.** The live binding had a structured
`claim_start_by_utc=2026-07-28T09:08:00Z`, but the director returned at
`09:08:07Z`, the harness launched the researcher at `09:08:07Z`, and the
claim began at `09:09:27Z`. A concurrent director correctly noticed the
missed fence and began a shortened rebind while the researcher was consuming
the stale command. The absolute owner/watchdog margins happened to remain
safe and the run completed, but the race could launch a future command whose
measured work no longer fits. Narrowly updated `$researcher`: immediately
before executing a director binding, compare its structured claim-start fence
with current UTC and inspect the exact bench once; if the fence passed without
a matching owner/claim, leave the bench unclaimed and return the exact binding
and resource IDs for a lifecycle-only director rebind. The rule explicitly
forbids drain, cold restart, repeated preparation, or scientific-scope changes.
The skill validator, repository DevEx checks, and diff checks pass. Expected
effect: expired admission envelopes are reconciled before atomic claim, while
valid near-term bindings still launch immediately and warm scientific work
does not acquire another static validation stage.

## 2026-07-28T09:36Z — preserve launch runway through the director handoff

**GPU safety audit.** One grouped authenticated Nebius listing returned
RUNNING instance `computeinstance-e00nczqf2p0x2y51wt` and READY disk
`computedisk-e00wjqwz8zdc3ph7sr`, exactly matching the sole non-retired
inventory record
`l40s-dual-kv4-sm89-computeinstance-e00nczqf2p0x2y51wt`. The recorded
controller-host user watchdog
`gemma4-dual-kv4-sm89-20260728t083202z-watchdog.service` remains
active/running as PID `2728448` in its recorded control group, with deadline
`2026-07-28T10:02:02.551113Z`. The bench is available and unclaimed, not
unsafe or ownerless. Retention remains justified because the positive,
hash-bound staged-E5M2 runner is compatible with its resident image and a
lifecycle-only correction is already being handled; no drain, provider
cleanup, or inventory retirement is warranted.

**Bottleneck and evidence.** The director persisted the staged-consumer live
binding with `claim_start_by_utc=2026-07-28T09:35:00Z`, updated project state
at `09:33:37Z`, and marked the bench ready at `09:34:15Z`, but continued its
turn until `09:35:06.969178Z`. The harness could not start the execution
researcher until `09:35:07.175979Z`, after the fence had already elapsed; at
`09:35:09Z` the bench still had no claim or owner. This repeats the earlier
`09:08:00Z` handoff expiry and converts a source-complete compatible warm
experiment into another rebind turn and paid idle time. The scientific arm
remains unconsumed, so the failure is coordination latency rather than
evidence against the KV4-to-E5M2 mechanism.

**Process change and expected effect.** Narrowly updated `$research-director`
to perform one final local clock check immediately before returning. A new
`claim_start_by_utc` must retain at least 120 seconds for one harness
scheduling interval and worker startup; with less runway, the director may
extend only that lifecycle fence when the unchanged absolute release,
watchdog, and spend authority still fit, otherwise it must leave the project
offline and the bench unclaimed. The rule does not add provider polling,
static science validation, or a new project. The skill validator, repository
DevEx checks, and diff checks pass. Expected effect: exact warm owners reach
their atomic claim instead of spending a researcher turn rejecting a binding
that expired inside the director turn, while the existing researcher-side
guard still prevents unsafe stale launches.

## 2026-07-28T09:54Z — reject shadow GPU inventories at the pool boundary

**GPU safety audit.** One grouped authenticated Nebius listing in the
configured default scope returned RUNNING instance
`computeinstance-e00nczqf2p0x2y51wt` and READY disk
`computedisk-e00wjqwz8zdc3ph7sr`, matching registered L40S bench
`l40s-dual-kv4-sm89-computeinstance-e00nczqf2p0x2y51wt`. Its recorded
controller-host user watchdog
`gemma4-dual-kv4-sm89-20260728t083202z-watchdog.service` is active/running as
PID `2728448` in the recorded control group, with deadline
`2026-07-28T10:02:02.551113Z`. The owner safely released its claim at
`09:52:21Z`; the bench is available, not ownerless while claimed or stale.
Reuse it immediately only if the director can issue an unchanged staged-E5M2
binding with enough time to release before the watchdog; otherwise recommend
draining exact instance `computeinstance-e00nczqf2p0x2y51wt` and disk
`computedisk-e00wjqwz8zdc3ph7sr` rather than paying for an unlaunchable final
window.

The newly registered B200 is in Nebius project
`project-i00hfrkjpr00wmz2kzj3qm` / `me-west1-a`, outside that default listing's
project scope, so absence from this one listing is not evidence that its
provider resources disappeared. Durable create/identity evidence names
instance `computeinstance-i00jxp168hnbx08c86` and disk
`computedisk-i00vn6qwf963gvwqx3`; registered bench
`b200-nvfp4-computeinstance-i00jxp168hnbx08c86` is claimed, its controller
watchdog `gemma4-b200-nvfp4-20260728t0944z-watchdog.service` is active/running
as PID `2788373`, and pool heartbeats are fresh through `09:54:25Z`, before
its `10:10:38.516142Z` deadline. No registered bench met the objective
unsafe/deadline/owner-loss condition for supervisor draining, and no provider
cleanup or inventory retirement was performed.

**Objective bottleneck and timing evidence.** Warm reuse was preserved: there
was no teardown or cold restart after the L40S integration errors, and its
image, packet, diagnostics, and compiled state remained resident. The final
claim lasted about 571 seconds (`09:42:50Z` to `09:52:21Z`) but produced no
scientific invocation. The unchanged container first failed on
`getpwuid(): uid not found: 1001`; a same-claim uid-0 repair was prepared, but
the retained repair deadline then passed before relaunch. The staged sample
remains unconsumed. The pool history also shows five ready/rebind events
between `09:19:13Z` and the eventual claim, following an earlier release at
`09:11:15Z`. By contrast, the independent B200 lane moved from provider start
at `09:45:38Z` to claim at `09:52:05Z`, is heartbeating during its pinned image
pull, and has not yet consumed CUDA science. The campaign bottleneck this turn
is therefore reliable conversion of prepared warm state into an actual
consumer invocation, not a lack of projects or static validation.

**Process change and expected effect.** At the L40S release boundary the
researcher first invoked `gpu_pool --lab <lab>/runtime`. `GpuPool` silently
appended another `runtime`, read the pre-existing 90-byte shadow inventory at
`runtime/runtime/gpus.json`, and falsely reported that the project did not own
the real bench. A separate observed form, `--lab <lab>/runtime/gpus.json`,
failed later with `NotADirectoryError`. The researcher diagnosed the path and
released correctly with `--lab <lab>`, but the silent shadow-state behavior is
unsafe at exactly the claim/release boundary.

Narrowly changed `research/factory/src/grad_research/gpu_pool.py` so `GpuPool`
rejects an inventory file or an existing `runtime/` inventory directory before
creating paths, with an actionable instruction to pass the lab root. Added
regressions proving both misuse forms fail and do not create
`runtime/runtime`. The full GPU-pool unit suite passes (`19` tests), as do
Python compilation, repository DevEx validation, and diff checks. Expected
effect: future repair owners address the canonical claim on the first release
attempt instead of consulting a shadow inventory, preventing false ownership
failures, missed lifecycle fences, and needless teardown/cold restart after a
recoverable integration error.

## 2026-07-28T10:04Z — fence an ownerless B200 claim and preserve repair wait

**GPU safety audit.** One grouped authenticated Nebius listing across the two
project scopes recorded by the live inventory returned exactly the registered
resources: RUNNING L40S instance
`computeinstance-e00nczqf2p0x2y51wt` with READY disk
`computedisk-e00wjqwz8zdc3ph7sr`, and RUNNING B200 instance
`computeinstance-i00jxp168hnbx08c86` with READY disk
`computedisk-i00vn6qwf963gvwqx3`. There were no provider-only or
inventory-only resources. The L40S replacement controller-host user watchdog
`gemma4-dual-kv4-sm89-20260728t0956z-watchdog.service` was active/running as
PID `2799587`; the old recorded unit was intentionally inactive only after the
inventory had atomically moved to this replacement. The B200 controller-host
user watchdog `gemma4-b200-nvfp4-20260728t0944z-watchdog.service` was
active/running as PID `2788373`. Neither lifecycle deadline had passed.

The B200 claim nevertheless became objectively ownerless: detached PID
`2794350` no longer existed, `OWNER.log` stopped at `10:00:35Z`, and claim
heartbeats stopped at `10:00:26Z` while the inventory remained claimed. Marked
registered bench `b200-nvfp4-computeinstance-i00jxp168hnbx08c86`
`drain_after_release=true`; this does not stop the claim, clean provider
resources, or retire the inventory record. Exact director cleanup IDs are
instance `computeinstance-i00jxp168hnbx08c86` and disk
`computedisk-i00vn6qwf963gvwqx3` in project
`project-i00hfrkjpr00wmz2kzj3qm`. The harness dispatched the same researcher
at `10:02:55Z`, and its in-place recovery restored the existing claim
heartbeat at `10:04:12Z`; preserve that repair rather than cold-create a B200.
The L40S was available with a compatible root-UID repair and justified
retention; it claimed at `10:03:21Z` with fresh heartbeats under the unchanged
warm disk and image, before its final `10:05:00Z` claim fence.

**Objective bottleneck and timing evidence.** Neither direct lane had yet
produced new model-specific science at the audit point. B200 moved from
provider start at `09:45:38Z` to claim at `09:52:05Z` and owner launch at
`09:53:25Z`. The pinned image finished downloading and remained resident; the
worker then exited `1` without the exact 24-row terminal, with raw output and
remote retrieval retained and the scientific sample unconsumed. The outer
owner correctly wrote a hash-bound `REPAIR_READY.json`, but its subsequent
`repair-handshake wait ... --deadline 10:08:30Z` died at argument parsing.
That killed the heartbeat thread at exactly the recoverable integration
boundary. L40S also remained warm: the director replaced its watchdog and
issued a root-UID repair rather than recreating the provider resource. Four
ready-content refreshes occurred from `09:59:25Z` through `10:02:12Z`, then
the owner claimed at `10:03:21Z`; the prior final-clock runway fix therefore
preserved a valid launch despite the 511-second director turn. The current
constraint is durable same-claim repair execution, not missing portfolio
breadth, cold setup, or scientific hypothesis supply.

**Process change and expected effect.** The shared tool documented
`ready --deadline`, while `wait` derived the same immutable deadline from
`REPAIR_READY.json` but rejected the caller's repeated `--deadline` option.
Narrowly extended `research/factory/tools/repair-handshake` so `wait` accepts
an optional RFC3339 `--deadline` only when it exactly matches the persisted
ready deadline; a mismatch fails closed as
`repair_wait_deadline_mismatch`. Added regressions for the matching blocking
path and mismatch rejection, and updated the shared-tools README. All eight
repair-handshake tests, Python compilation, repository DevEx validation, and
diff checks pass. Expected effect: the repaired B200 outer owner can keep its
heartbeat thread alive while waiting for the hash-bound in-place patch,
preserving the downloaded image and current claim through the remaining
window instead of turning an ordinary worker/integration error into teardown
and another cold pull.

## 2026-07-28T10:13Z — repair source-audit layout under the warm claim

**GPU safety audit.** One grouped authenticated Nebius listing across the two
configured project scopes returned exactly the non-retired inventory
resources at audit time: RUNNING L40S instance
`computeinstance-e00nczqf2p0x2y51wt` with READY disk
`computedisk-e00wjqwz8zdc3ph7sr`, and RUNNING B200 instance
`computeinstance-i00jxp168hnbx08c86` with READY disk
`computedisk-i00vn6qwf963gvwqx3`. There were no provider-only or
inventory-only resources. Controller-host user watchdogs
`gemma4-dual-kv4-sm89-20260728t0956z-watchdog.service` and
`gemma4-b200-nvfp4-20260728t1007z-watchdog.service` were both active/running
under their recorded control groups; the B200 replacement is still
active/running as PID `2823346` through `10:25:00Z`.

The L40S claim released at `10:08:31Z` with no compatible queued successor and
only 211 seconds before its lifecycle deadline. The director then recorded
provider cleanup and retired the inventory record at `10:11:34Z`, so a
deadline drain attempt correctly refused to mutate the retired record. The
B200 claim remains objectively ownerless: recorded repair owner PID `2816234`
is absent, its heartbeat stopped at `10:08:15Z`, its lease ended at
`10:10:38Z`, and `STATUS.json.active_session` still names that dead PID.
The bench is already correctly fenced with `drain_after_release=true`; no
second drain, provider cleanup, or retirement was performed. Exact director
disposition IDs are instance `computeinstance-i00jxp168hnbx08c86` and disk
`computedisk-i00vn6qwf963gvwqx3` in project
`project-i00hfrkjpr00wmz2kzj3qm`.

**Objective bottleneck and timing evidence.** Both current model-specific
lanes stopped before science on source-audit layout rather than on the
intervention. The L40S root-UID in-place repair claimed the warm bench at
`10:03:21Z`, heartbeated through `10:07:10Z`, and released at `10:08:31Z`;
after clearing the UID defect it rejected a stale declared source digest
(`7833f6d0...`) against the exact staged bytes (`1040f43a...`) and never
submitted the candidate. On B200, the resident pinned image passed SM100,
CUDA 12.9, CUTLASS FP4 support, image identity, vLLM version, mechanism
digest, and benchmark digest checks. Its compact sentinel failed only because
six repository source paths are not shipped inside `/vllm-workspace` in the
runtime image (`observed_sha256: null`); no CUDA kernel or 24-row evaluator
was submitted. The image pull and claim were preserved, and
`runtime/gpu_events.jsonl` shows no teardown/cold restart, but successive
repairs consumed the usable window without objective evidence. The real
bottleneck is conflating runtime source-tree layout with executable identity,
not insufficient static validation, project supply, or scientific portfolio
choice.

**Process change and expected effect.** Narrowly amended
`.agents/skills/researcher/SKILL.md`: when the pinned image and executable
package/version are verified but the image omits repository source files, a
needed source audit must use the already verified project-local pinned
snapshot (staged or mounted read-only under the same claim) or bind the
installed executable/module bytes. Missing runtime source layout is now a
repairable audit-layout defect followed directly by the first tiny real GPU
call; true source/executable/invocation mismatches remain fail-closed. This
does not add a validator or broaden the intervention. Skill validation,
repository DevEx validation, and diff checks pass. Expected effect: the next
same-claim owner can spend the retained B200 image on the first scientific
discriminator instead of treating packaging layout as a model-specific
negative or paying for another cold bench.

## 2026-07-28T10:23Z — dispatch durable repair independently of the director

**GPU safety audit.** One grouped authenticated Nebius listing for the sole
configured live project returned exactly the inventory resources: RUNNING
B200 instance `computeinstance-i00jxp168hnbx08c86` and READY disk
`computedisk-i00vn6qwf963gvwqx3` in
`project-i00hfrkjpr00wmz2kzj3qm`; there were no provider-only or
inventory-only resources. The recorded controller-host user watchdog
`gemma4-b200-nvfp4-20260728t1016z-watchdog.service` was active/running as PID
`2835319` with lifecycle deadline `10:35:00Z`. At `10:18:38Z`, recorded
development owner PID `2836406` matched start ticks `134989407` and the claim
was fresh.

The repair owner then reached its immutable `10:22:30Z` deadline and exited.
At `10:22:51Z`, `/proc/2836406` was absent while `STATUS.json.active_session`
still named that PID and the inventory remained claimed with its last
heartbeat at `10:22:27Z`. Marked registered bench
`b200-nvfp4-computeinstance-i00jxp168hnbx08c86`
`drain_after_release=true`; no provider cleanup, claim reclaim, or inventory
retirement was performed. Exact director disposition IDs are instance
`computeinstance-i00jxp168hnbx08c86` and disk
`computedisk-i00vn6qwf963gvwqx3`.

**Objective and timing evidence.** The previous source-layout change worked:
the resident pinned image was already up to date, and repair-g4 passed image,
commit-bearing version, benchmark hash, SM100, CUDA 12.9, source-layout, and
FP4-support gates. It executed one synchronized discovery call through both
required vLLM NVFP4 operators, then stopped before timed rows because the
installed runner closure omits the observer's stale `b_global_scale` name.
There is still no interpretable 24-row component terminal, endpoint result, or
movement against the campaign's `0.500119281574996 s/request` target, but this
is now a concrete same-claim oracle-adapter repair rather than a runtime
support negative. GPU events show warm reuse rather than teardown: provider
start `09:45:38Z`, first claim `09:52:05Z`, safe reclaim at `10:14:26Z`, a
132-second available interval, and the replacement claim at `10:16:39Z`.

The remaining throughput loss was scheduler latency around the durable
repair. The researcher exposed `REPAIR_READY` and completed at `10:19:36Z`,
but a director turn had been running since `10:15:54Z`; the harness did not
wake the repair researcher until that director completed at `10:20:14Z`, a
38.19-second delay. An earlier L40S durable repair waited approximately 142
seconds for the same boundary (`10:04:35Z` to `10:06:57Z`). Ordinary
portfolio admission should wait for the director, but a live owner requesting
a bounded repair is already admitted work and should not spend its deadline
heartbeating for that unrelated turn.

**Process change and expected effect.** Narrowly changed
`research/factory/src/grad_research/lab_harness.py` so free researcher slots
may dispatch only rows with a live durable owner and pending
`REPAIR_READY.json` while a director turn is running. Normal ready/active
projects remain blocked behind the director, so this neither selects science
nor adds portfolio concurrency. Added an event-loop regression proving the
durable repair starts while the director is still active; all 69 harness tests,
Python compilation, repository DevEx validation, and diff checks pass. The
live harness correctly deferred its source reload while the PID-managed owner
existed, so the active experiment was not disrupted. Expected effect: future
same-claim integration repairs begin tens to hundreds of seconds earlier,
leaving the researcher more of the bounded owner window to patch and rerun
against resident images instead of expiring into reclaim or cold setup.

## 2026-07-28T10:56Z — fence ownerless B200 endpoint claim after in-place repair

**GPU safety audit.** One grouped authenticated Nebius listing for the sole
configured live project returned one RUNNING instance
`computeinstance-i00hfh66qbsqy4mx7x` with its READY disk
`computedisk-i00svcmxdjhpm7bkez`, exactly matching the only non-retired
inventory bench
`b200-nvfp4-endpoint-computeinstance-i00hfh66qbsqy4mx7x`; there were no
provider-only or inventory-only resources. The recorded controller-host user
watchdog
`gemma4-b200-nvfp4-endpoint-20260728t1050z-watchdog.service` is
active/running as PID `2964618` in its exact recorded control group through
`2026-07-28T12:31:59.335947Z`. The claim heartbeat was fresh at
`10:55:02.378175Z`, and no deadline had passed.

The researcher correctly retained the mutable claim after the first
pre-science staging failure, patched the transfer scope, and launched repair
owner PID `2970327` with start ticks `135211973`. That owner again exited at
the `stage_project_snapshot` boundary after approximately 20 seconds. The
researcher observed it during the brief live interval, recorded it in
`STATUS.json.active_session`, and then completed its turn; at `10:56:03Z`
the PID was absent while both the active session and claimed inventory still
named it. This is now an objective owner-loss condition rather than a live
repair handoff. Marked the registered bench `drain_after_release=true`; no
claim reclaim, provider cleanup, or inventory retirement was performed.
Exact director disposition IDs are instance
`computeinstance-i00hfh66qbsqy4mx7x` and disk
`computedisk-i00svcmxdjhpm7bkez` in project
`project-i00hfrkjpr00wmz2kzj3qm`.

**Objective evidence and expected effect.** The campaign bottleneck remains
the complete exact-checkpoint B200 BF16-control versus native-NVFP4 c32
endpoint, not component support or project supply. Both owners stopped before
CUDA or a scientific sample at the snapshot/transfer boundary; no teardown or
cold provider restart occurred, and the second attempt reused the same remote
root and claim. The drain fence prevents this ownerless claim from silently
returning to the shared pool after release while preserving the running bench
for the director to choose either an immediate same-claim staging repair or
cleanup using the exact IDs above. No shared skill, tool, or harness change
was made: the existing same-claim repair path behaved as intended, and
changing it while this experiment is still recoverable would add process
rather than advance the endpoint measurement.

## 2026-07-28T11:05Z — suppress stale repair wakes during the live B200 transfer

**GPU safety audit.** One grouped authenticated Nebius listing for the sole
configured project returned RUNNING instance
`computeinstance-i00hfh66qbsqy4mx7x` and READY attached disk
`computedisk-i00svcmxdjhpm7bkez`, exactly matching the only non-retired
inventory bench; there were no provider-only or inventory-only resources.
The controller-host user watchdog
`gemma4-b200-nvfp4-endpoint-20260728t1050z-watchdog.service` is
active/running as PID `2964618` in its recorded control group through
`12:31:59.335947Z`. Repair-2 owner PID `2973170` is live with exact recorded
start ticks `135234099`, the claim heartbeated at `11:01:43.927467Z`, and no
deadline has passed. The prior drain fence remains set; no lifecycle,
provider, claim, or project mutation was made.

**Objective and timing evidence.** The direct campaign bottleneck remains the
complete exact-checkpoint B200 BF16-control versus native-NVFP4 endpoint.
Repair-2 added only the bound `ssh -n` fix and reused the original claim,
remote root, and partial staging state. It began at `10:58:43.588448Z` and is
actively transferring the first immutable 49.8-GB shard; a researcher
snapshot measured 4,962,262,560 remote bytes at approximately `11:01:47Z`.
No CUDA, conversion, server, control, candidate, or scientific sample has
started, but there has also been no teardown or cold restart.

The coordination loop was repeatedly treating the old
`b200-nvfp4-20260728T105522Z/REPAIR_READY.json` as pending after the
hash-bound replacement owner had already launched. It woke the researcher at
`10:59:27.671631Z` and again at `11:01:16.928358Z`; the resulting
44.756-second and 32.082-second turns only confirmed the healthy transfer,
then emitted `researcher_no_progress` and additional director wakes. This did
not interrupt the owner, but it spent agent and director cycles on a consumed
integration generation rather than the endpoint result.

**Process change and expected effect.** Narrowly changed
`research/factory/src/grad_research/lab_harness.py` so a ready generation is
not pending when an explicitly identified PID-managed repair owner was
launched after that ready marker. A ready marker created after the current
repair owner still wakes immediately, and the normal in-place outer-owner
handshake remains unchanged. Added both ordering regressions; all 71 harness
tests, Python compilation, repository DevEx validation, and diff checks pass.
The live metadata now resolves to no pending stale repair while PID `2973170`
continues unchanged. The running harness will defer source reload until the
durable owner exits. Expected effect: long checkpoint transfers and model
loads proceed without repeated status-only researcher/director turns, while a
genuinely new integration failure still receives the fast same-claim repair
dispatch.
