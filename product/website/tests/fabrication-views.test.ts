import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import { InterconnectStack } from "../../../hardware/publishing/sand-to-thought/articles/fabricating-a-transistor/figures/InterconnectStack";
import { patterningCamera } from "../../../hardware/publishing/sand-to-thought/articles/fabricating-a-transistor/figures/PatterningModel";
import { stages } from "../../../hardware/publishing/sand-to-thought/articles/fabricating-a-transistor/figures/process";

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
  expect(levels(render(0.75))).toBeGreaterThan(2);
  expect(levels(render(0.75))).toBeLessThan(9);
  expect(levels(render(1))).toBe(9);
  for (const progress of [0, 0.25, 0.5, 0.75, 1]) {
    const markup = render(progress);
    expect(markup).toContain("Silicon");
    expect(markup).toContain("Transistors remain at the silicon surface");
    expect(markup).not.toMatch(/NaN|Infinity/);
  }
});

it("carries the completed two-transistor structure into the chip before adding more wiring", () => {
  const render = (progress: number) =>
    renderToStaticMarkup(createElement(InterconnectStack, { progress }));
  const bounds = (markup: string) => {
    const inverter = markup.split('data-embedded-inverter="true"')[1];
    const values = [
      ...inverter.matchAll(/d="([MLZ0-9., \-]+)" data-region=/g),
    ].flatMap((match) => match[1].match(/-?\d+(?:\.\d+)?/g)!.map(Number));
    const xs = values.filter((_, i) => i % 2 === 0);
    return Math.max(...xs) - Math.min(...xs);
  };
  const start = render(0);
  const moving = render(0.3);
  const landed = render(0.52);
  const final = render(1);

  expect(bounds(start)).toBeGreaterThan(bounds(moving));
  expect(bounds(moving)).toBeGreaterThan(bounds(landed));
  expect((landed.match(/data-wiring-level=/g) ?? []).length).toBe(2);
  expect((final.match(/data-wiring-level=/g) ?? []).length).toBe(9);
  for (const markup of [start, moving, landed, final]) {
    expect(markup.includes('aria-label="n-doped source"')).toBe(true);
    expect(markup.includes('aria-label="p-doped source"')).toBe(true);
    expect(markup).not.toMatch(/NaN|Infinity/);
  }
});
