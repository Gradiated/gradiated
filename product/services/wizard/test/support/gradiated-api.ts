import type { ServerResponse } from "node:http";
import { DEFAULT_MODEL, FIXTURE_CATALOG } from "./catalog.js";
import {
  startServer,
  test as serverTest,
  type RunningServer,
  type Serve,
} from "./http-server.js";

export interface GradiatedApi extends RunningServer {
  authorizations: readonly string[];
}

export interface GradiatedApiOptions {
  acceptedKeys: readonly string[];
  catalogStatus?: number;
  catalog?: unknown;
}

const sendProblem = (
  response: ServerResponse,
  status: number,
  problem: { slug: string; title: string; detail: string; code: string },
): void => {
  response.writeHead(status, { "content-type": "application/problem+json" });
  response.end(
    JSON.stringify({
      type: `https://gradiated.com/problems/${problem.slug}`,
      title: problem.title,
      status,
      detail: problem.detail,
      code: problem.code,
      request_id: "stub",
    }),
  );
};

const usage = (outputTokens: number) => ({
  input_tokens: 1,
  output_tokens: outputTokens,
  total_tokens: 1 + outputTokens,
  input_tokens_details: { cached_tokens: 0 },
  output_tokens_details: { reasoning_tokens: 0 },
});

const readyText = { type: "output_text", text: "ready" };

const completedMessage = {
  type: "message",
  role: "assistant",
  status: "completed",
  content: [readyText],
};

const RESPONSE_EVENTS = [
  {
    type: "response.created",
    response: {
      id: "resp_wizard",
      object: "response",
      status: "in_progress",
      model: DEFAULT_MODEL,
      output: [],
      usage: usage(0),
    },
  },
  {
    type: "response.output_item.added",
    output_index: 0,
    item: {
      type: "message",
      id: "msg_0",
      role: "assistant",
      status: "in_progress",
      content: [],
    },
  },
  {
    type: "response.content_part.added",
    output_index: 0,
    content_index: 0,
    part: { type: "output_text", text: "" },
  },
  {
    type: "response.output_text.delta",
    output_index: 0,
    content_index: 0,
    delta: "ready",
  },
  {
    type: "response.content_part.done",
    output_index: 0,
    content_index: 0,
    part: readyText,
  },
  {
    type: "response.output_item.done",
    output_index: 0,
    item: completedMessage,
  },
  {
    type: "response.completed",
    response: {
      id: "resp_wizard",
      object: "response",
      status: "completed",
      incomplete_details: null,
      model: DEFAULT_MODEL,
      output: [completedMessage],
      usage: usage(1),
    },
  },
];

const RESPONSE_STREAM = RESPONSE_EVENTS.map(
  (event) => `event: ${event.type}\ndata: ${JSON.stringify(event)}\n\n`,
).join("");

export const startGradiatedApi = async (
  options: GradiatedApiOptions,
  serve: Serve = startServer,
): Promise<GradiatedApi> => {
  const catalogStatus = options.catalogStatus ?? 200;
  const catalog = options.catalog ?? FIXTURE_CATALOG;
  const authorizations: string[] = [];

  const server = await serve((request, response) => {
    authorizations.push(request.headers.authorization ?? "");
    const { pathname } = new URL(request.url ?? "/", "http://127.0.0.1");
    const accepted = options.acceptedKeys.some(
      (key) => request.headers.authorization === `Bearer ${key}`,
    );

    if (!accepted) {
      sendProblem(response, 401, {
        slug: "unauthenticated",
        title: "Authentication required",
        detail: "The API key was rejected.",
        code: "unauthenticated",
      });
      return;
    }

    if (pathname === "/models" && catalogStatus !== 200) {
      sendProblem(response, catalogStatus, {
        slug: "unavailable",
        title: "Service unavailable",
        detail: "The catalog is temporarily unavailable.",
        code: "unavailable",
      });
      return;
    }

    if (pathname === "/models") {
      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify(catalog));
      return;
    }

    if (pathname === "/v1/responses") {
      response.writeHead(200, {
        "content-type": "text/event-stream",
        "cache-control": "no-cache",
      });
      response.end(RESPONSE_STREAM);
      return;
    }

    sendProblem(response, 404, {
      slug: "not-found",
      title: "Not found",
      detail: "Not found.",
      code: "not_found",
    });
  });

  return { ...server, authorizations };
};

export const test = serverTest.extend(
  "serveGradiatedApi",
  async ({ serve }) =>
    (options: GradiatedApiOptions): Promise<GradiatedApi> =>
      startGradiatedApi(options, serve),
);
