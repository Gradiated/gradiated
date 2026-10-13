import { ashbyJobs } from "./ashby-jobs.generated";

export type Job = {
  /** The job posting in Ashby that applications go to. */
  ashbyJobPostingId: string;
  /** Sections from an Ashby description whose heading is not one of the standard ones. */
  extraSections?: { title: string; items: string[] }[];
  slug: string;
  datePosted?: string;
  foundingContext?: string;
  officeDays?: string;
  howWeWork?: string[];
  interviewSteps?: string[];
  title: string;
  team?: string;
  location: string;
  summary: string;
  purpose: string[];
  responsibilities: string[];
  problems: string[];
  requirements: string[];
  notFor: string[];
};

const nativeJobs: Job[] = [
  {
    slug: "engineer-journalist",
    ashbyJobPostingId: "b91af2c0-5367-454f-bc1d-1cc8d0e7f08c",
    datePosted: "2026-09-11",
    foundingContext:
      "We are early. Be the founding content and marketing person in the company.",
    officeDays: "Several days a week",
    howWeWork: [
      "We like to experiment a lot and do the hard thing even if it's likely to fail.",
      "We work in the office several days a week. We value working in person to solve hard problems, but are also flexible, some of the team work abroad for short periods.",
    ],
    interviewSteps: [
      "We get together in person and talk through the problems we will work on.",
      "A paid in-person working session, so we can get to know you and you can meet the team.",
      "References and an offer decision.",
    ],
    title: "Engineer Journalist",
    location: "Cambridge, London",
    summary:
      "Turn research on models, inference, and hardware into work that helps engineers understand the stack they rely on.",
    purpose: [
      "Software engineers increasingly rely on models, inference systems, and hardware for almost all of their day-to-day work, but rarely get a clear view of how those systems work. We think they should. Knowledge is power.",
      "Our research team produces whitepapers about the inference stack. You will be the translation layer between this work and regular full-stack software engineers who want a deeper understanding of what they are building on top of.",
    ],
    responsibilities: [
      "Work with our researchers as their work develops, not only after a paper is finished.",
      "Turn our whitepapers into articles that teach full-stack engineers the concepts, evidence, and practical consequences of the research.",
      "Read new model papers, then explain the architecture, training process, evaluations, strengths, weaknesses, and implications for inference.",
      "Build small experiments, benchmarks, diagrams, and code examples when they make an explanation more useful or more honest.",
      "Develop a distinct technical reputation for Gradiated that engineers trust.",
    ],
    problems: [],
    requirements: [
      "You have real software engineering experience and can investigate a technical claim in papers, code, traces, and benchmarks rather than repeating its summary.",
      "You write clearly and precisely, and you care about teaching rather than sounding clever.",
      "You can explain technical depth without removing the caveats, evidence, or uncertainty that make it trustworthy.",
      "You are curious enough to follow a question across models, training, inference software, systems, and hardware.",
      "You know how to interview technical people, challenge assumptions, and find the question that unlocks an explanation.",
      "You have writing, teaching, or explanatory work that shows how you think. It does not need to have been your job title.",
    ],
    notFor: [
      "You don't already read lots of whitepapers.",
      "You're scared about learning about hardware if you're not in that world already.",
      "You haven't truly been an engineer building production systems before.",
      "You need lots of handholding.",
    ],
  },
  {
    slug: "founding-inference-research-engineer",
    ashbyJobPostingId: "a68c08a7-1921-4fec-a565-db484c184db5",
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
      "You can explain hard technical solutions clearly",
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
    ashbyJobPostingId: "bfa00f96-d09e-4d13-b3e9-3e42bf28345a",
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
    ashbyJobPostingId: "449f708e-ac4f-41e8-946c-080bc8a6fbc9",
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

const nativeIds = new Set(nativeJobs.map((job) => job.ashbyJobPostingId));
const nativeSlugs = new Set(nativeJobs.map((job) => job.slug));

/** Native jobs first, then any Ashby postings that are not already written natively. */
export const jobs: Job[] = [
  ...nativeJobs,
  ...ashbyJobs.filter(
    (job) =>
      !nativeIds.has(job.ashbyJobPostingId) && !nativeSlugs.has(job.slug),
  ),
];
