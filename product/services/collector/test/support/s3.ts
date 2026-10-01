import { HeadBucketCommand, S3Client } from "@aws-sdk/client-s3";
import { inject } from "vitest";
import type { TestProject } from "vitest/node";

import { LocalDocker } from "../../../gateway/test/integration/stack/docker.js";
import { eventually } from "../../../gateway/test/integration/eventually.js";
import { freePort } from "../../../gateway/test/integration/ports.js";

export const bucket = "integration-contents";
export const credentials = {
  accessKeyId: "integration",
  secretAccessKey: "integration-secret",
};

declare module "vitest" {
  interface ProvidedContext {
    collectorS3Url: string;
  }
}

const clientAt = (endpoint: string) =>
  new S3Client({
    endpoint,
    region: "us-east-1",
    credentials,
    forcePathStyle: true,
    maxAttempts: 1,
  });
export const connectS3 = () => clientAt(inject("collectorS3Url"));

export default async (project: TestProject) => {
  const docker = await LocalDocker.connect(
    `collector-storage-${crypto.randomUUID()}`,
  );
  const port = await freePort();
  const url = `http://127.0.0.1:${port}`;
  const client = clientAt(url);

  try {
    await docker.run("s3", [
      "--publish",
      `127.0.0.1:${port}:8333`,
      "-e",
      `AWS_ACCESS_KEY_ID=${credentials.accessKeyId}`,
      "-e",
      `AWS_SECRET_ACCESS_KEY=${credentials.secretAccessKey}`,
      "-e",
      `S3_BUCKET=${bucket}`,
      "chrislusf/seaweedfs:4.47",
      "mini",
      "-dir=/data",
      "-ip=127.0.0.1",
      "-ip.bind=0.0.0.0",
    ]);
    await eventually(
      async () => {
        await client.send(new HeadBucketCommand({ Bucket: bucket }));
        return true;
      },
      30_000,
      "S3 bucket readiness",
    );
    project.provide("collectorS3Url", url);
  } catch (error) {
    await docker.removeOwned();
    throw error;
  } finally {
    client.destroy();
  }

  return () => docker.removeOwned();
};
