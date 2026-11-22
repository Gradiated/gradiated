import { useEffect, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { Label } from "./drawing";

export const applicationScenes = [
  "why-fpgas",
  "why-display",
  "why-prototype",
] as const;
export type Application = "cern" | "display" | "prototype";

export const applicationFor = (scene: string): Application | undefined =>
  scene === "why-fpgas"
    ? "cern"
    : scene === "why-display"
      ? "display"
      : scene === "why-prototype"
        ? "prototype"
        : undefined;

export const applicationTitles = {
  cern: "At CERN, particles leave measurements in a layered detector. Electronic signals reach an FPGA, which helps choose events for further analysis. Particle tracks and electronic data are different parts of the drawing.",
  display:
    "A yellow patch moves one pixel at a time across the incoming picture. The FPGA sends four groups of pixels to four LED driver circuits. All four display tiles show the same completed frame together.",
  prototype:
    "The same FPGA sits on a prototype board. A laptop loads a circuit, tests an incorrect result, then loads a correction and tests again. The proposed design can later be implemented as a separate ASIC.",
};

export const useApplicationMotion = <T extends Element = HTMLDivElement>() => {
  const host = useRef<T>(null);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    const element = host.current;
    if (!element) return;

    let visible = false;
    const update = () => setRunning(visible && !document.hidden);
    const observer = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      update();
    });
    observer.observe(element.closest(".fpga-stage") ?? element);
    document.addEventListener("visibilitychange", update);

    return () => {
      observer.disconnect();
      document.removeEventListener("visibilitychange", update);
    };
  }, []);

  return { host, running };
};

const Packet = ({
  path,
  className = "",
  delay = 0,
}: {
  path: string;
  className?: string;
  delay?: number;
}) => (
  <rect
    x={-2.5}
    y={-2.5}
    width={5}
    height={5}
    rx={0.6}
    className={`fpga-app-packet ${className}`}
    style={
      {
        offsetPath: `path('${path}')`,
        "--packet-delay": `${delay}s`,
      } as CSSProperties
    }
  />
);

const Computer = ({
  x,
  y,
  laptop = false,
}: {
  x: number;
  y: number;
  laptop?: boolean;
}) => (
  <g className="fpga-app-equipment">
    <rect x={x} y={y} width={128} height={86} rx={4} />
    <rect x={x + 7} y={y + 7} width={114} height={67} rx={1} />
    {laptop ? (
      <path d={`M${x} ${y + 86}l-12 13h152l-12 -13M${x + 48} ${y + 91}h32`} />
    ) : (
      <path d={`M${x + 54} ${y + 86}v15h-25h70h-25v-15`} />
    )}
  </g>
);

const tracks = [
  { d: "M78 264Q114 242 148 235", x: 148, y: 235 },
  { d: "M78 264Q106 220 110 184", x: 110, y: 184 },
  { d: "M78 264Q75 222 58 188", x: 58, y: 188 },
  { d: "M78 264Q42 232 11 227", x: 11, y: 227 },
  { d: "M78 264Q39 266 5 284", x: 5, y: 284 },
  { d: "M78 264Q61 287 31 308", x: 31, y: 308 },
  { d: "M78 264Q85 309 112 350", x: 112, y: 350 },
  { d: "M78 264Q113 279 162 294", x: 162, y: 294 },
  { d: "M78 264Q114 299 133 319", x: 133, y: 319 },
  { d: "M78 264Q62 296 70 316", x: 70, y: 316 },
];

const cernReadouts = [222.4, 260.8, 299.2].map((y) => {
  const angle = Math.asin((y - 264) / 108);
  const x = 78 + 100 * Math.cos(angle);
  const contactY = 264 + 100 * Math.sin(angle);
  const path = `M${78 + 108 * Math.cos(angle)} ${y}H200.64`;

  return { y, x, contactY, angle: (angle * 180) / Math.PI, path };
});

