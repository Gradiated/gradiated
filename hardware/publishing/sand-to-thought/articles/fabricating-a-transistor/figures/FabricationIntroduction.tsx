import { useLayoutEffect, useState } from "react";
import type { RefObject } from "react";
import { SmallWafer } from "./FabricationMachine";
import { portion, stages } from "./process";
import type { PatternState } from "./process";

export const initialOpening = {
  destination: 1,
  wafer: 0,
  centred: 1,
  gloves: 0,
  room: 0,
  operator: 0,
  entry: 0,
  transfer: 0,
  magnify: 0,
  machines: 0,
};
export type OpeningState = typeof initialOpening;

const openingScene: Record<keyof OpeningState, number> = {
  destination: stages.wafer,
  wafer: stages.wafer,
  centred: stages.cleanRoom,
  gloves: stages.cleanRoom,
  room: stages.cleanRoom,
  operator: stages.operator,
  entry: stages.operator,
  transfer: stages.handOff,
  magnify: stages.magnify,
  machines: stages.layout,
};

export const openingState = (
  index: number,
  progress: number,
  from: OpeningState,
): OpeningState => {
  const target: OpeningState = {
    destination: index === 0 ? 1 : 0,
    wafer: index >= stages.wafer ? 1 : 0,
    centred: index < stages.cleanRoom ? 1 : 0,
    gloves: index >= stages.cleanRoom ? 1 : 0,
    room: index >= stages.cleanRoom ? 1 : 0,
    operator: index >= stages.operator ? 1 : 0,
    entry: index >= stages.operator ? 1 : 0,
    transfer: index >= stages.handOff ? 1 : 0,
    magnify: index >= stages.magnify ? 1 : 0,
    machines: index >= stages.layout ? 1 : 0,
  };

  return Object.fromEntries(
    (Object.keys(target) as (keyof OpeningState)[]).map((key) => {
      if (index > openingScene[key]) return [key, target[key]];

      const start =
        index === stages.wafer && key === "wafer"
          ? 0.28
          : index === stages.cleanRoom && key === "room"
            ? 0.5
            : index === stages.cleanRoom && key === "gloves"
              ? 0.25
              : index === stages.operator && key === "entry"
                ? 0.25
                : index === stages.operator && key === "operator"
                  ? 0.16
                  : 0;
      const end =
        key === "destination"
          ? 0.38
          : index === stages.operator && key === "entry"
            ? 0.7
            : index === stages.operator && key === "operator"
              ? 0.25
              : 1;
      const t = portion(progress, start, end);

      return [key, from[key] + (target[key] - from[key]) * t];
    }),
  ) as OpeningState;
};

type Layout = {
  dx: number;
  dy: number;
  scale: number;
  source: { x: number; y: number; rx: number; ry: number };
  target: { x: number; y: number; rx: number; ry: number };
};

export const useOpeningLayout = (host: RefObject<HTMLDivElement | null>) => {
  const [layout, setLayout] = useState<Layout>();

  useLayoutEffect(() => {
    const canvas = host.current;
    const panel = canvas?.querySelector(".fab-wafer-panel");
    const wafer = panel?.querySelector<SVGSVGElement>(".fab-whole-wafer");
    const room = canvas?.querySelector(".fab-room");
    if (!canvas || !panel || !wafer || !room) return;

    const measure = () => {
      const bounds = canvas.getBoundingClientRect();
      const panelBounds = panel.getBoundingClientRect();
      const roomBounds = room.getBoundingClientRect();
      const scale = Math.min(wafer.clientWidth / 280, wafer.clientHeight / 264);
      const source = {
        x: panelBounds.left - bounds.left + wafer.clientWidth / 2,
        y: panelBounds.top - bounds.top + wafer.clientHeight / 2 - 13 * scale,
        rx: 95 * scale,
        ry: 76 * scale,
      };
      const target = {
        x: roomBounds.left - bounds.left + (332 / 640) * roomBounds.width,
        y: roomBounds.top - bounds.top + (128 / 258) * roomBounds.height,
        rx: (8 / 640) * roomBounds.width,
        ry: (5 / 258) * roomBounds.height,
      };
      setLayout({
        dx: bounds.width / 2 - source.x,
        dy: bounds.height / 2 - source.y,
        scale: Math.min(bounds.width * 0.7, 400) / (source.rx * 2),
        source,
        target,
      });
    };
    const observer = new ResizeObserver(measure);
    [canvas, panel, wafer, room].forEach((element) =>
      observer.observe(element),
    );
    measure();

    return () => observer.disconnect();
  }, [host]);

  return layout;
};

export const WaferTransfer = ({
  index,
  fromIndex,
  layout,
  progress,
  state,
}: {
  index: number;
  fromIndex: number;
  layout?: Layout;
  progress: number;
  state: PatternState;
}) => {
  const handingOff =
    index === stages.handOff ||
    (index === stages.operator && fromIndex === stages.handOff);

  if (!handingOff || !layout || progress <= 0 || progress >= 1) return null;

  const mix = (a: number, b: number) => a + (b - a) * progress;
  const x = mix(layout.source.x, layout.target.x);
  const y =
    mix(layout.source.y, layout.target.y) - Math.sin(Math.PI * progress) * 20;
  const rx = mix(layout.source.rx, layout.target.rx);
  const ry = mix(layout.source.ry, layout.target.ry);

  return (
    <svg className="fab-wafer-transfer" aria-hidden="true">
      <g
        transform={`translate(${x} ${y}) scale(${rx} ${ry})`}
        opacity={portion(progress, 0, 0.06) * (1 - portion(progress, 0.94, 1))}
      >
        <SmallWafer state={state} />
      </g>
    </svg>
  );
};
