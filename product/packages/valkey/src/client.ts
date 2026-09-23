import { defaultProvider } from "@aws-sdk/credential-provider-node";
import { formatUrl } from "@aws-sdk/util-format-url";
import { Hash } from "@smithy/hash-node";
import { HttpRequest } from "@smithy/protocol-http";
import { SignatureV4 } from "@smithy/signature-v4";
import { createClient, type RedisClientType } from "redis";

export type ValkeyEnvironment = {
  VALKEY_IAM_CACHE_NAME?: string | undefined;
  VALKEY_IAM_REGION?: string | undefined;
  VALKEY_IAM_USER?: string | undefined;
  VALKEY_URL: string;
};

type IamSettings = {
  cacheName: string;
  region: string;
  user: string;
};

// ElastiCache IAM tokens are valid for at most 15 minutes.
const IAM_TOKEN_TTL_SECONDS = 900;

const IAM_VARIABLES = [
  "VALKEY_IAM_CACHE_NAME",
  "VALKEY_IAM_REGION",
  "VALKEY_IAM_USER",
] as const;

type ValkeyConnection =
  | { kind: "url"; url: string }
  | { kind: "iam"; endpoint: URL; iam: IamSettings };

const resolveConnection = (
  environment: ValkeyEnvironment,
): ValkeyConnection => {
  const {
    VALKEY_IAM_CACHE_NAME: cacheName,
    VALKEY_IAM_REGION: region,
    VALKEY_IAM_USER: user,
  } = environment;

  if (!cacheName && !region && !user) {
    return { kind: "url", url: environment.VALKEY_URL };
  }

  if (!cacheName || !region || !user) {
    const missing = IAM_VARIABLES.filter((name) => !environment[name]);

    throw new Error(
      `Valkey IAM settings are incomplete; missing ${missing.join(", ")}`,
    );
  }

  const endpoint = new URL(environment.VALKEY_URL);

  if (endpoint.protocol !== "rediss:") {
    throw new Error("Valkey IAM authentication requires a rediss:// URL");
  }

  return { kind: "iam", endpoint, iam: { cacheName, region, user } };
};

const createIamAuthToken = async (
  signer: SignatureV4,
  { cacheName, user }: IamSettings,
): Promise<string> => {
  const request = new HttpRequest({
    method: "GET",
    protocol: "http:",
    hostname: cacheName,
    path: "/",
    headers: { host: cacheName },
    query: {
      Action: "connect",
      ResourceType: "ServerlessCache",
      User: user,
    },
  });
  const presigned = await signer.presign(request, {
    expiresIn: IAM_TOKEN_TTL_SECONDS,
  });

  return formatUrl(presigned).replace(/^http:\/\//, "");
};

export const createValkeyClient = (
  environment: ValkeyEnvironment,
): RedisClientType => {
  const connection = resolveConnection(environment);

  if (connection.kind === "url") {
    return createClient({ url: connection.url });
  }

  const { endpoint, iam } = connection;
  const signer = new SignatureV4({
    credentials: defaultProvider(),
    region: iam.region,
    service: "elasticache",
    sha256: Hash.bind(null, "sha256"),
  });

  return createClient({
    socket: {
      host: endpoint.hostname,
      port: Number(endpoint.port || 6379),
      tls: true,
    },
    credentialsProvider: {
      type: "async-credentials-provider",
      credentials: async () => ({
        username: iam.user,
        password: await createIamAuthToken(signer, iam),
      }),
    },
  });
};
