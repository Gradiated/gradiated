# Tiny transformer on the KV260

This implementation combines the Mac model/reference work at `6d2289946` with the Linux circuit/host work at `d93f07a`. The merge preserves both lineages and the current Mac joke edit. See [migration provenance](../../migration.json).

## What is verified

The original model ran on the physical board. The newer text-input candidate passed the Mac numerical and server RTL checks, then passed physical acceptance on the same FPGA configuration. All seven validation cases and three frozen completions matched. The original weights were restored and checked with the original BOS reference. [Physical acceptance record](../../results/physical-acceptance-20261114T232418Z-c39918/run.json)

- `model/conditioned.md` and `model/conditioned.json`: current text-input model, quality limits and payload pins.
- `model/README.md`: original model and integer-format study.
- `rtl/`: full circuit, interfaces and testbenches.
- `tools/`: training/reference arithmetic, simulation, host and board tooling.
- `material/`: editable creative text and frozen-source history. The editable joke file is not the trained dataset.
- `history/mac-record.md` and `history/server-record.md`: preserved chronological engineering records. They contain historical paths and status statements. Use the latest relevant entry and the current baseline registry, not an older opening status.

The [resource and memory baseline](resource-memory-baseline.md) ties routed Vivado usage to the deployed firmware and accounts for the model image, K/V cache and working buffers.

Separate variants preserve that baseline: [ctypes score slicing](variants/ctypes-slice-v1/README.md) and [observation counters](variants/observer-v1/README.md) have physical comparison evidence. The counters passed exact-output and readout checks, but timing neutrality remains inconclusive. The original circuit and weights were restored.

## Selected circuit comparison baseline

### 20 November 2026 — adopt attention-value-pair-v1

Aidan selected Experiment 23 as the 50 MHz comparison baseline for the frozen W16A16 model, succeeding Experiment 22. Two attention value-mixing lanes and two value banks preserved every timed reply. Median completion fell by 4.44–6.92% across three prompts and mixed-workload module energy per verified answer fell by 5.89%. The circuit uses 39,376 LUTs, 15,712 flip-flops, 58 DSPs and 39 block RAM tiles. The original board configuration passed restoration. [Board findings](../../results/attention-value-pair-20261119T234247Z-e21df0/findings.md)

| Component | SHA-256 |
| --- | --- |
| [Variant manifest](variants/attention-value-pair-v1/manifest.json) | `137ceb54320b5d41ac082d0b2f5667199de4e039e8188d925c33844147f55d84` |
| [Exact RTL replay](../../results/attention-value-pair-v1-rtl-20261119T203052Z/run.json) | `e9d57fea3d368173010e7532c832b01ba461e04c637a39651bcf705258aad81a` |
| [Routed build](../../results/attention-value-pair-v1-build-20261119T203714Z/run.json) | `43f40df14aa13a18cd22355ecf13e94a1aba10455d94a6870e97abed0d1f12ee` |
| [Physical comparison](../../results/attention-value-pair-20261119T234247Z-e21df0/run.json) | `d853f1eb8d6f3c1af10654601b29d91409178825073df385c9d63000f35f0d49` |

### 19 November 2026 — adopt projections-read-ahead-v1

Aidan selected Experiment 22 as the on-chip 50 MHz baseline for the frozen `chip-joke-text-20261109` W16A16 model. It succeeds Experiment 21. Within-row read-ahead in Q/K/V, attention output and feed-forward gate/up saved exactly 3,999 clocks per processed position. On three measured prompts, complete replies took 7.86–9.75% less time. Mixed VCC_SOM energy fell 8.52% per useful output token on this board. The combined circuit uses 38,178 LUTs, 15,595 flip-flops, 57 DSPs and 39 block RAM tiles. All 200 timed outputs and all 320 original restoration scores matched. [Physical measurements](../../results/projections-read-ahead-20261119T195431Z-008bba/findings.md)

| Component | SHA-256 |
| --- | --- |
| [Variant manifest](variants/projections-read-ahead-v1/manifest.json) | `48b4747abd41eeca3d92ee6b08f42a5914bbfefeb2cab8ed1b10889bcddabe61` |
| [Exact RTL replay](../../results/projections-read-ahead-v1-rtl-20261119T192912Z/run.json) | `cb674695ab9e565d6028902cde0559266b993eaade1ffcf0dea96b72d26c6a36` |
| [Routed build](../../results/projections-read-ahead-v1-build-20261119T193229Z/run.json) | `b062ddb88e78652818cf559debe6adeb62055ec8e883e5acacc30f52f846a1f4` |
| [Physical comparison](../../results/projections-read-ahead-20261119T195431Z-008bba/run.json) | `809492e99c0baf53cdc544941dd9a3700108a5fca9c6fb5ec588475866635307` |
| Generated source manifest | `805ddad6c8d4011ddba8bcc07d5d9bfc6c112e101efe638a902d3e591daf8911` |
| Programming image | `8547e1d14564856be84b79dbb08fa2c7f603b1a705d2f43a9c93af79d946866a` |
| Programming overlay | `ccf8e76ada91923a653765c76ccecf0d8cbf8ae76e65de8239622d16ff56b591` |

