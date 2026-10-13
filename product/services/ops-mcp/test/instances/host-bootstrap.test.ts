import { describe, expect, it } from "vitest";
import { hostBootstrapEnvironment } from "../../src/instances/host-bootstrap.js";
const id = "019d5a4a-0000-7000-8000-000000000001";
const instance = {
  provider: "runpod",
  providerAccountId: "account",
  providerInstanceId: "pod",
  region: null,
  faultDomain: null,
  sku: "8x NVIDIA B300",
};
const create = (sku = instance.sku, address = "100.65.73.119") =>
  hostBootstrapEnvironment(
    { ...instance, sku },
    id,
    "a".repeat(64),
    "tskey-auth-one-time",
    address,
  );
describe("GPU bootstrap environment", () => {
  it("contains pinned private runtime profiles and only scoped GPU credentials", async () => {
    const env = await create();
    const payload = JSON.parse(
      Buffer.from(env.GRADIATED_GPU_BOOTSTRAP, "base64").toString(),
    );
    expect(Object.keys(env)).toEqual(["GRADIATED_GPU_BOOTSTRAP"]);
    expect(payload.config.instance_id).toBe(id);
    expect(payload.api_endpoint).toBe("100.65.73.119");
    expect(payload.config.hf_home).toBe("/home/runtime/.cache/huggingface");
    for (const [digest, profile] of Object.entries(payload.config.runtimes) as [
      string,
      { image: string; environment?: Record<string, string> },
    ][]) {
      expect(profile.image).toContain(`@sha256:${digest}`);
      expect(profile.environment?.HOST_IDENTITY_FILE).toBeUndefined();
    }
    expect(JSON.stringify(payload)).not.toMatch(
      /nomad_node|AWS_SECRET|DATABASE_URL|client_secret/,
    );
  });
  it("limits RTX hosts to Kev and training profiles", async () => {
    const env = await create("1x NVIDIA RTX PRO 6000");
    const payload = JSON.parse(
      Buffer.from(env.GRADIATED_GPU_BOOTSTRAP, "base64").toString(),
    );
    expect(
      Object.values(payload.config.runtimes).every((p: unknown) => {
        const profile = p as { kind?: string; model_id: string };
        return (
          profile.kind === "training" ||
          profile.model_id === "jaredpalmer/kev-9b"
        );
      }),
    ).toBe(true);
  });
  it("rejects unqualified hardware and public control destinations", async () => {
    await expect(create("1x unknown GPU")).rejects.toThrow("qualified");
    await expect(create(instance.sku, "8.8.8.8")).rejects.toThrow("Tailscale");
  });
});
