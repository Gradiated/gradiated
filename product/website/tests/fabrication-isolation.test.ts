import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import {
  PatterningModel,
  patterningCamera,
} from "../src/components/articles/fabrication/PatterningModel";
import { scenes } from "../src/components/articles/fabrication/model";
import {
  activeSilicon,
  blendPattern,
  fieldOxideGrowth,
  insulationThickness,
  maskOpens,
  materialSurfaceHeight,
  nitrideThickness,
  patternState,
  resistState,
  siliconSurfaceHeight,
  stages,
  transitionPattern,
  visitFor,
} from "../src/components/articles/fabrication/process";
import {
  maskCycles,
  steps,
} from "../src/components/articles/fabrication/sequence";

const stateAt = (index: number, process = 1) =>
  patternState(index, {
    ...visitFor(1, steps[index].machine, undefined),
    process,
  });
const oxideTop = (x: number, state: ReturnType<typeof stateAt>) =>
  siliconSurfaceHeight(x, 23, state) + insulationThickness(x, 23, state);

it("keeps the scene manifest aligned and removes photoresist before selective oxidation", () => {
  const cycle = maskCycles.find(({ id }) => id === "isolation")!;
  expect(scenes.map(({ key }) => key)).toEqual(steps.map(({ key }) => key));
  expect(steps[stages.isolation].machine).toBe("deposit");
  expect(cycle.strip).toBe(stages.fieldOxide - 1);
  expect(stages.nitrideStrip).toBe(stages.fieldOxide + 1);
  expect(stages.padOxideStrip).toBe(stages.nitrideStrip + 1);
  expect(stages.gateOxide).toBe(stages.padOxideStrip + 1);
  expect(
    steps.slice(0, stages.inverter).filter(({ machine }) => machine),
  ).toHaveLength(47);
  const state = stateAt(stages.fieldOxide, 0);
  expect(resistState(state, "isolation").amount).toBe(0);
  expect(nitrideThickness(26, state)).toBeGreaterThan(0);
  expect(nitrideThickness(50, state)).toBe(0);
});

it("opens positive photoresist around the sites and retains nitride over both devices", () => {
  const state = stateAt(stages.prepareIsolation);
  for (const x of [0, 16, 26, 36, 50, 64, 74, 84, 100]) {
    expect(maskOpens("isolation", x, 23)).toBe(!activeSilicon(x));
    expect(nitrideThickness(x, state) > 0).toBe(activeSilicon(x));
    expect(insulationThickness(x, 23, state)).toBe(5);
  }
});

it("grows field oxide above and into silicon while protecting the channel sites", () => {
  const start = stateAt(stages.fieldOxide, 0);
  let previousBottom = siliconSurfaceHeight(50, 23, start);
  let previousTop = oxideTop(50, start);
  for (let sample = 1; sample <= 20; sample++) {
    const state = stateAt(stages.fieldOxide, sample / 20);
    const bottom = siliconSurfaceHeight(50, 23, state);
    const top = oxideTop(50, state);
    const growth = fieldOxideGrowth(50, state);
    expect(bottom).toBeLessThan(previousBottom);
    expect(top).toBeGreaterThan(previousTop);
    expect(siliconSurfaceHeight(50, 23, start) - bottom).toBeCloseTo(
      0.44 * growth,
    );
    for (const x of [26, 74]) {
      expect(siliconSurfaceHeight(x, 23, state)).toBe(
        siliconSurfaceHeight(x, 23, start),
      );
      expect(insulationThickness(x, 23, state)).toBe(
        insulationThickness(x, 23, start),
      );
    }
    previousBottom = bottom;
    previousTop = top;
  }
  const final = stateAt(stages.fieldOxide);
  expect(fieldOxideGrowth(40.5, final)).toBeGreaterThan(
    fieldOxideGrowth(39, final),
  );
  expect(fieldOxideGrowth(39, final)).toBeGreaterThan(
    fieldOxideGrowth(38, final),
  );
  expect(fieldOxideGrowth(38, final)).toBeGreaterThan(
    fieldOxideGrowth(37, final),
  );
  expect(fieldOxideGrowth(61, final)).toBeCloseTo(fieldOxideGrowth(39, final));
});

it("removes nitride and then thin oxide without restoring consumed silicon", () => {
  const grown = stateAt(stages.fieldOxide);
  for (let sample = 0; sample <= 20; sample++) {
    const removedNitride = stateAt(stages.nitrideStrip, sample / 20);
    const removedPad = stateAt(stages.padOxideStrip, sample / 20);
    for (const x of [16, 26, 39, 50, 61, 74, 84]) {
      expect(siliconSurfaceHeight(x, 23, removedNitride)).toBe(
        siliconSurfaceHeight(x, 23, grown),
      );
      expect(siliconSurfaceHeight(x, 23, removedPad)).toBe(
        siliconSurfaceHeight(x, 23, grown),
      );
      expect(insulationThickness(x, 23, removedNitride)).toBe(
        insulationThickness(x, 23, grown),
      );
      expect(insulationThickness(x, 23, removedPad)).toBeLessThanOrEqual(
        insulationThickness(x, 23, grown),
      );
    }
    expect(nitrideThickness(26, removedPad)).toBe(0);
  }
  const cleared = stateAt(stages.padOxideStrip);
  expect(insulationThickness(26, 23, cleared)).toBe(0);
  expect(insulationThickness(74, 23, cleared)).toBe(0);
  expect(insulationThickness(50, 23, cleared)).toBeGreaterThan(5);
  const fresh = stateAt(stages.gateOxide);
  expect(insulationThickness(26, 23, fresh)).toBeCloseTo(1.8);
  expect(insulationThickness(74, 23, fresh)).toBeCloseTo(1.8);
});

