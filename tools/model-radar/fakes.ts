// Test fakes. They are passed in where the real objects would be; nothing
// global is replaced.

import type {
  Model,
  Notifier,
  Alert,
  Scan,
  Source,
  SourceName,
} from "./model.ts";

export type Call = { url: string; init: RequestInit | undefined };

/**
 * A fetch that answers from a table of URL -> response maker and records each
 * call. Unknown URLs get a 404.
 */
export const fakeFetch = (routes: Record<string, () => Response>) => {
  const calls: Call[] = [];
  const send = (async (input: string | URL | Request, init?: RequestInit) => {
    const url = String(input);
    calls.push({ url, init });
    return routes[url]?.() ?? new Response("not found", { status: 404 });
  }) as typeof fetch;
  return { send, calls };
};

export const json =
  (body: unknown, headers: Record<string, string> = {}) =>
  () =>
    new Response(JSON.stringify(body), {
      headers: { "content-type": "application/json", ...headers },
    });

export const model = (id: string, owner = id.split("/")[0]!): Model => ({
  id,
  owner,
  name: id,
  url: `https://example.test/${id}`,
  details: [],
});

/** A source that returns whatever scans (or error) the test sets next. */
export class FakeSource implements Source {
  readonly name: SourceName;
  next: Scan[] | Error = [];

  constructor(name: SourceName) {
    this.name = name;
  }

  async scan(): Promise<Scan[]> {
    if (this.next instanceof Error) throw this.next;
    return this.next;
  }
}

/** A fake source that also describes models, recording what it was asked. */
export class DescribingSource extends FakeSource {
  readonly asked: string[][] = [];
  fail = false;

  async describe(models: Model[]): Promise<Model[]> {
    this.asked.push(models.map(({ id }) => id));
    if (this.fail) throw new Error("lookups down");
    return models.map((m) => ({ ...m, details: [...m.details, "described"] }));
  }
}

/** Keeps every batch of alerts it is sent, or fails if told to. */
export class RecordingNotifier implements Notifier {
  readonly sent: Alert[][] = [];
  fail = false;

  async send(alerts: Alert[]): Promise<void> {
    if (this.fail) throw new Error("notifier down");
    this.sent.push(alerts);
  }
}
