import { useId } from "react";
import { exposureColours } from "./materials";
import type { Rectangle } from "./process";

type Point = [number, number, number];
type ScreenPoint = [number, number];

const outline = (points: ScreenPoint[]) => {
  const sorted = [...points].sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const cross = (a: ScreenPoint, b: ScreenPoint, c: ScreenPoint) =>
    (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
  const half = (ordered: ScreenPoint[]) => {
    const result: ScreenPoint[] = [];
    for (const point of ordered) {
      while (
        result.length > 1 &&
        cross(result[result.length - 2], result[result.length - 1], point) <= 0
      )
        result.pop();
      result.push(point);
    }

    return result.slice(0, -1);
  };

  return (
    [...half(sorted), ...half([...sorted].reverse())]
      .map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(2)} ${y.toFixed(2)}`)
      .join(" ") + "Z"
  );
};

export const ExposureBeams = ({
  regions,
  surfaceHeight,
  project,
  height: beamHeight = 42,
}: {
  regions: Rectangle[];
  surfaceHeight: (x: number, y: number) => number;
  project: (point: Point) => ScreenPoint;
  height?: number;
}) => {
  const id = useId();

  return (
    <g aria-hidden="true" pointerEvents="none">
      <defs>
        <linearGradient id={`${id}-light`} x1="0" y1="0" x2="0" y2="1">
          <stop
            offset="0"
            stopColor={exposureColours.beamTop}
            stopOpacity=".22"
          />
          <stop
            offset="1"
            stopColor={exposureColours.beamBase}
            stopOpacity=".6"
          />
        </linearGradient>
      </defs>
      {regions.map(([x0, x1, y0, y1], i) => {
        const corners = [
          [x0, y0],
          [x1, y0],
          [x1, y1],
          [x0, y1],
        ];
        const height = Math.max(
          ...corners.map(([x, y]) => surfaceHeight(x, y)),
        );
        const marginX = Math.min(0.6, (x1 - x0) * 0.035);
        const marginY = Math.min(0.6, (y1 - y0) * 0.035);
        const base = corners.map(([x, y]) =>
          project([x, y, surfaceHeight(x, y)]),
        );
        const top = corners.map(([x, y]) =>
          project([
            x + (x === x0 ? -marginX : marginX),
            y + (y === y0 ? -marginY : marginY),
            height + beamHeight,
          ]),
        );

        return (
          <path
            key={i}
            data-exposure-region={`${x0} ${x1} ${y0} ${y1}`}
            d={outline([...base, ...top])}
            fill={`url(#${id}-light)`}
            stroke="color-mix(in srgb, var(--color-aegean-400) 35%, var(--color-light-000))"
            strokeWidth=".45"
            strokeOpacity=".6"
          />
        );
      })}
    </g>
  );
};
