import { useEffect, useState } from "react";
import type { CSSProperties } from "react";
import { useApplicationMotion } from "./ApplicationEnvironments";
import { Block, Label, Wire } from "./drawing";
import "./board.css";

type Point = readonly [number, number];

const wirePath = (points: readonly Point[]) =>
  `M${points.map(([x, y]) => `${x} ${y}`).join("L")}`;

const tokenWire = [
  [185, 262],
  [275, 262],
  [275, 266.8],
  [313, 266.8],
] as const;
const scoresWire = [
  [313, 293.2],
  [265, 293.2],
  [265, 290],
  [185, 290],
] as const;
const laptopWire = [
  [130, 115],
  [130, 122],
  [70, 122],
  [70, 131],
] as const;
const ethernetWire = [
  [70, 163],
  [70, 181],
  [55, 181],
  [55, 309],
  [96, 309],
  [96, 320],
] as const;
const controllerWire = [
  [130, 300],
  [130, 320],
] as const;

const flashWire = [
  [209, 352],
  [209, 389],
  [415, 389],
  [415, 400],
] as const;
const sdWire = [
  [75, 336],
  [55, 336],
  [55, 460],
  [130, 460],
  [130, 475],
] as const;
const ddrWire = [
  [110, 352],
  [110, 400],
] as const;

const tokenPath = wirePath(tokenWire);
const scoresPath = wirePath(scoresWire);
const laptopToEthernet = wirePath(laptopWire);
const ethernetToControllers = wirePath(ethernetWire);
const cpuToControllers = wirePath(controllerWire);

const cpu = [164, 280] as const;
const fpga = [326, 280] as const;
const controllerToCpu: Point[] = [
  [130, 328],
  ...[...controllerWire].reverse(),
  [130, 294],
  [164, 294],
  cpu,
];
const promptRoute: Point[] = [
  ...laptopWire,
  ...ethernetWire,
  [96, 328],
  ...controllerToCpu,
];
const tokenRoute = wirePath([
  cpu,
  [164, 262],
  ...tokenWire,
  [326, 266.8],
  fpga,
]);
const scoresRoute = wirePath([
  fpga,
  [326, 293.2],
  ...scoresWire,
  [164, 290],
  cpu,
]);

type RequestBeat = {
  activity:
    "firmware" | "linux" | "prompt" | "token" | "scores" | "reply" | "complete";
  shown: number;
  duration: number;
  quick?: boolean;
  route?: string;
  forwardToken?: boolean;
};

const requestPrompt = "We need more chips.";
const requestReply =
  "The wafer fab rejected our potatoes. Apparently 'locally sourced organic' isn't a process node";
const replyLength = requestReply.length;
const replyRoute = wirePath([...promptRoute].reverse());

const bootBeats: readonly RequestBeat[] = [
  {
    activity: "firmware",
    shown: 0,
    duration: 1050,
    route: wirePath([
      ...[...flashWire].reverse(),
      [209, 328],
      ...controllerToCpu,
    ]),
  },
  {
    activity: "linux",
    shown: 0,
    duration: 1450,
    route: wirePath([
      ...[...sdWire].reverse(),
      [110, 336],
      ...ddrWire,
      ddrWire[0],
      [110, 328],
      ...controllerToCpu,
    ]),
  },
];

const requestBeats: readonly RequestBeat[] = [
  ...bootBeats,
  {
    activity: "prompt",
    shown: 0,
    duration: 1450,
    route: wirePath(promptRoute),
  },
  { activity: "token", shown: 0, duration: 560, route: tokenRoute },
  ...Array.from({ length: replyLength }, (_, shown): RequestBeat[] => {
    const quick = shown >= 2;
    return [
      {
        activity: "scores",
        shown,
        duration: quick ? 90 : 730,
        quick,
        route: scoresRoute,
      },
      {
        activity: "reply",
        shown,
        duration: quick ? 115 : 1100,
        quick,
        route: replyRoute,
        forwardToken: shown + 1 < replyLength,
      },
    ];
  }).flat(),
  { activity: "complete", shown: replyLength, duration: 3900 },
];

