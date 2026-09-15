import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { resolveKey } from "../src/key.js";
import { readStoredKey } from "../src/credentials.js";
import { resolveAccount } from "../src/account.js";
import * as ui from "../src/ui.js";

vi.mock("../src/credentials.js", () => ({ readStoredKey: vi.fn() }));
vi.mock("../src/account.js", () => ({ resolveAccount: vi.fn() }));
vi.mock("../src/ui.js", () => ({
  selectOption: vi.fn(),
  askPassword: vi.fn(),
  fail: (message: string) => {
    throw new Error(message);
  },
}));

const options = { yes: false, key: undefined, mode: "auto" };
const targets = {
  apiBaseUrl: "https://api.example.com",
  inferenceBaseUrl: "https://api.example.com",
};

beforeEach(() => {
  vi.resetAllMocks();
  vi.stubEnv("GRADIATED_API_KEY", "grad_environment_fixture");
  vi.mocked(readStoredKey).mockResolvedValue("grad_saved_fixture");
  vi.mocked(ui.askPassword).mockResolvedValue("grad_pasted_fixture");
  vi.mocked(resolveAccount).mockResolvedValue({
    apiKey: "grad_account_fixture",
    organizationName: "Personal",
    balanceNanoUsd: 0,
  });
});
afterEach(() => vi.unstubAllEnvs());

describe("API key selection", () => {
  it.each([
    ["environment", "grad_environment_fixture"],
    ["stored", "grad_saved_fixture"],
    ["paste", "grad_pasted_fixture"],
    ["signup", "grad_account_fixture"],
    ["login", "grad_account_fixture"],
  ])(
    "honors %s with both detected credentials present",
    async (choice, expected) => {
      vi.mocked(ui.selectOption).mockResolvedValue(choice);
      expect(await resolveKey(options, targets)).toBe(expected);
      const menu = vi.mocked(ui.selectOption).mock.calls[0]![1];
      expect(menu.map((entry) => entry.value)).toEqual([
        "environment",
        "stored",
        "signup",
        "login",
        "paste",
      ]);
      expect(JSON.stringify(menu)).not.toContain("grad_environment_fixture");
      expect(JSON.stringify(menu)).not.toContain("grad_saved_fixture");
      if (choice === "signup" || choice === "login") {
        expect(resolveAccount).toHaveBeenCalledWith(targets, choice);
      } else {
        expect(resolveAccount).not.toHaveBeenCalled();
      }
    },
  );

  it("only offers keys that exist", async () => {
    vi.stubEnv("GRADIATED_API_KEY", "");
    vi.mocked(readStoredKey).mockResolvedValue(null);
    vi.mocked(ui.selectOption).mockResolvedValue("paste");
    await resolveKey(options, targets);
    expect(
      vi.mocked(ui.selectOption).mock.calls[0]![1].map((entry) => entry.value),
    ).toEqual(["signup", "login", "paste"]);
  });

  it("honors --key over environment and saved keys without prompting", async () => {
    expect(
      await resolveKey({ ...options, key: "grad_explicit_fixture" }, targets),
    ).toBe("grad_explicit_fixture");
    expect(ui.selectOption).not.toHaveBeenCalled();
    expect(resolveAccount).not.toHaveBeenCalled();
  });

  it.each(["signup", "login"])(
    "honors --%s over detected keys",
    async (mode) => {
      expect(await resolveKey({ ...options, mode }, targets)).toBe(
        "grad_account_fixture",
      );
      expect(resolveAccount).toHaveBeenCalledWith(targets, mode);
      expect(ui.selectOption).not.toHaveBeenCalled();
    },
  );

  it("keeps --yes non-interactive with environment-first precedence", async () => {
    expect(await resolveKey({ ...options, yes: true }, targets)).toBe(
      "grad_environment_fixture",
    );
    vi.stubEnv("GRADIATED_API_KEY", "");
    expect(await resolveKey({ ...options, yes: true }, targets)).toBe(
      "grad_saved_fixture",
    );
    expect(ui.selectOption).not.toHaveBeenCalled();
  });

  it("fails without prompting when --yes has no key", async () => {
    vi.stubEnv("GRADIATED_API_KEY", "");
    vi.mocked(readStoredKey).mockResolvedValue(null);
    await expect(
      resolveKey({ ...options, yes: true }, targets),
    ).rejects.toThrow("No Gradiated key found");
    expect(ui.selectOption).not.toHaveBeenCalled();
  });
});
