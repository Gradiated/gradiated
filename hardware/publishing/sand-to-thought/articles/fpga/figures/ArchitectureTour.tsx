import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { answers, address } from "./model";
import type { Bit } from "./model";
import { BitControls, Block, Label, Mux, SramFeedback, Wire } from "./drawing";
import type { CSSProperties } from "react";

export const architectureScenes = [
  "inside-chip",
  "clb-resources",
  "inside-clb",
  "truth-table",
  "selector",
  "stored-bit",
  "write-and-hold",
  "cell-hold",
  "lut",
  "flip-flop",
  "logic-block",
  "flip-flop-hold",
  "clb-output-setting",
  "routing-grid",
  "routing-switch",
  "routing-change",
] as const;

type View = "chip" | "clb-overview" | "clb" | "lut" | "cell" | "junction";

const views: Record<string, View> = {
  "inside-chip": "chip",
  "clb-resources": "clb-overview",
  "inside-clb": "clb",
  "truth-table": "lut",
  selector: "lut",
  "stored-bit": "cell",
  "write-and-hold": "cell",
  "cell-hold": "cell",
  lut: "lut",
  "flip-flop": "clb",
  "logic-block": "clb",
  "flip-flop-hold": "clb",
  "clb-output-setting": "clb",
  "routing-grid": "chip",
  "routing-switch": "junction",
  "routing-change": "junction",
  "routing-input": "junction",
};

const titles: Record<string, string> = {
  "inside-chip": "Return to the FPGA; the upper-left CLB is highlighted.",
  "clb-resources":
    "One UltraScale CLB contains eight LUTs and sixteen flip-flops. One LUT and one flip-flop are highlighted for the next close-up.",
  "inside-clb":
    "Focus on one LUT feeding a flip-flop, whose saved value reaches the CLB output.",
  "truth-table":
    "A two-input LUT stores four AND answers in SRAM. Faded AB row labels point to the corresponding answers; current inputs A = 1 and B = 0 select row 10, whose answer is 0.",
  selector: "Inputs A and B select one stored LUT answer without changing it.",
  "stored-bit":
    "Closer inside row 01: a conventional SRAM cell holds answer 0 through feedback.",
  "write-and-hold":
    "Access transistors turn on. Write drivers force the SRAM cell to store 1.",
  "cell-hold":
    "Access transistors turn off. Powered feedback retains answer 1.",
  lut: "Return to the complete LUT: rows 01 and 10 now hold 1, changing AND into OR.",
  "flip-flop":
    "Return to the CLB. Its flip-flop can capture a working result at a clock edge.",
  "logic-block":
    "The LUT holds the rule; the flip-flop holds the captured result.",
  "flip-flop-hold":
    "The LUT output changes to 0, but the saved value stays 1 without another rising clock edge. A configuration-controlled selector can choose the current or saved result.",
  "clb-output-setting":
    "A simplified configuration cell uses two NOT gates in a feedback loop to hold setting 1, selecting the flip-flop’s saved result. The LUT output remains 0 and the saved result remains 1.",
  "routing-grid":
    "Return to the chip. Two existing wires can feed a selector leading to the centre CLB.",
  "routing-switch":
    "Inside a routing junction: an SRAM feedback loop holds configuration bit 0, selecting the upper incoming wire, whose signal is 1.",
  "routing-change":
    "Write routing bit 1. The lower source, whose signal is 0, now reaches the destination.",
  "routing-input":
    "The lower source signal becomes 1. The stored routing bit stays 1; the connection stays selected.",
};

const clbScale = 72 / 560;
const lutScale = 270 / 560;
const cellScale = 0.12;
const lutOutputY = 192;
const routingScale = 44 / 560;
const routingUpperY = 200 - 8 / routingScale;
const routingLowerY = 200 + 8 / routingScale;
const clbLutOutputY = 165 + lutScale * lutOutputY;
const centreInClb = (x: number, y: number) =>
  [124 + clbScale * x, 124 + clbScale * y] as const;
