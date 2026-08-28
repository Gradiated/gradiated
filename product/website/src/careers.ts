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
      "Find and remove bottlenecks across model representation, GPU kernels, runtimes, and serving for open-weight models.",
    purpose: [
      "We are building an inference research team to find where current hardware and software waste time, memory, and energy when serving open-weight models.",
      "You will measure those bottlenecks, test changes across the inference stack, and turn useful results into production systems. Your findings will also inform our silicon work.",
    ],
    responsibilities: [
      "Measure target models and workloads on current NVIDIA and AMD hardware.",
      "Design and implement kernels, numerical formats, memory layouts, and cache policies.",
      "Change runtimes, schedulers, distributed execution, and serving paths when they limit the system.",
      "Test latency, throughput, energy use, model quality, correctness, and reliability on real workloads.",
      "Turn research results into production services.",
      "Share research publicly so that others can learn about how inference research is done.",
      "Work with the silicon team to identify hardware bottlenecks and design opportunities.",
    ],
    problems: [
      "Kernels and fused execution paths for exact model shapes.",
      "Low-bit formats that preserve model quality.",
      "KV-cache layout, movement, compression, and reuse.",
      "Sparse and mixture-of-experts execution.",
      "Speculative and parallel decoding.",
      "Prefill and decode scheduling across multiple GPUs.",
      "Performance models that explain the gap between hardware limits and measured results.",
      "Runtime designs for long-running agent workloads.",
    ],
    requirements: [
      "You have built an ML systems, compiler, runtime, or kernel project, and you can explain your decisions and results in detail.",
      "You can work in Python and a systems language such as C++ or Rust. We use C++ mostly.",
      "You can write CUDA or HIP kernels, or you have strong low-level systems experience and can learn GPU programming.",
      "You understand transformer execution, including attention, memory movement, and numerical precision.",
      "You use profiling and controlled experiments to identify system limits.",
      "You are open to learning about hardware, and what is limiting the execution of the model.",
      "You can maintain production code, not only experimental code.",
      "You can explain hard technical solutions clearly"
    ],
    notFor: [
      "You want to work within one layer of the inference stack.",
      "You want framework integration to be the main technical work.",
      "You want papers or notebook results to be the primary output.",
      "You aren't excited by rewriting things from scratch, and taking time to find the globally optimal solution to a problem.",
      "You need a complete specification before you can investigate a problem.",
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
      "Design model-specific inference hardware from performance modeling through RTL and verification.",
    purpose: [
      "This role will be part of our initial silicon team. The team will explore architectures for our inference workloads and turn the selected designs into working silicon.",
      "You will own a substantial part of the design and follow it through performance modeling, microarchitecture, RTL, and verification. You do not need to be an expert in every area, but you must work across the interfaces around your design.",
    ],
    responsibilities: [
      "Work with the inference research team to turn workload measurements into design requirements.",
      "Build analytical and cycle-accurate models to compare compute units, numerical formats, memory systems, dataflows, and interconnects.",
      "Own one or more design areas from microarchitecture through RTL implementation.",
      "Write test plans, build verification environments, and close functional and performance coverage.",
      "Use power, performance, area, and verification results to revise the design.",
      "Define hardware-software interfaces and the low-level execution model with the inference research team.",
      "Automate architecture exploration, simulation, regression testing, and analysis.",
      "Support emulation, tape-out, and silicon bring-up as the program advances.",
    ],
    problems: [
      "Compute units and numerical formats for target model operations.",
      "Memory hierarchies for weights, activations, and KV-cache state.",
      "Sparse access, expert routing, and data movement.",
      "On-chip and chip-to-chip communication for model parallelism.",
      "Performance models that stay useful as the design changes.",
      "Verification strategies for long-running and highly parallel model workloads.",
    ],
    requirements: [
      "You have deep experience in at least one area: microarchitecture, performance modeling, RTL design, or design verification.",
      "You can work across the adjacent parts of architecture, RTL, verification, and software.",
      "You can write SystemVerilog and use Python or C++ for modeling, automation, and verification.",
      "You understand pipelines, memory systems, interconnects, and ASIC design flows.",
      "You can turn incomplete workload evidence into a testable design question.",
      "You use measured results to explain technical trade-offs.",
      "Tape-out or silicon bring-up experience is useful, but it is not required for every candidate.",
    ],
    notFor: [
      "You want a narrowly specified block with fixed interfaces.",
      "You only want to focus on hardware, and are not interested in understanding models.",
      "You want to hand issues to another team when they cross a design boundary.",
      "You need a clear specification before you can start.",
    ],
  },
];