### 19 November 2026 — adopt norm-mul-shared-v1

Aidan selected Experiment 21 as the 50 MHz on-chip baseline for the frozen `chip-joke-text-20261109` W16A16 model. It succeeds Experiment 19. Experiment 20 accelerated normalisation. Experiment 21 kept every measured first-token, last-token and completion FPGA count identical to Experiment 20 while sharing one multiplier across the three normalisation stages. The resulting design uses 38,130 LUTs, 15,605 flip-flops, 57 DSPs and 39 BRAM tiles. The mixed VCC_SOM energy difference of +0.064% was within paired variation. The original research circuit and weights passed restoration. [Physical comparison](../../results/norm-mul-shared-20261119T184132Z-42cf65/findings.md)

| Component | SHA-256 |
| --- | --- |
| [Variant manifest](variants/norm-mul-shared-v1/manifest.json) | `79ebb5dddf5530966e129c6b0f66530862677940637f535cd9da0b002c0aa907` |
| [Exact RTL replay](../../results/norm-mul-shared-v1-rtl-20261119T175457Z/run.json) | `44433cdfd27434a4d0fa4f186d9f5a7acd029c6bd705c0831129c20f53f92dc0` |
| [Routed build](../../results/norm-mul-shared-v1-build-20261119T181925Z/run.json) | `522b417e52accb9fdfbb24d928f4f8ad2fdce6fc86f01b62b820738a165da1f7` |
| [Physical comparison](../../results/norm-mul-shared-20261119T184132Z-42cf65/run.json) | `bf0c620e65c5b91e437e9215dad7b80f07ee43e8c0626ae853609e4794100dd8` |
| Generated source manifest | `d23404ea222fef3796f4bf51be1243eb04445f9403665d9b1ca9882f6ce1a109` |
| Programming image | `1d4a154a3531458d51251467db74783e2deaef0cda43082d9cd94f7997dedc1b` |
| Programming overlay | `82d6750fd0606777c94f08dd3be8e10da370f39731086fc09ac7e5f618a9b32d` |

### 19 November 2026 — adopt ff-scalar-mul-dsp-v1

Aidan selected Experiment 19 as the 50 MHz on-chip baseline for the frozen `chip-joke-text-20261109` W16A16 model. It succeeds `probability-div-v1`. One feed-forward scalar uses 16 DSPs to form the same product in five clocks. Across three prompts, complete replies took 7.21–8.70% less time. Gross mixed-workload module energy per verified answer fell 8.09% on one board and boot. All four mixed pairs had steady SPI1/TPM counters. The routed circuit uses 38,350 LUTs, 14,978 flip-flops, 53 DSPs and 39 BRAM tiles. The original research image and weights passed restoration. [Physical results](../../results/ff-scalar-mul-dsp-20261119T171509Z-1b23a4/findings.md)

| Component | SHA-256 |
| --- | --- |
| [Variant manifest](variants/ff-scalar-mul-dsp-v1/manifest.json) | `6079670c23df17dc691de407c8b50462809f09c0680c1c38ef9af979cd09bad4` |
| Generated feed-forward RTL | `02951bbd794df85c3ef20024e77eb4603102214fefca6556c301f18d13b20c3a` |
| [Exact RTL replay](../../results/ff-scalar-mul-dsp-v1-rtl-20261119T165532Z/run.json) | `f358faddfef4f6484092948cc0d669036894f66adc6bf12161fab55eab46a529` |
| [Routed build](../../results/ff-scalar-mul-dsp-v1-build-20261119T165358Z/run.json) | `7e37ae06d062d4a682be42ab49ccdab55fb20c4c85807d08d95bdf8cb741fadd` |
| Programming image | `32bfea598cf17b7d8a3f0f155b42e16f9a91e9a4bdb9caa79c64da73abf345a2` |
| Programming overlay | `647fe48eb029ae60b5e59bae28ea605da3c15871da60dd91fcc98be67faca9d6` |
| Verified physical invocation | `dfbec9ebf78aa1a7a4a6a808317e5d4eb46a2b4839c11c8bf363eb3656cd5bb4` |
| [Physical run](../../results/ff-scalar-mul-dsp-20261119T171509Z-1b23a4/run.json) | `2e4afdcb1885e9cff5ae6c5308995620051a395fa5df2d9377c986685beefe40` |

### 19 November 2026 — adopt probability-div-v1

Aidan selected Experiment 18 as the baseline for new on-chip comparisons. It succeeds Experiment 13 (`attention-exp-pair-v2`). The frozen `chip-joke-text-20261109` W16A16 model runs at 50 MHz. The attention unit takes eight steps to divide each exponential by its sum, preserving the exact probability. All 200 timed replies matched. Median completion took 4.80–7.64% less time across the three prompts. Gross mixed-workload VCC_SOM energy per reply fell 6.46% on one board and boot. All three mixed pairs with steady peripheral counters showed a reduction. The circuit uses 38,383 LUTs, 14,466 flip-flops, 41 DSPs and 39 block RAM tiles. [Physical findings](../../results/probability-div-20261119T161808Z-5b91c1/findings.md)

