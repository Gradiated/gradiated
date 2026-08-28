export type Job = {
  slug: string;
  title: string;
  team: string;
  location: string;
  summary: string;
  purpose: string[];
  responsibilities: string[];
  problems: string[];
  requirements: string[];
  notFor: string[];
};

export const jobs: Job[] = [
  {
    slug: "founding-inference-research-engineer",
    title: "Founding Inference Research Engineer",
    team: "Inference Research",
    location: "Cambridge, London",
    summary:
      "Build and optimize the complete inference stack for open-weight models on existing hardware.",
    purpose: [
      "The best inference system does not come from one isolated optimization. Model structure, numerical formats, kernels, memory, scheduling, and serving affect each other.",
      "You will work across these layers. You will turn research ideas into measured systems that run real models.",
    ],
    responsibilities: [
      "Study open-weight models from their tensors and numerical behavior through to production execution.",
      "Build important parts of the inference stack from first principles.",
      "Write and optimize CUDA or HIP kernels for exact model shapes.",
      "Optimize and measure the stack on current NVIDIA and AMD hardware.",
      "Design model representations, quantization methods, memory layouts, and cache policies.",
      "Build execution, scheduling, distributed inference, and serving paths.",
      "Measure speed, energy use, model quality, correctness, and reliability on real workloads.",
      "Contribute useful work to open-source projects when that is the best path.",
      "Share clear evidence. Stop ideas that do not survive measurement.",
    ],
    problems: [
      "Model-specific kernels and fused execution paths.",
      "Low-bit formats that preserve model quality.",
      "KV-cache layout, movement, compression, and reuse.",
      "Sparse and mixture-of-experts execution.",
      "Speculative and parallel decoding.",
      "Prefill and decode scheduling across several GPUs.",
      "Performance models that explain the gap between hardware limits and measured results.",
      "New runtime designs for long-running agent workloads.",
    ],
    requirements: [
      "You have built a difficult ML or systems project that you can explain in detail.",
      "You can work in Python and a systems language such as C++ or Rust.",
      "You can write CUDA or HIP kernels, or you can learn a new GPU programming model quickly.",
      "You understand modern model execution, including attention, memory movement, and numerical precision.",
      "You use profiling and experiments to find the real limit.",
      "You can work without a complete specification.",
      "You write clearly and expose your reasoning to review.",
    ],
    notFor: [
      "You want to own one narrow layer and hand work to another team.",
      "You only want to connect existing inference frameworks.",
      "You only want to run experiments in notebooks.",
      "You want research papers to have priority over working systems.",
      "You optimize benchmark numbers without checking quality and correctness.",
      "You need a fixed roadmap before you can start useful work.",
    ],
  },
  {
    slug: "head-of-silicon",
    title: "Head of Silicon",
    team: "Silicon",
    location: "Bristol, London",
    summary:
      "Define our silicon direction and build a team for model-specific inference hardware.",
    purpose: [
      "This will be our first silicon hire, we do not yet have a fixed micro-architecture. Your first job will be to work with the inference research team to understand the models we want to serve, and the current hardware bottlenecks.",
      "You will build performance models and decide which ideas are worth pursuing. As the direction becomes clear, you will turn that into a silicon roadmap. You will then build and lead the team that takes the architecture through implementation, tape-out, and bring-up",
    ],
    responsibilities: [
      "Work with the inference research team to understand open-weight models and current hardware bottlenecks.",
      "Build analytical and simulation models to compare microarchitectures, memory systems, dataflows, and interconnects.",
      "Use those results to set targets for performance, power, area, cost, and reliability.",
      "Decide which capabilities belong in silicon, software, external IP, or partner designs.",
      "Turn the selected architecture into a roadmap through RTL, verification, physical design, tape-out, and bring-up.",
      "Select IP, EDA, foundry, packaging, manufacturing, and design partners.",
      "Hire and lead the initial silicon engineering team.",
      "Review microarchitecture, RTL, verification, PPA, and bring-up results.",
      "Define the hardware-software interface with the inference research team.",
    ],
    problems: [
      "Microarchitectures and numerical formats for dense, sparse, and mixture-of-experts models.",
      "Memory hierarchies for weights, activations, and KV-cache state.",
      "Dataflows for attention, expert routing, prefill, and decode.",
      "On-chip and chip-to-chip interconnects for model parallelism.",
      "Performance models that predict latency, throughput, power, and utilization before RTL.",
      "Hardware-software interfaces that can support new model structures without redesigning the chip.",
      "Verification strategies for long-running and highly parallel inference workloads.",
    ],
    requirements: [
      "You have led architecture or implementation for a complex digital chip and taken at least one design through tape-out and bring-up.",
      "You understand computer architecture, memory systems, interconnects, and power trade-offs.",
      "You can connect workload measurements to architecture decisions.",
      "You can work across architecture, RTL, verification, physical design, software, and systems.",
      "You can evaluate external partners and hold them to a high technical standard.",
      "You have hired and led a silicon engineering team.",
      "You still enjoy getting your hands dirty in technical work and don't shy away from caring about the details.",
    ],
    notFor: [
      "You are looking for a well defined role with little ambiguity.",
      "You want a management-only role.",
      "You want to copy a general GPU architecture instead of starting with the model definitions.",
      "You treat software as a fixed input to hardware design.",
      "You want a large team before you make progress.",
      "You lean on experience over trying new approaches.",
    ],
  },
  {
    slug: "founding-silicon-engineer",
    title: "Founding Silicon Engineer",
    team: "Silicon",
    location: "Bristol, London",
    summary:
      "Design model-specific inference hardware across architecture, implementation, and verification.",
    purpose: [
      "We want silicon engineers who understand the full path from model behavior to hardware activity. We do not want separate teams that pass incomplete specifications to each other.",
      "You will go deep where the problem requires it. You will also follow your work across the surrounding layers.",
    ],
    responsibilities: [
      "Study model workloads with the inference research team.",
      "Build analytical and cycle-accurate performance models.",
      "Explore compute, memory, dataflow, and interconnect designs.",
      "Turn selected designs into clear microarchitecture and RTL.",
      "Build verification environments and close functional and performance coverage.",
      "Use power, performance, and area results to change the design.",
      "Help build the hardware-software interface and low-level execution model.",
      "Automate design, simulation, verification, and analysis work.",
      "Support emulation, tape-out, and silicon bring-up as the program advances.",
    ],
    problems: [
      "Model-shaped compute and numerical units.",
      "Memory hierarchies for hot and cold model state.",
      "Sparse access, expert routing, and data movement.",
      "Network and chip-to-chip communication for inference.",
      "Performance models that stay useful as the design changes.",
      "Verification of long-running and highly parallel model workloads.",
      "Tools that let a small team explore and verify more designs.",
    ],
    requirements: [
      "You have deep digital silicon experience.",
      "You can work across architecture, modeling, RTL, verification, and software.",
      "You can use SystemVerilog and a programming language such as Python or C++.",
      "You understand pipelines, memory systems, interconnects, and ASIC design flows.",
      "You can turn incomplete workload evidence into a testable design question.",
      "You measure your work and explain the trade-offs clearly.",
      "Tape-out or silicon bring-up experience is useful, but it is not required for every candidate.",
    ],
    notFor: [
      "You want to work on one block without understanding the complete system.",
      "You want to pass specifications or bugs to another team without following them through.",
      "You do not want to read model or software code.",
      "You need a complete specification before you can start.",
      "You prefer familiar design patterns when workload evidence points elsewhere.",
      "You want verification, performance, or implementation to be someone else's problem.",
    ],
  },
];
