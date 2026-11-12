// Lists every public model repo under each watched Hugging Face org.
//
// Every repo, not just the newest: labs often create a repo privately and make
// it public weeks later, and it keeps its original creation date. Comparing
// the full list with the IDs seen last time catches the moment it goes public.

import type { Model, Scan, Source } from "./model.ts";

type HubModel = { id: string; pipeline_tag?: string };

export class HuggingFaceSource implements Source {
  static readonly API = "https://huggingface.co/api/models";
  readonly name = "Hugging Face";

  readonly #fetch: typeof fetch;
  readonly #orgs: readonly string[];

  constructor(send: typeof fetch, orgs: readonly string[]) {
    this.#fetch = send;
    this.#orgs = orgs;
  }

  async scan(): Promise<Scan[]> {
    const scans: Scan[] = [];
    for (const org of this.#orgs) {
      const repos = await this.#list(org);
      scans.push({
        scope: `huggingface:${org}`,
        owner: org,
        models: repos.map((repo) => this.#model(org, repo)),
      });
    }
    return scans;
  }

  /** Follows the API's Link: rel="next" pages until the org's list ends. */
  async #list(org: string): Promise<HubModel[]> {
    const repos: HubModel[] = [];
    let url: string | null =
      `${HuggingFaceSource.API}?author=${encodeURIComponent(org)}&limit=1000`;
    while (url) {
      const response = await this.#fetch(url, {
        signal: AbortSignal.timeout(30_000),
      });
      if (!response.ok) {
        throw new Error(
          `Hugging Face listing for ${org} failed (HTTP ${response.status}).`,
        );
      }
      const page: unknown = await response.json();
      if (!Array.isArray(page))
        throw new Error(`Hugging Face listing for ${org} was not a list.`);
      repos.push(...(page as HubModel[]));
      url = nextPage(response.headers.get("link"));
    }
    return repos;
  }

  #model(org: string, repo: HubModel): Model {
    return {
      id: repo.id,
      owner: org,
      name: repo.id,
      url: `https://huggingface.co/${repo.id}`,
      details: repo.pipeline_tag ? [repo.pipeline_tag] : [],
    };
  }
}

/** The next page's URL, only if it is another page of the same API. */
const nextPage = (link: string | null): string | null => {
  const next = link?.match(/<([^>]+)>;\s*rel="next"/)?.[1];
  return next?.startsWith(`${HuggingFaceSource.API}?`) ? next : null;
};