const lutFrame = { x: 220, y: 185, width: 650, bottom: 370 };
const lutCentre = centreInClb(
  40 + lutScale * lutFrame.x,
  165 + lutScale * lutFrame.y,
);
const cellCentre = centreInClb(40 + lutScale * 180, 165 + lutScale * 156);

const frames: Record<View, readonly [number, number, number]> = {
  chip: [280, 280, 1],
  "clb-overview": [160, 160, 6.9],
  clb: [160, 160, 6.9],
  lut: [
    lutCentre[0],
    lutCentre[1],
    560 / (lutFrame.width * lutScale * clbScale),
  ],
  cell: [
    cellCentre[0],
    cellCentre[1],
    560 / (560 * cellScale * lutScale * clbScale),
  ],
  junction: [220, 220, 560 / 44],
};

export const architectureTitle = (scene: string) => titles[scene];
export const architectureTransform = (view?: View, application = false) => {
  const [x, y, scale] = view
    ? frames[view]
    : [280, 280, application ? 0.32 : 1];

  return `matrix(${scale}, 0, 0, ${scale}, ${280 - scale * x}, ${280 - scale * y})`;
};

export const architectureStateFor = (scene: string) => {
  const view = views[scene];
  const afterWrite = [
    "write-and-hold",
    "cell-hold",
    "lut",
    "flip-flop",
    "logic-block",
    "flip-flop-hold",
    "clb-output-setting",
  ].includes(scene);
  const complete = [
    "lut",
    "flip-flop",
    "logic-block",
    "flip-flop-hold",
    "clb-output-setting",
  ].includes(scene);
  const bits = complete
    ? answers.OR
    : afterWrite
      ? ([0, 1, 0, 1] as const)
      : answers.AND;
  const route: Bit = ["routing-change", "routing-input"].includes(scene)
    ? 1
    : 0;

  const holdingResult = ["flip-flop-hold", "clb-output-setting"].includes(
    scene,
  );

  return {
    view,
    a: (scene === "selector" || holdingResult ? 0 : 1) as Bit,
    b: (scene === "selector" ? 1 : 0) as Bit,
    q: (scene === "logic-block" || holdingResult ? 1 : 0) as Bit,
    captured: scene === "logic-block" || holdingResult,
    bits,
    route,
    cellValue: (afterWrite ? 1 : 0) as Bit,
    access: scene === "write-and-hold",
    incoming: (scene === "routing-input" ? 1 : 0) as Bit,
  };
};

export const useArchitecture = (scene: string) => {
  const state = architectureStateFor(scene);
  const [inputs, setInputs] = useState<{ scene: string; a: Bit; b: Bit }>({
    scene,
    a: state.a,
    b: state.b,
  });
  const [saved, setSaved] = useState<{
    scene: string;
    q: Bit;
    captured: boolean;
  }>({ scene, q: 0, captured: false });
  const a = inputs.scene === scene ? inputs.a : state.a;
  const b = inputs.scene === scene ? inputs.b : state.b;

  useEffect(() => {
    setInputs({
      scene,
      a: state.a,
      b: state.b,
    });
    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const reset = () => {
      const captured = scene === "logic-block" && motion.matches;
      setSaved({ scene, q: captured ? state.q : 0, captured });
    };
    reset();
    motion.addEventListener("change", reset);

    return () => motion.removeEventListener("change", reset);
  }, [scene, state.a, state.b, state.q]);

  return {
    ...state,
    scene,
    a,
    b,
    q:
      scene === "logic-block" ? (saved.scene === scene ? saved.q : 0) : state.q,
    captured:
      scene === "logic-block"
        ? saved.scene === scene && saved.captured
        : state.captured,
    toggleA: () => setInputs({ scene, a: a === 0 ? 1 : 0, b }),
    toggleB: () => setInputs({ scene, a, b: b === 0 ? 1 : 0 }),
    capture: () =>
      setSaved((previous) => {
        const q = state.bits[address(a, b)];
        return previous.scene === scene && previous.q === q && previous.captured
          ? previous
          : { scene, q, captured: true };
      }),
  };
};

