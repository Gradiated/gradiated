type Site = "bram" | "dsp" | "outside" | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9;
export type Transfer = readonly [Site, Site, number];
export type Story = {
  description: string;
  stages: readonly (
    | "norm"
    | "input"
    | "control"
    | "feedForward"
    | "attention"
    | "cache"
    | "logits"
  )[];
  labels: Partial<Record<Site, string>>;
  transfers: readonly Transfer[];
  phases: readonly string[];
  comparison: string;
  lanes?: number;
  detail?: "lanes" | "full-map";
  multipliers?: number;
  clockPeriodsNs?: readonly [number, number];
};

function scoringLanes(count: number, comparison: string): Story {
  return {
    description: `The same input reaches ${count} lanes. Each reads its own weights and adds to a different score.`,
    stages: ["logits"],
    labels: {
      bram: "Weight banks",
      dsp: "Parallel products",
      5: "Score|totals",
    },
    transfers: [
      ["bram", "dsp", 0],
      ["dsp", 5, 1],
    ],
    phases: ["Read weights together", "Update separate scores"],
    lanes: count,
    detail: "lanes",
    comparison,
  };
}

export const stories: Record<string, Story> = {
  "measuring-inference": {
    description:
      "The FPGA sends all 320 scores to the Arm CPU and waits for one token ID to come back.",
    stages: [],
    labels: { 6: "Send|scores", 2: "Next|token", outside: "Arm CPU" },
    transfers: [
      [6, "outside", 0],
      ["outside", 2, 1],
    ],
    phases: ["Send 320 scores", "Return one token"],
    comparison: "One round trip for every generated token",
  },
  "measure-autonomous": {
    description:
      "Logic on the FPGA keeps the highest score as each result arrives. Its token ID starts the next prediction.",
    stages: ["control"],
    labels: { 6: "New|score", 5: "Best|so far", 2: "Next|token" },
    transfers: [
      [6, 5, 0],
      [5, 2, 1],
    ],
    phases: ["Compare each score", "Use the winning ID"],
    comparison: "Token selection moves from the CPU into the FPGA",
  },
  "measure-skip": {
    description:
      "While prompt tokens are waiting, save each key and value. Only the final prompt token needs next-token scores.",
    stages: ["input", "logits"],
    labels: {
      3: "Save|K and V",
      bram: "KV cache",
      5: "Last|token?",
      8: "Start|scoring",
    },
    transfers: [
      [3, "bram", 0],
      [5, 8, 1],
    ],
    phases: ["Every prompt token: save K and V", "Final token: start scoring"],
    comparison: "Hello: score after o",
  },
  "measure-multiply": {
    description:
      "The multiplier takes four bits from one input, calculates their contribution and combines it with the saved product.",
    stages: ["norm", "attention", "feedForward"],
    labels: { 3: "Next|4 bits", dsp: "Multiply", 6: "Partial|product" },
    transfers: [
      [3, "dsp", 0],
      ["dsp", 6, 1],
      [6, 3, 2],
    ],
    phases: ["Take four bits", "Update product", "Continue"],
    comparison: "64 calculation steps → 16",
  },
  "measure-divide": {
    description:
      "The divider compares the remainder with multiples of the divisor and saves two answer bits each clock.",
    stages: ["norm", "attention", "feedForward"],
    labels: { 4: "Bring|2 bits", 5: "Compare", 6: "Save|remainder" },
    transfers: [
      [4, 5, 0],
      [5, 6, 1],
      [6, 4, 2],
    ],
    phases: ["Bring down two bits", "Choose the digits", "Carry the remainder"],
    comparison: "64 calculation steps → 32",
  },
  "measure-score-pipeline": {
    description:
      "As the DSP works on the current pair, the controller asks memory for the next input and weight.",
    stages: ["logits"],
    labels: {
      3: "Read|next",
      bram: "Inputs + weights",
      dsp: "Current pair",
      6: "Running|score",
    },
    transfers: [
      [3, "bram", 0],
      ["dsp", 6, 0],
      ["bram", "dsp", 1],
    ],
    phases: ["Read and calculate together", "Next pair arrives"],
    comparison: "One scoring lane stays busy for more of the reply",
  },
  "measure-two-lanes": scoringLanes(2, "Two lanes: odd scores and even scores"),
  "measure-four-lanes": scoringLanes(
    4,
    "One-lane control → four lanes: 461 → 498 tokens/s",
  ),
  "measure-eight-lanes": scoringLanes(
    8,
    "Four → eight lanes: whole-model decode rose from 498 to 505 tokens/s.",
  ),
  "measure-feedforward-divide": {
    description:
      "The feed-forward divider checks whether the first quotient digits must be zero. When they are, it skips them.",
    stages: ["feedForward"],
    labels: { 4: "Check|prefix", 5: "Divide", 6: "Result" },
    transfers: [
      [4, 5, 0],
      [5, 6, 1],
    ],
    phases: ["Skip known zeros", "Finish the division"],
    comparison: "Repeated division by 45,426",
  },
  "measure-down-pipeline": {
    description:
      "The final feed-forward projection reads the next weight while the DSP adds the current product.",
    stages: ["feedForward"],
    labels: {
      3: "Read|next",
      bram: "Down weights",
      dsp: "Multiply + add",
      6: "Output|sum",
    },
    transfers: [
      [3, "bram", 0],
      ["dsp", 6, 0],
      ["bram", "dsp", 1],
    ],
    phases: ["Request and add together", "Use the next weight"],
    comparison: "128 input values → 32 weighted sums",
  },
  "measure-cache-pipeline": {
    description:
      "Attention requests the next key or value while it calculates with the one already fetched.",
    stages: ["attention", "cache"],
    labels: {
      3: "Next|address",
      bram: "KV cache",
      dsp: "Current term",
      6: "Running|sum",
    },
    transfers: [
      [3, "bram", 0],
      ["dsp", 6, 0],
      ["bram", "dsp", 1],
    ],
    phases: ["Request and calculate", "Receive next cache entry"],
    comparison: "One cache request ahead",
  },
  "measure-attention-divide": {
    description:
      "Each attention score needs an exponential. Its divider skips the leading zero digits just as the feed-forward divider did.",
    stages: ["attention"],
    labels: { 4: "Score", 5: "Skip|zeros", 6: "Finish|division" },
    transfers: [
      [4, 5, 0],
      [5, 6, 1],
    ],
    phases: ["Start an exponential", "Shorten its division"],
    comparison: "The shortcut repeats for each cached position",
  },
  "measure-lutram": {
    description:
      "The weights that combine the heads now live in LUT memory. The multiplier receives each weight on the same clock as before.",
    stages: ["attention"],
    labels: { 3: "LUT|memory", dsp: "Weighted sum" },
    transfers: [[3, "dsp", 0]],
    phases: ["Read weights from LUT memory"],
    comparison: "BRAM → LUT memory at build time · identical reply clocks",
  },
  "measure-exp-pair": {
    description:
      "Two exponential circuits handle neighbouring scores in one attention head. Each has its own table.",
    stages: ["attention"],
    labels: {
      4: "Score A",
      7: "Score B",
      5: "Exp A",
      8: "Exp B",
      6: "Ordered|results",
    },
    transfers: [
      [4, 5, 0],
      [7, 8, 0],
      [5, 6, 1],
      [8, 6, 1],
    ],
    phases: ["Process a pair", "Collect both results"],
    comparison: "A single unpaired score uses one circuit",
  },
  "measure-ddr-weight": {
    detail: "full-map",
    description:
      "One DDR4 transfer returns four weights. The FPGA selects one and requests another transfer for the next weight.",
    stages: ["attention"],
    labels: { outside: "External DDR4", 3: "Select|one", dsp: "Weighted sum" },
    transfers: [
      ["outside", 3, 0],
      [3, "dsp", 1],
    ],
    phases: ["Receive four weights", "Use one weight"],
    comparison: "1,024 requests for 1,024 weights",
  },
  "measure-ddr-row": {
    detail: "full-map",
    description:
      "One request brings in a row of 32 weights. The FPGA keeps each group of four and feeds the weights to the multiplier.",
    stages: ["attention"],
    labels: { outside: "External DDR4", 3: "Row|reader", dsp: "Weighted sum" },
    transfers: [
      ["outside", 3, 0],
      [3, "dsp", 1],
    ],
    phases: ["Fetch a row in eight transfers", "Use all 32 weights"],
    comparison: "1,024 requests → 32 row requests",
  },
  "measure-ddr-scores": {
    description:
      "The scoring weights live in DDR4. The FPGA fills a small buffer before starting the next group of eight scores.",
    stages: ["logits"],
    labels: {
      outside: "External DDR4",
      3: "Weight|buffer",
      dsp: "Scoring lanes",
    },
    transfers: [
      ["outside", 3, 0],
      [3, "dsp", 1],
    ],
    phases: ["Fetch 512 bytes", "Calculate eight candidate scores"],
    comparison: "20 KiB of weights off-chip · 8 BRAM tiles freed",
  },
  "measure-ddr-prefetch": {
    description:
      "DDR4 fills one buffer while the other supplies weights to the scoring lanes. Then the buffers swap jobs.",
    stages: ["logits"],
    labels: {
      outside: "External DDR4",
      3: "Buffer A",
      6: "Buffer B",
      dsp: "Scoring lanes",
    },
    transfers: [
      ["outside", 3, 0],
      [6, "dsp", 0],
      ["outside", 6, 1],
      [3, "dsp", 1],
    ],
    phases: ["Fill A · score from B", "Fill B · score from A"],
    comparison: "Two buffers overlap transfer and calculation",
  },
  "measure-probability-div": {
    description:
      "Divide one positive value by the sum of all the values. Its share can be at most one, so the fixed-point answer fits in 16 bits.",
    stages: ["attention"],
    labels: {
      4: "One|value",
      7: "Sum of|values",
      5: "Divide",
      6: "Token|share",
    },
    transfers: [
      [4, 5, 0],
      [7, 5, 0],
      [5, 6, 1],
    ],
    phases: ["Skip 48 leading bits", "Finish and round"],
    comparison: "32 division steps → 8",
  },
  "measure-feedforward-multiply": {
    description:
      "Split both inputs into four pieces. DSPs multiply pairs of pieces in parallel, then the circuit combines their products.",
    stages: ["feedForward"],
    labels: { 3: "Split|inputs", dsp: "Partial products", 6: "Shift|and add" },
    transfers: [
      [3, "dsp", 0],
      ["dsp", 6, 1],
    ],
    phases: ["Multiply pieces together", "Combine by place value"],
    comparison: "16 calculation clocks → 5",
  },
  "measure-norm-multiply": {
    description:
      "Each of the three normalisation stages gets a fast multiplier. The stages run one after another.",
    stages: ["norm"],
    labels: { 3: "Norm 1", 6: "Norm 2", 9: "Final|norm", dsp: "3 multipliers" },
    multipliers: 3,
    transfers: [
      [3, "dsp", 0],
      [6, "dsp", 1],
      [9, "dsp", 2],
    ],
    phases: [
      "First normalisation",
      "Second normalisation",
      "Final normalisation",
    ],
    comparison: "Three dedicated multipliers · 89 DSPs in the whole design",
  },
  "measure-norm-share": {
    description:
      "The same three stages now send their operands to one shared multiplier. Each gets a turn when it needs one.",
    stages: ["norm"],
    labels: { 3: "Norm 1", 6: "Norm 2", 9: "Final|norm", dsp: "1 multiplier" },
    multipliers: 1,
    transfers: [
      [3, "dsp", 0],
      [6, "dsp", 1],
      [9, "dsp", 2],
    ],
    phases: [
      "First stage uses it",
      "Second stage uses it",
      "Final stage uses it",
    ],
    comparison: "89 DSPs → 57 · same number of reply clocks",
  },
  "measure-projection-reads": {
    description:
      "Read-ahead reaches more weighted sums, including the projections that turn an input into its query, key and value.",
    stages: ["attention", "feedForward"],
    labels: {
      3: "Next|pair",
      bram: "Weights + inputs",
      dsp: "Current product",
      6: "Running|sum",
    },
    transfers: [
      [3, "bram", 0],
      ["dsp", 6, 0],
      ["bram", "dsp", 1],
    ],
    phases: ["Read and accumulate", "Use the next pair"],
    comparison:
      "3,999 fewer clocks per position across the affected projections",
  },
  "measure-value-pair": {
    description:
      "Two BRAM banks supply neighbouring value coordinates together. Two lanes apply the same attention weight and keep separate sums.",
    stages: ["attention", "cache"],
    labels: {
      bram: "Even / odd banks",
      dsp: "Two products",
      6: "Even|sum",
      9: "Odd|sum",
    },
    transfers: [
      ["bram", "dsp", 0],
      ["dsp", 6, 1],
      ["dsp", 9, 1],
    ],
    phases: ["Read adjacent values", "Update two sums"],
    comparison: "One extra DSP · same BRAM capacity",
    lanes: 2,
  },
  "measure-clock-rate": {
    description:
      "We ran the circuit from experiment 23 at 52.63 MHz. Each reply took the same number of ticks, but each tick came one nanosecond sooner.",
    stages: [
      "input",
      "norm",
      "attention",
      "cache",
      "feedForward",
      "logits",
      "control",
    ],
    labels: {},
    transfers: [],
    phases: ["Each clock pulse travels to all nine CLBs. Four clock cycles at each setting"],
    clockPeriodsNs: [20, 19],
    comparison:
      "Replies finished 5% sooner. Energy per output token fell 4.6%.",
  },
};
