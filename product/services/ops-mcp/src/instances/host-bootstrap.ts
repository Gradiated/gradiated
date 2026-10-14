import { readFile } from "node:fs/promises";
import { z } from "zod";
import type { ProviderInstance } from "./provider.js";

export const hostBootstrapEnvironment = async (
  instance: ProviderInstance,
  instanceId: string,
  managementToken: string,
  authKey: string,
  apiEndpoint: string,
  hostBundle?: { sha256: string; base_id: string; url: string },
) => {
  const count = Number(instance.sku.match(/^(\d+)x /)?.[1]);
  if (
    !Number.isInteger(count) ||
    count < 1 ||
    !/B300|RTX PRO 6000/.test(instance.sku)
  )
    throw new Error(
      "GPU enrollment supports the qualified B300 and RTX PRO 6000 runtimes",
    );
  if (
    !/^tskey-auth-/.test(authKey) ||
    !/^[A-Za-z0-9_-]{32,128}$/.test(managementToken)
  )
    throw new Error("Invalid scoped GPU bootstrap credentials");
  const address = z.ipv4().parse(apiEndpoint).split(".").map(Number);
  if (address[0] !== 100 || address[1]! < 64 || address[1]! > 127)
    throw new Error("GPU control requires a Tailscale address");
  const catalogue: Record<
    string,
    {
      gpus: number;
      kind?: string;
      model_id: string;
      environment?: Record<string, string>;
    }
  > = JSON.parse(
    await readFile(
      new URL("../../../../inference/gpu/runtimes.json", import.meta.url),
      "utf8",
    ),
  );
  const runtimes = Object.fromEntries(
    Object.entries(catalogue).filter(
      ([, profile]) =>
        profile.kind === "training" ||
        (profile.gpus <= count &&
          (instance.sku.includes("B300") ||
            profile.model_id === "jaredpalmer/kev-9b")),
    ),
  );
  if (
    !Object.keys(runtimes).length ||
    Object.values(runtimes).some(
      (profile) => profile.environment?.HOST_IDENTITY_FILE,
    )
  )
    throw new Error("GPU bootstrap requires private runtime profiles");
  return {
    GRADIATED_GPU_BOOTSTRAP: Buffer.from(
      JSON.stringify({
        ...(hostBundle ? { host_bundle: hostBundle } : {}),
        instance_id: z.uuid().parse(instanceId),
        management_token: managementToken,
        auth_key: authKey,
        api_endpoint: apiEndpoint,
        config: {
          instance_id: instanceId,
          hf_home: "/home/runtime/.cache/huggingface",
          runtimes,
        },
      }),
    ).toString("base64"),
  };
};
