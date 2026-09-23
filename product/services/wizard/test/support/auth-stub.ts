import type { RequestListener } from "node:http";
import { test as serverTest } from "./http-server.js";

export const SEND_CODE_PATH = "/api/auth/email-otp/send-verification-otp";
export const VERIFY_PATH = "/api/auth/sign-in/email-otp";
export const KEY_PATH = "/api/v1/wizard/key";

export const SESSION_COOKIE =
  "better-auth.session_token=fixture-session; better-auth.session_data=fixture-data";

export const KEY_SECRET = "grad_fixture";

type StubStatus = number | "reset";

export interface AuthStubState {
  sendStatus: StubStatus;
  verifyStatus: StubStatus;
  keyStatus: StubStatus;
  keyBody: Record<string, unknown>;
  cookies: readonly string[];
}

export interface AuthCall {
  path: string;
  body: unknown;
  cookie: string | undefined;
}

export interface AuthStub {
  baseUrl: string;
  state: AuthStubState;
  calls: AuthCall[];
}

interface StubReply {
  status: StubStatus;
  body: unknown;
  cookies: readonly string[];
}

const initialState = (): AuthStubState => ({
  sendStatus: 200,
  verifyStatus: 200,
  keyStatus: 201,
  keyBody: {
    secret: KEY_SECRET,
    organization_name: "Personal",
    balance_nano_usd: 5_000_000_000,
  },
  cookies: [
    "better-auth.session_token=fixture-session; Path=/; HttpOnly; SameSite=Lax",
    "better-auth.session_data=fixture-data; Expires=Wed, 16 Sep 2026 00:00:00 GMT; Path=/; HttpOnly",
  ],
});

const reply = (
  state: AuthStubState,
  path: string,
  cookie: string | undefined,
): StubReply => {
  if (path === SEND_CODE_PATH) {
    const sent = state.sendStatus === 200;

    return {
      status: state.sendStatus,
      body: sent ? { success: true } : { message: "Mail failed" },
      cookies: [],
    };
  }

  if (path === VERIFY_PATH) {
    const verified = state.verifyStatus === 200;

    return {
      status: state.verifyStatus,
      body: verified
        ? { user: { id: "fixture-user" } }
        : { message: "Sign-in failed" },
      cookies: state.cookies,
    };
  }

  if (path === KEY_PATH && cookie === SESSION_COOKIE) {
    const created = state.keyStatus === 201;

    return {
      status: state.keyStatus,
      body: created ? state.keyBody : { message: "Key service failed" },
      cookies: [],
    };
  }

  return { status: 401, body: { message: "Missing session" }, cookies: [] };
};

const handler =
  (state: AuthStubState, calls: AuthCall[]): RequestListener =>
  async (request, response) => {
    let raw = "";
    for await (const chunk of request) raw += String(chunk);

    const path = request.url ?? "/";
    const { cookie } = request.headers;
    calls.push({ path, body: raw ? JSON.parse(raw) : null, cookie });

    const { status, body, cookies } = reply(state, path, cookie);
    if (status === "reset") {
      request.socket.destroy();
      return;
    }

    response.writeHead(status, {
      "content-type": "application/json",
      ...(cookies.length > 0 ? { "set-cookie": [...cookies] } : {}),
    });
    response.end(JSON.stringify(body));
  };

export const test = serverTest.extend(
  "authStub",
  async ({ serve }): Promise<AuthStub> => {
    const state = initialState();
    const calls: AuthCall[] = [];
    const { baseUrl } = await serve(handler(state, calls));

    return { baseUrl, state, calls };
  },
);