type Tour = ReturnType<typeof useArchitecture>;

export const useOutgoingArchitecture = (tour: Tour) => {
  const [previous, setPrevious] = useState(tour);
  const [outgoing, setOutgoing] = useState<Tour>();

  if (
    previous.scene !== tour.scene ||
    previous.a !== tour.a ||
    previous.b !== tour.b ||
    previous.q !== tour.q
  ) {
    setPrevious(tour);

    if (previous.view !== tour.view) {
      const previousScale = previous.view ? frames[previous.view][2] : 1;
      const nextScale = tour.view ? frames[tour.view][2] : 1;
      setOutgoing(previousScale > nextScale ? previous : undefined);
    }
  }

  return outgoing;
};

const SramCell = ({ tour }: { tour: Tour }) => {
  const { cellValue, access } = tour;

  return (
    <g className="fpga-tour-sram" data-access={access}>
      <rect width={560} height={400} rx={8} className="fpga-tour-boundary" />
      <Label x={280} y={37}>
        One SRAM cell · row 01
      </Label>
      <Label x={280} y={67} small>
        Two NOT gates + two access transistors
      </Label>
      <Wire d="M95 190V112H465V190" control active={access} />
      <Label x={280} y={101} small>
        Access {access ? "on" : "off"}
      </Label>
      <path
        d="M243 145L303 175L243 205Z M317 255L257 285L317 315Z"
        className="fpga-gate"
      />
      <circle cx={310} cy={175} r={7} className="fpga-gate" />
      <circle cx={250} cy={285} r={7} className="fpga-gate" />
      <Wire d="M317 175H370V285H317M243 285H190V175H243" active />
      <Label x={280} y={228} small>
        NOT
      </Label>
      <Label x={280} y={341} small>
        NOT
      </Label>
      <circle cx={190} cy={230} r={4} className="fpga-dot" />
      <circle cx={370} cy={230} r={4} className="fpga-dot" />
      <Label x={165} y={259} value>
        {1 - cellValue}
      </Label>
      <circle cx={400} cy={255} r={20} className="fpga-gate" />
      <Label x={400} y={263} value>
        {cellValue}
      </Label>
      <path
        d="M443 308L416 277M418 286L416 277L425 280"
        className="fpga-wire"
      />
      <Label x={452} y={337} small>
        Stored answer
      </Label>
      <Wire d="M40 230H77M483 230H520" control active />
      <Wire d="M113 230H190M370 230H447" control active={access} />
      {[95, 465].map((x) => (
        <g key={x} className="fpga-tour-access-transistor">
          <path
            d={`M${x - 18} 230H${x - 12}V205M${x + 12} 205V230H${x + 18}M${x - 12} 205h6m3 0h6m3 0h6M${x - 18} 190H${x + 18}`}
            className={`fpga-wire ${access ? "fpga-tour-access-on" : ""}`}
          />
        </g>
      ))}
      <Label x={40} y={174} small>
        Write
      </Label>
      <Label x={40} y={202} value>
        0
      </Label>
      <Label x={520} y={174} small>
        Write
      </Label>
      <Label x={520} y={202} value>
        1
      </Label>
    </g>
  );
};

