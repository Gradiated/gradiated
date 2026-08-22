# Lamb Labs launch video: FPGA board identification

Date: 2026-08-04
Decision: The video board is frame-confirmed as the **AMD Kria KV260 Vision AI Starter Kit (SK-KV260-G)**. Treat Lamb Labs' KV260 result as an early FPGA proof of concept that appears closely based on public work, not as evidence that its custom board or ASIC is complete.

## Question and claim

Question: Which FPGA board is held up in the YouTube video `MhhY1Dy9ltE`, and which board should be considered for reproducing the 8-billion-parameter, low-power hardware/model co-design experiment?

Claim under test: the physical board is a specific, commercially purchasable FPGA development kit.

Scope: board identity, closely related public FPGA/LLM work, current official specifications, and reproducibility implications. Non-scope: validation of Lamb Labs' projected 20,000+ token/s or 63x intelligence-per-watt claims, and validation of an ASIC that is not publicly documented.

Falsification rule: reject the KV260 identification if a clear video frame shows a ZCU104-style full evaluation board (large green PCB with an FMC connector and DIMM) or an Alveo-style full-height PCIe card, or if Lamb Labs identifies a different board in primary material.

## Result

**Frame-confirmed identification: AMD Kria KV260 Vision AI Starter Kit, confidence 0.99.**

A user-supplied 4K clip covering 15--25 seconds was decoded at 0.25-second intervals. The unobstructed frames at approximately 17.5--18.5 seconds show the KV260's compact green carrier, K26 SOM/active-fan placement, edge-port cluster, mounting-hole pattern, and proportions. The frame lacks the ZCU104's large evaluation-board layout, DIMM, and FMC connector and lacks the Alveo U250's long PCIe-card form factor. This satisfies the original falsification rule in favor of KV260.

The inference is based on four mutually reinforcing facts:

1. YouTube oEmbed identifies the video as *Lamb Labs (YC S26) Launch* by Niki Kotecha. The visible HD thumbnail text includes the startup's `20,000+ tokens/second` and `63x intelligence per watt` claims.
2. Lamb Labs cofounder Thomas Lanning publicly forked `adamgallas/llama-fpga` on 2026-07-18, two weeks before the 2026-08-02 video publication. That repository supports the KV260, ZCU104, and Alveo U250 for LLaMA2-7B FPGA inference.
3. The 2025 Hummingbird paper is an unusually exact match to the user's description: it evaluates 4-bit LLaMA3-8B on the KV260 and ZCU104, reports a 42% power reduction, and reports the KV260 as the lowest-power/highest-power-efficiency implementation in its comparison (4.8 token/s, 3.81 W derived from Vivado reports, normalized performance per watt 1.44). The ZCU104 result is faster (8.6 token/s) but reported at 7.09 W and power efficiency 1.39.
4. AMD describes the KV260 as a compact, purchasable starter kit with a K26 SOM, carrier card, active thermal solution, and 4 GB DDR. Its dimensions (119 x 140 x 36 mm) fit a board readily held in one hand. Current official MSRP is $249.

### Rejected competing explanations

- **ZCU104.** It is also used by Hummingbird and the public repository, but the frame does not show its DIMM/FMC evaluation-board layout.
- **Alveo U250.** It is a full-height PCIe card and is physically incompatible with the frame.

## Company and founder maturity assessment

**Assessment: recent company and recent FPGA integration, not a publicly evidenced multi-year FPGA/ASIC research program. Confidence 0.85.**

