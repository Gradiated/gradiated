export type SurfacePoint = [number, number, number];

export const surfaceContours = (
  polygons: SurfacePoint[][],
): SurfacePoint[][] => {
  const points = new Map<string, SurfacePoint>();
  const edges = new Map<string, { from: string; to: string }>();
  const keyFor = (point: SurfacePoint) => {
    const key = point.map((value) => value.toFixed(5)).join(",");
    points.set(key, point);

    return key;
  };

  for (const polygon of polygons) {
    const keys = polygon.map(keyFor);
    for (let i = 0; i < keys.length; i++) {
      const from = keys[i],
        to = keys[(i + 1) % keys.length];
      if (from === to) continue;

      const reverse = `${to}|${from}`;
      if (edges.has(reverse)) edges.delete(reverse);
      else edges.set(`${from}|${to}`, { from, to });
    }
  }

  const outgoing = new Map<string, Set<string>>();
  for (const { from, to } of edges.values()) {
    if (!outgoing.has(from)) outgoing.set(from, new Set());
    outgoing.get(from)!.add(to);
  }

  const contours: SurfacePoint[][] = [];
  while (edges.size) {
    const start = edges.values().next().value!.from;
    const contour: SurfacePoint[] = [];
    let from = start;
    do {
      contour.push(points.get(from)!);
      const to = outgoing.get(from)?.values().next().value;
      if (to === undefined) break;

      outgoing.get(from)!.delete(to);
      edges.delete(`${from}|${to}`);
      from = to;
    } while (from !== start);
    if (contour.length >= 3) contours.push(contour);
  }

  return contours;
};