const LutContents = ({ tour, outgoing }: { tour: Tour; outgoing?: Tour }) => {
  const leavingLut = outgoing?.view === "lut" && tour.view !== "lut";
  const leavingCell = outgoing?.view === "cell" && tour.view !== "cell";
  const { a, b, bits, scene } = leavingLut ? outgoing : tour;
  const { view } = tour;
  const selected = address(a, b);
  const table = scene === "truth-table";
  const inputAY = (235 - 165) / lutScale;
  const inputBY = (280 - 165) / lutScale;

  return (
    <>
      <g
        className="fpga-tour-layer fpga-tour-lut-shell"
        data-visible={view === "lut"}
        data-zoom-out={leavingLut}
        aria-hidden={view !== "lut"}
      >
        <rect
          width={560}
          height={lutFrame.bottom}
          rx={6}
          className="fpga-tour-boundary"
        />
        <g opacity={0.5}>
          <Label x={84} y={29} small value>
            AB
          </Label>
        </g>
        <Label x={180} y={24} small>
          Answers
        </Label>
        <Label x={180} y={48} small>
          in SRAM
        </Label>
        {[
          {
            name: "A",
            value: a,
            y: inputAY,
            labelX: -55,
            path: `M${-40 / lutScale} ${(124.444444 - 165) / lutScale}H${-20 / lutScale}V${(235 - 165) / lutScale}H0`,
          },
          {
            name: "B",
            value: b,
            y: inputBY,
            labelX: -18,
            path: `M${-40 / lutScale} ${(280 - 165) / lutScale}H0`,
          },
        ].map((input) => (
          <g key={input.name}>
            <Wire d={input.path} active />
            <Label x={input.labelX} y={input.y - 18} small value anchor="end">
              {input.name} = {input.value}
            </Label>
          </g>
        ))}
        {bits.map((bit, row) => (
          <g key={row}>
            <g opacity={0.5}>
              <Label x={84} y={90 + row * 72} value>
                {Math.floor(row / 2)}
                {row % 2}
              </Label>
              <path
                d={`M106 ${84 + row * 72}H132m-6-4 6 4-6 4`}
                className="fpga-wire"
              />
            </g>
            <Block
              x={140}
              y={60 + row * 72}
              w={80}
              h={48}
              label={String(bit)}
              kind="config"
              active={!table && selected === row}
            />
          </g>
        ))}
        <g opacity={table ? 0.2 : 1}>
          <Wire d="M220 84H235V105H260" active={!table && selected === 0} />
          <Wire d="M220 156H245V135H260" active={!table && selected === 1} />
          <Wire d="M220 228H245V249H260" active={!table && selected === 2} />
          <Wire d="M220 300H235V279H260" active={!table && selected === 3} />
          <Mux
            x={260}
            y={120}
            selection={b}
            name="B"
            showSelectionLabel={false}
          />
          <Mux
            x={260}
            y={264}
            selection={b}
            name="B"
            showSelectionLabel={false}
          />
          <Wire d="M292 120H350V177H420" active={!table && a === 0} />
          <Wire d="M292 264H350V207H420" active={!table && a === 1} />
          <Mux
            x={420}
            y={lutOutputY}
            selection={a}
            name="A"
            showSelectionLabel={false}
          />
          <Wire d={`M0 ${inputAY}H32V350H436V239`} active />
          <path
            d={`M26 ${inputBY}q6-10 12 0M310 270q10-6 0-12`}
            fill="none"
            stroke="var(--fpga-paper)"
            strokeWidth={7}
          />
          <Wire
            d={`M0 ${inputBY}H26q6-10 12 0H52V336H310V270q10-6 0-12V167H276M310 311H276`}
            active
          />
          <circle cx={310} cy={311} r={3} className="fpga-dot" />
          <Wire d={`M452 ${lutOutputY}H560`} active={!table} />
          <Label x={506} y={164} small>
            Output
          </Label>
          <Label x={506} y={226} value>
            {bits[selected]}
          </Label>
        </g>
        <Wire d={`M560 ${lutOutputY}H584`} active />
      </g>
      <g
        transform="translate(146.4 132) scale(0.12)"
        className="fpga-tour-layer"
        data-visible={view === "cell"}
        data-zoom-out={leavingCell}
        aria-hidden={view !== "cell"}
      >
        <SramCell tour={leavingCell ? outgoing : tour} />
      </g>
    </>
  );
};

