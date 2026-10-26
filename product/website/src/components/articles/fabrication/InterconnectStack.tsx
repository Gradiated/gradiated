import { materialColours, siliconColours } from "./materials";
import { portion } from "./process";

type Point = [number, number, number];

export const InterconnectStack = ({ progress }: { progress: number }) => {
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
          [x, y, z],
          [x, y + depth, z],
          [x, y + depth, z + height],
          [x, y, z + height],
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
  const zoom = 1.35 - portion(progress, 0.02, 0.72) * 0.35;
  const layerCount = 9;
  const layerGrowth = (layer: number) =>
    layer < 2
      ? 1
      : portion(progress, 0.12 + (layer - 2) * 0.1, 0.22 + (layer - 2) * 0.1);
  const thickness = (layer: number) => (layer < 5 ? 3 : 6);
  const gate = materialColours.gate;
  const metal = materialColours.metal;
  const front = project([0, 100, -10]);

  return (
    <svg
      className="fab-interconnect-stack"
      viewBox="10 55 550 340"
      role="img"
      aria-label="A simplified cutaway of a larger chip region. Transistors remain at the silicon surface while nine levels of metal wiring and connecting vias build up above them. Insulation is shown faintly to reveal the wires."
    >
      <g transform={`translate(320 240) scale(${zoom}) translate(-320 -240)`}>
        {box("silicon", 0, 0, -24, 240, 100, 24, [
          siliconColours.top,
          siliconColours.side,
          siliconColours.front,
        ])}
        {[8, 35, 62, 89, 116, 143, 170, 197, 224].map((x, i) => (
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
              2,
              i % 2 ? materialColours.p : materialColours.n,
            )}
            {box(
              `drain-${i}`,
              x + 10,
              89,
              -1,
              5,
              11,
              2,
              i % 2 ? materialColours.p : materialColours.n,
            )}
            {box(`gate-${i}`, x + 6, 86, 1, 3, 14, 3, gate)}
            {box(`contact-${i}`, x + 10, 95, 1, 3, 3, 8, metal)}
          </g>
        ))}
        {Array.from({ length: layerCount }, (_, layer) => {
          const growth = layerGrowth(layer);
          if (!growth) return null;

          const z = 9 + layer * 17;
          const size = layer < 5 ? 4 : 7;
          const height = thickness(layer);
          const viaStart = layer
            ? 9 + (layer - 1) * 17 + thickness(layer - 1)
            : 0;
          const wire = portion(growth, 0.35, 1);
          return (
            <g key={layer} data-wiring-level={layer + 1}>
              <g opacity={0.13 * growth}>
                {box(
                  `oxide-${layer}`,
                  0,
                  0,
                  layer ? z - 17 : 0,
                  240,
                  100,
                  layer ? 17 : 9,
                  materialColours.insulator,
                )}
              </g>
              {(layer
                ? [
                    [20, 12],
                    [100, 60],
                    [220, 84],
                  ]
                : []
              ).map(([x, y], i) =>
                box(
                  `via-${layer}-${i}`,
                  x,
                  y,
                  viaStart,
                  3,
                  3,
                  (z - viaStart) * portion(growth, 0, 0.45),
                  metal,
                ),
              )}
              {wire > 0
                ? layer % 2 === 0
                  ? [12, 36, 60, 84, ...(layer === 0 ? [95] : [])].map((y, i) =>
                      box(
                        `wire-${layer}-${i}`,
                        0,
                        y,
                        z,
                        240 * wire,
                        size,
                        height * wire,
                        metal,
                      ),
                    )
                  : [20, 60, 100, 140, 180, 220].map((x, i) =>
                      box(
                        `wire-${layer}-${i}`,
                        x,
                        0,
                        z,
                        size,
                        100 * wire,
                        height * wire,
                        metal,
                      ),
                    )
                : null}
            </g>
          );
        })}
        <text
          x={front[0] + 12}
          y={front[1] + 5}
          fill={siliconColours.label}
          fontSize="12"
        >
          Silicon
        </text>
      </g>
    </svg>
  );
};
