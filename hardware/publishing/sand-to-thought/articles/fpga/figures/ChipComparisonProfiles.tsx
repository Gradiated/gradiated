import { ProfilePlot, type ProfileSpecs } from "./MeasuredProfile";

// The frozen workload includes the start position and two inputs per prompt byte.
const replies = [
  { promptPositions: 11, outputTokens: 90 },
  { promptPositions: 13, outputTokens: 122 },
  { promptPositions: 97, outputTokens: 104 },
];

// A batch-one illustrative scenario. Inputs are assumptions, not sampled timings.
function estimate(macPerMicrosecond: number, overheadUs: number, activeWatts: number) {
  let firstTokenUs = 0;
  let decodeUs = 0;
  let elapsedUs = 0;
  let outputTokens = 0;
  for (const reply of replies) {
    outputTokens += reply.outputTokens;
    const lastPosition = reply.promptPositions + reply.outputTokens; // Predicts EOS.
    for (let position = 1; position <= lastPosition; position++) {
      const projections = 4 * 32 * 32 + 3 * 32 * 128;
      const attention = 2 * 32 * position;
      const scoring = position >= reply.promptPositions ? 320 * 32 : 0;
      const stepUs = (projections + attention + scoring) / macPerMicrosecond + overheadUs;
      elapsedUs += stepUs;
      if (position <= reply.promptPositions) firstTokenUs += stepUs;
      else if (position < lastPosition) decodeUs += stepUs;
    }
  }
  return {
    latency: firstTokenUs / replies.length / 1000,
    speed: (outputTokens - replies.length) * 1e6 / decodeUs,
    efficiency: outputTokens * 1e6 / (activeWatts * elapsedUs),
  };
}

const cpuScenario = estimate(150, 10, 3.5);
const acceleratorScenario = estimate(1000, 50, 100);

const devices: { kind: string; name: string; specs?: ProfileSpecs }[] = [
  { kind: "FPGA", name: "KV260 FPGA" },
  { kind: "CPU", name: "KV260 CPU", specs: { weightCount: 2e9, bandwidth: 19.2, ...cpuScenario } },
  { kind: "GPU", name: "NVIDIA H100 SXM", specs: { weightCount: 80e9 / 2, bandwidth: 3350, ...acceleratorScenario } },
  { kind: "ASIC", name: "Google TPU v5e", specs: { weightCount: 16 * 2 ** 30 / 2, bandwidth: 819, ...acceleratorScenario } },
];

export function ChipComparisonProfiles({ compact = false }: { compact?: boolean }) {
  return (
    <div className="kv-chip-profiles">
      {devices.map(({ kind, name, specs }) => (
        <figure key={kind} className={specs ? "kv-chip-pending" : undefined}>
          {!compact && <figcaption>
            <strong>{kind}</strong> · {name}
            <small>{specs ? "Illustrative estimate · unmeasured" : "Inference measured · experiment 24"}</small>
          </figcaption>}
          <ProfilePlot title={compact ? `${kind} · ${name}, ${specs ? "illustrative estimate" : "inference measured"}` : name} specs={specs} compact={compact} />
          {compact && (
            <figcaption>
              {name}
              {specs && <small>(placeholder)</small>}
            </figcaption>
          )}
        </figure>
      ))}
    </div>
  );
}
