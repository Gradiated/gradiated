import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import { InterconnectStack } from "../src/components/articles/fabrication/InterconnectStack";
import { patterningCamera } from "../src/components/articles/fabrication/PatterningModel";
import { stages } from "../src/components/articles/fabrication/process";

it("reveals the via's interior at the cut face, then smoothly restores the wider view", () => {
  const original = { elevation: 0.65, section: 1, cutY: 34 };
  const entering = patterningCamera(stages.via, 0.14, original);
  expect(entering.ymax).toBeGreaterThan(25);
  expect(entering.ymax).toBeLessThan(34);
  const cut = patterningCamera(stages.via, 1, original);
  expect(cut.ymax).toBe(25);
  expect(patterningCamera(stages.upperMetal, 0, cut).ymax).toBe(25);
  expect(patterningCamera(stages.upperMetal, 1, cut).ymax).toBe(34);
});

it("extends the existing two wiring levels progressively while retaining the silicon and devices", () => {
  const render = (progress: number) =>
    renderToStaticMarkup(createElement(InterconnectStack, { progress }));
  const levels = (markup: string) =>
    [...markup.matchAll(/data-wiring-level=/g)].length;
  expect(levels(render(0))).toBe(2);
  expect(levels(render(0.5))).toBeGreaterThan(2);
  expect(levels(render(0.5))).toBeLessThan(9);
  expect(levels(render(1))).toBe(9);
  for (const progress of [0, 0.25, 0.5, 0.75, 1]) {
    const markup = render(progress);
    expect(markup).toContain("Silicon");
    expect(markup).toContain("Transistors remain at the silicon surface");
    expect(markup).not.toMatch(/NaN|Infinity/);
  }
});
