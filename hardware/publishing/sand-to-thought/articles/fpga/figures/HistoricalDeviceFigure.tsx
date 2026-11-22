import { Label, Wire } from "./drawing";
import { WorldLayer } from "./WorldLayer";

const TilePattern = ({
  x,
  y,
  size,
  selected = false,
}: {
  x: number;
  y: number;
  size: number;
  selected?: boolean;
}) => (
  <g>
    <rect
      x={x}
      y={y}
      width={size}
      height={size}
      className={selected ? "fpga-selected-row" : "fpga-die-tile"}
    />
    <path
      d={`M${x + 2} ${y + size * 0.3}h${size - 4}M${x + 2} ${y + size * 0.55}h${size - 4}M${x + size * 0.33} ${y + 2}v${size - 4}M${x + size * 0.66} ${y + 2}v${size - 4}`}
      className="fpga-die-detail"
    />
  </g>
);

const ChipDie = () => {
  const coordinate = (i: number) =>
    i * 23 + (i >= 3 ? 5 : 0) + (i >= 4 ? 8 : 0) + (i >= 6 ? 5 : 0);

  return (
    <g>
      <rect
        x={166}
        y={66}
        width={228}
        height={254}
        rx={2}
        className="fpga-die"
      />
      <rect x={172} y={73} width={216} height={228} className="fpga-die-io" />
      {Array.from({ length: 64 }, (_, i) => (
        <TilePattern
          key={i}
          x={180 + coordinate(i % 8)}
          y={90 + coordinate(Math.floor(i / 8))}
          size={20}
          selected={i === 27}
        />
      ))}
      <path
        d="M250 87V294M324 87V294M177 160H383M177 234H383"
        className="fpga-die-buffer"
      />
      <path d="M275 82V302M177 186H383" className="fpga-die-configuration" />
      {Array.from({ length: 13 }, (_, i) => (
        <g key={i} className="fpga-die-pads">
          <rect x={175 + i * 16} y={76} width={7} height={7} />
          <rect x={175 + i * 16} y={306} width={7} height={7} />
          <rect x={169} y={91 + i * 16} width={5} height={7} />
          <rect x={386} y={91 + i * 16} width={5} height={7} />
        </g>
      ))}
    </g>
  );
};

const TileDetail = () => (
  <>
    <rect x={60} y={35} width={295} height={290} rx={3} className="fpga-die" />
    {[50, 112, 183, 247, 307].map((y) => (
      <g key={y} opacity={0.8}>
        {Array.from({ length: 18 }, (_, i) => (
          <rect
            key={i}
            x={70 + i * 15}
            y={y}
            width={10}
            height={9}
            className="fpga-die-memory"
          />
        ))}
      </g>
    ))}
    <g>
      {[90, 250].map((x) => (
        <g key={x}>
          <rect
            x={x}
            y={72}
            width={70}
            height={28}
            rx={2}
            className="fpga-die-switch"
          />
          <path
            d={`M${x + 6} 80h58M${x + 6} 91h58M${x + 20} 75v22M${x + 47} 75v22`}
            className="fpga-die-detail"
          />
        </g>
      ))}
      {Array.from({ length: 5 }, (_, i) => (
        <path
          key={i}
          d={`M70 ${138 + i * 7}H345M${84 + i * 52} 64V178`}
          className="fpga-die-detail"
        />
      ))}
      <Wire d="M60 152H185V86H250" active />
    </g>
    <g>
      <rect
        x={217}
        y={207}
        width={115}
        height={28}
        rx={3}
        className="fpga-die-switch"
      />
      <Label x={274} y={226} small>
        Selectors
      </Label>
      <rect
        x={78}
        y={202}
        width={115}
        height={35}
        rx={3}
        className="fpga-die-storage"
      />
      <Label x={135} y={225} small>
        Flip-flop
      </Label>
      <path d="M120 237l10 -8 10 8" className="fpga-wire" />
      {[78, 218].map((x, i) => (
        <g key={x}>
          <rect
            x={x}
            y={267}
            width={114}
            height={29}
            rx={3}
            className="fpga-die-lut"
          />
          <Label x={x + 57} y={287} small>{`LUT ${i === 0 ? "F" : "G"}`}</Label>
        </g>
      ))}
    </g>
    <Wire d="M355 85H380" active />
    <Label x={395} y={80} anchor="start" small>
      Routing
    </Label>
    <Label x={395} y={101} anchor="start" small>
      switches
    </Label>
    <Wire d="M355 117H370V147H380" control active />
    <Label x={395} y={142} anchor="start" small>
      Stored
    </Label>
    <Label x={395} y={163} anchor="start" small>
      settings
    </Label>
    <Wire d="M355 281H380" active />
    <Label x={395} y={276} anchor="start" small>
      Logic and
    </Label>
    <Label x={395} y={297} anchor="start" small>
      working state
    </Label>
    <Label x={280} y={357} small className="fpga-note">
      One repeated tile · functional regions, simplified shapes
    </Label>
  </>
);

