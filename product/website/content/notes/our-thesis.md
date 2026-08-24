---
title: Thesis
description: Inference should be a choice, not a constraint.
date: 2026-07-13
---

# Thesis

AI is moving from software that responds to people, to software that keeps working when nobody is there. As models get smarter and more applications connect them to real-world work, the world is going to have a near-insatiable demand for inference.

Intelligence is comparable to the invention of electricity. Factories initially replaced steam engines with electric motors to carry out the same work at reduced cost. But once electricity became cheap enough, it reorganized industry: refrigeration, elevators, radios, air conditioning, and home appliances followed. Demand for power rose enormously. We think there will be near-unlimited demand for inference—likely on a far more dramatic scale, because of what AI can unlock. AI is still at the start of this journey. In coding, for example, models mostly emulate a human developer and generate lots of iterative pull requests. The overall design of software products has not changed entirely, _yet_.

The first part of that transformation is longer-running work moving to the cloud. Software is starting to shift from reactive to proactive: agents can research, plan, use tools, and keep working for hours without a human waiting for each response.

Inference today is not built for those cloud tasks. They can run for hours without human interaction and tolerate much higher latency. For them, _efficiency_ is the priority, not _latency_. Current inference is poorly set up for this. Ask any developer and they will tell you that everything is heading in this direction.

Gradiated is a harness for this kind of work, with an API underneath. Developers give the harness a task, tools, a budget, a deadline, and a quality bar. It plans, runs, and revises the work; the API lets them control the cost and latency tradeoffs beneath it. The goal is simple: use the right model, at the right cost, for each part of the job.

Our approach is to optimize every layer of the vertical stack. The product is a developer tool—not infrastructure for its own sake, in the same way Stripe is a developer tool rather than a fintech company. Underneath are the software, infrastructure, and eventually chip design needed to make those runs cheaper and more capable. As with any engineering task, optimizing across the whole stack is how to win. Gradiated will go much deeper from the start.

## Inference systems and hardware

We've already made significant progress in inference systems research. Take GLM 5.2 as an example. Today, inference is fundamentally memory-bandwidth bound rather than compute-bound. In practice, only around 3% of the model's parameters are responsible for roughly 70% of the computation during inference. That changes how you should think about hardware design. Rather than building a general-purpose accelerator, you can architect a chip specifically for this workload—for example, pairing around 20GB of ultra-high-bandwidth memory dedicated to the hot working set used in matrix multiplication with approximately 380GB of lower-cost memory for the remaining parameters. By matching the memory hierarchy to the model's access patterns, you dramatically reduce bandwidth bottlenecks while substantially lowering the cost of inference.

The optimal architecture changes as models evolve. A dense model like GLM 5.2 has very different requirements from a sparse mixture-of-experts model such as Kimi K2, where only a subset of experts are active on each forward pass. Those models benefit from different memory layouts, routing mechanisms, interconnect topologies, and scheduling strategies. There is unlikely to be a single "best" accelerator for every frontier model.

This is why we're building a full end-to-end simulation environment spanning both hardware and software. Instead of designing chips or software in isolation, we can co-design compilers, runtimes, memory hierarchies, and silicon around the model architectures we serve. The simulator lets us explore architectural trade-offs before tape-out, optimize across the entire stack, and rapidly adapt as new model architectures emerge. Rather than chasing yesterday's workloads, we're designing inference infrastructure that evolves alongside the models themselves.

There will be challenges. Chip design is slow and the supply chain is difficult. Software alone is enough to win right now, but getting the full stack right is key to building a trillion-dollar company—at which point we are directly competing with Nvidia.

If Gradiated succeeds, exactly the right intelligence will be provided for every task. That will make us the leading provider, because it means we outperform every provider.

So the plan is:

- Ship cheaper inference for cloud tasks with lower latency needs. Use software to achieve this while making margin in the early days.
- Build chips at scale to provide more inference flexibility than anyone else can provide.
- As we build expertise and distribution, expand into all of inference.
