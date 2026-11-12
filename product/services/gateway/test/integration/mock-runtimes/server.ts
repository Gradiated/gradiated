// Loopback-only, bounded HTTP fault server with out-of-band test controls.
//
// Scenario selection never uses customer request fields. Requests, assertions and
// events are accessible only to the owning test process, not via an admin endpoint.
import {
  createServer,
  type IncomingHttpHeaders,
  type IncomingMessage,
  type Server,
  type ServerResponse,
} from "node:http";
import type { Socket } from "node:net";

import { deferred, within, type Deferred } from "../eventually.js";
import { object, type JsonObject } from "../json.js";
import { profile as kevProfile } from "./kev.js";
import { profile as openRouterProfile } from "./openrouter.js";
import type { RuntimeProfile, StreamEvents } from "./profile.js";
import { profile as vllmProfile } from "./vllm.js";

const BODY_LIMIT = 32_000_000;
const GATE_TIMEOUT_MS = 8000;
const STALL_LIMIT_MS = 5000;
const DISCONNECT_CODES = new Set([
  "EPIPE",
  "ECONNRESET",
  "ERR_STREAM_DESTROYED",
  "ERR_STREAM_WRITE_AFTER_END",
]);

class UpstreamRejection extends Error {
  constructor(
    readonly status: number,
    readonly body: Buffer,
  ) {
    super(`real runtime rejected with HTTP ${status}`);
  }
}
const PROFILES: Record<ProfileKind, RuntimeProfile> = {
  kev: kevProfile,
  vllm: vllmProfile,
  openrouter: openRouterProfile,
};

export const RUNTIME_KINDS = ["kev", "vllm"] as const;

export type RuntimeKind = (typeof RUNTIME_KINDS)[number];

/** OpenRouter is external capacity rather than a runtime a case deploys. */
export type ProfileKind = RuntimeKind | "openrouter";

export const isRuntimeKind = (value: string): value is RuntimeKind =>
  RUNTIME_KINDS.some((kind) => kind === value);

export type Fault =
  | "ok"
  | "disconnect"
  | "invalid_json"
  | "oversize"
  | "missing_usage"
  | "missing_done"
  | "partial_disconnect"
  | "stall"
  | "wrong_content_type";

const BODY_FAULTS: ReadonlySet<Fault> = new Set(["invalid_json", "oversize"]);
const STREAM_FAULTS: ReadonlySet<Fault> = new Set([
  "missing_usage",
  "missing_done",
  "partial_disconnect",
  "stall",
  "wrong_content_type",
]);

// Mutations deliberately break the wire schema, so they see plain JSON rather
// than the runtime's own types.
export interface PlanOptions {
  fault?: Fault;
  status?: number;
  cached?: number;
  fragment?: number;
  gate?: Deferred;
  mutateBody?: (body: JsonObject) => void;
  mutateEvents?: (events: StreamEvents) => void;
  errorUsage?: JsonObject;
}

export interface Plan {
  readonly fault: Fault;
  readonly status: number;
  readonly cached: number;
  readonly fragment: number;
  readonly gate: Deferred | undefined;
  readonly entered: Deferred;
  readonly mutateBody: ((body: JsonObject) => void) | undefined;
  readonly mutateEvents: ((events: StreamEvents) => void) | undefined;
  readonly errorUsage: JsonObject | undefined;
}

const plan = (options: PlanOptions = {}): Plan => ({
  fault: options.fault ?? "ok",
  status: options.status ?? 200,
  cached: options.cached ?? 0,
  fragment: options.fragment ?? 0,
  gate: options.gate,
  entered: deferred(),
  mutateBody: options.mutateBody,
  mutateEvents: options.mutateEvents,
  errorUsage: options.errorUsage,
});

/**
 * Where a runtime's successful responses come from. `synthetic` generates them from
 * the wire profile, which is deterministic and supports every fault. `proxy` forwards
 * to a real inference server that serves only `model`, so the gateway sees real bytes;
 * calls are still recorded and faults still apply, but token counts are whatever the
 * real model produced.
 */
export type Upstream =
  | { kind: "synthetic" }
  | {
      kind: "proxy";
      baseUrl: string;
      model: string;
      authorization?: string;
    };

export const SYNTHETIC: Upstream = { kind: "synthetic" };