| Component | SHA-256 |
| --- | --- |
| [Variant manifest](variants/probability-div-v1/manifest.json) | `5e3d785dd345992446ba815fb451ff48f443a6be3b770de41857d28ff78646a2` |
| Generated attention RTL | `d9b481daa7e488bcfe7140a619f46163f4900e88ffa54286047850f53c732cdd` |
| [Exact RTL replay](../../results/probability-div-v1-rtl-20261119T160135Z/run.json) | `109a10b3b77600aad61e9284de2e1851646a0ca35d4bd108c006dcefac1b7f79` |
| [Routed build](../../results/probability-div-v1-build-20261119T155633Z/run.json) | `46c9246b510356a38405a5b23d6fcb623daf8ea4e31e276c6ee684be027fd302` |
| Programming image | `3edb7cc4e141d3cfebeaafbc21b22230bbf769bc30d405a0f55431b3cf264b8b` |
| Programming overlay | `5d0571c7c2d2c0317d4ef7bf38c0d88c7e1466b4d37bd08a7555d52233d58bef` |
| Verified physical invocation | `d8d53840f1f30813c54df037983a574b1bff7d52da4b1ce6413a2692e1aadc1d` |
| [Physical run](../../results/probability-div-20261119T161808Z-5b91c1/run.json) | `090a9238d89ce7f6999b48c33a5d31f0d7d07534e469bda345116faa263e4555` |

### 18 November 2026 — adopt attention-exp-pair-v2

Aidan selected the two-exponential circuit from Experiment 13 as the speed baseline for Experiment 14, superseding `attention-exp-div-v1`. Both units process scores within one attention head. The frozen `chip-joke-text-20261109` W16A16 model runs at 50 MHz.

All 36 timed replies matched and all 108 FPGA counters agreed with simulation. Across three prompts, median completion time fell by 4.53–6.92%. The routed circuit uses 38,329 LUTs, 14,464 flip-flops, 41 DSPs and 39 BRAM tiles. This spends 3,813 more LUTs, 883 more flip-flops, four more DSPs and one more BRAM tile. Module energy per verified reply fell by 5.46–6.05% across three pairs on one boot. One control block recorded SPI1 activity. The two pairs with steady peripheral counters showed 5.46% and 6.05% reductions. [Board measurements and restoration](../../results/attention-exp-pair-v2-20261117T232821Z-e72da4/findings.md) · [Independent audit](../../results/attention-exp-pair-v2-20261117T232821Z-e72da4/audit-manifest.json) · [Exact replay](../../results/attention-exp-pair-v2-rtl-20261117T230104Z/findings.md)

| Component | SHA-256 |
| --- | --- |
| [Variant manifest](variants/attention-exp-pair-v2/manifest.json) | `f1920ec220dab2c6cf50a67dee511c84e074850cb895b47110b33ee83b17d2ac` |
| Generated attention RTL | `d013e57bfeba5c096b8ab3e31ffe7084a02ac55558121e1cef93078a1035ee01` |
| [Routed build and programming files](../../results/attention-exp-pair-v2-build-20261117T225852Z/run.json), programming image | `a44cc30cad8db1844459470b63d2325b544dcef34709db88366bbc201409930d` |
| Programming overlay | `c53292a9fed6f2305200bb55602eb69f12ae8f24e42cae1e64a280d929d996fc` |
| Verified physical invocation | `93a3d46e67cdeb9aea34db0a8f4198a0a31dde601a198cf148cedfdb09304030` |
| [Physical run record](../../results/attention-exp-pair-v2-20261117T232821Z-e72da4/run.json) | `897f86341c09f680edfc4eac54e27281cfe1a39453540bd5d736fc12dd2aed67` |

### 17 November 2026 — adopt attention-exp-div-v1

Aidan selected **`attention-exp-div-v1`** as the baseline for subsequent KV260 teaching comparisons after Experiment 11, superseding `attention-cache-pipeline-v1`. It shortens the three exact divisions by 45,426 inside attention's exponential. The frozen `chip-joke-text-20261109` W16A16 model, rounding, variable probability division, cache pipeline, eight final-score lanes and 50 MHz clock remain unchanged.

The [physical comparison](../../results/attention-exp-div-20261117T132955Z-48d0fb/findings.md) and [independent audit](../../results/attention-exp-div-20261117T132955Z-48d0fb/audit-manifest.json) passed. All 36 timed outputs and 108 timing counters matched their references. Across three prompts, median first-token time fell 2.4–12.2%, decode rate rose 14.6–25.0%, and completion time fell 12.1–17.3%. Gross VCC_SOM energy per verified answer fell 15.4–15.7% across three paired blocks. The routed circuit uses 34,516 LUTs, 13,581 registers, 37 DSPs and 38 block RAM tiles, saving 253 LUTs and 71 registers against its control.