- Y Combinator lists Lamb Labs as founded in 2026 by Niki Kotecha and Thomas Lanning. The company launch occurred in the S26 batch.
- Kotecha's relevant prior work is substantive but software/model-side: a Cambridge MEng/BA in Chemical Engineering, an Imperial AI PhD focused on reinforcement learning, graph neural networks, process control, and supply-chain optimization, with publications beginning in 2023. No prior FPGA, RTL, physical-design, or tapeout record was located.
- Lanning's public CV records a Mathematical Physics BSc from Edinburgh and a 2023--2024 MSc in Mathematical and Theoretical Physics from Oxford, plus Python/ML and CERN-data projects. No prior FPGA, RTL, board-design, or semiconductor role was located in the CV or pre-launch public repositories.
- Lanning forked `adamgallas/llama-fpga` on 2026-07-18. As retrieved on 2026-08-04, the fork is zero commits ahead of upstream and four commits behind. Its public HEAD is an upstream commit, with no founder-authored public delta.
- The upstream project already implements 4-bit LLaMA2-7B on KV260 at about 5 token/s. Lamb Labs later reports 5.5 token/s, 3.75 GB of model weights, and approximately 19 GB/s usable memory bandwidth. The close identity of board, model size, quantization footprint, and throughput supports reproduction/adaptation of the public accelerator as the leading explanation. A private rewrite or material unpublished modification remains possible.
- Lamb Labs' own site labels diffusion post-training and the KV260 accelerator as shipped, its custom `Merino` FPGA/memory board as in production/bring-up, and custom ASICs as the endgame. The published Merino asset is a CAD/layout rendering, not a photograph of an assembled and measured board.
- The site's `20,000+ token/s` and `63x intelligence-per-watt` figures are targets for the future ASIC. They are not measurements from the KV260. Its `2x` diffusion-model claim is presently illustrated by a single demo; no public weights, code, benchmark suite, quality study, paper, or independent reproduction was located. The site says Hugging Face availability is coming soon.

### Reproducibility judgment

- **KV260 demonstration:** moderately reproducible for an experienced FPGA/Vivado developer using the upstream `llama-fpga` project and its verified KV260 boot image. It is not turnkey for a hardware beginner because the documentation is limited, the generated HDL is difficult to read, prefill is not accelerated, context is limited to 1,024 tokens, and model preparation/toolchain setup remain necessary.
- **Their custom Merino board:** not currently reproducible from public material; only a rendering and high-level description are public.
- **Their diffusion model conversion:** not currently reproducible; promised artifacts and full evaluations are absent.
- **Their ASIC target:** not reproducible and not yet demonstrated in silicon.

The two power statements can be reconciled analytically: a later founder post reports 4.4 W idle and 10.3 W while decoding, so the incremental decode power is 5.9 W, consistent with the earlier shorthand claim of "only 6 W." Total board power during decoding is about 10.3 W under that account, not 6 W.

## Purchase recommendation for direct inference-optimization learning

**Recommendation: buy the KV260 if the learner wants to start directly with inference accelerators and accepts a steep toolchain. Confidence 0.90.** Do not substitute a Basys 3 or Arty A7 merely because it is labeled beginner-friendly: those boards are better for introductory digital-logic courses, but they provide a less direct path to memory-bound, multi-billion-parameter inference.

Why the KV260 fits this goal:

- 256K system logic cells, 1.2K DSP slices, 144 BRAM blocks, 64 UltraRAM blocks, 4 GB DDR, and an Arm processing system expose useful accelerator tradeoffs rather than toy-scale logic only.
- The board supports handwritten RTL, packaged AXI kernels, HLS C/C++, DMA, bare-metal control, and Linux/PYNQ-style host integration.
- `llama-fpga` provides an immediate 4-bit LLaMA2-7B decode baseline on the exact board, including Vivado design, XSA, SDK C, and a verified KV260 image.
- `TeLLMe_FPGA_2026` provides a second, more research-oriented baseline with public HLS C/C++ for end-to-end ternary BitNet prefill and decode, PYNQ runtime, golden-data verification, and an interactive chatbot path.
- AMD FINN provides a maintained open quantized-neural-network dataflow framework for learning architecture generation, arbitrary precision, folding, and throughput/resource tradeoffs, although it is not an LLM-first flow.

Limitations:

- The KV260 is not an introductory trainer: few switches/LEDs are exposed, the Kria boot stack and PS/PL boundary add complexity, and Vivado/Vitis builds are large and slow.
- FPGA work teaches RTL, cycle-level microarchitecture, verification, timing closure, bandwidth, fixed-point arithmetic, and resource mapping. It does not by itself teach transistor design, standard-cell characterization, SRAM macros, clock-tree synthesis, DRC/LVS, or foundry tapeout.
- The starter-kit box does not include a power supply, microSD card, cables, or peripherals. The minimum practical acquisition is `SK-KV260-G`, a supported 12 V/3 A supply, a 16 GB or larger microSD card, USB-A-to-micro-B cable, and Ethernet cable. AMD's official 36 W supply is `HW-PSA01-SK-G`; its accessory pack is `HW-BACCP01-SK-G`.

