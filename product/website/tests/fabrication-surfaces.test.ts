import { expect, it } from "vitest";
import { surfaceContours } from "../../../hardware/publishing/sand-to-thought/articles/fabricating-a-transistor/figures/surfaces";
import type { SurfacePoint } from "../../../hardware/publishing/sand-to-thought/articles/fabricating-a-transistor/figures/surfaces";

const square = (x: number, y: number): SurfacePoint[] => [
  [x, y, 0],
  [x + 1, y, 0],
  [x + 1, y + 1, 0],
  [x, y + 1, 0],
];
const signedArea = (points: SurfacePoint[]) =>
  points.reduce((area, [x, y], i) => {
    const [nextX, nextY] = points[(i + 1) % points.length];

    return area + (x * nextY - nextX * y) / 2;
  }, 0);

it("removes shared strip edges without losing the surface outline", () => {
  const contours = surfaceContours([square(0, 0), square(1, 0), square(2, 0)]);
  expect(contours).toHaveLength(1);
  expect(contours[0]).toHaveLength(8);
  expect(signedArea(contours[0])).toBe(3);
});

it("keeps real holes with opposite winding rather than filling them", () => {
  const ring = Array.from({ length: 9 }, (_, i) => [i % 3, Math.floor(i / 3)])
    .filter(([x, y]) => x !== 1 || y !== 1)
    .map(([x, y]) => square(x, y));
  const contours = surfaceContours(ring);
  expect(contours).toHaveLength(2);
  const areas = contours.map(signedArea).sort((a, b) => a - b);
  expect(areas).toEqual([-1, 9]);
});

it("preserves disconnected regions and joining on a sloped surface", () => {
  expect(surfaceContours([square(0, 0), square(4, 0)])).toHaveLength(2);
  const slope = [square(0, 0), square(1, 0)].map((polygon) =>
    polygon.map(([x, y]) => [x, y, x * 0.4] as SurfacePoint),
  );
  const contours = surfaceContours(slope);
  expect(contours).toHaveLength(1);
  expect(contours[0].every(([x, , z]) => z === x * 0.4)).toBe(true);
});
