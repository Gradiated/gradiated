import { expect, it } from "vitest";
import {
  contactInsulatorHeight,
  deviceSurfaceHeight,
  materialSurfaceHeight,
  patternState,
  stages,
  upperInsulatorHeight,
} from "../../../hardware/publishing/sand-to-thought/articles/fabricating-a-transistor/figures/process";
import { scenes } from "../../../hardware/publishing/sand-to-thought/articles/fabricating-a-transistor/figures/model";
import {
  maskCycles,
  steps,
} from "../../../hardware/publishing/sand-to-thought/articles/fabricating-a-transistor/figures/sequence";

const stateAt = (index: number, process: number) =>
  patternState(index, {
    machine: steps[index].machine,
    progress: 0.6,
    process,
    loaded: 1,
    working: true,
  });
const sites = [0, 16, 26, 36, 50, 64, 74, 84, 100].flatMap((x) =>
  [0, 8, 23, 34].map((y) => [x, y] as const),
);

it("polishes the deposited device insulation before coating the contact mask", () => {
  const cycle = maskCycles.find((cycle) => cycle.id === "contact")!;
  expect(stages.contactPolish).toBe(stages.contactInsulation + 1);
  expect(cycle.coat).toBe(stages.contactPolish + 1);
  expect(steps[stages.contactPolish].machine).toBe("polish");
  expect(scenes.map((scene) => scene.key)).toEqual(
    steps.map((step) => step.key),
  );
  expect(scenes[stages.contactPolish].html).toContain(
    "ref-dielectric-polishing",
  );
});

it("deposits oxide over the device contours, then only removes it until the surface is flat", () => {
  const deposited = stateAt(stages.contactInsulation, 1);
  const before = sites.map(([x, y]) => materialSurfaceHeight(deposited, x, y));
  expect(Math.max(...before) - Math.min(...before)).toBeGreaterThan(5);
  for (const [x, y] of sites) {
    expect(
      materialSurfaceHeight(deposited, x, y) -
        deviceSurfaceHeight(x, y, deposited),
    ).toBeCloseTo(20);
    let previous = materialSurfaceHeight(deposited, x, y);
    for (let sample = 0; sample <= 10; sample++) {
      const state = stateAt(stages.contactPolish, sample / 10);
      const height = materialSurfaceHeight(state, x, y);
      expect(height).toBeLessThanOrEqual(previous);
      expect(height).toBeCloseTo(contactInsulatorHeight(x, y, state));
      expect(height).toBeGreaterThan(deviceSurfaceHeight(x, y, state));
      expect(state.cover).toBe(1);
      expect(state.contacts).toBe(0);
      expect(state.metal).toBe(0);
      previous = height;
    }
    expect(previous).toBeCloseTo(14);
    expect(
      materialSurfaceHeight(stateAt(stages.contactPolish + 1, 0), x, y),
    ).toBeCloseTo(previous);
  }
});

it("keeps the later oxide polishing subtractive and the finished inverter unchanged", () => {
  for (const [x, y] of sites) {
    let previous = upperInsulatorHeight(x, y, stateAt(stages.polish, 0));
    for (let sample = 1; sample <= 10; sample++) {
      const height = upperInsulatorHeight(
        x,
        y,
        stateAt(stages.polish, sample / 10),
      );
      expect(height).toBeLessThanOrEqual(previous);
      previous = height;
    }
    expect(previous).toBeCloseTo(25);
    const opening = stateAt(0, 1);
    const inverter = stateAt(stages.inverter, 1);
    expect(opening.contactPolish).toBe(1);
    expect(inverter.contactPolish).toBe(1);
    expect(contactInsulatorHeight(x, y, opening)).toBe(14);
    expect(contactInsulatorHeight(x, y, inverter)).toBe(14);
  }
});
