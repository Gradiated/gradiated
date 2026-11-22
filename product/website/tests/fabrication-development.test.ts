import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import { materialColours } from "../../../hardware/publishing/sand-to-thought/articles/fabricating-a-transistor/figures/materials";
import {
  PatterningModel,
  patterningCamera,
} from "../../../hardware/publishing/sand-to-thought/articles/fabricating-a-transistor/figures/PatterningModel";
import {
  exposureRegions,
  materialSurfaceHeight,
  maskOpens,
  resistThickness,
  patternState,
  patternSurfaceHeight,
  visitFor,
} from "../../../hardware/publishing/sand-to-thought/articles/fabricating-a-transistor/figures/process";
import {
  maskCycles,
  steps,
} from "../../../hardware/publishing/sand-to-thought/articles/fabricating-a-transistor/figures/sequence";

type Point = [number, number];

const contains = (path: string, [x, y]: Point) => {
  let winding = 0;
  for (const contour of path.split("Z")) {
    const values = contour.match(/-?\d+(?:\.\d+)?/g)?.map(Number) ?? [];
    const points: Point[] = [];
    for (let i = 0; i < values.length; i += 2)
      points.push([values[i], values[i + 1]]);
    for (let i = 0; i < points.length; i++) {
      const [ax, ay] = points[i];
      const [bx, by] = points[(i + 1) % points.length];
      const side = (bx - ax) * (y - ay) - (x - ax) * (by - ay);
      if (ay <= y && by > y && side > 0) winding++;
      if (ay > y && by <= y && side < 0) winding--;
    }
  }

  return winding !== 0;
};

it.each(["contact", "via"] as const)(
  "keeps recessed %s opening walls behind the intact photoresist surface",
  (mask) => {
    const index = maskCycles.find(({ id }) => id === mask)!.develop;
    const view = patterningCamera(index, 1, { elevation: 0.65, section: 1 });
    for (const progress of [0.25, 0.6, 1]) {
      const visit = {
        ...visitFor(1, steps[index].machine, undefined),
        process: progress,
      };
      const state = patternState(index, visit);
      const markup = renderToStaticMarkup(
        createElement(PatterningModel, {
          index,
          progress: 1,
          fromIndex: index - 1,
          view,
          visit,
          state,
          input: 0,
        }),
      );
      const faces = [...markup.matchAll(/<path\b[^>]*>/g)]
        .map(([tag]) =>
          Object.fromEntries(
            [...tag.matchAll(/([\w-]+)="([^"]*)"/g)].map(([, key, value]) => [
              key,
              value,
            ]),
          ),
        )
        .filter(
          (face) => face["aria-label"] === "Photoresist · temporary mask",
        );
      for (const [x0, x1, , y1] of exposureRegions(mask, view.ymax)) {
        if (y1 + 0.25 >= view.ymax) continue;

        const x = (x0 + x1) / 2;
        const y = y1 + 0.25;
        const point = view.project([x, y, patternSurfaceHeight(state, x, y)]);
        const visible = faces.filter((face) => contains(face.d, point)).pop();
        expect(visible?.fill).toBe(materialColours.resist[0]);
      }
    }
  },
);

it.each(["n", "p"] as const)(
  "erodes the %s-implant photoresist from a level top instead of compressing it around the gate",
  (mask) => {
    const cycle = maskCycles.find(({ id }) => id === mask)!;
    const points = [16, 26, 36, 64, 74, 84]
      .filter((x) => !maskOpens(mask, x, 23))
      .map((x) => [x, 23] as const);
    let previous = points.map(() => Infinity);

    for (const progress of [0, 0.25, 0.5, 0.65, 0.9, 1]) {
      const state = patternState(cycle.strip, {
        ...visitFor(1, "strip", undefined),
        process: progress,
      });
      const thicknesses = points.map(([x, y]) =>
        resistThickness(state, mask, x, y),
      );
      const tops = points.flatMap(([x, y], i) =>
        thicknesses[i] > 0.001
          ? [materialSurfaceHeight(state, x, y) + thicknesses[i]]
          : [],
      );

      tops.forEach((top) => expect(top).toBeCloseTo(tops[0], 8));
      thicknesses.forEach((thickness, i) =>
        expect(thickness).toBeLessThanOrEqual(previous[i]),
      );
      if (progress === 0.65) {
        expect(thicknesses[1]).toBe(0);
        expect(thicknesses[0]).toBeGreaterThan(0);
      }
      if (progress === 1) expect(thicknesses).toEqual([0, 0, 0]);
      expect(state.implantN).toBe(1);
      expect(state.implantP).toBe(mask === "p" ? 1 : 0);
      previous = thicknesses;
    }
  },
);
