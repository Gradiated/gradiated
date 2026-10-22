import { readFile } from "node:fs/promises";
import { z } from "zod";

// What every host should run. A host on another image is re-imaged, which
// installs the bundle; a host on this image gets the bundle in place.
// RunPod's ECR delegation pulls only by tag, so the image is an input-hash tag
// and imageDigest records the build it names.
export const pinsSchema = z.strictObject({
  image: z
    .string()
    .regex(
      /^\d{12}\.dkr\.ecr\.[a-z0-9-]+\.amazonaws\.com\/[a-z0-9/._-]+:gpu-base-inputs-[0-9a-f]{64}$/,
    ),
  imageDigest: z.string().regex(/^sha256:[0-9a-f]{64}$/),
  hostBundle: z.strictObject({
    sha256: z.string().regex(/^[0-9a-f]{64}$/),
    baseId: z.string().regex(/^[A-Za-z0-9._-]{1,64}$/),
  }),
});

export type Pins = z.infer<typeof pinsSchema>;

export const readPins = async (file: string) =>
  pinsSchema.parse(JSON.parse(await readFile(file, "utf8")));
