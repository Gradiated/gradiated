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
      "Define the silicon strategy from measured model and workload behavior.",
      "Set clear targets for performance, power, area, cost, and reliability.",
      "Lead architecture work across compute, memory, interconnects, I/O, packaging, and systems.",
      "Build models that connect model-level behavior to silicon-level limits.",
      "Set the roadmap from architecture exploration through tape-out and bring-up.",
      "Make build, buy, and partner decisions for IP, EDA tools, packaging, foundries, and manufacturing.",
      "Hire and lead a small team of engineers who work across technical boundaries.",
      "Stay close to implementation, verification, and measured results.",
      "Work with the inference team so software and silicon evolve together.",
    ],
    problems: [
      "Memory systems for dense and sparse model weights.",
      "Dataflows for attention, mixture-of-experts layers, and long contexts.",
      "Compute and memory balance for prefill and decode.",
      "Interconnects for model parallelism and routed experts.",
      "Simulation and performance prediction before tape-out.",
      "Hardware-software interfaces that let the system change with new models.",
      "Verification and bring-up plans for a small first team.",
    ],
    requirements: [
      "You have owned major technical decisions for complex digital silicon.",
      "You have taken at least one high-performance design through tape-out and bring-up.",
      "You understand computer architecture, memory systems, interconnects, and power trade-offs.",
      "You can connect workload measurements to architecture decisions.",
      "You can work across architecture, RTL, verification, physical design, software, and systems.",
      "You can evaluate external partners and hold them to a high technical standard.",
      "You have built or led a strong technical team.",
      "You still want to do technical work yourself.",
    ],
    notFor: [
      "You want a management-only role.",
      "You want to copy a general GPU architecture instead of starting with the model definitions.",
      "You treat software as a fixed input to hardware design.",
      "You need a large team before you can make progress.",
      "You want to delegate the hard architecture decisions.",
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