/**
 * Names each planned setting the response to this request would ignore, so a
 * plan that does not fit the request fails the test instead of serving success.
 */
const ignoredSettings = (
  plan: Plan,
  stream: boolean,
  upstream: Upstream,
): string[] => {
  const disconnects = plan.fault === "disconnect";
  const answers = !disconnects && plan.status === 200;
  const synthesizes = answers && upstream.kind === "synthetic";
  const faultApplies =
    disconnects ||
    (stream
      ? synthesizes && STREAM_FAULTS.has(plan.fault)
      : answers && BODY_FAULTS.has(plan.fault));
  const settings: [name: string, set: boolean, used: boolean][] = [
    [`fault ${plan.fault}`, plan.fault !== "ok", faultApplies],
    [`status ${plan.status}`, plan.status !== 200, !disconnects],
    ["errorUsage", plan.errorUsage !== undefined, !disconnects && !answers],
    ["cached", plan.cached !== 0, synthesizes],
    ["fragment", plan.fragment !== 0, answers && stream],
    ["mutateBody", plan.mutateBody !== undefined, answers && !stream],
    ["mutateEvents", plan.mutateEvents !== undefined, synthesizes && stream],
  ];

  return settings.filter(([, set, used]) => set && !used).map(([name]) => name);
};

interface Accepted {
  readonly body: JsonObject;
  readonly plan: Plan;
}

export class Runtime {
  readonly calls: JsonObject[] = [];
  resolutionStatus = 200;
  readonly headers: IncomingHttpHeaders[] = [];
  readonly errors: string[] = [];
  upstreamCancelled = 0;
  upstreamResponses = 0;
  readonly url: string;

  readonly #profile: RuntimeProfile;
  readonly #model: string;
  readonly #token: string;
  readonly #upstream: Upstream;
  readonly #plans: Plan[] = [];
  readonly #server: Server;
  readonly #sockets = new Set<Socket>();
  readonly #stopping = deferred();

  private constructor(
    kind: ProfileKind,
    model: string,
    token: string,
    upstream: Upstream,
    server: Server,
  ) {
    this.#profile = PROFILES[kind];
    this.#model = model;
    this.#token = token;
    this.#upstream = upstream;
    this.#server = server;

    const address = server.address();
    if (address === null || typeof address === "string") {
      throw new Error("the mock runtime is not listening on a TCP port");
    }
    this.url = `http://127.0.0.1:${address.port}`;
  }

  static async start(
    kind: ProfileKind,
    model: string,
    token: string,
    upstream: Upstream = SYNTHETIC,
  ): Promise<Runtime> {
    const server = createServer();
    await new Promise<void>((resolve) =>
      server.listen(0, "127.0.0.1", resolve),
    );
    const runtime = new Runtime(kind, model, token, upstream, server);
    server.on("connection", (socket) => {
      runtime.#sockets.add(socket);
      socket.on("close", () => runtime.#sockets.delete(socket));
    });
    server.on("request", (request, response) => {
      void runtime.#handle(request, response);
    });
    return runtime;
  }

  enqueue(options: PlanOptions = {}): Plan {
    const queued = plan(options);
    this.#plans.push(queued);

    return queued;
  }

  async close(): Promise<void> {
    this.#stopping.resolve();
    for (const socket of this.#sockets) socket.destroy();
    await new Promise<void>((resolve) => this.#server.close(() => resolve()));
  }

  async #handle(
    request: IncomingMessage,
    response: ServerResponse,
  ): Promise<void> {
    if (request.method === "GET") {
      return reply(
        response,
        request.url === "/health" ? 200 : 404,
        Buffer.from("{}"),
      );
    }

    try {
      const accepted = await this.#accept(request, response);
      if (accepted) await this.#respond(request, response, accepted);
    } catch (error) {
      if (error instanceof UpstreamRejection) {
        return reply(response, error.status, error.body);
      }

      if (isDisconnect(error)) return; // Deliberate cancellation and fault tests close sockets.

      this.errors.push(error instanceof Error ? error.message : String(error));
      try {
        reply(
          response,
          500,
          Buffer.from('{"error":{"message":"mock contract violation"}}'),
        );
      } catch {
        // The peer is already gone.
      }
    }
  }

  /** Validates and records a request, then waits for its plan's gate. */
  async #accept(
    request: IncomingMessage,
    response: ServerResponse,
  ): Promise<Accepted | undefined> {
    if (request.headers.authorization !== `Bearer ${this.#token}`) {
      reply(response, 401, Buffer.from('{"error":{"message":"unauthorized"}}'));
      return undefined;
    }

    if (request.url !== this.#profile.path) {
      throw new Error(`unexpected path ${request.url}`);
    }

    const body = object(JSON.parse(await readBody(request)));
    const privateModel =
      typeof body.model === "string" && /^[a-f0-9-]{36}\/.+$/.test(body.model);
    this.#profile.validate(
      body,
      privateModel ? (body.model as string) : this.#model,
    );
    this.calls.push(body);
    this.headers.push(request.headers);
    if (privateModel && this.resolutionStatus !== 200) {
      reply(
        response,
        this.resolutionStatus,
        Buffer.from('{"error":{"message":"adapter resolution unavailable"}}'),
      );
      return undefined;
    }

    const current = this.#plans.shift() ?? plan();
    current.entered.resolve();

    if (
      current.gate &&
      !(await within(current.gate.promise, GATE_TIMEOUT_MS)).settled
    ) {
      if (!this.#stopping.settled()) {
        throw new Error("test did not release runtime gate");
      }

      return undefined;
    }

    return { body, plan: current };
  }