export const BoardFigure = ({
  request,
  lecture = false,
}: {
  request: boolean;
  lecture?: boolean;
}) => {
  const { host, running } = useApplicationMotion<SVGGElement>();
  const [step, setStep] = useState(0);
  const [reducedMotion, setReducedMotion] = useState(false);
  const playing = request && running && !reducedMotion;
  const slowdown = lecture ? 3 : 1;
  const { activity, shown, duration, quick, route, forwardToken } =
    requestBeats[step];
  const nextStep =
    step === requestBeats.length - 1 ? bootBeats.length : step + 1;

  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReducedMotion(media.matches);

    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    if (!request) setStep(0);
    if (!playing || route) return;

    const timer = window.setTimeout(
      () => setStep(nextStep),
      duration * slowdown,
    );
    return () => window.clearTimeout(timer);
  }, [request, playing, nextStep, duration, route, slowdown]);

  const staticRequest = request && reducedMotion;
  const loadingFirmware = request && !staticRequest && activity === "firmware";
  const loadingLinux = request && !staticRequest && activity === "linux";
  const startupMessage = loadingFirmware
    ? "Read firmware from boot flash."
    : "Load Linux from microSD into DDR4. Arm runs it from there.";
  const startingUp = loadingFirmware || loadingLinux;
  const prompt = request && activity === "prompt";
  const replying = request && activity === "reply";
  const sendingToken = request && (activity === "token" || forwardToken);
  const returningScores = request && activity === "scores";
  const networkActive = staticRequest || prompt || replying;

  return (
    <g
      ref={host}
      className="fpga-board"
      style={{ "--fpga-board-slowdown": slowdown } as CSSProperties}
      data-request={request}
      data-activity={
        staticRequest ? "complete" : request ? activity : undefined
      }
      data-playing={playing}
      data-quick={quick}
    >
      <g className="fpga-world-equipment">
        <rect x={-10} y={130} width={580} height={385} rx={12} />
        <rect x={20} y={165} width={520} height={285} rx={8} />
        <rect x={45} y={200} width={470} height={178} rx={6} />
      </g>
      <Label x={300} y={153}>
        KV260 carrier board
      </Label>
      <Label x={300} y={190} small>
        K26 module
      </Label>
      <Label
        x={75}
        y={200}
        anchor="start"
        small
        className="fpga-board-chip-label"
      >
        Zynq chip
      </Label>
      <Label x={390} y={223} small>
        FPGA logic
      </Label>

      <g className="fpga-board-support">
        <Wire d={wirePath(ddrWire)} active={loadingLinux} />
        <Wire d={wirePath(flashWire)} active={loadingFirmware} />
        <Wire d={wirePath(sdWire)} active={loadingLinux} />
        <Block x={75} y={320} w={170} h={32} label="Controllers" />
        <Block x={65} y={400} w={170} h={38} label="DDR4 RAM" kind="memory" />
        <Block
          x={335}
          y={400}
          w={160}
          h={38}
          label="Boot flash"
          kind="config"
        />
        <Block x={65} y={475} w={130} h={32} label="microSD" kind="storage" />
        <Wire d="M582 480H530V450" />
        <path d="M578 476l-6 4 6 4" className="fpga-wire" />
        <Label x={480} y={505} small>
          Power in
        </Label>
      </g>

      <Wire d={ethernetToControllers} active={networkActive} />
      <Wire d={cpuToControllers} active={networkActive || startingUp} />
      <Block x={15} y={131} w={110} h={32} label="Ethernet" />
      <Block x={75} y={250} w={110} h={50} label="CPU" />
      <g className="fpga-board-data">
        <Wire d={tokenPath} active={staticRequest || sendingToken} />
        <Wire d={scoresPath} active={staticRequest || returningScores} />
        <path d="M307 262.8l6 4-6 4M191 286l-6 4 6 4" className="fpga-wire" />
        <Label x={230} y={252} small>
          Token
        </Label>
        <Label x={258} y={312} small>
          Scores
        </Label>
      </g>

      <g className="fpga-board-laptop">
        <g className="fpga-world-equipment">
          <rect
            className="fpga-board-laptop-display"
            x={65}
            y={51}
            width={130}
            height={55}
            rx={4}
          />
          <path
            className="fpga-board-laptop-base"
            d="M65 106L53 115H207L195 106"
          />
        </g>
        {request ? (
          <foreignObject x={77} y={8} width={246} height={94}>
            <div className="fpga-board-screen">
              <div className="fpga-board-screen-header">
                <span>
                  {startingUp ? (
                    "Starting the board"
                  ) : (
                    <>
                      Prompt<code>“{requestPrompt}”</code>
                    </>
                  )}
                </span>
              </div>
              <div className="fpga-board-reply">
                {startingUp
                  ? startupMessage
                  : requestReply.slice(0, staticRequest ? replyLength : shown)}
              </div>
            </div>
          </foreignObject>
        ) : (
          <Label x={130} y={86}>
            Laptop
          </Label>
        )}
        {request && (
          <Label x={349} y={60} anchor="start" small>
            Laptop
          </Label>
        )}
        <Wire d={laptopToEthernet} active={networkActive} />
      </g>

      {request && route && !reducedMotion && (
        <g key={step} aria-hidden="true">
          {forwardToken && (
            <circle
              r={4}
              className="fpga-board-request-marker"
              style={{
                offsetPath: `path("${tokenRoute}")`,
                animationDuration: `${duration * slowdown * 0.7}ms`,
              }}
            />
          )}
          <circle
            r={4}
            className="fpga-board-request-marker"
            style={{
              offsetPath: `path("${route}")`,
              animationDuration: `${duration * slowdown}ms`,
            }}
            onAnimationEnd={() => setStep(nextStep)}
          />
        </g>
      )}
    </g>
  );
};