Suggested experiment sequence:

1. Reproduce the published `llama-fpga` KV260 baseline and record exact tokens/s, time to first token, maximum context, accuracy/quality identity, PL utilization, clock rate, memory bandwidth, idle power, and load power.
2. Build a small INT8 then INT4 matrix-vector engine in HLS or RTL with AXI DMA. Compare arithmetic intensity, burst length, tiling, double buffering, and DSP/LUT implementations.
3. Modify one controlled dimension in the LLM accelerator: weight packing, burst scheduler, buffering, quantization, attention fusion, or prefill dataflow. Require golden-output correctness before accepting speedups.
4. Reproduce TeLLMe's ternary prefill/decode path and compare its table-lookup matmul against DSP-based INT4 under the same board-level power boundary.
5. After the FPGA loop is understood, port one small accelerator block through an open ASIC flow such as Yosys/OpenROAD with an open PDK to learn which FPGA optimizations transfer to standard-cell silicon and which do not.

### Board alternatives and upgrade triggers

No second FPGA board is recommended initially.

- **ZCU104:** a meaningful embedded-FPGA upgrade because the public LLM project can split weights across PS and PL memory and reports approximately 8--9 token/s, but AMD's current MSRP is $1,678. It is not proportionally more educational than KV260 for a first inference project.
- **Alveo U250/U280-class card:** useful later for multi-channel DDR or HBM experiments, but requires a PCIe desktop/server, substantially more power and money, and is incompatible with a laptop-only physical setup. Buy only when memory-channel scaling is the explicit experiment.
- **Basys 3, Arty A7, PYNQ-Z2, or Zybo Z7:** easier for introductory FPGA coursework but materially smaller or less suitable for the public multi-billion-parameter LLM baselines. They are lateral moves or downgrades for this objective.
- **Versal/AI Engine or HBM boards:** consider only after the KV260 has been exhausted and there is a concrete experiment requiring AI Engines, HBM, or much larger fabric; otherwise the added tool and architectural complexity obscures rather than accelerates learning.

The upgrade condition is evidence-based: buy another board only after an experiment is demonstrably blocked by KV260 capacity, memory bandwidth, I/O, or lack of a specific hard block, and the next board removes that exact bottleneck.

### macOS control plane and remote Linux build host

A MacBook Pro is suitable as the control plane: edit source, use Git, flash the microSD card, access UART, SSH into the KV260, open its Jupyter/PYNQ interface, collect telemetry, and visualize results. AMD Vivado/Vitis 2026.1 does not list macOS as a supported host; supported development hosts are Windows and x86-64 Linux distributions.

Recommended remote build host:

- x86-64 Ubuntu 22.04.5 LTS or a supported Ubuntu 24.04 point release
- 64 GB RAM for comfortable embedded/HLS work; AMD lists 32 GB minimum and 64 GB recommended
- 8--16 vCPUs
- at least 250 GB persistent SSD, with 500 GB preferable for multiple tool versions and build artifacts; AMD lists up to 200 GB for a full Vitis installation
- persistent storage for the tool installation and Vivado IP cache so every rental session does not start from zero

The remote host does not need an FPGA attached for simulation, HLS, synthesis, implementation, or bitstream generation. Transfer the `.bit`, `.xsa`, software, and logs to the Mac or directly to the KV260 over SSH. The exception is interactive Hardware Manager/ILA/JTAG debugging: the KV260 exposes integrated UART and JTAG through its FTDI USB interface, so that workflow needs a supported host with USB/network reachability to the physical board. A small local x86 Linux machine can be added later if remote USB access becomes a recurring bottleneck.

Minimum bench equipment:

- KV260 `SK-KV260-G`
- supported 12 V/3 A supply; AMD official `HW-PSA01-SK-G` is 36 W
- 16--32 GB quality microSD card and a Mac-compatible card reader
- USB-C-to-micro-B data cable, or USB-A-to-micro-B plus a USB-C adapter, for integrated UART/JTAG
- Ethernet cable and, if the Mac lacks Ethernet, a USB-C Ethernet adapter or a connection through the same router/switch