Energy evidence covers the module rail on one board boot. One control block recorded 1,282 ms of SPI1 active time and zero new TPM transfers. The other two pairs recorded zero counter deltas and still showed about 15.5% lower energy. All blocks remain included. These counters do not quantify the peripheral's energy contribution. Whole-board energy and broader workloads remain unmeasured.

| Component | Frozen identity |
| --- | --- |
| Variant source | [Manifest](variants/attention-exp-div-v1/manifest.json), SHA-256 `75ec7149f28b741057817d0945502c23531c4a595b419bddbbf24b861176f610` |
| Generated attention RTL | SHA-256 `5751f23c22f12b7560c71246bf172d82ce1636d9fc9123187bc88796eefea333` |
| Programming image | `gradiated-tiny-attention-exp-div-v1-50mhz.bit.bin`, SHA-256 `8f9280f37353e7595528900df9062407a277a04e4c8734d012aeb4471654fe9b` |
| Programming overlay | `kv260-attention-exp-div-program.dtbo`, SHA-256 `2980c7dc670a5cb22cc00f37c25f738fdadd0f0e1affae4c4cf6d4fb6d3c5051` |
| Verified physical packet | `attention-exp-div-20261117T132955Z-48d0fb/invocation.json`, SHA-256 `f8ba58103713597a8a2cc954b4028cf40ebf96969c2d1d65701f87447b906674` |
| Physical record | [run.json](../../results/attention-exp-div-20261117T132955Z-48d0fb/run.json), SHA-256 `45c7d2ae0e857d9921ff01d8a7f36358deb426cf6c8143a36273d3053508c12d` |

The [routed build](../../results/attention-exp-div-build-20261117T130122Z/run.json) and its [metadata correction](../../results/attention-exp-div-build-20261117T130122Z/metadata-correction.md) preserve the source and implementation evidence. Earlier baselines, completed runs and prepared workload manifests retain their original identities. Adoption changes the selected comparison baseline only. The original research circuit and weights were restored and verified after Experiment 11. This decision runs no experiment or board operation and does not select the next experiment.

### 17 November 2026 — adopt attention-cache-pipeline-v1

Aidan selected **`attention-cache-pipeline-v1`** for subsequent KV260 circuit comparisons after Experiment 10. It overlaps the next eligible cache read with the current attention multiply-accumulate. The W16A16 model, arithmetic, cache layout, eight final-score lanes and 50 MHz clock are unchanged.

The [physical comparison](../../results/attention-cache-pipeline-20261117T112139Z-daeb2e/findings.md) matched all 36 timed requests and 108 hardware counters. Across three fixed prompts, median time to first token fell 0.6–4.9%, decode rate rose 5.5–8.8%, and completion time fell 4.9–7.0%. Gross VCC_SOM module energy per verified answer fell 6.1–6.7% across three pairs on one boot. SPI1 was active after the third candidate block. A separate idle test reproduced the wake alongside TPM traffic. The original snapshots cannot establish whether that activity overlapped the energy window. [Independent audit](../../results/attention-cache-pipeline-20261117T112139Z-daeb2e/audit-manifest.json) · [SPI1 diagnosis](../../devices/kv260-spi1-clock-diagnosis.md)

| Component | Frozen identity |
| --- | --- |
| Variant source | [Manifest](variants/attention-cache-pipeline-v1/manifest.json), SHA-256 `1f9aedf96848f00d0568ac29f4f341b9305610733be1c60e77ef5c5a48c21656` |
| Generated attention RTL | SHA-256 `2992c3f0b8630a5fa1086406c81210170ede46e86058e94a875bd2d3ac9f0538` |
| Programming image | `gradiated-tiny-attention-cache-pipeline-v1-50mhz.bit.bin`, SHA-256 `bdb9de86c20de87b2693d45247ca3a75dcdf700f6d41861bbfd2c018593c3c33` |
| Programming overlay | `kv260-attention-cache-pipeline-program.dtbo`, SHA-256 `4ff5e2ee4e8a1bfe864a2102b178b8ef65a60b0c2aff24500b24dc40cddb3f89` |
| Verified physical packet | `attention-cache-pipeline-20261117T112139Z-daeb2e/invocation.json`, SHA-256 `8c44f55a0c6f403b7b948213873a6d91b358f58daf72bd64f09de3030476987b` |
| Physical record | [run.json](../../results/attention-cache-pipeline-20261117T112139Z-daeb2e/run.json), SHA-256 `bfecd146fe93cb3b6fe0c387a59e6c51f291f09290baaa567c9aa125fabda078` |

The [routed build](../../results/attention-cache-pipeline-build-20261117T105651Z/run.json) pins the full synthesis source and implementation reports. After the physical comparison, the original research circuit and weights were restored and all 320 BOS scores matched. Earlier results keep their original circuit pins.

### 17 November 2026 — adopt ff-down-pipeline-v1

Aidan selected **`ff-down-pipeline-v1`** as the next KV260 comparison baseline after Experiment 9. It overlaps the next read with the current multiply-accumulate in the feed-forward down projection. The model, clock, arithmetic, eight final-score lanes and cache stay fixed.

