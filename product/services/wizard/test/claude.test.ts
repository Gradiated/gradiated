import { afterEach, describe, expect, it, vi } from "vitest";
import { applyNowCommand, currentShell } from "../src/agents/claude.js";

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("currentShell", () => {
  it("maps $SHELL to the known POSIX shells", () => {
    if (process.platform === "win32") return;
    vi.stubEnv("SHELL", "/bin/zsh");
    expect(currentShell()).toBe("zsh");
    vi.stubEnv("SHELL", "/usr/bin/fish");
    expect(currentShell()).toBe("fish");
    vi.stubEnv("SHELL", "/bin/bash");
    expect(currentShell()).toBe("bash");
  });

  it("reports unknown for shells without profile support", () => {
    if (process.platform === "win32") return;
    vi.stubEnv("SHELL", "/bin/tcsh");
    expect(currentShell()).toBe("unknown");
    vi.stubEnv("SHELL", "");
    expect(currentShell()).toBe("unknown");
  });
});

describe("applyNowCommand", () => {
  it("sources the profile the wizard actually updated", () => {
    expect(applyNowCommand(["/home/u/.zshrc"], "zsh")).toBe(
      "source /home/u/.zshrc",
    );
    expect(applyNowCommand([], "zsh")).toBeNull();
  });

  it("prefers .bash_profile for bash, whose login shells ignore .bashrc", () => {
    expect(
      applyNowCommand(["/home/u/.bashrc", "/home/u/.bash_profile"], "bash"),
    ).toBe("source /home/u/.bash_profile");
    expect(applyNowCommand(["/home/u/.bashrc"], "bash")).toBe(
      "source /home/u/.bashrc",
    );
    expect(applyNowCommand([], "bash")).toBeNull();
  });

  it("sources the fish config", () => {
    expect(applyNowCommand(["/home/u/.config/fish/config.fish"], "fish")).toBe(
      "source /home/u/.config/fish/config.fish",
    );
    expect(applyNowCommand([], "fish")).toBeNull();
  });

  it("returns Windows session PATH commands that need no profile", () => {
    expect(applyNowCommand([], "powershell")).toContain(".gradiated\\bin");
    expect(applyNowCommand([], "cmd")).toContain(".gradiated\\bin");
  });

  it("returns null for unknown shells so the fallback message is used", () => {
    expect(applyNowCommand(["/home/u/.zshrc"], "unknown")).toBeNull();
  });
});