Useful but optional:

- inline 12 V DC power meter/data logger for total input power and joules/token
- inexpensive logic analyzer or oscilloscope only when external interfaces are being developed; Vivado ILA covers many internal signals
- second microSD card for a known-good recovery image

Not required initially: external JTAG programmer, camera, monitor, keyboard, standalone oscilloscope, or another FPGA board.

## Important qualification for a purchase decision

The public FPGA numbers do **not** establish 20,000 token/s on the KV260. Hummingbird reports 4.8 token/s for LLaMA3-8B on KV260 and 8.6 token/s on ZCU104. The launch-video overlay is therefore most plausibly an ASIC target/projection or a different metric, not demonstrated KV260 throughput.

The founder-forked open-source `llama-fpga` repository targets LLaMA2-7B with 4-bit AWQ. Its README marks the KV260 path as currently buggy, while it provides ZCU104 and Alveo U250 projects. Hummingbird's exact LLaMA3-8B implementation was not located in a public repository. Buying the KV260 is suitable for learning and architecture experiments, but should not be treated as a turnkey reproduction.

The Hummingbird power figures are reported as derived from Vivado reports. They are not measured wall-power figures for a complete starter-kit setup and should not be compared directly with board-level or system-level measurements without fresh instrumentation.

## Acquisition history and remaining uncertainty

The requested full-video download could not be completed directly from this environment. YouTube returned `Sign in to confirm you're not a bot` to yt-dlp and a clean, isolated Chromium profile. No authentication cookies, CAPTCHA bypass, or personal browser profile were used. The user subsequently supplied a 4K 15--25 second clip, which resolved the board-identity uncertainty.

Remaining uncertainty concerns provenance of Lamb Labs' private implementation, not board identity. Public history cannot rule out unpublished FPGA/ASIC work, contractors, advisors, or private repositories.

## UK acquisition check (Cambridge)

Checked 2026-08-04 at 15:00 BST. Inventory and delivery promises below are vendor-reported and can change between page retrieval and checkout. The 8--16 week figures shown by distributors are manufacturer/factory replenishment lead times; they do not apply to units already shown in stock.

- **Fastest identified option:** Farnell UK, order code `4690049`, reported 20 units of `SK-KV260-G` in stock at GBP 210.60 ex VAT / GBP 252.72 inc VAT. Farnell advertised next-business-day express delivery by 13:00 for orders before 18:00, with the final Cambridge delivery promise calculated at checkout.
- **Best immediate fallback:** DigiKey UK, part `122-SK-KV260-G-ND`, reported about 400 units in stock at GBP 212.67 ex VAT / GBP 255.20 inc VAT. DigiKey stated that UK orders are typically delivered within 48 hours and that orders over GBP 65 ship free. Select the UPS DDP option if offered so duty and customs are prepaid; other carriers may use CPT terms.
- **Second fallback:** Mouser UK, part `217-SK-KV260-G`, reported 126 units available for immediate dispatch at GBP 230.87 ex VAT. Mouser stated that most UPS/FedEx/DHL orders ship the same day and that the UK storefront uses DDP terms, but it did not expose a Cambridge arrival date without checkout.
- **Power/accessories:** the starter kit's power supply is sold separately. Farnell reported 77 `HW-BACCP01-SK-G` accessory packs in stock with next-business-day express eligibility at GBP 58.91 ex VAT / GBP 70.69 inc VAT. The pack includes the official supply, micro-USB and Ethernet cables, HDMI cable, microSD card/adapter, and camera. For an inference-only setup, DigiKey reported 59 standalone `HW-PSA01-SK-G` supplies in stock at GBP 24.71 ex VAT / GBP 29.65 inc VAT; a microSD card and data cable would still be required.

Purchase recommendation: for the least-friction same-day order, buy the board and full accessory pack from Farnell before its stated cutoff, after confirming the Cambridge postcode still shows next-business-day express at checkout. The reported combined total is approximately GBP 323.41 inc VAT before any express-delivery surcharge. Do not substitute a standalone K26 SOM, KR260, or a similarly named carrier board for the `SK-KV260-G` if the goal is compatibility with the identified KV260 work.