const ClbResources = ({
  visible,
  leaving,
}: {
  visible: boolean;
  leaving: boolean;
}) => (
  <g
    className="fpga-tour-layer fpga-tour-clb-resources"
    data-visible={visible}
    data-zoom-out={leaving}
    aria-hidden={!visible}
  >
    {Array.from({ length: 8 }, (_, index) => {
      const x = 22 + (index % 2) * 278;
      const y = 108 + Math.floor(index / 2) * 102;
      const selected = index === 0;

      return (
        <g key={index}>
          {!selected && (
            <>
              <Block x={x} y={y} w={84} h={38} label="LUT" />
              <Block
                x={x + 120}
                y={y}
                w={116}
                h={38}
                label="Flip-flop"
                kind="storage"
              />
            </>
          )}
          <Block
            x={x + 120}
            y={y + 48}
            w={116}
            h={38}
            label="Flip-flop"
            kind="storage"
          />
        </g>
      );
    })}
  </g>
);

const LogicBlock = ({ tour, outgoing }: { tour: Tour; outgoing?: Tour }) => {
  const { view } = tour;
  const visible = view === "clb-overview" || view === "clb";
  const leaving =
    !visible && (outgoing?.view === "clb" || outgoing?.view === "clb-overview");
  const block = leaving ? outgoing : tour;
  const connected = block.view === "clb";
  const showingResult = [
    "flip-flop",
    "logic-block",
    "flip-flop-hold",
    "clb-output-setting",
  ].includes(block.scene);
  const overview = block.view === "clb-overview";
  const showingSetting = block.scene === "clb-output-setting";
  const showingOutputChoice =
    block.scene === "flip-flop-hold" || showingSetting;
  const d = block.bits[address(block.a, block.b)];

  return (
    <g transform={`translate(124 124) scale(${clbScale})`}>
      <g
        className="fpga-tour-layer"
        data-visible={visible}
        data-context={view === "lut" && !leaving}
        data-zoom-out={leaving}
        aria-hidden={!visible}
      >
        <rect
          y={overview ? 80 : 0}
          width={560}
          height={overview ? 440 : 560}
          rx={10}
          className="fpga-tour-boundary"
        />
      </g>
      <ClbResources
        visible={visible && overview}
        leaving={leaving && overview}
      />
      <g
        className="fpga-tour-layer fpga-tour-clb-shell"
        data-visible={visible}
        data-overview={overview}
        data-context={view === "lut" && !leaving}
        data-zoom-out={leaving}
        aria-hidden={!visible}
      >
        <g
          className="fpga-tour-layer fpga-tour-connections"
          data-visible={connected}
          data-context={view === "lut" && !leaving}
          aria-hidden={view !== "clb"}
        >
          <Wire d="M0 124.444444H20V235H40M0 280H40" active />
          <Label x={-12} y={104} small value anchor="end">
            A = {block.a}
          </Label>
          <Label x={-12} y={260} small value anchor="end">
            B = {block.b}
          </Label>
          <Wire d={`M310 ${clbLutOutputY}H345V295H360`} active />
          <Label x={350} y={clbLutOutputY - 18} value>
            {d}
          </Label>
          <Wire d="M560 280H640" active />
          <Label x={600} y={260} value>
            {block.q}
          </Label>
          <Wire d="M435 340V425" />
          <Label x={435} y={463} small>
            Clock
          </Label>
          {showingOutputChoice ? (
            <g>
              <Wire d={`M330 ${clbLutOutputY}V160H520V265H530`} />
              <path d="M530 245l20 12v46l-20 12z" className="fpga-gate" />
              <Wire d="M510 295H530M550 280H560" active />
              <circle cx={330} cy={clbLutOutputY} r={3} className="fpga-dot" />
              {showingSetting && <Wire d="M530 295H540V280H550" active />}
            </g>
          ) : (
            <Wire d="M510 295H540V280H560" active />
          )}
        </g>
        <g
          className="fpga-tour-layer fpga-tour-output-setting"
          data-visible={(visible || leaving) && showingSetting}
          aria-hidden={!visible || !showingSetting}
        >
          <Label x={472} y={38} small>
            SRAM
          </Label>
          <g transform="translate(472 93)">
            <SramFeedback />
          </g>
          <circle cx={520} cy={95} r={3} className="fpga-dot" />
          <Label x={540} y={80} value>
            1
          </Label>
          <Wire d="M520 95H540V251" control active />
        </g>
        <g
          className="fpga-tour-resource fpga-block fpga-block--logic is-selected"
          style={{
            transform: overview
              ? "translate(22px, 108px)"
              : "translate(40px, 165px)",
          }}
        >
          <rect
            width={270}
            height={view === "lut" ? lutFrame.bottom * lutScale : 185}
            rx={5}
            style={{
              transform: overview
                ? "scale(0.3111111111, 0.2054054054)"
                : "scale(1, 1)",
            }}
          />
          <g
            className="fpga-tour-resource-label"
            style={{
              transform: overview
                ? "translate(42px, 25px)"
                : "translate(135px, -18px)",
            }}
          >
            <Label x={0} y={0}>
              {overview ? "LUT" : `LUT set to ${showingResult ? "OR" : "AND"}`}
            </Label>
          </g>
        </g>
        <g
          className="fpga-tour-resource fpga-block fpga-block--storage is-selected"
          style={{
            transform: overview
              ? "translate(142px, 108px)"
              : "translate(360px, 250px)",
          }}
        >
          <rect
            width={150}
            height={90}
            rx={4}
            style={{
              transform: overview
                ? "scale(0.7733333333, 0.4222222222)"
                : "scale(1, 1)",
            }}
          />
          <g
            className="fpga-tour-resource-label"
            style={{
              transform: overview
                ? "translate(58px, 25px)"
                : "translate(75px, -18px)",
            }}
          >
            <Label x={0} y={0}>
              Flip-flop
            </Label>
          </g>
          <g
            className="fpga-tour-layer"
            data-visible={connected}
            aria-hidden={view !== "clb"}
          >
            {showingResult && (
              <>
                <Label x={75} y={32} small>
                  Saved value
                </Label>
                <Label x={75} y={67} value>
                  {block.q}
                </Label>
              </>
            )}
            <path d="M60 90l15 -14 15 14" className="fpga-wire" />
          </g>
        </g>
        {block.scene === "logic-block" && (
          <g className="fpga-tour-capture" aria-hidden="true">
            <circle cx={435} cy={425} r={12} className="fpga-tour-clock-edge" />
            <circle
              r={5}
              className="fpga-tour-clock-packet"
              style={{ offsetPath: 'path("M435 425V340")' } as CSSProperties}
            />
            <circle
              r={7}
              className="fpga-tour-data-packet"
              style={
                {
                  offsetPath: `path("M330 ${clbLutOutputY}H345V295H540V280H640")`,
                } as CSSProperties
              }
              onAnimationStart={leaving ? undefined : tour.capture}
              onAnimationIteration={leaving ? undefined : tour.capture}
            />
          </g>
        )}
      </g>
      <g transform={`translate(40 165) scale(${lutScale})`}>
        <LutContents tour={tour} outgoing={outgoing} />
      </g>
    </g>
  );
};

