import { readFile } from "node:fs/promises";
import path from "node:path";

import {
  createControlDatabase,
  createInstanceService,
} from "@gradiated/control";
import { z } from "zod";

import type { Backend } from "../backend.js";
import { kmsSigner } from "@gradiated/nomad-pki";
import { hostImage, readSecret } from "./aws.js";
import { nomadNodeReader } from "./nomad-node.js";
import { createRegistrations } from "./registration.js";
import { createRunPodProvider } from "./runpod.js";

const RUNTIME_READER_SECRET = "gradiated/prod/nomad/host-runtime-reader";

// V8 parse errors quote their input, which here is a secret.
const parseSecretJson = (value: string): unknown => {
  try {
    return JSON.parse(value);
  } catch {
    throw new Error("deployment-status-tokens is not valid JSON");
  }
};

export type RegistrationSettings = {
  readonly credentialsDirectory: string;
  readonly hostImage: string;
  readonly caKeyId: string;
};

export const productionRegistrations = (
  settings: RegistrationSettings,
  backend: Backend,
  audit: (event: Record<string, unknown>) => void,
) => {
  const credential = async (name: string) => {
    try {
      return (
        await readFile(path.join(settings.credentialsDirectory, name), "utf8")
      ).trim();
    } catch {
      throw new Error(`Registration is not configured: ${name} is missing`);
    }
  };

  let instances: ReturnType<typeof createInstanceService> | undefined;

  return createRegistrations({
    providers: {
      runpod: async () =>
        createRunPodProvider({ apiKey: await credential("runpod-api-key") }),
    },
    instances: async () =>
      (instances ??= createInstanceService(
        createControlDatabase(await credential("database-url"), 2).database,
      )),
    hostImage: () => hostImage(settings.hostImage),
    caCertificate: () => credential("nomad-ca"),
    signer: kmsSigner(settings.caKeyId),
    runtimeReader: async () => {
      const key = await readSecret(
        RUNTIME_READER_SECRET,
        z.object({ AccessKeyId: z.string(), SecretAccessKey: z.string() }),
      );

      return {
        accessKeyId: key.AccessKeyId,
        secretAccessKey: key.SecretAccessKey,
      };
    },
    servingTokens: async (provider) => {
      const statusTokens = z
        .record(z.string(), z.string())
        .parse(parseSecretJson(await credential("deployment-status-tokens")));
      const deploymentStatus = statusTokens[provider];
      if (!deploymentStatus) {
        throw new Error(`No deployment status token for ${provider}`);
      }

      return {
        runtimeAccess: await credential("runtime-access-token"),
        deploymentStatus,
      };
    },
    readNode: nomadNodeReader(backend),
    audit,
  });
};
