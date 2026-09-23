import { describe, expect, it } from "vitest";

import type { VersionView } from "@/store/fine-tuning-types";
import { evaluationResults } from "@/store/mock-evaluation";

import { seededSupportTriage } from "./support/fine-tuning";

const {
  seed,
  task: supportTriage,
  version: seededVersion,
} = seededSupportTriage();

const versionJudged = (
  outcome: Partial<VersionView["summary"]["vs_comparison"]>,
  holdoutExamples = seededVersion.summary.holdout_examples,
): VersionView => ({
  ...seededVersion,
  summary: {
    ...seededVersion.summary,
    holdout_examples: holdoutExamples,
    vs_comparison: {
      ...seededVersion.summary.vs_comparison,
      win: 0,
      tie: 0,
      loss: 0,
      unresolved: 0,
      ...outcome,
    },
  },
});

const results = (version: VersionView, options: { limit?: number } = {}) =>
  evaluationResults({
    version,
    conversations: seed.conversations,
    traces: seed.traces,
    taskSlug: supportTriage.slug,
    ...options,
  });

describe("evaluationResults", () => {
  it("returns the same verdicts for the same version", () => {
    const verdicts = () => results(seededVersion).map((line) => line.verdict);

    expect(verdicts().length).toBeGreaterThan(0);
    expect(verdicts()).toEqual(verdicts());
  });

  it("degrades the losing side of each verdict", () => {
    const equivalent = results(versionJudged({ tie: 1 }));
    const better = results(versionJudged({ win: 1 }));
    const worse = results(versionJudged({ loss: 1 }));

    expect(equivalent.map((line) => line.verdict)).toEqual(
      equivalent.map(() => "equivalent"),
    );
    for (const [index, line] of equivalent.entries()) {
      expect(line.comparison_response).toBe(line.fine_tuned_response);
      expect(better[index]).toMatchObject({
        verdict: "better",
        fine_tuned_response: line.fine_tuned_response,
      });
      expect(worse[index]).toMatchObject({
        verdict: "worse",
        comparison_response: line.comparison_response,
        fine_tuned_response: better[index]?.comparison_response,
      });
    }
    expect(
      better.some(
        (line) => line.comparison_response !== line.fine_tuned_response,
      ),
    ).toBe(true);
  });

  it("marks every line unresolved when nothing resolved", () => {
    expect(
      results(versionJudged({ unresolved: 1 })).every(
        (line) => line.verdict === "unresolved",
      ),
    ).toBe(true);
  });

  it("shows at most the limit and never more than the holdout", () => {
    expect(results(seededVersion, { limit: 3 })).toHaveLength(3);
    expect(results(versionJudged({ win: 1 }, 2), { limit: 12 })).toHaveLength(
      2,
    );
  });
});
