import { beforeEach, describe, expect, it, vi } from "vitest";
import { signIn } from "../src/account.js";
import { readStoredKey } from "../src/credentials.js";
import { resolveKey } from "../src/key.js";
import * as ui from "../src/ui.js";

vi.mock("../src/credentials.js", () => ({ readStoredKey: vi.fn() }));
vi.mock("../src/account.js", () => ({ signIn: vi.fn() }));
vi.mock("../src/ui.js", () => import("./support/ui-stub.js"));

const LABELS = {
  environment: "Use the detected API key",
  stored: "Use the saved API key",
  signup: "Create a free account",
  login: "Log in to an existing account",
  paste: "Paste an existing API key",
};

const DISCOVER = {
  kind: "discover",
  environmentKey: "grad_environment_fixture",
} as const;
const NO_ENVIRONMENT_KEY = { kind: "discover", environmentKey: null } as const;
const API_BASE_URL = "https://api.example.com";
const paths = { home: "/home/fixture", credentials: "/unused" };
const interactive = {
  apiBaseUrl: API_BASE_URL,
  interactive: true,
  offerAccount: true,
  paths,
};
const unattended = { ...interactive, interactive: false };

const menuLabels = (): string[] =>
  vi
    .mocked(ui.selectOption)
    .mock.calls[0]![1].map((option: { label: string }) => option.label);

const chooseLabel = (label: string): void => {
  vi.mocked(ui.selectOption).mockImplementation(async (_message, choices) => {
    const choice = choices.find((option) => option.label === label);
    if (choice === undefined) throw new Error(`No choice labelled ${label}`);
    return choice.value;
  });
};

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(readStoredKey).mockResolvedValue("grad_saved_fixture");
  vi.mocked(ui.askPassword).mockResolvedValue("grad_pasted_fixture");
  vi.mocked(signIn).mockResolvedValue("grad_account_fixture");
});

describe("API key selection", () => {
  it.each([
    ["environment", "grad_environment_fixture"],
    ["stored", "grad_saved_fixture"],
    ["paste", "grad_pasted_fixture"],
    ["signup", "grad_account_fixture"],
    ["login", "grad_account_fixture"],
  ] as const)(
    "honors %s with both detected credentials present",
    async (choice, expected) => {
      chooseLabel(LABELS[choice]);

      expect(await resolveKey(DISCOVER, interactive)).toBe(expected);
      expect(menuLabels()).toEqual(Object.values(LABELS));

      const menu = JSON.stringify(vi.mocked(ui.selectOption).mock.calls[0]);
      expect(menu).not.toContain("grad_environment_fixture");
      expect(menu).not.toContain("grad_saved_fixture");

      if (choice === "signup" || choice === "login") {
        expect(signIn).toHaveBeenCalledWith(API_BASE_URL, choice);
      } else {
        expect(signIn).not.toHaveBeenCalled();
      }
    },
  );

  it("only offers keys that exist", async () => {
    vi.mocked(readStoredKey).mockResolvedValue(null);
    chooseLabel(LABELS.paste);

    await resolveKey(NO_ENVIRONMENT_KEY, interactive);

    expect(menuLabels()).toEqual([LABELS.signup, LABELS.login, LABELS.paste]);
  });

  it("offers no account choices when an account must not be created", async () => {
    chooseLabel(LABELS.paste);

    await resolveKey(DISCOVER, { ...interactive, offerAccount: false });

    expect(menuLabels()).toEqual([
      LABELS.environment,
      LABELS.stored,
      LABELS.paste,
    ]);
  });

  it("honors --key over environment and saved keys without prompting", async () => {
    expect(
      await resolveKey(
        { kind: "key", key: "grad_explicit_fixture" },
        interactive,
      ),
    ).toBe("grad_explicit_fixture");
    expect(ui.selectOption).not.toHaveBeenCalled();
    expect(signIn).not.toHaveBeenCalled();
  });

  it.each(["signup", "login"] as const)(
    "honors --%s over detected keys",
    async (mode) => {
      expect(await resolveKey({ kind: "account", mode }, interactive)).toBe(
        "grad_account_fixture",
      );
      expect(signIn).toHaveBeenCalledWith(API_BASE_URL, mode);
      expect(ui.selectOption).not.toHaveBeenCalled();
    },
  );

  it("prefers the environment key, then the saved key, when unattended", async () => {
    expect(await resolveKey(DISCOVER, unattended)).toBe(
      "grad_environment_fixture",
    );
    expect(await resolveKey(NO_ENVIRONMENT_KEY, unattended)).toBe(
      "grad_saved_fixture",
    );
    expect(ui.selectOption).not.toHaveBeenCalled();
  });

  it("fails without prompting when unattended with no key", async () => {
    vi.mocked(readStoredKey).mockResolvedValue(null);

    await expect(resolveKey(NO_ENVIRONMENT_KEY, unattended)).rejects.toThrow(
      "No Gradiated key found",
    );
    expect(ui.selectOption).not.toHaveBeenCalled();
  });
});
