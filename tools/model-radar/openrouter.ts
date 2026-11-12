// Lists OpenRouter's models under each watched prefix. One request covers all
// of them: the API returns every model it serves.

import type { Model, Scan, Source } from "./model.ts";

type RouterModel = {
  id: string;
  name?: string;
  context_length?: number | null;
  hugging_face_id?: string | null;
};

export class OpenRouterSource implements Source {
  static readonly API = "https://openrouter.ai/api/v1/models";
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

  #model(prefix: string, entry: RouterModel): Model {
    const details: string[] = [];
    if (entry.context_length)
      details.push(`${contextSize(entry.context_length)} context`);
    if (entry.hugging_face_id)
      details.push(`weights: ${entry.hugging_face_id}`);
    return {
      id: entry.id,
      owner: prefix,
      name: entry.name || entry.id,
      url: `https://openrouter.ai/${entry.id}`,
      details,
    };
  }
}

/**
 * The same model listed again: a ":free" or ":batch" tier, or a "~lab/...-latest"
 * alias. These would double the alerts and say nothing new.
 */
const isVariant = (id: string) => id.includes(":") || id.startsWith("~");

/** 262144 -> "262k", 1048576 -> "1M", as OpenRouter's own pages show them. */
const contextSize = (tokens: number) =>
  tokens >= 999_500
    ? `${Number((tokens / 1_000_000).toFixed(1))}M`
    : `${Math.round(tokens / 1000)}k`;
