import {
  isManaged,
  MANAGED_TAG,
  replacementSettled,
  type AwsGpuClient,
  type Ec2Instance,
} from "./aws.js";

// Why the GPU fleet may not change this instance, or undefined if it may.
export const ec2Refusal = (instance: Ec2Instance, accountId: string) => {
  if (!isManaged(instance))
    return `EC2 instance ${instance.id} is not tagged ${MANAGED_TAG.key}=${MANAGED_TAG.value}, so the GPU fleet cannot manage it`;
  if (instance.accountId !== accountId)
    return `EC2 instance ${instance.id} is in account ${instance.accountId}, not ${accountId}`;
};

export const managedInstance = async (
  client: AwsGpuClient,
  instanceId: string,
  accountId = client.accountId,
) => {
  const instance = await client.instance(instanceId);
  const refusal = ec2Refusal(instance, accountId);
  if (refusal) throw new Error(refusal);

  return instance;
};

// Run before a root volume is replaced. Anything on the old root, such as a
// lease holder's privileged container, could read a bootstrap secret or copy
// the credentials of a profile attached now, so neither is left. A secret an
// earlier attempt left would also reach the new root's launcher first.
// Returns whether the bootstrap profile had to be removed.
export const prepareReplacement = async (
  client: AwsGpuClient,
  instance: Ec2Instance,
) => {
  const { id } = instance;
  await client.deleteBootstrapSecret(id);
  if (await client.bootstrapSecretReadable(id))
    throw new Error(
      `The bootstrap secret of ${id} is still readable after its deletion; the root volume was not replaced`,
    );

  const { removed, kept } = await client.disassociateBootstrapProfile(id);
  const otherProfile =
    kept[0] ?? (removed === 0 ? instance.instanceProfileArn : undefined);
  if (otherProfile)
    throw new Error(
      `EC2 instance ${id} has instance profile ${otherProfile}, not the bootstrap profile; remove it before re-imaging the instance`,
    );

  return removed > 0;
};

// Without an image EC2 restores the instance's original launch AMI, so a pin
// change would never reach an existing host.
export const replaceWithTemplateImage = async (
  client: AwsGpuClient,
  instanceId: string,
  clientToken: string,
) => {
  const imageId = await client.launchTemplateImage();
  const task = await client.replaceRootVolume(instanceId, clientToken, imageId);
  return { imageId, task };
};

// A task still in flight can swap the root volume under a launcher that has
// just read its key, so no key is written until every task has ended.
export const replacementProgress = async (
  client: AwsGpuClient,
  instanceId: string,
) => {
  const tasks = await client.replaceRootVolumeTasks(instanceId);
  return {
    inFlight: tasks.filter((task) => !replacementSettled(task)),
    last: tasks.at(-1),
  };
};

// What a host still holds of its bootstrap access after trying to remove both
// its secret and its bootstrap profile, and any other profile it keeps.
export const removeBootstrapAccess = async (
  client: AwsGpuClient,
  instanceId: string,
) => {
  const left: string[] = [];
  let kept: string[] = [];
  await client.deleteBootstrapSecret(instanceId).catch(() => {
    left.push("its bootstrap secret");
  });
  await client
    .disassociateBootstrapProfile(instanceId)
    .then((result) => {
      kept = result.kept;
    })
    .catch(() => {
      left.push("its instance profile");
    });
  return { left, kept };
};
