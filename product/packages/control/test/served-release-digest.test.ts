import { readFileSync } from "node:fs";
import { join } from "node:path";

import { ModelDeploymentReleaseSchema } from "@gradiated/contracts";
import { describe, expect, it } from "vitest";
import { z } from "zod";

import { servedReleaseDigest } from "../src/deployment-status/service.js";

// Both sides compute this key independently, so never regenerate one side to match the other.

const fixtureSchema = z.object({
  cases: z.array(
    z.strictObject({
      name: z.string(),
      release: ModelDeploymentReleaseSchema,
      digest: z.string(),
    }),
  ),
});

const { cases } = fixtureSchema.parse(
  JSON.parse(
    readFileSync(
      join(
        import.meta.dirname,
        "../../../services/gateway/test/fixtures/release-digests.json",
      ),
      "utf8",
    ),
  ),
);

describe("served release digest", () => {
  it.each(cases)("matches the gateway fixture for $name", (fixture) => {
    expect(servedReleaseDigest(fixture.release)).toBe(fixture.digest);
  });

  it("matches the digest the Rust gateway pins for a chat release", () => {
    expect(
      servedReleaseDigest({
        schema_version: 1,
        runtime_revision: "sglang-local-test-revision",
        model_path: "mlx-community/Qwen3-0.6B-4bit",
        model_revision: "73e3e38d981303bc594367cd910ea6eb48349da8",
        tokenizer_path: "mlx-community/Qwen3-0.6B-4bit",
        tokenizer_revision: "73e3e38d981303bc594367cd910ea6eb48349da8",
      }),
    ).toBe(
      "sha256:e4a74e6c4981b6176e08acc9fa391ca5fe5562485b5df96fdf088c48ae406eda",
    );
  });

  it("includes the protocol, which a decision deployment declares", () => {
    const chat = {
      schema_version: 1 as const,
      runtime_revision: "kev-f0ae8fb9-systemone-v1",
      model_path: "jaredpalmer/kev-9b",
      model_revision: "2629c06a5aeb0feb3b9783bafed17ed8f39ecf5c",
      runtime_model_name: "jaredpalmer/kev-9b",
      tokenizer_path: "Qwen/Qwen3.5-9B-Base",
      tokenizer_revision: "68c46c4b3498877f3ef123c856ecfde50c39f404",
    };
    const decision = { ...chat, protocol: "system_one" as const };

    expect(servedReleaseDigest(decision)).toBe(
      "sha256:4805b0811b6b3abfc82777b3e8f34aadd159dff5404f1c63290b11b17e3ac306",
    );
    expect(servedReleaseDigest(chat)).not.toBe(servedReleaseDigest(decision));
  });
});