export const CernEnvironment = () => (
  <g className="fpga-app-cern">
    <g className="fpga-app-equipment fpga-detector">
      {[42, 63, 84, 100].map((r) => (
        <circle key={r} cx={78} cy={264} r={r} />
      ))}
      {Array.from({ length: 20 }, (_, i) => {
        const a = (i * Math.PI) / 10;
        return (
          <path
            key={i}
            d={`M${78 + 84 * Math.cos(a)} ${264 + 84 * Math.sin(a)}L${78 + 100 * Math.cos(a)} ${264 + 100 * Math.sin(a)}`}
          />
        );
      })}
      <path d="M-24 264H48M108 264H180" className="fpga-app-beamline" />
    </g>
    <Label x={78} y={141}>
      CERN detector
    </Label>
    <Label x={78} y={394} small>
      Particle collision
    </Label>
    <Computer x={438} y={237} />
    {[0, 2.5].map((delay, event) => (
      <g
        key={event}
        className={`fpga-collision-event ${event ? "is-rejected" : "is-kept"}`}
        style={{ "--event-delay": `${delay}s` } as CSSProperties}
      >
        <circle cx={78} cy={264} r={4} className="fpga-collision-flash" />
        {tracks.map(({ d, x, y }) => (
          <g key={d}>
            <path d={d} pathLength={1} className="fpga-particle-track" />
            <circle
              r={2}
              className="fpga-particle-head"
              style={{ offsetPath: `path('${d}')` }}
            />
            <circle cx={x} cy={y} r={3.4} className="fpga-detector-hit" />
          </g>
        ))}
        {cernReadouts.map(({ y, path }, i) => (
          <Packet
            key={y}
            path={path}
            className="fpga-cern-input"
            delay={delay + i * 0.08}
          />
        ))}
        <Packet
          path="M359.36 260.8H410V280H438"
          className="fpga-cern-decision"
          delay={delay}
        />
        <g className="fpga-cern-result">
          <path
            d={event ? "M494 263l16 16m0 -16l-16 16" : "M489 271l9 9 17 -18"}
            className="fpga-app-result-mark"
          />
          <Label x={502} y={299} small>
            {event ? "Skip" : "Keep"}
          </Label>
        </g>
      </g>
    ))}
    <g className="fpga-app-equipment">
      {cernReadouts.map(({ y, x, contactY, angle, path }) => (
        <g key={y}>
          <rect
            x={0}
            y={-6}
            width={8}
            height={12}
            rx={1}
            transform={`translate(${x} ${contactY}) rotate(${angle})`}
          />
          <path d={path} />
        </g>
      ))}
      <path d="M359.36 260.8H410V280H438" />
    </g>
    <Label x={502} y={367} small>
      Event selection
    </Label>
    <Label x={502} y={390} small>
      Further analysis
    </Label>
  </g>
);

const Picture = ({
  x,
  y,
  size = 10,
  tiled = false,
  delay = 0,
}: {
  x: number;
  y: number;
  size?: number;
  tiled?: boolean;
  delay?: number;
}) => (
  <g
    className="fpga-app-pixels"
    style={{ "--picture-delay": `${delay}s` } as CSSProperties}
  >
    {Array.from({ length: 12 }, (_, j) =>
      Array.from({ length: 12 }, (_, i) => {
        const pixel = {
          x: x + i * size,
          y: y + j * size + (tiled ? Math.floor(j / 3) * 8.4 : 0),
          width: size - 1.5,
          height: size - 1.5,
        };

        return (
          <g key={`${i}-${j}`}>
            <rect {...pixel} />
            {j >= 4 && j < 7 && (
              <rect
                {...pixel}
                className={`is-lit fpga-display-blob ${i < 3 ? "is-start" : ""}`}
                style={
                  {
                    "--pixel-phase": `${-((2 - i + 12) % 12) * 0.4}s`,
                  } as CSSProperties
                }
              />
            )}
          </g>
        );
      }),
    )}
  </g>
);

