import { afterEach, describe, expect, it, vi } from "vitest";

import {
  requiredEnv,
  requiredServiceUrls,
  upsertModelDeployments,
} from "../src/operations/catalog-operation.js";
import { modelRecord } from "./support.js";

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("catalog operation environment", () => {
  it("rejects a missing variable", () => {
    vi.stubEnv("CATALOG_TEST_VALUE", "");

    expect(() => requiredEnv("CATALOG_TEST_VALUE")).toThrow(
      "CATALOG_TEST_VALUE is required",
    );
  });

  it("pairs each deployment with its service URL", () => {
    vi.stubEnv("CATALOG_TEST_URLS", " http://a , http://b ");

    expect(requiredServiceUrls("CATALOG_TEST_URLS", ["one", "two"])).toEqual([
      { id: "one", serviceUrl: "http://a" },
      { id: "two", serviceUrl: "http://b" },
    ]);
  });

  it.each(["http://a", "http://a,http://b,http://c"])(
    "rejects a URL count that does not match the deployments: %s",
    (urls) => {
      vi.stubEnv("CATALOG_TEST_URLS", urls);

      expect(() =>
        requiredServiceUrls("CATALOG_TEST_URLS", ["one", "two"]),
      ).toThrow("CATALOG_TEST_URLS must contain 2 URLs");
    },
  );
});

describe("model deployment configuration", () => {
  it("upserts the model, then each deployment with shared placement and release", async () => {
    const calls: unknown[] = [];
    const release = {
      schema_version: 1,
      runtime_revision: "runtime-v1",
      model_path: "/models/kimi",
      model_revision: "abc",
      tokenizer_path: "/models/kimi",
      tokenizer_revision: "abc",
    } as const;
    const placement = {
      provider: "runpod",
      region: "us",
      faultDomain: "runpod:pod-1",
    };

    await upsertModelDeployments(
      {
        upsertModel: async (input) => {
          calls.push(["model", input.id]);
          return modelRecord;
        },
        upsertModelDeployment: async (input) => {
          calls.push(["deployment", input]);
          return { ...input, createdAt: new Date(), updatedAt: new Date() };
        },
      },
      {
        model: modelRecord,
        deployments: [
          { id: "one", serviceUrl: "http://a" },
          { id: "two", serviceUrl: "http://b" },
        ],
        placement,
        release,
      },
    );

    expect(calls).toEqual([
      ["model", modelRecord.id],
      ...["one", "two"].map((id, index) => [
        "deployment",
        {
          id,
          modelId: modelRecord.id,
          status: "available",
          ...placement,
          serviceUrl: ["http://a", "http://b"][index],
          release,
        },
      ]),
    ]);
  });
});
