import https from "node:https";
import { readFileSync } from "node:fs";

export type BackendSystem =
  "prometheus" | "loki" | "alertmanager" | "kubernetes" | "nomad";
export type BackendParams = Record<string, string | readonly string[]>;
export type Backend = (
  system: BackendSystem,
  path: string,
  params?: BackendParams,
) => Promise<unknown>;

export type BackendConfig = {
  prometheus: string;
  loki: string;
  lokiTenant: string;
  alertmanager: string;
  nomad: {
    url: string;
    caFile: string;
    certFile: string;
    keyFile: string;
    tokenFile: string;
  };
};

const MAX_BYTES = 8_000_000;
const TIMEOUT_MS = 10_000;
const KUBERNETES_URL = "https://kubernetes.default.svc";
const SERVICE_ACCOUNT = "/var/run/secrets/kubernetes.io/serviceaccount";

const searchParams = (params: BackendParams): string => {
  const search = new URLSearchParams();

  for (const [key, value] of Object.entries(params)) {
    for (const item of [value].flat()) search.append(key, item);
  }

  return search.toString();
};

const parseBody = (chunks: Uint8Array[]): unknown => {
  try {
    return JSON.parse(Buffer.concat(chunks).toString());
  } catch {
    throw new Error("upstream_invalid");
  }
};

type HttpsResponse = {
  body: unknown;
  headers: Record<string, string | string[] | undefined>;
};

const getHttps = (
  url: URL,
  agent: https.Agent,
  headers: Record<string, string>,
): Promise<HttpsResponse> =>
  new Promise((resolve, reject) => {
    const request = https.get(url, { agent, headers }, (response) => {
      const chunks: Buffer[] = [];
      let size = 0;

      response.on("data", (chunk: Buffer) => {
        size += chunk.length;
        if (size > MAX_BYTES) {
          request.destroy(new Error("response_limit"));
          return;
        }

        chunks.push(chunk);
      });
      response.on("error", reject);
      response.on("end", () => {
        if (response.statusCode !== 200) {
          reject(new Error("upstream_failed"));
          return;
        }

        try {
          resolve({ body: parseBody(chunks), headers: response.headers });
        } catch (error) {
          reject(error);
        }
      });
    });
    const timeout = setTimeout(
      () => request.destroy(new Error("upstream_timeout")),
      TIMEOUT_MS,
    );

    request.on("close", () => clearTimeout(timeout));
    request.on("error", reject);
  });

const getHttp = async (
  url: URL,
  headers: Record<string, string>,
): Promise<unknown> => {
  const response = await fetch(url, {
    headers,
    signal: AbortSignal.timeout(TIMEOUT_MS),
    redirect: "error",
  });
  if (!response.ok || !response.body) {
    await response.body?.cancel();
    throw new Error("upstream_failed");
  }

  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;

      size += value.length;
      if (size > MAX_BYTES) throw new Error("response_limit");

      chunks.push(value);
    }
  } finally {
    await reader.cancel();
  }

  return parseBody(chunks);
};

export const createBackend = (config: BackendConfig): Backend => {
  let kubernetesAgent: https.Agent | undefined;
  let nomadTls: { material: string; agent: https.Agent } | undefined;

  return async (system, path, params = {}) => {
    if (system === "kubernetes") {
      const url = new URL(path, KUBERNETES_URL);
      url.search = searchParams(params);
      kubernetesAgent ??= new https.Agent({
        ca: readFileSync(`${SERVICE_ACCOUNT}/ca.crt`),
      });
      const token = readFileSync(`${SERVICE_ACCOUNT}/token`, "utf8").trim();

      const { body } = await getHttps(url, kubernetesAgent, {
        authorization: `Bearer ${token}`,
      });

      return body;
    }

    if (system === "nomad") {
      const { nomad } = config;
      const url = new URL(path, nomad.url);
      url.search = searchParams(params);
      const [ca, cert, key] = [nomad.caFile, nomad.certFile, nomad.keyFile].map(
        (file) => readFileSync(file, "utf8"),
      );
      const material = `${ca}\n${cert}\n${key}`;
      if (nomadTls?.material !== material) {
        nomadTls = { material, agent: new https.Agent({ ca, cert, key }) };
      }
      const token = readFileSync(nomad.tokenFile, "utf8").trim();

      const { body, headers } = await getHttps(url, nomadTls.agent, {
        "x-nomad-token": token,
      });

      return { data: body, next_token: headers["x-nomad-nexttoken"] ?? null };
    }

    const url = new URL(path, config[system]);
    url.search = searchParams(params);

    return getHttp(
      url,
      system === "loki" ? { "X-Scope-OrgID": config.lokiTenant } : {},
    );
  };
};