export const DisplayEnvironment = () => (
  <g className="fpga-app-display">
    <Label x={72} y={188}>
      Incoming picture
    </Label>
    <g className="fpga-app-equipment">
      <rect x={0} y={205} width={145} height={150} rx={4} />
      <path d="M60 355v16H36h73H85v-16M145 222.4H200.64" />
    </g>
    <Picture x={12} y={219} />
    {[0, 0.1, 0.2, 0.3].map((delay) => (
      <Packet
        key={delay}
        path="M145 222.4H200.64"
        className="fpga-display-input"
        delay={delay}
      />
    ))}
    <Label x={500} y={188}>
      LED video wall
    </Label>
    {[222.4, 260.8, 299.2, 337.6].map((y, i) => (
      <g key={y}>
        <g className="fpga-app-equipment">
          <path d={`M359.36 ${y}H395M407 ${y}H432`} />
          <rect x={395} y={y - 5} width={12} height={10} rx={1} />
          <rect x={432} y={y - 18} width={136} height={36} rx={1} />
        </g>
        <Packet
          path={`M359.36 ${y}H432`}
          className="fpga-display-output"
          delay={0.2 + i * 0.1}
        />
      </g>
    ))}
    <Picture x={440} y={208} tiled delay={0.2} />
    <Label x={500} y={390} small>
      Four coordinated tiles
    </Label>
    <Label x={400} y={367} small>
      Drivers
    </Label>
  </g>
);

export const PrototypeEnvironment = () => (
  <g className="fpga-app-prototype">
    <Computer x={0} y={237} laptop />
    <g className="fpga-app-equipment">
      <rect x={191} y={191} width={178} height={178} rx={6} />
      {[
        [198, 198],
        [362, 198],
        [198, 362],
        [362, 362],
      ].map(([x, y]) => (
        <circle key={`${x}-${y}`} cx={x} cy={y} r={2} />
      ))}
      <path d="M128 260.8H200.64M359.36 299.2H388V413H64V336" />
      <path d="M64 237V156H502V237" className="fpga-app-design-path" />
      <rect x={455} y={237} width={94} height={94} rx={4} />
      {[472, 502, 532].map((x) => (
        <path key={x} d={`M${x} 227v10m0 94v10`} />
      ))}
      {[254, 284, 314].map((y) => (
        <path key={y} d={`M445 ${y}h10m94 0h10`} />
      ))}
      <path d="M470 267h18l21 17 -21 17h-18zM510 284h22" />
    </g>
    <Label x={283} y={144} small>
      Design for a future chip
    </Label>
    <Label x={502} y={366}>
      Future ASIC
    </Label>
    <g className="fpga-prototype-fail">
      <path d="M56 259l16 16m0 -16l-16 16" className="fpga-app-result-mark" />
      <Label x={64} y={297} small>
        Test: 0 ≠ 1
      </Label>
    </g>
    <g className="fpga-prototype-pass">
      <path d="M51 267l9 9 17 -18" className="fpga-app-result-mark" />
      <Label x={64} y={297} small>
        Test: 1 = 1
      </Label>
    </g>
    <Packet path="M128 260.8H200.64" className="fpga-prototype-write" />
    <Packet path="M128 260.8H200.64" className="fpga-prototype-test" />
    <Packet
      path="M359.36 299.2H388V413H64V336"
      className="fpga-prototype-return"
    />
  </g>
);

export const ApplicationCircuit = ({
  application,
}: {
  application: Application;
}) => (
  <g className={`fpga-app-circuit fpga-app-circuit--${application}`}>
    {application === "prototype" && (
      <rect
        x={124}
        y={124}
        width={72}
        height={72}
        rx={4}
        className="fpga-prototype-config"
      />
    )}
    <path
      d={
        application === "cern"
          ? "M32 100H100V160H124M32 220H108V180H124M32 340H100V280H124"
          : application === "prototype"
            ? "M32 220H108V180H124"
            : "M32 100H100V160H124"
      }
      className="fpga-app-circuit-input"
    />
    <path
      d="M196 160H220V160H244M316 160H340V160H364M220 280H244M316 280H340V280H364M220 160V400H244M316 400H340V400H364"
      className="fpga-app-circuit-work"
    />
    {application === "cern" && (
      <path d="M196 280H208V300H244" className="fpga-app-circuit-work" />
    )}
    <path
      d={
        application === "display"
          ? "M436 160H460V100H528M436 280H452V220H528M436 400H460V340H528M316 400H340V460H528"
          : application === "prototype"
            ? "M436 280H460V340H528"
            : "M436 280H460V220H528"
      }
      className="fpga-app-circuit-output"
    />
  </g>
);