Across three fixed prompts at 50 MHz, time to first token fell 6.2–9.2%, decode rate rose 3.6–6.1%, and completion time fell 4.4–6.0%. Gross VCC_SOM energy per verified answer fell 4.9–5.0%. All 36 timed requests and 108 timing counters matched their references. The accepted implementation has 34,799 LUTs, 13,648 registers, 37 DSPs and 38 block RAM tiles. [Physical comparison](../../results/ff-down-pipeline-20261117T095726Z-1092a6/findings.md) · [Independent audit](../../results/ff-down-pipeline-20261117T095726Z-1092a6/audit-manifest.json)

| Component | Frozen identity |
| --- | --- |
| Variant source | [Manifest](variants/ff-down-pipeline-v1/manifest.json), SHA-256 `d8ef00248b7dc439911c0dc744e32103f9c0f3214666fc93c6c8d5f3be242d1b` |
| Generated feed-forward RTL | SHA-256 `9698ca6ecd09f2eeb97756775528e1b902da10eb2beb12a50378e5eefc91e56a` |
| Programming image | `gradiated-tiny-ff-down-pipeline-v1-50mhz.bit.bin`, SHA-256 `dbfa399e2a73a74d99032eb3970f322842da5b58b143d5b90e91abc67ca2d0b0` |
| Programming overlay | `kv260-ff-down-pipeline-program.dtbo`, SHA-256 `e6200d8e726d265d7cbbc62ad79e82c10042818abe313bad79e57b551cc059a7` |
| Verified physical packet | `ff-down-pipeline-20261117T095726Z-1092a6/invocation.json`, SHA-256 `3f9982c5994fcac542fa8ed908eafe2c339684660871ca5b5348c82fd813d66e` |
| Physical record | [run.json](../../results/ff-down-pipeline-20261117T095726Z-1092a6/run.json), SHA-256 `0ebaa4ce5b7ae2b4e3c63256aa6c1907826dacd92215934ddd6b0fd0336839c7` |

The [routed build](../../results/ff-down-pipeline-build-20261117T000146Z/run.json) pins the complete source and implementation reports. The KV260 held the original research circuit and weights after the physical comparison. This dated selection applies to subsequent comparisons. Earlier benchmark manifests and results retain their own pins.

### 16 November 2026 — adopt ff-exp-div-v1

Aidan selected **`ff-exp-div-v1`** as the comparison baseline for subsequent KV260 teaching experiments. It derives from the adopted eight-lane design and shortens three exact divisions in the feed-forward exponential. The frozen `chip-joke-text-20261109` W16A16 model, eight final-score lanes, numerical rules, context limit and 50 MHz target remain fixed.

The [physical comparison](../../results/ff-exp-div-20261116T230715Z-0969cc/findings.md) and [independent audit](../../results/ff-exp-div-20261116T230715Z-0969cc/audit-manifest.json) passed. On three prompts in one boot, completion time fell 9.2–12.1% and gross VCC_SOM energy per answer fell 10.2–10.8% with exact outputs. At 50 MHz, the routed implementation uses 34,785 LUTs, 13,646 registers, 37 DSPs and 38 block RAM tiles.

| Component | Frozen identity |
| --- | --- |
| Variant source | [Manifest](variants/ff-exp-div-v1/manifest.json), SHA-256 `5991b5472be92b0cab51f4422c52e9e1cfe443369909f967c9b8d8af8989934c` |
| Generated feed-forward RTL | SHA-256 `e6401554a7b4f44b60613880e4f0fd59756f9edf45acfa7fb0b81f4bfb0c1a64` |
| Programming image | `gradiated-tiny-ff-exp-div-v1-50mhz.bit.bin`, SHA-256 `8c4d35ed79feae3e655b6db0aabdac1f9773e7662c3fad92701a60fc01de1a1b` |
| Programming overlay | `kv260-ff-exp-div-program.dtbo`, SHA-256 `b6caab9c8671c01fc83c1b01f33c146d7865ea5d276f8ec0074c89d01d2b9bf5` |
| Verified physical packet | `ff-exp-div-20261116T230715Z-0969cc/invocation.json`, SHA-256 `97b043883e38a2ce11047b737968e84ceecd6ba6b6e035b712d844a94ad42bd8` |
| Physical run | [run.json](../../results/ff-exp-div-20261116T230715Z-0969cc/run.json), SHA-256 `5b0a9a277980aba69d1853aac6523ca7dfafc9fc0c3bba0082103ae1c22c8ec6` |

The [routed build](../../results/ff-exp-div-build-20261116T213813Z/run.json) pins the complete source closure and images. This research selection uses the audited candidate as the next comparison control. The original circuit and weights were verified at restoration. Earlier results and separately prepared benchmark manifests retain their original pins.

### 16 November 2026 — adopt logits-8-lanes-v1

Aidan adopted **`logits-8-lanes-v1`** as the selected circuit comparison baseline on 16 November 2026, after experiment 7. This supersedes scalar-div-v1 as the starting point for new experiments. Earlier versions, result records and their dated selection statements remain historical evidence. Adoption does not change the circuit currently loaded on the board or authorise new experiments.