  async #respond(
    request: IncomingMessage,
    response: ServerResponse,
    { body, plan }: Accepted,
  ): Promise<void> {
    const ignored = ignoredSettings(plan, Boolean(body.stream), this.#upstream);
    if (ignored.length > 0) {
      throw new Error(`the plan does not apply: ${ignored.join(", ")}`);
    }

    if (plan.fault === "disconnect") return void request.socket.destroy();

    if (plan.status !== 200) return replyFailure(response, plan);

    const upstream = this.#upstream;
    if (body.stream) {
      return upstream.kind === "proxy"
        ? await this.#relay(upstream, response, body, plan)
        : this.#stream(response, body, plan);
    }

    const result =
      upstream.kind === "proxy"
        ? await this.#forward(upstream, body)
        : this.#profile.response(body, plan.cached);
    plan.mutateBody?.(result);

    if (plan.fault === "invalid_json") {
      return reply(
        response,
        200,
        Buffer.from("not json PRIVATE_RUNTIME_DETAIL"),
      );
    }

    if (plan.fault === "oversize") {
      // Declare a body far larger than the gateway's cap, then deliver nothing.
      response.writeHead(200, {
        "Content-Type": "application/json",
        "Content-Length": "8000001",
      });
      response.flushHeaders();
      return void response.socket?.destroy();
    }

    reply(response, 200, Buffer.from(JSON.stringify(result)));
  }

  async #forward(
    upstream: Extract<Upstream, { kind: "proxy" }>,
    body: JsonObject,
  ): Promise<JsonObject> {
    const response = await fetch(`${upstream.baseUrl}${this.#profile.path}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(upstream.authorization
          ? { Authorization: upstream.authorization }
          : {}),
      },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(120_000),
    });
    const text = await response.text();
    if (!response.ok) {
      throw new UpstreamRejection(response.status, Buffer.from(text));
    }
    return object(JSON.parse(text));
  }

  /** Relay the real runtime's SSE body byte for byte, so framing is the runtime's own. */
  async #relay(
    upstream: Extract<Upstream, { kind: "proxy" }>,
    response: ServerResponse,
    body: JsonObject,
    plan: Plan,
  ): Promise<void> {
    const disconnected = new AbortController();
    const abort = (): void => {
      if (!response.writableEnded) {
        this.upstreamCancelled += 1;
        disconnected.abort();
      }
    };
    response.once("close", abort);

    try {
      const source = await fetch(`${upstream.baseUrl}${this.#profile.path}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(upstream.authorization
            ? { Authorization: upstream.authorization }
            : {}),
        },
        body: JSON.stringify(body),
        signal: AbortSignal.any([
          disconnected.signal,
          AbortSignal.timeout(120_000),
        ]),
      });
      this.upstreamResponses += 1;
      if (!source.ok) {
        return reply(
          response,
          source.status,
          Buffer.from(await source.arrayBuffer()),
        );
      }
      if (!source.body) {
        throw new Error("real runtime returned no stream body");
      }

      response.writeHead(200, {
        "Content-Type":
          source.headers.get("content-type") ?? "text/event-stream",
        Connection: "close",
      });
      response.flushHeaders();
      const reader = source.body.getReader();
      for (
        let read = await reader.read();
        !read.done;
        read = await reader.read()
      ) {
        await writeFragments(response, Buffer.from(read.value), plan.fragment);
      }
      response.end();
    } catch (error) {
      if (!disconnected.signal.aborted && !isDisconnect(error)) {
        this.errors.push(String(error));
      }
      response.socket?.destroy();
    } finally {
      response.off("close", abort);
    }
  }

  #stream(response: ServerResponse, body: JsonObject, plan: Plan): void {
    let events = this.#profile.events(body, plan.cached);
    plan.mutateEvents?.(events);
    if (plan.fault === "missing_usage") {
      events = events.filter(
        (event) => typeof event === "string" || !event.usage,
      );
    }
    if (plan.fault === "missing_done") events = events.slice(0, -1);
    response.writeHead(200, {
      "Content-Type":
        plan.fault === "wrong_content_type"
          ? "application/json"
          : "text/event-stream",
      Connection: "close",
    });
    void this.#writeEvents(response, events, plan);
  }

  // Node frames these writes as HTTP chunks, the same way a real SSE runtime does;
  // one write per `fragment` bytes is what puts frame boundaries at arbitrary offsets.
  async #writeEvents(
    response: ServerResponse,
    events: StreamEvents,
    plan: Plan,
  ): Promise<void> {
    try {
      for (const [index, event] of events.entries()) {
        if (plan.fault === "partial_disconnect" && index === 2) {
          return void response.socket?.destroy();
        }
        if (plan.fault === "stall" && index === 2) {
          await within(this.#stopping.promise, STALL_LIMIT_MS);
          return void response.socket?.destroy();
        }
        // A string starting with a colon is an SSE comment, such as a keepalive.
        const line =
          typeof event === "string" && event.startsWith(":")
            ? event
            : `data: ${typeof event === "string" ? event : JSON.stringify(event)}`;
        await writeFragments(
          response,
          Buffer.from(`${line}\r\n\r\n`),
          plan.fragment,
        );
      }
      response.end();
    } catch (error) {
      if (!isDisconnect(error)) this.errors.push(String(error));
      response.socket?.destroy();
    }
  }
}

