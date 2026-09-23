import type { IncomingMessage, ServerResponse } from "node:http";
import { betterAuth } from "better-auth";
import { memoryAdapter } from "better-auth/adapters/memory";
import { emailOTP } from "better-auth/plugins";
import { KEY_PATH, KEY_SECRET } from "./auth-stub.js";
import { test as serverTest } from "./http-server.js";

export interface AuthActivity {
  code: string;
  deliveries: number;
  keyRequests: number;
  signedInUsers: string[];
}

export interface BetterAuthServer {
  baseUrl: string;
  activity: AuthActivity;
}

type Auth = ReturnType<typeof createAuth>;

const createAuth = (baseUrl: string, deliver: (otp: string) => void) =>
  betterAuth({
    baseURL: baseUrl,
    basePath: "/api/auth",
    secret: "test-only-auth-secret-at-least-thirty-two-characters",
    database: memoryAdapter({
      user: [],
      session: [],
      account: [],
      verification: [],
    }),
    // Better Auth disables origin checks under NODE_ENV=test by default.
    // Keep production protection enabled so missing headers cannot slip through.
    advanced: { disableOriginCheck: false, disableCSRFCheck: false },
    plugins: [
      emailOTP({
        expiresIn: 600,
        otpLength: 6,
        storeOTP: "hashed",
        sendVerificationOTP: async ({ otp }) => deliver(otp),
      }),
    ],
  });

const toHeaders = (request: IncomingMessage): Headers => {
  const headers = new Headers();

  for (const [name, value] of Object.entries(request.headers)) {
    if (value === undefined) continue;

    headers.set(name, Array.isArray(value) ? value.join(", ") : value);
  }

  return headers;
};

const toFetchRequest = async (
  request: IncomingMessage,
  baseUrl: string,
): Promise<Request> => {
  let body = "";
  for await (const chunk of request) body += String(chunk);

  return new Request(`${baseUrl}${request.url ?? "/"}`, {
    method: request.method ?? "GET",
    headers: toHeaders(request),
    ...(body ? { body } : {}),
  });
};

const sendFetchResponse = async (
  response: ServerResponse,
  result: Response,
): Promise<void> => {
  response.statusCode = result.status;
  result.headers.forEach((value, name) => {
    if (name !== "set-cookie") response.setHeader(name, value);
  });

  const cookies = result.headers.getSetCookie();
  if (cookies.length > 0) response.setHeader("set-cookie", cookies);

  response.end(await result.text());
};

const createKey = async (
  auth: Auth,
  baseUrl: string,
  activity: AuthActivity,
  request: IncomingMessage,
  response: ServerResponse,
): Promise<void> => {
  activity.keyRequests++;
  const headers = toHeaders(request);
  const session = await auth.api.getSession({ headers });
  response.setHeader("content-type", "application/json");

  if (session === null || headers.get("origin") !== baseUrl) {
    response.writeHead(401).end('{"message":"Missing session or origin"}');
    return;
  }

  activity.signedInUsers.push(session.user.id);
  response.writeHead(201).end(
    JSON.stringify({
      secret: KEY_SECRET,
      organization_name: "Personal",
      balance_nano_usd: 0,
    }),
  );
};

export const test = serverTest.extend(
  "betterAuthServer",
  async ({ serve }): Promise<BetterAuthServer> => {
    const activity: AuthActivity = {
      code: "",
      deliveries: 0,
      keyRequests: 0,
      signedInUsers: [],
    };

    // Better Auth needs the server's base URL, so the handler reads `auth`
    // only once requests arrive.
    const { baseUrl } = await serve(async (request, response) => {
      try {
        if (request.url === KEY_PATH) {
          await createKey(auth, baseUrl, activity, request, response);
          return;
        }

        const result = await auth.handler(
          await toFetchRequest(request, baseUrl),
        );
        await sendFetchResponse(response, result);
      } catch {
        response.writeHead(500).end('{"message":"Test auth server failed"}');
      }
    });
    const auth = createAuth(baseUrl, (otp) => {
      activity.code = otp;
      activity.deliveries++;
    });

    return { baseUrl, activity };
  },
);