This version includes the autonomous controller, prompt-score skipping, faster exact scalar multiplication and division, final-projection pipelining and eight final-score lanes. It derives directly from the verified four-lane circuit. The frozen chip-joke-text-20261109 W16A16 model, exact arithmetic, context limit, output selection and 50 MHz target remain unchanged.

The [physical comparison](../../results/logits-8-lanes-20261116T202250Z-44df9d/findings.md) and [independent audit](../../results/logits-8-lanes-20261116T202250Z-44df9d/audit-manifest.json) passed. Compared directly with four lanes, decode rate rose 1.1–1.7%, completion time fell 0.7–1.6% and measured gross VCC_SOM energy per answer/output token fell 0.66–1.05% across three pairs. The net design cost is four DSPs, 393 LUTs and 322 registers, with unchanged block RAM. Totals are 37 of 1,248 DSPs, 35,188 LUTs, 13,689 registers and 38 BRAM tiles. We select the fastest verified version for the teaching campaign, accepting this small resource increase. Four lanes remains a useful alternative, and no lost concurrent-user capacity has been measured. The small energy difference is scoped to these prompts and this board boot, not a general or whole-board energy guarantee.

| Component | Frozen identity |
| --- | --- |
| Variant source | [Manifest](variants/logits-8-lanes-v1/manifest.json), SHA-256 `5236089e0455414df2aa095e153667cda0e6615987f3884bef479bc9cda9545f` |
| Generated transformer | SHA-256 `dc5851764926a6b5e3638aea760eb025d86da844241497a175e125c6210d0e2d` |
| Tested programming file | `gradiated-tiny-logits-8-lanes-v1-50mhz.bit.bin`, SHA-256 `bdc134c65a151699d2ddd690b0ddc799cbd09edb688b8a7c4f0ecf7dd498c9e2` |
| Programming overlay | `kv260-logits-8-lanes-program.dtbo`, SHA-256 `a1bc5ea2bdbb02d29b1d9759da24be67594f9d0033c40483cfd47828cc16b1a7` |
| Captured software and execution packet | `logits-8-lanes-20261116T202250Z-44df9d/invocation.json`, SHA-256 `06340ed7c83556e17047ea9308a833ab94892d36a432a50a174440e4b117b5bb` |
| Physical run record | [run.json](../../results/logits-8-lanes-20261116T202250Z-44df9d/run.json), SHA-256 `8f826df934aa6940ef839638682300aae8aa49b8777474f01fe741b553bab536` |

The [build record](../../results/logits-8-lanes-build-20261116T190809Z/run.json) pins the full build evidence. The physical run pins the exact host software, source patch, workload and original-state restoration. Future comparisons use this candidate arm as their control, with the same software and measurement boundaries unless explicitly changed. Keep all previous source closures, images and results immutable. Selecting this baseline does not silently retarget prepared broader benchmark manifests, which remain pinned to their historical implementation until separately reviewed.

The original circuit and weights remain restored and verified. This decision ran no inference, simulation or build and made no board changes. Shared artifact backup remains pending. No commit, push or deployment is included.

### 16 November 2026 — adopt scalar-div-v1

Aidan selected **`scalar-div-v1`** as the working baseline for subsequent experiments. It derives from scalar-mul-v1 and replaces only the generic divider with exact two-bit-per-step division. Thirty-two calculation steps and one finish step replace 64 calculation steps. The frozen **chip-joke-text-20261109** model, multiplication, numerical rules, tables, cache layout, output selection, native reader and 50 MHz target remain unchanged. Both the [physical comparison](../../results/scalar-div-20261116T105755Z-3c2ae0/findings.md) and [independent audit](../../results/scalar-div-20261116T105755Z-3c2ae0/audit-manifest.json) passed.

The adoption trades 540 additional LUTs and 284 additional registers for 24–27% lower first-token time, 30–35% higher decode rate, 23–27% lower complete-request time and about 25% lower gross VCC_SOM energy per verified answer. DSP usage remains 30 and block RAM remains 36.5 tiles. Active module power stays around 3.12–3.13 W. Evidence covers three natural prompts on one board in one boot, with additional exact simulation and arithmetic tests. Whole-board energy, long-term stability and other models remain outside this result. The routed build retains 72 DSP pipeline advisories, with zero design-rule errors or critical warnings.

| Component | Frozen identity |
| --- | --- |
| Circuit source | [Variant manifest](variants/scalar-div-v1/manifest.json), SHA-256 `73123c2c753093e1e359de64a98b98e48471382ba4bd85758108ab7a78944f13` |
| Tested programming file | `gradiated-tiny-scalar-div-v1-50mhz.bit.bin`, SHA-256 `22f5d16ed47cf25c3c793d82ee18242b5b635f49e916a13a8b9ed750dd70fb0d` |
| Captured software and execution packet | `scalar-div-20261116T105755Z-3c2ae0/invocation.json`, SHA-256 `e6475419fd77096d5c1cd6b202d58bcd7d1bce626cef1abbfd853b04a381a9a1` |