## Sources

| Source | Publication/revision | Retrieved | Evidence type | Relevance |
|---|---:|---:|---|---|
| https://www.youtube.com/watch?v=MhhY1Dy9ltE | Published 2026-08-02 per public page metadata | 2026-08-04 | Primary video metadata and thumbnails | Video identity and visible launch claims |
| https://www.linkedin.com/posts/niki-kotecha_were-building-ultra-fast-ultra-low-power-activity-7475939701007290368-HmVc | 2026 launch post | 2026-08-04 | Primary company/founder claim | Lamb Labs' sub-1 W product direction |
| https://github.com/thomas-lanning/llama-fpga | Fork created 2026-07-18 | 2026-08-04 | Primary public development activity | Cofounder's FPGA/LLM repository selection |
| https://github.com/adamgallas/llama-fpga | README current at retrieval | 2026-08-04 | Primary open-source implementation | Supported boards, model, speed, limitations |
| https://github.com/UCI-CORSA/TeLLMe_FPGA_2026 | FPGA 2026 artifact, current at retrieval | 2026-08-04 | Primary open-source research artifact | KV260 PYNQ runtime, HLS source, prefill/decode verification |
| https://github.com/Xilinx/FINN | Current at retrieval | 2026-08-04 | Primary AMD/Xilinx open-source framework | Quantized dataflow accelerator learning path |
| https://www.ycombinator.com/companies/lamb-labs | Current company profile and launch | 2026-08-04 | Primary/accelerator-hosted founder claims | Founding year, founders, roadmap, targets |
| https://lamb-labs.com/ | Current company site | 2026-08-04 | Primary company claims and artifacts | Product stages, FPGA claim, Merino render, ASIC targets |
| https://www.linkedin.com/posts/thomas-lanning_getting-the-board-warmed-up-only-6w-to-ugcPost-7484439356724731904-NmGn/ | Founder post, approximately July 2026 | 2026-08-04 | Primary founder claim | 7B model and 6 W incremental-power shorthand |
| https://www.optimlpse.co.uk/author/niki-kotecha/ | Current profile | 2026-08-04 | Primary research-group profile | Kotecha education and RL research focus |
| https://github.com/thomas-lanning/portfolio | Public portfolio, last pushed 2025-05-31 | 2026-08-04 | Primary founder portfolio/CV | Lanning education and pre-company work |
| https://arxiv.org/abs/2507.03308 | v2, 2025-10-17 | 2026-08-04 | Primary research paper; vendor-tool-derived power | Exact LLaMA3-8B results on KV260/ZCU104 |
| https://www.amd.com/en/products/system-on-modules/kria/k26/kv260-vision-starter-kit.html | Current product page | 2026-08-04 | Vendor-reported | KV260 part number, dimensions, memory, MSRP |
| https://docs.amd.com/r/en-US/ug1089-kv260-starter-kit | Rev. 1.4, 2025-06-25 | 2026-08-04 | Vendor documentation | Interfaces, boot flow, tools integration, box contents |
| https://www.amd.com/en/products/system-on-modules/kria/k26/kv260-vision-starter-kit/power-supply-adapter.html | Current product page | 2026-08-04 | Vendor-reported | Official 12 V, 36 W supply identity |
| https://docs.amd.com/r/en-US/ug1742-vitis-release-notes/Installation-Requirements | Vitis 2026.1, 2026-06-23 | 2026-08-04 | Vendor documentation | Supported host OS, RAM, and disk requirements |
| https://xilinx.github.io/PYNQ_Bootcamp/board-setup-image-creation.html | Current at retrieval | 2026-08-04 | Primary AMD/Xilinx training material | KV260 PYNQ setup and remote Jupyter access |
| https://www.amd.com/en/products/adaptive-socs-and-fpgas/evaluation-boards/zcu104.html | Current product page | 2026-08-04 | Vendor-reported | ZCU104 identity and MSRP |
| https://www.amd.com/en/products/accelerators/alveo/u250/a-u250-a64g-pq-g.html | Current product page | 2026-08-04 | Vendor-reported | U250 form factor, power, lifecycle guidance |
| https://uk.farnell.com/amd/sk-kv260-g/vision-ai-startr-kit-arm-cortex/dp/4690049 | Live product page | 2026-08-04 15:00 BST | Distributor-reported, time-sensitive | UK stock, price, and next-business-day delivery claim |
| https://uk.farnell.com/amd/hw-baccp01-sk-g/basic-accessory-pack-ai-starter/dp/4690048 | Live product page | 2026-08-04 15:00 BST | Distributor-reported, time-sensitive | Accessory-pack stock, contents, price, and delivery claim |
| https://www.digikey.co.uk/en/products/detail/amd/SK-KV260-G/13985269 | Live product page | 2026-08-04 15:00 BST | Distributor-reported, time-sensitive | UK-facing stock, VAT price, shipping, and incoterms |
| https://www.digikey.co.uk/en/products/detail/amd/HW-PSA01-SK-G/14111903 | Live product page | 2026-08-04 15:00 BST | Distributor-reported, time-sensitive | Standalone official supply stock and price |
| https://www.mouser.co.uk/ProductDetail/AMD-Xilinx/SK-KV260-G | Live product page | 2026-08-04 15:00 BST | Distributor-reported, time-sensitive | Immediate-dispatch fallback stock and price |