const Package = () => (
  <>
    <rect
      x={123}
      y={39}
      width={314}
      height={298}
      rx={9}
      className="fpga-package-shadow"
    />
    {Array.from({ length: 17 }, (_, i) => (
      <g key={i} className="fpga-package-pins">
        <rect x={143 + i * 16} y={20} width={7} height={26} rx={1} />
        <rect x={143 + i * 16} y={327} width={7} height={26} rx={1} />
        <rect x={107} y={55 + i * 16} width={26} height={7} rx={1} />
        <rect x={427} y={55 + i * 16} width={26} height={7} rx={1} />
      </g>
    ))}
    <rect
      x={129}
      y={34}
      width={302}
      height={299}
      rx={8}
      className="fpga-package"
    />
    <rect
      x={147}
      y={51}
      width={266}
      height={272}
      rx={3}
      className="fpga-package-cavity"
    />
    <ChipDie />
    {Array.from({ length: 13 }, (_, i) => (
      <g key={i} className="fpga-bond-wires">
        <path
          d={`M${178 + i * 16} 79L${151 + i * 20} 54M${178 + i * 16} 310L${151 + i * 20} 321M172 ${94 + i * 16}L149 ${59 + i * 20}M389 ${94 + i * 16}L411 ${59 + i * 20}`}
        />
      </g>
    ))}
    <Wire d="M394 187H474" />
    <Label x={485} y={181} anchor="start" small>
      I/O
    </Label>
    <Label x={485} y={203} anchor="start" small>
      edge
    </Label>
  </>
);

export const HistoricalDeviceFigure = ({ scene }: { scene: string }) => {
  const history = scene === "history";
  const tile = scene === "first-fpga-block";

  return (
    <WorldLayer
      title={
        history
          ? "A timeline from programmable logic to modern FPGAs, beside the same teaching chip."
          : tile
            ? "Zoom into tile 27 on the same XC2064 die. Faded surrounding lines retain the package context. The enlarged drawing separates routing, configuration memory, two LUTs and a flip-flop. Shapes are simplified."
            : "Xilinx XC2064 in a 68-pin package. Its die contains an eight-by-eight array of 64 logic blocks. One tile is highlighted for the next zoom."
      }
    >
      <g
        className="fpga-world-visibility"
        data-visible={history}
        aria-hidden={!history}
      >
        <Wire d="M-12 135V425" />
        {[
          [155, "1970s", "Memory → logic"],
          [235, "1984", "FPGA concept"],
          [315, "1985", "XC2064"],
          [395, "Later", "RAM, arithmetic, CPUs"],
        ].map(([y, year, label]) => (
          <g key={year}>
            <circle
              cx={-12}
              cy={Number(y) - 6}
              r={4}
              className="fpga-junction"
            />
            <Label x={8} y={Number(y)} anchor="start" value>
              {year}
            </Label>
            <Label x={8} y={Number(y) + 25} anchor="start" small>
              {label}
            </Label>
          </g>
        ))}
        <Label x={420} y={130}>
          A modern FPGA
        </Label>
      </g>
      <g
        className="fpga-world-visibility"
        data-visible={!history}
        aria-hidden={history}
      >
        <Label x={320} y={66}>
          {tile ? "One tile inside the XC2064" : "XC2064 · 1985"}
        </Label>
        <g
          className="fpga-historical-camera"
          style={{
            transform: tile
              ? "matrix(16,0,0,16,-3994,-2504)"
              : "matrix(1,0,0,1,40,90)",
          }}
        >
          <g className="fpga-history-context" data-detail={tile}>
            <Package />
          </g>
          <g
            className="fpga-historical-tile fpga-world-visibility"
            data-visible={tile}
            aria-hidden={!tile}
            transform="translate(254 164) scale(0.06779661) translate(-60 -35)"
          >
            <TileDetail />
          </g>
        </g>
      </g>
    </WorldLayer>
  );
};
