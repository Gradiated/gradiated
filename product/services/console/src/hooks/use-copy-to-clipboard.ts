import { useEffect, useRef, useState } from "react";

const RESET_AFTER_MS = 1_500;

export type CopyState = "idle" | "copied" | "failed";

export const copyLabel = (state: CopyState, idleLabel: string) => {
  if (state === "copied") return "Copied";
  if (state === "failed") return "Copy failed";

  return idleLabel;
};

export const useCopyToClipboard = () => {
  const [state, setState] = useState<CopyState>("idle");
  const resetTimer = useRef<number | undefined>(undefined);

  useEffect(() => () => window.clearTimeout(resetTimer.current), []);

  const copy = async (text: string) => {
    window.clearTimeout(resetTimer.current);

    try {
      await navigator.clipboard.writeText(text);
      setState("copied");
    } catch (error) {
      console.error(
        "clipboard_write_failed",
        error instanceof Error ? error.name : typeof error,
      );
      setState("failed");
    }

    resetTimer.current = window.setTimeout(
      () => setState("idle"),
      RESET_AFTER_MS,
    );
  };

  return { state, copy };
};