## Reproduction details

Runtime evidence directory (ignored): `.agents/runtime/youtube-board-MhhY1Dy9ltE/`

Key commands:

```sh
uvx --from yt-dlp yt-dlp --js-runtimes node --dump-single-json --no-playlist \
  'https://youtube.com/watch?v=MhhY1Dy9ltE'

curl -L --fail --silent --show-error \
  'https://www.youtube.com/oembed?url=https%3A%2F%2Fwww.youtube.com%2Fwatch%3Fv%3DMhhY1Dy9ltE&format=json'

for index in 1 2 3; do
  curl -L --fail --silent --show-error \
    "https://i.ytimg.com/vi/MhhY1Dy9ltE/maxres${index}.jpg" \
    -o ".agents/runtime/youtube-board-MhhY1Dy9ltE/maxres${index}.jpg"
done

gh api repos/thomas-lanning/llama-fpga
gh api repos/thomas-lanning/llama-fpga/readme -H 'Accept: application/vnd.github.raw+json'
```

Artifact hashes:

- `maxresdefault.jpg`: `448c10b4f624795f95f67a03b033bde64c7a05ac99ab4b95cab7000d668b72d5`
- `maxres1.jpg`: `acc5f4c8798ae4a4c637723eaad6da37db98bbdc43ddd97ded38e8ebdb2a1e6f`
- `maxres2.jpg`: `e18cacef81d19cb13d15b3a9bf746035ba823ee0c88cd6dd063e005337bf4f50`
- `maxres3.jpg`: `2be73bf36261e5512101ba005b710d9c5e6aa671e305e0bfa06aec3d8d3f2472`
- `hummingbird.pdf`: `1d0c9d601f45699e3cb326f2c791a9c54c12249a108f12b62ef770d5b62e3b2e`
- User-supplied `mhhY1Dy9ltE_15-25_4k_exact.mkv`: `7fbe12a2c190fa36485ea4e3a37b2e93abeeaf813e47e48d25aa7b714256fe3b`
- Extracted `original-18.25s.jpg`: `070aa13ffd90aab297eba805cb291125c7c0323d64d6d0db524f88c1b36e2463`
- Lamb Labs site application asset: `aaea67395566aa2604fcad075e25a591577bbc6ea3ce12311ff604685e8c1516`
- Lamb Labs Merino board rendering: `d6f5c6309bca208bbf907be23ff9bb250a7e681dba45d4110b220c16236ae8ac`
- Thomas Lanning public CV: `e53f34bab54173b2f0372551ffadbd5f5cff9d1328b3405323757a73c3b456e3`

## Next action and kill condition

Next action: monitor the promised Hugging Face release, independent evaluation, a populated Merino-board bring-up photo, and any ASIC tapeout/foundry evidence. Reassess maturity when one of those artifacts appears.

Kill condition: do not treat the 20,000+ token/s or 63x claims as achieved until measured silicon results identify the model, quality, precision, batch/context, chip process, system boundary, and power methodology.