The [build record](../../results/scalar-div-build-20261116T104711Z/run.json) pins implementation artifacts and resource use. The [physical record](../../results/scalar-div-20261116T105755Z-3c2ae0/run.json) pins software, workloads, measurements and original-circuit/weight restoration. Preserve these immutable sources and all earlier baselines. Adoption remains an explicit decision weighing correctness, speed, energy, resources and evidence scope. Alternative versions can remain useful for different constraints.

Adoption does not reprogram the board or rerun measurements. The original circuit and weights remain in their verified restored state. New work needs current state checks and a new reviewed packet. The next experiment is for discussion. Shared artifact backup remains pending. No commit, push or deployment is part of this decision.

### 16 November 2026 — adopt scalar-mul-v1

Aidan selected **`scalar-mul-v1`** as the working baseline for subsequent experiments. It derives from prefill-skip-v1 and replaces only the scalar multiplier with an exact four-bit-per-step implementation. The frozen **chip-joke-text-20261109** model, W16A16 numerical rules, division, tables, cache layout, output selection, host reader and 50 MHz clock are unchanged. Both the [physical comparison](../../results/scalar-mul-20261116T001133Z-268099/findings.md) and [independent audit](../../results/scalar-mul-20261116T001133Z-268099/audit-manifest.json) passed.

The adoption trades 20 additional DSPs and 818 additional LUTs for 27–32% lower first-token time, 24–30% higher decode rate, 22–24% lower complete-request time and 22.1–22.5% lower gross VCC_SOM energy per verified answer. Register usage falls by 884 and BRAM is unchanged. Active power is nearly unchanged. These results cover three prompts on one board in one boot, with additional exact simulation and arithmetic tests. They do not establish whole-board energy, long-term stability or suitability for every model. The routed build retains 72 unwaived DSP pipeline advisories and has no errors or critical warnings.

| Component | Frozen identity |
| --- | --- |
| Circuit source | [Variant manifest](variants/scalar-mul-v1/manifest.json), SHA-256 `46220377267d0dada7e2dbc57a4e2a159e644b2ed5ceed1923df0528e2a87f8a` |
| Tested programming file | `gradiated-tiny-scalar-mul-v1-50mhz.bit.bin`, SHA-256 `b361611b97d720b99c727103202905ad2229bcb8d5e06d0e78bad8cecffefffa` |
| Captured software and execution packet | `scalar-mul-20261116T001133Z-268099/invocation.json`, SHA-256 `8a220cce716949251602ebd7f67a9aa7ee79c018da72830698de99982306aee4` |

The [build record](../../results/scalar-mul-build-20261116T001040Z/run.json) pins implementation artifacts and resources. The [physical record](../../results/scalar-mul-20261116T001133Z-268099/run.json) pins software, workload, measurements and restoration. Preserve these immutable sources, outputs and all earlier baselines. Future adoption is an explicit decision weighing speed, energy, resource cost, correctness and evidence scope, not an automatic consequence of any improvement. Alternative versions can remain useful for different constraints.

Adoption does not reprogram the board or rerun measurements. The original circuit and weights were restored at the end of the accepted comparison, after which Aidan shut the board down for the night. A future run needs current power/boot/state checks and a new reviewed packet. The next experiment is still for discussion. Shared artifact backup remains pending. No commit, push or deployment is part of this decision.

### 15 November 2026 — adopt prefill-skip-v1

Aidan selected **`prefill-skip-v1`** as the working baseline for subsequent experiments. It retains autonomous prompt sequencing, token selection and decode, and omits only intermediate prompt vocabulary projections. The frozen model, numerical rules and 50 MHz clock are unchanged. The [physical comparison](../../results/prefill-skip-20261115T224422Z-754f19/findings.md) and [independent audit](../../results/prefill-skip-20261115T224422Z-754f19/audit-manifest.json) passed. First-token time fell about 13–15%, decode rate stayed unchanged and VCC_SOM module energy per verified completion fell 2.7–3.1% across three matched pairs. Active power was nearly unchanged. Scope remains three prompts, one board and one boot, with additional simulation boundary checks. Skipped projections cannot report saturation in their unused scores.

| Component | Frozen identity |
| --- | --- |
| Circuit source | [Variant manifest](variants/prefill-skip-v1/manifest.json), SHA-256 `c3fc573062521eb1f0e43e6b744afeaa6199b754dc36946f0a8a6c5645c814a1` |
| Tested programming file | `gradiated-tiny-prefill-skip-v1-50mhz.bit.bin`, SHA-256 `6ae36d72a8045c1dac2c7af28c840ab136c74e6e58360531bec51fde0370088a` |
| Captured software and execution packet | `prefill-skip-20261115T224422Z-754f19/invocation.json`, SHA-256 `b5859231b43bccfe5c14ea9a23825f12e26c4dbfb19162209e26621f8ec75dd7` |

