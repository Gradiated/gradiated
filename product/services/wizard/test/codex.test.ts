import { describe, expect, it } from "vitest";
import {
  buildProfileBlock,
  buildProviderBlock,
  mergeProfileConfig,
  mergeProviderConfig,
} from "../src/agents/codex.js";

describe("Codex configuration", () => {
  it("builds a Responses provider without embedding the API key", () => {
    const block = buildProviderBlock("https://api.gradiated.com/");

    expect(block).toContain("[model_providers.gradiated]");
    expect(block).toContain('base_url = "https://api.gradiated.com/v1"');
    expect(block).toContain('wire_api = "responses"');
    expect(block).toContain('auth = { command = "node"');
    expect(block).not.toContain("grad_");
  });

  it("replaces the managed provider block and preserves user configuration", () => {
    const oldBlock = buildProviderBlock("https://old.example.com");
    const existing = `model = "openai-model"\n\n${oldBlock}\n\n[features]\nweb_search = true\n`;
    const merged = mergeProviderConfig(
      existing,
      buildProviderBlock("https://api.gradiated.com"),
    );

    expect(merged).toContain('model = "openai-model"');
    expect(merged).toContain("[features]");
    expect(merged).toContain("web_search = true");
    expect(merged).not.toContain("old.example.com");
    expect(merged).toContain("https://api.gradiated.com/v1");
    expect(merged.indexOf("[features]")).toBeLessThan(
      merged.indexOf("[model_providers.gradiated]"),
    );
  });

  it("keeps profile root keys before user-defined tables", () => {
    const merged = mergeProfileConfig(
      "[features]\nweb_search = true\n",
      buildProfileBlock("z-ai/glm-5.3-flash"),
    );

    expect(merged.indexOf('model_provider = "gradiated"')).toBeLessThan(
      merged.indexOf("[features]"),
    );
  });
});
