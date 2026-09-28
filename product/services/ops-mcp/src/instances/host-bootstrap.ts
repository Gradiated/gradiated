import { randomUUID } from "node:crypto";

export interface ArtifactCredentials {
  readonly accessKeyId: string;
  readonly secretAccessKey: string;
}

export interface HostBootstrap {
  readonly instanceId: string;
  readonly nodeName: string;
  readonly nomadNodeId: string;
  readonly nomadNodeSecret: string;
  readonly ca: string;
  readonly certificate: string;
  readonly privateKey: string;
  readonly artifact: ArtifactCredentials;
}

export const nodeName = (provider: string, providerInstanceId: string) => {
  const name = `${provider}-${providerInstanceId}`.toLowerCase();
  if (!/^[a-z0-9-]{1,63}$/.test(name)) {
    throw new Error(`${name} is not a valid Nomad node name`);
  }

  return name;
};

// Nomad refuses a known node id presented with a different secret, so a returning
// node reuses both from the bootstrap the machine already carries.
export const nomadNodeIdentity = (
  boundNodeId: string | null,
  environment: Readonly<Record<string, string>>,
) => {
  const secret = environment.GRADIATED_NOMAD_NODE_SECRET;
  if (
    boundNodeId &&
    environment.GRADIATED_NOMAD_NODE_ID === boundNodeId &&
    secret
  ) {
    return { nomadNodeId: boundNodeId, nomadNodeSecret: secret };
  }

  return { nomadNodeId: randomUUID(), nomadNodeSecret: randomUUID() };
};

const base64 = (value: string) => Buffer.from(value).toString("base64");

export const hostBootstrapEnvironment = (
  host: HostBootstrap,
): Record<string, string> => {
  const { accessKeyId, secretAccessKey } = host.artifact;
  // The host sources this file, so accept only what AWS issues.
  if (!/^[A-Z0-9]{16,128}$/.test(accessKeyId)) {
    throw new Error("Artifact access key id has an unexpected format");
  }
  if (!/^[A-Za-z0-9/+]{40}$/.test(secretAccessKey)) {
    throw new Error("Artifact secret access key has an unexpected format");
  }

  return {
    GRADIATED_INSTANCE_ID: host.instanceId,
    GRADIATED_NODE_NAME: host.nodeName,
    GRADIATED_NOMAD_NODE_ID: host.nomadNodeId,
    GRADIATED_NOMAD_NODE_SECRET: host.nomadNodeSecret,
    GRADIATED_NOMAD_CA: base64(host.ca),
    GRADIATED_NOMAD_CERT: base64(host.certificate),
    GRADIATED_NOMAD_KEY: base64(host.privateKey),
    GRADIATED_ARTIFACT_ENV: base64(
      `AWS_ACCESS_KEY_ID=${accessKeyId}\nAWS_SECRET_ACCESS_KEY=${secretAccessKey}\n`,
    ),
  };
};

const SERVING_TOKEN = /^[A-Za-z0-9_-]{32,256}$/;

export const servingEnvironment = (tokens: {
  readonly runtimeAccess: string;
  readonly deploymentStatus: string;
}): Record<string, string> => {
  // The host writes these into nginx configuration.
  for (const token of [tokens.runtimeAccess, tokens.deploymentStatus]) {
    if (!SERVING_TOKEN.test(token)) {
      throw new Error(
        "Serving tokens must contain 32-256 base64url characters",
      );
    }
  }

  return {
    GRADIATED_RUNTIME_ACCESS_TOKEN: tokens.runtimeAccess,
    GRADIATED_DEPLOYMENT_STATUS_TOKEN: tokens.deploymentStatus,
  };
};