const RoutingJunction = ({
  tour,
  outgoing,
}: {
  tour: Tour;
  outgoing?: Tour;
}) => {
  const visible = tour.view === "junction";
  const leaving = !visible && outgoing?.view === "junction";
  const { route, incoming } = leaving ? outgoing : tour;

  return (
    <g
      transform={`translate(198 ${220 - 200 * routingScale}) scale(${routingScale})`}
      className="fpga-tour-layer fpga-tour-routing"
      data-visible={visible}
      data-zoom-out={leaving}
      aria-hidden={!visible}
    >
      <rect
        y={36}
        width={560}
        height={364}
        rx={8}
        className="fpga-tour-boundary"
      />
      <Wire d={`M0 ${routingUpperY}H205V170H265`} active={route === 0} />
      <Wire d={`M0 ${routingLowerY}H205V230H265`} active={route === 1} />
      <Label x={90} y={routingUpperY - 24} small>
        From CLB 1
      </Label>
      <Label x={90} y={routingUpperY + 30} value>
        1
      </Label>
      <Label x={90} y={routingLowerY - 24} small>
        From CLB 4
      </Label>
      <Label x={90} y={routingLowerY + 30} value>
        {incoming}
      </Label>
      <g transform="translate(265 200) scale(2)">
        <Mux
          x={0}
          y={0}
          selection={route}
          name="Stored setting"
          showSelectionLabel={false}
        />
      </g>
      <Wire d="M329 200H560" active />
      <Label x={470} y={176} small>
        To CLB 5
      </Label>
      <Label x={470} y={230} value>
        {route === 0 ? 1 : incoming}
      </Label>
      <g className="fpga-block fpga-block--config is-selected">
        <rect x={233} y={288} width={150} height={72} rx={4} />
        <g transform="translate(275 324) scale(0.6)">
          <SramFeedback />
        </g>
        <circle cx={303.8} cy={324} r={2} className="fpga-dot" />
        <Wire d="M303.8 324H337V294H297V248" control active />
        <Label x={357} y={331} value>
          {route}
        </Label>
      </g>
      <Label x={396} y={321} small anchor="start">
        Stored setting
      </Label>
      <Label x={396} y={345} small anchor="start">
        in SRAM
      </Label>
    </g>
  );
};

