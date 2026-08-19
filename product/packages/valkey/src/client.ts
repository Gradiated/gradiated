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

const createIamAuthToken = async (
  cacheName: string,
  region: string,
  user: string,
): Promise<string> => {
  const signer = new SignatureV4({
    credentials: defaultProvider(),
    region,
    service: "elasticache",
    sha256: Hash.bind(null, "sha256"),
  });
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

  return formatUrl(await signer.presign(request, { expiresIn: 900 })).replace(
    "http://",
    "",
  );
};

export const createValkeyClient = (
  environment: ValkeyEnvironment,
): RedisClientType => {
  if (
    !environment.VALKEY_IAM_CACHE_NAME ||
    !environment.VALKEY_IAM_REGION ||
    !environment.VALKEY_IAM_USER
  ) {
    return createClient({ url: environment.VALKEY_URL });
  }

  const endpoint = new URL(environment.VALKEY_URL);
  const cacheName = environment.VALKEY_IAM_CACHE_NAME;
  const region = environment.VALKEY_IAM_REGION;
  const user = environment.VALKEY_IAM_USER;
  const socket =
    endpoint.protocol === "rediss:"
      ? {
          host: endpoint.hostname,
          port: Number(endpoint.port || 6379),
          tls: true as const,
        }
      : { host: endpoint.hostname, port: Number(endpoint.port || 6379) };

  return createClient({
    socket,
    credentialsProvider: {
      type: "async-credentials-provider",
      credentials: async () => ({
        username: user,
        password: await createIamAuthToken(cacheName, region, user),
      }),
    },
  });
};
