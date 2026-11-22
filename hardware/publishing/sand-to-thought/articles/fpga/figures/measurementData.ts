export type Measurements = {
  ttftMs: number
  decodeTps: number
  joulesPerToken: number
}

// Available sites in the K26 routed utilisation report. CLBs contain LUTs and registers.
export const fabricCapacity = {
  clbs: 14640, luts: 117120, registers: 234240, dsps: 1248, bram: 144, uram: 64,
}

export type FabricUsage = typeof fabricCapacity

type MeasurementStep = {
  resources: FabricUsage
  label: string
  runId: string
  value: Measurements
  control?: Measurements
  controlStep?: number
}

// From the pinned physical run records. TTFT averages all 18 requests. Decode pools output intervals and their durations across the same requests.
// Energy is the mean of three gross VCC_SOM blocks, each with six verified answers (632 output tokens).
// Each step has its own measured control. The same circuit can have different values in different runs.
export const measurements: readonly MeasurementStep[] = [
  {
    label: 'CPU chooses each token',
    runId: 'autonomous-prefill-decode-20261115T210134Z-97efcb',
    resources: { clbs: 5386, luts: 31792, registers: 11027, dsps: 10, bram: 36.5, uram: 0 },
    value: { ttftMs: 156.8783, decodeTps: 205.0517, joulesPerToken: 0.02013366 },
  },
  {
    label: 'FPGA chooses each token',
    runId: 'autonomous-prefill-decode-20261115T210134Z-97efcb',
    resources: { clbs: 5869, luts: 33238, registers: 13698, dsps: 10, bram: 36.5, uram: 0 },
    value: { ttftMs: 125.1036, decodeTps: 251.3001, joulesPerToken: 0.01616573 },
    controlStep: 0,
    control: { ttftMs: 156.8783, decodeTps: 205.0517, joulesPerToken: 0.02013366 },
  },
  {
    label: 'Skip unused next-token scores',
    runId: 'prefill-skip-20261115T224422Z-754f19',
    resources: { clbs: 5927, luts: 33175, registers: 13712, dsps: 10, bram: 36.5, uram: 0 },
    value: { ttftMs: 108.4869, decodeTps: 251.3001, joulesPerToken: 0.01566976 },
    controlStep: 1,
    control: { ttftMs: 125.1071, decodeTps: 251.3004, joulesPerToken: 0.01613870 },
  },
  {
    label: 'Multiply four bits at a time',
    runId: 'scalar-mul-20261116T001133Z-268099',
    resources: { clbs: 6141, luts: 33993, registers: 12828, dsps: 30, bram: 36.5, uram: 0 },
    value: { ttftMs: 78.6346, decodeTps: 318.2444, joulesPerToken: 0.01220584 },
    controlStep: 2,
    control: { ttftMs: 108.4947, decodeTps: 251.3001, joulesPerToken: 0.01571722 },
  },
  {
    label: 'Divide two bits at a time',
    runId: 'scalar-div-20261116T105755Z-3c2ae0',
    resources: { clbs: 6231, luts: 34533, registers: 13112, dsps: 30, bram: 36.5, uram: 0 },
    value: { ttftMs: 57.6424, decodeTps: 422.2058, joulesPerToken: 0.00914552 },
    controlStep: 3,
    control: { ttftMs: 78.6367, decodeTps: 318.2441, joulesPerToken: 0.01221697 },
  },
  {
    label: 'Read the next weight while adding',
    runId: 'logits-pipeline-20261116T143416Z-2592fd',
    resources: { clbs: 6153, luts: 34547, registers: 13123, dsps: 30, bram: 36.5, uram: 0 },
    value: { ttftMs: 57.4482, decodeTps: 460.8053, joulesPerToken: 0.00854580 },
    controlStep: 4,
    control: { ttftMs: 57.6504, decodeTps: 422.2058, joulesPerToken: 0.00915551 },
  },
  {
    label: 'Two lanes for next-token scores',
    runId: 'logits-2-lanes-20261116T164332Z-6c4968',
    resources: { clbs: 6035, luts: 34603, registers: 13202, dsps: 31, bram: 38, uram: 0 },
    value: { ttftMs: 57.3487, decodeTps: 485.1285, joulesPerToken: 0.00818059 },
    controlStep: 5,
    control: { ttftMs: 57.4485, decodeTps: 460.8060, joulesPerToken: 0.00852052 },
  },
  {
    label: 'Four lanes for next-token scores',
    runId: 'logits-4-lanes-20261116T170727Z-020546',
    resources: { clbs: 6217, luts: 34795, registers: 13367, dsps: 33, bram: 38, uram: 0 },
    value: { ttftMs: 57.2799, decodeTps: 498.2787, joulesPerToken: 0.00800133 },
    controlStep: 5,
    control: { ttftMs: 57.4416, decodeTps: 460.8065, joulesPerToken: 0.00851003 },
  },
  {
    label: 'Eight lanes for next-token scores',
    runId: 'logits-8-lanes-20261116T202250Z-44df9d',
    resources: { clbs: 6159, luts: 35188, registers: 13689, dsps: 37, bram: 38, uram: 0 },
    value: { ttftMs: 57.2652, decodeTps: 505.1246, joulesPerToken: 0.00794414 },
    controlStep: 7,
    control: { ttftMs: 57.2853, decodeTps: 498.2787, joulesPerToken: 0.00801680 },
  },
  {
    label: 'Shorter division in the feed-forward stage',
    runId: 'ff-exp-div-20261116T230715Z-0969cc',
    resources: { clbs: 6059, luts: 34785, registers: 13646, dsps: 37, bram: 38, uram: 0 },
    value: { ttftMs: 49.7181, decodeTps: 557.7790, joulesPerToken: 0.00706845 },
    controlStep: 8,
    control: { ttftMs: 57.2763, decodeTps: 505.1246, joulesPerToken: 0.00789152 },
  },
  {
    label: 'Read ahead in the feed-forward weighted sum',
    runId: 'ff-down-pipeline-20261117T095726Z-1092a6',
    resources: { clbs: 6075, luts: 34799, registers: 13648, dsps: 37, bram: 38, uram: 0 },
    value: { ttftMs: 46.4356, decodeTps: 584.2653, joulesPerToken: 0.00672070 },
    controlStep: 9,
    control: { ttftMs: 49.7223, decodeTps: 557.7782, joulesPerToken: 0.00706860 },
  },
  {
    label: 'Read ahead in the KV cache',
    runId: 'attention-cache-pipeline-20261117T112139Z-daeb2e',
    resources: { clbs: 6265, luts: 34769, registers: 13652, dsps: 37, bram: 38, uram: 0 },
    value: { ttftMs: 44.4400, decodeTps: 626.5006, joulesPerToken: 0.00629673 },
    controlStep: 10,
    control: { ttftMs: 46.4370, decodeTps: 584.2670, joulesPerToken: 0.00673284 },
  },
  {
    label: 'Shorter division in attention',
    runId: 'attention-exp-div-20261117T132955Z-48d0fb',
    resources: { clbs: 6295, luts: 34516, registers: 13581, dsps: 37, bram: 38, uram: 0 },
    value: { ttftMs: 39.6458, decodeTps: 751.5737, joulesPerToken: 0.00531961 },
    controlStep: 11,
    control: { ttftMs: 44.4238, decodeTps: 626.5004, joulesPerToken: 0.00629810 },
  },
  {
    label: 'Store the weights that combine the heads in distributed RAM',
    runId: 'output-projection-lutram-20261117T155233Z-6a5a09',
    resources: { clbs: 6416, luts: 34913, registers: 13588, dsps: 37, bram: 37.5, uram: 0 },
    value: { ttftMs: 39.6549, decodeTps: 751.5755, joulesPerToken: 0.00534086 },
    controlStep: 12,
    control: { ttftMs: 39.6552, decodeTps: 751.5753, joulesPerToken: 0.00534296 },
  },
  {
    label: 'Two attention scores at once',
    runId: 'attention-exp-pair-v2-20261117T232821Z-e72da4',
    resources: { clbs: 6659, luts: 38329, registers: 14464, dsps: 41, bram: 39, uram: 0 },
    value: { ttftMs: 38.0689, decodeTps: 804.5780, joulesPerToken: 0.00505629 },
    controlStep: 12,
    control: { ttftMs: 39.6539, decodeTps: 751.5752, joulesPerToken: 0.00536963 },
  },
]
