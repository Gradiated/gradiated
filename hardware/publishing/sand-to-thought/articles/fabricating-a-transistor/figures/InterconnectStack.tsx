import { useLayoutEffect, useRef, useState } from "react";
import { PatterningModel, patterningCamera } from "./PatterningModel";
import { patternState, portion, stages, visitFor } from "./process";
import type { PatternState } from "./process";
import { materialColours, siliconColours } from "./materials";
import {
  interconnectLevels,
  interconnectSolids,
  inverterPlacement,
} from "./interconnectLayout";

type Point = [number, number, number];

type Transform = Pick<DOMMatrix, "a" | "b" | "c" | "d" | "e" | "f">;
const finishedVisit = visitFor(1, undefined, undefined);
const finishedCamera = patterningCamera(stages.finish, 1, {
  elevation: 0.65,
  section: 1,
});

export const InterconnectStack = ({
  progress,
  state = patternState(stages.finish, finishedVisit),
  camera = finishedCamera,
}: {
  progress: number;
  state?: PatternState;
  camera?: ReturnType<typeof patterningCamera>;
}) => {
  const svg = useRef<SVGSVGElement>(null);
  const [source, setSource] = useState<Transform>();

  useLayoutEffect(() => {
    const detail = svg.current
      ?.closest(".fab-visuals")
      ?.querySelector<SVGSVGElement>(
        ".fab-detail-panel .fab-pattern-model > svg",
      );
    if (!detail || !svg.current) return;

    const measure = () => {
      const destinationMatrix = svg.current?.getScreenCTM();
      const sourceMatrix = detail.getScreenCTM();
      if (!destinationMatrix || !sourceMatrix) return;

      const matrix = destinationMatrix.inverse().multiply(sourceMatrix);
      setSource({
        a: matrix.a,
        b: matrix.b,
        c: matrix.c,
        d: matrix.d,
        e: matrix.e,
        f: matrix.f,
      });
    };
    const observer = new ResizeObserver(measure);
    observer.observe(detail);
    observer.observe(svg.current);
    measure();

    return () => observer.disconnect();
  }, []);
  const project = ([x, y, z]: Point) =>
    [115 + x * 1.65 - y * 0.62, 300 + y * 0.34 - z * 1.35] as const;
  const face = (points: Point[]) =>
    `${points.map((point, i) => `${i ? "L" : "M"}${project(point).join(" ")}`).join(" ")}Z`;
  const box = (
    key: string,
    x: number,
    y: number,
    z: number,
    width: number,
    depth: number,
    height: number,
    colours: readonly string[],
  ) => (
    <g key={key}>
      <path
        d={face([
          [x + width, y, z],
          [x + width, y + depth, z],
          [x + width, y + depth, z + height],
          [x + width, y, z + height],
        ])}
        fill={colours[1]}
      />
      <path
        d={face([
          [x, y + depth, z],
          [x + width, y + depth, z],
          [x + width, y + depth, z + height],
          [x, y + depth, z + height],
        ])}
        fill={colours[2]}
      />
      <path
        d={face([
          [x, y, z + height],
          [x + width, y, z + height],
          [x + width, y + depth, z + height],
          [x, y + depth, z + height],
        ])}
        fill={colours[0]}
      />
    </g>
  );
  const zoom = 1.35 - portion(progress, 0.25, 0.72) * 0.35;
  const arrival = portion(progress, 0.12, 0.52);
  const context = portion(progress, 0.25, 0.52);
  const inverterProject = (point: Point): [number, number] => {
    const [x, y] = camera.project(point);
    const start: [number, number] = source
      ? [
          source.a * x + source.c * y + source.e,
          source.b * x + source.d * y + source.f,
        ]
      : [240 + x * 0.6, 210 + y * 0.6];
    const destination = project([
      inverterPlacement.x + point[0] * inverterPlacement.scale,
      inverterPlacement.y + point[1] * inverterPlacement.scale,
      point[2] * inverterPlacement.scale,
    ]);
    const end = [
      320 + (destination[0] - 320) * zoom,
      240 + (destination[1] - 240) * zoom,
    ];

    return [
      start[0] + (end[0] - start[0]) * arrival,
      start[1] + (end[1] - start[1]) * arrival,
    ];
  };
  const layerGrowth = (layer: number) =>
    layer < 2
      ? 1
      : portion(
          progress,
          0.52 + (layer - 2) * 0.055,
          0.64 + (layer - 2) * 0.055,
        );
  const gate = materialColours.gate;
  const metal = materialColours.metal;
  const front = project([0, 100, -10]);
  const wiringOpacity = portion(progress, 0.42, 0.52);

  return (
    <svg
      ref={svg}
      className="fab-interconnect-stack"
      viewBox="10 55 550 340"
      role="img"
      aria-label="The finished NOT gate moves into a simplified cutaway of a larger chip region. Transistors remain at the silicon surface while nine levels of separate metal routes build up above them. Vias connect selected wires on adjacent levels. Insulation separates the remaining crossings and is shown faintly to reveal the wires."
    >
      <g
        opacity={context}
        transform={`translate(320 240) scale(${zoom}) translate(-320 -240)`}
      >
        {box("silicon", 0, 0, -24, 240, 100, 24, [
          siliconColours.top,
          siliconColours.side,
          siliconColours.front,
        ])}
        {[8, 35, 62, 143, 170, 197, 224].map((x, i) => (
          <g key={x}>
            {i % 2
              ? box(`well-${i}`, x - 2, 84, -7, 21, 16, 7, materialColours.well)
              : null}
            {box(
              `source-${i}`,
              x,
              89,
              -1,
              5,
              11,
              1,
              i % 2 ? materialColours.p : materialColours.n,
            )}
            {box(
              `drain-${i}`,
              x + 10,
              89,
              -1,
              5,
              11,
              1,
              i % 2 ? materialColours.p : materialColours.n,
            )}
            {box(`gate-${i}`, x + 6, 86, 0.4, 3, 14, 1.2, gate)}
            {box(`contact-${i}`, x + 10, 95, 0, 3, 3, 5.6, metal)}
            {box(`local-${i}`, x + 9, 94, 5.6, 5, 5, 1.2, metal)}
          </g>
        ))}
        <text
          x={front[0] + 12}
          y={front[1] + 5}
          fill={siliconColours.label}
          fontSize="12"
        >
          Silicon
        </text>
      </g>
      <PatterningModel
        embedded
        index={stages.finish}
        fromIndex={stages.finish - 1}
        progress={1}
        state={state}
        visit={finishedVisit}
        input={0}
        view={{ ...camera, project: inverterProject }}
      />
      <g
        opacity={context * wiringOpacity}
        transform={`translate(320 240) scale(${zoom}) translate(-320 -240)`}
      >
        {interconnectLevels.map(({ z }, layer) => {
          const growth = layerGrowth(layer);
          if (!growth) return null;

          const lower = interconnectLevels[layer - 1];
          const base = lower ? lower.z + lower.height : 0;

          return (
            <g key={layer} data-wiring-level={layer + 1}>
              <g opacity={0.07 * growth}>
                {box(
                  `oxide-${layer}`,
                  0,
                  0,
                  base,
                  240,
                  100,
                  z - base,
                  materialColours.insulator,
                )}
              </g>
              {interconnectSolids
                .filter((solid) => solid.layer === layer)
                .sort(
                  (a, b) =>
                    Number(a.kind === "wire") - Number(b.kind === "wire") ||
                    a.y - b.y,
                )
                .map((solid) => {
                  const amount =
                    solid.kind === "via"
                      ? portion(growth, 0, 0.45)
                      : portion(growth, 0.35, 1);
                  if (!amount) return null;

                  return (
                    <g
                      key={solid.id}
                      opacity={amount}
                      data-interconnect={solid.kind}
                      data-net={solid.net}
                    >
                      {box(
                        solid.id,
                        solid.x,
                        solid.y,
                        solid.z,
                        solid.width,
                        solid.depth,
                        solid.height * (solid.kind === "via" ? amount : 1),
                        metal,
                      )}
                    </g>
                  );
                })}
            </g>
          );
        })}
      </g>
    </svg>
  );
};