export const ArchitectureContents = ({
  tour,
  outgoing,
}: {
  tour: Tour;
  outgoing?: Tour;
}) => (
  <>
    <LogicBlock tour={tour} outgoing={outgoing} />
    <RoutingJunction tour={tour} outgoing={outgoing} />
  </>
);

export const ArchitectureControls = ({ tour }: { tour: Tour }) => {
  const controls = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    const element = controls.current;
    const host = element?.closest<HTMLElement>(".fpga-application-tour");
    const drawing = host?.querySelector<SVGSVGElement>(".fpga-drawing");
    if (tour.view !== "lut" || !element || !host || !drawing) return;

    const update = () => {
      const matrix = drawing.getScreenCTM();
      if (!matrix) return;

      const scale = 560 / lutFrame.width;
      const point = new DOMPoint(
        280 + (280 - lutFrame.x) * scale,
        280 + (lutFrame.bottom - lutFrame.y) * scale,
      ).matrixTransform(matrix);
      const bounds = host.getBoundingClientRect();
      element.style.left = `${point.x - bounds.left}px`;
      element.style.top = `${point.y - bounds.top + 12}px`;
    };
    const resize = new ResizeObserver(update);
    resize.observe(drawing);
    update();

    return () => {
      resize.disconnect();
      element.style.removeProperty("left");
      element.style.removeProperty("top");
    };
  }, [tour.scene, tour.view]);

  return ["selector", "lut"].includes(tour.scene) ? (
    <div
      ref={controls}
      className="fpga-controls"
      role="group"
      aria-label="Try the circuit"
    >
      <span className="sr-only" role="status">
        Inputs {tour.a}
        {tour.b} select answer {tour.bits[address(tour.a, tour.b)]}.
        {" The stored rule is unchanged."}
      </span>
      <BitControls name="A" value={tour.a} onChange={tour.toggleA} />
      <BitControls name="B" value={tour.b} onChange={tour.toggleB} />
    </div>
  ) : null;
};

export const ArchitectureLocation = ({ scene }: { scene: string }) => {
  const view = views[scene];

  if (!view) return null;

  return (
    <p className="fpga-tour-location">
      {view === "cell"
        ? "FPGA › CLB › LUT › One SRAM cell"
        : view === "lut"
          ? "FPGA › CLB › LUT"
          : view === "clb-overview"
            ? "FPGA › One CLB"
            : view === "clb"
              ? "FPGA › CLB › Selected example"
              : view === "junction"
                ? "FPGA › Routing junction"
                : "Whole FPGA"}
    </p>
  );
};
