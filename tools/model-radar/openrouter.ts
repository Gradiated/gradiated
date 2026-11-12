// Lists OpenRouter's models under each watched prefix. One request covers all
// of them: the API returns every model it serves. For new models only, it also
// looks up who serves each one and whether its weights are public yet.

import type { Model, Scan, Source } from "./model.ts";

type RouterModel = {
  id: string;
  name?: string;
  hugging_face_id?: string | null;
};

export class OpenRouterSource implements Source {
  static readonly API = "https://openrouter.ai/api/v1/models";
  static readonly HUB_API = "https://huggingface.co/api/models";
  /** Up to this many providers are named; more are counted. */
  static readonly PROVIDERS_SHOWN = 5;
  readonly name = "OpenRouter";

  readonly #fetch: typeof fetch;
  readonly #prefixes: readonly string[];

  constructor(send: typeof fetch, prefixes: readonly string[]) {
    this.#fetch = send;
    this.#prefixes = prefixes;
  }

  async scan(): Promise<Scan[]> {
    const response = await this.#fetch(OpenRouterSource.API, {
      signal: AbortSignal.timeout(30_000),
    });
    if (!response.ok)
      throw new Error(`OpenRouter listing failed (HTTP ${response.status}).`);
    const body = (await response.json()) as { data?: unknown };
    if (!Array.isArray(body.data))
      throw new Error("OpenRouter listing had no model list.");

    const byPrefix = new Map(
      this.#prefixes.map((prefix) => [prefix, [] as Model[]]),
    );
    for (const entry of body.data as RouterModel[]) {
      if (typeof entry?.id !== "string" || isVariant(entry.id)) continue;
      const prefix = entry.id.split("/")[0]!.toLowerCase();
      byPrefix.get(prefix)?.push(this.#model(prefix, entry));
    }
    return [...byPrefix].map(([prefix, models]) => ({
      scope: `openrouter:${prefix}`,
      owner: prefix,
      models,
    }));
  }

  /** Adds "served by …" and the weights' status. A lookup that fails is left out. */
  async describe(models: Model[]): Promise<Model[]> {
    return Promise.all(
      models.map(async (model) => {
        const [providers, weights] = await Promise.all([
          this.#providers(model),
          this.#weights(model),
        ]);
        const details = [...model.details];
        if (providers) details.push(`served by ${providers}`);
        if (weights) details.push(weights);
        return { ...model, details };
      }),
    );
  }

  #model(prefix: string, entry: RouterModel): Model {
    const model: Model = {
      id: entry.id,
      owner: prefix,
      name: entry.name || entry.id,
      url: `https://openrouter.ai/${entry.id}`,
      details: [],
    };
    if (entry.hugging_face_id && MODEL_ID.test(entry.hugging_face_id))
      model.weights = entry.hugging_face_id;
    return model;
  }

  /** "Tencent", "Moonshot AI, Together and Fireworks", or "Tencent and 5 others". */
  async #providers(model: Model): Promise<string | null> {
    if (!MODEL_ID.test(model.id)) return null;
    const body = await this.#json(
      `${OpenRouterSource.API}/${model.id}/endpoints`,
    );
    const endpoints = (body as { data?: { endpoints?: unknown } } | null)?.data
      ?.endpoints;
    if (!Array.isArray(endpoints)) return null;
    const names = [
      ...new Set(
        endpoints
          .map(
            (endpoint) =>
              (endpoint as { provider_name?: unknown }).provider_name,
          )
          .filter((name): name is string => typeof name === "string" && !!name),
      ),
    ];
    if (!names.length) return null;
    // The lab's own endpoint first: "MoonshotAI: Kimi" is served by "Moonshot AI".
    const lab = squash(model.name.split(":")[0]!);
    names.sort((a, b) => Number(squash(b) === lab) - Number(squash(a) === lab));
    if (names.length > OpenRouterSource.PROVIDERS_SHOWN) {
      const others = names.length - 1;
      return `${names[0]} and ${others} others`;
    }
    return names.length === 1
      ? names[0]!
      : `${names.slice(0, -1).join(", ")} and ${names.at(-1)}`;
  }

  /** Whether the Hugging Face model OpenRouter names is public yet. */
  async #weights(model: Model): Promise<string | null> {
    if (!model.weights) return null;
    const response = await this.#get(
      `${OpenRouterSource.HUB_API}/${model.weights}`,
    );
    if (!response) return null;
    if (response.ok) return "weights live";
    // Hugging Face answers 401 for a private model and 404 for one not made yet.
    if (response.status === 401 || response.status === 404)
      return "weights not public yet";
    return null;
  }

  async #json(url: string): Promise<unknown> {
    const response = await this.#get(url);
    if (!response?.ok) return null;
    return response.json().catch(() => null);
  }

  async #get(url: string): Promise<Response | null> {
    try {
      return await this.#fetch(url, { signal: AbortSignal.timeout(15_000) });
    } catch {
      return null;
    }
  }
}

/** "org/name": the only shape put into a URL path. */
const MODEL_ID = /^[\w.-]+\/[\w.-]+$/;

/** "Moonshot AI" and "MoonshotAI" both become "moonshotai". */
const squash = (name: string) => name.toLowerCase().replace(/[^a-z0-9]/g, "");

/**
 * The same model listed again: a ":free" or ":batch" tier, or a "~lab/...-latest"
 * alias. These would double the alerts and say nothing new.
 */
const isVariant = (id: string) => id.includes(":") || id.startsWith("~");
