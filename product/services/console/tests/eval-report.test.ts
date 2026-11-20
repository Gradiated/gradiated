import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { EvalSummary } from "../src/components/report/eval-blocks";
import { EvalDataContext } from "../src/components/report/eval-context";
import { parseReport } from "../src/components/report/report-schema";
import {
  aggregate,
  parseEval,
  pickModels,
  verdictOf,
} from "../src/lib/eval-data";
import { sampleEval } from "../src/stories/eval-fixture";

const index = parseEval(JSON.stringify(sampleEval));
const [mini, frontier] = index.models;

describe("eval data", () => {
  it("pools rollouts per model", () => {
    expect(aggregate(index, mini!.id, index.metric)).toMatchObject({
      n: 18,
      passed: 15,
    });
    expect(aggregate(index, frontier!.id, index.metric)).toMatchObject({
      n: 18,
      passed: 13,
    });
  });

  it("leaves rollouts that did not complete out of the score", () => {
    const broken = structuredClone(sampleEval);
    broken.rollouts[0]!.status = "error";
    const result = aggregate(
      parseEval(JSON.stringify(broken)),
      mini!.id,
      index.metric,
    );

    expect(result).toMatchObject({ n: 17, passed: 14, incomplete: 1 });
  });

  it("compares models case by case", () => {
    const verdicts = index.cases.map(
      (item) =>
        verdictOf(index, item.id, mini!, frontier!, index.metric).verdict,
    );

    expect(verdicts).toEqual([
      "better",
      "same",
      "worse",
      "same",
      "same",
      "better",
    ]);
  });

  it("ignores a model selection that repeats one model", () => {
    expect(pickModels(index, ["frontier", "frontier"])).toEqual([
      mini,
      frontier,
    ]);
  });

  it("rejects files that are not evals", () => {
    expect(() => parseEval('{"schema":"other"}')).toThrow(
      /Not a valid eval file/,
    );
  });
});

describe("difference interval groups", () => {
  it("keeps cases without the grouping tag", () => {
    const grouped = structuredClone(sampleEval);
    grouped.interval_group_by = "Customer";
    grouped.cases[0]!.tags = { ...grouped.cases[0]!.tags, Customer: "Acme" };
    const html = renderToStaticMarkup(
      createElement(
        EvalDataContext.Provider,
        {
          value: new Map([
            [
              "a.eval.json",
              {
                status: "ready" as const,
                index: parseEval(JSON.stringify(grouped)),
              },
            ],
          ]),
        },
        createElement(EvalSummary, { eval: "a.eval.json" }),
      ),
    );

    const [, low, high] = /95% interval (\S+) pts to (\S+) pts/.exec(html)!;
    expect(low).not.toBe(high);
  });
});

describe("difference interval pairing", () => {
  it("shows no interval when the models were never scored on the same case", () => {
    const unpaired = structuredClone(sampleEval);
    for (const rollout of unpaired.rollouts)
      if (
        (rollout.model_id === "support-mini") !==
        (rollout.case_id === "case-1")
      )
        rollout.status = "error";
    const html = renderToStaticMarkup(
      createElement(
        EvalDataContext.Provider,
        {
          value: new Map([
            [
              "a.eval.json",
              {
                status: "ready" as const,
                index: parseEval(JSON.stringify(unpaired)),
              },
            ],
          ]),
        },
        createElement(EvalSummary, { eval: "a.eval.json" }),
      ),
    );

    expect(html).not.toContain("95% interval");
  });
});

describe("eval report tags", () => {
  it("collects the eval files a report references", () => {
    const report = parseReport(
      '{% eval-summary eval="a.eval.json" /%}\n\n{% eval-cases eval="a.eval.json" /%}\n\n{% eval-breakdown eval="b.eval.json" by="Area" /%}',
    );

    expect(report.errors).toEqual([]);
    expect(report.evalFiles).toEqual(["a.eval.json", "b.eval.json"]);
  });

  it("renders a summary from a loaded eval", () => {
    const html = renderToStaticMarkup(
      createElement(
        QueryClientProvider,
        { client: new QueryClient() },
        createElement(
          EvalDataContext.Provider,
          {
            value: new Map([
              ["a.eval.json", { status: "ready" as const, index }],
            ]),
          },
          createElement(EvalSummary, { eval: "a.eval.json" }),
        ),
      ),
    );

    expect(html).toContain("passes 83.3%");
    expect(html).toContain("against 72.2%");
    expect(html).toContain("6 cases");
  });
});
