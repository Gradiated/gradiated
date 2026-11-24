import { readFile } from "node:fs/promises";
import { AwsGpuBaseImageSchema, gpuBaseRepository } from "@gradiated/gpu-hosts";
import { z } from "zod";

import { isAws, type GpuHost } from "./hosts.js";

// What every host should run. A host on another image is re-imaged, which
// installs the bundle; a host on this image gets the bundle in place.
// RunPod's ECR delegation pulls only by tag, so the image is an input-hash tag
// and imageDigest records the build it names.
export const pinsSchema = z
  .strictObject({
    image: z
      .string()
      .regex(
        /^\d{12}\.dkr\.ecr\.[a-z0-9-]+\.amazonaws\.com\/[a-z0-9/._-]+:gpu-base-inputs-[0-9a-f]{64}$/,
      ),
    imageDigest: z.string().regex(/^sha256:[0-9a-f]{64}$/),
    // What AWS hosts run instead, while image predates AWS support; a tag or a
    // digest in the same repository.
    awsImage: AwsGpuBaseImageSchema.optional(),
    hostBundle: z.strictObject({
      sha256: z.string().regex(/^[0-9a-f]{64}$/),
      baseId: z.string().regex(/^[A-Za-z0-9._-]{1,64}$/),
    }),
  })
  .refine(
    ({ image, awsImage }) =>
      !awsImage || gpuBaseRepository(awsImage) === gpuBaseRepository(image),
    { message: "awsImage must be in image's repository", path: ["awsImage"] },
  );

export type Pins = z.infer<typeof pinsSchema>;

export const pinnedImage = (pins: Pins, host: GpuHost) =>
  isAws(host) ? (pins.awsImage ?? pins.image) : pins.image;

export const readPins = async (file: string) =>
  pinsSchema.parse(JSON.parse(await readFile(file, "utf8")));
