import { beforeEach, describe, expect, vi } from "vitest";
import { signIn } from "../src/account.js";
import { failureMessage, WizardError } from "../src/errors.js";
import { HttpStatusError, NetworkError } from "../src/http.js";
import * as ui from "../src/ui.js";
import {
  KEY_PATH,
  KEY_SECRET,
  SEND_CODE_PATH,
  SESSION_COOKIE,
  test as it,
  VERIFY_PATH,
} from "./support/auth-stub.js";
import { unreachableUrl } from "./support/http-server.js";
import { rejectionOf } from "./support/rejection.js";

vi.mock("../src/ui.js", () => import("./support/ui-stub.js"));

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(ui.askText)
    .mockResolvedValueOnce(" person@example.com ")
    .mockResolvedValueOnce(" 123456 ");
});

describe("account setup", () => {
  it.for(["signup", "login"] as const)(
    "completes %s through the deployed auth routes with a session",
    async (mode, { authStub }) => {
      expect(await signIn(authStub.baseUrl, mode)).toBe(KEY_SECRET);
      expect(authStub.calls).toEqual([
        {
          path: SEND_CODE_PATH,
          body: { email: "person@example.com", type: "sign-in" },
          cookie: undefined,
        },
        {
          path: VERIFY_PATH,
          body: { email: "person@example.com", otp: "123456" },
          cookie: undefined,
        },
        { path: KEY_PATH, body: null, cookie: SESSION_COOKIE },
      ]);
    },
  );

  it.for([400, 401, 422])(
    "does not mint a key after the code is rejected with HTTP %i",
    async (status, { authStub }) => {
      authStub.state.verifyStatus = status;

      await expect(signIn(authStub.baseUrl, "login")).rejects.toThrow(
        new WizardError(
          "The code was rejected. Run the wizard and request a new one.",
        ),
      );
      expect(authStub.calls).toHaveLength(2);
    },
  );

  it("names verification, not a rejected code, when sign-in is unavailable", async ({
    authStub,
  }) => {
    authStub.state.verifyStatus = 503;

    const error = await rejectionOf(
      signIn(authStub.baseUrl, "login"),
      WizardError,
    );

    expect(error).toEqual(
      new WizardError("Could not verify the code (503): Sign-in failed"),
    );
    expect(failureMessage(error)).toBe(
      "Could not verify the code (503): Sign-in failed (http_503)",
    );
    expect(authStub.calls).toHaveLength(2);
  });

  it.for([
    ["verification", "verifyStatus", "Could not verify the code", 2],
    ["key creation", "keyStatus", "Could not create an API key", 3],
  ] as const)(
    "names %s when its connection drops",
    async ([, step, action, requests], { authStub }) => {
      authStub.state[step] = "reset";

      const error = await rejectionOf(
        signIn(authStub.baseUrl, "signup"),
        WizardError,
      );

      expect(error).toEqual(
        new WizardError(`${action}: The request could not reach the server.`),
      );
      expect(failureMessage(error)).toContain("(network_failure)");
      expect(authStub.calls).toHaveLength(requests);
    },
  );

  it("reports a missing session before attempting key creation", async ({
    authStub,
  }) => {
    authStub.state.cookies = [];

    await expect(signIn(authStub.baseUrl, "signup")).rejects.toThrow(
      "session cookie",
    );
    expect(authStub.calls).toHaveLength(2);
  });

  it.for([
    [
      "signup",
      5_000_000_000,
      "Account ready.",
      ["Current balance: $5.00 (from the API)."],
    ],
    ["signup", 0, "Account ready.", ["Current balance: $0.00 (from the API)."]],
    [
      "login",
      5_000_000_000,
      "Logged in.",
      ["Current balance: $5.00 (from the API)."],
    ],
    ["login", 0, "Logged in.", []],
  ] as const)(
    "reports %s with a balance of %i nano-USD",
    async ([mode, balance, message, balanceLines], { authStub }) => {
      authStub.state.keyBody = {
        ...authStub.state.keyBody,
        balance_nano_usd: balance,
      };

      await signIn(authStub.baseUrl, mode);

      expect(vi.mocked(ui.success).mock.calls).toEqual([[message]]);
      expect(vi.mocked(ui.info).mock.calls).toEqual(
        balanceLines.map((line) => [line]),
      );
    },
  );

  it("reports no balance when the key response omits it", async ({
    authStub,
  }) => {
    authStub.state.keyBody = {
      secret: KEY_SECRET,
      organization_name: "Personal",
    };

    expect(await signIn(authStub.baseUrl, "signup")).toBe(KEY_SECRET);
    expect(ui.success).toHaveBeenCalledWith("Account ready.");
    expect(ui.info).not.toHaveBeenCalled();
  });

  it("stops before verification when the code cannot be sent", async ({
    authStub,
  }) => {
    authStub.state.sendStatus = 503;

    const error = await rejectionOf(
      signIn(authStub.baseUrl, "signup"),
      WizardError,
    );

    expect(error).toEqual(
      new WizardError(
        "Could not send the verification code (503): Mail failed",
      ),
    );
    expect(error.cause).toBeInstanceOf(HttpStatusError);
    expect(authStub.calls).toHaveLength(1);
    expect(ui.askText).toHaveBeenCalledTimes(1);
  });

  it("names key creation when the key service fails", async ({ authStub }) => {
    authStub.state.keyStatus = 503;

    const error = await rejectionOf(
      signIn(authStub.baseUrl, "login"),
      WizardError,
    );

    expect(error).toEqual(
      new WizardError("Could not create an API key (503): Key service failed"),
    );
    expect(error.cause).toMatchObject({ status: 503 });
    expect(authStub.calls).toHaveLength(3);
  });

  it("names the step that could not reach the server", async () => {
    const error = await rejectionOf(
      signIn(await unreachableUrl(), "signup"),
      WizardError,
    );

    expect(error).toEqual(
      new WizardError(
        "Could not send the verification code: The request could not reach the server.",
      ),
    );
    expect(error.cause).toBeInstanceOf(NetworkError);
  });

  it("rejects a key response without a secret", async ({ authStub }) => {
    authStub.state.keyBody = { organization_name: "Personal" };

    await expect(signIn(authStub.baseUrl, "signup")).rejects.toThrow(
      new WizardError("The key response did not include a secret."),
    );
  });
});