it("preserves material geometry between adjacent visits and keeps reverse transitions continuous", () => {
  for (let index = stages.isolation; index <= stages.poly; index++) {
    const from = stateAt(index - 1);
    const to = stateAt(index, 0);
    const mixed = blendPattern(from, to, 0.5);
    for (const x of [0, 3, 16, 26, 39, 50, 61, 74, 97, 100]) {
      expect(materialSurfaceHeight(from, x, 23)).toBeCloseTo(
        materialSurfaceHeight(to, x, 23),
      );
      expect(materialSurfaceHeight(mixed, x, 23)).toBeCloseTo(
        materialSurfaceHeight(from, x, 23),
      );
    }
    expect(blendPattern(to, from, 0)).toEqual(to);
    expect(blendPattern(to, from, 1)).toEqual(from);
  }
});

it("renders the full isolation and gate handoff with finite geometry and no residual nitride in the inverter", () => {
  for (const index of [
    stages.isolation,
    stages.prepareIsolation,
    stages.fieldOxide,
    stages.nitrideStrip,
    stages.padOxideStrip,
    stages.gateOxide,
    stages.patternGate,
    stages.inverter,
  ]) {
    for (const process of [0, 0.5, 1]) {
      const state = stateAt(index, process);
      const markup = renderToStaticMarkup(
        createElement(PatterningModel, {
          index,
          progress: 1,
          fromIndex: index - 1,
          view: patterningCamera(index, 1, { elevation: 0.55, section: 1 }),
          visit: { ...visitFor(1, steps[index].machine, undefined), process },
          state,
          input: 0,
        }),
      );
      expect(markup).not.toMatch(/NaN|Infinity/);
      if (index === stages.fieldOxide)
        expect(markup).toContain(
          "Silicon nitride · temporary oxidation barrier",
        );
      if (index === stages.inverter) {
        expect(markup).not.toContain(
          "Silicon nitride · temporary oxidation barrier",
        );
        expect(markup).toContain("n-doped source");
        expect(markup).toContain("p-doped source");
      }
    }
  }
});

it("keeps fresh gate oxide and the deposited gate film continuous across the isolation slopes", () => {
  for (const index of [stages.gateOxide, stages.poly]) {
    const state = stateAt(index);
    for (const edge of [2, 40, 60, 98]) {
      expect(
        Math.abs(
          materialSurfaceHeight(state, edge - 0.0001, 23) -
            materialSurfaceHeight(state, edge + 0.0001, 23),
        ),
      ).toBeLessThan(0.01);
    }
  }
});

it("fades the clearing thin oxide independently of the surviving field oxide", () => {
  const index = stages.padOxideStrip;
  const opacities = (remaining: number, label: string) => {
    const state = { ...stateAt(index), padOxideStrip: 1 - remaining };
    const markup = renderToStaticMarkup(
      createElement(PatterningModel, {
        index,
        progress: 1,
        fromIndex: index - 1,
        view: patterningCamera(index, 1, { elevation: 0.55, section: 1 }),
        visit: visitFor(1, steps[index].machine, undefined),
        state,
        input: 0,
      }),
    );

    return [...markup.matchAll(/<path\b[^>]*>/g)]
      .map(([tag]) => tag)
      .filter((tag) => tag.includes(`aria-label="${label}"`))
      .map((tag) => Number(tag.match(/\bopacity="([^"]+)"/)![1]));
  };
  let previous = 1;
  for (const remaining of [0.16, 0.12, 0.08, 0.04, 0.01]) {
    const thin = opacities(remaining, "Thin oxide · insulator");
    expect(thin.length).toBeGreaterThan(0);
    expect(Math.max(...thin)).toBeLessThanOrEqual(previous);
    previous = Math.max(...thin);
    expect(
      opacities(remaining, "Field oxide · insulator").every((v) => v === 1),
    ).toBe(true);
  }
  expect(previous).toBeLessThan(0.02);
  expect(opacities(0, "Thin oxide · insulator")).toHaveLength(0);
});

it("jumps directly to the destination materials without reviving old photoresist masks", () => {
  for (const [fromIndex, toIndex] of [
    [stages.inverter, stages.padOxideStrip],
    [stages.padOxideStrip, stages.inverter],
    [stages.patternGate, stages.fieldOxide],
  ]) {
    const from = stateAt(fromIndex);
    const to = stateAt(toIndex, 0);
    for (const progress of [0, 0.1, 0.5, 1]) {
      const state = transitionPattern(from, to, progress, fromIndex, toIndex);
      expect(state).toEqual(to);
      expect(
        maskCycles.filter(({ id }) => resistState(state, id).amount > 0.001)
          .length,
      ).toBeLessThanOrEqual(1);
    }
  }
  const from = stateAt(stages.fieldOxide, 0.5);
  const to = stateAt(stages.nitrideStrip, 0);
  expect(
    transitionPattern(from, to, 0.5, stages.fieldOxide, stages.nitrideStrip),
  ).toEqual(blendPattern(from, to, 0.5));
  expect(
    transitionPattern(to, from, 0.5, stages.nitrideStrip, stages.fieldOxide),
  ).toEqual(blendPattern(to, from, 0.5));
});
