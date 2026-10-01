import { Agent, request } from "node:https";
import { z } from "zod";
import {
  cliProfile,
  issueCertificate,
  kmsSigner,
  type CertificateSigner,
} from "./certificates.js";
import { expiryTimestamp, renewingCertificate } from "./renewal.js";

const REQUEST_TIMEOUT_MS = 10_000;
const SERVER_NAME = "server.global.nomad";
export type NomadRequest = (
  path: string,
  method?: "GET" | "POST" | "DELETE",
  body?: unknown,
) => Promise<unknown>;
const nomadEnvironmentSchema = z.object({
  NOMAD_ADDR: z.url(),
  NOMAD_TOKEN: z.string().min(1),
  NOMAD_CA_PEM: z.string().min(1),
  NOMAD_CLIENT_CERT_PEM: z.string().min(1).optional(),
  NOMAD_CLIENT_KEY_PEM: z.string().min(1).optional(),
  NOMAD_CA_KMS_KEY: z.string().min(1).optional(),
});

const nomadCredentialsSchema = nomadEnvironmentSchema.refine(
  (value) =>
    value.NOMAD_CA_KMS_KEY ||
    (value.NOMAD_CLIENT_CERT_PEM && value.NOMAD_CLIENT_KEY_PEM),
  "Nomad needs a CA signing key or a client certificate and private key",
);

export type NomadEnvironment = z.infer<typeof nomadEnvironmentSchema>;

export const parseNomadEnvironment = (
  environment: NodeJS.ProcessEnv,
): NomadEnvironment | null =>
  environment.NOMAD_ADDR ? nomadCredentialsSchema.parse(environment) : null;

export const createNomadRequest = (
  nomad: NomadEnvironment,
  options: {
    signer?: CertificateSigner;
    onCertificate?: (expires: number) => void;
  } = {},
): NomadRequest => {
  const signingKey = nomad.NOMAD_CA_KMS_KEY;
  const certificate = signingKey
    ? renewingCertificate(async () => {
        const issued = await issueCertificate(
          nomad.NOMAD_CA_PEM,
          options.signer ?? kmsSigner(signingKey),
          cliProfile,
        );
        options.onCertificate?.(expiryTimestamp(issued.certificate));
        return issued;
      })
    : undefined;
  const agent = new Agent({
    keepAlive: true,
    ca: nomad.NOMAD_CA_PEM,
    timeout: 30_000,
    servername: SERVER_NAME,
  });

  return async (path, method = "GET", payload) => {
    const issued = await certificate?.get();
    return new Promise((resolve, reject) => {
      const outgoing = request(
        new URL(path, nomad.NOMAD_ADDR),
        {
          agent,
          method,
          cert: issued?.certificate ?? nomad.NOMAD_CLIENT_CERT_PEM,
          key: issued?.privateKey ?? nomad.NOMAD_CLIENT_KEY_PEM,
          headers: {
            "x-nomad-token": nomad.NOMAD_TOKEN,
            "content-type": "application/json",
          },
          signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
        },
        (response) => {
          let body = "";
          response.setEncoding("utf8");
          response.on("data", (chunk: string) => (body += chunk));
          response.on("close", () => {
            if (!response.complete) {
              reject(
                Object.assign(new Error(`Nomad ${path} ended early`), {
                  code: "ECONNRESET",
                }),
              );
            }
          });
          response.on("end", () => {
            if (response.statusCode !== 200) {
              reject(
                Object.assign(
                  new Error(`Nomad ${path} returned ${response.statusCode}`),
                  { code: String(response.statusCode) },
                ),
              );
              return;
            }
            try {
              resolve(JSON.parse(body));
            } catch (error) {
              reject(error);
            }
          });
        },
      );
      // The logger never prints messages, so a timeout needs a code to be told apart.
      outgoing.on("error", (error) =>
        reject(
          error.name === "AbortError"
            ? Object.assign(error, { code: "ETIMEDOUT" })
            : error,
        ),
      );
      outgoing.end(payload === undefined ? undefined : JSON.stringify(payload));
    });
  };
};
