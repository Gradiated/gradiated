import { readFile } from "node:fs/promises";
import path from "node:path";
import { randomBytes } from "node:crypto";

import {
  createControlDatabase,
  createInstanceService,
  createInstanceCertificateService,
} from "@gradiated/control";
import { z } from "zod";

import type { Backend } from "../backend.js";
import { kmsSigner } from "@gradiated/nomad-pki";
import { readSecret } from "./aws.js";
import { nomadNodeReader } from "./nomad-node.js";
import { createRegistrations } from "./registration.js";
import { createRunPodProvider } from "./runpod.js";
import { sshRunner } from "./ssh.js";
import { tailscaleAuthKey } from "./tailscale.js";

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
  let certificateCredentials:
    ReturnType<typeof createInstanceCertificateService> | undefined;

  return createRegistrations({
    providers: {
      runpod: async () => {
        const optional = async (name: string) =>
          readFile(
            path.join(settings.credentialsDirectory, name),
            "utf8",
          ).catch((error: NodeJS.ErrnoException) => {
            if (error.code === "ENOENT") return null;

            throw new Error(
              `Cannot read in-place enrollment credential ${name}`,
            );
          });
        const [privateKey, pinnedKeys] = await Promise.all([
          optional("runpod-ssh-key"),
          optional("runpod-ssh-host-keys"),
        ]);
        let inPlace;
        if (privateKey && pinnedKeys) {
          let parsed: unknown;
          try {
            parsed = JSON.parse(pinnedKeys);
          } catch {
            throw new Error("runpod-ssh-host-keys is not valid JSON");
          }
          const hostKeys = z
            .record(z.string(), z.string().regex(/^[a-f0-9]{64}$/))
            .parse(parsed);
          inPlace = { run: sshRunner(privateKey), hostKeys };
        }

        return createRunPodProvider({
          apiKey: await credential("runpod-api-key"),
          inPlace,
        });
      },
    },
    instances: async () =>
      (instances ??= createInstanceService(
        createControlDatabase(await credential("database-url"), 2).database,
      )),
    certificateCredentials: async () =>
      (certificateCredentials ??= createInstanceCertificateService(
        createControlDatabase(await credential("database-url"), 2).database,
      )),
    hostImage: settings.hostImage,
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
        runtimeAccess: randomBytes(32).toString("base64url"),
        deploymentStatus,
      };
    },
    tailscaleAuthKey,
    readNode: nomadNodeReader(backend),
    audit,
  });
};
