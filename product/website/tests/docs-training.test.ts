import { createRequire } from "node:module";
import { describe, expect, it } from "vitest";

import {
  CATALOG,
  SDK_LANGUAGES,
  compact,
  estimatePlan,
  illustrativeRouterPrompts,
  operatingPoint,
  renderMessages,
  routerCurve,
  usd,
} from "../src/components/docs/training/data";
import type { RecipeKind } from "../src/components/docs/training/data";
import {
  RECIPES,
  recipeSnippet,
} from "../src/components/docs/training/recipes";
import recording from "../src/components/docs/training/run-replay.json";

const { parseMeta } = createRequire(import.meta.url)(
  "../scripts/docs-code-meta.cjs",
) as { parseMeta(meta: string): { title?: string; lines: Set<number> } };

const chat = [
  { role: "user" as const, content: "Is 391 prime?" },
  { role: "assistant" as const, content: "<think>17 x 23</think>No." },
  { role: "user" as const, content: "And 397?" },
  { role: "assistant" as const, content: "<think>no factor</think>Yes." },
];
const defaults = {
  train_on: "last" as const,
  thinking: "auto" as const,
  preserve_thinking: false,
};

describe("renderMessages, ported from grad's planner", () => {
  it("trains only the last assistant turn by default", () => {
    const rendered = renderMessages("r", chat, defaults);
    if (!rendered.ok) throw new Error(rendered.error);

    const trained = rendered.spans.filter((span) => span.trained);
    expect(trained.map((span) => span.message)).toEqual([3]);
    expect(
      rendered.spans.filter((span) => span.kind === "header"),
    ).toHaveLength(4);
  });

  it("strips reasoning from earlier turns unless preserve_thinking", () => {
    const stripped = renderMessages("r", chat, defaults);
    const kept = renderMessages("r", chat, {
      ...defaults,
      preserve_thinking: true,
    });
    if (!stripped.ok || !kept.ok) throw new Error("render failed");

    expect(stripped.spans[3].text).toBe("No.<|im_end|>\n");
    expect(stripped.spans[3].stripped).toBe("<think>17 x 23</think>");
    expect(kept.spans[3].text).toContain("<think>");
    expect(stripped.spans[7].text).toContain("<think>");
  });

  it("refuses a thinking mode the record contradicts", () => {
    const off = renderMessages("r_1", chat, { ...defaults, thinking: "off" });
    expect(off).toEqual({
      ok: false,
      error: "Record 'r_1' contains a <think> block but thinking='off'.",
    });

    const plain = [
      { role: "user" as const, content: "hi" },
      { role: "assistant" as const, content: "hello" },
    ];
    expect(
      renderMessages("r_2", plain, { ...defaults, thinking: "on" }).ok,
    ).toBe(false);
  });

  it("lets a message's own train field win", () => {
    const rendered = renderMessages(
      "r",
      [
        { role: "user", content: "a", train: true },
        { role: "assistant", content: "b", train: false },
      ],
      defaults,
    );
    if (!rendered.ok) throw new Error(rendered.error);

    expect(rendered.spans.map((span) => span.trained)).toEqual([
      false,
      true,
      false,
      false,
    ]);
  });
});

describe("estimatePlan", () => {
  it("matches the planner's arithmetic", () => {
    const plan = estimatePlan({
      records: 14_200,
      tokensPerRecord: 2_973,
      epochs: 1,
      batchSize: 128,
      evalFraction: 0.1,
      price: 0.4,
      maxCostUsd: null,
    });

    expect(plan.trainRecords).toBe(12_780);
    expect(plan.steps).toBe(100);
    expect(plan.warnings).toEqual([]);
    expect(compact(plan.tokens)).toBe("38.0M");
    expect(usd(plan.costUsd)).toBe("$15.20");
  });

  it("warns about too few steps and a low cap, as runs.plan does", () => {
    const plan = estimatePlan({
      records: 400,
      tokensPerRecord: 100,
      epochs: 1,
      batchSize: 128,
      evalFraction: 0.1,
      price: 1.2,
      maxCostUsd: 0.01,
    });

    expect(plan.warnings[0]).toBe(
      "3 steps is below the 100 we recommend; use batch_size=3 or more epochs/data.",
    );
    expect(plan.warnings[1]).toContain("status stopped_budget");
  });

  it("formats money like the CLI", () => {
    expect(usd(0.165)).toBe("$0.17");
    expect(usd(0.0096)).toBe("$0.0096");
    expect(usd(0)).toBe("$0.00");
  });
});

describe("recipe snippets", () => {
  it("has one for every recipe in every SDK language", () => {
    for (const kind of Object.keys(RECIPES) as RecipeKind[]) {
      for (const language of SDK_LANGUAGES) {
        const { code } = recipeSnippet(kind, language);
        const recipe = RECIPES[kind];
        expect(code).toContain(recipe.name);
        if (language === "Python") expect(code).toContain(recipe.className);
        if (language === "CLI")
          expect(code).toContain(`--recipe ${recipe.cli}`);
      }
    }
  });

  it("only names catalog models", () => {
    const ids = new Set(CATALOG.map((model) => model.id));
    for (const recipe of Object.values(RECIPES)) {
      if (recipe.model) expect(ids.has(recipe.model)).toBe(true);
    }
  });
});

describe("router illustration", () => {
  it("picks the most offload within the allowed drop", () => {
    const curve = routerCurve(illustrativeRouterPrompts(), 1, 6);
    const chosen = operatingPoint(curve, 0.02);

    expect(curve[0].offload).toBe(0);
    expect(curve[0].quality - chosen.quality).toBeLessThanOrEqual(0.02 + 1e-9);
    for (const point of curve) {
      if (curve[0].quality - point.quality <= 0.02) {
        expect(point.offload).toBeLessThanOrEqual(chosen.offload);
      }
    }
  });
});

describe("recorded run", () => {
  it("keeps every frame the size the renderer drew", () => {
    const rows = recording.rows as unknown as Array<Array<[string, string]>>;
    const width = (id: number) =>
      [...rows[id].map(([text]) => text).join("")].length;

    for (const frame of [...recording.frames, ...recording.interrupt]) {
      expect(frame.wide).toHaveLength(30);
      expect(frame.narrow).toHaveLength(18);
      for (const id of frame.wide) expect(width(id)).toBeLessThanOrEqual(100);
    }
    expect(recording.frames.at(-1)?.label).toBe("completed");
  });
});

describe("code fence meta", () => {
  it("reads a title and highlighted line ranges", () => {
    const meta = parseMeta('title="train.py" {1,3-4}');
    expect(meta.title).toBe("train.py");
    expect([...meta.lines]).toEqual([1, 3, 4]);
  });
});
