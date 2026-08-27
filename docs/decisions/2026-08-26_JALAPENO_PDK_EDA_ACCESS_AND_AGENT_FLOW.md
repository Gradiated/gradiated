# Jalapeño, PDK, EDA access, and agent workflow

Date: 2026-08-26

## Decision

Use open tools and a public or partner PDK for the first evidence cycle. Seek commercial EDA access through a startup, European Chips Design Platform, university, or design-house route only after the workload and architecture show a strong measured advantage.

Do not claim that a simulated Kimi K3 chip is tapeout-ready until it passes a foundry-qualified PDK flow, signoff, and silicon validation.

## What PDK means

PDK means Process Design Kit. It is the foundry-specific data that lets EDA tools model and check a process. It normally includes process rules, layer definitions, transistor models, standard-cell libraries, timing and power views, extraction data, DRC/LVS/DFM decks, and approved IP or macro views.

GF describes PDKs as models, rules, and libraries that describe process details to EDA tools. TSMC describes a production PDK as including symbols, PCells, netlisting, technology files, and flow support through extraction and signoff.

## What is public about Jalapeño

OpenAI states that it designed Jalapeño from scratch around its model, kernel, serving, memory, and networking requirements. It names Broadcom for silicon implementation and networking, and Celestica for board, rack, and system integration. OpenAI also states that the design reached tapeout in nine months and that OpenAI models accelerated parts of design and optimisation.

OpenAI does not publicly name the EDA vendors, foundry, process node, PDK version, physical design methodology, or exact license arrangement. The following is therefore an inference: a production Jalapeño program almost certainly used commercial EDA tools and a foundry-qualified PDK, with Broadcom or another implementation partner owning much of the physical-design and signoff execution. This inference is not evidence that the flow used Cadence, Synopsys, or Siemens specifically.

## Can agents use production EDA?

Yes. The safe model is an agent-controlled, approval-gated batch flow:

1. Agent writes or edits RTL, constraints, tests, kernel mappings, and tool scripts.
2. A runner launches lint, simulation, formal checks, synthesis, place and route, extraction, timing, power, and physical verification.
3. The agent parses reports and proposes the next experiment.
4. A human reviews architecture changes, IP and PDK use, waivers, signoff, and tapeout decisions.

Commercial EDA is usually scriptable through Tcl, Python, command-line jobs, APIs, and license-server workflows. It is not generally agent-native, but it is automatable. Cadence and Synopsys now also market agentic EDA products. These vendor claims show commercial support for agent workflows, but they do not remove the need for engineering review.

The agent must run inside the controlled design environment. PDK files, foundry rules, licensed IP, and customer data must not leave that environment. The agent should never approve a waiver or release GDS without a human gate.

## Access routes for a UK startup

The practical routes are:

- Open flow: Yosys, Verilator, OpenROAD, KLayout, Magic, Netgen, and an open PDK such as SKY130, GF180, or IHP SG13G2. This is suitable for learning, architecture, RTL, and relative PPA. It is not a substitute for an advanced-node production PDK.
- EUROPRACTICE: UKRI-STFC operates the UK service. It supports SMEs and startups with design and fabrication services. Its public 2026–2027 academic price list shows low-cost access to bundled Cadence and other tools, but academic and commercial eligibility differs. Treat the listed prices as a route for eligible members, not a direct startup quote.
- EuroCDP: the European Chips Design Platform offers startups and SMEs access to EDA, IP, training, testing, packaging, fabrication, and design enablement. It advertises nominal-cost incubation and preferential commercial rates. Confirm that the company is eligible as a UK organisation under the current Chips Joint Undertaking rules.
- Vendor startup programs: Synopsys advertises a browser-based EDA-as-a-Service startup program for qualifying companies. Siemens advertises Cre8Ventures cloud labs for startups. Cadence offers managed cloud and partner-hosted EDA environments. These require vendor screening and a quote.
- Design house or foundry partner: this is the normal route for an advanced AI ASIC. The partner provides the PDK, licensed IP, implementation, signoff, package, test, and foundry relationship. The startup should own the workload contract, architecture, compiler/runtime, and acceptance tests.

## Cost planning

Exact commercial EDA prices are normally quote-based. The following bands are planning estimates, not vendor quotations.

| Route | Planning view |
| --- | --- |
| Open tools and open PDK | £0 software licence. Budget for compute, engineering, and test hardware. |
| Academic access | Often nominal. EUROPRACTICE publishes, for example, a 2026–2027 Cadence IC package at €1,890 one-off for the first five licences plus €1,905 per site per year for academic members. |
| Startup programme or European platform | Case-by-case. It can reduce licence cost, but eligibility and scope control the price. |
| Direct commercial EDA | Usually a serious six-figure annual budget for a useful multi-tool flow, and more for several users, advanced-node options, compute, support, and signoff. Obtain quotes from Cadence, Synopsys, and Siemens after fixing the target foundry and node. |
| Advanced AI ASIC first silicon | Multi-million-pound programme risk. Siemens gives US$20–30 million as an example range for first silicon at advanced technologies. Packaging, HBM, SerDes, IP, verification, staff, masks, and respins can dominate the EDA licence cost. |

The low-cost route can prove architecture. It cannot prove advanced-node frequency, power, yield, HBM behaviour, or package thermals.

## Recommended operating model

Copy the useful part of the Jalapeño model, not its undisclosed tool list:

- Build a workload and serving specification for Kimi K3.
- Measure the same workload on B300 and record power, latency, throughput, memory traffic, and system limits.
- Search architectural choices with the Foundry ledger, Timeloop/Accelergy, SCALE-Sim, and network simulation.
- Implement a small RTL accelerator slice and validate it with Verilator and formal checks.
- Move the winning slice to a real PDK flow through a partner.
- Use the agent to explore candidates and parse results. Keep architecture, PDK, signoff, and tapeout decisions under human control.

The current repository evidence remains analytical and uncalibrated. The correct investor claim is therefore “a measured software baseline plus a falsifiable hardware hypothesis,” not “a proven better chip.”

## Sources

- OpenAI, [Jalapeño announcement](https://openai.com/index/openai-broadcom-jalapeno-inference-chip/)
- OpenAI, [Jalapeño first results](https://openai.com/index/jalapeno-first-results/)
- GlobalFoundries, [Process Design Kits](https://gf.com/design-support/process-design-kits/)
- TSMC, [5nm design infrastructure and PDK certification](https://pr.tsmc.com/english/news/1987)
- EUROPRACTICE, [2026–2027 tool pricing](https://www.europractice.stfc.ac.uk/tools/pricing.html)
- EUROPRACTICE, [SME and startup services](https://www.europractice.stfc.ac.uk/europractice_com/)
- EuroCDP, [services for startups and SMEs](https://eurocdp.eu/services/)
- Synopsys, [Startup Program](https://www.synopsys.com/cloud/startup-program.html)
- Cadence, [Cerebrus AI Studio](https://www.cadence.com/en_US/home/tools/digital-design-and-signoff/soc-implementation-and-floorplanning/cadence-cerebrus-ai-studio.html/)
- Siemens, [EDA AI System](https://eda.sw.siemens.com/en-US/eda-cloud-solutions/eda-ai-system/)
- Siemens, [Cre8Ventures](https://resources.sw.siemens.com/en-US/cre8ventures/)