The [build record](../../results/prefill-skip-build-20261115T224330Z/run.json) pins source, Vivado artifacts and resource usage. The [physical run](../../results/prefill-skip-20261115T224422Z-754f19/run.json) pins the tested host and raw evidence. These files remain immutable. Adoption changes the selected starting point, not historical results or the circuit currently loaded on the board. The original firmware and weights were restored and all 320 BOS scores checked. Verified build and measurement artifacts are on the Mac, with shared backup pending.

Experiment 3 branched from this version and changed only scalar multiplication implementation. The [scalar-mul-v1 physical comparison](../../results/scalar-mul-20261116T001133Z-268099/findings.md) passed, with faster first-token delivery and decode and lower VCC_SOM energy. The subsequent scalar-mul-v1 adoption is recorded above, retaining this earlier baseline and its measurements. Use the same host and measurement boundaries for both arms. Original, autonomous and prefill-skip versions remain separately reproducible. DSP sharing is a future experiment, not part of experiment 3.

### Earlier adoption — autonomous-v1

On 15 November 2026, Aidan approved **`autonomous-v1`** (`kv260-autonomous-v1`) as the baseline for subsequent FPGA circuit experiments. The [physical comparison](../../results/autonomous-prefill-decode-20261115T210134Z-97efcb/findings.md) and [independent audit](../../results/autonomous-prefill-decode-20261115T210134Z-97efcb/audit-manifest.json) support this decision: exact outputs passed, median completion time fell by about 17–21% across the three prompts, and gross VCC_SOM energy per answer fell by 19.6–19.9% across three matched pairs. Qualification covers one board boot and these workloads.

The model remains **`chip-joke-text-20261109`**, with its existing [benchmark freeze](../../models/baselines.json), W16A16 numerical rules, byte/hex encoding, greedy selection and 256-position context. The selected circuit runs at 50 MHz. It derives from the original `rtl/`, replacing only the AXI wrapper with prompt sequencing, token selection, feedback and output buffering. The separate `observer-v1` circuit is not its parent.

Exact baseline identity is defined by these preserved artifacts, rather than whichever files happen to be newest:

| Component | Frozen identity |
| --- | --- |
| Circuit source | [Variant manifest](variants/autonomous-v1/manifest.json), SHA-256 `b964dde00531a9cf65aa6121cfb1c36c321213d01b765d4a690e9da5fcb94980` |
| Tested programming file | `gradiated-tiny-autonomous-v1-50mhz.bit.bin`, SHA-256 `071f8cf91657fb5446e66754c28795faa52b92ca2e4aa6ddba71859b1396e3a9` |
| Captured software and execution packet | `autonomous-prefill-decode-20261115T210134Z-97efcb/invocation.json`, SHA-256 `d4614b800cf029b99e449e3428fca79d03034a96299842edd6c6f97e66ea9bf4` |

The [completed run record](../../results/autonomous-prefill-decode-20261115T210134Z-97efcb/run.json) locates the captured packet under repository-root `.agents/runtime/hardware/inference/outputs/` and pins its evidence manifest. The invocation pins the actual FPGA-controlled host path, including `autonomous_runtime.py`, `autonomous_comparison.py` and `autonomous_mmio.so`. The [build record](../../results/autonomous-build-20261115T204747Z/run.json) pins the build materials and resource costs. Preserve those exact sources, model payloads and programming file. Future changes get separate variant/run identities and record whether they branch from this baseline or another version.

Keep the original CPU-controlled circuit (`kv260-tiny-transformer-50mhz-conditioned-sealed`), its original-host and slice-host results, and the observer variant for historical comparisons. This decision selects the FPGA-controlled implementation for new circuit comparisons. It does not rewrite earlier results or their baselines. Subsequent adoption decisions should be dated here, retaining this entry.

Each new experiment follows the [measurement standard](../../experiments/measurement-standard.md), with the same FPGA-controlled host path on both sides unless host software is the declared intervention. Prepare a fresh reviewed execution packet for the current board state and boot. Historical warning anchors and session identifiers belong to their original runs. Preserve the selected circuit and inference routines while updating only explicitly reviewed run-specific setup and metadata. New workloads or measurement boundaries require their own identities.

The board remains in the original state restored after the accepted comparison. This adoption did not load a circuit, run an experiment, commit or push. Source changes remain local, and shared artifact backup remains pending.

## Local software checks

The pinned runtime lives at repository-root `.agents/runtime/hardware/inference/`. It is ignored by Git and currently recovered locally. The original inference checkout remains untouched.

```sh
hardware/research/inference/implementations/kv260/check.sh
hardware/research/inference/implementations/kv260/generative.sh verify
hardware/research/inference/implementations/kv260/generative.sh conditioned-chat --format fixed
```

These commands use the existing Mac environment. They do not configure the board. The software CLI uses a bounded worker and enforces the selected model hashes. Reproduction training is opt-in, never an implicit verification step.

Linux board packages and historical reports are preserved separately in the recovery archive. Embedded absolute paths identify the original run, not a promise that the report can be resumed on the Mac. New hardware runs need an explicit setup and fresh record. Historical packaged artifacts retain their original source hashes, even where the current consolidated tooling differs.
