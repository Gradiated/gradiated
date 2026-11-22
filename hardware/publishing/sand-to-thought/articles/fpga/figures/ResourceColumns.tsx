import { Label, Wire } from "./drawing";

const logicRows = Array.from({ length: 20 }, (_, row) => -116 + row * 60);
const memoryRows = [-116, 184, 484, 784];
const dspRows = [-116, 34, 184, 334, 484, 634, 784, 934];
const lanes = [-8, 0, 8];
const originalChannels = [100, 220, 340, 460];
const extraChannels = [676, 868, 1060, 1180, 1300];
const horizontalTracks = Array.from(
  { length: 22 },
  (_, row) => -140 + row * 60,
);
const tracks = [
  ...horizontalTracks.flatMap((y) =>
    lanes.map(
      (lane) => `M${originalChannels.includes(y) ? 468 : 92} ${y + lane}H1332`,
    ),
  ),
  ...originalChannels.flatMap((x) =>
    lanes.map((lane) => `M${x + lane} -140V92M${x + lane} 468V1100`),
  ),
  ...extraChannels.flatMap((x) =>
    lanes.map((lane) => `M${x + lane} -140V1100`),
  ),
].join("");

export const ResourceColumnTracks = ({ visible }: { visible: boolean }) => (
  <g
    className="fpga-tour-layer fpga-resource-columns-extra"
    data-visible={visible}
    aria-hidden={!visible}
  >
    <Wire d={tracks} />
  </g>
);

export const ResourceColumnLogic = ({ visible }: { visible: boolean }) => (
  <g
    className="fpga-tour-layer fpga-resource-columns-extra"
    data-visible={visible}
    aria-hidden={!visible}
  >
    {[124, 244, 364, 1084, 1204].flatMap((x) =>
      logicRows
        .filter((y) => (x < 500 ? ![124, 244, 364].includes(y) : y !== 1024))
        .map((y) => (
          <g key={`${x}-${y}`} className="fpga-block fpga-block--logic">
            <rect x={x} y={y} width={72} height={36} rx={3} />
          </g>
        )),
    )}
  </g>
);

export const ResourceColumnHardBlocks = ({ visible }: { visible: boolean }) => (
  <g
    className="fpga-tour-layer fpga-resource-columns-extra"
    data-visible={visible}
    aria-hidden={!visible}
  >
    {[508, 892].flatMap((x) =>
      memoryRows
        .filter((y) => x !== 508 || y !== 184)
        .map((y) => (
          <g key={`${x}-${y}`} className="fpga-block fpga-block--memory">
            <rect x={x} y={y} width={136} height={260} rx={4} />
          </g>
        )),
    )}
    {dspRows
      .filter((y) => y !== 334)
      .map((y) => (
        <g key={y} className="fpga-block fpga-block--arithmetic">
          <rect x={700} y={y} width={136} height={112} rx={4} />
        </g>
      ))}
  </g>
);

export const ResourceColumnLegend = ({ visible }: { visible: boolean }) => (
  <g
    className="fpga-tour-layer fpga-resource-columns-legend"
    data-visible={visible}
    aria-hidden={!visible}
  >
    {[
      { label: "CLB", kind: "logic" },
      { label: "BRAM", kind: "memory" },
      { label: "DSP", kind: "arithmetic" },
    ].map(({ label, kind }, index) => (
      <g key={kind} className={`fpga-block fpga-block--${kind}`}>
        <rect x={100 + index * 140} y={26} width={18} height={18} rx={2} />
        <Label x={128 + index * 140} y={43} anchor="start">
          {label}
        </Label>
      </g>
    ))}
  </g>
);
