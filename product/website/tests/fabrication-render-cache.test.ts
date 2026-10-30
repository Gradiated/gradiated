import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it, vi } from "vitest";
import {
  PatterningModel,
  patterningCamera,
} from "../src/components/articles/fabrication/PatterningModel";
import {
  patternState,
  visitFor,
} from "../src/components/articles/fabrication/process";
import { steps } from "../src/components/articles/fabrication/sequence";

// Retain the component's refs across server renders to exercise its frame cache.
const retained = vi.hoisted(() => ({
  enabled: false,
  cursor: 0,
  refs: [] as { current: unknown }[],
}));
vi.mock("react", async (importOriginal) => {
  const react = await importOriginal<typeof import("react")>();

  return {
    ...react,
    useRef: (initial: unknown) => {
      if (!retained.enabled) return react.useRef(initial);

      const slot = retained.cursor++;

      return (retained.refs[slot] ??= { current: initial });
    },
  };
});

it.each(steps.map((step, index) => ({ key: step.key, index })))(
  "keeps cached geometry identical through processing, camera changes and reverse jumps at $key",
  ({ index: destination }) => {
    retained.refs = [];
    for (const index of [
      destination,
      steps.length - destination - 1,
      destination,
    ]) {
      for (const process of [0, 0.25, 0.6, 1]) {
        const visit = {
          ...visitFor(0.6, steps[index].machine, undefined),
          process,
        };
        const props = {
          index,
          fromIndex: index - 1,
          progress: 0.6,
          view: patterningCamera(index, process, {
            elevation: 1.05,
            section: 0,
          }),
          visit,
          state: patternState(index, visit),
          input: 0,
        };
        retained.enabled = true;
        retained.cursor = 0;
        const cached = renderToStaticMarkup(
          createElement(PatterningModel, props),
        );
        retained.enabled = false;
        const fresh = renderToStaticMarkup(
          createElement(PatterningModel, props),
        );
        expect(cached, `${steps[index].key} at ${process}`).toBe(fresh);
      }
    }
  },
);
