import { createInstanceService } from "@gradiated/control";
import { z } from "@hono/zod-openapi";

import { requiredEnv, withControlDatabase } from "./catalog-operation.js";
import { hostImage, readSecret } from "./instances/aws.js";
import {
  hostBootstrapEnvironment,
  issueNomadClientCertificate,
  nomadNodeIdentity,
  nodeName,
} from "./instances/host-bootstrap.js";
import {
  nomadNodeReaderFromEnvironment,
  waitForNomadNode,
} from "./instances/nomad-node.js";
import type { InstanceProvider } from "./instances/provider.js";
import { createRunPodProvider } from "./instances/runpod.js";

const NODE_READY_TIMEOUT_MS = 30 * 60 * 1000;

const providers: Record<string, () => InstanceProvider> = {
  runpod: () => createRunPodProvider({ apiKey: requiredEnv("RUNPOD_API_KEY") }),
};

const [providerName = "", providerInstanceId] = process.argv.slice(2);
const createProvider = providers[providerName];
if (!createProvider || !providerInstanceId) {
  throw new Error(
    `Usage: instance:register <${Object.keys(providers).join("|")}> <provider-instance-id>`,
  );
}

const readNode = await nomadNodeReaderFromEnvironment();
const provider = createProvider();
const image = await hostImage(requiredEnv("NOMAD_BASE_IMAGE"));
const [authority, artifact] = await Promise.all([
  readSecret(
    "gradiated/prod/nomad/ca",
    z.object({ "ca.pem": z.string(), "ca-key.pem": z.string() }),
  ),
  readSecret(
    "gradiated/prod/nomad/host-runtime-reader",
    z.object({ AccessKeyId: z.string(), SecretAccessKey: z.string() }),
  ),
]);
const instance = await provider.describe(providerInstanceId);
const tls = await issueNomadClientCertificate({
  certificate: authority["ca.pem"],
  privateKey: authority["ca-key.pem"],
});

const record = await withControlDatabase(({ database }) =>
  createInstanceService(database).register(instance),
);
const identity = nomadNodeIdentity(
  record.nomadNodeId,
  await provider.environment(providerInstanceId),
);
const name = nodeName(instance.provider, instance.providerInstanceId);
console.log(
  `Recorded instance ${record.id} (${record.sku}); registering Nomad node ${name}`,
);

await provider.bootstrap(
  instance,
  image,
  hostBootstrapEnvironment({
    instanceId: record.id,
    nodeName: name,
    ...identity,
    ca: authority["ca.pem"],
    ...tls,
    artifact: {
      accessKeyId: artifact.AccessKeyId,
      secretAccessKey: artifact.SecretAccessKey,
    },
  }),
);
console.log(
  `Booting ${image.reference}; waiting for Nomad node ${identity.nomadNodeId}`,
);

await waitForNomadNode(readNode, {
  nomadNodeId: identity.nomadNodeId,
  instanceId: record.id,
  timeoutMs: NODE_READY_TIMEOUT_MS,
});
await withControlDatabase(({ database }) =>
  createInstanceService(database).bindNomadNode(
    record.id,
    identity.nomadNodeId,
  ),
);
console.log(`Nomad node ${name} is ready; Nomad now places jobs on it`);
