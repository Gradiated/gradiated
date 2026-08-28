import { useState } from "react";
import type { ReactElement } from "react";

import { useDocsSession } from "./DocsSession";

const copyText = async (value: string): Promise<void> => {
  await navigator.clipboard.writeText(value);
};

export const DocsApiKeyAction = (): ReactElement | null => {
  const session = useDocsSession();
  const [creating, setCreating] = useState(false);
  const [copied, setCopied] = useState(false);

  const copyApiKey = async (key: string): Promise<void> => {
    await copyText(key);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  };

  const createAndCopy = async (): Promise<void> => {
    setCreating(true);
    try {
      const key = await session.createDocsKey();
      if (key) await copyApiKey(key);
    } finally {
      setCreating(false);
    }
  };

  const actionClass =
    "cursor-pointer rounded-md border border-ink bg-ink px-3 py-1.5 font-site-mono text-[9px] font-medium uppercase tracking-[0.06em] text-paper hover:bg-transparent hover:text-ink disabled:cursor-not-allowed disabled:opacity-50";

  if (session.status !== "ready" || !session.workspace) return null;

  if (session.apiKey) {
    return (
      <button
        className={actionClass}
        onClick={() => void copyApiKey(session.apiKey!)}
        type="button"
      >
        {copied ? "Copied" : "Copy API key"}
      </button>
    );
  }

  if (!session.canManageKeys) return null;

  return (
    <button
      className={actionClass}
      disabled={creating}
      onClick={() => void createAndCopy()}
      type="button"
    >
      {creating ? "Creating…" : copied ? "Copied" : "Create API key"}
    </button>
  );
};
