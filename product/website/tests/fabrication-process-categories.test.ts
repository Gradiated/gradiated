import { expect, it } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { FabricationProcessIndicator } from "../../../hardware/publishing/sand-to-thought/articles/fabricating-a-transistor/figures/FabricationProcessIndicator";
import { processCategoryFor } from "../../../hardware/publishing/sand-to-thought/articles/fabricating-a-transistor/figures/processCategories";
import { steps } from "../../../hardware/publishing/sand-to-thought/articles/fabricating-a-transistor/figures/sequence";

it.each([
  ["coat", "pattern"],
  ["expose", "pattern"],
  ["develop", "pattern"],
  ["strip", "remove"],
  ["contact-planarise", "remove"],
  ["pattern-gate", "remove"],
  ["poly", "add"],
  ["field-oxide", "add"],
  ["implant", "modify"],
  ["well-anneal", "modify"],
  ["destination", undefined],
  ["finish", undefined],
])("classifies %s by the operation being demonstrated", (key, expected) => {
  const step = steps.find((candidate) => candidate.key === key);
  expect(step).toBeDefined();
  expect(processCategoryFor(step!)).toBe(expected);
});

it("does not imply that the animation demonstrates cleaning or inspection", () => {
  const shown = new Set(steps.map(processCategoryFor));

  expect(shown.has("clean")).toBe(false);
  expect(shown.has("inspect")).toBe(false);
});

it("highlights one category for an operation and none for an overview", () => {
  const oxide = steps.find((step) => step.key === "oxide")!;
  const operation = renderToStaticMarkup(
    createElement(FabricationProcessIndicator, { step: oxide }),
  );
  const overview = renderToStaticMarkup(
    createElement(FabricationProcessIndicator, { step: steps[0] }),
  );

  expect(operation.match(/data-active="true"/g)).toHaveLength(1);
  expect(operation).toContain('aria-label="Adding material"');
  expect(overview).not.toContain('data-active="true"');
  expect(overview).toContain("Overview");
});
