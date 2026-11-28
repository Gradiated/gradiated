import { describe, expect, it } from "vitest";

import { searchEntries } from "../src/components/docs/DocsSearch";
import { curlFor } from "../src/components/docs/training/ApiReference";
import { ERROR_ENTRIES } from "../src/components/docs/training/ErrorCodes";
import requestExamples from "../src/components/docs/training/api-examples.json";
import {
  API,
  TAG_ORDER,
  example,
  operationAnchor,
  typeLabel,
} from "../src/components/docs/training/api-schema";
import { SDK_CALLS } from "../src/components/docs/training/api-sdk";
import { ERROR_DOCS } from "../src/components/docs/training/error-docs";
import generatedCodes from "../src/docs/training/generated/error-codes.json";
import vercel from "../vercel.json";
import { buildSearchIndex } from "../scripts/docs-search-index.mjs";

const operationIds = new Set(API.operations.map((op) => op.id));

describe("training API reference", () => {
  it("lists only public operations, each under a known tag", () => {
    expect(API.operations.length).toBeGreaterThan(40);
    for (const op of API.operations) {
      expect(op.path).not.toMatch(/trainer-jobs/);
      expect(TAG_ORDER).toContain(op.tag);
    }
  });

  it("gives every operation a unique anchor", () => {
    const anchors = API.operations.map(operationAnchor);
    expect(new Set(anchors).size).toBe(anchors.length);
    expect(
      operationAnchor(API.operations.find((op) => op.id === "createRun")!),
    ).toBe("create-run");
  });

  it("resolves every schema reference", () => {
    const missing = new Set<string>();
    const walk = (value: unknown): void => {
      if (!value || typeof value !== "object") return;
      const ref = (value as { $ref?: unknown }).$ref;
      if (typeof ref === "string" && !API.schemas[ref]) missing.add(ref);
      Object.values(value).forEach(walk);
    };
    walk(API.operations);
    walk(API.schemas);
    expect([...missing]).toEqual([]);
  });

  it("names request examples and SDK calls by real operation ids", () => {
    for (const id of Object.keys(requestExamples))
      expect(operationIds).toContain(id);
    for (const id of Object.keys(SDK_CALLS)) expect(operationIds).toContain(id);
  });

  it("has a request example for every operation that takes a body", () => {
    const withBody = API.operations.filter(
      (op) => op.body && op.id !== "pinArtifact",
    );
    for (const op of withBody) {
      expect(Object.keys(requestExamples), op.id).toContain(op.id);
    }
  });

  it("writes curl with the curated body and the base URL variable", () => {
    const op = API.operations.find((o) => o.id === "createRun")!;
    const curl = curlFor(op);
    expect(curl).toContain('curl -X POST "$GRADIATED_BASE_URL/v1/runs"');
    expect(curl).toContain('"max_cost_usd": 5');
    const get = API.operations.find((o) => o.id === "getRun")!;
    expect(curlFor(get)).toMatch(
      /^curl "\$GRADIATED_BASE_URL\/v1\/runs\/run_[0-9a-f]{24}"/,
    );
  });

  it("derives readable types and example values from the schema", () => {
    const run = API.operations.find((o) => o.id === "getRun")!;
    const schema = run.responses[0]!.schema!;
    expect(typeLabel(schema)).toBe("Run");
    const value = example(schema) as Record<string, unknown>;
    expect(value.id).toMatch(/^run_[0-9a-f]{24}$/);
    expect(typeof value.created_at).toBe("string");
  });
});

describe("error codes", () => {
  it("explains every code grad-server answers with", () => {
    const undocumented = Object.keys(generatedCodes.codes).filter(
      (code) => !ERROR_DOCS[code],
    );
    expect(undocumented).toEqual([]);
  });

  it("explains no code the server no longer has", () => {
    const stale = Object.keys(ERROR_DOCS).filter(
      (code) => !(code in generatedCodes.codes),
    );
    expect(stale).toEqual([]);
  });

  it("gives every entry a meaning and a status", () => {
    for (const entry of ERROR_ENTRIES) {
      expect(entry.means, entry.code).not.toBe("");
      expect(entry.statuses.length, entry.code).toBeGreaterThan(0);
    }
  });

  it("sends a problem's type URL to its entry", () => {
    expect(vercel.redirects).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          source: "/problems/:code/",
          destination: "/docs/training/errors/?code=:code",
        }),
      ]),
    );
  });
});

describe("docs search", () => {
  const index = buildSearchIndex(
    [
      {
        path: "/docs/training/recipes/router/",
        title: "Model router",
        source:
          '# Model router\n\nIntro text.\n\n## Train a router\n\nPass `rubric` to score.\n\n```python\n## not a heading\n```\n\n<DocsStep title="Pick candidates">\n\nTwo models.\n',
      },
    ],
    {
      groups: { "/docs/training/recipes/router/": "Recipe guides" },
      entries: [
        {
          path: "/docs/training/errors/#artifact_pinned",
          title: "Errors",
          heading: "artifact_pinned",
          text: "409 The artifact is pinned.",
        },
      ],
    },
  ) as { entries: Array<{ path: string; heading?: string; group: string }> };

  it("indexes each section under its heading's anchor, skipping code", () => {
    const paths = index.entries.map((entry) => entry.path);
    expect(paths).toContain("/docs/training/recipes/router/#train-a-router");
    expect(paths).toContain("/docs/training/recipes/router/#pick-candidates");
    expect(paths).not.toContain("/docs/training/recipes/router/#not-a-heading");
  });

  it("ranks a heading match above a body match", () => {
    const results = searchEntries(
      index.entries.map((entry) => ({ text: "", title: "", ...entry })),
      "artifact pinned",
    );
    expect(results[0]?.heading).toBe("artifact_pinned");
    expect(searchEntries(index.entries as never, "")).toEqual([]);
  });
});
