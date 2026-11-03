import { z } from "zod";
import { ControlServiceError } from "../errors.js";

const LayerCountSchema = z.number().int().min(1).max(4096);
const ExpertCountSchema = z.number().int().min(0).max(4096);
const ConfigurationSchema = z.object({
  num_hidden_layers: LayerCountSchema,
  n_routed_experts: ExpertCountSchema.nullable().optional(),
  num_local_experts: ExpertCountSchema.nullable().optional(),
});
const DocumentSchema = z
  .object({ text_config: z.unknown().optional() })
  .passthrough();
export type BaseModelConfiguration = {
  layerCount: number;
  expertCount: number;
};
const repository = z
  .string()
  .regex(/^[a-zA-Z0-9][a-zA-Z0-9._-]*\/[a-zA-Z0-9][a-zA-Z0-9._-]*$/);
const revision = z.string().regex(/^[0-9a-f]{40}$/);
const MAX_CONFIG_BYTES = 1024 * 1024;

export const readBaseModelConfiguration = async (
  modelRepository: string,
  modelRevision: string,
  fetcher: typeof fetch = fetch,
): Promise<BaseModelConfiguration> => {
  try {
    const repo = repository.parse(modelRepository);
    const commit = revision.parse(modelRevision);
    let url = new URL(
      `https://huggingface.co/${repo}/resolve/${commit}/config.json`,
    );
    const signal = AbortSignal.timeout(10_000);
    for (let redirects = 0; redirects <= 3; redirects++) {
      if (url.origin !== "https://huggingface.co")
        throw new Error("Invalid model configuration origin.");

      const response = await fetcher(url, { signal, redirect: "manual" });
      if ([301, 302, 303, 307, 308].includes(response.status)) {
        await response.body?.cancel();
        const location = response.headers.get("location");
        if (!location) throw new Error("Missing configuration redirect.");

        url = new URL(location, url);
        continue;
      }
      if (!response.ok || !response.body) {
        await response.body?.cancel();
        throw new Error("Base configuration is unavailable.");
      }

      const reader = response.body.getReader();
      const chunks: Uint8Array[] = [];
      let size = 0;
      try {
        if (Number(response.headers.get("content-length")) > MAX_CONFIG_BYTES)
          throw new Error("Oversized configuration.");

        for (;;) {
          const chunk = await reader.read();
          if (chunk.done) break;

          size += chunk.value.length;
          if (size > MAX_CONFIG_BYTES)
            throw new Error("Oversized configuration.");

          chunks.push(chunk.value);
        }
      } finally {
        await reader.cancel();
      }
      const document = DocumentSchema.parse(
        JSON.parse(Buffer.concat(chunks, size).toString("utf8")),
      );
      const config = ConfigurationSchema.parse(
        document.text_config ?? document,
      );
      return {
        layerCount: config.num_hidden_layers,
        expertCount:
          config.n_routed_experts === undefined
            ? (config.num_local_experts ?? 0)
            : (config.n_routed_experts ?? 0),
      };
    }
    throw new Error("Too many configuration redirects.");
  } catch {
    throw new ControlServiceError(
      "unavailable",
      "The exact base checkpoint configuration could not be loaded. Check the base model and revision, then retry.",
    );
  }
};