const replyFailure = (response: ServerResponse, plan: Plan): void => {
  const error: JsonObject = { error: { message: "PRIVATE_RUNTIME_DETAIL" } };
  if (plan.errorUsage !== undefined) error.usage = plan.errorUsage;

  reply(
    response,
    plan.status,
    Buffer.from(JSON.stringify(error)),
    plan.status === 307 ? { Location: "/must-not-follow" } : undefined,
  );
};

const isDisconnect = (error: unknown): boolean =>
  error instanceof Error &&
  "code" in error &&
  typeof error.code === "string" &&
  DISCONNECT_CODES.has(error.code);

const write = (response: ServerResponse, chunk: Buffer): Promise<void> =>
  new Promise((resolve, reject) => {
    response.write(chunk, (error) => (error ? reject(error) : resolve()));
  });

/** A fragment of zero writes the payload whole. */
const writeFragments = async (
  response: ServerResponse,
  payload: Buffer,
  fragment: number,
): Promise<void> => {
  const size = fragment || payload.length;
  for (let offset = 0; offset < payload.length; offset += size) {
    await write(response, payload.subarray(offset, offset + size));
  }
};

const reply = (
  response: ServerResponse,
  status: number,
  body: Buffer,
  extra?: Record<string, string>,
): void => {
  response.writeHead(status, {
    "Content-Type": "application/json",
    "Content-Length": String(body.length),
    ...extra,
  });
  response.end(body);
};

const readBody = (request: IncomingMessage): Promise<string> =>
  new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    let size = 0;
    request.on("data", (chunk: Buffer) => {
      size += chunk.length;
      if (size > BODY_LIMIT) {
        reject(new Error("request body exceeded the bounded mock limit"));
        request.socket.destroy();
        return;
      }
      chunks.push(chunk);
    });
    request.on("error", reject);
    request.on("end", () => {
      if (size === 0) reject(new Error("empty request body"));
      else resolve(Buffer.concat(chunks).toString());
    });
  });
